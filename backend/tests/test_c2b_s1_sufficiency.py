"""C2B-S1: claim-level evidence sufficiency in the canonical runtime.

One production sufficiency decision per acceptance claim - computed by the
canonical runtime, consumed by the AcceptancePromotionGate, projected
losslessly by the C2A adapter, and replayed by the Skill S1 gate.  Legacy
artifacts without the artifact replay as NOT_EVALUABLE, never fabricated.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    AcceptanceCandidate,
    AuthorityClass,
    AuthoritySubject,
    BehaviorChangeClass,
    BehaviorClassificationRecord,
    ClarificationAnswerClass,
    ClarificationStatus,
    ContractFact,
    ContractFactSet,
    ContractFactType,
    ContractMode,
    CoverageDisposition,
    CoverageDispositionRecord,
    CurrentnessState,
    DitaOtProcessingState,
    DomainActivation,
    EvidenceSourceType,
    GenerationProfile,
    HumanClarification,
    IssueDomain,
    MissingQuestion,
    PromotionStatus,
    QuestionResearchRecord,
    ResearchRequirement,
    ResearchStatus,
    RuntimeEntryPoint,
    ScopeResolution,
    SufficiencyStatus,
)
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE,
    assess_claim_sufficiency,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = REPO_ROOT / "skills" / "test-plan-generation" / "scripts"


def _load_skill(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SKILL_SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = _load_skill("canonical_runtime_adapter", "canonical_runtime_adapter.py")
run_gates = _load_skill("run_gates", "run_gates.py")


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _fact(
    text: str,
    *,
    authority: AuthorityClass = AuthorityClass.CUSTOMER_REQUEST,
    authoritative: bool = True,
    evidence: str = "ev:1",
) -> ContractFact:
    return ContractFact(
        fact_type=ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
        literal=text,
        source_evidence_ids=[evidence],
        source_reference="jira:test:$.description",
        authority_class=authority,
        authoritative=authoritative,
    )


def _candidate(statement: str, facts: list[ContractFact], evidence=None):
    return AcceptanceCandidate(
        statement=statement,
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        accepted_human_contract=False,
        source_fact_ids=[row.fact_id for row in facts],
        source_disposition_ids=[],
        evidence_ids=list(evidence if evidence is not None else ["ev:1"]),
        in_scope=True,
        observable=True,
        exact_values_supported=True,
        contradicts_human_contract=False,
        unresolved_decision_ids=[],
    )


def _research(
    question: MissingQuestion,
    status: ResearchStatus,
    requirement: ResearchRequirement = ResearchRequirement.DOCUMENTATION,
) -> QuestionResearchRecord:
    import hashlib

    return QuestionResearchRecord(
        question_id=question.question_id,
        requirement_id="research-requirement:"
        + hashlib.sha256(question.question_id.encode()).hexdigest()[:32],
        research_requirement=requirement,
        research_status=status,
        reason="test-controlled",
    )


def _question(text: str) -> MissingQuestion:
    return MissingQuestion(
        question=text,
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        target_source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
        blocking=False,
    )


def _assess(candidate, facts, *, research=(), classifications=(),
            currentness=None, clarifications=(), question_links=()):
    dispositions = []
    questions_by_disposition = {}
    for q in question_links:
        row = CoverageDispositionRecord(
            candidate=candidate.statement,
            disposition=CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
            source_fact_ids=[f.fact_id for f in facts],
            source_question_ids=[q.question_id],
            rationale="test",
        )
        dispositions.append(row)
    if dispositions:
        candidate.source_disposition_ids = [d.disposition_id for d in dispositions]
    return assess_claim_sufficiency(
        candidate,
        facts_by_id={row.fact_id: row for row in facts},
        dispositions_by_id={row.disposition_id: row for row in dispositions},
        research_by_question={row.question_id: row for row in research},
        classifications_by_disposition={
            row.disposition_id: row for row in classifications
        },
        evidence_currentness=currentness or {},
        admitted_clarifications=list(clarifications),
    )


# ---------------------------------------------------------------------------
# Status rules (spec sections 4-8, 14 hard negatives)
# ---------------------------------------------------------------------------


def test_authoritative_ticket_evidence_is_sufficient() -> None:
    fact = _fact("The new mode keeps the most recent N entries.")
    record = _assess(_candidate("The new mode keeps the most recent N entries.",
                                [fact]), [fact])
    assert record.status == SufficiencyStatus.SUFFICIENT
    assert record.authority_basis == "CUSTOMER_REQUEST"
    assert record.research_completion == "NOT_REQUIRED"


def test_observation_only_evidence_is_insufficient() -> None:
    for authority in (AuthorityClass.TECHNICALLY_INFERRED,
                      AuthorityClass.USER_EXPECTATION,
                      AuthorityClass.HISTORICAL_EXPECTATION):
        fact = _fact("Observed: the entry vanishes after a purge.",
                     authority=authority)
        record = _assess(_candidate("The entry vanishes after a purge.",
                                    [fact]), [fact])
        assert record.status == SufficiencyStatus.INSUFFICIENT, authority
        assert "not" in record.decision_reason or "establishing" in record.decision_reason


def test_no_evidence_is_insufficient() -> None:
    record = _assess(_candidate("A claim with no backing.", []), [])
    assert record.status == SufficiencyStatus.INSUFFICIENT


def test_pending_research_is_insufficient() -> None:
    fact = _fact("The mode keeps N entries.")
    question = _question("What does the mode do?")
    record = _assess(
        _candidate("The mode keeps N entries.", [fact]),
        [fact],
        research=[_research(question, ResearchStatus.PENDING)],
        question_links=[question],
    )
    assert record.status == SufficiencyStatus.INSUFFICIENT
    assert record.research_completion == "PENDING"


def test_not_found_research_caps_partial_never_proves_opposite() -> None:
    fact = _fact("The mode keeps N entries.")
    question = _question("What does the mode do?")
    record = _assess(
        _candidate("The mode keeps N entries.", [fact]),
        [fact],
        research=[_research(question, ResearchStatus.NOT_FOUND)],
        question_links=[question],
    )
    assert record.status == SufficiencyStatus.PARTIAL
    assert record.established_portion
    assert "not proof of the opposite" in record.decision_reason


def test_partial_research_caps_partial() -> None:
    fact = _fact("The mode keeps N entries.")
    question = _question("Scope of the mode?")
    record = _assess(
        _candidate("The mode keeps N entries.", [fact]),
        [fact],
        research=[_research(question, ResearchStatus.PARTIAL)],
        question_links=[question],
    )
    assert record.status == SufficiencyStatus.PARTIAL


def test_conflicted_research_is_conflicted() -> None:
    fact = _fact("The mode keeps N entries.")
    question = _question("What does the mode do?")
    record = _assess(
        _candidate("The mode keeps N entries.", [fact]),
        [fact],
        research=[_research(question, ResearchStatus.CONFLICTED)],
        question_links=[question],
    )
    assert record.status == SufficiencyStatus.CONFLICTED


def test_implementation_only_does_not_establish_desired_behavior() -> None:
    fact = _fact("The handler deletes the row when the flag is set.",
                 authority=AuthorityClass.IMPLEMENTATION_CONFIRMED)
    record = _assess(
        _candidate("The product removes the entry when the option is on.",
                   [fact]),
        [fact],
    )
    assert record.status == SufficiencyStatus.PARTIAL
    assert "implementation evidence" in record.decision_reason


def test_stale_evidence_caps_current_claim() -> None:
    fact = _fact("The mode keeps N entries.", evidence="ev:old")
    record = _assess(
        _candidate("The mode keeps N entries.", [fact], evidence=["ev:old"]),
        [fact],
        currentness={"ev:old": CurrentnessState.SUPERSEDED},
    )
    assert record.status == SufficiencyStatus.PARTIAL
    assert record.currentness == "STALE"


def test_wrong_applicability_is_insufficient() -> None:
    fact = _fact("The mode keeps N entries.")
    candidate = _candidate("The mode keeps N entries.", [fact])
    candidate.in_scope = False
    record = _assess(candidate, [fact])
    assert record.status == SufficiencyStatus.INSUFFICIENT
    assert record.applicability == "WRONG_APPLICABILITY"


def test_sufficiency_does_not_bleed_into_neighboring_claim() -> None:
    fact = _fact("Control A limits retained entries.")
    claim_a = _candidate("Control A limits retained entries.", [fact])
    claim_b = _candidate("Control B changes the log destination.", [])
    assert _assess(claim_a, [fact]).status == SufficiencyStatus.SUFFICIENT
    assert _assess(claim_b, []).status == SufficiencyStatus.INSUFFICIENT


def test_unknown_classification_caps_partial() -> None:
    fact = _fact("The mode keeps N entries.")
    disposition = CoverageDispositionRecord(
        candidate="The mode keeps N entries.",
        disposition=CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
        source_fact_ids=[fact.fact_id],
        rationale="test",
    )
    candidate = _candidate("The mode keeps N entries.", [fact])
    candidate.source_disposition_ids = [disposition.disposition_id]
    record = assess_claim_sufficiency(
        candidate,
        facts_by_id={fact.fact_id: fact},
        dispositions_by_id={disposition.disposition_id: disposition},
        research_by_question={},
        classifications_by_disposition={
            disposition.disposition_id: BehaviorClassificationRecord(
                disposition_id=disposition.disposition_id,
                behavior_class=BehaviorChangeClass.UNKNOWN,
                rationale="unresolved",
            )
        },
        evidence_currentness={},
        admitted_clarifications=[],
    )
    assert record.status == SufficiencyStatus.PARTIAL


# ---------------------------------------------------------------------------
# Clarification integration (spec section 10)
# ---------------------------------------------------------------------------


def _admitted_clarification(question: MissingQuestion, answer: str) -> HumanClarification:
    row = HumanClarification(
        question_ref=question.question_id,
        question_revision=question.question_revision,
        answer=answer,
        answer_classification=ClarificationAnswerClass.EXPECTED_BEHAVIOR,
        provided_by="product-owner",
        authority_role=AuthorityClass.CONFIRMED_PRODUCT_DECISION,
    )
    row.status = ClarificationStatus.ADMITTED
    return row


def test_admitted_clarification_lifts_to_sufficient() -> None:
    fact = _fact("Observed during review.", authority=AuthorityClass.USER_EXPECTATION)
    question = _question("What is the expected behavior?")
    candidate = _candidate("The panel retains its state after a refresh.", [fact])
    baseline = _assess(candidate, [fact], question_links=[question])
    assert baseline.status == SufficiencyStatus.INSUFFICIENT

    lifted = _assess(
        candidate,
        [fact],
        question_links=[question],
        clarifications=[_admitted_clarification(question, "It retains its state.")],
    )
    assert lifted.status == SufficiencyStatus.SUFFICIENT
    assert lifted.authority_basis == "HUMAN_CLARIFICATION"


def test_stale_or_wrong_question_clarification_contributes_nothing() -> None:
    fact = _fact("Observed during review.", authority=AuthorityClass.USER_EXPECTATION)
    question = _question("What is the expected behavior?")
    other = _question("An unrelated question?")
    candidate = _candidate("The panel retains its state after a refresh.", [fact])

    stale = _admitted_clarification(question, "It retains its state.")
    stale.status = ClarificationStatus.STALE
    record = _assess(candidate, [fact], question_links=[question],
                     clarifications=[stale])
    assert record.status == SufficiencyStatus.INSUFFICIENT

    wrong_binding = _admitted_clarification(other, "It retains its state.")
    record = _assess(candidate, [fact], question_links=[question],
                     clarifications=[wrong_binding])
    assert record.status == SufficiencyStatus.INSUFFICIENT


# ---------------------------------------------------------------------------
# Promotion integration (spec section 9)
# ---------------------------------------------------------------------------


def _promote_with_sufficiency(candidate, facts, record):
    dispositions = [
        CoverageDispositionRecord(
            candidate=candidate.statement,
            disposition=CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
            source_fact_ids=[row.fact_id for row in facts],
            rationale="test",
        )
    ]
    candidate.source_disposition_ids = [row.disposition_id for row in dispositions]
    gate, decisions = CANONICAL_REASONING_SERVICE.acceptance_promotion_gate(
        [candidate],
        ContractFactSet(
            contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
            facts=facts,
        ),
        ScopeResolution(),
        dispositions,
        sufficiency=[record],
    )
    return decisions[0]


def test_promotion_gate_consumes_sufficiency() -> None:
    fact = _fact("The mode keeps N entries.")
    candidate = _candidate("The mode keeps N entries.", [fact])
    record = _assess(candidate, [fact])
    assert record.status == SufficiencyStatus.SUFFICIENT
    decision = _promote_with_sufficiency(candidate, [fact], record)
    assert decision.status == PromotionStatus.PROMOTED
    assert decision.sufficiency_ref == record.sufficiency_id

    insufficient = copy.deepcopy(record)
    insufficient.status = SufficiencyStatus.INSUFFICIENT
    insufficient.established_portion = ""
    insufficient.sufficiency_id = ""
    decision = _promote_with_sufficiency(candidate, [fact], insufficient)
    assert decision.status == PromotionStatus.REJECTED
    assert any("INSUFFICIENT" in reason for reason in decision.reasons)

    conflicted = copy.deepcopy(record)
    conflicted.status = SufficiencyStatus.CONFLICTED
    conflicted.sufficiency_id = ""
    decision = _promote_with_sufficiency(candidate, [fact], conflicted)
    assert decision.status == PromotionStatus.REJECTED


def test_partial_promotion_is_bounded() -> None:
    fact = _fact("The mode keeps N entries.")
    candidate = _candidate("The mode keeps N entries.", [fact])
    record = _assess(candidate, [fact])
    partial = copy.deepcopy(record)
    partial.status = SufficiencyStatus.PARTIAL
    partial.established_portion = "keeps N entries"
    partial.sufficiency_id = ""
    decision = _promote_with_sufficiency(candidate, [fact], partial)
    assert decision.status == PromotionStatus.PROMOTED

    # A candidate whose evidence exceeds the portion's bindings cannot
    # promote; bind the record to the expanded candidate's identity.
    expanded = _candidate("The mode keeps N entries.", [fact],
                          evidence=["ev:1", "ev:outside"])
    partial_expanded = copy.deepcopy(partial)
    partial_expanded.claim_ref = expanded.candidate_id
    partial_expanded.sufficiency_id = ""
    decision = _promote_with_sufficiency(expanded, [fact], partial_expanded)
    assert decision.status == PromotionStatus.REJECTED
    assert any("bounded established portion" in reason for reason in decision.reasons)


def test_p1_safety_rules_survive_sufficiency() -> None:
    count_fact = _fact("A count limit keeps only the most recent N entries.")
    logs_fact = _fact("A log-only action removes just the log file.")
    combined = _candidate(
        "When both the count limit and the log-only action are configured "
        "together, a run keeps the last N entries and removes only their log "
        "files.",
        [count_fact, logs_fact],
    )
    record = _assess(combined, [count_fact, logs_fact])
    # Both controls are ticket-evidenced: claim-level sufficiency can be
    # SUFFICIENT while the P1 cross-product rule still blocks the combination.
    assert record.status == SufficiencyStatus.SUFFICIENT
    decision = _promote_with_sufficiency(combined, [count_fact, logs_fact], record)
    assert decision.status == PromotionStatus.REJECTED
    assert any("cross-product" in reason for reason in decision.reasons)


# ---------------------------------------------------------------------------
# Production entry point + C2A replay (spec sections 11, 15, 16, 17)
# ---------------------------------------------------------------------------


def _runtime_result():
    from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME

    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99099",
        tenant_id="tenant_c2b_s1",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    packet = {
        "jira_key": "GUIDES-99099",
        "issue": {
            "issue_key": "GUIDES-99099",
            "summary": "Housekeeping retention options.",
            "description": (
                "The housekeeping job removes output history entries older "
                "than the configured number of days. Provide an option to "
                "keep only the most recent entries per output preset. "
                "Provide an option to remove only the log file and keep the "
                "history entry for audit purposes."
            ),
            "deployment_model": "On-prem",
            "product_version": "5.0",
        },
    }
    return CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request, packet=packet
    )


def test_production_entry_point_carries_sufficiency() -> None:
    result = _runtime_result()
    payload = result.output_payload
    sufficiency = payload["sufficiency"]
    candidates = payload["acceptance_candidates"]
    assert len(sufficiency) == len(candidates)
    by_claim = {row["claim_ref"]: row for row in sufficiency}
    promoted = {
        row["candidate_id"]
        for row in payload["promotion_decisions"]
        if row["status"] == "PROMOTED"
    }
    # The canonical output cannot promote an INSUFFICIENT/CONFLICTED claim.
    for candidate_id in promoted:
        assert by_claim[candidate_id]["status"] in {"SUFFICIENT", "PARTIAL"}
    # Every promotion decision references its sufficiency artifact.
    for row in payload["promotion_decisions"]:
        if row["status"] == "PROMOTED":
            assert row["sufficiency_ref"] == by_claim[row["candidate_id"]][
                "sufficiency_id"
            ]
    # Trace carries the same artifact for audit.
    assert len(result.trace.sufficiency) == len(candidates)


def test_c2a_replay_evaluates_real_sufficiency_artifact() -> None:
    envelope = _runtime_result().model_dump(mode="json")
    manifest, meta = adapter.project_runtime_result(envelope)
    assert "evidence_sufficiency" in manifest
    assert "evidence_sufficiency" not in meta["unavailable_fields"]
    report = run_gates.replay_runtime_projection(manifest)
    statuses = {row["gate"]: row["status"] for row in report["gate_results"]}
    assert statuses["evidence-sufficiency"] in {"PASS", "FAIL"}
    assert statuses["evidence-sufficiency"] != "NOT_EVALUABLE"
    assert report["runtime_promotion_status"] == "AGREES"


def test_legacy_artifact_without_sufficiency_is_not_evaluable() -> None:
    envelope = _runtime_result().model_dump(mode="json")
    del envelope["output_payload"]["sufficiency"]
    manifest, meta = adapter.project_runtime_result(envelope)
    assert "evidence_sufficiency" not in manifest
    assert "evidence_sufficiency" in meta["unavailable_fields"]
    report = run_gates.replay_runtime_projection(manifest)
    statuses = {row["gate"]: row["status"] for row in report["gate_results"]}
    assert statuses["evidence-sufficiency"] == "NOT_EVALUABLE"


def test_deliberate_sufficiency_disagreement_is_reported() -> None:
    envelope = _runtime_result().model_dump(mode="json")
    manifest, _meta = adapter.project_runtime_result(envelope)
    runtime = manifest["_runtime"]
    promoted = next(
        row for row in runtime["promotion_decisions"]
        if row["status"] == "PROMOTED"
    )
    candidate_id = promoted["candidate_id"]
    # Tamper only the projected claim row (the runtime artifact is untouched).
    claim_row = next(
        row
        for row in manifest["evidence_sufficiency"]["claim_assessments"]
        if row["claim_ref"] == candidate_id
    )
    claim_row["sufficiency_status"] = "INSUFFICIENT"
    before_runtime = copy.deepcopy(runtime)
    report = run_gates.replay_runtime_projection(manifest)
    assert report["runtime_promotion_status"] == "DISAGREES"
    assert any(
        row["gate"] == "evidence-sufficiency"
        and row["severity"] == "BLOCKING_POLICY_DIVERGENCE"
        and row["runtime_artifact_ref"] == candidate_id
        for row in report["disagreements"]
    )
    assert manifest["_runtime"] == before_runtime
