"""Existing-vs-New behavior classification for Question-Based UAC reasoning.

Regression coverage for the Output History purge ticket pattern: existing
documentation establishes the current baseline (AGE-based purge removes Output
History and logs after a configured period) while the Jira enhancement proposes
new behavior (COUNT-based retention, LOGS_ONLY retention action).  The system
must never confuse "documented today" with "required after this fix".
"""

from __future__ import annotations

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    AuthorityClass,
    AuthorityResolution,
    AuthoritySubject,
    BehaviorChangeClass,
    BehaviorClassificationRecord,
    CanonicalBehaviorModel,
    CanonicalRuntimeStage,
    ContractFact,
    ContractFactSet,
    ContractFactType,
    ContractMode,
    CoverageDisposition,
    CoverageDispositionRecord,
    CurrentnessState,
    EvidenceLifecycleStatus,
    EvidenceRecord,
    EvidenceSourceType,
    GateStatus,
    GenerationProfile,
    AcceptanceCandidate,
    AcceptancePromotionDecision,
    ProductContractOwnership,
    ProductOwnership,
    PromotionStatus,
    ResolutionState,
    RuntimeEntryPoint,
    ScopeResolution,
    SourceVisibility,
    UiApplicability,
    VerificationState,
)
from app.services.canonical_evidence_service import build_bundle
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE,
)
from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME


TENANT = "tenant-behavior-class"


def _record(
    *,
    source_type: EvidenceSourceType,
    reference: str,
    text: str,
    authority: AuthorityClass = AuthorityClass.CUSTOMER_REQUEST,
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
        evidence_confidence=0.9,
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


def _doc_record() -> EvidenceRecord:
    return _record(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        reference="expleague:output-history",
        text="AGE-based purge removes Output History and logs after the "
        "configured period.",
        authority=AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
    )


def _jira_record(text: str) -> EvidenceRecord:
    return _record(
        source_type=EvidenceSourceType.JIRA_DESCRIPTION,
        reference="jira:GUIDES-99002",
        text=text,
    )


def _diff_record(text: str) -> EvidenceRecord:
    return _record(
        source_type=EvidenceSourceType.IMPLEMENTATION_DIFF,
        reference="github:AdobeStarling/starling:pull/99002",
        text=text,
        authority=AuthorityClass.IMPLEMENTATION_CONFIRMED,
        authority_subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
    )


def _disposition(
    candidate: str,
    evidence: list[EvidenceRecord],
    disposition: CoverageDisposition = CoverageDisposition.SEMANTIC_REGRESSION,
) -> CoverageDispositionRecord:
    return CoverageDispositionRecord(
        candidate=candidate,
        disposition=disposition,
        evidence_ids=[row.evidence_id for row in evidence],
        rationale="test disposition",
    )


def _classify(
    dispositions: list[CoverageDispositionRecord],
    records: list[EvidenceRecord],
    conflicts: list[AuthorityResolution] | None = None,
) -> list[BehaviorClassificationRecord]:
    bundle = build_bundle(records, tenant_id=TENANT)
    if conflicts:
        bundle = bundle.model_copy(update={"authority_conflicts": conflicts})
    return CANONICAL_REASONING_SERVICE.classify_behavior_changes(
        ContractFactSet(contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT),
        dispositions,
        bundle,
    )


def test_age_baseline_is_existing_confirmed() -> None:
    doc = _doc_record()
    disposition = _disposition(
        "AGE-based purge removes Output History and logs after the configured "
        "period.",
        [doc],
    )
    (row,) = _classify([disposition], [doc])
    assert row.behavior_class == BehaviorChangeClass.EXISTING_CONFIRMED
    assert row.existing_evidence_ids == [doc.evidence_id]
    assert not row.requested_evidence_ids
    assert row.disposition_id == disposition.disposition_id


def test_count_and_logs_only_are_new_requirements() -> None:
    count_jira = _jira_record("Add COUNT-based retention to output history purge.")
    logs_jira = _jira_record("Add a LOGS_ONLY retention action to output history "
                             "purge.")
    count = _disposition(
        "The purge retains only the latest COUNT entries.",
        [count_jira],
        CoverageDisposition.ACCEPTANCE_CONTRACT,
    )
    logs_only = _disposition(
        "The LOGS_ONLY action retains log entries while purging output history.",
        [logs_jira],
        CoverageDisposition.ACCEPTANCE_CONTRACT,
    )
    rows = _classify([count, logs_only], [count_jira, logs_jira])
    by_disposition = {row.disposition_id: row for row in rows}
    for disposition in (count, logs_only):
        row = by_disposition[disposition.disposition_id]
        assert row.behavior_class == BehaviorChangeClass.NEW_REQUIREMENT
        assert not row.existing_evidence_ids
        assert row.requested_evidence_ids


def test_generated_output_preservation_is_preserved_existing_behavior() -> None:
    doc = _doc_record()
    jira = _jira_record(
        "Generated Outputs entries must remain intact after a log-only purge."
    )
    disposition = _disposition(
        "Generated Outputs entries must remain intact after a log-only purge.",
        [doc, jira],
    )
    (row,) = _classify([disposition], [doc, jira])
    assert row.behavior_class == BehaviorChangeClass.PRESERVED_EXISTING_BEHAVIOR
    assert doc.evidence_id in row.existing_evidence_ids
    assert jira.evidence_id in row.requested_evidence_ids


def test_documented_behavior_changed_by_ticket_is_modified() -> None:
    doc = _doc_record()
    jira = _jira_record("Change the AGE purge to also keep pinned entries.")
    disposition = _disposition(
        "The AGE purge also keeps pinned Output History entries.",
        [doc, jira],
        CoverageDisposition.ACCEPTANCE_CONTRACT,
    )
    (row,) = _classify([disposition], [doc, jira])
    assert row.behavior_class == BehaviorChangeClass.MODIFIED_EXISTING_BEHAVIOR


def test_unsupported_combination_semantics_stay_unknown_until_resolved() -> None:
    historical = _record(
        source_type=EvidenceSourceType.HISTORICAL_JIRA,
        reference="jira:GUIDES-10000",
        text="An older ticket discussed purge combinations.",
        authority=AuthorityClass.HISTORICAL_EXPECTATION,
    )
    disposition = _disposition(
        "Combining COUNT retention with LOGS_ONLY purges logs first, then "
        "applies the count.",
        [historical],
        CoverageDisposition.ACCEPTANCE_CONTRACT,
    )
    (row,) = _classify([disposition], [historical])
    assert row.behavior_class == BehaviorChangeClass.UNKNOWN

    # And with no linked evidence at all the behavior is equally unknown.
    bare = _disposition("Combining COUNT with LOGS_ONLY is defined.", [])
    (bare_row,) = _classify([bare], [])
    assert bare_row.behavior_class == BehaviorChangeClass.UNKNOWN


def test_conflicting_sources_mark_conflicted() -> None:
    doc = _doc_record()
    jira = _jira_record("The AGE purge must never remove log entries.")
    conflict = AuthorityResolution(
        claim_key="claim:age-purge-logs",
        status=ResolutionState.CONFLICTED,
        selected_evidence_ids=[doc.evidence_id],
        competing_evidence_ids=[jira.evidence_id],
        reason="Documentation and the ticket disagree.",
    )
    disposition = _disposition("The AGE purge removes log entries.", [doc, jira])
    (row,) = _classify([disposition], [doc, jira], [conflict])
    assert row.behavior_class == BehaviorChangeClass.CONFLICTED


def test_change_set_only_behavior_is_new_requirement_never_documented() -> None:
    diff = _diff_record("Add LOGS_ONLY retention action handling.")
    disposition = _disposition(
        "The LOGS_ONLY action retains log entries while purging output history.",
        [diff],
        CoverageDisposition.IMPLEMENTATION_ORACLE,
    )
    (row,) = _classify([disposition], [diff])
    assert row.behavior_class == BehaviorChangeClass.NEW_REQUIREMENT
    assert row.change_evidence_ids == [diff.evidence_id]

    with pytest.raises(ValueError, match="existing-behavior evidence"):
        BehaviorClassificationRecord(
            disposition_id=disposition.disposition_id,
            behavior_class=BehaviorChangeClass.NEW_REQUIREMENT,
            existing_evidence_ids=["ev-doc-1"],
            requested_evidence_ids=["ev-jira-1"],
            rationale="documentation cannot claim a new feature",
        )
    with pytest.raises(ValueError, match="change evidence"):
        BehaviorClassificationRecord(
            disposition_id=disposition.disposition_id,
            behavior_class=BehaviorChangeClass.EXISTING_CONFIRMED,
            existing_evidence_ids=["ev-doc-1"],
            change_evidence_ids=[diff.evidence_id],
            rationale="new implementation is not historical documented behavior",
        )


def test_reviewer_rejects_unresolved_classification_on_acceptance() -> None:
    jira = _jira_record("Add COUNT-based retention.")
    accept = _disposition(
        "The purge retains only the latest COUNT entries.",
        [jira],
        CoverageDisposition.ACCEPTANCE_CONTRACT,
    )
    rows = _classify([accept], [jira])
    assert rows[0].behavior_class == BehaviorChangeClass.NEW_REQUIREMENT

    unknown = BehaviorClassificationRecord(
        disposition_id=accept.disposition_id,
        behavior_class=BehaviorChangeClass.UNKNOWN,
        rationale="combination semantics unresolved",
    )
    gate = CANONICAL_REASONING_SERVICE.behavioral_completeness_gate(
        [],
        [],
        ScopeResolution(),
        [],
        [accept],
        None,
        None,
        None,
        [unknown],
    )
    assert gate.status == GateStatus.FAILED
    assert any("cannot ground an acceptance contract" in f for f in gate.failures)

    answered = CANONICAL_REASONING_SERVICE.behavioral_completeness_gate(
        [],
        [],
        ScopeResolution(),
        [],
        [accept],
        None,
        None,
        None,
        rows,
    )
    assert answered.status == GateStatus.PASSED


def test_promotion_gate_blocks_unknown_behavior_classification() -> None:
    jira = _jira_record("Add COUNT-based retention.")
    accept = _disposition(
        "The purge retains only the latest COUNT entries.",
        [jira],
        CoverageDisposition.ACCEPTANCE_CONTRACT,
    )
    fact = ContractFact(
        fact_type=ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
        literal=accept.candidate,
        source_evidence_ids=[jira.evidence_id],
        source_reference=jira.source_reference,
        authority_class=AuthorityClass.CUSTOMER_REQUEST,
        authoritative=True,
    )
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[fact],
    )
    candidate = AcceptanceCandidate(
        statement=accept.candidate,
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        source_fact_ids=[fact.fact_id],
        source_disposition_ids=[accept.disposition_id],
        evidence_ids=[jira.evidence_id],
        in_scope=True,
        observable=True,
    )
    unknown = BehaviorClassificationRecord(
        disposition_id=accept.disposition_id,
        behavior_class=BehaviorChangeClass.UNKNOWN,
        rationale="combination semantics unresolved",
    )
    gate, decisions = CANONICAL_REASONING_SERVICE.acceptance_promotion_gate(
        [candidate],
        facts,
        ScopeResolution(),
        [accept],
        [unknown],
    )
    assert decisions[0].status == PromotionStatus.BLOCKED
    assert any(
        "behavior classification is unresolved" in reason
        for reason in decisions[0].reasons
    )
    assert gate.status == GateStatus.BLOCKED

    (answered,) = _classify([accept], [jira])
    gate_ok, decisions_ok = CANONICAL_REASONING_SERVICE.acceptance_promotion_gate(
        [candidate],
        facts,
        ScopeResolution(),
        [accept],
        [answered],
    )
    assert decisions_ok[0].status == PromotionStatus.PROMOTED
    assert gate_ok.status == GateStatus.PASSED


def test_writer_never_confuses_documented_today_with_new_requirement() -> None:
    doc = _doc_record()
    jira = _jira_record("Add COUNT-based retention.")
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99002",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT
    )
    accept = _disposition(
        "The purge retains only the latest COUNT entries.",
        [jira],
        CoverageDisposition.ACCEPTANCE_CONTRACT,
    )
    candidate = AcceptanceCandidate(
        statement=accept.candidate,
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        source_disposition_ids=[accept.disposition_id],
        evidence_ids=[jira.evidence_id],
        in_scope=True,
        observable=True,
    )
    promoted = AcceptancePromotionDecision(
        candidate_id=candidate.candidate_id,
        status=PromotionStatus.PROMOTED,
        resulting_disposition=CoverageDisposition.ACCEPTANCE_CONTRACT,
        authority_supported=True,
        scope_established=True,
        observable=True,
        exact_values_supported=True,
        contradicts_human_contract=False,
    )

    # A candidate backed by an unresolved classification must not be written.
    unknown = BehaviorClassificationRecord(
        disposition_id=accept.disposition_id,
        behavior_class=BehaviorChangeClass.UNKNOWN,
        rationale="combination semantics unresolved",
    )
    with pytest.raises(RuntimeError, match="existing-vs-new classification"):
        CANONICAL_REASONING_SERVICE.render_final_plan(
            request,
            facts,
            ScopeResolution(),
            CanonicalBehaviorModel(),
            [],
            [],
            [],
            [accept],
            [candidate],
            [promoted],
            [],
            behavior_classifications=[unknown],
        )

    # A new requirement must not cite evidence that elsewhere serves as the
    # documented baseline (no "documented today" claims for new behavior).
    (answered,) = _classify([accept], [jira])
    assert answered.behavior_class == BehaviorChangeClass.NEW_REQUIREMENT
    documented_elsewhere = BehaviorClassificationRecord(
        disposition_id=_disposition(
            "AGE-based purge removes Output History and logs after the "
            "configured period.",
            [doc],
        ).disposition_id,
        behavior_class=BehaviorChangeClass.EXISTING_CONFIRMED,
        existing_evidence_ids=[doc.evidence_id],
        rationale="documented baseline",
    )
    contaminated = AcceptanceCandidate(
        statement=accept.candidate,
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        source_disposition_ids=[accept.disposition_id],
        evidence_ids=[jira.evidence_id, doc.evidence_id],
        in_scope=True,
        observable=True,
    )
    contaminated_promotion = promoted.model_copy(
        update={"candidate_id": contaminated.candidate_id}
    )
    with pytest.raises(RuntimeError, match="must not attribute existing documentation"):
        CANONICAL_REASONING_SERVICE.render_final_plan(
            request,
            facts,
            ScopeResolution(),
            CanonicalBehaviorModel(),
            [],
            [],
            [],
            [accept],
            [contaminated],
            [contaminated_promotion],
            [],
            behavior_classifications=[answered, documented_elsewhere],
        )

    # The honest combination renders: the new requirement cites only the ticket.
    plan, rendered = CANONICAL_REASONING_SERVICE.render_final_plan(
        request,
        facts,
        ScopeResolution(),
        CanonicalBehaviorModel(),
        [],
        [],
        [],
        [accept],
        [candidate],
        [promoted],
        [],
        behavior_classifications=[answered],
    )
    assert candidate.candidate_id in plan.promoted_candidate_ids
    assert answered.classification_id in plan.behavior_classification_ids
    assert "COUNT" in rendered


def test_runtime_classifies_every_resolved_behavior() -> None:
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99002",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet={
            "jira_key": "GUIDES-99002",
            "issue": {
                "issue_key": "GUIDES-99002",
                "summary": "Add COUNT retention and a LOGS_ONLY action to output "
                "history purge.",
                "description": (
                    "In scope: Native PDF. Out of scope: HTML5. "
                    "Enable DITA-OT Processing: ON. Output preset type: Native PDF. "
                    "The existing AGE-based purge behavior must remain compatible "
                    "after upgrade."
                ),
                "deployment_model": "On-prem",
                "product_version": "5.0",
            },
        },
    )
    stages = [row.stage for row in result.trace.stage_trace]
    classifier_index = stages.index(CanonicalRuntimeStage.BEHAVIOR_CHANGE_CLASSIFIER)
    assert stages[classifier_index - 1] == (
        CanonicalRuntimeStage.COVERAGE_DISPOSITION_CLASSIFIER
    )
    assert stages[classifier_index + 1] == (
        CanonicalRuntimeStage.ACCEPTANCE_CONTRACT_RESOLVER
    )

    open_states = {
        "OPEN_QUESTION",
        "PRODUCT_SCOPE_QUESTION",
        "ENGINEERING_DESIGN_DECISION",
        "OUT_OF_SCOPE",
        "UNSUPPORTED_INFERENCE",
    }
    dispositions = result.output_payload["coverage_dispositions"]
    classifications = result.output_payload["behavior_classifications"]
    class_by_disposition = {
        row["disposition_id"]: row for row in classifications
    }
    finalizing = [
        row for row in dispositions if row["disposition"] not in open_states
    ]
    assert finalizing, "expected at least one resolved behavior in the packet run"
    assert {row["disposition_id"] for row in finalizing} == set(class_by_disposition)
    for row in classifications:
        if row["behavior_class"] == "NEW_REQUIREMENT":
            assert not row["existing_evidence_ids"]
        if row["behavior_class"] in {
            "EXISTING_CONFIRMED",
            "MODIFIED_EXISTING_BEHAVIOR",
            "PRESERVED_EXISTING_BEHAVIOR",
        }:
            assert row["existing_evidence_ids"]
    assert result.trace.behavior_classifications
    assert {row.classification_id for row in result.trace.behavior_classifications} == {
        row["classification_id"] for row in classifications
    }
