"""Convergence stage: the virtual refinement team (PM / Developer / QE
perspectives over collected research), plus evidence-bearing conversational
clarification in the blocked render.  Advisory only - no evidence authority
changes."""

from __future__ import annotations

from app.core.schemas_canonical_test_plan_runtime import (
    AuthorityClass,
    AuthoritySubject,
    ContractMode,
    EvidenceSourceType,
    GateStatus,
    GateDecision,
    MissingQuestion,
    OpenQuestionClass,
    QuestionResearchRecord,
    ResearchRequirement,
    ResearchStatus,
    ResearchWorkerResult,
    ResearchWorkerRole,
    ResearchWorkerStatus,
    ConvergenceStatus,
)
from app.services.convergence_service import CONVERGENCE_SERVICE


def _question(text: str, *, blocking: bool = True) -> MissingQuestion:
    return MissingQuestion(
        question=text,
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        target_source_types=[],
        blocking=blocking,
        open_question_class=OpenQuestionClass.USER_ACCEPTANCE_DECISION,
    )


def _result(question, status, findings=(), conflicts=(), limitations=()):
    from app.core.schemas_canonical_test_plan_runtime import ResearchFinding

    return ResearchWorkerResult(
        worker_role=ResearchWorkerRole.DOC_RESEARCHER,
        question_id=question.question_id,
        status=status,
        findings=[ResearchFinding(**f) for f in findings],
        limitations=list(limitations),
        conflicts=list(conflicts),
    )


def _finding(claim, role):
    return {"claim": claim, "evidence_role": role, "source_refs": []}


def test_convergence_views_split_by_evidence_role_and_converge() -> None:
    question = _question("Does the mode change the behavior?")
    result = _result(
        question,
        ResearchWorkerStatus.ANSWER_FOUND,
        findings=(
            _finding("The product intends a visible warning indicator.", "REQUIREMENT_CLARIFICATION"),
            _finding("Code computes a visible warning indicator per run.", "IMPLEMENTATION_EVIDENCE"),
            _finding("The slide shows a visible warning indicator dot.", "OBSERVED_BEHAVIOR"),
            _finding("Documentation establishes a visible warning indicator.", "EXISTING_BEHAVIOR"),
        ),
    )
    records = CONVERGENCE_SERVICE.evaluate([question], [], [result])
    assert len(records) == 1
    row = records[0]
    assert row.status == ConvergenceStatus.CONVERGED
    assert row.pm_view and row.dev_view and row.qe_view
    # Documented existing behavior sits with the product/PM view.
    assert any("Documentation establishes" in claim for claim in row.pm_view)
    assert row.agreements  # overlapping claims across views
    assert row.convergence_id.startswith("convergence:")


def test_convergence_conflicts_and_unknowns_are_explicit() -> None:
    question = _question("Which behavior applies?")
    conflicted = _result(
        question,
        ResearchWorkerStatus.CONFLICTED,
        findings=(_finding("Comment claims WARN lines set the flag.", "REQUIREMENT_CLARIFICATION"),),
        conflicts=("Comment says WARN; code at HEAD only flags Error/Fatal.",),
    )
    records = CONVERGENCE_SERVICE.evaluate([question], [], [conflicted])
    assert records[0].status == ConvergenceStatus.CONFLICTED
    assert "WARN" in records[0].conflicts[0]

    missing = _result(question, ResearchWorkerStatus.NO_RELEVANT_EVIDENCE,
                      limitations=["Searched approved docs: nothing relevant."])
    records = CONVERGENCE_SERVICE.evaluate([question], [], [missing])
    assert records[0].status == ConvergenceStatus.UNRESOLVED
    assert records[0].acceptance_changing_unknowns
    assert "NO_RELEVANT_EVIDENCE" in records[0].acceptance_changing_unknowns[0]

    partial = _result(question, ResearchWorkerStatus.PARTIAL,
                      findings=(_finding("Only part is established.", "REQUIREMENT_CLARIFICATION"),))
    records = CONVERGENCE_SERVICE.evaluate([question], [], [partial])
    assert records[0].status == ConvergenceStatus.CONVERGED_WITH_LIMITS


def test_convergence_uses_research_record_when_no_worker_rows() -> None:
    question = _question("Unanswered question?")
    research = QuestionResearchRecord(
        question_id=question.question_id,
        requirement_id="research-requirement:" + "a" * 32,
        research_requirement=ResearchRequirement.DOCUMENTATION,
        research_status=ResearchStatus.NOT_FOUND,
        reason="Mandated research executed and found no answer.",
    )
    records = CONVERGENCE_SERVICE.evaluate([question], [research], [])
    assert records[0].status == ConvergenceStatus.UNRESOLVED
    assert records[0].acceptance_changing_unknowns


def test_blocked_render_carries_evidence_and_conflict_for_decisions() -> None:
    from app.core.schemas_canonical_test_plan_runtime import (
        ContractFact,
        ContractFactSet,
        ContractFactType,
        ScopeResolution,
        CanonicalBehaviorModel,
    )
    from app.services.canonical_test_plan_reasoning_service import (
        CANONICAL_REASONING_SERVICE,
    )
    from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME
    from app.core.schemas_canonical_test_plan_runtime import (
        GenerationProfile,
        RuntimeEntryPoint,
    )

    question = _question("Which product decision covers the warning indicator gap?")
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            ContractFact(
                fact_type=ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
                literal="The export job writes a completion marker.",
                normalized_value="the export job writes a completion marker.",
                source_evidence_ids=["ev-1"],
                source_reference="test:description",
                authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
                authority_class=AuthorityClass.CUSTOMER_REQUEST,
                authoritative=True,
            )
        ],
    )
    scope = ScopeResolution()
    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], scope, [question]
    )
    resolution = CANONICAL_REASONING_SERVICE.resolve_acceptance_contract_with_trace(
        facts, dispositions, [question]
    )
    _gate, promotions = CANONICAL_REASONING_SERVICE.acceptance_promotion_gate(
        resolution.candidates, facts, scope, dispositions
    )
    # Build the convergence record through the service so conflict
    # classification and the decision formulation are the real ones.
    result = _result(
        question,
        ResearchWorkerStatus.CONFLICTED,
        findings=(
            _finding(
                "The 2026-08-15 Jira comment describes a log-scan indicator.",
                "REQUIREMENT_CLARIFICATION",
            ),
        ),
        conflicts=("Fix comment says WARN lines; code at HEAD flags only Error/Fatal.",),
    )
    convergence = CONVERGENCE_SERVICE.evaluate([question], [], [result])
    assert convergence[0].decision  # acceptance-changing conflict
    blocked_gate = GateDecision(
        gate="AcceptancePromotionGate",
        status=GateStatus.BLOCKED,
        failures=["No supported acceptance-contract candidate is available."],
    )
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99111",
        tenant_id="tenant_conv",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    _plan, rendered = CANONICAL_REASONING_SERVICE.render_final_plan(
        request, facts, scope, CanonicalBehaviorModel(), [], [question],
        [], dispositions, resolution.candidates, promotions, [blocked_gate],
        acceptance_resolution=resolution,
        convergence=convergence,
    )
    # Decision-quality clarification: the raw question prose is never the
    # human question; the decision form carries established + undecided.
    assert "Decision needed:" in rendered
    assert "Established by evidence:" in rendered
    assert "Which product decision covers the warning indicator gap?" not in rendered
