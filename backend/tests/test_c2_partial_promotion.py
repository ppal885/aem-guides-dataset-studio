"""C2: partial promotion in the AcceptancePromotionGate.

Promoted candidates are delivered even when others are blocked.  A candidate
blocked only by an unresolved product decision is delivered as a TBD
criterion; any other blocker keeps it out of the contract and visible with its
reason.  The gate blocks only when nothing is deliverable, FAILED rules are
unchanged, and a partial result is never postable.
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
    CoverageDispositionRecord,
    GateDecision,
    GateStatus,
    GenerationProfile,
    GenerationResult,
    MissingQuestion,
    OpenQuestionClass,
    PromotionStatus,
    RuntimeEntryPoint,
    ScopeResolution,
)
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE as S,
)
from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME
from app.services.test_plan_runtime_adapters import LEGACY_COMPATIBILITY_PROJECTOR

_PROMOTABLE = [
    "The archive includes a completion marker.",
    "The archive preserves prior manifests.",
    "The export log lists every skipped topic.",
    "The output folder keeps the original file names.",
]
_DECISION_CLAIMS = [
    "The archive records the processing mode.",
    "The export log shows the preset name.",
]


def _fact(
    text: str, fact_type: ContractFactType = ContractFactType.DIRECT_EXPECTED_BEHAVIOR
) -> ContractFact:
    return ContractFact(
        fact_type=fact_type,
        literal=text,
        normalized_value=text.casefold(),
        source_evidence_ids=["ev-1"],
        source_reference="jira:GUIDES-99420:$.description",
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        authority_class=AuthorityClass.CUSTOMER_REQUEST,
        authoritative=True,
    )


def _question(text: str) -> MissingQuestion:
    return MissingQuestion(
        question=text,
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        target_source_types=[],
        blocking=True,
        open_question_class=OpenQuestionClass.USER_ACCEPTANCE_DECISION,
    )


def _disposition(
    fact: ContractFact, question: MissingQuestion | None = None
) -> CoverageDispositionRecord:
    return CoverageDispositionRecord(
        candidate=fact.literal,
        disposition=CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
        source_fact_ids=[fact.fact_id],
        source_question_ids=[question.question_id] if question else [],
        rationale="from ticket",
    )


def _pipeline(promotable: list[str], decided: list[tuple[str, str]], extra=()):
    """Run resolve -> promotion gate -> writer -> renderer on fixtures."""

    facts_list, dispositions, questions = [], [], []
    for text in promotable:
        fact = _fact(text)
        facts_list.append(fact)
        dispositions.append(_disposition(fact))
    for text, question_text in decided:
        fact = _fact(text)
        question = _question(question_text)
        facts_list.append(fact)
        questions.append(question)
        dispositions.append(_disposition(fact, question))
    for fact, question in extra:
        facts_list.append(fact)
        if question is not None:
            questions.append(question)
        dispositions.append(_disposition(fact, question))
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=facts_list,
    )
    scope = ScopeResolution()
    batch = S.resolve_acceptance_contract_with_trace(facts, dispositions, questions)
    gate, decisions = S.acceptance_promotion_gate(
        batch.candidates, facts, scope, dispositions
    )
    written = S.write_acceptance_criteria(
        batch.candidates, decisions, facts, dispositions, questions=questions
    )
    gates = [gate]
    plan, rendered = S.render_final_plan(
        CANONICAL_TEST_PLAN_RUNTIME.build_request(
            jira_key="GUIDES-99420",
            tenant_id="tenant_c2",
            entry_point=RuntimeEntryPoint.PYTHON_API,
            generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
        ),
        facts, scope, CanonicalBehaviorModel(), [], questions, [],
        dispositions, batch.candidates, decisions, gates,
        acceptance_resolution=batch,
        written_acceptance_criteria=written,
    )
    return batch, gate, decisions, written, plan, rendered, gates


def _status(gates: list[GateDecision]) -> str:
    # Mirrors the runtime envelope rule: any FAILED/BLOCKED gate -> blocked.
    blocked = any(g.status in {GateStatus.FAILED, GateStatus.BLOCKED} for g in gates)
    return "blocked" if blocked else "completed"


def _tbd_lines(written) -> list[str]:
    return [
        sub.text
        for criterion in written
        for sub in criterion.sub_points
        if sub.text.startswith("TBD")
    ]


def test_four_promoted_plus_one_open_decision_delivers_five_criteria() -> None:
    _b, gate, decisions, written, plan, rendered, gates = _pipeline(
        _PROMOTABLE,
        [(_DECISION_CLAIMS[0], "Which processing modes does the marker apply under?")],
    )
    assert gate.status == GateStatus.PASSED
    assert sum(d.status == PromotionStatus.PROMOTED for d in decisions) == 4
    assert _status(gates) == "completed"
    assert len(written) == 5
    tbd = [c for c in written if c.sub_points]
    assert len(tbd) == 1
    assert tbd[0].outcome.startswith("The archive records the processing mode")
    assert _tbd_lines(written) == [
        "TBD (product owner decides): Which processing modes does the marker "
        "apply under?"
    ]
    assert "TBD (product owner decides): Which processing modes" in rendered
    assert "Generation status" not in rendered
    assert len(plan.promoted_candidate_ids) == 4


def test_zero_promoted_two_open_decisions_delivers_two_tbd_criteria() -> None:
    _b, gate, decisions, written, _plan, rendered, gates = _pipeline(
        [],
        [
            (_DECISION_CLAIMS[0], "Which processing modes does the marker apply under?"),
            (_DECISION_CLAIMS[1], "Which roles may regenerate the archive?"),
        ],
    )
    assert gate.status == GateStatus.PASSED
    assert all(d.status == PromotionStatus.BLOCKED for d in decisions)
    assert all(
        d.resulting_disposition == CoverageDisposition.ACCEPTANCE_TBD
        for d in decisions
    )
    assert _status(gates) == "completed"
    assert len(written) == 2
    assert len(_tbd_lines(written)) == 2
    assert rendered.count("TBD (product owner decides):") == 2


def test_problem_only_candidate_stays_out_of_contract_with_reason() -> None:
    problem = _fact(
        "There is no easy way to find skipped topics.",
        ContractFactType.PROBLEM_STATEMENT,
    )
    # Linked to an open decision as well: a mixed blocker is never a TBD.
    question = _question("Should skipped topics be listed in the export log?")
    _b, gate, decisions, written, plan, rendered, gates = _pipeline(
        _PROMOTABLE[:1], [], extra=[(problem, question)]
    )
    assert gate.status == GateStatus.PASSED
    assert _status(gates) == "completed"
    assert len(written) == 1
    assert not _tbd_lines(written)
    blocked = [d for d in decisions if d.status != PromotionStatus.PROMOTED]
    assert len(blocked) == 1
    assert blocked[0].resulting_disposition == CoverageDisposition.OPEN_QUESTION
    assert any("PROBLEM_TO_SOLUTION_PROMOTION" in r for r in blocked[0].reasons)
    gaps = next(s for s in plan.sections if s.section_key == "evidence_gaps")
    assert any(
        item.startswith(problem.literal) and "PROBLEM_TO_SOLUTION_PROMOTION" in item
        for item in gaps.items
    )


def test_integrity_failure_still_fails_gate() -> None:
    fact = _fact(_PROMOTABLE[0])
    question = _question("Which processing modes does the marker apply under?")
    decided = _fact(_DECISION_CLAIMS[0])
    dispositions = [_disposition(fact), _disposition(decided, question)]
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[fact, decided],
    )
    batch = S.resolve_acceptance_contract_with_trace(facts, dispositions, [question])
    broken = batch.candidates[0].model_copy(
        update={"source_disposition_ids": ["coverage:missing"], "candidate_id": ""}
    )
    gate, _decisions = S.acceptance_promotion_gate(
        [broken, *batch.candidates[1:]], facts, ScopeResolution(), dispositions
    )
    assert gate.status == GateStatus.FAILED
    assert any("missing source dispositions" in f for f in gate.failures)


def test_insufficient_evidence_mode_still_blocks() -> None:
    fact = _fact(_PROMOTABLE[0])
    dispositions = [_disposition(fact)]
    facts = ContractFactSet(
        contract_mode=ContractMode.INSUFFICIENT_EVIDENCE_FOR_CONTRACT, facts=[fact]
    )
    batch = S.resolve_acceptance_contract_with_trace(facts, dispositions, [])
    gate, _ = S.acceptance_promotion_gate(
        batch.candidates, facts, ScopeResolution(), dispositions
    )
    assert gate.status == GateStatus.BLOCKED


def _result(promotions: list[dict]) -> GenerationResult:
    return GenerationResult.model_construct(
        status="completed",
        validation_status="passed",
        gate_decisions=[
            GateDecision(gate="AcceptancePromotionGate", status=GateStatus.PASSED)
        ],
        structured_plan=None,
        output_payload={"promotion_decisions": promotions},
    )


def test_partial_result_is_never_postable() -> None:
    _b, _gate, decisions, *_ = _pipeline(
        _PROMOTABLE,
        [(_DECISION_CLAIMS[0], "Which processing modes does the marker apply under?")],
    )
    payload = [d.model_dump(mode="json") for d in decisions]
    # Before C2 the same inputs blocked the gate and were not postable.
    assert not LEGACY_COMPATIBILITY_PROJECTOR.is_postable(_result(payload))
    promoted_only = [row for row in payload if row["status"] == "PROMOTED"]
    assert LEGACY_COMPATIBILITY_PROJECTOR.is_postable(_result(promoted_only))
