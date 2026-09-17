"""Decision semantics: partial UAC + bounded TBD, decision-quality
clarification, and conflict classification before clarification.

Locked rules under test:

1. An unresolved acceptance-changing decision never suppresses otherwise
   established Acceptance Criteria: established criteria generate and only
   the unresolved decision is represented as a bounded ``(TBD)``.
   Zero-AC BLOCKED is reserved for cases where no safe acceptance contract
   can be formed at all.
2. The human clarification is a concrete product decision (established
   behavior + undecided point + what QE must decide), never the raw Jira
   problem prose.
3. Conflicts are classified before clarification (product-contract /
   implementation / lifecycle-currentness / evidence-quality).  Only
   acceptance-changing unresolved conflicts may produce a TBD; a
   lifecycle/currentness conflict alone never becomes a product
   clarification and never blocks an established behavioral contract.
"""

from __future__ import annotations

from app.core.schemas_canonical_test_plan_runtime import (
    AuthorityClass,
    AuthoritySubject,
    CanonicalBehaviorModel,
    ContractFact,
    ContractFactSet,
    ContractFactType,
    ContractMode,
    CoverageDisposition,
    GateDecision,
    GateStatus,
    GenerationProfile,
    MissingQuestion,
    OpenQuestionClass,
    PromotionStatus,
    QuestionResearchRecord,
    ResearchRequirement,
    ResearchStatus,
    ResearchWorkerResult,
    ResearchWorkerRole,
    ResearchWorkerStatus,
    RuntimeEntryPoint,
    ScopeResolution,
    ConvergenceStatus,
)
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE,
    desired_behavior_claims,
    research_resolved_question_ids,
)
from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME
from app.services.convergence_service import CONVERGENCE_SERVICE


_DESIRED_CLAIM = (
    "Authors get a visible warning indicator on each generated output so "
    "they can see publish warnings without opening the publish log."
)
_RAW_GAP_QUESTION = (
    "Which established product behavior or product decision addresses this "
    "gap: you are not getting the traffic lights in the new editor and must "
    "open the log to notice warnings?"
)
_IMPLEMENTATION_CONFLICT = (
    "Fix comment says WARN lines set the flag; code at HEAD flags only "
    "Error/Fatal."
)
_LIFECYCLE_CONFLICT = (
    "A comment headed 'Fixed by' describes an approach, but the linked "
    "issue status is In Progress and no release establishes it."
)
_EVIDENCE_QUALITY_CONFLICT = (
    "The attachment was truncated and the second image cannot be verified."
)


def _question(text: str, *, blocking: bool = True,
              fact_ids: tuple[str, ...] = ()) -> MissingQuestion:
    return MissingQuestion(
        question=text,
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        target_source_types=[],
        blocking=blocking,
        open_question_class=OpenQuestionClass.USER_ACCEPTANCE_DECISION,
        source_fact_ids=list(fact_ids),
    )


def _finding(claim, role, refs=("ev-1",)):
    return {"claim": claim, "evidence_role": role, "source_refs": list(refs)}


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


def _research_record(question, status=ResearchStatus.ANSWER_FOUND, worker=None):
    request_ids = ["research-request:test-1"]
    if worker is not None:
        # Production binding: the record carries the worker result's
        # research_id in research_request_ids.
        request_ids.append(worker.research_id)
    return QuestionResearchRecord(
        question_id=question.question_id,
        requirement_id="research-requirement:" + "b" * 32,
        research_requirement=ResearchRequirement.DOCUMENTATION,
        research_status=status,
        research_request_ids=request_ids,
        reason="mandated research terminated",
    )


def _facts() -> ContractFactSet:
    return ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            ContractFact(
                fact_type=ContractFactType.PROBLEM_STATEMENT,
                literal=(
                    "You are not getting the traffic lights in the new "
                    "editor outputs view."
                ),
                normalized_value=(
                    "you are not getting the traffic lights in the new "
                    "editor outputs view."
                ),
                source_evidence_ids=["ev-1"],
                source_reference="test:description",
                authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
                authority_class=AuthorityClass.CUSTOMER_REQUEST,
                authoritative=True,
            )
        ],
    )


def _render(facts, scope, questions, dispositions, resolution, promotions,
            gates, convergence, research_resolved=()):
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99222",
        tenant_id="tenant_decision",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    return CANONICAL_REASONING_SERVICE.render_final_plan(
        request,
        facts,
        scope,
        CanonicalBehaviorModel(),
        [],
        questions,
        [],
        dispositions,
        resolution.candidates,
        promotions,
        gates,
        acceptance_resolution=resolution,
        convergence=convergence,
        research_resolved_question_ids=set(research_resolved),
    )


def test_established_acs_survive_with_one_bounded_tbd() -> None:
    """Regression 1: an unresolved acceptance-changing decision suppresses
    only itself; the research-established desired behavior still promotes
    to a proposed AC."""
    facts = _facts()
    scope = ScopeResolution()
    # Production questions are linked to their triggering facts.
    question = _question(
        _RAW_GAP_QUESTION, fact_ids=(facts.facts[0].fact_id,)
    )
    worker = _result(
        question,
        ResearchWorkerStatus.ANSWER_FOUND,
        findings=(_finding(_DESIRED_CLAIM, "DESIRED_BEHAVIOR"),),
        conflicts=(_IMPLEMENTATION_CONFLICT,),
    )
    research = _research_record(question, worker=worker)

    # The desired-behavior release applies.
    assert research_resolved_question_ids([question], [research], [worker]) == {
        question.question_id
    }
    claims = desired_behavior_claims(
        question, {question.question_id: research}, [worker]
    )
    assert claims and claims[0][0] == _DESIRED_CLAIM

    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], scope, [question], [research],
        worker_results=[worker],
    )
    proposed = [
        row
        for row in dispositions
        if row.disposition == CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT
    ]
    assert proposed, "research-established desired behavior must ground a candidate"
    assert all(row.research_derived for row in proposed)
    # The question no longer earns a raw-prose TBD disposition.
    assert not any(
        row.disposition == CoverageDisposition.ACCEPTANCE_TBD
        and question.question_id in row.source_question_ids
        for row in dispositions
    )

    resolution = CANONICAL_REASONING_SERVICE.resolve_acceptance_contract_with_trace(
        facts, dispositions, [question],
        resolved_question_ids={question.question_id},
        research_records=[research],
    )
    gate, promotions = CANONICAL_REASONING_SERVICE.acceptance_promotion_gate(
        resolution.candidates, facts, scope, dispositions
    )
    promoted = [
        row for row in promotions if row.status == PromotionStatus.PROMOTED
    ]
    assert promoted, f"desired-behavior candidate must promote: {promotions}"

    convergence = CONVERGENCE_SERVICE.evaluate([question], [research], [worker])
    assert convergence[0].status == ConvergenceStatus.CONFLICTED
    assert convergence[0].decision

    _plan, rendered = _render(
        facts, scope, [question], dispositions, resolution, promotions,
        [gate], convergence,
        research_resolved={question.question_id},
    )
    # The established contract survived...
    assert "None generated until the blocking decisions" not in rendered
    assert _DESIRED_CLAIM[:60] in rendered
    # ...and only the residual decision is the bounded TBD.
    assert "(TBD)" in rendered
    assert "Decision needed:" in rendered
    # The raw Jira problem prose is never the human question.
    assert _RAW_GAP_QUESTION not in rendered


def test_lifecycle_conflict_alone_produces_no_decision() -> None:
    """Regression 2: a lifecycle/currentness conflict caps shipped/current
    claims but never becomes a product clarification by itself."""
    question = _question("Is the behavior part of the current product?")
    worker = _result(
        question,
        ResearchWorkerStatus.ANSWER_FOUND,
        findings=(
            _finding("Documentation establishes the outputs list.", "EXISTING_BEHAVIOR"),
            _finding("The customer wants the indicator in the editor.", "DESIRED_BEHAVIOR"),
        ),
        conflicts=(_LIFECYCLE_CONFLICT,),
    )
    records = CONVERGENCE_SERVICE.evaluate([question], [], [worker])
    row = records[0]
    assert row.conflict_classes == ["LIFECYCLE_CURRENTNESS"]
    assert row.status != ConvergenceStatus.CONFLICTED
    assert not row.acceptance_changing
    assert row.decision == ""

    # Render level: once research established the desired behavior (the
    # contract stands), the lifecycle-only conflict adds no clarification
    # line - it caps shipped/current claims only.
    facts = _facts()
    scope = ScopeResolution()
    question = _question(
        "Is the behavior part of the current product?",
        fact_ids=(facts.facts[0].fact_id,),
    )
    worker = _result(
        question,
        ResearchWorkerStatus.ANSWER_FOUND,
        findings=(_finding(_DESIRED_CLAIM, "DESIRED_BEHAVIOR"),),
        conflicts=(_LIFECYCLE_CONFLICT,),
    )
    research = _research_record(question, worker=worker)
    records = CONVERGENCE_SERVICE.evaluate([question], [research], [worker])
    row = records[0]
    assert row.conflict_classes == ["LIFECYCLE_CURRENTNESS"]
    assert not row.acceptance_changing
    assert row.decision == ""

    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], scope, [question], [research],
        worker_results=[worker],
    )
    resolution = CANONICAL_REASONING_SERVICE.resolve_acceptance_contract_with_trace(
        facts, dispositions, [question],
        resolved_question_ids={question.question_id},
        research_records=[research],
    )
    gate, promotions = CANONICAL_REASONING_SERVICE.acceptance_promotion_gate(
        resolution.candidates, facts, scope, dispositions
    )
    _plan, rendered = _render(
        facts, scope, [question], dispositions, resolution, promotions,
        [gate], records,
        research_resolved={question.question_id},
    )
    assert _DESIRED_CLAIM[:60] in rendered
    assert _LIFECYCLE_CONFLICT not in rendered
    assert "(TBD)" not in rendered


def test_raw_problem_prose_is_never_the_decision_question() -> None:
    """Regression 3: convergence converts the uncertainty into a concrete
    product decision; the raw Jira problem statement is not emitted."""
    question = _question(_RAW_GAP_QUESTION)
    worker = _result(
        question,
        ResearchWorkerStatus.ANSWER_FOUND,
        findings=(_finding(_DESIRED_CLAIM, "DESIRED_BEHAVIOR"),),
        conflicts=(_IMPLEMENTATION_CONFLICT,),
    )
    records = CONVERGENCE_SERVICE.evaluate([question], [], [worker])
    decision = records[0].decision
    assert decision
    assert "Established by evidence:" in decision
    assert "Undecided:" in decision
    assert "Decision needed:" in decision
    assert "you are not getting the traffic lights" not in decision.casefold()


def test_only_acceptance_changing_conflicts_produce_tbd() -> None:
    """Regression 4: evidence-quality and lifecycle conflicts never produce
    a decision; product-contract, implementation, and unknowns do."""
    question = _question("Which severity drives the indicator?")

    quality = _result(
        question,
        ResearchWorkerStatus.ANSWER_FOUND,
        findings=(_finding("The indicator exists per output.", "EXISTING_BEHAVIOR"),),
        conflicts=(_EVIDENCE_QUALITY_CONFLICT,),
    )
    row = CONVERGENCE_SERVICE.evaluate([question], [], [quality])[0]
    assert row.conflict_classes == ["EVIDENCE_QUALITY"]
    assert row.decision == ""

    contract = _result(
        question,
        ResearchWorkerStatus.ANSWER_FOUND,
        findings=(_finding("The indicator exists per output.", "EXISTING_BEHAVIOR"),),
        conflicts=(
            "The ticket expects the indicator on every successful output; the "
            "stated expectation elsewhere requires it only on failures.",
        ),
    )
    row = CONVERGENCE_SERVICE.evaluate([question], [], [contract])[0]
    assert row.conflict_classes == ["PRODUCT_CONTRACT"]
    assert row.acceptance_changing
    assert row.decision

    implementation = _result(
        question,
        ResearchWorkerStatus.ANSWER_FOUND,
        findings=(_finding("The indicator exists per output.", "EXISTING_BEHAVIOR"),),
        conflicts=(_IMPLEMENTATION_CONFLICT,),
    )
    row = CONVERGENCE_SERVICE.evaluate([question], [], [implementation])[0]
    assert row.conflict_classes == ["IMPLEMENTATION"]
    assert row.acceptance_changing
    assert row.decision

    unknown = _result(
        question,
        ResearchWorkerStatus.NOT_FOUND,
        limitations=["Searched approved docs and code: nothing found."],
    )
    row = CONVERGENCE_SERVICE.evaluate([question], [], [unknown])[0]
    assert row.status == ConvergenceStatus.UNRESOLVED
    assert row.acceptance_changing
    assert row.decision


def test_zero_ac_blocked_only_when_no_safe_contract_exists() -> None:
    """Regression 5: with no established candidate at all the run is still
    blocked; the blocking question falls back to plain text only because no
    convergence exists (research never produced an answer)."""
    question = _question("Which behavior is the acceptance contract?")
    facts = _facts()
    scope = ScopeResolution()
    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], scope, [question]
    )
    resolution = CANONICAL_REASONING_SERVICE.resolve_acceptance_contract_with_trace(
        facts, dispositions, [question]
    )
    assert not resolution.candidates
    gate, promotions = CANONICAL_REASONING_SERVICE.acceptance_promotion_gate(
        resolution.candidates, facts, scope, dispositions
    )
    assert gate.status == GateStatus.BLOCKED
    _plan, rendered = _render(
        facts, scope, [question], dispositions, resolution, promotions,
        [gate], [],
    )
    assert "None generated until the blocking decisions are resolved" in rendered
    assert "(TBD) Which behavior is the acceptance contract?" in rendered
