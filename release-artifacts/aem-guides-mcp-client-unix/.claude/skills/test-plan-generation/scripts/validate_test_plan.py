from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ac_contract import AC_EXACT_FORMAT, parse_ac_line, validate_ac_sequence
from performance_contract import COMPARATIVE_ORACLE_RE, QUANTIFIED_VALUE_RE, QUANTIFIED_WORKLOAD_RE


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
SCENARIO_RE = re.compile(r"^- P[012]\b")
AC_LINK_RE = re.compile(r"\[AC-\d{2}(?:,\s*AC-\d{2})*\]")
UNDERLYING_SOURCE_RE = re.compile(
    r"(?i:https?)://|\b[A-Z][A-Z0-9]+-\d+\b|(?i:\b(?:Jira (?:UAC|description|comment)|"
    r"RAG (?:URL|chunk)|DITA (?:spec|source)|Figma (?:node|frame)|attachment(?: ID)?|"
    r"source file|commit [0-9a-f]{7,40})\b)|(?i:\b(?:DOC|SPEC|CHUNK|SOURCE):\S+)|[A-Za-z]:[\\/]",
)
GRAPH_PATH_ONLY_RE = re.compile(
    r"(?i)^(?:graph[- ]?)?path(?:\s+id)?(?:\s*[:=]\s*|\s+)\S+$"
)
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
MAIN_FEATURE_COVERAGE_RE = re.compile(
    r"^- Main feature coverage:\s*(?:Covered|Partially covered|Not covered|Unverified)\b",
    re.IGNORECASE,
)
AUTOMATION_VERDICT_RE = re.compile(
    r"\b(?:Covered|Partially covered|Not covered|Unverified)\b",
    re.IGNORECASE,
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
    parsed_acceptance: list[tuple[int, dict[str, str]]] = []
    for number, line in acceptance:
        criterion = parse_ac_line(line)
        if criterion is None:
            errors.append(
                f"line {number}: acceptance criterion must use the exact machine-readable format `{AC_EXACT_FORMAT}`"
            )
            continue
        parsed_acceptance.append((number, criterion))
        if criterion["sphere"] == "Performance":
            if not QUANTIFIED_WORKLOAD_RE.search(criterion["given"]):
                errors.append(
                    f"line {number}: Performance Given must define a quantified workload "
                    "(for example topic count, user count, job count, or iterations)"
                )
            if not (
                QUANTIFIED_VALUE_RE.search(criterion["then"])
                or COMPARATIVE_ORACLE_RE.search(criterion["then"])
            ):
                errors.append(
                    f"line {number}: Performance Then must define a measurable numeric or "
                    "source-backed comparative oracle; if no approved threshold exists, keep "
                    "performance conditional in Open Questions"
                )
        if native_ac_empty and criterion["status"] == "Confirmed":
            errors.append(f"line {number}: derived criterion cannot be Confirmed when Jira AC is empty")
        if destructive.search(line):
            errors.append(f"line {number}: destructive operational procedure is not a product acceptance criterion")
        if prescribed.search(line):
            errors.append(f"line {number}: acceptance criterion prescribes an unapproved implementation choice")
        evidence = criterion["evidence"]
        if GRAPH_PATH_ONLY_RE.fullmatch(evidence):
            errors.append(
                f"line {number}: Evidence must cite the graph leaf's underlying Jira, URL/chunk, "
                "DITA source, Figma node, attachment, or inspected code - never only a graph path"
            )
        elif not UNDERLYING_SOURCE_RE.search(evidence):
            errors.append(
                f"line {number}: Evidence must cite an underlying Jira, URL/chunk, DITA source, Figma node, "
                "attachment, inspected code path, or graph leaf - never only a graph path"
            )
    errors.extend(validate_ac_sequence([criterion for _, criterion in parsed_acceptance]))

    scenarios = sections["Test Scenarios"]
    if not any(line.startswith("- Test data to prepare:") for _, line in scenarios):
        errors.append("Test Scenarios must begin with explicit 'Test data to prepare:' guidance")
    for number, line in scenarios:
        if SCENARIO_RE.match(line) and "Incident recovery validation" not in line and not AC_LINK_RE.search(line):
            errors.append(f"line {number}: P0/P1/P2 scenario is missing an AC mapping")
        if SCENARIO_RE.match(line) and ("Action:" not in line or "Expected:" not in line):
            errors.append(f"line {number}: P0/P1/P2 scenario must use plain-English Action: and Expected: wording")

    defined_acs = {criterion["id"] for _, criterion in parsed_acceptance}
    scenario_acs: set[str] = set()
    for _, line in sections["Test Scenarios"]:
        for group in AC_LINK_RE.findall(line):
            linked = set(re.findall(r"AC-\d{2}", group))
            scenario_acs.update(linked)
    automation_lines = [line for _, line in sections["Automation Coverage & Gaps"]]
    automation_acs = {
        ac
        for line in automation_lines
        if AUTOMATION_VERDICT_RE.search(line)
        and not line.lower().startswith("- main feature coverage:")
        for ac in re.findall(r"AC-\d{2}", line)
    }
    for ac in sorted(defined_acs):
        if ac not in scenario_acs:
            errors.append(f"acceptance criterion {ac} has no Test Scenarios mapping")
        if ac not in automation_acs:
            errors.append(f"acceptance criterion {ac} has no verdict in Automation Coverage & Gaps")

    main_feature_coverage = [
        line for line in automation_lines if MAIN_FEATURE_COVERAGE_RE.match(line)
    ]
    if len(main_feature_coverage) != 1:
        errors.append(
            "Automation Coverage & Gaps must contain exactly one 'Main feature coverage: "
            "Covered|Partially covered|Not covered|Unverified' bullet"
        )

    scenario_lines = sections["Test Scenarios"]
    if scenario_lines and not any(
        line.lower().startswith(("- setup and test data", "- test data to prepare:"))
        for _, line in scenario_lines
    ):
        errors.append(
            "Test Scenarios must include at least one 'Test data to prepare:' bullet with concrete "
            "fixtures, identifier/example values, config, environment, and oracles"
        )

    for number, line in sections["Regression Areas"]:
        content = line[2:].strip() if line.startswith("- ") else line.strip()
        if content and len(content) < 60:
            errors.append(
                f"line {number}: Regression Areas bullet is too terse to be a QA regression item; "
                f"state what to re-test and the risk, not just an area name"
            )

    for number, line in sections["Open Questions"]:
        lowered = line.lower()
        if "no open questions" in lowered:
            continue
        if line.startswith("- ") and "impact" not in lowered:
            errors.append(
                f"line {number}: Open Questions bullet must state the QA impact of the answer "
                f"(name the decision and what each possible answer changes for testing)"
            )

    scope_text = "\n".join(line for _, line in sections["Scope From Git"]).lower()
    if re.search(r"[a-z]:[\\/]", scope_text):
        mentions_sha = "sha" in scope_text
        acknowledges = any(
            token in scope_text
            for token in ("not captured", "not recorded", "provisional", "anchored to the inspected", "verified remote ref")
        )
        synced = any(token in scope_text for token in ("ahead", "behind", "fast-forward", "fetched", "synced"))
        if not (mentions_sha and (acknowledges or synced)):
            errors.append(
                "Scope From Git cites a clone path but does not state its sync/SHA state; give the captured SHA "
                "plus fetch/ahead/behind, or an explicit provisional acknowledgment that the SHA was not captured"
            )

    jira_key_re = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
    known_bug_text = "\n".join(line for _, line in sections["Known Jira Bugs / Past Similar Tickets"])
    known_bug_keys = set(jira_key_re.findall(known_bug_text))
    for number, line in sections["Regression Areas"]:
        for key in jira_key_re.findall(line):
            if key.startswith("AC-"):
                continue
            if key not in known_bug_keys:
                errors.append(
                    f"line {number}: Regression Areas cites Jira {key} that is not vetted and listed in "
                    f"Known Jira Bugs; do not name-drop unrelated tickets"
                )

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

    history_terms = ("Similarity:", "Status:", "Resolution:", "Affected version:", "Fix version:", "RCA:", "Test evidence:", "Impact:")
    strength_terms = ("strongest", "structural twin", "adjacent", "weak", "setup-only", "setup only", "closest")
    for number, line in sections["Known Jira Bugs / Past Similar Tickets"]:
        if JIRA_RE.match(line):
            missing = [term for term in history_terms if term.lower() not in line.lower()]
            if missing:
                errors.append(f"line {number}: historical Jira entry is missing {', '.join(missing)}")
            lowered = line.lower()
            if "similarity:" in lowered:
                similarity_clause = lowered.split("similarity:", 1)[1].split("status:", 1)[0]
                if not any(term in similarity_clause for term in strength_terms):
                    errors.append(
                        f"line {number}: historical Jira entry must state a match strength in its Similarity "
                        f"clause (e.g. strongest match, structural twin, adjacent, weak/setup-only) so area-only "
                        f"or keyword-only matches are not padded into this section"
                    )
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
                errors.append(f"line {number}: customer profile evidence is missing {', '.join(missing)}")
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
