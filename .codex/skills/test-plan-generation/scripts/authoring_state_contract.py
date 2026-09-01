"""Deterministic UAC routing for editor state and structural authoring defects."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SCHEMA_VERSION = "aem-guides-authoring-state-contract-v2"

_MAP_PREVIEW_RE = re.compile(
    r"\bmap\s+preview\b|\bpreview\s+mode\b.*\bmap\b|\bcondition(?:s)?\s+panel\b",
    re.I | re.S,
)
_AUTHORING_VIEWPORT_RE = re.compile(
    r"\b(author(?:ing)?\s+(?:view|canvas)|editing\s+screen|active\s+(?:element|cursor|caret)|"
    r"reference\s+(?:link|insertion)|insert(?:ing)?\s+(?:an?\s+)?(?:xref|reference)|scroll(?:s|ed|ing)?\s+(?:up|to\s+the\s+top))\b",
    re.I,
)
_SCROLL_RE = re.compile(r"\b(scroll|viewport|active\s+location|cursor|caret)\b", re.I)
_CALS_DELETE_RE = re.compile(
    r"(?=.*\b(?:cals|table)\b)(?=.*\bdelet(?:e|ed|ing)\b)"
    r"(?=.*\b(?:two|2|multiple)\s+(?:selected\s+)?columns?\b)",
    re.I | re.S,
)
_LARGE_FILE_RE = re.compile(r"\blargeFileTagCount\b", re.I)


def classify_contract(issue_text: str) -> str | None:
    """Return one mutually exclusive authoring contract route."""
    if _LARGE_FILE_RE.search(issue_text):
        return "large_file_configuration"
    if _CALS_DELETE_RE.search(issue_text):
        return "cals_multi_column_delete"
    if _MAP_PREVIEW_RE.search(issue_text):
        return "map_preview_state"
    if _AUTHORING_VIEWPORT_RE.search(issue_text) and _SCROLL_RE.search(issue_text):
        return "authoring_viewport_stability"
    return None


def _ac(
    ac_id: str,
    sphere: str,
    given: str,
    when: str,
    then: str,
    evidence: str,
) -> str:
    return (
        f"{ac_id} [Proposed]: ({sphere}) Given {given} | When {when} | "
        f"Then {then} | Evidence: {evidence}."
    )


def _authoring_viewport(evidence: str) -> dict[str, object]:
    return {
        "acceptance_criteria": [
            _ac(
                "AC-01",
                "Basic",
                "a long topic is open in Author view with the active caret or selected element deep in the document",
                "the author types or pastes content at that active location",
                "the active element remains visible and the viewport does not jump to the document top or an unrelated section",
                evidence,
            ),
            _ac(
                "AC-02",
                "Integration",
                "the intended insertion location is active and visible inside a long topic",
                "the author inserts or updates a cross-reference or reference link and closes the picker",
                "focus returns to the intended insertion location, that location remains visible, and exactly the intended reference is present",
                evidence,
            ),
            _ac(
                "AC-03",
                "Negative",
                "a reference picker was opened from an active location inside a long topic",
                "the author cancels the picker without selecting a target",
                "focus returns to the intended location without inserting a reference or mutating surrounding content",
                evidence,
            ),
            _ac(
                "AC-04",
                "Basic",
                "an edit or inserted reference causes content above the active element to reflow",
                "the Author canvas lays out the changed content",
                "the viewport is restored relative to the active element rather than to an exact prior pixel offset",
                evidence,
            ),
        ],
        "test_scenarios": [
            "Test data to prepare: one long DITA topic with uniquely labelled sections near the start, middle, and end; inline text and valid cross-reference targets; use the active element and surrounding text as the viewport oracle, not a numeric latency or pixel SLA.",
            "P0 [AC-01, AC-04]: Action: place the caret in the deep labelled section, type, paste, and repeat the edit after layout reflow. Expected: the active element stays visible, the caret and selection remain correct, and the canvas never jumps to the top or an unrelated section.",
            "P0 [AC-02, AC-04]: Action: insert and then update a cross-reference from the deep labelled section and close the picker each time. Expected: focus returns to the intended location, one correct reference exists, and surrounding content is unchanged.",
            "P1 [AC-03]: Action: open the reference picker from the deep labelled section and cancel it repeatedly. Expected: no reference or duplicate content is inserted, focus returns to the intended location, and the location remains visible.",
        ],
        "forbidden_automatic_scope": [
            "left map tree or outline-panel state",
            "save, reopen, or version-restore persistence",
            "old-editor or cross-editor parity",
            "numeric performance SLA derived only from content size",
            "data-loss impact without direct evidence",
        ],
        "performance_decision": "not_required_from_fixture_alone",
    }


def _map_preview(evidence: str) -> dict[str, object]:
    return {
        "acceptance_criteria": [
            _ac(
                "AC-01",
                "Basic",
                "a map preview is scrolled to a selected topic with conditions applied in the right panel",
                "the user switches away and returns to the map preview during the active session",
                "the preview restores the selected topic, relative scroll location, and applied condition state",
                evidence,
            ),
            _ac(
                "AC-02",
                "Integration",
                "a topic opened from map preview was edited",
                "the user returns to preview and refreshes the topic or the complete map",
                "the latest content appears without resetting the selected topic, relative scroll location, or right-panel condition state",
                evidence,
            ),
        ],
        "test_scenarios": [
            "Test data to prepare: standard map, bookmap, and subject scheme with topic, DITAVAL, Markdown, and non-DITA references; include a long topic and an applied condition in the right panel.",
            "P0 [AC-01]: Action: scroll to a deep topic, apply a condition, switch tabs for several minutes, and return. Expected: selected topic, relative map-preview position, and condition state are restored.",
            "P0 [AC-02]: Action: edit the selected topic, return to map preview, and use topic refresh and toolbar map refresh. Expected: latest content is shown while selected-topic, scroll, and condition state remain intact.",
        ],
        "forbidden_automatic_scope": [
            "Author-canvas caret restoration",
            "reference-picker focus restoration",
        ],
        "performance_decision": "conditional_only_when_an_approved_large-map_oracle_exists",
    }


def _cals_delete(evidence: str) -> dict[str, object]:
    return {
        "acceptance_criteria": [
            _ac(
                "AC-01",
                "Basic",
                "a valid CALS table has a source-defined row and column count with distinct content in every cell",
                "the author deletes the source-defined set of selected columns",
                "the row count is unchanged, the visible column count decreases by the number of distinct deleted columns, and no blank ghost column remains",
                evidence,
            ),
            _ac(
                "AC-02",
                "Integration",
                "the source-defined selected columns are deleted from the CALS table",
                "the resulting Author and Source representations are inspected",
                "remaining cell content and order are preserved and no orphan column or span metadata references a deleted column",
                evidence,
            ),
        ],
        "test_scenarios": [
            "Test data to prepare: use the source-defined CALS row/column counts and selected-column positions; give every cell a unique row-column label. Add span cases only when current evidence makes them applicable.",
            "P0 [AC-01, AC-02]: Action: delete the source-defined selected columns. Expected: the row count is unchanged, the visible column count decreases by the distinct deleted-column count, no ghost column appears, and every retained label keeps its relative order.",
            "P1 [AC-02]: Action: when span handling is applicable, repeat next to the source-defined spans and inspect Source view. Expected: retained spans remain valid and no column specification or span endpoint targets a removed column.",
        ],
        "forbidden_automatic_scope": ["simpletable or reltable parity unless current Jira/UAC names it"],
        "performance_decision": "not_required",
    }


def _large_file_configuration(evidence: str) -> dict[str, object]:
    return {
        "acceptance_criteria": [
            _ac(
                "AC-01",
                "Basic",
                "a topic's parsed tag count is below the configured largeFileTagCount threshold",
                "the author edits the topic",
                "normal dirty-state and undo or redo behavior remains available",
                evidence,
            ),
            _ac(
                "AC-02",
                "Integration",
                "a topic reaches or exceeds the configured largeFileTagCount threshold",
                "the topic is opened for editing",
                "the documented large-file safeguard behavior follows the configured tag-count boundary rather than a hard-coded table-cell count",
                evidence,
            ),
        ],
        "test_scenarios": [
            "Test data to prepare: record the effective largeFileTagCount value and create topics immediately below and at or above that parsed-tag threshold; do not infer the threshold from an observed UI or structure count.",
            "P0 [AC-01, AC-02]: Action: edit both boundary topics and compare dirty-state plus undo or redo availability. Expected: behavior changes only at the configured parsed-tag boundary and matches the documented large-file safeguard.",
        ],
        "classification": "working_as_designed_configuration",
        "forbidden_automatic_scope": [
            "classifying an observed UI or structure count as the product threshold",
            "treating cell count as equivalent to parsed DITA tag count",
            "inventing a performance SLA",
        ],
        "performance_decision": "not_required_from_cell_count_alone",
    }


def derive_contract(issue_text: str, evidence: str = "Current Jira/UAC") -> dict[str, object]:
    """Create a deterministic candidate contract without expanding Jira scope."""
    route = classify_contract(issue_text)
    builders = {
        "authoring_viewport_stability": _authoring_viewport,
        "map_preview_state": _map_preview,
        "cals_multi_column_delete": _cals_delete,
        "large_file_configuration": _large_file_configuration,
    }
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "route": route,
        "acceptance_criteria": [],
        "test_scenarios": [],
        "forbidden_automatic_scope": [],
    }
    if route:
        payload.update(builders[route](evidence))
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issue_file", help="UTF-8 Jira/UAC text file")
    parser.add_argument("--evidence", default="Current Jira/UAC")
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    issue_path = Path(args.issue_file)
    if not issue_path.is_file():
        parser.error(f"issue file not found: {issue_path}")
    payload = derive_contract(issue_path.read_text(encoding="utf-8"), args.evidence)
    rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
