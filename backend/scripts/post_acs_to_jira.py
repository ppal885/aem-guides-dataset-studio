"""Post ONLY the Acceptance Criteria from a validated test plan into a Jira issue's
Acceptance Criteria field, and add a 'Needs_Human_Review' marker.

Usage:
    python scripts/post_acs_to_jira.py --key GUIDES-XXXXX [--plan path] [--dry-run]

Reads output/test-plans/<KEY>-test-plan.md by default. Extracts the clean
`- AC-##: <statement>` lines from the Acceptance Criteria section and writes them (and
nothing else) to the AC field. Adds a Needs_Human_Review label and a short comment noting
the ACs are AI-generated and pending human review.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(_BACKEND))
from dotenv import load_dotenv

load_dotenv(_BACKEND / ".env")

AC_LINE = re.compile(r"^- (AC-\d{2}:.+)$")
HEADING = re.compile(r"^\*\*(.+?)\*\*$")


def extract_acceptance_criteria(markdown: str) -> list[str]:
    out, in_section = [], False
    for line in markdown.splitlines():
        h = HEADING.match(line.strip())
        if h:
            in_section = h.group(1).strip() == "Acceptance Criteria"
            continue
        if in_section:
            m = AC_LINE.match(line.rstrip())
            if m:
                out.append(m.group(1).strip())
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--key", required=True)
    p.add_argument("--plan", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--label", default="Needs_Human_Review")
    args = p.parse_args()

    from app.services.test_plan_artifact_service import TEST_PLANS_DIR, _normalize_jira_key
    from app.services.jira_client import JiraClient

    key = _normalize_jira_key(args.key)
    plan_path = Path(args.plan) if args.plan else TEST_PLANS_DIR / f"{key}-test-plan.md"
    if not plan_path.exists():
        print(f"ERROR: plan not found: {plan_path}", file=sys.stderr)
        return 1

    acs = extract_acceptance_criteria(plan_path.read_text(encoding="utf-8"))
    if not acs:
        print("ERROR: no clean 'AC-##:' lines found in the Acceptance Criteria section", file=sys.stderr)
        return 1

    ac_text = "\n".join(acs)  # ONLY the acceptance criteria - nothing else
    comment = ("Acceptance Criteria posted by the AEM Guides test-plan skill (AI-generated). "
               "Flagged Needs_Human_Review - a human must review and confirm before sign-off.")
    print(f"Issue: {key}\nAC field content to post ({len(acs)} criteria):\n" + "-" * 60)
    print(ac_text)
    print("-" * 60 + f"\nLabel: {args.label}")

    if args.dry_run:
        print("\nDry-run: nothing written.")
        return 0

    c = JiraClient()
    c.set_acceptance_criteria(key, ac_text, review_label=args.label, review_comment=comment)
    print(f"\nOK: updated {key} Acceptance Criteria field, added label {args.label} and a review comment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
