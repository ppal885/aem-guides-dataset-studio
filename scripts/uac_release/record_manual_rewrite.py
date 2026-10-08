#!/usr/bin/env python3
"""Mark an Acceptance Criteria text written by a Claude or Codex session, so the harvester does not learn
from it as a QE edit.

The automation and QE share one Jira account, so a field write by a Claude session looks like a QE edit.
This script stores the SHA-256 of such texts in the ticket's hidden issue property "uac-manual-rewrite"
(no field, comment or visible change). The harvester labels a harvested edit CLAUDE_REWRITE when its text
matches one of them, and QE_EDIT otherwise.

  python scripts/uac_release/record_manual_rewrite.py --ticket GUIDES-41774 --reason "readability rewrite"
  python scripts/uac_release/record_manual_rewrite.py --ticket GUIDES-41774 --from-history --reason "..."

--from-history marks every change of the field by the automation's account after its first write (the
runner's own post), for rewrites made before this script existed.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import uac_learning_harvester as harvester  # noqa: E402

PROPERTY = "uac-manual-rewrite"
KEEP = 50


def mark(jira, key: str, texts: list[str], reason: str) -> list[str]:
    """Add the texts' SHA-256 to the ticket's property. Returns the new hashes."""
    current = jira.get_issue_property(key, PROPERTY) or {}
    rewrites = list(current.get("rewrites") or [])
    known = {r.get("sha256") for r in rewrites}
    added = []
    for text in texts:
        sha = harvester._sha(text)
        if text.strip() and sha not in known:
            rewrites.append({"sha256": sha, "reason": reason, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
            known.add(sha)
            added.append(sha)
    if added:
        jira.set_issue_property(key, PROPERTY, {"rewrites": rewrites[-KEEP:]})
    return added


def history_texts(jira, key: str, field_id: str, own_name: str) -> list[str]:
    """Texts the automation's account wrote to the field after its first write."""
    issue = jira._json("GET", f"/rest/api/2/issue/{key}?expand=changelog&fields={field_id}")
    own = [c["to"] for c in harvester.ac_field_changes(issue, field_id) if c["by"] == own_name]
    return own[1:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticket", action="append", required=True)
    parser.add_argument("--reason", required=True, help='e.g. "readability rewrite" or "user-directed correction"')
    parser.add_argument("--from-history", action="store_true")
    parser.add_argument("--field", default="customfield_13400", help="the Acceptance Criteria field id")
    parser.add_argument("--env-file", type=Path, default=common.REPO_ROOT / "backend" / ".env")
    args = parser.parse_args(argv)
    common.load_env_file(args.env_file)
    jira = common.JiraClient.from_env()
    own_name = str((jira.myself() or {}).get("name") or "")
    for key in args.ticket:
        texts = history_texts(jira, key, args.field, own_name) if args.from_history else [
            jira.get_field(key, args.field) or ""]
        added = mark(jira, key, texts, args.reason)
        print(f"{key}: marked {len(added)} text(s) as a Claude rewrite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
