from __future__ import annotations

import re
import sys
from pathlib import Path


SECTIONS = (
    "Understanding From Jira",
    "Acceptance Criteria",
    "Expected Behaviour",
    "Scope From Git",
    "Code Touched",
    "Lines Changed",
    "Test Scenarios",
    "Known Jira Bugs / Past Similar Tickets",
    "Regression Areas",
    "Automation Coverage & Gaps",
    "Open Questions",
)
HEADING_RE = re.compile(r"^\*\*(.+?)\*\*$")
AC_RE = re.compile(r"^- AC-\d{2} \[(Confirmed|Proposed)\]:\s+\S")
ANY_AC_RE = re.compile(r"^- AC-\d{2} \[([^]]+)\]")
SCENARIO_RE = re.compile(r"^- P[012]\b")
AC_LINK_RE = re.compile(r"\[AC-\d{2}(?:,\s*AC-\d{2})*\]")
JIRA_RE = re.compile(r"^- (?:[A-Z][A-Z0-9]+-\d+)\b")
WINDOWS_PATH_RE = re.compile(r"(?<![\w])([A-Za-z]:\\[^`\n;,]+)")
MOJIBAKE = ("\u00e2\u20ac", "\u00e2\u2030", "\u00c3", "\u00c2", "\ufffd")
UNDERSTANDING_PREFIXES = (
    "- Issue understood:",
    "- Why it matters:",
    "- Requested outcome:",
    "- Lifecycle understood as:",
    "- Evidence boundary:",
)


def _section_map(lines: list[str]) -> tuple[dict[str, list[tuple[int, str]]], list[str]]:
    errors: list[str] = []
    sections: dict[str, list[tuple[int, str]]] = {name: [] for name in SECTIONS}
    seen: list[str] = []
    current: str | None = None
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        heading = HEADING_RE.match(line)
        if heading:
            name = heading.group(1)
            if name not in SECTIONS:
                errors.append(f"line {number}: unexpected section '{name}'")
                current = None
                continue
            seen.append(name)
            current = name
            continue
        if current is None:
            errors.append(f"line {number}: content appears outside the required sections")
            continue
        if not line.startswith("- "):
            errors.append(f"line {number}: section content must be a Markdown bullet starting with '- '")
        sections[current].append((number, line))
    if tuple(seen) != SECTIONS:
        errors.append("required sections are missing, duplicated, or out of order")
    return sections, errors


def validate(text: str) -> list[str]:
    lines = text.splitlines()
    sections, errors = _section_map(lines)

    for marker in MOJIBAKE:
        if marker in text:
            errors.append(f"output contains mojibake marker {marker!r}")

    if "requires authorization" in text.lower() and re.search(
        r"live Jira|fetched via .*jira|Jira MCP.*(?:success|fetched)", text, re.IGNORECASE
    ):
        errors.append("Jira authorization warning contradicts successful live Jira evidence")

    understanding = sections["Understanding From Jira"]
    understanding_lines = [line for _, line in understanding]
    if len(understanding_lines) != len(UNDERSTANDING_PREFIXES):
        errors.append("Understanding From Jira must contain exactly five confidence-check bullets")
    for prefix in UNDERSTANDING_PREFIXES:
        if not any(line.startswith(prefix) and line[len(prefix) :].strip() for line in understanding_lines):
            errors.append(f"Understanding From Jira is missing required bullet '{prefix}'")
    why_it_matters = next(
        (line for line in understanding_lines if line.startswith("- Why it matters:")),
        "",
    )
    if "customer context resolved from jira:" not in why_it_matters.lower():
        errors.append(
            "Why it matters must state 'Customer context resolved from Jira:' and its Jira field/label source"
        )

    acceptance = sections["Acceptance Criteria"]
    native_ac_empty = any(
        phrase in text.lower()
        for phrase in ("native acceptance criteria field is empty", "no jira-authored ac", "jira ac field is empty")
    )
    destructive = re.compile(
        r"\b(delete|deleting|remove|removing|clear|clearing|terminate|restart)\b.*\b(node|workflow|pod|tracker)",
        re.IGNORECASE,
    )
    prescribed = re.compile(
        r"\bmust\b.*\b(include a terminal step|single consistent source of truth|single source of truth|"
        r"retry the commit|serialize|path-level lock|reconcil(?:e|ing)|clear(?:ing)? .*node)",
        re.IGNORECASE,
    )
    for number, line in acceptance:
        match = ANY_AC_RE.match(line)
        if not match or not AC_RE.match(line):
            errors.append(f"line {number}: acceptance criterion must use exact AC-## [Confirmed|Proposed]: syntax")
            continue
        if native_ac_empty and match.group(1) == "Confirmed":
            errors.append(f"line {number}: derived criterion cannot be Confirmed when Jira AC is empty")
        if destructive.search(line):
            errors.append(f"line {number}: destructive operational procedure is not a product acceptance criterion")
        if prescribed.search(line):
            errors.append(f"line {number}: acceptance criterion prescribes an unapproved implementation choice")

    scenarios = sections["Test Scenarios"]
    if not any(line.startswith("- Test data to prepare:") for _, line in scenarios):
        errors.append("Test Scenarios must begin with explicit 'Test data to prepare:' guidance")
    for number, line in scenarios:
        if SCENARIO_RE.match(line) and "Incident recovery validation" not in line and not AC_LINK_RE.search(line):
            errors.append(f"line {number}: P0/P1/P2 scenario is missing an AC mapping")
        if SCENARIO_RE.match(line) and ("Action:" not in line or "Expected:" not in line):
            errors.append(f"line {number}: P0/P1/P2 scenario must use plain-English Action: and Expected: wording")

    if "..." in text:
        for number, line in enumerate(lines, start=1):
            if "..." in line:
                errors.append(f"line {number}: abbreviated path or ellipsis is not allowed")

    for number, line in sections["Scope From Git"]:
        if re.match(r"^- [A-Za-z]:\\", line) and any(word in line.lower() for word in ("clone", "branch", "repo")):
            required = ("branch", "sha", "fetch", "ahead", "behind", "clean")
            missing = [word for word in required if word not in line.lower()]
            if missing:
                errors.append(f"line {number}: clone evidence is missing {', '.join(missing)}")

    for section_name in ("Code Touched", "Automation Coverage & Gaps"):
        for number, line in sections[section_name]:
            if "\\" in line:
                quoted_candidates = re.findall(r"`([^`]*\\[^`]*)`", line)
                unquoted_text = re.sub(r"`[^`]*`", "", line)
                unquoted_candidates = re.findall(r"([^`\s,;]+\\[^`\s,;]+)", unquoted_text)
                for candidate in quoted_candidates + unquoted_candidates:
                    if candidate.startswith(("<", "/")):
                        continue
                    if not re.match(r"^[A-Za-z]:\\", candidate):
                        errors.append(f"line {number}: cited Windows path is not absolute: {candidate}")

    automation = sections["Automation Coverage & Gaps"]
    recipe_terms = ("layer", "setup", "poll", "timeout", "assert", "cleanup", "tag")
    for number, line in automation:
        if "Not covered" in line:
            lowered = line.lower()
            missing = [term for term in recipe_terms if term not in lowered]
            if missing:
                errors.append(f"line {number}: Not covered automation recipe is missing {', '.join(missing)}")
        if "Not suitable for automation" in line and re.search(
            r"post-cleanup|subsequent|fresh generation|normal operation", line, re.IGNORECASE
        ):
            errors.append(f"line {number}: repeatable post-recovery behavior is automatable")

    history_terms = ("Status:", "Resolution:", "Affected version:", "Fix version:", "RCA:", "Test evidence:", "Impact:")
    for number, line in sections["Known Jira Bugs / Past Similar Tickets"]:
        if JIRA_RE.match(line):
            missing = [term for term in history_terms if term.lower() not in line.lower()]
            if missing:
                errors.append(f"line {number}: historical Jira entry is missing {', '.join(missing)}")
    history_text = "\n".join(line for _, line in sections["Known Jira Bugs / Past Similar Tickets"])
    for number, line in sections["Known Jira Bugs / Past Similar Tickets"]:
        if "Observed Customer Jira Profile:" not in line:
            continue
        if not re.search(r"Observed Customer Jira Profile:\s*[^-]+\s+-", line):
            errors.append(f"line {number}: customer profile must name the resolved customer")
        if "unavailable" not in line.lower():
            required_profile_terms = (
                "resolved from",
                "profile",
                "approval",
                "Jira keys",
                "Bug/Defect",
                "problem-report",
                "test-data",
                "representative",
                "Aggregate context",
            )
            missing = [term for term in required_profile_terms if term.lower() not in line.lower()]
            if missing:
                errors.append(
                    f"line {number}: customer profile evidence is missing {', '.join(missing)}"
                )
    if history_text and not all(term in history_text.lower() for term in ("jql", "error", "workflow")):
        errors.append("historical search must report multiple narrow JQL intents including error and workflow searches")

    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_test_plan.py <markdown-file>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    errors = validate(path.read_text(encoding="utf-8"))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("PASS: test plan satisfies executable quality gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
