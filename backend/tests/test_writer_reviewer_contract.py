"""Writer/Reviewer boundary contract.

Three defects observed on real runs, each guarded here:

1.  The acceptance contract rendered as bare bullets with no AC IDs, so no
    criterion could be referenced in review or mapped to a scenario.
2.  A "proposed acceptance contract" was emitted that was the ticket's own
    capability request ("Ability to view the topic list...").  Asking for a
    capability is not a criterion: it cannot be passed or failed.
3.  Coverage lanes rendered "internal evidence recorded for N closure records
    (see trace)", which announces bookkeeping rather than dispositioning
    anything, while the gates still reported PASS.
"""

from __future__ import annotations

import pytest

from app.services.canonical_test_plan_reasoning_service import (
    _AC_META_PROSE_RE,
    _COVERAGE_FILLER_RE,
    _is_request_not_outcome,
)


class TestRequestGrammarDetection:
    @pytest.mark.parametrize(
        "statement",
        [
            # The real GUIDES-11947 render.
            "Ability to view the topic list in the same order as it appears "
            "in the map.",
            "Need a way to view list of topics in same order as they are in "
            "the map.",
            "Provide a way to export the topic list as CSV.",
            "There should be a way to retain only the newest N outputs.",
            "Support for adding COUNT-based retention to the purge policy.",
            "The customer would like to see warnings without opening the log.",
        ],
    )
    def test_capability_requests_are_rejected(self, statement):
        assert _is_request_not_outcome(statement)

    @pytest.mark.parametrize(
        "statement",
        [
            # Outcome grammar stays valid even when the ticket author phrased
            # the original request this way - it is testable as written.
            "The export job writes a completion marker.",
            "The Topic List report lists topics in the order they appear in "
            "the map.",
            "Output History shows a warning status for an output that "
            "completed with publish warnings.",
            "The exported CSV uses the same topic order as the report.",
            "Purging with LOGS_ONLY removes the logs and keeps the generated "
            "output.",
        ],
    )
    def test_observable_outcomes_are_accepted(self, statement):
        assert not _is_request_not_outcome(statement)

    def test_empty_statement_is_not_a_request(self):
        assert not _is_request_not_outcome("   ")


class TestCoverageFillerDetection:
    @pytest.mark.parametrize(
        "line",
        [
            "Absent value: internal evidence recorded for 12 closure records (see trace)",
            "Hierarchy: internal evidence recorded for 3 closure records",
        ],
    )
    def test_bookkeeping_lines_are_rejected(self, line):
        assert _COVERAGE_FILLER_RE.search(line)

    @pytest.mark.parametrize(
        "line",
        [
            "Topic order is preserved when the map nests submaps two levels deep.",
            "CSV export writes one row per topic reference, including duplicates.",
            # "(see trace)" is a legitimate citation suffix on a real
            # disposition and must not be treated as filler on its own.
            "Submap topics keep map order in the export (see trace)",
        ],
    )
    def test_real_dispositions_are_accepted(self, line):
        assert not _COVERAGE_FILLER_RE.search(line)


class TestEvidenceCommentaryDetection:
    @pytest.mark.parametrize(
        "line",
        [
            "Customer-stated desired behavior for the output list.",
            "This is the verbatim ask from the Jira description.",
            "The attachment shows an amber traffic light.",
            "Documentation establishes the AGE-based purge window.",
        ],
    )
    def test_commentary_is_rejected(self, line):
        assert _AC_META_PROSE_RE.search(line)

    def test_outcome_without_commentary_is_accepted(self):
        assert not _AC_META_PROSE_RE.search(
            "Output History shows a warning status for an output that "
            "completed with publish warnings."
        )


class TestRenderedPlanContract:
    """End-to-end: what the tester actually receives."""

    @pytest.fixture(scope="class")
    def result(self):
        from tests import test_canonical_test_plan_runtime_contracts as contracts

        return contracts._canonical_result()

    def test_acceptance_contract_is_a_flat_numbered_ac_list(self, result):
        rendered = result.rendered_output
        contract = rendered.split("## Proposed acceptance contract", 1)[1]
        contract = contract.split("\n## ", 1)[0]
        criteria = [
            line for line in contract.splitlines() if line.startswith("- ")
        ]

        assert criteria, "acceptance contract rendered no criteria"
        for index, line in enumerate(criteria, start=1):
            assert line.startswith(f"- AC-{index:02d}: ")

    def test_bookkeeping_never_reaches_the_reader(self, result):
        assert "internal evidence recorded" not in result.rendered_output

    def test_bookkeeping_is_still_retained_for_trace(self, result):
        # Suppression is a presentation decision only: the closure records
        # must remain in the structured plan so traceability is not lost.
        plan = result.output_payload.get("structured_plan") or {}
        items = [
            item
            for section in plan.get("sections", [])
            for item in section.get("items", [])
        ]

        assert any("internal evidence recorded" in item for item in items)

    def test_no_section_heading_is_rendered_without_content(self, result):
        lines = result.rendered_output.splitlines()
        for position, line in enumerate(lines):
            if not line.startswith("## "):
                continue
            body = lines[position + 1 :]
            following = [
                entry
                for entry in body[: next(
                    (
                        offset
                        for offset, entry in enumerate(body)
                        if entry.startswith("## ")
                    ),
                    len(body),
                )]
                if entry.strip()
            ]
            assert following, f"empty section rendered: {line}"
