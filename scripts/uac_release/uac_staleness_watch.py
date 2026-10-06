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
     status codes, an API spec), and attachments (an API contract, a design, a screenshot);
  3. alert once per such comment or attachment (remembered in <output_dir>/staleness-state.json).

Scope JQL: config "staleness_jql", else the approved scope JQL plus the posted label, limited to tickets
updated in the last "staleness_days" days (default 7).
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
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
AC_FIELD_NAME = "Acceptance Criteria"


def staleness_jql(config: dict) -> str:
    if config.get("staleness_jql"):
        return config["staleness_jql"]
    scope = config.get("approved_scope_jql") or config["jql"]
    days = int(config.get("staleness_days", 7))
    return f'({scope}) AND labels = "{config["labels"]["posted"]}" AND updated >= -{days}d'


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


def fix_comments_after(issue: dict, since: str, own_name: str = "") -> list[dict]:
    comments = ((issue.get("fields") or {}).get("comment") or {}).get("comments") or []
    found = []
    for comment in comments:
        author = str((comment.get("author") or {}).get("name") or "")
        created = str(comment.get("created") or "")
        if since and _after(created, since) and not _automation(author, own_name) \
                and FIX_SIGNAL.search(comment.get("body") or ""):
            found.append({"id": str(comment.get("id")), "author": author, "created": created})
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
    for attachment in fields.get("attachment") or []:
        author = str((attachment.get("author") or {}).get("name") or "")
        created = str(attachment.get("created") or "")
        if since and _after(created, since) and not _automation(author, own_name):
            found.append({"id": f"attachment:{attachment.get('id')}", "author": author, "created": created,
                          "what": f"the attachment {attachment.get('filename')}"})
    return found


def stale_lines(config: dict, jira, logger, keys: list[str], state: dict, own_name="") -> list[str]:
    """Alert lines for new evidence on each ticket. The ids alerted are added to `state`; the caller saves it
    only once the alert was delivered. A ticket that cannot be read becomes an alert line of its own, so the
    other tickets' alerts are not lost."""
    field_id = config["acceptance_criteria_field"]
    hosts = tuple(config.get("linked_doc_hosts") or linked_docs.DEFAULT_HOSTS)
    if isinstance(own_name, str):
        own_name = {own_name, *(config.get("learning_generator_users") or [])} - {""}
    lines = []
    for key in keys:
        try:
            issue = jira._json("GET", f"/rest/api/2/issue/{key}?expand=changelog&fields=comment,attachment")
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
            lines.append(f"{key}: a root cause or fix was reported by {comment['author']} on {comment['created'][:10]}, "
                         f"after the Acceptance Criteria were last changed on {since[:10]}; review the UAC")
            seen.add(comment["id"])
        for item in new_evidence_after(issue, since, own_name, hosts):
            if item["id"] in seen:
                continue
            lines.append(f"{key}: {item['author']} added {item['what']} on {item['created'][:10]}, after the "
                         f"Acceptance Criteria were last changed on {since[:10]}; review the UAC against it")
            seen.add(item["id"])
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
    common.append_run_record(out, {
        "run_id": run_id, "tool": "uac-staleness", "dry_run": args.dry_run,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started)),
        "seconds": round(time.time() - started), "exit_code": exit_code, "alerts": lines})
    if not args.dry_run and jira is not None:
        result = common.send_alert(config, jira, logger, "uac-staleness", run_id, lines)
        # Remember what was alerted only once QE has it; a failed or unconfigured alert is tried again next run.
        if result in ("POSTED", "NONE", "SUPPRESSED"):
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        else:
            logger.warning("alert %s: the alerted comments are not marked as seen", result)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
