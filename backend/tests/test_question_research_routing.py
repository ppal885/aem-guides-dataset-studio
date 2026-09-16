"""Mandatory research routing for Question-Based UAC generation.

Regression coverage for the Output History purge ticket pattern: material
questions are identifiable from Jira/configuration, but the Coverage Reasoner
and Writer must never answer documentation-dependent questions from inference
alone.  The mandated flow is:

    Canonical Evidence -> Question Planner -> Research Requirement Classification
        -> Doc/Code/Historical Research as required -> Question Resolver
        -> Coverage Reasoner -> Writer -> Reviewer

with the hard gate that a material question whose ``research_requirement`` is
not ``NONE`` and whose ``research_status`` is ``PENDING`` cannot be finalized.
``NOT_FOUND`` never asserts that the opposite behavior is true.
"""

from __future__ import annotations

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    CANONICAL_STAGE_ORDER,
    ApplicabilityState,
    AuthorityClass,
    AuthoritySubject,
    BehaviorHypothesis,
    CanonicalBehaviorModel,
    CanonicalRuntimeStage,
    ClosureDimensionResult,
    ClosureDisposition,
    ContractFact,
    ContractFactSet,
    ContractFactType,
    ContractMode,
    CoverageDisposition,
    CurrentnessState,
    DirectedRetrievalRecord,
    EvidenceLifecycleStatus,
    EvidenceRecord,
    EvidenceSourceType,
    GateStatus,
    GenerationProfile,
    HypothesisState,
    InvestigationMateriality,
    MissingQuestion,
    ProductContractOwnership,
    ProductOwnership,
    QuestionResearchRecord,
    ResearchRequirement,
    ResearchRoutingProductContext,
    ResearchRoutingRequest,
    ResearchStatus,
    RetrievalStatus,
    RuntimeEntryPoint,
    ScopeResolution,
    SemanticDimension,
    SourceVisibility,
    UiApplicability,
    VerificationState,
)
from app.services.canonical_evidence_service import build_bundle
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE,
)
from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME
from app.services.question_research_routing_service import (
    QUESTION_RESEARCH_ROUTER,
)


TENANT = "tenant-research-routing"


def _record(
    *,
    source_type: EvidenceSourceType,
    reference: str,
    text: str,
    authority: AuthorityClass = AuthorityClass.CUSTOMER_REQUEST,
    confidence: float = 0.8,
    authority_subject: AuthoritySubject | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        source_type=source_type,
        authority_subject=authority_subject,
        source_reference=reference,
        tenant_id=TENANT,
        content={"text": text},
        product="AEM Guides",
        product_area="Publishing",
        capability="Output generation",
        surface="Map console",
        retrieved_at="2026-09-01T01:00:00Z",
        currentness=CurrentnessState.CURRENT,
        ui_applicability=UiApplicability.UNKNOWN,
        evidence_confidence=confidence,
        requirement_authority=authority,
        verification_status=VerificationState.VERIFIED_SOURCE,
        lifecycle_status=EvidenceLifecycleStatus.INSPECTED,
        inspected=True,
        ownership=ProductOwnership(
            product="AEM Guides",
            contract_ownership=(
                ProductContractOwnership.AEM_GUIDES_PRODUCT_CONTRACT
            ),
        ),
        visibility=SourceVisibility(tenant_id=TENANT),
    )


def _purge_question(
    text: str,
    *,
    subject: AuthoritySubject = AuthoritySubject.PRODUCT_CONTRACT,
    sources: list[EvidenceSourceType] | None = None,
    dimension: SemanticDimension | None = SemanticDimension.GENERATED_OUTPUT,
    closure_ids: list[str] | None = None,
) -> MissingQuestion:
    return MissingQuestion(
        question=text,
        dimension=dimension,
        authority_subject=subject,
        target_source_types=sources
        or [
            EvidenceSourceType.JIRA_DESCRIPTION,
            EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        ],
        blocking=True,
        materiality=InvestigationMateriality.P1,
        source_closure_ids=closure_ids or [],
    )


def _purge_questions() -> list[MissingQuestion]:
    """The material questions of the Output History purge ticket."""

    return [
        _purge_question(
            "What is the existing behavior of the AGE parameter for output "
            "history purge?"
        ),
        _purge_question(
            "What is the retention scope of the COUNT parameter for output "
            "history purge?"
        ),
        _purge_question(
            "Which entries does LOGS_ONLY mode retain after an output history "
            "purge?"
        ),
        _purge_question(
            "Is the purge action compatible with each output generation mode?",
            subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
            sources=[
                EvidenceSourceType.CURRENT_CODE,
                EvidenceSourceType.CURRENT_PR,
            ],
        ),
        _purge_question(
            "Are the purge defaults backward-compatible for existing presets?"
        ),
        _purge_question(
            "What happens to Generated Outputs entries after a log-only purge?"
        ),
    ]


def _facts(mode: ContractMode) -> ContractFactSet:
    return ContractFactSet(contract_mode=mode)


def _closure_row(
    question: MissingQuestion,
    disposition: ClosureDisposition,
    *,
    rationale: str = "The dimension is unresolved on current evidence.",
) -> ClosureDimensionResult:
    row = ClosureDimensionResult(
        entity="output history purge",
        dimension=question.dimension or SemanticDimension.GENERATED_OUTPUT,
        applicability=ApplicabilityState.APPLICABLE,
        disposition=disposition,
        rationale=rationale,
    )
    if row.closure_id not in question.source_closure_ids:
        question.source_closure_ids = sorted(
            set(question.source_closure_ids) | {row.closure_id}
        )
    return row


def _research_record(
    question: MissingQuestion,
    status: ResearchStatus,
    *,
    requirement: ResearchRequirement = ResearchRequirement.DOCUMENTATION,
    request_ids: list[str] | None = None,
    evidence_ids: list[str] | None = None,
) -> QuestionResearchRecord:
    requirement_record = CANONICAL_REASONING_SERVICE.classify_research_requirements(
        [question], _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT)
    )[0]
    return QuestionResearchRecord(
        question_id=question.question_id,
        requirement_id=requirement_record.requirement_id,
        research_requirement=requirement
        if requirement == requirement_record.research_requirement
        else requirement_record.research_requirement,
        research_status=status,
        research_request_ids=request_ids or [],
        evidence_ids=evidence_ids or [],
        reason="test-controlled research state",
    )


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def test_purge_ticket_questions_require_mandatory_research() -> None:
    questions = _purge_questions()
    records = CANONICAL_REASONING_SERVICE.classify_research_requirements(
        questions, _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT)
    )

    by_question = {row.question_id: row for row in records}
    assert set(by_question) == {row.question_id for row in questions}
    for question in questions:
        record = by_question[question.question_id]
        assert record.material is True
        assert record.required_source_types, question.question
        if question.authority_subject == AuthoritySubject.ACTUAL_IMPLEMENTATION:
            assert record.research_requirement == ResearchRequirement.IMPLEMENTATION
        else:
            # AGE behavior, COUNT retention scope, LOGS_ONLY retained entries,
            # backward-compatible defaults, and Generated Outputs behavior are
            # all documented product behavior the Jira/config evidence cannot
            # answer by itself.
            assert record.research_requirement == ResearchRequirement.DOCUMENTATION


def test_classification_covers_every_route() -> None:
    historical = _purge_question(
        "Has any historical ticket already decided the purge retention rule?",
        sources=[EvidenceSourceType.HISTORICAL_JIRA],
    )
    both = _purge_question(
        "Does the documented purge default match the implemented default?",
        sources=[
            EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
            EvidenceSourceType.CURRENT_CODE,
        ],
    )
    multi = _purge_question(
        "Which documented, implemented, and historically decided purge rules "
        "conflict?",
        sources=[
            EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
            EvidenceSourceType.CURRENT_CODE,
            EvidenceSourceType.HISTORICAL_JIRA,
        ],
    )
    jira_only = _purge_question(
        "What does the current ticket ask QA to verify?",
        sources=[EvidenceSourceType.JIRA_DESCRIPTION],
    )
    records = CANONICAL_REASONING_SERVICE.classify_research_requirements(
        [historical, both, multi, jira_only],
        _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT),
    )
    by_question = {row.question_id: row for row in records}
    assert (
        by_question[historical.question_id].research_requirement
        == ResearchRequirement.HISTORICAL
    )
    assert (
        by_question[both.question_id].research_requirement
        == ResearchRequirement.DOCUMENTATION_AND_IMPLEMENTATION
    )
    assert (
        by_question[multi.question_id].research_requirement
        == ResearchRequirement.MULTI_SOURCE
    )
    assert (
        by_question[jira_only.question_id].research_requirement
        == ResearchRequirement.NONE
    )
    assert not by_question[jira_only.question_id].required_source_types


def test_human_accepted_contract_needs_no_documentation_research() -> None:
    questions = _purge_questions()
    records = CANONICAL_REASONING_SERVICE.classify_research_requirements(
        questions, _facts(ContractMode.HUMAN_ACCEPTED_CONTRACT)
    )
    by_question = {row.question_id: row for row in records}
    for question in questions:
        if question.authority_subject == AuthoritySubject.PRODUCT_CONTRACT:
            # An explicit Human Accepted AC is the acceptance authority: Jira
            # authority itself is sufficient, so no documentation research may
            # be mandated for restating it.
            assert (
                by_question[question.question_id].research_requirement
                == ResearchRequirement.NONE
            )
        else:
            assert (
                by_question[question.question_id].research_requirement
                == ResearchRequirement.IMPLEMENTATION
            )


# ---------------------------------------------------------------------------
# Research status resolution
# ---------------------------------------------------------------------------


def _retrieval(
    question: MissingQuestion,
    matched: list[EvidenceRecord],
) -> DirectedRetrievalRecord:
    return DirectedRetrievalRecord(
        question_id=question.question_id,
        query=question.question,
        authority_subject=question.authority_subject,
        target_source_types=question.target_source_types,
        matched_evidence_ids=[row.evidence_id for row in matched],
        status=RetrievalStatus.USED if matched else RetrievalStatus.UNAVAILABLE,
        reason="Targeted supplied evidence matched the question."
        if matched
        else "No supplied evidence matched; absence is not treated as rejection.",
    )


def test_jira_only_match_leaves_documentation_research_partial() -> None:
    """Jira/config evidence alone never satisfies documentation research."""

    question = _purge_questions()[0]
    jira_record = _record(
        source_type=EvidenceSourceType.JIRA_DESCRIPTION,
        reference="jira:GUIDES-99001",
        text="The ticket asks how the AGE parameter behaves for output history "
        "purge.",
    )
    bundle = build_bundle([jira_record], tenant_id=TENANT)
    requirements = CANONICAL_REASONING_SERVICE.classify_research_requirements(
        [question], _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT)
    )
    retrieval = _retrieval(question, [jira_record])
    hypothesis = BehaviorHypothesis(
        statement=question.question,
        state=HypothesisState.CONFIRMED,
        supporting_evidence_ids=[jira_record.evidence_id],
        derived_from_question_id=question.question_id,
        confidence=0.9,
    )
    records = CANONICAL_REASONING_SERVICE.resolve_question_research(
        [question],
        requirements,
        [retrieval],
        [hypothesis],
        evidence=bundle,
    )
    (record,) = records
    assert record.research_status == ResearchStatus.PARTIAL
    assert record.research_request_ids == [retrieval.retrieval_id]
    assert record.evidence_ids == [jira_record.evidence_id]


def test_skipped_research_stays_pending() -> None:
    question = _purge_questions()[0]
    requirements = CANONICAL_REASONING_SERVICE.classify_research_requirements(
        [question], _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT)
    )
    (record,) = CANONICAL_REASONING_SERVICE.resolve_question_research(
        [question], requirements, [], []
    )
    assert record.research_status == ResearchStatus.PENDING
    assert not record.research_request_ids
    assert not record.evidence_ids


def test_not_found_is_not_a_negative_answer() -> None:
    question = _purge_questions()[0]
    requirements = CANONICAL_REASONING_SERVICE.classify_research_requirements(
        [question], _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT)
    )
    retrieval = _retrieval(question, [])
    (record,) = CANONICAL_REASONING_SERVICE.resolve_question_research(
        [question], requirements, [retrieval], []
    )
    assert record.research_status == ResearchStatus.NOT_FOUND
    assert "not treated as the opposite behavior" in record.reason
    # NOT_FOUND must never be validated as an answer.
    with pytest.raises(ValueError, match="ANSWER_FOUND requires"):
        QuestionResearchRecord(
            question_id=question.question_id,
            requirement_id=requirements[0].requirement_id,
            research_requirement=requirements[0].research_requirement,
            research_status=ResearchStatus.ANSWER_FOUND,
            reason="no request executed",
        )


def test_documented_answer_completes_research() -> None:
    question = _purge_questions()[0]
    doc_record = _record(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        reference="expleague:output-history-purge",
        text="The AGE parameter purges output history entries older than the "
        "configured number of days.",
        authority=AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
        confidence=0.95,
    )
    bundle = build_bundle([doc_record], tenant_id=TENANT)
    requirements = CANONICAL_REASONING_SERVICE.classify_research_requirements(
        [question], _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT)
    )
    retrieval = _retrieval(question, [doc_record])
    hypothesis = BehaviorHypothesis(
        statement=question.question,
        state=HypothesisState.CONFIRMED,
        supporting_evidence_ids=[doc_record.evidence_id],
        derived_from_question_id=question.question_id,
        confidence=0.95,
    )
    (record,) = CANONICAL_REASONING_SERVICE.resolve_question_research(
        [question],
        requirements,
        [retrieval],
        [hypothesis],
        evidence=bundle,
    )
    assert record.research_status == ResearchStatus.ANSWER_FOUND


# ---------------------------------------------------------------------------
# Coverage hard gate
# ---------------------------------------------------------------------------


def _confirmed_hypothesis(question: MissingQuestion) -> BehaviorHypothesis:
    return BehaviorHypothesis(
        statement=question.question,
        state=HypothesisState.CONFIRMED,
        supporting_evidence_ids=["ev-support-1"],
        derived_from_question_id=question.question_id,
        confidence=0.9,
    )


def test_coverage_rejects_pending_mandatory_research() -> None:
    """Coverage cannot finalize a material question while research is PENDING."""

    for question in _purge_questions():
        closure_row = _closure_row(question, ClosureDisposition.UNRESOLVED_AND_EXPOSED)
        hypothesis = _confirmed_hypothesis(question)
        pending = _research_record(question, ResearchStatus.PENDING)

        finalized = CANONICAL_REASONING_SERVICE.classify_coverage(
            _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT),
            [closure_row],
            [],
            [hypothesis],
            ScopeResolution(),
            [question],
        )
        assert finalized[0].disposition != CoverageDisposition.OPEN_QUESTION

        gated = CANONICAL_REASONING_SERVICE.classify_coverage(
            _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT),
            [closure_row],
            [],
            [hypothesis],
            ScopeResolution(),
            [question],
            [pending],
        )
        assert len(gated) == 1
        assert gated[0].disposition == CoverageDisposition.OPEN_QUESTION
        assert "never executed" in gated[0].rationale
        assert question.question_id in gated[0].source_question_ids


def test_coverage_cannot_finalize_from_jira_alone() -> None:
    """PARTIAL research (Jira-only match) keeps the purge questions open."""

    for question in _purge_questions():
        closure_row = _closure_row(question, ClosureDisposition.UNRESOLVED_AND_EXPOSED)
        hypothesis = _confirmed_hypothesis(question)
        partial = _research_record(
            question,
            ResearchStatus.PARTIAL,
            request_ids=["retrieval:partial-1"],
            evidence_ids=["ev-jira-1"],
        )
        gated = CANONICAL_REASONING_SERVICE.classify_coverage(
            _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT),
            [closure_row],
            [],
            [hypothesis],
            ScopeResolution(),
            [question],
            [partial],
        )
        assert len(gated) == 1
        assert gated[0].disposition == CoverageDisposition.OPEN_QUESTION
        assert "partially answered" in gated[0].rationale


def test_not_found_never_means_opposite_behavior() -> None:
    question = _purge_questions()[2]
    closure_row = _closure_row(
        question,
        ClosureDisposition.INVESTIGATED_AND_REJECTED,
        rationale="No current evidence retained the entries.",
    )
    not_found = _research_record(
        question,
        ResearchStatus.NOT_FOUND,
        request_ids=["retrieval:not-found-1"],
    )

    ungated = CANONICAL_REASONING_SERVICE.classify_coverage(
        _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT),
        [closure_row],
        [],
        [],
        ScopeResolution(),
        [question],
    )
    assert [row.disposition for row in ungated] == [
        CoverageDisposition.INVESTIGATED_AND_REJECTED
    ]

    rows = CANONICAL_REASONING_SERVICE.classify_coverage(
        _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT),
        [closure_row],
        [],
        [],
        ScopeResolution(),
        [question],
        [not_found],
    )
    assert rows
    assert all(
        row.disposition != CoverageDisposition.INVESTIGATED_AND_REJECTED
        for row in rows
    )
    linked = [row for row in rows if question.question_id in row.source_question_ids]
    assert linked
    assert all(row.disposition == CoverageDisposition.OPEN_QUESTION for row in linked)
    assert any(
        "not treated as the opposite behavior" in row.rationale for row in linked
    )


def test_answer_found_research_allows_finalization() -> None:
    question = _purge_questions()[5]
    closure_row = _closure_row(question, ClosureDisposition.UNRESOLVED_AND_EXPOSED)
    hypothesis = _confirmed_hypothesis(question)
    answered = _research_record(
        question,
        ResearchStatus.ANSWER_FOUND,
        request_ids=["retrieval:answered-1"],
        evidence_ids=["ev-doc-1"],
    )
    rows = CANONICAL_REASONING_SERVICE.classify_coverage(
        _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT),
        [closure_row],
        [],
        [hypothesis],
        ScopeResolution(),
        [question],
        [answered],
    )
    assert len(rows) == 1
    assert rows[0].disposition == CoverageDisposition.GENERATED_OUTPUT_VALIDATION


def test_not_required_research_does_not_block_coverage() -> None:
    """Human Accepted AC proceeds without unnecessary documentation research."""

    question = _purge_question(
        "Is reading a run's output history required to succeed?",
    )
    requirements = CANONICAL_REASONING_SERVICE.classify_research_requirements(
        [question], _facts(ContractMode.HUMAN_ACCEPTED_CONTRACT)
    )
    assert requirements[0].research_requirement == ResearchRequirement.NONE
    (record,) = CANONICAL_REASONING_SERVICE.resolve_question_research(
        [question], requirements, [], []
    )
    assert record.research_status == ResearchStatus.NOT_REQUIRED

    closure_row = _closure_row(question, ClosureDisposition.UNRESOLVED_AND_EXPOSED)
    hypothesis = _confirmed_hypothesis(question)
    rows = CANONICAL_REASONING_SERVICE.classify_coverage(
        _facts(ContractMode.HUMAN_ACCEPTED_CONTRACT),
        [closure_row],
        [],
        [hypothesis],
        ScopeResolution(),
        [question],
        [record],
    )
    assert len(rows) == 1
    assert rows[0].disposition == CoverageDisposition.GENERATED_OUTPUT_VALIDATION


# ---------------------------------------------------------------------------
# Reviewer and Writer
# ---------------------------------------------------------------------------


def test_reviewer_detects_skipped_or_pending_mandatory_research() -> None:
    question = _purge_questions()[0]
    requirements = CANONICAL_REASONING_SERVICE.classify_research_requirements(
        [question], _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT)
    )

    skipped = CANONICAL_REASONING_SERVICE.behavioral_completeness_gate(
        [],
        [question],
        ScopeResolution(),
        [],
        [],
        None,
        requirements,
        [],
    )
    assert skipped.status == GateStatus.FAILED
    assert any("research routing was skipped" in row for row in skipped.failures)

    pending = _research_record(question, ResearchStatus.PENDING)
    pending_gate = CANONICAL_REASONING_SERVICE.behavioral_completeness_gate(
        [],
        [question],
        ScopeResolution(),
        [],
        [],
        None,
        requirements,
        [pending],
    )
    assert pending_gate.status == GateStatus.FAILED
    assert any("still PENDING" in row for row in pending_gate.failures)

    answered = _research_record(
        question,
        ResearchStatus.ANSWER_FOUND,
        request_ids=["retrieval:answered-1"],
        evidence_ids=["ev-doc-1"],
    )
    answered_gate = CANONICAL_REASONING_SERVICE.behavioral_completeness_gate(
        [],
        [question],
        ScopeResolution(),
        [],
        [],
        None,
        requirements,
        [answered],
    )
    assert answered_gate.status == GateStatus.PASSED


def _render_request():
    return CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99001",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )


def test_writer_never_compensates_for_missing_research() -> None:
    question = _purge_questions()[5]
    pending = _research_record(question, ResearchStatus.PENDING)
    compensating = CANONICAL_REASONING_SERVICE.classify_coverage(
        _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT),
        [_closure_row(question, ClosureDisposition.UNRESOLVED_AND_EXPOSED)],
        [],
        [_confirmed_hypothesis(question)],
        ScopeResolution(),
        [question],
    )
    assert compensating[0].disposition != CoverageDisposition.OPEN_QUESTION

    with pytest.raises(RuntimeError, match="must not compensate for missing"):
        CANONICAL_REASONING_SERVICE.render_final_plan(
            _render_request(),
            _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT),
            ScopeResolution(),
            CanonicalBehaviorModel(),
            [],
            [question],
            [],
            compensating,
            [],
            [],
            [],
            research_records=[pending],
        )


def test_writer_keeps_unresearched_questions_visible() -> None:
    question = _purge_questions()[5]
    pending = _research_record(question, ResearchStatus.PENDING)
    gated = CANONICAL_REASONING_SERVICE.classify_coverage(
        _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT),
        [_closure_row(question, ClosureDisposition.UNRESOLVED_AND_EXPOSED)],
        [],
        [_confirmed_hypothesis(question)],
        ScopeResolution(),
        [question],
        [pending],
    )
    plan, rendered = CANONICAL_REASONING_SERVICE.render_final_plan(
        _render_request(),
        _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT),
        ScopeResolution(),
        CanonicalBehaviorModel(),
        [],
        [question],
        [],
        gated,
        [],
        [],
        [],
        research_records=[pending],
    )
    assert question.question in rendered
    assert question.question_id in plan.open_question_ids
    assert not plan.promoted_candidate_ids


# ---------------------------------------------------------------------------
# Traceability chain and runtime wiring
# ---------------------------------------------------------------------------


def test_traceability_chain_question_to_coverage_decision() -> None:
    """Question -> Research Requirement -> Research Request -> Research Evidence
    -> Resolution -> Coverage Decision is preserved by deterministic IDs."""

    question = _purge_questions()[0]
    jira_record = _record(
        source_type=EvidenceSourceType.JIRA_DESCRIPTION,
        reference="jira:GUIDES-99001",
        text="The ticket asks how the AGE parameter behaves for output history "
        "purge.",
    )
    doc_record = _record(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        reference="expleague:output-history-purge",
        text="The AGE parameter purges output history entries older than the "
        "configured number of days.",
        authority=AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
        confidence=0.95,
    )
    bundle = build_bundle([jira_record, doc_record], tenant_id=TENANT)
    facts = _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT)

    requirements = CANONICAL_REASONING_SERVICE.classify_research_requirements(
        [question], facts
    )
    (requirement,) = requirements
    assert requirement.question_id == question.question_id
    assert requirement.research_requirement == ResearchRequirement.DOCUMENTATION

    retrievals = CANONICAL_REASONING_SERVICE.retrieve_for_questions(bundle, [question])
    (retrieval,) = retrievals
    assert retrieval.question_id == question.question_id
    assert doc_record.evidence_id in retrieval.matched_evidence_ids

    hypotheses, _model = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        bundle, [question], retrievals, CanonicalBehaviorModel()
    )
    (hypothesis,) = hypotheses
    assert hypothesis.derived_from_question_id == question.question_id

    (research,) = CANONICAL_REASONING_SERVICE.resolve_question_research(
        [question],
        requirements,
        retrievals,
        hypotheses,
        evidence=bundle,
    )
    assert research.question_id == question.question_id
    assert research.requirement_id == requirement.requirement_id
    assert research.research_request_ids == [retrieval.retrieval_id]
    assert doc_record.evidence_id in research.evidence_ids
    assert research.research_status == ResearchStatus.ANSWER_FOUND

    closure_row = _closure_row(question, ClosureDisposition.UNRESOLVED_AND_EXPOSED)
    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts,
        [closure_row],
        [],
        hypotheses,
        ScopeResolution(),
        [question],
        [research],
    )
    (disposition,) = dispositions
    assert question.question_id in disposition.source_question_ids
    assert hypothesis.hypothesis_id in disposition.source_hypothesis_ids
    assert closure_row.closure_id in disposition.source_closure_ids
    assert disposition.disposition == CoverageDisposition.GENERATED_OUTPUT_VALIDATION


def _runtime_packet() -> dict[str, object]:
    return {
        "jira_key": "GUIDES-99001",
        "issue": {
            "issue_key": "GUIDES-99001",
            "summary": "Add an output history purge action for generated outputs.",
            "description": (
                "In scope: Native PDF. Out of scope: HTML5. "
                "Enable DITA-OT Processing: ON. Output preset type: Native PDF. "
                "The existing behavior must remain compatible after upgrade."
            ),
            "deployment_model": "On-prem",
            "product_version": "5.0",
        },
        "dita_spec_evidence": [
            {
                "canonical_url": "https://docs.oasis.test/dita/topicref",
                "text": "A topicref can reference nested map content and "
                "participates in hierarchy.",
            }
        ],
    }


def test_runtime_runs_classification_stage_and_publishes_research_trace() -> None:
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99001",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=_runtime_packet(),
    )

    stages = [row.stage for row in result.trace.stage_trace]
    assert stages == list(CANONICAL_STAGE_ORDER)
    classifier_index = stages.index(CanonicalRuntimeStage.RESEARCH_REQUIREMENT_CLASSIFIER)
    assert stages[classifier_index - 1] == CanonicalRuntimeStage.MISSING_QUESTION_GENERATOR
    # R2: the research orchestrator executes workers between classification
    # and directed retrieval.
    assert stages[classifier_index + 1] == CanonicalRuntimeStage.RESEARCH_ORCHESTRATOR

    requirements = result.output_payload["research_requirements"]
    research = result.output_payload["question_research"]
    questions = result.output_payload["missing_questions"]
    retrievals = result.output_payload["directed_retrievals"]
    handoffs = result.output_payload.get(
        "github_implementation_verification_handoffs", []
    )

    requirement_by_question = {row["question_id"]: row for row in requirements}
    research_by_question = {row["question_id"]: row for row in research}
    request_ids = {row["retrieval_id"] for row in retrievals} | {
        row["HANDOFF_ID"] for row in handoffs
    } | {
        # R2: worker envelopes are first-class research requests.
        row["research_id"]
        for row in result.output_payload.get("research_worker_results") or []
    }
    assert set(requirement_by_question) == {row["question_id"] for row in questions}
    assert set(research_by_question) == {row["question_id"] for row in questions}
    for row in research:
        requirement = requirement_by_question[row["question_id"]]
        assert row["requirement_id"] == requirement["requirement_id"]
        assert row["research_requirement"] == requirement["research_requirement"]
        assert set(row["research_request_ids"]) <= request_ids
        if row["research_status"] == "PENDING":
            pytest.fail(
                "mandatory research was left pending in a fully executed runtime: "
                f"{row['question_id']}"
            )
    # The trace carries the same records for auditability.
    assert result.trace.research_requirements
    assert {
        row.requirement_id for row in result.trace.research_requirements
    } == {row["requirement_id"] for row in requirements}
    assert {row.research_id for row in result.trace.question_research} == {
        row["research_id"] for row in research
    }


def test_human_accepted_runtime_proceeds_without_documentation_research() -> None:
    packet = _runtime_packet()
    issue = packet["issue"]
    assert isinstance(issue, dict)
    issue["acceptance_criteria"] = [
        "Reading a run's output history after a log-only purge must not fail."
    ]
    issue["labels"] = ["uac_done"]
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99001",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    assert result.output_payload["contract_facts"]["contract_mode"] == (
        "HUMAN_ACCEPTED_CONTRACT"
    )
    research = result.output_payload["question_research"]
    product_contract_questions = {
        row["question_id"]: row
        for row in result.output_payload["missing_questions"]
        if row["authority_subject"] == "PRODUCT_CONTRACT"
    }
    for question_id in product_contract_questions:
        record = next(row for row in research if row["question_id"] == question_id)
        assert record["research_requirement"] == "NONE"
        assert record["research_status"] == "NOT_REQUIRED"

# ---------------------------------------------------------------------------
# Reusable per-question research-routing contract (Question Planner surface)
# ---------------------------------------------------------------------------

_ROUTING_PRODUCT_CONTEXT = ResearchRoutingProductContext(
    product="AEM Guides",
    product_area="Publishing",
    product_versions=["5.0"],
    deployment_modes=["on-prem"],
)


def test_routing_contract_binds_to_a_planned_question() -> None:
    """The contract invokes per question; the batch path derives from it."""

    question = _purge_questions()[0]
    request = QUESTION_RESEARCH_ROUTER.build_request(question)
    assert request.question_id == question.question_id
    assert request.request_id.startswith("research-route:")

    record = QUESTION_RESEARCH_ROUTER.classify(
        request,
        question=question,
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
    )
    assert record.research_requirement == ResearchRequirement.DOCUMENTATION
    assert record.routing_request_id == request.request_id
    assert record.applicability == ApplicabilityState.APPLICABLE

    # The ticket-level batch classifier is exactly this per-question contract.
    (batch,) = CANONICAL_REASONING_SERVICE.classify_research_requirements(
        [question], _facts(ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT)
    )
    assert batch.requirement_id == record.requirement_id


def test_routing_contract_accepts_planner_supplied_fields() -> None:
    """question_id + research_need + required_source_type + product_context +
    applicability are accepted without another architectural rewrite."""

    question = _purge_questions()[3]  # mode/action compatibility (implementation)
    request = ResearchRoutingRequest(
        question_id=question.question_id,
        research_need=ResearchRequirement.DOCUMENTATION_AND_IMPLEMENTATION,
        required_source_type=[
            EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
            EvidenceSourceType.CURRENT_CODE,
        ],
        product_context=_ROUTING_PRODUCT_CONTEXT,
        applicability=ApplicabilityState.APPLICABLE,
    )
    record = QUESTION_RESEARCH_ROUTER.classify(
        request,
        question=question,
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
    )
    # The explicit need overrides the evidence-path derivation.
    assert record.research_requirement == (
        ResearchRequirement.DOCUMENTATION_AND_IMPLEMENTATION
    )
    assert record.required_source_types == [
        EvidenceSourceType.CURRENT_CODE,
        EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
    ]
    assert record.product_context == _ROUTING_PRODUCT_CONTEXT
    assert record.applicability == ApplicabilityState.APPLICABLE
    assert record.material is True


def test_routing_contract_without_a_missing_question_object() -> None:
    """A later Question Planner can route by question_id alone."""

    question_id = "question:" + "0" * 32
    request = ResearchRoutingRequest(
        question_id=question_id,
        research_need=ResearchRequirement.IMPLEMENTATION,
        required_source_type=[EvidenceSourceType.CURRENT_CODE],
        product_context=_ROUTING_PRODUCT_CONTEXT,
        applicability=ApplicabilityState.APPLICABLE,
    )
    record = QUESTION_RESEARCH_ROUTER.classify(request)
    assert record.question_id == question_id
    assert record.research_requirement == ResearchRequirement.IMPLEMENTATION
    assert record.required_source_types == [EvidenceSourceType.CURRENT_CODE]
    assert record.material is True

    # And the same record resolves per question through the contract.
    code_record = _record(
        source_type=EvidenceSourceType.CURRENT_CODE,
        reference="repo:starling/purge.py",
        text="The purge action keeps log entries in LOGS_ONLY mode.",
        authority=AuthorityClass.IMPLEMENTATION_CONFIRMED,
        authority_subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
    )
    bundle = build_bundle([code_record], tenant_id=TENANT)
    retrieval = DirectedRetrievalRecord(
        question_id=question_id,
        query="LOGS_ONLY retained entries",
        authority_subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        target_source_types=[EvidenceSourceType.CURRENT_CODE],
        matched_evidence_ids=[code_record.evidence_id],
        status=RetrievalStatus.USED,
        reason="Targeted supplied evidence matched the question.",
    )
    hypothesis = BehaviorHypothesis(
        statement="LOGS_ONLY retains log entries.",
        state=HypothesisState.CONFIRMED,
        supporting_evidence_ids=[code_record.evidence_id],
        derived_from_question_id=question_id,
        confidence=0.9,
    )
    research = QUESTION_RESEARCH_ROUTER.resolve(
        record,
        retrievals=[retrieval],
        hypotheses=[hypothesis],
        evidence=bundle,
    )
    assert research.research_status == ResearchStatus.ANSWER_FOUND
    assert research.requirement_id == record.requirement_id
    assert research.research_request_ids == [retrieval.retrieval_id]


def test_routing_contract_applicability_makes_research_not_applicable() -> None:
    question = _purge_questions()[0]
    request = QUESTION_RESEARCH_ROUTER.build_request(
        question,
        applicability=ApplicabilityState.NOT_APPLICABLE,
    )
    record = QUESTION_RESEARCH_ROUTER.classify(
        request,
        question=question,
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
    )
    assert record.material is False
    research = QUESTION_RESEARCH_ROUTER.resolve(record)
    assert research.research_status == ResearchStatus.NOT_APPLICABLE


def test_routing_contract_rejects_incoherent_requests() -> None:
    question = _purge_questions()[0]
    with pytest.raises(ValueError, match="cannot mandate required source types"):
        ResearchRoutingRequest(
            question_id=question.question_id,
            research_need=ResearchRequirement.NONE,
            required_source_type=[EvidenceSourceType.CURRENT_CODE],
        )
    with pytest.raises(ValueError, match="or an explicit research_need"):
        QUESTION_RESEARCH_ROUTER.classify(
            ResearchRoutingRequest(question_id=question.question_id)
        )
    with pytest.raises(ValueError, match="disagree on question_id"):
        QUESTION_RESEARCH_ROUTER.classify(
            ResearchRoutingRequest(question_id="question:" + "1" * 32),
            question=question,
        )


def test_routing_contract_request_identity_is_deterministic() -> None:
    question = _purge_questions()[0]
    first = QUESTION_RESEARCH_ROUTER.build_request(question)
    second = QUESTION_RESEARCH_ROUTER.build_request(question)
    assert first.request_id == second.request_id
    other = QUESTION_RESEARCH_ROUTER.build_request(
        question, research_need=ResearchRequirement.HISTORICAL
    )
    assert other.request_id != first.request_id
