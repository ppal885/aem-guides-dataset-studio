#!/usr/bin/env python3
"""Validate AEM Guides test plans for blast-radius and bug-discovery quality gates."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


BLAST_HEADING = "## 4. Blast radius and risk analysis"
CLASSIFICATION_TABLE = "| Area / component | Impact level | Why affected | Evidence | Regression action |"
RISK_TABLE = "| Risk ID | Surface / failure mode | User/business impact | Likelihood | Priority | Evidence | Scenario / exclusion |"
BUG_HYPOTHESIS_TABLE = "| Hypothesis ID | Rank | Trigger / heuristic | Suspected bug | Evidence / signal | Confidence | Scenario / exclusion |"
KILL_FIX_TABLE = "| Changed branch / contract | Escape mode | Test to kill incomplete fix | Evidence | Scenario / exclusion |"
HISTORICAL_TABLE = "| Historical Jira | Signal type | Why it matters | Risk / hypothesis influenced | Automation lesson |"
INTERACTION_TABLE = "| Interaction ID | Selected combination | Why this can exercise changed path | Risk / hypothesis | Scenario |"
SCENARIO_TABLE = "| Scenario ID | Ring | Pack | Priority | Title | Trace to risk / hypothesis / evidence | Automation layer | Oracle summary |"
AUTOMATION_TABLE = "| Existing / proposed check | Layer | Strength classification | Why | Gap / action |"
EXCLUSION_TABLE = "| Area / component | Reason excluded | Evidence |"
EVIDENCE_TABLE = "| Evidence ID | Source | What it proves | Link / path |"

VALID_IMPACT_LEVELS = {
    "Direct",
    "Shared-path",
    "Downstream",
    "Compatibility",
    "Observability/Recovery",
    "Not impacted",
    "Unknown",
}

VALID_AUTOMATION_STRENGTHS = {
    "Exact and strong",
    "Exact but weak oracle",
    "Partial",
    "Obsolete",
    "Mocked-path only",
    "Missing",
}

REQUIRED_HEADINGS = [
    BLAST_HEADING,
    "## 5. Bug hypothesis register",
    "## 6. Kill the Fix analysis",
    "## 7. Historical regression signals",
    "## 8. Interaction matrix",
    "## 9. Prioritized scenarios",
    "## 10. Detailed test scenarios",
    "## 11. Automation strength assessment",
    "## 12. Regression pack split",
    "## 13. Focused exploratory charters",
    "## 14. Residual Risk and Release Confidence",
    "## 15. Traceability and quality gates",
]

REQUIRED_BLAST_CONTENT = [
    "### Execution/change-path narrative",
    CLASSIFICATION_TABLE,
    RISK_TABLE,
    "### Existing behavior that must remain unchanged",
    "### Minimum direct regression",
    "### Shared-path regression",
    "### Downstream regression",
    "### Conditional regression",
    "### Explicit exclusions",
    "### Unknowns that can expand the scope",
]

VAGUE_ORACLE_PATTERNS = re.compile(
    r"\b(no error|no errors|works correctly|works as expected|verify behavior|should work|successfully works)\b",
    re.I,
)
DRAFT_STATUS = re.compile(r"Review status:\s*Draft\b", re.I)
READY_STATUS = re.compile(r"Review status:\s*Review-ready\b", re.I)
MISSING_EVIDENCE = re.compile(r"\b(missing|unavailable|not inspected|not available|unknown|not configured)\b", re.I)
SCENARIO_REF = re.compile(r"\b(?:SC|TC|S)-\d{2,4}\b", re.I)
RISK_REF = re.compile(r"\b(?:BR|RISK)-\d{1,4}\b", re.I)
HYP_REF = re.compile(r"\bBH-\d{1,4}\b", re.I)
EVIDENCE_REF = re.compile(r"\bE\d{1,4}\b")
EXCLUSION_WORD = re.compile(r"\b(excluded|exclusion|not impacted|exclude)\b", re.I)


def validate_text(text: str) -> list[str]:
    errors: list[str] = []

    for heading in REQUIRED_HEADINGS:
        if heading not in text:
            errors.append(f"Missing required heading: {heading}")
    if BLAST_HEADING not in text:
        return errors

    blast = _section(text, BLAST_HEADING)
    for required in REQUIRED_BLAST_CONTENT:
        if required not in blast:
            errors.append(f"Missing required blast-radius content: {required}")

    evidence_ids = _collect_ids(_table_rows(text, EVIDENCE_TABLE), 0)
    impact_rows = _table_rows(blast, CLASSIFICATION_TABLE)
    risk_rows = _table_rows(blast, RISK_TABLE)
    hypothesis_rows = _table_rows(text, BUG_HYPOTHESIS_TABLE)
    kill_rows = _table_rows(text, KILL_FIX_TABLE)
    historical_rows = _table_rows(text, HISTORICAL_TABLE)
    interaction_rows = _table_rows(text, INTERACTION_TABLE)
    scenario_rows = _table_rows(text, SCENARIO_TABLE)
    automation_rows = _table_rows(text, AUTOMATION_TABLE)
    exclusion_rows = _table_rows(blast, EXCLUSION_TABLE)

    scenario_ids = _collect_ids(scenario_rows, 0)
    risk_ids = _collect_ids(risk_rows, 0)
    hypothesis_ids = _collect_ids(hypothesis_rows, 0)
    interaction_ids = _collect_ids(interaction_rows, 0)

    _validate_impact_rows(errors, impact_rows, scenario_ids)
    _validate_risk_rows(errors, risk_rows, scenario_ids)
    _validate_hypotheses(errors, hypothesis_rows, scenario_ids)
    _validate_kill_fix(errors, text, kill_rows, scenario_ids)
    _validate_historical(errors, historical_rows)
    _validate_interactions(errors, interaction_rows, scenario_ids)
    _validate_scenarios(errors, text, scenario_rows, risk_ids, hypothesis_ids, interaction_ids, evidence_ids)
    _validate_automation(errors, automation_rows)
    _validate_exclusions(errors, exclusion_rows)
    _validate_bug_plan_coverage(errors, text, scenario_rows)
    _validate_draft_gating(errors, text)

    if re.search(r"\bprobably impacted\b|\bmaybe impacted\b|\bassume(?:d)? impacted\b", text, re.I):
        errors.append("Suspected impact appears to be presented without confirmed evidence; label as Unknown/provisional.")

    if READY_STATUS.search(text) and errors:
        errors.append("Plan cannot be Review-ready while semantic validation errors exist.")

    return errors


def _validate_impact_rows(errors: list[str], rows: list[str], scenario_ids: set[str]) -> None:
    if not rows:
        errors.append("Blast-radius classification table has no data rows.")
        return
    levels = {_cell(row, 1) for row in rows}
    if "Direct" not in levels:
        errors.append("Blast-radius classification table must identify at least one Direct impact.")
    unknown_levels = sorted(level for level in levels if level and level not in VALID_IMPACT_LEVELS)
    if unknown_levels:
        errors.append(f"Invalid impact level(s): {', '.join(unknown_levels)}")
    for row in rows:
        level = _cell(row, 1)
        action = _cell(row, 4)
        area = _cell(row, 0)
        if level in {"Direct", "Shared-path"} and not (_has_existing_ref(action, scenario_ids) or EXCLUSION_WORD.search(action)):
            errors.append(f"{level} blast-radius item lacks scenario/exclusion mapping: {area}")


def _validate_risk_rows(errors: list[str], rows: list[str], scenario_ids: set[str]) -> None:
    if not rows:
        errors.append("Failure/risk register has no data rows.")
        return
    for row in rows:
        risk_id = _cell(row, 0)
        priority = _cell(row, 4).upper()
        mapping = _cell(row, 6)
        if priority in {"P0", "P1", "HIGH", "CRITICAL"} and not (_has_existing_ref(mapping, scenario_ids) or EXCLUSION_WORD.search(mapping)):
            errors.append(f"P0/P1 risk missing scenario or exclusion: {risk_id}")


def _validate_hypotheses(errors: list[str], rows: list[str], scenario_ids: set[str]) -> None:
    if not rows:
        errors.append("Bug Hypothesis Register has no data rows.")
        return
    for row in rows:
        hyp_id = _cell(row, 0)
        mapping = _cell(row, 6)
        if not (_has_existing_ref(mapping, scenario_ids) or EXCLUSION_WORD.search(mapping)):
            errors.append(f"Bug hypothesis missing scenario/exclusion mapping: {hyp_id}")


def _validate_kill_fix(errors: list[str], text: str, rows: list[str], scenario_ids: set[str]) -> None:
    diff_available = re.search(r"Diff evidence:\s*(available|yes|inspected)", text, re.I)
    diff_not_inspected = "Diff not inspected" in text
    if diff_available and not rows:
        errors.append("Fix diff was inspected but Kill the Fix table has no rows.")
        return
    if diff_available:
        for row in rows:
            contract = _cell(row, 0)
            mapping = _cell(row, 4)
            if not (_has_existing_ref(mapping, scenario_ids) or EXCLUSION_WORD.search(mapping)):
                errors.append(f"Kill-the-fix item missing scenario/exclusion mapping: {contract}")
    elif not diff_not_inspected:
        errors.append("Kill the Fix section must state diff not inspected or provide changed-branch coverage.")


def _validate_historical(errors: list[str], rows: list[str]) -> None:
    if not rows:
        errors.append("Historical Jira search/signals are missing.")
        return
    if not any(_cell(row, 1).strip() for row in rows):
        errors.append("Historical Jira rows must include signal types; treat history as risk signals, not specs.")


def _validate_interactions(errors: list[str], rows: list[str], scenario_ids: set[str]) -> None:
    if not rows:
        errors.append("Interaction matrix has no selected targeted/pairwise interactions.")
        return
    for row in rows:
        interaction_id = _cell(row, 0)
        why = _cell(row, 2)
        scenario = _cell(row, 4)
        if len(why) < 12:
            errors.append(f"Interaction lacks explanation of changed-path exercise: {interaction_id}")
        if not _has_existing_ref(scenario, scenario_ids):
            errors.append(f"Interaction missing scenario mapping: {interaction_id}")


def _validate_scenarios(
    errors: list[str],
    text: str,
    rows: list[str],
    risk_ids: set[str],
    hypothesis_ids: set[str],
    interaction_ids: set[str],
    evidence_ids: set[str],
) -> None:
    if not rows:
        errors.append("Prioritized scenario table has no scenario rows.")
        return
    if not any(_cell(row, 1).startswith("R0") for row in rows):
        errors.append("At least one R0 control scenario is required.")
    packs = {_cell(row, 2) for row in rows}
    if "PR Gate" not in packs:
        errors.append("Regression pack split must include PR Gate scenario coverage.")
    for row in rows:
        scenario_id = _cell(row, 0)
        trace = _cell(row, 5)
        oracle = _cell(row, 7)
        if not oracle or VAGUE_ORACLE_PATTERNS.search(oracle):
            errors.append(f"Scenario has missing/vague observable oracle: {scenario_id}")
        if not _references_any_known_id(trace, risk_ids, hypothesis_ids, interaction_ids, evidence_ids):
            errors.append(f"Scenario trace references no known risk/hypothesis/interaction/evidence ID: {scenario_id}")
        detail = _scenario_detail(text, scenario_id)
        if detail and "Multi-layer oracle" not in detail:
            errors.append(f"Detailed scenario missing Multi-layer oracle field: {scenario_id}")


def _validate_automation(errors: list[str], rows: list[str]) -> None:
    if not rows:
        errors.append("Automation strength assessment has no rows.")
        return
    for row in rows:
        strength = _cell(row, 2)
        if strength not in VALID_AUTOMATION_STRENGTHS:
            errors.append(f"Invalid automation strength classification: {strength or '(blank)'}")


def _validate_exclusions(errors: list[str], rows: list[str]) -> None:
    for row in rows:
        area = _cell(row, 0)
        reason = _cell(row, 1)
        evidence = _cell(row, 2)
        if not reason or not evidence:
            errors.append(f"Exclusion lacks reason/evidence: {area}")


def _validate_bug_plan_coverage(errors: list[str], text: str, scenario_rows: list[str]) -> None:
    is_bug = re.search(r"\b(bug|regression|defect|reopened|customer reproduction|reproduction)\b", text, re.I)
    if not is_bug:
        return
    combined = "\n".join(_cell(row, 4) + " " + _cell(row, 5) + " " + _cell(row, 7) for row in scenario_rows) + "\n" + text
    required = {
        "reproduction": r"\brepro(?:duction)?\b|customer reproduction|minimal reproduction",
        "control": r"\bR0\b|control",
        "negative": r"\bnegative\b|invalid|malformed|empty|missing",
        "recovery": r"\brecover(?:y)?\b|rollback|retry|reopen|state/recovery",
    }
    for name, pattern in required.items():
        if not re.search(pattern, combined, re.I):
            errors.append(f"Bug plan lacks required {name} coverage.")


def _validate_draft_gating(errors: list[str], text: str) -> None:
    missing_evidence_lines = [
        line
        for line in text.splitlines()
        if MISSING_EVIDENCE.search(line)
        and not re.search(r":\s*(none|not applicable|n/a|yes)\.?\s*$", line, re.I)
        and not re.match(r"\|\s*Unknown\s*\|", line)
    ]
    if missing_evidence_lines and READY_STATUS.search(text) and not DRAFT_STATUS.search(text):
        errors.append("Missing Jira/RAG/code/diff evidence requires Draft status, not Review-ready.")
    if "Release confidence:" not in text:
        errors.append("Residual Risk and Release Confidence section must include Release confidence.")


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    match = re.search(r"^##\s+\d+\.", text[start + len(heading) :], re.M)
    end = start + len(heading) + match.start() if match else len(text)
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


def _references_any_known_id(text: str, *known_sets: set[str]) -> bool:
    return any(_has_existing_ref(text, known) for known in known_sets)


def _scenario_detail(text: str, scenario_id: str) -> str:
    pattern = re.compile(rf"Scenario ID:\s*{re.escape(scenario_id)}\b(.*?)(?=\n\s*-\s*Scenario ID:|\n##\s+\d+\.|\Z)", re.S | re.I)
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
    print("OK: test plan satisfies blast-radius and bug-discovery validation gates.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
