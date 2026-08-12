"""Render the Jira card and five-section UI projection from a validated plan."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from extract_acs import extract


HEADING_RE = re.compile(r"^\*\*(.+?)\*\*$")
PAST_JIRA_RE = re.compile(
    r"^- (?:\*\*)?[A-Z][A-Z0-9]+-\d+(?:\*\*)?(?:\s|$|[-:\u2014])"
)
SOURCE_SECTIONS = (
    "Understanding From Jira",
    "Acceptance Criteria",
    "Test Scenarios",
    "Regression Areas",
    "Known Jira Bugs / Past Similar Tickets",
    "Open Questions",
)

IMPACT_FALLBACK = "Impact not specified; QA impact requires confirmation"


def _sections(text: str) -> dict[str, list[str]]:
    sections = {name: [] for name in SOURCE_SECTIONS}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        heading = HEADING_RE.fullmatch(line.strip())
        if heading:
            current = heading.group(1) if heading.group(1) in sections else None
            continue
        if current and line.strip():
            sections[current].append(line)
    return sections


def _labelled_bullet(lines: list[str], label: str) -> str:
    prefix = f"- {label}:"
    for line in lines:
        stripped = line.strip()
        if stripped.casefold().startswith(prefix.casefold()):
            return stripped[len(prefix) :].strip()
    return ""


def _impact_text(lines: list[str]) -> str:
    impact = _labelled_bullet(lines, "Why it matters")
    if not impact or re.fullmatch(
        r"(?:unknown|not specified|not available|requires confirmation)[.!]?",
        impact,
        re.I,
    ):
        return IMPACT_FALLBACK
    return impact


def project(text: str) -> tuple[str, list[str]]:
    sections = _sections(text)
    problems: list[str] = []
    criteria, ac_problems = extract(text)
    problems.extend(ac_problems)
    issue = _labelled_bullet(sections["Understanding From Jira"], "Issue understood")
    requested_outcome = _labelled_bullet(
        sections["Understanding From Jira"], "Requested outcome"
    )
    if not issue:
        problems.append("Understanding From Jira is missing 'Issue understood'")
    if not requested_outcome:
        problems.append("Understanding From Jira is missing 'Requested outcome'")
    if not sections["Test Scenarios"]:
        problems.append("Test Scenarios is empty; compact view cannot be rendered")
    if not sections["Regression Areas"]:
        problems.append("Regression Areas is empty; compact view cannot be rendered")
    if not sections["Open Questions"]:
        problems.append("Open Questions is empty; compact view cannot be rendered")

    past_jiras = [
        line
        for line in sections["Known Jira Bugs / Past Similar Tickets"]
        if PAST_JIRA_RE.match(line)
    ][:5]
    if not past_jiras:
        past_jiras = ["- No same-defect-class past Jira was found in the validated evidence."]

    if problems:
        return "", problems

    acceptance_lines = [f"- {criterion['raw']}" for criterion in criteria]
    understood = issue
    if requested_outcome:
        understood = f"{understood} Requested outcome: {requested_outcome}"
    output = [
        f"> **What I understood from Jira:** {understood}",
        f"> **Why it matters:** {_impact_text(sections['Understanding From Jira'])}",
        "",
        "**Acceptance Criteria**",
        *acceptance_lines,
        "",
        "**Test Scenarios**",
        *sections["Test Scenarios"],
        "",
        "**Regression Areas**",
        *sections["Regression Areas"],
        "",
        "**Past Jiras**",
        *past_jiras,
        "",
        "**Open Questions**",
        *sections["Open Questions"],
    ]
    return "\n".join(output).rstrip() + "\n", []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Project a full validated plan into the Jira card and five-section UI view."
    )
    parser.add_argument("plan_file")
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    plan_path = Path(args.plan_file)
    if not plan_path.is_file():
        print(f"plan file not found: {plan_path}", file=sys.stderr)
        return 2
    compact, problems = project(plan_path.read_text(encoding="utf-8"))
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    if args.out:
        out_path = Path(args.out)
        out_path.write_text(compact, encoding="utf-8")
        print(f"wrote compact view to {out_path}")
    else:
        print(compact, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
