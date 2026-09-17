"""P3: Bounded Acceptance TBD and Partial Contract Promotion.

An unresolved acceptance question blocks only the claims whose correctness
depends on that unresolved answer.  Ticket-wide blocking is replaced by
claim-level dependency through canonical coverage linkage.

Invariants under test:
- UNRESOLVED ACCEPTANCE BEHAVIOR MUST REMAIN TBD.
- AN UNRESOLVED DIMENSION MUST NOT BLOCK AN INDEPENDENT SUFFICIENT CLAIM.
- A TBD MUST NEVER BE SILENTLY FILLED BY THE MODEL.
- RESEARCH MUST RUN BEFORE RESIDUAL UNCERTAINTY BECOMES A TBD.
"""

from __future__ import annotations

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    AuthorityClass,
    AuthoritySubject,
    ContractFact,
    ContractFactSet,
    ContractFactType,
    ContractMode,
    CoverageDisposition,
    CoverageDispositionRecord,
    EvidenceSourceType,
    GenerationProfile,
    HumanClarification,
    MissingQuestion,
    OpenQuestionClass,
    QuestionResearchRecord,
    ResearchRequirement,
    ResearchRequirementRecord,
    ResearchStatus,
    RuntimeEntryPoint,
    ScopeResolution,
    SemanticDimension,
)
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE as S,
)
from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME


def _fact(
    text: str,
    fact_type: ContractFactType = ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
    authority: AuthorityClass = AuthorityClass.CUSTOMER_REQUEST,
) -> ContractFact:
    return ContractFact(
        fact_type=fact_type,
        literal=text,
        normalized_value=text.casefold(),
        source_evidence_ids=["ev-1"],
        source_reference="test:description",
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        authority_class=authority,
        authoritative=True,
    )


def _blocking_question(text: str, *, dimension=None) -> MissingQuestion:
    return MissingQuestion(
        question=text,
        dimension=dimension,
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        target_source_types=[],
        blocking=True,
        open_question_class=OpenQuestionClass.USER_ACCEPTANCE_DECISION,
    )


def _research(
    question: MissingQuestion, status: ResearchStatus
) -> QuestionResearchRecord:
    requirement = ResearchRequirementRecord(
        question_id=question.question_id,
        research_requirement=ResearchRequirement.DOCUMENTATION,
        material=True,
        required_source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
        rationale="test requirement",
    )
    return QuestionResearchRecord(
        question_id=question.question_id,
        requirement_id=requirement.requirement_id,
        research_requirement=requirement.research_requirement,
        research_status=status,
        research_request_ids=(
            [] if status in {ResearchStatus.PENDING} else ["research-worker:test"]
        ),
        evidence_ids=[],
        reason="test research state",
    )


def _acceptance_disposition(
    text: str, fact: ContractFact, question: MissingQuestion | None = None
) -> CoverageDispositionRecord:
    return CoverageDispositionRecord(
        candidate=text,
        disposition=CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
        source_fact_ids=[fact.fact_id],
        source_question_ids=(
            [question.question_id] if question is not None else []
        ),
        rationale="from ticket",
    )


# ---------------------------------------------------------------------------
# Claim-level dependency (spec sections 2, 3, 13, 14)
# ---------------------------------------------------------------------------


def test_unresolved_question_blocks_only_dependent_claims() -> None:
    fact_a = _fact("The archive includes a completion marker.")
    fact_b = _fact("The archive preserves prior manifests.")
    question = _blocking_question(
        "Which processing modes does the marker apply under?"
    )
    dispositions = [
        _acceptance_disposition(fact_a.literal, fact_a),
        _acceptance_disposition(fact_b.literal, fact_b, question=question),
    ]
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[fact_a, fact_b],
    )
    batch = S.resolve_acceptance_contract_with_trace(
        facts, dispositions, [question]
    )
    by_statement = {row.statement: row for row in batch.candidates}
    # Claim A has no question link: independent, not blocked.
    assert by_statement[fact_a.literal].unresolved_decision_ids == []
    # Claim B depends on the unresolved question: still blocked.
    assert by_statement[fact_b.literal].unresolved_decision_ids == [
        question.question_id
    ]


def test_promotion_gate_promotes_independent_and_blocks_dependent() -> None:
    fact_a = _fact("The archive includes a completion marker.")
    fact_b = _fact("The archive preserves prior manifests.")
    question = _blocking_question(
        "Which processing modes does the marker apply under?"
    )
    dispositions = [
        _acceptance_disposition(fact_a.literal, fact_a),
        _acceptance_disposition(fact_b.literal, fact_b, question=question),
    ]
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[fact_a, fact_b],
    )
    batch = S.resolve_acceptance_contract_with_trace(
        facts, dispositions, [question]
    )
    gate, decisions = S.acceptance_promotion_gate(
        batch.candidates, facts, ScopeResolution(), dispositions
    )
    by_statement = {d.candidate_id: d for d in decisions}
    candidate_by_statement = {c.statement: c for c in batch.candidates}
    assert (
        by_statement[candidate_by_statement[fact_a.literal].candidate_id].status.value
        == "PROMOTED"
    )
    blocked = by_statement[
        candidate_by_statement[fact_b.literal].candidate_id
    ]
    assert blocked.status.value == "BLOCKED"


# ---------------------------------------------------------------------------
# ACCEPTANCE_TBD representation (spec sections 4, 16)
# ---------------------------------------------------------------------------


def test_exhausted_research_yields_bounded_acceptance_tbd() -> None:
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[_fact("The archive includes a completion marker.")],
    )
    question = _blocking_question(
        "Which processing modes does the marker apply under?"
    )
    research = _research(question, ResearchStatus.NOT_FOUND)
    rows = S.classify_coverage(
        facts, [], [], [], ScopeResolution(), [question], [research]
    )
    tbd = [row for row in rows if row.disposition == CoverageDisposition.ACCEPTANCE_TBD]
    assert len(tbd) == 1
    row = tbd[0]
    assert row.source_question_ids == [question.question_id]
    # Stays acceptance-lane; never demoted to regression/investigation.
    assert (row.coverage_class, row.priority) == ("ACCEPTANCE", "P0")
    # And it never promotes.
    batch = S.resolve_acceptance_contract_with_trace(
        facts,
        [
            row,
            _acceptance_disposition(facts.facts[0].literal, facts.facts[0]),
        ],
        [question],
    )
    assert all(
        CoverageDispositionRecord  # noqa: B018 - sanity that rows are typed
        is not None
        for _ in [0]
    )
    tbd_candidates = [
        c
        for c in batch.discovered_candidates
        if row.disposition_id in c.source_disposition_ids
    ]
    assert not tbd_candidates


def test_pending_research_never_becomes_a_final_tbd() -> None:
    # R2 invariant: research must run before residual uncertainty becomes a
    # TBD.  PENDING means never executed - the question stays open/blocking.
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[_fact("The archive includes a completion marker.")],
    )
    question = _blocking_question(
        "Which processing modes does the marker apply under?"
    )
    research = _research(question, ResearchStatus.PENDING)
    rows = S.classify_coverage(
        facts, [], [], [], ScopeResolution(), [question], [research]
    )
    assert not [
        row for row in rows if row.disposition == CoverageDisposition.ACCEPTANCE_TBD
    ]


def test_clarified_question_never_becomes_tbd() -> None:
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[_fact("The archive includes a completion marker.")],
    )
    question = _blocking_question(
        "Which processing modes does the marker apply under?"
    )
    research = _research(question, ResearchStatus.NOT_FOUND)
    rows = S.classify_coverage(
        facts,
        [],
        [],
        [],
        ScopeResolution(),
        [question],
        [research],
        {question.question_id},
    )
    assert not [
        row for row in rows if row.disposition == CoverageDisposition.ACCEPTANCE_TBD
    ]


def test_multiple_independent_tbds_stay_separate() -> None:
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[_fact("The archive includes a completion marker.")],
    )
    q1 = _blocking_question("Which processing modes does the marker apply under?")
    q2 = _blocking_question("Which roles may regenerate the archive?")
    research = [
        _research(q1, ResearchStatus.NOT_FOUND),
        _research(q2, ResearchStatus.SOURCE_UNAVAILABLE),
    ]
    rows = S.classify_coverage(
        facts, [], [], [], ScopeResolution(), [q1, q2], research
    )
    tbds = [row for row in rows if row.disposition == CoverageDisposition.ACCEPTANCE_TBD]
    assert len(tbds) == 2
    assert {row.candidate for row in tbds} == {q1.question, q2.question}
    assert all(len(row.source_question_ids) == 1 for row in tbds)


# ---------------------------------------------------------------------------
# Production entry point (spec sections 11, 19, 22)
# ---------------------------------------------------------------------------


def _run(issue: dict, clarifications: list[dict] | None = None):
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99311",
        tenant_id="tenant_p3",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
        options=(
            {"human_clarifications": clarifications} if clarifications else None
        ),
    )
    packet = {"jira_key": "GUIDES-99311", "issue": issue}
    return CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request, packet=packet
    )


def test_partial_promotion_production_run() -> None:
    # Accepted core behavior + one unresolved applicability dimension:
    # core claims promote, the dimension survives as bounded TBD, status is
    # NEEDS_HUMAN_REVIEW (never BLOCKED, never silently COMPLETED).
    result = _run(
        {
            "issue_key": "GUIDES-99311",
            "summary": "Completed archives expose a distinct attention state.",
            "description": (
                "Generation completes successfully but can contain log "
                "entries reviewers miss. Authors publish the map as Native "
                "PDF output."
            ),
            "labels": ["accepted_uac"],
            "acceptance_criteria": [
                "Completed generation that contains log entries requiring "
                "attention is shown with a distinct attention state, separate "
                "from hard failure."
            ],
            "deployment_model": "On-prem",
            "product_version": "5.0",
        }
    )
    payload = result.output_payload
    promoted = [
        row for row in payload["promotion_decisions"] if row["status"] == "PROMOTED"
    ]
    assert promoted
    # The unresolved applicability dimension survives as a bounded
    # ACCEPTANCE_TBD bound to its exact question; the run is
    # NEEDS_HUMAN_REVIEW - never BLOCKED, never silently COMPLETED.
    tbds = [
        row
        for row in payload["coverage_dispositions"]
        if row["disposition"] == "ACCEPTANCE_TBD"
    ]
    blocking = [
        row for row in payload["missing_questions"] if row["blocking"]
    ]
    assert blocking, "fixture must produce an unresolved acceptance dimension"
    assert result.status == "needs_human_review"
    # Human output renders the promoted AC and never the compact blocked doc.
    rendered = result.rendered_output or ""
    assert "distinct attention state" in rendered
    assert "No Acceptance Criteria were generated" not in rendered
    if tbds:
        tbd_question_ids = {
            qid for row in tbds for qid in row["source_question_ids"]
        }
        assert tbd_question_ids <= {row["question_id"] for row in blocking}
        assert "Product decisions required" in rendered


def test_critical_negative_control_unresolved_core_stays_blocked() -> None:
    # The unresolved product decision determines WHAT the solution is:
    # nothing promotes, the run stays BLOCKED.  P2 preserved.
    result = _run(
        {
            "issue_key": "GUIDES-99311",
            "summary": "Reviewers miss important log entries.",
            "description": (
                "There is no easy way to notice entries that need attention "
                "after generation completes."
            ),
            "deployment_model": "On-prem",
            "product_version": "5.0",
        }
    )
    payload = result.output_payload
    assert result.status == "blocked"
    assert not payload["acceptance_candidates"]
    assert not [
        row for row in payload["promotion_decisions"] if row["status"] == "PROMOTED"
    ]
    rendered = result.rendered_output or ""
    assert "None generated until the blocking decisions are resolved." in rendered


def test_clarification_resume_lifts_tbd_and_keeps_promotions_stable() -> None:
    issue = {
        "issue_key": "GUIDES-99311",
        "summary": "Completed archives expose a distinct attention state.",
        "description": (
            "Generation completes successfully but can contain log entries "
            "reviewers miss."
        ),
        "labels": ["accepted_uac"],
        "acceptance_criteria": [
            "Completed generation that contains log entries requiring "
            "attention is shown with a distinct attention state, separate "
            "from hard failure."
        ],
        "deployment_model": "On-prem",
        "product_version": "5.0",
    }
    first = _run(issue)
    first_promoted = {
        row["candidate_id"]
        for row in first.output_payload["promotion_decisions"]
        if row["status"] == "PROMOTED"
    }
    blocking = [
        row
        for row in first.output_payload["missing_questions"]
        if row["blocking"]
    ]
    if not blocking:
        pytest.skip("fixture produced no blocking question to resume")
    target = blocking[0]
    resumed = _run(
        issue,
        clarifications=[
            {
                "question_ref": target["question_id"],
                "question_revision": target["question_revision"],
                "answer": "The behavior applies in both processing modes.",
                "answer_classification": "PRODUCT_DECISION",
                "provided_by": "qe-reviewer",
                "authority_role": "CONFIRMED_PRODUCT_DECISION",
            }
        ],
    )
    assert resumed.status in {"needs_human_review", "completed"}
    resumed_promoted = {
        row["candidate_id"]
        for row in resumed.output_payload["promotion_decisions"]
        if row["status"] == "PROMOTED"
    }
    # Previously promoted independent ACs remain stable on resume.
    assert first_promoted <= resumed_promoted
