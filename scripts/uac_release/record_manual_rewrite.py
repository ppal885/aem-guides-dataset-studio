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

A rewrite a QE asked for in a chat is a correction: record what kind of mistake it fixed and the lesson,
so the harvester can count the same mistake across tickets (common.CORRECTION_PATTERNS lists the kinds):

  python scripts/uac_release/record_manual_rewrite.py --ticket GUIDES-15177 --reason "QE correction" \\
      --pattern screen-name --pattern tbd-answerable --lesson "Say Language variables panel, not window"

Running it again for a text that is already marked adds the patterns and lesson to that mark.

A QE who rewrote the field directly in Jira made a QE edit, not a Claude rewrite. --qe-edit records the
patterns and lessons for that text without relabelling the edit:

  python scripts/uac_release/record_manual_rewrite.py --ticket GUIDES-51870 --qe-edit --reason "QE rewrite" \\
      --pattern stale-after-rca --lesson "Refresh the UAC when the root cause arrives"
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


def mark(jira, key: str, texts: list[str], reason: str, patterns: list[str] = (), lessons: list[str] = (),
         qe_edit: bool = False) -> list[str]:
    """Add the texts' SHA-256 to the ticket's property, with the correction patterns and lessons when given.
    A text that is already marked gets the new patterns and lessons. Returns the new hashes."""
    current = jira.get_issue_property(key, PROPERTY) or {}
    rewrites = list(current.get("rewrites") or [])
    by_sha = {r.get("sha256"): r for r in rewrites if isinstance(r, dict)}
    added, updated = [], False
    for text in texts:
        if not text.strip():
            continue
        sha = harvester._sha(text)
        entry = by_sha.get(sha)
        if entry is None:
            entry = {"sha256": sha, "reason": reason, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
            if qe_edit:
                entry["qe_edit"] = True  # a correction record only; the harvester keeps it a QE_EDIT
            rewrites.append(entry)
            by_sha[sha] = entry
            added.append(sha)
        new_patterns = [p for p in patterns if p not in (entry.get("patterns") or [])]
        if new_patterns:
            entry["patterns"] = list(entry.get("patterns") or []) + new_patterns
            updated = True
        new_lessons = [t for t in lessons if t and t not in (entry.get("lessons") or [])]
        if new_lessons:
            entry["lessons"] = list(entry.get("lessons") or []) + new_lessons
            updated = True
    if added or updated:
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
    parser.add_argument("--pattern", action="append", default=[], choices=sorted(common.CORRECTION_PATTERNS),
                        help="the kind of mistake this correction fixed (repeatable)")
    parser.add_argument("--qe-edit", action="store_true",
                        help="the text is a QE's own edit: record patterns and lessons, do not mark a Claude rewrite")
    parser.add_argument("--lesson", action="append", default=[], help="one sentence: what the UAC should have said (repeatable)")
    parser.add_argument("--field", default="customfield_13400", help="the Acceptance Criteria field id")
    parser.add_argument("--env-file", type=Path, default=common.REPO_ROOT / "backend" / ".env")
    args = parser.parse_args(argv)
    common.load_env_file(args.env_file)
    jira = common.JiraClient.from_env()
    own_name = str((jira.myself() or {}).get("name") or "")
    for key in args.ticket:
        texts = history_texts(jira, key, args.field, own_name) if args.from_history else [
            jira.get_field(key, args.field) or ""]
        added = mark(jira, key, texts, args.reason, args.pattern, args.lesson, args.qe_edit)
        extra = f"; patterns {', '.join(args.pattern)}" if args.pattern else ""
        kind = "a QE edit with patterns" if args.qe_edit else "a Claude rewrite"
        print(f"{key}: marked {len(added)} new text(s) as {kind}{extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
