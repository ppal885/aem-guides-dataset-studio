"""Render the concise five-section UI projection from a validated plan."""

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
JIRA_LINE_RE = re.compile(
    r"^-\s+(?:\*\*|`)?(?P<key>[A-Z][A-Z0-9]+-\d+)(?:\*\*|`)?"
    r"\s*(?:[-:\u2013\u2014]\s*)?(?P<body>.*)$"
)
NOISY_JIRA_DETAIL_RE = re.compile(
    r"(?i)(?:\.?\s+|;\s*)(?:status|resolution|affected version|fix version|rca|"
    r"test evidence|impact|assignee|priority|created|updated)\s*:.*$"
)
AUTOMATION_VERDICT_RE = re.compile(
    r"(?i)\b(?P<verdict>partially covered|not covered|covered|unverified)\b"
)
AUTOMATION_AC_RE = re.compile(r"\bAC-\d{2}\b")
SOURCE_SECTIONS = (
    "Understanding From Jira",
    "Acceptance Criteria",
    "Test Scenarios",
    "Regression Areas",
    "Known Jira Bugs / Past Similar Tickets",
    "Automation Coverage & Gaps",
    "Open Questions",
)


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


def _sentence(value: str) -> str:
    cleaned = value.strip().rstrip(".")
    if not cleaned:
        return ""
    return cleaned[0].upper() + cleaned[1:] + "."


def _acceptance_projection(criterion: dict[str, str]) -> str:
    return (
        f"- {criterion['id']}: Given {criterion['given']} | "
        f"When {criterion['when']} | Then {criterion['then']}."
    )


def _regression_scenario(line: str) -> str:
    content = line.strip()
    if content.startswith("- "):
        content = content[2:].strip()
    if "Action:" in content and "Expected:" in content:
        return f"- P3 [Regression]: {content}"

    confirm_match = re.match(
        r"(?i)^(?P<action>.+?)\s+to confirm\s+(?P<expected>.+?)[.]?$",
        content,
    )
    if confirm_match:
        return (
            "- P3 [Regression]: "
            f"Action: {_sentence(confirm_match.group('action'))} "
            f"Expected: {_sentence(confirm_match.group('expected'))}"
        )
    return (
        "- P3 [Regression]: "
        f"Action: {_sentence('Validate ' + content)} "
        "Expected: The named adjacent workflow remains correct and the primary fix "
        "introduces no regression."
    )


def _jira_worth_checking(line: str) -> str | None:
    match = JIRA_LINE_RE.match(line.strip())
    if not match:
        return None
    key = match.group("key")
    body = NOISY_JIRA_DETAIL_RE.sub("", match.group("body")).strip().rstrip(".")
    if not body:
        return f"- {key}"

    if "Similarity:" in body:
        title, _ = body.split("Similarity:", 1)
    elif re.search(r"(?i)\bsimilar because\b", body):
        title, _ = re.split(r"(?i)\bsimilar because\b", body, maxsplit=1)
    else:
        title = body

    title = title.strip().rstrip("-:;,. ") or "Related Jira"
    return f"- {key} - {title}."


def _automation_projection(lines: list[str]) -> list[str]:
    entries: list[tuple[str, str, str]] = []
    declared_main_verdict: str | None = None
    for line in lines:
        verdict_match = AUTOMATION_VERDICT_RE.search(line)
        if not verdict_match:
            continue
        verdict = verdict_match.group("verdict").casefold()
        if line.strip().casefold().startswith("- main feature coverage:"):
            declared_main_verdict = verdict
            continue
        ac_ids = ", ".join(dict.fromkeys(AUTOMATION_AC_RE.findall(line))) or "Main feature"
        lowered = line.casefold()
        if ".feature" in lowered or "guides-ui-tests" in lowered or "ui layer" in lowered:
            target = "feature-file/UI automation"
        elif (
            "dxml-it-tests" in lowered
            or "integration" in lowered
            or "api layer" in lowered
            or " it " in f" {lowered} "
        ):
            target = "integration/API test automation"
        else:
            target = "the appropriate feature file or integration-test suite"
        entries.append((ac_ids, verdict, target))

    if not entries:
        return [
            "- Main feature coverage: Unverified - direct feature-file and integration-test "
            "evidence was not found.",
            "- Recommended automation: inspect the relevant UI feature file and backend "
            "integration-test suite before selecting the automation layer.",
        ]

    verdicts = [verdict for _, verdict, _ in entries]
    if declared_main_verdict:
        main_verdict = declared_main_verdict[0].upper() + declared_main_verdict[1:]
    elif all(verdict == "covered" for verdict in verdicts):
        main_verdict = "Covered"
    elif all(verdict == "not covered" for verdict in verdicts):
        main_verdict = "Not covered"
    elif all(verdict == "unverified" for verdict in verdicts):
        main_verdict = "Unverified"
    else:
        main_verdict = "Partially covered"

    output = [
        f"- Main feature coverage: {main_verdict} - based on direct automation evidence "
        f"for {len(entries)} AC mapping(s)."
    ]
    for ac_ids, verdict, target in entries:
        display = verdict[0].upper() + verdict[1:]
        if verdict == "not covered":
            output.append(
                f"- {ac_ids}: {display} - add high-level coverage in {target} for the "
                "primary action, observable result, negative boundary, and cleanup."
            )
        elif verdict == "partially covered":
            output.append(
                f"- {ac_ids}: {display} - extend {target} to cover the missing primary-result "
                "or boundary assertion."
            )
        elif verdict == "unverified":
            output.append(
                f"- {ac_ids}: {display} - confirm coverage in {target} before automation handoff."
            )
        else:
            output.append(
                f"- {ac_ids}: {display} - existing {target} covers the stated acceptance path."
            )
    return output


def project(text: str) -> tuple[str, list[str]]:
    sections = _sections(text)
    problems: list[str] = []
    criteria, ac_problems = extract(text)
    problems.extend(ac_problems)
    if not sections["Test Scenarios"]:
        problems.append("Test Scenarios is empty; compact view cannot be rendered")
    if not sections["Regression Areas"]:
        problems.append("Regression Areas is empty; compact view cannot be rendered")
    if not sections["Open Questions"]:
        problems.append("Open Questions is empty; compact view cannot be rendered")

    regression_scenarios = [
        _regression_scenario(line) for line in sections["Regression Areas"]
    ]
    jira_tickets = [
        projected
        for line in sections["Known Jira Bugs / Past Similar Tickets"]
        if PAST_JIRA_RE.match(line)
        for projected in [_jira_worth_checking(line)]
        if projected is not None
    ][:5]
    if not jira_tickets:
        jira_tickets = [
            "- No same-mechanism Jira ticket is worth checking from the validated evidence."
        ]
    automation = _automation_projection(sections["Automation Coverage & Gaps"])

    if problems:
        return "", problems

    acceptance_lines = [_acceptance_projection(criterion) for criterion in criteria]
    output = [
        "**Acceptance Criteria**",
        *acceptance_lines,
        "",
        "**Test Scenarios**",
        *sections["Test Scenarios"],
        *regression_scenarios,
        "",
        "**Jira Tickets Worth Checking**",
        *jira_tickets,
        "",
        "**Automation Coverage**",
        *automation,
        "",
        "**Open Questions**",
        *sections["Open Questions"],
    ]
    return "\n".join(output).rstrip() + "\n", []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Project a full validated plan into the concise five-section UI view."
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
