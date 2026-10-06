#!/usr/bin/env python3
"""Tell QE when a root cause, a fix or an API contract arrives on a ticket after its UAC was posted.

A UAC written before the root cause is known can describe the wrong scenario, and one written before the
developer's API contract or design can miss endpoints, fields and status codes. When a later comment names
the root cause, a fix, a pull request or a merge, or gives an API contract or design, the UAC should be
reviewed. This script finds
those tickets and sends one alert (on the configured alert ticket, mentioning the configured people)
listing them. It never edits or comments on the ticket itself and never changes the UAC.

For each ticket in scope that carries the posted label:
  1. find when the Acceptance Criteria field last changed (Jira changelog);
  2. find human comments created after that time whose text reports a root cause or a fix, or gives an
     API contract or design (an HTTP method with a path, request/response body, status codes, API spec);
  3. alert once per such comment (remembered in <output_dir>/staleness-state.json).

Scope JQL: config "staleness_jql", else the approved scope JQL plus the posted label, limited to tickets
updated in the last "staleness_days" days (default 7).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

STATE_FILE = "staleness-state.json"
# The same signal the skill uses to decide whether a UAC was written with the root cause known.
FIX_SIGNAL = common.import_skill_module("uac_completeness_check").FIX_SIGNAL
# A developer's API contract or design: an HTTP method with a path, request/response bodies, status codes,
# or a named API spec / design document. A passing mention of "API" is not enough.
CONTRACT_SIGNAL = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE)\s+/[\w{}/.:-]+|\bAPI\s+(contract|spec(ification)?|design)\b"
    r"|\b(request|response)\s+(body|payload|schema)\b|\bstatus\s+codes?\b|\b(swagger|openapi)\b"
    r"|\btechnical\s+design\b|\bdesign\s+doc(ument)?\b", re.IGNORECASE)
SIGNALS = (("a root cause or fix", FIX_SIGNAL), ("an API contract or design", CONTRACT_SIGNAL))
AC_FIELD_NAME = "Acceptance Criteria"


def staleness_jql(config: dict) -> str:
    if config.get("staleness_jql"):
        return config["staleness_jql"]
    scope = config.get("approved_scope_jql") or config["jql"]
    days = int(config.get("staleness_days", 7))
    return f'({scope}) AND labels = "{config["labels"]["posted"]}" AND updated >= -{days}d'


def last_ac_change(issue: dict, field_id: str) -> str:
    """ISO time of the last change to the Acceptance Criteria field, or "" when the changelog has none."""
    latest = ""
    for history in (issue.get("changelog") or {}).get("histories") or []:
        for item in history.get("items") or []:
            if item.get("fieldId") == field_id or item.get("field") == AC_FIELD_NAME:
                latest = max(latest, str(history.get("created") or ""))
    return latest


def fix_comments_after(issue: dict, since: str, own_name: str = "") -> list[dict]:
    """Human comments after `since` that report a root cause or fix, or give an API contract or design."""
    comments = ((issue.get("fields") or {}).get("comment") or {}).get("comments") or []
    found = []
    for comment in comments:
        author = str((comment.get("author") or {}).get("name") or "")
        created = str(comment.get("created") or "")
        if not since or created <= since or author == own_name:
            continue
        body = comment.get("body") or ""
        kinds = [kind for kind, signal in SIGNALS if signal.search(body)]
        if kinds:
            found.append({"id": str(comment.get("id")), "author": author, "created": created,
                          "kind": " and ".join(kinds)})
    return found


def stale_lines(config: dict, jira, logger, keys: list[str], state: dict, own_name: str = "") -> list[str]:
    field_id = config["acceptance_criteria_field"]
    lines = []
    for key in keys:
        issue = jira._json("GET", f"/rest/api/2/issue/{key}?expand=changelog&fields=comment")
        since = last_ac_change(issue, field_id)
        if not since:
            continue
        seen = set(state.get(key) or [])
        for comment in fix_comments_after(issue, since, own_name):
            if comment["id"] in seen:
                continue
            lines.append(f"{key}: {comment['kind']} was reported by {comment['author']} on {comment['created'][:10]}, "
                         f"after the Acceptance Criteria were last changed on {since[:10]}; review the UAC")
            seen.add(comment["id"])
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
    if not args.dry_run:
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        if jira is not None:
            common.send_alert(config, jira, logger, "uac-staleness", run_id, lines)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
