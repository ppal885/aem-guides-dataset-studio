#!/usr/bin/env python3
"""Tell QE when new evidence arrives on a ticket after its UAC was posted.

A UAC written before the root cause, the fix, an API contract or a design document existed can describe
the wrong thing. When any of these arrives later, the UAC should be reviewed. This script finds those
tickets and sends one alert (on the configured alert ticket, mentioning the configured people) listing
them. It never edits or comments on the ticket itself and never changes the UAC.

For each ticket in scope that carries the posted label:
  1. find when the Acceptance Criteria field last changed (Jira changelog);
  2. find what people other than the automation added after that time: comments that report a root
     cause or a fix, comments that link a wiki page (a design document or specification), comments that
     give an API contract or design in their text (an HTTP method with a path, a request/response body,
     status codes, an API spec), comments that decide what to build (a numbered list of steps, "let's
     create ...", a scope decision), and attachments (an API contract, a design, a screenshot);
  3. find merged commits in the product repositories (config "staleness_repos", else STARLING_REPO_PATH and
     XML_EDITOR_REPO_PATH) whose subject names the ticket and whose pull request number or hash the
     Acceptance Criteria do not cite - a fix can be merged with no Jira comment at all;
  4. alert once per such comment, attachment or commit (remembered in <output_dir>/staleness-state.json).

Scope JQL: config "staleness_jql", else every ticket with the posted label, limited to tickets updated in
the last "staleness_days" days (default 7).
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import linked_docs  # noqa: E402

STATE_FILE = "staleness-state.json"
# The same signal the skill uses to decide whether a UAC was written with the root cause known.
FIX_SIGNAL = common.import_skill_module("uac_completeness_check").FIX_SIGNAL
# An API contract or design written in a comment: an upper-case HTTP method with a path or URL, a request
# body/payload/schema, a list of status codes, or a named API spec / design document. A passing mention is not
# enough: a repro step ("Delete /content/dam/...", "I get ...") or an error ("status code 500", "the response
# body is empty") is not a contract.
CONTRACT_SIGNAL = re.compile(
    r"(?-i:\b(?:GET|POST|PUT|PATCH|DELETE)\s+(?:/|https?://)\S+)"
    r"|\bAPI\s+(?:contract|spec(?:ification)?|design)\b|\brequest\s+(?:body|payload|schema)\b"
    r"|\bresponse\s+schema\b|\bstatus\s+codes?\s*[:=-]?\s*\d{3}\s*(?:,|/|and|or)\s*\d{3}"
    r"|\b(?:swagger|openapi)\b|\btechnical\s+design\b|\bdesign\s+doc(?:ument)?\b", re.IGNORECASE)
# A decision on what to build, written after the UAC: a numbered list of what to do, "let's create ...", or a
# scope decision. GUIDES-58680 got "lets create a sample extension for this with following - 1. ... 2. ... 3. ..."
# from the product owner; had it come after the UAC, none of the signals above would have caught it.
DECISION_SIGNAL = re.compile(
    r"(?m)^\s*(?:\d{1,2}[.)]|#)\s+\w"
    r"|\blet'?s\s+(?:create|build|implement|go\s+with|keep|drop|add|remove|make|not)\b"
    r"|\b(?:out\s+of\s+scope|in\s+scope|scope\s+is|we\s+(?:have\s+)?decided|decision\s+is|agreed\s+to|we\s+will\s+not"
    r"|won'?t\s+(?:support|fix|implement))\b", re.IGNORECASE)
DECISION_MIN_WORDS = 8
AC_FIELD_NAME = "Acceptance Criteria"


def staleness_jql(config: dict) -> str:
    """Every ticket that carries the posted label and changed recently. The release scope is not used: a
    posted ticket without an unreleased fix version (GUIDES-51870) got its root cause and fix PR hours after
    the UAC, and was never checked."""
    if config.get("staleness_jql"):
        return config["staleness_jql"]
    days = int(config.get("staleness_days", 7))
    return f'labels = "{config["labels"]["posted"]}" AND updated >= -{days}d'


def _when(value: str) -> datetime.datetime | None:
    """A Jira timestamp (2026-01-10T10:00:00.000+0000) as an aware datetime, or None."""
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f%z")
    except (TypeError, ValueError):
        return None


def _after(created: str, since: str) -> bool:
    """True when `created` is later than `since`, comparing real times, not strings (offsets can differ)."""
    a, b = _when(created), _when(since)
    return a > b if a and b else bool(since) and created > since


def _automation(author: str, own_name) -> bool:
    """own_name is the automation's Jira user, or a set of generator users."""
    return author in own_name if isinstance(own_name, (set, frozenset)) else author == own_name


def last_ac_change(issue: dict, field_id: str) -> str:
    """ISO time of the last change to the Acceptance Criteria field, or "" when the changelog has none."""
    latest = ""
    for history in (issue.get("changelog") or {}).get("histories") or []:
        for item in history.get("items") or []:
            if item.get("fieldId") == field_id or item.get("field") == AC_FIELD_NAME:
                created = str(history.get("created") or "")
                if not latest or _after(created, latest):
                    latest = created
    return latest


# A comment the Vision agent posted through a person's account: "[Vision] PR created — xmleditor · via Copilot".
# Its fix or PR still makes the UAC stale, but QE should see that it is an automated proposal, not a developer's word.
VISION_COMMENT = re.compile(r"^\s*(?:h\d\.\s*)?\[?\s*vision\b", re.I)


def _reporter(author: str, body: str) -> str:
    """Who to name in the alert: the Vision agent when the comment carries its tag, else the author."""
    return f"the Vision agent (posted by {author})" if VISION_COMMENT.match(body or "") else author


def fix_comments_after(issue: dict, since: str, own_name: str = "") -> list[dict]:
    comments = ((issue.get("fields") or {}).get("comment") or {}).get("comments") or []
    found = []
    for comment in comments:
        author = str((comment.get("author") or {}).get("name") or "")
        created = str(comment.get("created") or "")
        body = comment.get("body") or ""
        if since and _after(created, since) and not _automation(author, own_name) and FIX_SIGNAL.search(body):
            found.append({"id": str(comment.get("id")), "author": author, "created": created,
                          "reporter": _reporter(author, body)})
    return found


def new_evidence_after(issue: dict, since: str, own_name: str = "",
                       hosts: tuple[str, ...] = linked_docs.DEFAULT_HOSTS) -> list[dict]:
    """Attachments, and comments that link a wiki page or give an API contract, added by people after the UAC
    last changed."""
    fields = issue.get("fields") or {}
    found = []
    for comment in (fields.get("comment") or {}).get("comments") or []:
        author = str((comment.get("author") or {}).get("name") or "")
        created = str(comment.get("created") or "")
        if not since or not _after(created, since) or _automation(author, own_name):
            continue
        body = comment.get("body") or ""
        if linked_docs.find_links({"description": body}, "", hosts):
            found.append({"id": str(comment.get("id")), "author": author, "created": created,
                          "what": "a wiki page link (design document or specification)"})
        elif CONTRACT_SIGNAL.search(body):
            found.append({"id": str(comment.get("id")), "author": author, "created": created,
                          "what": "an API contract or design in a comment"})
        elif DECISION_SIGNAL.search(body) and len(body.split()) >= DECISION_MIN_WORDS:
            found.append({"id": str(comment.get("id")), "author": author, "created": created,
                          "what": "a decision on what to build (a list of steps or a scope decision) in a comment"})
    for attachment in fields.get("attachment") or []:
        author = str((attachment.get("author") or {}).get("name") or "")
        created = str(attachment.get("created") or "")
        if since and _after(created, since) and not _automation(author, own_name):
            found.append({"id": f"attachment:{attachment.get('id')}", "author": author, "created": created,
                          "what": f"the attachment {attachment.get('filename')}"})
    return found


# Merged commits that name the ticket in the product repositories. A fix can be merged without any Jira comment
# (GUIDES-55887: the UAC followed an unmerged PR from a bot comment while a different fix, #8280, was already in
# develop), so the watcher also reads the repositories' history. The repositories come from config
# "staleness_repos" ({"path": ..., "ref": ...}), else the code researcher's *_REPO_PATH variables.
REPO_PATH_VARIABLES = ("STARLING_REPO_PATH", "XML_EDITOR_REPO_PATH")
DEFAULT_REF = "origin/develop"
_PR_NUMBER = re.compile(r"\(#(\d+)\)|\bpull/(\d+)\b|#(\d+)\b")


def staleness_repos(config: dict) -> list[dict]:
    """[{"path", "ref"}] for every configured product repository that exists on this machine."""
    configured = config.get("staleness_repos")
    if configured is None:
        configured = [{"path": os.environ.get(name, "")} for name in REPO_PATH_VARIABLES]
    repos = []
    for entry in configured:
        entry = {"path": entry} if isinstance(entry, str) else dict(entry or {})
        path = str(entry.get("path") or "").strip()
        if path and Path(path).is_dir():
            repos.append({"path": path, "ref": str(entry.get("ref") or DEFAULT_REF)})
    return repos


def _key_pattern(key: str) -> re.Pattern:
    """GUIDES-55887 also matches "Guides- 55887", "GUIDES_55887" and "guides 55887" in a commit subject."""
    project, _, number = key.partition("-")
    return re.compile(rf"\b{re.escape(project)}[-_ ]*{re.escape(number)}(?!\d)", re.I)


def fetch_repos(repos: list[dict], logger) -> None:
    """Bring each repository's remote branches up to date once per run; a failed fetch keeps the old refs."""
    for repo in repos:
        try:
            run = subprocess.run(["git", "-C", repo["path"], "fetch", "--quiet", "origin"], capture_output=True,
                                 text=True, encoding="utf-8", errors="replace", timeout=300)
            if run.returncode != 0:
                logger.warning("fetch failed in %s: %s", repo["path"], run.stderr.strip()[:200])
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("fetch failed in %s: %s", repo["path"], exc)


def merged_commits(repo: dict, key: str, logger) -> list[dict]:
    """Commits on the repository's ref whose subject names the ticket, newest first. A repository that cannot
    be read gives no commits and a log line, never a crash."""
    path, ref = repo["path"], repo["ref"]
    number = key.partition("-")[2]
    try:
        run = subprocess.run(["git", "-C", path, "log", ref, "-F", f"--grep={number}",
                              "--format=%H%x09%cI%x09%an%x09%s"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("%s: could not read %s at %s: %s", key, path, ref, exc)
        return []
    if run.returncode != 0:
        logger.warning("%s: could not read %s at %s: %s", key, path, ref, run.stderr.strip()[:200])
        return []
    pattern = _key_pattern(key)
    commits = []
    for line in run.stdout.splitlines():
        sha, committed, author, subject = (line.split("\t", 3) + ["", "", ""])[:4]
        if not pattern.search(subject):
            continue  # the key was only in the body (a revert or a long list); the subject must name it
        numbers = [n for group in _PR_NUMBER.findall(subject) for n in group if n]
        commits.append({"sha": sha, "committed": committed, "author": author, "subject": subject,
                        "pr": numbers[0] if numbers else "", "repo": Path(path).name})
    return commits


def unmentioned_commits(commits: list[dict], ac_text: str) -> list[dict]:
    """Commits the Acceptance Criteria do not cite, by pull request number (#8280) or short hash."""
    text = ac_text or ""
    found = []
    for commit in commits:
        cited_pr = commit["pr"] and re.search(rf"#{commit['pr']}\b", text)
        cited_sha = commit["sha"][:7] and commit["sha"][:7] in text
        if not (cited_pr or cited_sha):
            found.append(commit)
    return found


def stale_lines(config: dict, jira, logger, keys: list[str], state: dict, own_name="") -> list[str]:
    """Alert lines for new evidence on each ticket. The ids alerted are added to `state`; the caller saves it
    only once the alert was delivered. A ticket that cannot be read becomes an alert line of its own, so the
    other tickets' alerts are not lost."""
    field_id = config["acceptance_criteria_field"]
    hosts = tuple(config.get("linked_doc_hosts") or linked_docs.DEFAULT_HOSTS)
    if isinstance(own_name, str):
        own_name = {own_name, *(config.get("learning_generator_users") or [])} - {""}
    repos = staleness_repos(config)
    if repos and config.get("staleness_fetch", True):
        fetch_repos(repos, logger)
    lines = []
    for key in keys:
        try:
            issue = jira._json("GET", f"/rest/api/2/issue/{key}?expand=changelog&fields=comment,attachment,{field_id}")
        except Exception as exc:  # noqa: BLE001 - one ticket never hides the others' alerts
            logger.exception("%s: could not read the ticket", key)
            lines.append(f"{key}: could not be checked for new evidence ({type(exc).__name__}: {exc})")
            continue
        since = last_ac_change(issue, field_id)
        if not since:
            continue
        seen = set(state.get(key) or [])
        for comment in fix_comments_after(issue, since, own_name):
            if comment["id"] in seen:
                continue
            lines.append(f"{key}: a root cause or fix was reported by {comment.get('reporter') or comment['author']} "
                         f"on {comment['created'][:10]}, "
                         f"after the Acceptance Criteria were last changed on {since[:10]}; review the UAC")
            seen.add(comment["id"])
        for item in new_evidence_after(issue, since, own_name, hosts):
            if item["id"] in seen:
                continue
            lines.append(f"{key}: {item['author']} added {item['what']} on {item['created'][:10]}, after the "
                         f"Acceptance Criteria were last changed on {since[:10]}; review the UAC against it")
            seen.add(item["id"])
        ac_text = str((issue.get("fields") or {}).get(field_id) or "")
        for repo in repos:
            for commit in unmentioned_commits(merged_commits(repo, key, logger), ac_text):
                commit_id = f"commit:{commit['sha'][:12]}"
                if commit_id in seen:
                    continue
                pr = f" (#{commit['pr']})" if commit["pr"] else ""
                lines.append(f"{key}: a commit naming the ticket is merged in {commit['repo']} {repo['ref']}{pr} by "
                             f"{commit['author']} on {commit['committed'][:10]}: \"{commit['subject'][:120]}\"; the "
                             "Acceptance Criteria do not cite it; review the UAC against the merged change")
                seen.add(commit_id)
        if seen:
            state[key] = sorted(seen)
        logger.info("%s: UAC last changed %s", key, since[:19])
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=common.REPO_ROOT / "backend" / ".env")
    parser.add_argument("--dry-run", action="store_true", help="find stale tickets but send no alert")
    args = parser.parse_args(argv)

    common.load_env_file(args.env_file)
    config = common.load_config(args.config)
    out = Path(config["output_dir"])
    logger = common.setup_logging(out / "logs", "uac-staleness")
    run_id, started = common.new_run_id(), time.time()
    state_path = out / STATE_FILE
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    except ValueError:
        state = {}
    lines: list[str] = []
    exit_code = 0
    jira = None
    try:
        jira = common.JiraClient.from_env()
        own_name = str((jira.myself() or {}).get("name") or "")
        keys = jira.search_keys(staleness_jql(config), int(config.get("max_tickets", 100)))
        logger.info("posted tickets to check: %s", ", ".join(keys) or "none")
        lines = stale_lines(config, jira, logger, keys, state, own_name)
    except Exception as exc:  # noqa: BLE001 - record and alert on anything that stops the run
        logger.exception("run %s stopped", run_id)
        lines.append(f"The staleness check stopped before finishing: {type(exc).__name__}: {exc}")
        exit_code = 3
    for line in lines:
        logger.warning("stale: %s", line)
    result = "DRY_RUN" if args.dry_run else "NOT_SENT"
    if not args.dry_run and jira is not None:
        result = common.send_alert(config, jira, logger, "uac-staleness", run_id, lines)
        # Remember what was alerted only once QE has it; a failed or unconfigured alert is tried again next run.
        if result in ("POSTED", "NONE", "SUPPRESSED"):
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        else:
            logger.warning("alert %s: the alerted comments are not marked as seen", result)
    # The release page lists these alerts and says when they did not reach anyone: from 2026-10-01 every alert
    # was NOT_CONFIGURED (no alerts.ticket) and only this log knew.
    common.append_run_record(out, {
        "run_id": run_id, "tool": "uac-staleness", "dry_run": args.dry_run,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started)),
        "seconds": round(time.time() - started), "exit_code": exit_code, "alerts": lines,
        "alert_result": result})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
