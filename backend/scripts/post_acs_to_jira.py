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


QE_ASSIGNEE_FIELD = "customfield_18512"  # AEM Guides Jira "QE Assignee" user field


def _qe_assignee_username(client, key: str) -> str | None:
    """Return the QE Assignee's Jira username (for a [~name] mention), or None."""
    try:
        issue = client.get_issue(key, fields=QE_ASSIGNEE_FIELD)
        qe = (issue.get("fields") or {}).get(QE_ASSIGNEE_FIELD)
        if isinstance(qe, dict):
            return qe.get("name") or None
    except Exception:  # noqa: BLE001 - tagging is best-effort, never block the AC post
        return None
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--key", required=True)
    p.add_argument("--plan", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--label", default="Needs_Human_Review")
    p.add_argument("--no-qe-tag", action="store_true",
                   help="do not add a comment tagging the QE Assignee to review")
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
    c = JiraClient()

    # First-post vs update: read the current AC field so a re-run does not repeat
    # the identical "posted" comment. An update gets an update-specific comment.
    existing = ""
    try:
        existing = (c.get_issue(key, fields="customfield_13400")
                    .get("fields", {}).get("customfield_13400") or "").strip()
    except Exception:  # noqa: BLE001 - if we cannot read it, treat as a first post
        existing = ""
    is_update = bool(existing) and existing != ac_text
    unchanged = bool(existing) and existing == ac_text

    if unchanged:
        comment = None  # nothing changed - do not add a noise comment
    elif is_update:
        comment = (f"Acceptance Criteria field updated by the AEM Guides test-plan skill "
                   f"(now {len(acs)} criteria, AI-generated). Flagged {args.label} - please re-review the updated criteria.")
    else:
        comment = ("Acceptance Criteria posted by the AEM Guides test-plan skill (AI-generated). "
                   f"Flagged {args.label} - a human must review and confirm before sign-off.")

    mode = "unchanged" if unchanged else ("update" if is_update else "first post")
    print(f"Issue: {key} ({mode})\nAC field content to post ({len(acs)} criteria):\n" + "-" * 60)
    print(ac_text)
    print("-" * 60 + f"\nLabel: {args.label}")

    if args.dry_run:
        print("\nDry-run: nothing written.")
        return 0

    c.set_acceptance_criteria(key, ac_text, review_label=args.label, review_comment=comment)
    verb = "unchanged (re-affirmed)" if unchanged else ("updated" if is_update else "set")
    print(f"\nOK: {verb} {key} Acceptance Criteria field ({len(acs)} criteria); label {args.label}"
          + ("; comment added." if comment else "; no comment (content unchanged)."))

    # Tag the QE Assignee only on the FIRST post (avoid re-tagging on every update),
    # unless explicitly disabled.
    if args.no_qe_tag:
        pass
    elif is_update or unchanged:
        print("NOTE: not a first post - skipped re-tagging the QE Assignee (already tagged initially).")
    else:
        qe = _qe_assignee_username(c, key)
        if qe:
            c.add_comment(key, f"[~{qe}] please review the acceptance criteria for this case (QE Assignee). "
                               f"These AI-drafted ACs are in the Acceptance Criteria field and labelled {args.label}.")
            print(f"OK: added a comment tagging QE Assignee [~{qe}] to review.")
        else:
            print("NOTE: no QE Assignee set on the issue - skipped the review tag.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
