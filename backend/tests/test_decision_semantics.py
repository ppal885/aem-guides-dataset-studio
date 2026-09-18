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
    _AC_META_PROSE_RE,
    _existing_claim_text,
    desired_behavior_claims,
    existing_behavior_claims,
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
# A genuine product-authority conflict: two ticket-side product statements
# disagree on the required behavior (no code anchor, no lifecycle content).
_PRODUCT_CONTRACT_CONFLICT = (
    "The ticket description requires the indicator on every successful "
    "output with warnings; an accepted scope note on the same ticket limits "
    "it to failed outputs only."
)
# Code-vs-code contradiction with no ticket authority involved.
_CODE_VS_CODE_CONFLICT = (
    "The admin path at HEAD sets the flag on WARN matches; the public path "
    "at HEAD sets the flag only on Error/Fatal matches."
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
    # PENDING means research never executed: it cannot cite requests/evidence.
    request_ids = [] if status == ResearchStatus.PENDING else ["research-request:test-1"]
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
        conflicts=(_PRODUCT_CONTRACT_CONFLICT,),
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
    # ...and only the residual decision is the bounded TBD - at most one.
    assert "(TBD)" in rendered
    assert "Decision needed:" in rendered
    assert rendered.count("Decision needed:") == 1
    # The raw Jira problem prose is never the human question.
    assert _RAW_GAP_QUESTION not in rendered


def test_lifecycle_conflict_does_not_block_established_acs() -> None:
    """Regression 1+2: admitted documentation + Jira + implementation
    evidence produce ACs even while a lifecycle/currentness conflict
    remains; the lifecycle conflict is not a product-decision blocker."""
    facts = _facts()
    scope = ScopeResolution()
    question = _question(
        _RAW_GAP_QUESTION, fact_ids=(facts.facts[0].fact_id,)
    )
    desired = _result(
        question,
        ResearchWorkerStatus.ANSWER_FOUND,
        findings=(_finding(_DESIRED_CLAIM, "DESIRED_BEHAVIOR"),),
        conflicts=(_LIFECYCLE_CONFLICT,),
    )
    implementation = _result(
        question,
        ResearchWorkerStatus.ANSWER_FOUND,
        findings=(
            _finding(
                "Code at the inspected revision derives the indicator from "
                "the stored flag.",
                "IMPLEMENTATION_EVIDENCE",
            ),
        ),
    )
    research = _research_record(question, worker=desired)
    convergence = CONVERGENCE_SERVICE.evaluate(
        [question], [research], [desired, implementation]
    )
    row = convergence[0]
    assert row.conflict_classes == ["LIFECYCLE_CURRENTNESS"]
    assert not row.acceptance_changing
    assert row.decision == ""

    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], scope, [question], [research],
        worker_results=[desired, implementation],
    )
    resolution = CANONICAL_REASONING_SERVICE.resolve_acceptance_contract_with_trace(
        facts, dispositions, [question],
        resolved_question_ids={question.question_id},
        research_records=[research],
    )
    gate, promotions = CANONICAL_REASONING_SERVICE.acceptance_promotion_gate(
        resolution.candidates, facts, scope, dispositions
    )
    assert any(row.status == PromotionStatus.PROMOTED for row in promotions)

    _plan, rendered = _render(
        facts, scope, [question], dispositions, resolution, promotions,
        [gate], convergence,
        research_resolved={question.question_id},
    )
    assert _DESIRED_CLAIM[:60] in rendered
    assert "(TBD)" not in rendered
    assert "None generated until the blocking decisions" not in rendered


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


def test_s1_lift_only_with_completed_research() -> None:
    """The S1 research lift: a research-derived candidate is sufficient when
    the mandated research terminated with an answer, and stays INSUFFICIENT
    when research is still pending or found nothing - the lift never rescues
    unresearched claims."""
    from app.services.canonical_test_plan_reasoning_service import (
        assess_claim_sufficiency,
    )

    facts = _facts()
    scope = ScopeResolution()
    question = _question(
        _RAW_GAP_QUESTION, fact_ids=(facts.facts[0].fact_id,)
    )
    worker = _result(
        question,
        ResearchWorkerStatus.ANSWER_FOUND,
        findings=(_finding(_DESIRED_CLAIM, "DESIRED_BEHAVIOR"),),
    )
    research = _research_record(question, worker=worker)
    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], scope, [question], [research],
        worker_results=[worker],
    )
    resolution = CANONICAL_REASONING_SERVICE.resolve_acceptance_contract_with_trace(
        facts, dispositions, [question],
        resolved_question_ids={question.question_id},
        research_records=[research],
    )
    assert resolution.candidates
    candidate = resolution.candidates[0]
    facts_by_id = {row.fact_id: row for row in facts.facts}
    dispositions_by_id = {row.disposition_id: row for row in dispositions}

    completed = assess_claim_sufficiency(
        candidate,
        facts_by_id=facts_by_id,
        dispositions_by_id=dispositions_by_id,
        research_by_question={question.question_id: research},
        classifications_by_disposition={},
        evidence_currentness={},
        admitted_clarifications=[],
    )
    assert completed.status.value != "INSUFFICIENT"
    assert completed.authority_basis == "ADMITTED_RESEARCH"

    pending = _research_record(question, status=ResearchStatus.PENDING)
    blocked = assess_claim_sufficiency(
        candidate,
        facts_by_id=facts_by_id,
        dispositions_by_id=dispositions_by_id,
        research_by_question={question.question_id: pending},
        classifications_by_disposition={},
        evidence_currentness={},
        admitted_clarifications=[],
    )
    assert blocked.status.value == "INSUFFICIENT"

    not_found = _research_record(question, status=ResearchStatus.NOT_FOUND)
    not_found_record = not_found
    missing = assess_claim_sufficiency(
        candidate,
        facts_by_id=facts_by_id,
        dispositions_by_id=dispositions_by_id,
        research_by_question={question.question_id: not_found_record},
        classifications_by_disposition={},
        evidence_currentness={},
        admitted_clarifications=[],
    )
    assert missing.status.value == "INSUFFICIENT"


def test_writer_contract_produces_observable_outcome_not_evidence_summary() -> None:
    """Writer contract: the AC is a short observable product outcome - the
    attribution wrapper, the verbatim customer quote, and the meta sentence
    are all stripped, and the wanting frame flips to a requirement modal."""
    from app.services.canonical_test_plan_reasoning_service import (
        _desired_claim_text,
    )

    claim = (
        'The slide text explicitly states the customer position: "The '
        "outputs are very handy on this side, but as you are not getting "
        'the traffic lights for processing, authors would need to be '
        'knowledgeable enough to check the log." The customer states they '
        "want the per-output traffic-light warning indication that the old "
        "UI provided, restored in the XML editor outputs. This wording "
        "matches the Jira issue description verbatim."
    )
    assert _desired_claim_text(claim) == (
        "The per-output traffic-light warning indication that the old UI "
        "provided must be restored in the XML editor outputs."
    )


def test_reviewer_rejects_meta_prose_in_promoted_ac() -> None:
    """Reviewer contract: a promoted AC that still carries meta/evidence
    commentary fails the final UAC instead of passing the gates."""
    facts = _facts()
    scope = ScopeResolution()
    question = _question(
        _RAW_GAP_QUESTION, fact_ids=(facts.facts[0].fact_id,)
    )
    worker = _result(
        question,
        ResearchWorkerStatus.ANSWER_FOUND,
        findings=(
            _finding(
                "Verbatim ask from the ticket: authors cannot see warnings "
                "without opening the log.",
                "DESIRED_BEHAVIOR",
            ),
        ),
    )
    research = _research_record(question, worker=worker)
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
    assert any(row.status == PromotionStatus.PROMOTED for row in promotions)
    gates = [gate]
    _plan, rendered = _render(
        facts, scope, [question], dispositions, resolution, promotions,
        gates, [],
        research_resolved={question.question_id},
    )
    reviewer = [
        row
        for row in gates
        if row.gate.value == "FinalQEPlanRenderer"
        and row.status == GateStatus.FAILED
    ]
    assert reviewer
    assert "Verbatim ask" in rendered
    assert "failed review" in rendered


def test_research_answered_question_produces_no_tbd() -> None:
    """G2: a research-answered question with no acceptance-changing conflict
    converges and never surfaces a TBD - in convergence or in the render."""
    facts = _facts()
    scope = ScopeResolution()
    question = _question(
        "What does the product documentation establish for the outputs list?",
        fact_ids=(facts.facts[0].fact_id,),
    )
    worker = _result(
        question,
        ResearchWorkerStatus.ANSWER_FOUND,
        findings=(
            _finding(
                "Documentation establishes the outputs list with per-run "
                "status colors.",
                "EXISTING_BEHAVIOR",
            ),
        ),
    )
    research = _research_record(question, worker=worker)
    records = CONVERGENCE_SERVICE.evaluate([question], [research], [worker])
    row = records[0]
    assert row.status == ConvergenceStatus.CONVERGED
    assert not row.acceptance_changing
    assert row.decision == ""

    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], scope, [question], [research],
        worker_results=[worker],
    )
    resolution = CANONICAL_REASONING_SERVICE.resolve_acceptance_contract_with_trace(
        facts, dispositions, [question], research_records=[research]
    )
    gate, promotions = CANONICAL_REASONING_SERVICE.acceptance_promotion_gate(
        resolution.candidates, facts, scope, dispositions
    )
    _plan, rendered = _render(
        facts, scope, [question], dispositions, resolution, promotions,
        [gate], records,
    )
    assert question.question not in rendered
    assert "(TBD)" not in rendered


def test_non_material_unknown_after_an_answer_produces_no_tbd() -> None:
    """G2: when research established the answer, a remaining NOT_FOUND on a
    secondary route is an evidence limitation, not a product decision."""
    question = _question("Which documented behavior covers the outputs list?")
    answered = _result(
        question,
        ResearchWorkerStatus.ANSWER_FOUND,
        findings=(
            _finding(
                "Documentation establishes the outputs list status behavior.",
                "EXISTING_BEHAVIOR",
            ),
        ),
    )
    blind_route = _result(
        question,
        ResearchWorkerStatus.NOT_FOUND,
        limitations=["The attachment does not address the claim."],
    )
    research = _research_record(question, worker=answered)
    records = CONVERGENCE_SERVICE.evaluate(
        [question], [research], [answered, blind_route]
    )
    row = records[0]
    assert row.acceptance_changing_unknowns  # the limitation stays visible
    assert row.status == ConvergenceStatus.CONVERGED_WITH_LIMITS
    assert not row.acceptance_changing
    assert row.decision == ""


def test_raw_problem_prose_is_never_the_decision_question() -> None:
    """Regression 3: convergence converts the uncertainty into a concrete
    product decision; the raw Jira problem statement is not emitted."""
    question = _question(_RAW_GAP_QUESTION)
    worker = _result(
        question,
        ResearchWorkerStatus.ANSWER_FOUND,
        findings=(_finding(_DESIRED_CLAIM, "DESIRED_BEHAVIOR"),),
        conflicts=(_PRODUCT_CONTRACT_CONFLICT,),
    )
    records = CONVERGENCE_SERVICE.evaluate([question], [], [worker])
    decision = records[0].decision
    assert decision
    assert "Established by evidence:" in decision
    assert "Undecided:" in decision
    assert "Decision needed:" in decision
    assert "you are not getting the traffic lights" not in decision.casefold()


def test_requirement_implementation_mismatch_is_not_a_product_decision() -> None:
    """The fix comment establishes WARN scanning; the inspected code sets the
    flag only for Error/Fatal.  That is a requirement-vs-implementation
    mismatch (a Developer finding), never a QE product decision - the
    established requirement continues into the contract."""
    question = _question("Which log severities drive the indicator?")
    worker = _result(
        question,
        ResearchWorkerStatus.ANSWER_FOUND,
        findings=(_finding(_DESIRED_CLAIM, "DESIRED_BEHAVIOR"),),
        conflicts=(_IMPLEMENTATION_CONFLICT,),
    )
    row = CONVERGENCE_SERVICE.evaluate([question], [], [worker])[0]
    assert row.conflict_classes == ["REQUIREMENT_IMPLEMENTATION_MISMATCH"]
    assert row.status == ConvergenceStatus.CONVERGED_WITH_LIMITS
    assert not row.acceptance_changing
    assert row.decision == ""
    assert row.implementation_findings
    assert "WARN" in row.implementation_findings[0]


def test_only_acceptance_changing_conflicts_produce_tbd() -> None:
    """Regression 4: only product-authority conflicts and unresolved
    unknowns may produce a TBD; implementation-lane, lifecycle, and
    evidence-quality conflicts never do."""
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

    code_vs_code = _result(
        question,
        ResearchWorkerStatus.ANSWER_FOUND,
        findings=(_finding("The indicator exists per output.", "EXISTING_BEHAVIOR"),),
        conflicts=(_CODE_VS_CODE_CONFLICT,),
    )
    row = CONVERGENCE_SERVICE.evaluate([question], [], [code_vs_code])[0]
    assert row.conflict_classes == ["IMPLEMENTATION"]
    assert not row.acceptance_changing
    assert row.decision == ""
    assert row.implementation_findings

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


# ---------------------------------------------------------------------------
# C-root: documented existing behavior must reach the acceptance lane.
#
# Locked rule, in two halves:
#   1. Documented existing behavior GROUNDS a PROPOSED baseline candidate, so
#      documentation research is never dropped from the acceptance lane.
#   2. It does NOT RESOLVE the question.  Documentation records what the
#      product does today; the decision about what it should do stays open,
#      so the bounded ACCEPTANCE_TBD is still emitted alongside.
#
# Collapsing the two halves is the regression these tests exist to catch: if
# documented behavior resolved the question, a finding that explicitly states
# "the documentation does not specify an ordering rule" would silently close
# the very decision it failed to answer.
# ---------------------------------------------------------------------------

_EXISTING_CLAIM = (
    "Documentation establishes that Output History shows a warning status "
    "for an output that completed with publish warnings."
)
_EXISTING_OUTCOME = (
    "Output History shows a warning status for an output that completed "
    "with publish warnings."
)


def _existing_case(claim=_EXISTING_CLAIM, role="EXISTING_BEHAVIOR"):
    facts = _facts()
    question = _question(_RAW_GAP_QUESTION, fact_ids=(facts.facts[0].fact_id,))
    worker = _result(
        question,
        ResearchWorkerStatus.ANSWER_FOUND,
        findings=(_finding(claim, role),),
    )
    return facts, question, worker, _research_record(question, worker=worker)


def test_documented_existing_behavior_grounds_a_proposed_candidate() -> None:
    """C-root: an EXISTING_BEHAVIOR finding from documentation research must
    ground a PROPOSED candidate, never be silently dropped."""
    facts, question, worker, research = _existing_case()

    claims = existing_behavior_claims(
        question, {question.question_id: research}, [worker]
    )
    assert claims and claims[0][0] == _EXISTING_CLAIM

    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], ScopeResolution(), [question], [research],
        worker_results=[worker],
    )
    proposed = [
        row
        for row in dispositions
        if row.disposition == CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT
    ]
    assert proposed, "documented existing behavior must ground a candidate"
    row = proposed[0]
    assert row.research_derived
    # The researcher's documentation framing is stripped; the observable
    # product outcome survives.
    assert row.candidate == _EXISTING_OUTCOME
    # Provenance is carried so the behavior-classification lane can tag it.
    assert row.evidence_ids == ["ev-1"]
    assert "Documented existing behavior" in row.rationale


def test_documented_existing_behavior_never_resolves_the_question() -> None:
    """The decision half of the locked rule: documentation is the baseline,
    not the decision.  The question stays unresolved and keeps its bounded
    TBD, so the Human still owns the acceptance call."""
    facts, question, worker, research = _existing_case()

    assert not research_resolved_question_ids([question], [research], [worker])

    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], ScopeResolution(), [question], [research],
        worker_results=[worker],
    )
    linked = [
        row
        for row in dispositions
        if question.question_id in row.source_question_ids
    ]
    assert any(
        row.disposition == CoverageDisposition.ACCEPTANCE_TBD for row in linked
    ), "documented behavior must not suppress the open acceptance decision"
    assert any(
        row.disposition == CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT
        for row in linked
    ), "the documented baseline must still be carried alongside the TBD"


def test_documentation_that_disclaims_an_answer_grounds_nothing() -> None:
    """A finding whose substance is what the documentation does NOT establish
    is the absence of a contract.  It must never become an AC - that is the
    exact shape that would otherwise close a decision it never answered."""
    facts, question, worker, research = _existing_case(
        claim=(
            "Documentation establishes the Output History list; it does not "
            "specify any warning status for completed outputs."
        ),
    )
    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], ScopeResolution(), [question], [research],
        worker_results=[worker],
    )
    for row in dispositions:
        if row.disposition == CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT:
            assert "does not specify" not in row.candidate
    assert any(
        row.disposition == CoverageDisposition.ACCEPTANCE_TBD
        for row in dispositions
        if question.question_id in row.source_question_ids
    )


def test_documented_behavior_unrelated_to_the_question_is_not_promoted() -> None:
    """Documentation research returns everything it found about a feature
    area.  A finding that shares no term with the question answered a
    different question, so it must not enter the acceptance lane."""
    facts, question, worker, research = _existing_case(
        claim=(
            "Documentation establishes that the baseline comparison panel "
            "supports side-by-side revision selection."
        ),
    )
    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], ScopeResolution(), [question], [research],
        worker_results=[worker],
    )
    assert not [
        row
        for row in dispositions
        if row.disposition == CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT
    ]


def test_existing_behavior_candidate_clears_the_reviewer_meta_prose_gate() -> None:
    """The Reviewer rejects "documentation establishes ..." as meta prose, so
    the framing must be stripped before the candidate is emitted - the gate
    itself is never weakened."""
    # The gate still rejects the raw finding.
    assert _AC_META_PROSE_RE.search(_EXISTING_CLAIM)
    # The normalized candidate passes it.
    assert not _AC_META_PROSE_RE.search(_existing_claim_text(_EXISTING_CLAIM))

    facts, question, worker, research = _existing_case()
    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], ScopeResolution(), [question], [research],
        worker_results=[worker],
    )
    for row in dispositions:
        if row.disposition == CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT:
            assert not _AC_META_PROSE_RE.search(row.candidate)


def test_observed_behavior_alone_never_grounds_a_candidate() -> None:
    """Guard: observation is not a requirement.  Widening the admitted roles
    to documentation must not let a QE run become an acceptance contract."""
    facts, question, worker, research = _existing_case(
        claim="The indicator did not appear on the run under test.",
        role="OBSERVED_BEHAVIOR",
    )
    assert not research_resolved_question_ids([question], [research], [worker])
    assert not existing_behavior_claims(
        question, {question.question_id: research}, [worker]
    )
    assert not desired_behavior_claims(
        question, {question.question_id: research}, [worker]
    )

    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], ScopeResolution(), [question], [research],
        worker_results=[worker],
    )
    assert not [
        row
        for row in dispositions
        if row.disposition == CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT
    ]


def test_terminated_research_without_establishing_claim_stays_acceptance_lane() -> None:
    """C-root residual: research that terminated ANSWER_FOUND but established
    no acceptance-bearing claim is a bounded TBD, never a generic open
    question that carries no research at all."""
    facts, question, worker, research = _existing_case(
        claim="The feature area is covered by the publishing guide.",
        role="SUPPORTING_CONTEXT",
    )
    assert not research_resolved_question_ids([question], [research], [worker])

    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], ScopeResolution(), [question], [research],
        worker_results=[worker],
    )
    linked = [
        row
        for row in dispositions
        if question.question_id in row.source_question_ids
    ]
    assert linked, "a terminated blocking question must stay in coverage"
    assert any(
        row.disposition == CoverageDisposition.ACCEPTANCE_TBD for row in linked
    )


def test_lanes_stay_consistent_on_documented_existing_behavior() -> None:
    """convergence_service caps the *unknown* when documentation was found
    (``answered = EXISTING or DESIRED``).  The reasoning lane must then carry
    that documentation as a candidate - otherwise the research is suppressed
    in one lane and unrepresented in the other, which is the C-root drop."""
    facts, question, worker, research = _existing_case()

    # Convergence lane: documented existing behavior counts as answered.
    row = CONVERGENCE_SERVICE.evaluate([question], [research], [worker])[0]
    assert not row.acceptance_changing

    # Reasoning lane: the same finding grounds a candidate.
    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], ScopeResolution(), [question], [research],
        worker_results=[worker],
    )
    assert [
        r
        for r in dispositions
        if r.disposition == CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT
    ]
