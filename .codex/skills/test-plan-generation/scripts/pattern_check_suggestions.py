"""Suggest QE-approved historical pattern checks for the current ticket (opt-in).

WHAT IT DOES
------------
Reads the current ticket's own text and returns at most a few QE-approved
checks (data/pattern_checks.json) whose trigger words appear in that text.
Each check came from the benchmark TRAIN split and was approved by a human QE.

WHAT IT MUST NEVER DO
---------------------
A suggestion is SUPPORTING_DISCOVERY only. It is a coverage candidate or a
research question for the author, never an acceptance criterion by itself:
current-ticket evidence must independently support any requirement that
results. The output says so on every suggestion.

OFF BY DEFAULT
--------------
SKILL_PATTERN_CHECKS_MODE=PATTERN_CHECKS_SUGGEST turns it on. Absent, blank or
unknown values keep it DISABLED, and a disabled run does not read the data file.
A missing or malformed data file reports UNAVAILABLE with no suggestions; it
never blocks or relaxes any other gate.

Usage:
    python pattern_check_suggestions.py TICKET_TEXT_FILE [--limit N] [--json]

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

MODES = ("PATTERN_CHECKS_DISABLED", "PATTERN_CHECKS_SUGGEST")
MODE_ENV = "SKILL_PATTERN_CHECKS_MODE"
DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "pattern_checks.json"
SCHEMA_VERSION = "aem-guides-pattern-checks-v1"
DEFAULT_LIMIT = 3
NOTICE = (
    "Historical pattern suggestion, not an acceptance criterion. "
    "Use it only if current-ticket evidence supports it."
)


def mode(env=None) -> str:
    source = os.environ if env is None else env
    raw = str(source.get(MODE_ENV, "") or "").strip().upper()
    return raw if raw in MODES else "PATTERN_CHECKS_DISABLED"


def load_checks(path: Path = DATA_PATH) -> list[dict]:
    """Return validated checks, or raise ValueError for a missing or malformed file."""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"pattern checks unreadable: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("pattern checks have an unknown schema_version")
    if data.get("status") != "HUMAN_QE_APPROVED" or data.get("authority") != "SUPPORTING_DISCOVERY":
        raise ValueError("pattern checks are not human-approved supporting discovery")
    checks = data.get("checks")
    if not isinstance(checks, list):
        raise ValueError("pattern checks have no checks list")
    required = ("check_id", "pattern_id", "title", "check", "applies_when", "exclude_when", "trigger")
    for row in checks:
        if not isinstance(row, dict) or any(not str(row.get(key) or "").strip() for key in required):
            raise ValueError("a pattern check is missing a required field")
        try:
            re.compile(row["trigger"])
        except re.error as exc:
            raise ValueError(f"{row['check_id']} has an invalid trigger: {exc}") from exc
    return checks


def suggest(ticket_text: str, *, env=None, path: Path = DATA_PATH, limit: int = DEFAULT_LIMIT) -> dict:
    """Return {mode, status, suggestions}; status is DISABLED, UNAVAILABLE or OK."""

    current = mode(env)
    if current == "PATTERN_CHECKS_DISABLED":
        return {"mode": current, "status": "DISABLED", "suggestions": []}
    try:
        checks = load_checks(path)
    except ValueError as exc:
        return {"mode": current, "status": "UNAVAILABLE", "reason": str(exc), "suggestions": []}
    text = ticket_text or ""
    matched = []
    for row in checks:
        hit = re.search(row["trigger"], text, re.IGNORECASE)
        if hit:
            matched.append((row, hit.group(0)))
    matched.sort(key=lambda item: (-int(item[0].get("train_support_jiras") or 0), item[0]["check_id"]))
    suggestions = [
        {
            "check_id": row["check_id"],
            "pattern_id": row["pattern_id"],
            "title": row["title"],
            "check": row["check"],
            "applies_when": row["applies_when"],
            "exclude_when": row["exclude_when"],
            "triggered_by": trigger_text,
            "authority": "SUPPORTING_DISCOVERY",
            "notice": NOTICE,
        }
        for row, trigger_text in matched[: max(0, limit)]
    ]
    return {"mode": current, "status": "OK", "suggestions": suggestions}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ticket_text_file", type=Path)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = suggest(args.ticket_text_file.read_text(encoding="utf-8", errors="replace"), limit=args.limit)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    print(f"pattern checks: {result['status']} ({result['mode']})")
    if result.get("reason"):
        print(f"  {result['reason']}")
    for row in result["suggestions"]:
        print(f"- {row['check_id']} {row['title']} (triggered by: {row['triggered_by']})")
        print(f"  {row['check']}")
        print(f"  Applies when: {row['applies_when']} Does not apply when: {row['exclude_when']}")
        print(f"  {row['notice']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
