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

from types import SimpleNamespace

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    AcceptanceCandidate,
    AcceptancePromotionDecision,
    AcceptanceSubPoint,
    AcceptanceSubPointKind,
    AuthorityClass,
    ContractFact,
    ContractFactSet,
    ContractMode,
    ContractFactType,
    ClarificationAnswerClass,
    ClarificationStatus,
    ConvergenceRecord,
    ConvergenceStatus,
    CoverageDisposition,
    CoverageDispositionRecord,
    HumanClarification,
    PromotionStatus,
    ResearchFinding,
    ResearchFindingEvidenceRole,
    ResearchWorkerResult,
    ResearchWorkerRole,
    ResearchWorkerStatus,
    ScopeResolution,
    WrittenAcceptanceCriterion,
    WriterProjectionStatus,
)
from app.services.agent_execution_provider import _conflict_text
from app.services.canonical_evidence_service import normalize_legacy_packet
from app.services.canonical_test_plan_reasoning_service import (
    _AC_META_PROSE_RE,
    _AC_NEAR_DUPLICATE_JACCARD,
    _acceptance_contract_delivery_failures,
    _acceptance_presentation_failures,
    _acceptance_source_line,
    _COVERAGE_FILLER_RE,
    _DISPOSITION_SECTIONS,
    _absorb_near_duplicate,
    _as_manual_qe_check,
    _as_outcome_sentence,
    _clarification_source_lines,
    _convergence_detail_lines,
    _documented_baseline_contract_statement,
    _derive_outcome_statement,
    _derive_tbd_question,
    _fact_types,
    _is_request_not_outcome,
    _is_requested_capability,
    _render_written_criterion,
    _split_independent_requirements,
    _writer_projection_completeness,
    CANONICAL_REASONING_SERVICE,
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
            line
            for line in contract.splitlines()
            if line.startswith("- AC-")
        ]

        assert criteria, "acceptance contract rendered no criteria"
        assert len(criteria) <= 10, "presented acceptance contract exceeds ten points"
        for index, line in enumerate(criteria, start=1):
            assert line.startswith(f"- AC-{index:02d}: Verify that ")

    def test_every_criterion_carries_a_source_line(self, result):
        contract = result.rendered_output.split(
            "## Proposed acceptance contract", 1
        )[1].split("\n## ", 1)[0]
        lines = contract.splitlines()
        criteria = [
            position
            for position, line in enumerate(lines)
            if line.startswith("- AC-")
        ]

        assert criteria
        for position in criteria:
            assert lines[position + 1].startswith("  **Source:** ")

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


class TestRequestToOutcomeDerivation:
    """Stage 18 must derive an observable outcome, not copy the ask.

    The boundary trace proved AcceptanceContractResolver emitted
    ``statement=row.candidate`` byte-identical to the Jira text, and degraded
    ``observable`` to a non-emptiness check -- which made the promotion gate's
    observability rejection structurally unreachable.
    """

    def test_request_grammar_is_reframed_as_an_outcome(self):
        from app.services.canonical_test_plan_reasoning_service import (
            _derive_outcome_statement,
        )

        derived = _derive_outcome_statement(
            "Ability to view the topic list in the same order as it appears in the map"
        )

        assert derived is not None
        assert derived.startswith("A user can view the topic list")
        assert "Ability to" not in derived

    def test_every_content_word_survives_the_reframe(self):
        from app.services.canonical_test_plan_reasoning_service import (
            _derive_outcome_statement,
        )

        source = "Need a way to view list of topics in same order as they are in map"
        derived = _derive_outcome_statement(source)

        assert derived is not None
        for word in ("topics", "same", "order", "map"):
            assert word in derived

    def test_it_fires_after_a_separator_in_a_jira_summary(self):
        from app.services.canonical_test_plan_reasoning_service import (
            _derive_outcome_statement,
        )

        derived = _derive_outcome_statement(
            "New Reports UI - Topic List | Need a way to view list of topics in map"
        )

        assert derived is not None
        assert "Need a way to" not in derived

    def test_it_fails_closed_when_it_cannot_reframe(self):
        from app.services.canonical_test_plan_reasoning_service import (
            _derive_outcome_statement,
        )

        assert _derive_outcome_statement("The CSV export is broken") is None

    def test_a_derived_outcome_is_no_longer_request_grammar(self):
        from app.services.canonical_test_plan_reasoning_service import (
            _derive_outcome_statement,
            _is_request_not_outcome,
        )

        derived = _derive_outcome_statement("Ability to export the topic list")

        assert derived is not None
        assert not _is_request_not_outcome(derived)


class TestSourceLineDerivation:
    """A Source line may only name sources that AC's own facts carry.

    This is the structural guarantee behind the locked rule that a source line
    must never say "Experience League" for behavior Experience League does not
    establish.
    """

    def test_it_never_credits_a_source_the_ac_does_not_cite(self):
        from app.services.canonical_test_plan_reasoning_service import (
            _acceptance_source_line,
        )

        class _Fact:
            def __init__(self, reference):
                self.source_reference = reference

        line = _acceptance_source_line(["f1"], {"f1": _Fact("jira:GUIDES-1:description")})

        assert "Jira" in line
        assert "Experience League" not in line

    def test_a_documentation_fact_is_labelled_as_documentation(self):
        from app.services.canonical_test_plan_reasoning_service import (
            _acceptance_source_line,
        )

        class _Fact:
            def __init__(self, reference):
                self.source_reference = reference

        line = _acceptance_source_line(
            ["f1"],
            {"f1": _Fact("https://experienceleague.adobe.com/docs/guides")},
        )

        assert "Experience League" in line

    def test_no_supporting_fact_is_reported_as_qe_derived(self):
        from app.services.canonical_test_plan_reasoning_service import (
            _acceptance_source_line,
        )

        assert "QE-derived" in _acceptance_source_line([], {})

    def test_admitted_human_decision_is_named_as_its_own_source(self):
        clarification = HumanClarification(
            question_ref="question:source-line",
            answer="The image view includes direct and nested uses.",
            answer_classification=ClarificationAnswerClass.PRODUCT_DECISION,
            provided_by="requester",
            authority_role=AuthorityClass.CONFIRMED_PRODUCT_DECISION,
            source_context="Interactive product-decision response for GUIDES-38274",
            status=ClarificationStatus.ADMITTED,
        )
        reference = f"clarification:{clarification.clarification_id}"

        line = _acceptance_source_line(
            [],
            {},
            [reference],
            _clarification_source_lines([clarification]),
        )

        assert line == "GUIDES-38274 — requester-confirmed product decision."


class TestWriterSourcePreservation:
    def test_direct_and_nested_reference_decision_stays_one_contract(self):
        statement = (
            "Add a user-facing view for each image or media asset that shows "
            "every direct and nested topic use and the baseline content version "
            "that will use it."
        )

        assert _split_independent_requirements(statement) == [statement]

    def test_documented_example_is_not_promoted_as_an_exact_contract_value(self):
        statement = (
            "For Referred Content, the documented Pick Automatically rule "
            "selects the version corresponding to the content in which it is "
            "referenced. Adobe's example states that topic A version 1.5 "
            "selects image B version 1.2."
        )

        concise = _documented_baseline_contract_statement(statement)

        assert "Pick Automatically" in concise
        assert "1.5" not in concise
        assert "1.2" not in concise
        assert "documented" not in concise

    def test_manual_qe_check_reframes_a_user_facing_view_request(self):
        assert _as_manual_qe_check(
            "Add a user-facing view for each image or media asset that shows "
            "every direct and nested topic use."
        ) == (
            "Verify that each image or media asset has a user-facing view that "
            "shows every direct and nested topic use."
        )

    def test_manual_qe_check_reframes_a_preservation_directive(self):
        assert _as_manual_qe_check(
            "Preserve existing baseline resolution options. This change does "
            "not introduce a new label-resolution rule."
        ) == (
            "Verify that the existing baseline resolution options stay "
            "unchanged; this change does not introduce a new label-resolution rule."
        )

    def test_manual_qe_check_places_a_fronted_context_after_the_outcome(self):
        assert _as_manual_qe_check(
            'For Referred Content, the "Pick Automatically" rule selects '
            "the matching version."
        ) == (
            'Verify that for Referred Content, the "Pick Automatically" rule '
            "selects the matching version."
        )


class TestRetrievalResidueNeverReachesTheReader:
    """Retrieved documentation must not define this ticket's scope."""

    def test_corpus_retrieval_boilerplate_is_recognised(self):
        from app.services.canonical_test_plan_reasoning_service import (
            _RETRIEVAL_BOILERPLATE_RE,
        )

        for residue in (
            "Learning retrieval profile for AEM Guides folder postprocessing.",
            "Use this for QA/test-plan retrieval when the ticket mentions metadata.",
            "High-signal topics and headings: configuration overrides, Cloud Service.",
            "Retrieval terms: publishing, preset",
        ):
            assert _RETRIEVAL_BOILERPLATE_RE.search(residue), residue

    def test_a_real_product_sentence_is_not_treated_as_residue(self):
        from app.services.canonical_test_plan_reasoning_service import (
            _RETRIEVAL_BOILERPLATE_RE,
        )

        assert not _RETRIEVAL_BOILERPLATE_RE.search(
            "The topic list is sorted by title in the new Reports UI."
        )


class TestScopeIsATicketDecision:
    """Documentation may establish behavior; it may not declare ticket scope.

    A real run rendered "In scope: Applies to folders under Experience Manager
    DAM and affects DAM Update Asset workflow postprocessing/UUID generation"
    for a topic-ordering ticket, sourced entirely from a retrieved Experience
    League page.
    """

    def test_documentation_authorities_are_excluded_from_scope(self):
        from app.services.canonical_test_plan_reasoning_service import (
            AuthorityClass,
            _TICKET_UNDERSTANDING_AUTHORITIES,
        )

        assert AuthorityClass.CUSTOMER_REQUEST in _TICKET_UNDERSTANDING_AUTHORITIES
        assert (
            AuthorityClass.OFFICIAL_PRODUCT_CONTRACT
            not in _TICKET_UNDERSTANDING_AUTHORITIES
        )


class TestRequestedCapabilityAuthorityBoundary:
    """A Jira request is not an accepted product contract merely by its wording."""

    @pytest.mark.parametrize(
        "literal",
        [
            "Could we add also a where used for each topic?",
            "Can we also show the parent map column?",
            "Would it be possible to export the CSV in map order?",
            "Is it possible to support COUNT-based retention?",
            "Any chance of adding a warning indicator to the outputs view?",
        ],
    )
    def test_requested_capabilities_are_recognised(self, literal):
        assert _is_requested_capability(literal)

    @pytest.mark.parametrize(
        "literal",
        [
            "What should happen when the map is empty?",
            "Which retention mode becomes the default?",
            "Should COUNT retention apply per map or per preset?",
            "Who owns the purge schedule?",
        ],
    )
    def test_genuine_decisions_are_not_capabilities(self, literal):
        assert not _is_requested_capability(literal)

    def test_description_capability_request_stays_a_product_decision(self):
        types = _fact_types("description", "Could we add also a where used for each topic?")
        assert ContractFactType.HUMAN_OPEN_QUESTIONS in types
        assert ContractFactType.DIRECT_EXPECTED_BEHAVIOR not in types

    def test_accepted_uac_capability_wording_remains_a_contract(self):
        types = _fact_types(
            "issue.acceptance_criteria.0",
            "Could we add also a where used for each topic?",
        )
        assert ContractFactType.HUMAN_OPEN_QUESTIONS not in types
        assert ContractFactType.DIRECT_EXPECTED_BEHAVIOR in types

    def test_description_capability_request_cannot_be_promoted_as_an_ac(self):
        bundle = normalize_legacy_packet(
            {
                "jira_key": "GUIDES-11947",
                "issue": {
                    "description": (
                        "Could we add also a where used for each topic?"
                    )
                },
            },
            tenant_id="writer-contract-test",
        )
        facts = CANONICAL_REASONING_SERVICE.extract_contract_facts(bundle)
        scope = ScopeResolution(in_scope=["Topic List"])
        coverage = CANONICAL_REASONING_SERVICE.classify_coverage(
            facts, [], [], [], scope, []
        )
        candidates = CANONICAL_REASONING_SERVICE.resolve_acceptance_contract(
            facts, coverage, []
        )
        _, decisions = CANONICAL_REASONING_SERVICE.acceptance_promotion_gate(
            candidates, facts, scope, coverage
        )

        assert not candidates
        assert not decisions

    def test_genuine_open_question_still_routes_to_the_open_question_lane(self):
        types = _fact_types("description", "Which retention mode becomes the default?")
        assert ContractFactType.HUMAN_OPEN_QUESTIONS in types

    def test_explicit_open_question_path_is_never_reclassified(self):
        # An explicitly keyed open question keeps its lane even when its text
        # reads like a capability request.
        types = _fact_types("open_question", "Could we add a where used column?")
        assert ContractFactType.HUMAN_OPEN_QUESTIONS in types


class TestCompoundRequirementSplitting:
    """D2: two independent requirements are two pass/fail contracts."""

    def test_compound_jira_sentence_splits_into_two_requirements(self):
        clauses = _split_independent_requirements(
            "Ability to view the topic list in the same order as it appears in "
            "the map and the corresponding downloaded CSV should have topics "
            "listed in same order"
        )
        assert len(clauses) == 2
        assert "topic list" in clauses[0]
        assert "CSV" in clauses[1]

    @pytest.mark.parametrize(
        "statement",
        [
            "Topics and maps are listed together.",
            "The report shows the title and the file name.",
            "Purging removes the logs and the generated output.",
        ],
    )
    def test_descriptive_conjunctions_are_never_split(self, statement):
        assert _split_independent_requirements(statement) == [statement]

    def test_each_split_clause_becomes_an_observable_outcome(self):
        clauses = _split_independent_requirements(
            "Ability to view the topic list in the same order as it appears in "
            "the map and the corresponding downloaded CSV should have topics "
            "listed in same order"
        )
        outcomes = [
            _derive_outcome_statement(clause) or _as_outcome_sentence(clause)
            for clause in clauses
        ]
        for outcome in outcomes:
            assert not _is_request_not_outcome(outcome), outcome
            assert outcome.endswith(".")
        # The split preserves content; it never invents a new subject.
        assert "topic list" in outcomes[0]
        assert "CSV" in outcomes[1]


class TestUnresolvedBehaviorStaysInTheContract:
    """D1-c: material-but-unresolved behavior renders as a bounded (TBD).

    It must remain inside the acceptance contract - never relocated to a
    sibling "open product decisions" or "evidence gaps" section - and it must
    read as the open decision rather than as an asserted outcome.
    """

    def test_tbd_question_always_ends_with_a_question_mark(self):
        question = _derive_tbd_question("Could we add also a where used for each topic?")
        assert question is not None
        assert question.endswith("?")

    def test_tbd_question_does_not_assert_either_answer(self):
        question = _derive_tbd_question("Could we add also a where used for each topic?")
        assert "where used for each topic" in question
        # It asks; it never states the behavior as settled.
        assert not _is_request_not_outcome(question)
        assert "confirm" in question.casefold()

    def test_empty_statement_produces_no_question(self):
        assert _derive_tbd_question("") is None
        assert _derive_tbd_question("   ") is None

    def test_acceptance_tbd_is_not_diverted_to_product_decisions(self):
        # The routing table must keep a bounded TBD acceptance-lane; routing it
        # to product_decisions is exactly the diversion D1 removes.
        assert (
            _DISPOSITION_SECTIONS[CoverageDisposition.ACCEPTANCE_TBD]
            == "acceptance_contract"
        )
        assert (
            _DISPOSITION_SECTIONS[CoverageDisposition.PRODUCT_SCOPE_QUESTION]
            == "product_decisions"
        )


class TestWrittenCriterionRendering:
    """The Writer's output carries sub-points and TBD markers into the render."""

    def test_tbd_sub_point_renders_under_its_criterion_with_a_marker(self):
        criterion = WrittenAcceptanceCriterion(
            outcome="The Topic List shows topics in map order.",
            sub_points=[
                AcceptanceSubPoint(
                    text="Confirm the expected behavior for where used for each topic?",
                    kind=AcceptanceSubPointKind.TBD_QUESTION,
                )
            ],
            source_line="Jira ask.",
        )
        rendered = _render_written_criterion(criterion)
        outcome, _, sub_block = rendered.partition("\n")
        assert outcome == "Verify that the Topic List shows topics in map order."
        assert sub_block.startswith("- ")
        assert sub_block.rstrip().endswith("(TBD)")
        assert "?" in sub_block

    def test_confirmed_variant_sub_point_carries_no_tbd_marker(self):
        criterion = WrittenAcceptanceCriterion(
            outcome="The Topic List shows topics in map order.",
            sub_points=[
                AcceptanceSubPoint(
                    text="Nested maprefs keep their resolved position.",
                    kind=AcceptanceSubPointKind.CONFIRMED_VARIANT,
                )
            ],
            source_line="Jira ask.",
        )
        rendered = _render_written_criterion(criterion)
        assert "(TBD)" not in rendered

    def test_a_tbd_question_sub_point_must_end_with_a_question_mark(self):
        with pytest.raises(ValueError):
            AcceptanceSubPoint(
                text="Map order becomes the default.",
                kind=AcceptanceSubPointKind.TBD_QUESTION,
            )

    def test_unresolved_criterion_is_marked_tbd(self):
        criterion = WrittenAcceptanceCriterion(
            outcome="Confirm the expected behavior for where used for each topic?",
            unresolved=True,
            source_line="Jira ask.",
        )
        assert _render_written_criterion(criterion).endswith("(TBD)")

    def test_existing_qe_verb_is_not_prefixed_twice(self):
        criterion = WrittenAcceptanceCriterion(
            outcome="Verify that the Topic List shows topics in map order.",
            source_line="Jira ask.",
        )
        assert _render_written_criterion(criterion) == (
            "Verify that the Topic List shows topics in map order."
        )


class TestReviewerRemainsFailClosed:
    """D2 must not weaken the Reviewer - good Writer output is the fix."""

    def test_meta_prose_is_still_rejected(self):
        assert _AC_META_PROSE_RE.search("The attachment shows a missing image.")
        assert _COVERAGE_FILLER_RE.search(
            "Internal evidence recorded for 12 closure records (see trace)."
        )

    def test_writer_output_does_not_bypass_request_grammar_detection(self):
        # A criterion the Writer failed to reframe is still caught downstream.
        assert _is_request_not_outcome(
            "Ability to view the topic list in the same order as it appears in the map."
        )

    def test_generic_qe_wording_and_generic_source_block_delivery(self):
        failures = _acceptance_presentation_failures(
            ["Verify that the system works correctly."],
            {"Verify that the system works correctly.": "Jira."},
        )

        assert any("generic QE subject" in failure for failure in failures)
        assert any("criterion-specific source" in failure for failure in failures)

    def test_more_than_ten_criteria_block_instead_of_hiding_coverage(self):
        statements = [
            f"Verify that Output History keeps retention case {index} visible."
            for index in range(11)
        ]
        failures = _acceptance_contract_delivery_failures(
            statements,
            {statement: "Jira GUIDES-55040." for statement in statements},
            [],
        )

        assert any("would hide 1 criterion" in failure for failure in failures)


class TestNearDuplicateCriteriaAreMerged:
    """A Jira summary and its description restate one requirement.

    GUIDES-11947 carries the same ask twice - "Ability to view the topic list
    in the same order as it appears in the map" (description) and "Need a way
    to view list of topics in same order as they are in map" (summary).  Both
    are admitted candidates, so the contract rendered the same requirement as
    two acceptance criteria.  The Writer owns how the contract reads, so it
    folds them into one criterion while keeping every source binding.
    """

    def _absorb(self, written, outcome, **kwargs):
        return _absorb_near_duplicate(
            written,
            outcome,
            unresolved=kwargs.get("unresolved", False),
            candidate_ids=kwargs.get("candidate_ids", ["cand-2"]),
            fact_ids=kwargs.get("fact_ids", ["fact-2"]),
            disposition_ids=kwargs.get("disposition_ids", []),
            evidence_ids=kwargs.get("evidence_ids", ["ev-2"]),
        )

    def _criterion(self, outcome, **kwargs):
        return WrittenAcceptanceCriterion(
            outcome=outcome,
            source_candidate_ids=kwargs.get("candidate_ids", ["cand-1"]),
            source_fact_ids=kwargs.get("fact_ids", ["fact-1"]),
            evidence_ids=kwargs.get("evidence_ids", ["ev-1"]),
            unresolved=kwargs.get("unresolved", False),
            source_line="Jira.",
        )

    def test_the_two_guides_11947_restatements_collapse_to_one(self):
        written = [
            self._criterion(
                "A user can view the topic list in the same order as it appears in the map."
            )
        ]
        assert self._absorb(
            written, "A user can view list of topics in same order as they are in map."
        )
        assert len(written) == 1

    def test_merging_keeps_the_wording_that_carries_more_source_detail(self):
        written = [self._criterion("Topics are listed in map order.")]
        assert self._absorb(written, "Topics are listed in resolved map order.")
        assert written[0].outcome == "Topics are listed in resolved map order."

    def test_a_tie_keeps_the_criterion_already_in_the_contract(self):
        # Neither wording is demonstrably richer, so the merge must be stable
        # rather than pick arbitrarily.  Promotion order decides.
        incumbent = (
            "A user can view the topic list in the same order as it appears in the map."
        )
        written = [self._criterion(incumbent)]
        self._absorb(
            written, "A user can view list of topics in same order as they are in map."
        )
        assert written[0].outcome == incumbent

    def test_no_source_binding_is_lost_when_two_criteria_merge(self):
        written = [
            self._criterion(
                "A user can view the topic list in the same order as it appears in the map."
            )
        ]
        self._absorb(
            written, "A user can view list of topics in same order as they are in map."
        )
        merged = written[0]
        assert set(merged.source_candidate_ids) == {"cand-1", "cand-2"}
        assert set(merged.source_fact_ids) == {"fact-1", "fact-2"}
        assert set(merged.evidence_ids) == {"ev-1", "ev-2"}

    def test_distinct_outcomes_are_never_merged(self):
        written = [
            self._criterion(
                "A user can view the topic list in the same order as it appears in the map."
            )
        ]
        assert not self._absorb(
            written,
            "The corresponding downloaded CSV should have topics listed in same order.",
        )
        assert len(written) == 1

    def test_an_open_question_is_never_absorbed_into_a_settled_outcome(self):
        # Folding a TBD into a confirmed criterion would silently resolve a
        # decision the evidence left open.
        written = [
            self._criterion(
                "A user can view the topic list in the same order as it appears in the map."
            )
        ]
        assert not self._absorb(
            written,
            "Confirm the expected behavior for view the topic list in the order it appears in the map?",
            unresolved=True,
        )
        assert len(written) == 1

    def test_merge_threshold_matches_the_repository_redundancy_rule(self):
        # The Writer must not drift from the evaluator that scores redundancy.
        import importlib.util
        from pathlib import Path

        precision_path = (
            Path(__file__).resolve().parents[2] / "scripts" / "uac_eval" / "precision.py"
        )
        assert precision_path.is_file(), precision_path
        spec = importlib.util.spec_from_file_location("_precision", precision_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert _AC_NEAR_DUPLICATE_JACCARD == module.REDUNDANCY_JACCARD

    def test_criterion_identity_is_recomputed_after_a_merge(self):
        written = [self._criterion("Topics are listed in map order.")]
        before = written[0].criterion_id
        assert self._absorb(written, "Topics are listed in resolved map order.")
        assert written[0].criterion_id != before


class TestWriterProjectionCompleteness:
    """Regression coverage must remain visible or fail before delivery."""

    def _coverage_fixture(self):
        fact = ContractFact(
            fact_type=ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
            literal=(
                "Output History retains configured entries, generated outputs, "
                "and existing default behavior."
            ),
            source_reference="jira:GUIDES-55040:description",
        )
        facts = ContractFactSet(
            contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
            facts=[fact],
        )
        p0 = CoverageDispositionRecord(
            candidate=(
                "Output History retains configured entries, generated outputs, "
                "and existing default behavior."
            ),
            disposition=CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
            source_fact_ids=[fact.fact_id],
            rationale="Ticket outcome.",
            priority="P0",
            coverage_class="ACCEPTANCE",
            contract_type="POSITIVE",
            applicability="APPLICABLE",
        )
        candidate = AcceptanceCandidate(
            statement=p0.candidate,
            contract_mode=facts.contract_mode,
            source_fact_ids=[fact.fact_id],
            source_disposition_ids=[p0.disposition_id],
            in_scope=True,
            observable=True,
        )
        promotion = AcceptancePromotionDecision(
            candidate_id=candidate.candidate_id,
            status=PromotionStatus.PROMOTED,
            resulting_disposition=CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
            authority_supported=True,
            scope_established=True,
            observable=True,
            exact_values_supported=True,
        )
        p1 = CoverageDispositionRecord(
            candidate="Output History retention variants preserve the selected behavior.",
            disposition=CoverageDisposition.CONFIGURATION_VARIANT,
            source_fact_ids=[fact.fact_id],
            rationale="Each supported COUNT value is a material regression variant.",
            priority="P1",
            coverage_class="QE_REGRESSION",
            contract_type="PRESERVATION",
            applicability="APPLICABLE",
            variants=[
                "Output History retains the newest one entry for COUNT retention.",
                "Output History retains the newest two entries for COUNT retention.",
                "Output History retains generated outputs when LOGS_ONLY purges logs.",
                "Output History keeps AGE retention behavior when AGE is selected.",
                "Output History keeps the existing default when no retention mode is selected.",
            ],
        )
        return facts, candidate, promotion, p0, p1

    def test_opposed_fallback_states_are_not_merged(self):
        written = [
            WrittenAcceptanceCriterion(
                outcome="Output History keeps the fallback enabled.",
                source_line="Jira GUIDES-55040.",
            )
        ]

        assert not _absorb_near_duplicate(
            written,
            "Output History keeps the fallback disabled.",
            unresolved=False,
            candidate_ids=["cand-disabled"],
            fact_ids=["fact-disabled"],
            disposition_ids=["disp-disabled"],
            evidence_ids=["ev-disabled"],
        )
        assert len(written) == 1

    def test_output_history_count_and_logs_only_variants_remain_attached(self):
        facts, candidate, promotion, p0, p1 = self._coverage_fixture()

        written = CANONICAL_REASONING_SERVICE.write_acceptance_criteria(
            [candidate],
            [promotion],
            facts,
            [p0, p1],
        )
        records, failures = _writer_projection_completeness(
            [p0, p1],
            written,
            {},
        )

        assert not failures
        criterion = written[0]
        assert len(criterion.sub_points) == 5
        assert {
            sub_point.text for sub_point in criterion.sub_points
        } == set(p1.variants)
        p1_record = next(
            row for row in records if row.coverage_disposition_id == p1.disposition_id
        )
        assert p1_record.status == WriterProjectionStatus.ATTACHED_VARIANT

    def test_dynamic_value_regression_is_not_merged_into_ordering(self):
        from app.core.schemas_canonical_test_plan_runtime import (
            CanonicalBehaviorModel,
            GenerationProfile,
            RuntimeEntryPoint,
            ScopeResolution,
        )
        from app.services.canonical_test_plan_runtime import (
            CANONICAL_TEST_PLAN_RUNTIME,
        )

        facts, candidate, promotion, p0, _ = self._coverage_fixture()
        dynamic = CoverageDispositionRecord(
            candidate=(
                "The Topic List reads the current topic title after dc:title "
                "changes instead of retaining an older value."
            ),
            disposition=CoverageDisposition.SEMANTIC_REGRESSION,
            source_fact_ids=[facts.facts[0].fact_id],
            evidence_ids=["repo:guides-ui@abc123:topic-list.ts:44-58"],
            rationale=(
                "Ticket-bound implementation research established current "
                "dynamic-value behavior that must remain visible."
            ),
            priority="P1",
            coverage_class="QE_REGRESSION",
            contract_type="PRESERVATION",
            applicability="APPLICABLE",
            state_or_transition="DYNAMIC_VALUE",
            variants=[
                (
                    "The Topic List reads the current topic title after dc:title "
                    "changes instead of retaining an older value."
                )
            ],
        )

        written = CANONICAL_REASONING_SERVICE.write_acceptance_criteria(
            [candidate],
            [promotion],
            facts,
            [p0, dynamic],
        )
        records, failures = _writer_projection_completeness(
            [p0, dynamic],
            written,
            {},
        )

        assert not failures
        dynamic_criterion = next(
            row
            for row in written
            if dynamic.disposition_id in row.source_disposition_ids
        )
        assert dynamic_criterion.outcome == dynamic.variants[0]
        assert not dynamic_criterion.sub_points
        assert all(
            dynamic.variants[0] not in sub_point.text
            for row in written
            if row is not dynamic_criterion
            for sub_point in row.sub_points
        )
        dynamic_record = next(
            row
            for row in records
            if row.coverage_disposition_id == dynamic.disposition_id
        )
        assert dynamic_record.status == WriterProjectionStatus.STANDALONE_AC

        request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
            jira_key="GUIDES-55040",
            tenant_id="tenant-writer",
            entry_point=RuntimeEntryPoint.PYTHON_API,
            generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
        )
        _plan, rendered = CANONICAL_REASONING_SERVICE.render_final_plan(
            request,
            facts,
            ScopeResolution(),
            CanonicalBehaviorModel(),
            [],
            [],
            [],
            [p0, dynamic],
            [candidate],
            [promotion],
            [],
            written_acceptance_criteria=written,
        )
        assert dynamic_criterion.outcome in rendered

    def test_unhosted_typed_p1_variant_fails_closed(self):
        _, _, _, _, p1 = self._coverage_fixture()

        records, failures = _writer_projection_completeness([p1], [], {})

        assert failures
        assert records[0].status == WriterProjectionStatus.EXPLICITLY_EXCLUDED


class TestResearchConflictReachesTheReader:
    """Finding C: research ran, but nothing it established reached the plan.

    Two independent defects hid it.  The worker envelope read only
    ``description``/``text`` from a conflict, so every role-contract conflict
    (``topic``/``claims``/``resolution``) collapsed to an empty string; and
    the normal render dropped the convergence evidence that the blocked
    render already showed.
    """

    GUIDES_11947_DOWNLOAD_FORMAT = {
        "topic": "Format of the Topic List report download",
        "claims": [
            {
                "claim": (
                    "The ticket describes 'the corresponding downloaded CSV' "
                    "for the Topic List report."
                ),
                "authority": "Ticket/reporter language",
            },
            {
                "claim": (
                    "Product documentation describes the Topic List "
                    "'Download' as producing an excel sheet."
                ),
                "authority": "Adobe official product documentation",
            },
        ],
        "resolution": "Unresolved by this research.",
    }

    GUIDES_11947_DEFAULT_ORDERING = {
        "topic": "Default ordering of the Topic List report",
        "claims": [
            {
                "claim": (
                    "The ticket asserts that the Topic List report should "
                    "show topics in the order they appear in the map."
                ),
                "authority": "Ticket/reporter language",
            },
            {
                "claim": (
                    "Product documentation describes the Topic List report "
                    "as listing topics sorted by title."
                ),
                "authority": "Adobe official product documentation",
            },
        ],
        "resolution": "Unresolved by this research.",
    }

    def test_structured_conflict_is_not_collapsed_to_empty_text(self):
        text = _conflict_text(self.GUIDES_11947_DOWNLOAD_FORMAT)

        assert text
        assert "Format of the Topic List report download" in text
        assert "excel sheet" in text
        assert "downloaded CSV" in text
        assert "Adobe official product documentation" in text

    def test_conflict_keeps_the_description_and_plain_string_paths(self):
        assert _conflict_text({"description": "doc says X"}) == "doc says X"
        assert _conflict_text({"text": "doc says Y"}) == "doc says Y"
        assert _conflict_text("already plain") == "already plain"

    def test_unusable_conflict_yields_no_text_instead_of_a_stringified_dict(self):
        assert _conflict_text({}) == ""
        assert _conflict_text({"claims": [{"authority": "Ticket"}]}) == ""

    def _record(self, **kwargs):
        defaults = dict(
            question_id="question:" + "a" * 32,
            status=ConvergenceStatus.CONFLICTED,
            decision="Confirm the Topic List download format.",
        )
        defaults.update(kwargs)
        return ConvergenceRecord(**defaults)

    def test_detail_carries_evidence_unknown_and_conflict(self):
        record = self._record(
            pm_view=["Documentation describes an excel sheet."],
            acceptance_changing_unknowns=["Default sort order is not documented."],
            conflicts=["CSV versus excel sheet."],
        )

        detail = _convergence_detail_lines(record)

        assert detail == [
            "- What the evidence shows: Documentation describes an excel sheet.",
            "- Still unknown: Default sort order is not documented.",
            "- Conflict to resolve: CSV versus excel sheet.",
        ]

    def test_developer_and_qe_evidence_are_used_when_product_view_is_empty(self):
        assert _convergence_detail_lines(self._record(dev_view=["code reads title"]))[
            0
        ] == "- What the evidence shows: code reads title"
        assert _convergence_detail_lines(self._record(qe_view=["observed title order"]))[
            0
        ] == "- What the evidence shows: observed title order"

    def test_a_decision_without_evidence_adds_no_detail(self):
        assert _convergence_detail_lines(self._record()) == []
        assert _convergence_detail_lines(None) == []
    def test_real_worker_payload_surfaces_its_product_conflict_to_the_reader(self):
        """End-to-end: the raw worker envelope a researcher actually returned for
        GUIDES-11947 must reach the reader as a product decision carrying its
        contract conflict - not a silently dropped implementation note."""
        from app.services.convergence_service import (
            CONFLICT_PRODUCT_CONTRACT,
            ConvergenceService,
        )

        question_id = "question:" + "b" * 32
        worker_result = ResearchWorkerResult(
            worker_role=ResearchWorkerRole.DOC_RESEARCHER,
            question_id=question_id,
            status=ResearchWorkerStatus.PARTIAL,
            findings=[
                ResearchFinding(
                    claim=(
                        "The Topic List report lists topics sorted by title in the "
                        "Reports panel."
                    ),
                    evidence_role=ResearchFindingEvidenceRole.EXISTING_BEHAVIOR,
                    source_refs=["ev:DOC:topic-list"],
                )
            ],
            conflicts=[
                _conflict_text(self.GUIDES_11947_DOWNLOAD_FORMAT),
                _conflict_text(self.GUIDES_11947_DEFAULT_ORDERING),
            ],
        )

        question = SimpleNamespace(question_id=question_id)
        records = ConvergenceService().evaluate(
            questions=[question],
            research_records=[],
            worker_results=[worker_result],
        )

        assert len(records) == 1
        record = records[0]
        assert CONFLICT_PRODUCT_CONTRACT in record.conflict_classes
        assert record.decision, "an acceptance-changing conflict must need a decision"

        detail = _convergence_detail_lines(record)
        conflict_lines = [
            line for line in detail if line.startswith("- Conflict to resolve:")
        ]
        assert len(conflict_lines) == 1
        # The acceptance-changing conflict is the one the reader must decide,
        # even though the other conflict sorts first alphabetically.
        assert "Default ordering" in conflict_lines[0]
        # Neither conflict was collapsed to empty text on the way in.
        assert all(record.conflicts)
        assert any("excel sheet" in conflict for conflict in record.conflicts)