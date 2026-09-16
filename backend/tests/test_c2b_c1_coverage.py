"""C2B-C1: canonical Coverage Decision convergence.

One canonical production coverage artifact: the CoverageDispositionRecord now
carries priority (P0/P1/SUPPORTING/EXCLUDED), coverage_class
(ACCEPTANCE/QE_REGRESSION/INVESTIGATION), contract_type
(POSITIVE/NEGATIVE/PRESERVATION), and the sufficiency link - derived once in
the canonical classifier, consumed by the AcceptancePromotionGate, projected
losslessly for Skill C1 replay.  No second coverage algorithm.

SUFFICIENT evidence does not automatically mean ACCEPTANCE coverage.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    AcceptanceCandidate,
    ApplicabilityState,
    AuthorityClass,
    AuthoritySubject,
    BehaviorHypothesis,
    ClosureDimensionResult,
    ClosureDisposition,
    ContractFact,
    ContractFactSet,
    ContractFactType,
    ContractMode,
    CoverageDisposition,
    CoverageDispositionRecord,
    EvidenceSourceType,
    GenerationProfile,
    HypothesisState,
    MissingQuestion,
    PromotionStatus,
    RuntimeEntryPoint,
    ScopeResolution,
    SemanticDimension,
    SufficiencyStatus,
)
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE,
    _derive_c1,
    _derive_contract_type,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = REPO_ROOT / "skills" / "test-plan-generation" / "scripts"


def _load_skill(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SKILL_SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = _load_skill("cra_c1", "canonical_runtime_adapter.py")
run_gates = _load_skill("run_gates_c1", "run_gates.py")


def _fact(
    text: str,
    fact_type: ContractFactType = ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
    *,
    authority: AuthorityClass = AuthorityClass.CUSTOMER_REQUEST,
) -> ContractFact:
    return ContractFact(
        fact_type=fact_type,
        literal=text,
        source_evidence_ids=["ev:1"],
        source_reference="jira:test:$.description",
        authority_class=authority,
        authoritative=True,
    )


# ---------------------------------------------------------------------------
# Derivation + structural validation (spec sections 3-5, 21)
# ---------------------------------------------------------------------------


def test_derivation_mapping_is_exact() -> None:
    assert _derive_c1(CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
                      has_direct_evidence=True)[:2] == ("ACCEPTANCE", "P0")
    assert _derive_c1(CoverageDisposition.SEMANTIC_REGRESSION,
                      has_direct_evidence=True)[:2] == ("QE_REGRESSION", "P1")
    assert _derive_c1(CoverageDisposition.SEMANTIC_REGRESSION,
                      has_direct_evidence=False)[:2] == (
        "QE_REGRESSION",
        "SUPPORTING",
    )
    assert _derive_c1(CoverageDisposition.IMPLEMENTATION_ORACLE,
                      has_direct_evidence=True)[:2] == (
        "INVESTIGATION",
        "SUPPORTING",
    )
    assert _derive_c1(CoverageDisposition.KNOWN_LIMITATION,
                      has_direct_evidence=True)[:2] == (
        "INVESTIGATION",
        "SUPPORTING",
    )
    assert _derive_c1(CoverageDisposition.OUT_OF_SCOPE,
                      has_direct_evidence=True)[:2] == ("", "EXCLUDED")
    assert _derive_c1(CoverageDisposition.OPEN_QUESTION,
                      has_direct_evidence=True)[:2] == (
        "INVESTIGATION",
        "SUPPORTING",
    )
    assert _derive_contract_type(
        CoverageDisposition.NEGATIVE_BOUNDARY, set()
    ) == "NEGATIVE"
    assert _derive_contract_type(
        CoverageDisposition.CONFIGURATION_VARIANT,
        {ContractFactType.COMPATIBILITY_REQUIREMENTS},
    ) == "PRESERVATION"
    assert _derive_contract_type(
        CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
        {ContractFactType.DIRECT_EXPECTED_BEHAVIOR},
    ) == "POSITIVE"


def test_structural_validation_of_canonical_coverage() -> None:
    with pytest.raises(ValueError, match="acceptance-contract"):
        CoverageDispositionRecord(
            candidate="x",
            disposition=CoverageDisposition.SEMANTIC_REGRESSION,
            rationale="r",
            coverage_class="ACCEPTANCE",
            priority="P0",
            contract_type="POSITIVE",
            acceptance_impact="i",
        )
    with pytest.raises(ValueError, match="QE_REGRESSION"):
        CoverageDispositionRecord(
            candidate="x",
            disposition=CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
            rationale="r",
            coverage_class="QE_REGRESSION",
            priority="P1",
            contract_type="POSITIVE",
            acceptance_impact="i",
        )
    with pytest.raises(ValueError, match="INVESTIGATION"):
        CoverageDispositionRecord(
            candidate="x",
            disposition=CoverageDisposition.NFR_COVERAGE,
            rationale="r",
            coverage_class="INVESTIGATION",
            priority="SUPPORTING",
            contract_type="POSITIVE",
            acceptance_impact="i",
        )
    with pytest.raises(ValueError, match="P0"):
        CoverageDispositionRecord(
            candidate="x",
            disposition=CoverageDisposition.SEMANTIC_REGRESSION,
            rationale="r",
            coverage_class="QE_REGRESSION",
            priority="P0",
            contract_type="POSITIVE",
            acceptance_impact="i",
        )
    with pytest.raises(ValueError, match="EXCLUDED"):
        CoverageDispositionRecord(
            candidate="x",
            disposition=CoverageDisposition.KNOWN_LIMITATION,
            rationale="r",
            coverage_class="QE_REGRESSION",
            priority="EXCLUDED",
            contract_type="POSITIVE",
            acceptance_impact="i",
        )
    # Legacy unclassed records remain valid and readable.
    legacy = CoverageDispositionRecord(
        candidate="x",
        disposition=CoverageDisposition.SEMANTIC_REGRESSION,
        rationale="r",
    )
    assert legacy.coverage_class == "" and legacy.priority == ""


def test_fact_backed_classification_stamps_c1_fields() -> None:
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            _fact("The new mode keeps the most recent N entries."),
            _fact(
                "Existing configurations remain unchanged after the upgrade.",
                ContractFactType.COMPATIBILITY_REQUIREMENTS,
            ),
            _fact(
                "The purge must never delete generated outputs.",
                ContractFactType.EXPLICIT_NEGATIVE_REQUIREMENTS,
            ),
        ],
    )
    rows = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], ScopeResolution(), []
    )
    by_fact = {row.source_fact_ids[0]: row for row in rows}
    fid = {f.literal: f.fact_id for f in facts.facts}
    primary = by_fact[fid["The new mode keeps the most recent N entries."]]
    assert (primary.coverage_class, primary.priority, primary.contract_type) == (
        "ACCEPTANCE",
        "P0",
        "POSITIVE",
    )
    compat = by_fact[fid["Existing configurations remain unchanged after the upgrade."]]
    assert (compat.coverage_class, compat.priority, compat.contract_type) == (
        "QE_REGRESSION",
        "P1",
        "PRESERVATION",
    )
    negative = by_fact[fid["The purge must never delete generated outputs."]]
    assert (negative.coverage_class, negative.contract_type) == (
        "QE_REGRESSION",
        "NEGATIVE",
    )
    for row in rows:
        assert row.revision


# ---------------------------------------------------------------------------
# Promotion gate integration (spec section 12)
# ---------------------------------------------------------------------------


def _candidate_for(disposition: CoverageDispositionRecord) -> AcceptanceCandidate:
    return AcceptanceCandidate(
        statement=disposition.candidate,
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        accepted_human_contract=False,
        source_fact_ids=list(disposition.source_fact_ids),
        source_disposition_ids=[disposition.disposition_id],
        evidence_ids=["ev:1"],
        in_scope=True,
        observable=True,
        exact_values_supported=True,
        contradicts_human_contract=False,
        unresolved_decision_ids=[],
    )


def test_qe_regression_and_investigation_never_promote() -> None:
    fact = _fact("The new mode keeps the most recent N entries.")
    for klass, disposition in (
        ("QE_REGRESSION", CoverageDisposition.SEMANTIC_REGRESSION),
        ("INVESTIGATION", CoverageDisposition.IMPLEMENTATION_ORACLE),
    ):
        row = CoverageDispositionRecord(
            candidate=fact.literal,
            disposition=disposition,
            source_fact_ids=[fact.fact_id],
            rationale="r",
            coverage_class=klass,
            priority="P1" if klass == "QE_REGRESSION" else "SUPPORTING",
            contract_type="POSITIVE",
            acceptance_impact="i",
        )
        candidate = _candidate_for(row)
        gate, decisions = CANONICAL_REASONING_SERVICE.acceptance_promotion_gate(
            [candidate],
            ContractFactSet(
                contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
                facts=[fact],
            ),
            ScopeResolution(),
            [row],
        )
        (decision,) = decisions
        assert decision.status == PromotionStatus.REJECTED, klass
        assert any("ACCEPTANCE-class" in reason for reason in decision.reasons)


# ---------------------------------------------------------------------------
# Unfamiliar fixture (spec section 18)
# ---------------------------------------------------------------------------


def test_unfamiliar_fixture_classification_matrix() -> None:
    primary = _fact("The export job must write a completion marker.")
    existing = _fact(
        "Existing exports remain unchanged after the upgrade.",
        ContractFactType.COMPATIBILITY_REQUIREMENTS,
    )
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[primary, existing],
    )
    question = MissingQuestion(
        question="Which component drops the marker?",
        dimension=SemanticDimension.DOWNSTREAM_PROCESSOR,
        authority_subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        target_source_types=[EvidenceSourceType.CURRENT_CODE],
        blocking=False,
    )
    hypothesis = BehaviorHypothesis(
        statement="The marker write happens in the shared writer path.",
        state=HypothesisState.CONFIRMED,
        derived_from_question_id=question.question_id,
        supporting_evidence_ids=["ev:code"],
    )
    closure_row = ClosureDimensionResult(
        entity="export job lifecycle",
        dimension=SemanticDimension.LIFECYCLE,
        applicability=ApplicabilityState.APPLICABLE,
        disposition=ClosureDisposition.COVERED,
        rationale="Covered by inspected evidence.",
    )
    rows = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [closure_row], [], [hypothesis], ScopeResolution(), [question]
    )
    by_disposition = {row.candidate: row for row in rows}

    primary_row = by_disposition[primary.literal]
    assert (primary_row.coverage_class, primary_row.priority) == (
        "ACCEPTANCE",
        "P0",
    )
    existing_row = by_disposition[existing.literal]
    assert (existing_row.coverage_class, existing_row.priority,
            existing_row.contract_type) == (
        "QE_REGRESSION",
        "P1",
        "PRESERVATION",
    )
    root_cause = by_disposition[hypothesis.statement]
    assert (root_cause.coverage_class, root_cause.priority) == (
        "INVESTIGATION",
        "SUPPORTING",
    )
    adjacent = by_disposition[closure_row.entity if closure_row.entity in by_disposition else next(
        key for key in by_disposition if key.startswith("LIFECYCLE")
    )]
    assert adjacent.priority == "SUPPORTING"


# ---------------------------------------------------------------------------
# Production entry point + media-label shape (spec sections 16, 21)
# ---------------------------------------------------------------------------


def _runtime_run(description: str):
    from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME

    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99102",
        tenant_id="tenant_c2b_c1",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    packet = {
        "jira_key": "GUIDES-99102",
        "issue": {
            "issue_key": "GUIDES-99102",
            "summary": "Hard to manage version labels on rich assets",
            "description": description,
            "deployment_model": "On-prem",
            "product_version": "5.0",
        },
    }
    return CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request, packet=packet
    )


def test_production_media_label_coverage_trace() -> None:
    result = _runtime_run(
        "There is no easy way to manage version labels on rich assets. "
        "The upload dialog does not have an option to assign a label."
    )
    rows = result.output_payload["coverage_dispositions"]
    assert rows
    # Every classed row satisfies the structural contract.
    for row in rows:
        if row["coverage_class"]:
            assert row["priority"]
            assert row["contract_type"]
            assert row["revision"]
    # The established problem stays investigation context, never acceptance:
    # KNOWN_LIMITATION maps to INVESTIGATION/SUPPORTING and can never promote.
    problem_rows = [
        row
        for row in rows
        if row["disposition"] == "KNOWN_LIMITATION"
    ]
    assert problem_rows
    assert all(
        (row["coverage_class"], row["priority"])
        == ("INVESTIGATION", "SUPPORTING")
        for row in problem_rows
    )
    # No candidate from problem rows.
    promoted = {
        row["candidate_id"]
        for row in result.output_payload["promotion_decisions"]
        if row["status"] == "PROMOTED"
    }
    candidates = {
        row["candidate_id"]: row
        for row in result.output_payload["acceptance_candidates"]
    }
    for candidate_id in promoted:
        assert "dropdown" not in candidates[candidate_id]["statement"].casefold()

    # C2A replay: coverage-reasoner is now genuinely evaluable.
    manifest, meta = adapter.project_runtime_result(
        result.model_dump(mode="json")
    )
    report = run_gates.replay_runtime_projection(manifest)
    statuses = {row["gate"]: row["status"] for row in report["gate_results"]}
    assert statuses["coverage-reasoner"] in {"PASS", "FAIL"}


def test_legacy_artifact_stays_not_evaluable_for_c1() -> None:
    result = _runtime_run("The export job must write a completion marker.")
    envelope = result.model_dump(mode="json")
    for row in envelope["output_payload"]["coverage_dispositions"]:
        row["priority"] = ""
        row["coverage_class"] = ""
        row["contract_type"] = ""
    manifest, meta = adapter.project_runtime_result(envelope)
    assert "coverage_decisions.priority" in meta["lossy_fields"]
    report = run_gates.replay_runtime_projection(manifest)
    statuses = {row["gate"]: row["status"] for row in report["gate_results"]}
    assert statuses["coverage-reasoner"] == "NOT_EVALUABLE"


def test_deliberate_c1_disagreement_is_reported() -> None:
    result = _runtime_run("The export job must write a completion marker.")
    envelope = result.model_dump(mode="json")
    manifest, _meta = adapter.project_runtime_result(envelope)
    runtime = manifest["_runtime"]
    promoted = next(
        (
            row
            for row in runtime["promotion_decisions"]
            if row["status"] == "PROMOTED"
        ),
        None,
    )
    if promoted is None:
        pytest.skip("fixture produced no promotion to tamper with")
    candidate = next(
        row
        for row in runtime["acceptance_candidates"]
        if row["candidate_id"] == promoted["candidate_id"]
    )
    linked = candidate["source_disposition_ids"][0]
    before = copy.deepcopy(runtime)
    for row in manifest["coverage_decisions"]["items"]:
        if row["coverage_id"] == linked:
            row["coverage_class"] = "QE_REGRESSION"
            row["priority"] = "P1"
    report = run_gates.replay_runtime_projection(manifest)
    assert report["runtime_promotion_status"] == "DISAGREES"
    assert any(
        row["gate"] == "coverage-reasoner"
        and row["severity"] == "BLOCKING_POLICY_DIVERGENCE"
        for row in report["disagreements"]
    )
    assert manifest["_runtime"] == before
