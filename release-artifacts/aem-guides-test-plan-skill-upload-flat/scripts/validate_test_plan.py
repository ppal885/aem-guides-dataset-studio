#!/usr/bin/env python3
"""Validate AEM Guides test plans (compact 3-section template, plain-English friendly)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ACTION_HEADINGS = (
    "## 1. Action items (QA — start here)",
    "## 1. Action items",
)
SUPPLEMENTARY_HEADINGS = (
    "## 2. Supplementary — context, risks & traceability",
    "## 2. Supplementary",
)
SUMMARY_HEADINGS = (
    "## 1. Summary & expected behaviour",
    "## 1. Summary & what should happen",
)
BLAST_HEADINGS = (
    "## 2. Blast radius & risks",
    "## 2. What can break & risks",
)
SCENARIOS_HEADINGS = (
    "## 3. Scenarios & release",
    "## 3. Test scenarios & release",
)

CHANGE_PATH_HEADINGS = ("### Change path", "### Code path (where the fix lives)")
MUST_NOT_REGRESS_HEADINGS = (
    "### Must not regress (R0)",
    "### Must not break (regression checks)",
)
HYPOTHESIS_HEADINGS = (
    "### Bug hypotheses (top 3 only)",
    "### Likely bugs to watch (top 3)",
)
HISTORICAL_HEADINGS = (
    "### Related past Jiras (historical regression)",
    "### Related past Jiras",
)
RESIDUAL_HEADINGS = (
    "### Residual risk & sign-off",
    "### What's left & sign-off",
)
EVIDENCE_HEADINGS = (
    "### Key evidence (inline)",
    "### Where we got the facts (evidence)",
)
ACCEPTANCE_HEADINGS = (
    "### Acceptance criteria (UAC)",
    "### Sign-off checks (minimum before release)",
    "### Sign-off checks (acceptance from Jira)",
)

IMPACT_TABLES = (
    "| Area | Impact | Why | Scenario / exclusion |",
    "| Area | Impact | Why | Test / skip |",
)
RISK_TABLES = (
    "| Risk ID | Priority | Failure mode | Scenario / exclusion |",
    "| Risk ID | Priority | What goes wrong | Test / skip |",
)
SCENARIO_TABLES = (
    "| Scenario ID | Priority | Title | Trace (EB / risk) | Oracle summary |",
    "| Scenario ID | Priority | Title | Links to | How to verify |",
)
AUTOMATION_TABLE = "| Check | Layer | Strength | Gap |"
AUTOMATION_TABLE_ALT = "| Check | Where | Coverage | Gap |"
HYPOTHESIS_TABLE = "| ID | Suspected bug | Signal | Scenario |"
HYPOTHESIS_TABLE_ALT = "| ID | What we suspect | How you'd notice | Test |"
HISTORICAL_TABLE = "| Jira | Signal | Why it matters for this ticket | Scenario influenced |"
HISTORICAL_TABLE_ALT = "| Jira | What happened | Why it matters here | Test |"
EVIDENCE_TABLE = "| Evidence ID | Source | Classification | What it proves | Link / path |"
CONFIDENCE_TABLE = "| Dimension | Score | Evidence / deduction |"

LOCAL_REPO_PATH_RE = re.compile(
    r"(?:xmleditor|starling|guides-ui-tests|dxml-it-tests).*[\\/].+|\b[A-Za-z]:[\\/].+|/[A-Za-z0-9_.-]+/.+",
    re.I,
)

VALID_IMPACT_LEVELS = {
    "Direct",
    "Shared-path",
    "Downstream",
    "Compatibility",
    "Not impacted",
    "Unknown",
}

VALID_AUTOMATION_STRENGTHS = {
    "Exact and strong",
    "Exact but weak oracle",
    "Exact but weak check",
    "Partial",
    "Obsolete",
    "Mocked-path only",
    "Missing",
    "Best match for this bug",
}
VALID_CLASSIFICATIONS = {
    "ticket-confirmed",
    "documentation-confirmed",
    "specification-confirmed",
    "implementation-derived",
    "previous-JIRA-derived",
    "assumption",
    "human-clarification-required",
}

VAGUE_CHECK_PATTERNS = re.compile(
    r"\b(no error|no errors|works correctly|works as expected|verify behavior|should work|successfully works)\b",
    re.I,
)
DRAFT_STATUS = re.compile(r"Review status:\*{0,2}\s*Draft\b", re.I)
READY_STATUS = re.compile(r"Review status:\*{0,2}\s*Review-ready\b", re.I)
ROUTING_STATUS = re.compile(r"\b(QE_REVIEW_READY|QE_REVIEW_WITH_FLAGS|Draft-human-clarification|HUMAN_INPUT_REQUIRED)\b")
SCORE_LINE = re.compile(r"\bScore:\*{0,2}\s*(\d{1,3})\b", re.I)
QE_REQUIRED = re.compile(r"\bQE review:\*{0,2}\s*Required\b|\bQE review package\b", re.I)
MISSING_EVIDENCE = re.compile(r"\b(missing|unavailable|not inspected|not available|unknown|not configured)\b", re.I)
EXCLUSION_WORD = re.compile(r"\b(excluded|exclusion|not impacted|exclude|skip)\b", re.I)
EB_BULLET = re.compile(r"\*\*EB-\d+:\*\*", re.I)
EVIDENCE_MAP_FORBIDDEN = re.compile(r"^##\s+3\.\s+Evidence map\b", re.M | re.I)
HOW_TO_CHECK = re.compile(r"\b(Multi-layer oracle|How to check)\b", re.I)


def _is_action_first_layout(text: str) -> bool:
    return any(h in text for h in ACTION_HEADINGS)


def validate_text(text: str) -> list[str]:
    errors: list[str] = []

    if EVIDENCE_MAP_FORBIDDEN.search(text):
        errors.append("Remove deprecated '## 3. Evidence map' section; use inline evidence in section 1.")

    if len(text.splitlines()) > 195:
        errors.append("Plan exceeds ~3-page limit (>195 lines); trim tables and prose.")

    action_first = _is_action_first_layout(text)

    if action_first:
        _require_one_of(errors, text, ACTION_HEADINGS, "Action items section")
        _require_one_of(errors, text, SUPPLEMENTARY_HEADINGS, "Supplementary section")
        _require_one_of(errors, text, ("### Summary & expected behaviour",), "Summary subsection")
        _require_one_of(errors, text, ("### What can break & risks",), "Risks subsection")
        _require_one_of(
            errors,
            text,
            EVIDENCE_HEADINGS
            + (
                "### Evidence & release status",
                "### Where we got the facts (evidence)",
            ),
            "Evidence subsection",
        )
        _require_one_of(errors, text, ("**Code path:**", "### Change path", "### Code path (where the fix lives)"), "Code path hint")
        _require_one_of(errors, text, IMPACT_TABLES, "Impact table")
        _require_one_of(errors, text, RISK_TABLES, "Risk table")
        if not any(h in text for h in MUST_NOT_REGRESS_HEADINGS) and "regression" not in text.lower():
            errors.append("Missing regression coverage (Must not break subsection or regression mention in risks).")
        _require_one_of(
            errors,
            text,
            HYPOTHESIS_HEADINGS
            + ("**Likely bugs to watch:**", "### Likely bugs to watch"),
            "Likely bugs subsection",
        )
        _require_one_of(errors, text, HISTORICAL_HEADINGS, "Related past Jiras subsection")
        _require_one_of(errors, text, (HISTORICAL_TABLE, HISTORICAL_TABLE_ALT), "Historical Jiras table header")
        _require_one_of(errors, text, ("### Test list (priority order)", "### Prioritized scenarios"), "Scenario list subsection")
        _require_one_of(errors, text, SCENARIO_TABLES, "Scenario table")
        _require_one_of(errors, text, ("### Steps for P0 / P1 tests", "### Scenario details (P0/P1 only)"), "Scenario steps subsection")
        _require_one_of(errors, text, ACCEPTANCE_HEADINGS, "Sign-off / acceptance subsection")
        _require_one_of(errors, text, ("### Automation coverage", "### Automation"), "Automation subsection")
        _require_one_of(errors, text, (AUTOMATION_TABLE, AUTOMATION_TABLE_ALT), "Automation table")
        _require_one_of(errors, text, (EVIDENCE_TABLE,), "Evidence classification table")
        _require_one_of(errors, text, (CONFIDENCE_TABLE,), "Confidence breakdown table")
        _require_one_of(errors, text, ("### QE review package",), "QE review package")
        _require_one_of(errors, text, ("### Evidence & release status", "### Residual risk & sign-off", "### What's left & sign-off"), "Release status subsection")
    else:
        _require_one_of(errors, text, SUMMARY_HEADINGS, "Summary section")
        _require_one_of(errors, text, ("### Expected behaviour",), "Expected behaviour")
        _require_one_of(errors, text, EVIDENCE_HEADINGS, "Evidence subsection")
        _require_one_of(errors, text, BLAST_HEADINGS, "Impact / risks section")
        _require_one_of(errors, text, CHANGE_PATH_HEADINGS, "Code path subsection")
        _require_one_of(errors, text, IMPACT_TABLES, "Impact table")
        _require_one_of(errors, text, RISK_TABLES, "Risk table")
        _require_one_of(errors, text, MUST_NOT_REGRESS_HEADINGS, "Regression checks subsection")
        _require_one_of(errors, text, HYPOTHESIS_HEADINGS, "Likely bugs subsection")
        _require_one_of(errors, text, HISTORICAL_HEADINGS, "Related past Jiras subsection")
        _require_one_of(errors, text, (HISTORICAL_TABLE, HISTORICAL_TABLE_ALT), "Historical Jiras table header")
        _require_one_of(errors, text, SCENARIOS_HEADINGS, "Scenarios section")
        _require_one_of(errors, text, ("### Prioritized scenarios", "### Test list (priority order)"), "Scenario list subsection")
        _require_one_of(errors, text, SCENARIO_TABLES, "Scenario table")
        _require_one_of(errors, text, ("### Scenario details (P0/P1 only)", "### Steps for P0 / P1 tests"), "Scenario steps subsection")
        _require_one_of(errors, text, ("### Automation", "### Automation coverage"), "Automation subsection")
        _require_one_of(errors, text, (AUTOMATION_TABLE, AUTOMATION_TABLE_ALT), "Automation table")
        _require_one_of(errors, text, (EVIDENCE_TABLE,), "Evidence classification table")
        _require_one_of(errors, text, (CONFIDENCE_TABLE,), "Confidence breakdown table")
        _require_one_of(errors, text, ("### QE review package",), "QE review package")
        _require_one_of(errors, text, RESIDUAL_HEADINGS, "Sign-off subsection")

    impact_header = _first_present(text, IMPACT_TABLES)
    risk_header = _first_present(text, RISK_TABLES)
    hypothesis_header = _first_present(text, (HYPOTHESIS_TABLE, HYPOTHESIS_TABLE_ALT))
    scenario_header = _first_present(text, SCENARIO_TABLES)
    automation_header = _first_present(text, (AUTOMATION_TABLE, AUTOMATION_TABLE_ALT))
    historical_header = _first_present(text, (HISTORICAL_TABLE, HISTORICAL_TABLE_ALT))
    evidence_header = _first_present(text, (EVIDENCE_TABLE,))
    confidence_header = _first_present(text, (CONFIDENCE_TABLE,))

    impact_rows = _table_rows(text, impact_header) if impact_header else []
    risk_rows = _table_rows(text, risk_header) if risk_header else []
    hypothesis_rows = _table_rows(text, hypothesis_header) if hypothesis_header else []
    scenario_rows = _table_rows(text, scenario_header) if scenario_header else []
    automation_rows = _table_rows(text, automation_header) if automation_header else []
    evidence_rows = _table_rows(text, evidence_header) if evidence_header else []
    confidence_rows = _table_rows(text, confidence_header) if confidence_header else []

    scenario_ids = _collect_ids(scenario_rows, 0)
    risk_ids = _collect_ids(risk_rows, 0)

    eb_count = len(EB_BULLET.findall(text))
    if eb_count < 3:
        errors.append("Expected behaviour needs at least 3 numbered EB-* bullets.")
    if eb_count > 10:
        errors.append("Expected behaviour has too many EB-* bullets (>10); keep 5–7.")

    _validate_impact_rows(errors, impact_rows, scenario_ids)
    _validate_risk_rows(errors, risk_rows, scenario_ids)
    _validate_hypotheses(errors, hypothesis_rows, scenario_ids)
    _validate_historical(errors, text, _table_rows(text, historical_header) if historical_header else [])
    _validate_scenarios(errors, text, scenario_rows, risk_ids)
    _validate_automation(errors, automation_rows)
    _validate_evidence_table(errors, evidence_rows)
    _validate_repository_evidence(errors, text, evidence_rows, automation_rows)
    _validate_confidence_and_qe(errors, text, confidence_rows)
    _validate_inline_evidence(errors, text)
    _validate_draft_gating(errors, text)

    if re.search(r"\bprobably impacted\b|\bmaybe impacted\b|\bassume(?:d)? impacted\b", text, re.I):
        errors.append("Label suspected impact as Unknown/provisional, not confirmed.")

    if READY_STATUS.search(text) and errors:
        errors.append("Plan cannot be Review-ready while semantic validation errors exist.")

    return errors


def _require_one_of(errors: list[str], text: str, options: tuple[str, ...], label: str) -> None:
    if not any(option in text for option in options):
        errors.append(f"Missing required content: {label} (expected one of: {options[0]}…)")


def _first_present(text: str, options: tuple[str, ...]) -> str | None:
    for option in options:
        if option in text:
            return option
    return None


def _validate_impact_rows(errors: list[str], rows: list[str], scenario_ids: set[str]) -> None:
    if not rows:
        errors.append("Impact table has no data rows.")
        return
    levels = {_cell(row, 1) for row in rows}
    if "Direct" not in levels:
        errors.append("Impact table must include at least one Direct item.")
    unknown_levels = sorted(level for level in levels if level and level not in VALID_IMPACT_LEVELS)
    if unknown_levels:
        errors.append(f"Invalid impact level(s): {', '.join(unknown_levels)}")
    for row in rows:
        level = _cell(row, 1)
        action = _cell(row, 3)
        area = _cell(row, 0)
        if level in {"Direct", "Shared-path"} and not (_has_existing_ref(action, scenario_ids) or EXCLUSION_WORD.search(action)):
            errors.append(f"{level} impact lacks scenario/exclusion mapping: {area}")


def _validate_risk_rows(errors: list[str], rows: list[str], scenario_ids: set[str]) -> None:
    if not rows:
        errors.append("Risk table has no data rows.")
        return
    for row in rows:
        risk_id = _cell(row, 0)
        priority = _cell(row, 1).upper()
        mapping = _cell(row, 3)
        if priority in {"P0", "P1", "HIGH", "CRITICAL"} and not (_has_existing_ref(mapping, scenario_ids) or EXCLUSION_WORD.search(mapping)):
            errors.append(f"P0/P1 risk missing scenario or exclusion: {risk_id}")


def _validate_hypotheses(errors: list[str], rows: list[str], scenario_ids: set[str]) -> None:
    if len(rows) > 3:
        errors.append("Likely bugs table has more than 3 rows; keep top 3 only.")
    for row in rows:
        hyp_id = _cell(row, 0)
        mapping = _cell(row, 3)
        if not (_has_existing_ref(mapping, scenario_ids) or EXCLUSION_WORD.search(mapping)):
            errors.append(f"Likely bug row missing test/exclusion mapping: {hyp_id}")


def _validate_historical(errors: list[str], text: str, rows: list[str]) -> None:
    if rows:
        if len(rows) > 5:
            errors.append("Related past Jiras table has more than 5 rows; keep max 5.")
        for row in rows:
            jira = _cell(row, 0)
            signal = _cell(row, 1)
            if not jira or not signal:
                errors.append(f"Historical Jira row missing Jira key or description: {jira or '(blank)'}")
        return
    if "Historical search:" not in text and "no related Jiras found" not in text.lower():
        errors.append("Related past Jiras section must have data rows or a 'Historical search: no related Jiras found' line.")


def _validate_scenarios(errors: list[str], text: str, rows: list[str], risk_ids: set[str]) -> None:
    if not rows:
        errors.append("Scenario table has no rows.")
        return
    if len(rows) > 10:
        errors.append("Scenario table exceeds 10 rows.")
    if not any(re.search(r"\bR0\b", _cell(row, 0) + _cell(row, 1), re.I) for row in rows):
        errors.append("At least one R0 regression scenario is required.")
    for row in rows:
        scenario_id = _cell(row, 0)
        trace = _cell(row, 3)
        check_col = _cell(row, 4)
        if not check_col or VAGUE_CHECK_PATTERNS.search(check_col):
            errors.append(f"Scenario has missing/vague pass criteria: {scenario_id}")
        if not (re.search(r"\bEB-\d+\b", trace, re.I) or _has_existing_ref(trace, risk_ids) or EXCLUSION_WORD.search(trace)):
            errors.append(f"Scenario must link to EB-* or risk ID: {scenario_id}")
        detail = _scenario_detail(text, scenario_id)
        if _cell(row, 1).upper() in {"P0", "P1"} and detail and not HOW_TO_CHECK.search(detail):
            errors.append(f"P0/P1 scenario missing 'How to check' steps: {scenario_id}")


def _validate_automation(errors: list[str], rows: list[str]) -> None:
    if not rows:
        errors.append("Automation table has no rows.")
        return
    for row in rows:
        strength = _cell(row, 2)
        if strength not in VALID_AUTOMATION_STRENGTHS:
            errors.append(f"Invalid automation coverage label: {strength or '(blank)'}")


def _validate_evidence_table(errors: list[str], rows: list[str]) -> None:
    if not rows:
        errors.append("Evidence table has no data rows.")
        return
    if len(rows) > 10:
        errors.append("Evidence table has more than 10 rows; keep it compact.")
    seen_classifications: set[str] = set()
    for row in rows:
        evidence_id = _cell(row, 0)
        classification = _cell(row, 2)
        proof = _cell(row, 3)
        link = _cell(row, 4)
        if not evidence_id:
            errors.append("Evidence row missing Evidence ID.")
        if classification not in VALID_CLASSIFICATIONS:
            errors.append(f"Invalid evidence classification: {classification or '(blank)'}")
        else:
            seen_classifications.add(classification)
        if not proof:
            errors.append(f"Evidence row missing what it proves: {evidence_id or '(blank)'}")
        if not link:
            errors.append(f"Evidence row missing link/path: {evidence_id or '(blank)'}")
    if "ticket-confirmed" not in seen_classifications:
        errors.append("Evidence table must include at least one ticket-confirmed row.")


def _validate_repository_evidence(
    errors: list[str],
    text: str,
    evidence_rows: list[str],
    automation_rows: list[str],
) -> None:
    """Enforce local repo evidence for Review-ready plans and strong automation claims."""
    evidence_blob = "\n".join(evidence_rows)
    automation_blob = "\n".join(automation_rows)
    review_ready = bool(READY_STATUS.search(text) or "QE_REVIEW_READY" in text)
    product_repo = re.search(r"\b(xmleditor|starling)\b.*[\\/].+:\d+|[\\/](xmleditor|starling)[\\/].+:\d+", evidence_blob, re.I)
    test_repo = re.search(r"\b(guides-ui-tests|dxml-it-tests)\b.*[\\/].+:\d+|[\\/](guides-ui-tests|dxml-it-tests)[\\/].+:\d+", evidence_blob + "\n" + automation_blob, re.I)
    if review_ready and not product_repo:
        errors.append("Review-ready plan requires local product repo evidence with xmleditor/starling path:line.")
    for row in automation_rows:
        strength = _cell(row, 2)
        if strength and strength not in {"Missing", "Partial"} and not test_repo:
            errors.append("Non-missing strong automation coverage requires guides-ui-tests or dxml-it-tests path:line evidence.")
            break


def _validate_confidence_and_qe(errors: list[str], text: str, rows: list[str]) -> None:
    if not rows:
        errors.append("Confidence breakdown table has no data rows.")
        return
    dimensions = {_cell(row, 0).lower() for row in rows}
    required = {
        "ticket completeness",
        "retrieval quality",
        "evidence coverage",
        "source consistency",
        "sign-off testability",
        "requirement traceability",
    }
    missing = sorted(required - dimensions)
    if missing:
        errors.append(f"Confidence breakdown missing dimension(s): {', '.join(missing)}")
    for row in rows:
        dimension = _cell(row, 0)
        score = _cell(row, 1)
        if not re.fullmatch(r"\d{1,3}", score):
            errors.append(f"Confidence row has non-numeric score: {dimension or '(blank)'}")
            continue
        value = int(score)
        if value < 0 or value > 100:
            errors.append(f"Confidence row score out of range 0-100: {dimension}")
    score_match = SCORE_LINE.search(text)
    if not score_match:
        errors.append("Plan header must include deterministic Score: <0-100>.")
    elif int(score_match.group(1)) > 100:
        errors.append("Plan score must be in range 0-100.")
    if not ROUTING_STATUS.search(text):
        errors.append("Plan must include routing status: QE_REVIEW_READY, QE_REVIEW_WITH_FLAGS, or Draft-human-clarification.")
    if not QE_REQUIRED.search(text):
        errors.append("QE review must be explicitly required; high score must not auto-approve.")


def _validate_inline_evidence(errors: list[str], text: str) -> None:
    if not READY_STATUS.search(text):
        return
    if not LOCAL_REPO_PATH_RE.search(text):
        errors.append("Review-ready plan requires code/repo path in section 1.")


def _validate_draft_gating(errors: list[str], text: str) -> None:
    if "Release confidence:" not in text:
        errors.append("Sign-off section must include Release confidence.")
    if MISSING_EVIDENCE.search(text) and READY_STATUS.search(text) and not DRAFT_STATUS.search(text):
        errors.append("Missing evidence requires Draft status, not Review-ready.")


def _section(text: str, start_heading: str, end_heading: str) -> str:
    start = text.index(start_heading)
    try:
        end = text.index(end_heading, start + len(start_heading))
    except ValueError:
        end = len(text)
    return text[start:end]


def _table_rows(text: str, header: str) -> list[str]:
    lines = text.splitlines()
    rows: list[str] = []
    for index, line in enumerate(lines):
        if line.strip() != header:
            continue
        cursor = index + 2
        while cursor < len(lines) and lines[cursor].strip().startswith("|"):
            row = lines[cursor].strip()
            if not re.match(r"^\|\s*-", row):
                rows.append(row)
            cursor += 1
        break
    return rows


def _cell(row: str, index: int) -> str:
    cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
    return cells[index] if index < len(cells) else ""


def _collect_ids(rows: list[str], index: int) -> set[str]:
    return {_cell(row, index).strip() for row in rows if _cell(row, index).strip()}


def _has_existing_ref(text: str, known_ids: set[str]) -> bool:
    return any(identifier and identifier in text for identifier in known_ids)


def _scenario_detail(text: str, scenario_id: str) -> str:
    pattern = re.compile(
        rf"-\s*\*\*{re.escape(scenario_id)}\*\*(.*?)(?=\n-\s*\*\*S-|\n###\s+|\n##\s+\d+\.|\Z)",
        re.S | re.I,
    )
    match = pattern.search(text)
    return match.group(0) if match else ""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    args = parser.parse_args(argv)
    text = args.plan.read_text(encoding="utf-8")
    errors = validate_text(text)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("OK: test plan satisfies compact template validation gates.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
