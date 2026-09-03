"""Phase 2 contract, normalization, authority, isolation, and trace tests."""

from __future__ import annotations

import json
import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.schemas_canonical_test_plan_runtime import (
    CANONICAL_STAGE_ORDER,
    AcceptanceCandidate,
    AcceptancePromotionDecision,
    AcceptanceResolutionBatch,
    ApplicabilityState,
    AuthorityClass,
    AuthoritySubject,
    BehaviorHypothesis,
    BehaviorRelationType,
    ClosureDisposition,
    ClosureDimensionResult,
    ContractFact,
    ContractFactSet,
    ContractFactType,
    ContractMode,
    CoverageDispositionRecord,
    CoverageDisposition,
    CurrentnessState,
    EvidenceDirectness,
    EvidenceLifecycleStatus,
    EvidenceRecord,
    EvidenceSourceType,
    FeedbackClassification,
    GenerationProfile,
    HypothesisState,
    IssueDomain,
    MissingQuestion,
    ProductContractOwnership,
    ProductOwnership,
    PromotionStatus,
    ResolutionState,
    RuntimeEntryPoint,
    ScopeResolution,
    SemanticDimension,
    SourceVisibility,
    UiApplicability,
    UserFeedbackCandidate,
    VerificationState,
)
from app.services.canonical_evidence_service import (
    build_bundle,
    normalize_benchmark_public_input,
    normalize_legacy_packet,
    normalize_user_feedback,
    resolve_authority,
    visible_bundle,
)
from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE,
)
from app.services.test_plan_runtime_adapters import LEGACY_COMPATIBILITY_PROJECTOR


TENANT = "tenant-a"


def _record(
    *,
    source_type: EvidenceSourceType = EvidenceSourceType.CURRENT_JIRA,
    reference: str = "jira:GUIDES-1",
    content: object = None,
    authority: AuthorityClass = AuthorityClass.CUSTOMER_REQUEST,
    confidence: float = 0.8,
    currentness: CurrentnessState = CurrentnessState.CURRENT,
    lifecycle: EvidenceLifecycleStatus = EvidenceLifecycleStatus.INSPECTED,
    ownership: ProductContractOwnership = ProductContractOwnership.AEM_GUIDES_PRODUCT_CONTRACT,
    claim: str = "claim:behavior",
    tenant_id: str = TENANT,
    retrieved_at: str = "2026-08-23T01:00:00Z",
    feedback: UserFeedbackCandidate | None = None,
    authority_subject: AuthoritySubject | None = None,
) -> EvidenceRecord:
    inspected = lifecycle in {
        EvidenceLifecycleStatus.INSPECTED,
        EvidenceLifecycleStatus.USED,
    }
    return EvidenceRecord(
        source_type=source_type,
        authority_subject=authority_subject,
        source_reference=reference,
        tenant_id=tenant_id,
        content={"value": reference} if content is None else content,
        product="AEM Guides",
        product_area="Publishing",
        capability="Output generation",
        surface="Map console",
        retrieved_at=retrieved_at,
        currentness=currentness,
        ui_applicability=UiApplicability.UNKNOWN,
        evidence_confidence=confidence,
        requirement_authority=authority,
        verification_status=VerificationState.VERIFIED_SOURCE,
        lifecycle_status=lifecycle,
        inspected=inspected,
        used=lifecycle == EvidenceLifecycleStatus.USED,
        ownership=ProductOwnership(
            product="AEM Guides",
            contract_ownership=ownership,
        ),
        visibility=SourceVisibility(tenant_id=tenant_id),
        claim_keys=[claim] if claim else [],
        feedback=feedback,
    )


def test_evidence_contract_has_all_required_fields_and_distinctions() -> None:
    required_fields = {
        "evidence_id",
        "source_type",
        "authority_subject",
        "source_reference",
        "source_location",
        "product",
        "product_area",
        "capability",
        "surface",
        "content",
        "extracted_facts",
        "source_timestamp",
        "retrieved_at",
        "product_version",
        "deployment_model",
        "currentness",
        "evidence_confidence",
        "requirement_authority",
        "verification_status",
        "lifecycle_status",
        "retrieved_by_query",
        "inspected",
        "used",
        "rejected_reason",
    }
    assert required_fields <= set(EvidenceRecord.model_fields)
    assert {
        "ACCEPTED_UAC",
        "PRODUCT_DECISION",
        "ENGINEERING_DECISION",
        "OFFICIAL_PRODUCT_DOCUMENTATION",
        "DITA_SPECIFICATION",
        "DITA_OT_DOCUMENTATION",
        "CURRENT_CODE",
        "CURRENT_PR",
        "HISTORICAL_JIRA",
        "EXISTING_AUTOMATION",
        "UI_OBSERVATION",
        "OBSERVED_UI_FLOW",
        "USER_FEEDBACK",
        "CUSTOMER_REQUEST",
        "SCREENSHOT_REPRODUCTION",
    } <= {item.value for item in EvidenceSourceType}
    assert {
        "RETRIEVED",
        "INSPECTED",
        "USED",
        "REJECTED",
    } <= {item.value for item in EvidenceLifecycleStatus}


def test_evidence_id_ignores_retrieval_time_and_usage_but_bundle_records_usage() -> (
    None
):
    inspected = _record(retrieved_at="2026-08-23T01:00:00Z")
    used = _record(
        retrieved_at="2026-08-23T02:00:00Z",
        lifecycle=EvidenceLifecycleStatus.USED,
    )
    assert inspected.evidence_id == used.evidence_id
    assert (
        build_bundle([inspected], tenant_id=TENANT).bundle_id
        != build_bundle([used], tenant_id=TENANT).bundle_id
    )


def test_bundle_order_and_ids_are_deterministic_without_cross_source_collapse() -> None:
    jira = _record(reference="jira:GUIDES-1")
    docs = _record(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        reference="doc:https://example.test/guides",
        authority=AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
    )
    first = build_bundle([jira, docs], tenant_id=TENANT)
    second = build_bundle([docs, jira], tenant_id=TENANT)
    assert first.bundle_id == second.bundle_id
    assert [row.evidence_id for row in first.records] == [
        row.evidence_id for row in second.records
    ]
    assert jira.evidence_id != docs.evidence_id


@pytest.mark.parametrize(
    ("lifecycle", "inspected", "used", "reason"),
    [
        (EvidenceLifecycleStatus.RETRIEVED, True, False, ""),
        (EvidenceLifecycleStatus.INSPECTED, False, False, ""),
        (EvidenceLifecycleStatus.USED, True, False, ""),
        (EvidenceLifecycleStatus.REJECTED, True, False, ""),
    ],
)
def test_lifecycle_invariants_fail_closed(
    lifecycle: EvidenceLifecycleStatus,
    inspected: bool,
    used: bool,
    reason: str,
) -> None:
    with pytest.raises(ValidationError):
        EvidenceRecord(
            source_type=EvidenceSourceType.CURRENT_JIRA,
            source_reference="jira:GUIDES-2",
            tenant_id=TENANT,
            content={"summary": "x"},
            lifecycle_status=lifecycle,
            inspected=inspected,
            used=used,
            rejected_reason=reason,
            visibility=SourceVisibility(tenant_id=TENANT),
        )


def test_confidence_and_authority_are_independent() -> None:
    low = _record(confidence=0.1, authority=AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT)
    high = _record(
        reference="jira:GUIDES-1:user",
        confidence=0.99,
        authority=AuthorityClass.USER_EXPECTATION,
    )
    resolution = resolve_authority([high, low])[0]
    assert resolution.selected_evidence_ids == [low.evidence_id]
    assert low.evidence_confidence < high.evidence_confidence


def test_equal_authority_conflict_is_preserved() -> None:
    one = _record(
        reference="uac:1",
        content={"expected": "A"},
        authority=AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT,
    )
    two = _record(
        reference="uac:2",
        content={"expected": "B"},
        authority=AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT,
    )
    resolution = resolve_authority([one, two])[0]
    assert resolution.status == ResolutionState.CONFLICTED
    assert set(resolution.competing_evidence_ids) == {one.evidence_id, two.evidence_id}


def test_old_vs_new_ui_selects_current_and_retains_historical() -> None:
    old = _record(
        source_type=EvidenceSourceType.UI_OBSERVATION,
        reference="ui:old",
        content={"label": "Old"},
        authority=AuthorityClass.TECHNICALLY_INFERRED,
        currentness=CurrentnessState.HISTORICAL_COMPATIBILITY,
        ownership=ProductContractOwnership.OBSERVED_UI_STATE,
    )
    new = _record(
        source_type=EvidenceSourceType.UI_OBSERVATION,
        reference="ui:new",
        content={"label": "New"},
        authority=AuthorityClass.TECHNICALLY_INFERRED,
        ownership=ProductContractOwnership.OBSERVED_UI_STATE,
    )
    resolution = resolve_authority([old, new])[0]
    assert resolution.status == ResolutionState.SUPERSEDED
    assert resolution.selected_evidence_ids == [new.evidence_id]
    assert old.evidence_id in resolution.competing_evidence_ids


def test_contract_and_current_ui_are_resolved_as_different_authority_subjects() -> None:
    docs = _record(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        reference="doc:contract",
        content={"label": "Documented"},
        authority=AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
    )
    observation = _record(
        source_type=EvidenceSourceType.UI_OBSERVATION,
        reference="ui:current",
        content={"label": "Observed"},
        authority=AuthorityClass.TECHNICALLY_INFERRED,
        ownership=ProductContractOwnership.OBSERVED_UI_STATE,
    )
    resolutions = resolve_authority([observation, docs])
    by_subject = {row.subject: row for row in resolutions}
    assert by_subject[AuthoritySubject.PRODUCT_CONTRACT].selected_evidence_ids == [
        docs.evidence_id
    ]
    assert by_subject[AuthoritySubject.CURRENT_UI].selected_evidence_ids == [
        observation.evidence_id
    ]


def test_user_expectation_cannot_override_accepted_requirement() -> None:
    accepted = _record(
        source_type=EvidenceSourceType.ACCEPTED_UAC,
        reference="uac:accepted",
        authority=AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT,
    )
    expected = _record(
        source_type=EvidenceSourceType.USER_FEEDBACK,
        reference="feedback:expectation",
        authority=AuthorityClass.USER_EXPECTATION,
        feedback=UserFeedbackCandidate(
            candidate_id="fb-1",
            classifications=[FeedbackClassification.USER_EXPECTATION],
        ),
    )
    resolution = resolve_authority([expected, accepted])[0]
    assert resolution.selected_evidence_ids == [accepted.evidence_id]


def test_code_cannot_override_formal_product_contract() -> None:
    code = _record(
        source_type=EvidenceSourceType.CURRENT_CODE,
        reference="repo:current",
        authority=AuthorityClass.IMPLEMENTATION_CONFIRMED,
    )
    contract = _record(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        reference="doc:contract",
        authority=AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
    )
    resolutions = resolve_authority([code, contract])
    by_subject = {row.subject: row for row in resolutions}
    assert by_subject[AuthoritySubject.PRODUCT_CONTRACT].selected_evidence_ids == [
        contract.evidence_id
    ]
    assert by_subject[AuthoritySubject.ACTUAL_IMPLEMENTATION].selected_evidence_ids == [
        code.evidence_id
    ]


def test_pr_labeled_as_contract_evidence_still_cannot_override_accepted_uac() -> None:
    accepted = _record(
        source_type=EvidenceSourceType.ACCEPTED_UAC,
        reference="uac:accepted-contract",
        content={"expected": "Accepted behavior"},
        authority=AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT,
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
    )
    implementation = _record(
        source_type=EvidenceSourceType.CURRENT_PR,
        reference="pr:implementation",
        content={"expected": "Incidental implementation"},
        authority=AuthorityClass.IMPLEMENTATION_CONFIRMED,
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
    )
    resolution = resolve_authority([implementation, accepted])[0]
    assert resolution.subject == AuthoritySubject.PRODUCT_CONTRACT
    assert resolution.selected_evidence_ids == [accepted.evidence_id]
    assert implementation.evidence_id in resolution.competing_evidence_ids


def test_assets_and_guides_ownership_are_resolved_separately() -> None:
    guides = _record(
        reference="guides:contract",
        ownership=ProductContractOwnership.AEM_GUIDES_PRODUCT_CONTRACT,
    )
    assets = _record(
        reference="assets:contract",
        ownership=ProductContractOwnership.AEM_ASSETS_PLATFORM_CONTRACT,
    )
    resolutions = resolve_authority([guides, assets])
    assert len(resolutions) == 2
    assert all(row.status != ResolutionState.CONFLICTED for row in resolutions)
    assert {item for row in resolutions for item in row.selected_evidence_ids} == {
        guides.evidence_id,
        assets.evidence_id,
    }


def test_feedback_is_claim_scoped_and_never_intended_product_authority() -> None:
    feedback = normalize_user_feedback(
        {
            "id": "fb-1",
            "classification": "USER_OBSERVATION",
            "authoritative_for": ["experienced_state", "intended_behavior"],
        },
        tenant_id=TENANT,
        jira_key="GUIDES-1",
    )
    assert feedback.feedback is not None
    assert feedback.feedback.authoritative_for == ["experienced_state"]
    assert feedback.feedback.intended_behavior_authority is False
    assert feedback.requirement_authority == AuthorityClass.USER_EXPECTATION
    with pytest.raises(ValidationError):
        _record(
            source_type=EvidenceSourceType.USER_FEEDBACK,
            reference="feedback:bad",
            authority=AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT,
            feedback=UserFeedbackCandidate(candidate_id="fb-bad"),
        )


def test_packet_adapter_preserves_all_source_distinctions_and_graph_lineage() -> None:
    packet = {
        "jira_key": "GUIDES-1",
        "issue": {
            "issue_key": "GUIDES-1",
            "source": "jira_api",
            "summary": "Observed issue",
            "comments": [{"id": "c1", "body": "comment"}],
            "attachments": [{"id": "a1", "filename": "shot.png"}],
        },
        "experience_league_evidence": [{"canonical_url": "https://example.test/doc"}],
        "dita_spec_evidence": [{"canonical_url": "https://example.test/dita"}],
        "publishing_transform_context": {"results": [{"path": "src/pdf2.xsl"}]},
        "repository_evidence": {
            "repositories": [
                {
                    "id": "starling",
                    "head_sha": "abc123",
                    "matches": [{"path": "tests/test_publish.py"}],
                }
            ]
        },
        "implementation_diff_evidence": {"id": "diff-1", "revision": "abc123"},
        "pull_request_evidence": {"id": "pr-1", "revision": "abc123"},
        "ui_observations": [{"id": "ui-1", "value": "visible"}],
        "observed_ui_flows": [{"id": "flow-1", "value": "open/save"}],
        "screenshot_reproductions": [{"id": "screen-1", "value": "reproduced"}],
        "evidence_graph": {
            "evidence_paths": [
                {"leaf_citations": [{"leaf_id": "leaf-1", "source_ref": "GUIDES-2"}]}
            ]
        },
    }
    bundle = normalize_legacy_packet(packet, tenant_id=TENANT)
    types = {row.source_type for row in bundle.records}
    assert {
        EvidenceSourceType.CURRENT_JIRA,
        EvidenceSourceType.JIRA_COMMENT,
        EvidenceSourceType.JIRA_ATTACHMENT,
        EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        EvidenceSourceType.DITA_SPECIFICATION,
        EvidenceSourceType.DITA_OT_DOCUMENTATION,
        EvidenceSourceType.CURRENT_CODE,
        EvidenceSourceType.IMPLEMENTATION_DIFF,
        EvidenceSourceType.CURRENT_PR,
        EvidenceSourceType.EXISTING_AUTOMATION,
        EvidenceSourceType.UI_OBSERVATION,
        EvidenceSourceType.OBSERVED_UI_FLOW,
        EvidenceSourceType.SCREENSHOT_REPRODUCTION,
        EvidenceSourceType.EVIDENCE_GRAPH_LEAF,
    } <= types
    graph = next(
        row
        for row in bundle.records
        if row.source_type == EvidenceSourceType.EVIDENCE_GRAPH_LEAF
    )
    assert graph.directness == EvidenceDirectness.DERIVED
    assert graph.derived_from


def test_tenant_visibility_and_secret_redaction_fail_closed() -> None:
    packet = {
        "jira_key": "GUIDES-1",
        "issue": {
            "issue_key": "GUIDES-1",
            "source": "jira_api",
            "authorization": "Bearer very-secret-token",
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-1",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
        options={"starling_repo_path": "C:/safe", "api_key": "must-not-survive"},
    )
    bundle = CANONICAL_TEST_PLAN_RUNTIME.normalize_packet(packet, request=request)
    serialized = json.dumps(bundle.model_dump(mode="json"))
    assert "very-secret-token" not in serialized
    assert "must-not-survive" not in request.model_dump_json()
    other = request.principal.model_copy(update={"tenant_id": "tenant-b"})
    with pytest.raises(ValueError, match="another tenant"):
        visible_bundle(bundle, other)


def test_benchmark_adapter_rejects_answer_fields_and_private_paths() -> None:
    safe = {"record_id": "GUIDES-1", "pre_uac_evidence": {"summary": "safe"}}
    bundle = normalize_benchmark_public_input(safe, tenant_id=TENANT, split="train")
    assert bundle.records[0].source_type == EvidenceSourceType.BENCHMARK_PUBLIC_INPUT
    with pytest.raises(ValueError, match="evaluator-only"):
        normalize_benchmark_public_input(
            {**safe, "human_uac": ["sealed"]}, tenant_id=TENANT, split="blind"
        )
    with pytest.raises(ValueError, match="private benchmark"):
        normalize_benchmark_public_input(
            safe,
            tenant_id=TENANT,
            split="blind",
            source_path="benchmark/v2/private/blind.jsonl",
        )


def test_runtime_trace_records_canonical_stage_and_usage_lifecycles() -> None:
    packet = {
        "jira_key": "GUIDES-1",
        "issue": {
            "issue_key": "GUIDES-1",
            "source": "jira_api",
            "summary": "Publishing should retain the exact Ready status.",
            "description": (
                "In scope: Native PDF. Out of scope: HTML5. "
                "Enable DITA-OT Processing: ON. Output preset type: Native PDF."
            ),
            "attachments": [{"id": "a1", "filename": "unread.png"}],
        },
        "dita_spec_evidence": [{"canonical_url": "https://example.test/dita"}],
        "publishing_transform_context": {"results": [{"path": "src/pdf2.xsl"}]},
        "evidence_graph_evaluation": {"used_for_plan": False},
        "evidence_graph": {
            "evidence_paths": [
                {"leaf_citations": [{"leaf_id": "leaf-1", "source_ref": "GUIDES-2"}]}
            ]
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-1",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    statuses = {row.lifecycle_status for row in result.evidence_bundle.records}
    assert EvidenceLifecycleStatus.RETRIEVED in statuses
    assert EvidenceLifecycleStatus.USED in statuses
    assert EvidenceLifecycleStatus.IGNORED_BY_COMPATIBILITY_PATH not in statuses
    assert result.trace.consumed_evidence_ids
    assert result.trace.evidence_usage_trace
    assert [row.stage for row in result.trace.stage_trace] == list(
        CANONICAL_STAGE_ORDER
    )
    assert all(
        row.evidence_id
        in {record.evidence_id for record in result.evidence_bundle.records}
        for row in result.trace.evidence_usage_trace
    )


def _canonical_packet() -> dict[str, object]:
    return {
        "jira_key": "GUIDES-77",
        "issue": {
            "issue_key": "GUIDES-77",
            "summary": 'Publishing should display the exact "Ready" status.',
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
                "text": "A topicref can reference nested map content and participates in hierarchy.",
            }
        ],
        "repository_evidence": {
            "repositories": [
                {
                    "id": "starling",
                    "head_sha": "abc123",
                    "matches": [
                        {
                            "path": "src/publish/StatusWriter.java",
                            "reads": ["cq:lastModified"],
                            "consumers": ["ActivationStatusResolver"],
                            "generated_artifacts": ["Native PDF"],
                        }
                    ],
                }
            ]
        },
    }


def _canonical_result():
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-77",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    return CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=_canonical_packet(),
    )


def test_runtime_has_no_arbitrary_generator_hook_and_owns_exact_stage_order() -> None:
    assert not hasattr(CANONICAL_TEST_PLAN_RUNTIME, "generate")
    assert list(inspect.signature(type(CANONICAL_TEST_PLAN_RUNTIME)).parameters) == [
        "shadow_service",
        "github_verification_service",
        "pattern_resolver",
    ]
    assert (
        "generator" not in inspect.signature(CANONICAL_TEST_PLAN_RUNTIME.run).parameters
    )
    assert (
        "generator"
        not in inspect.signature(
            CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility
        ).parameters
    )
    result = _canonical_result()
    assert [row.stage for row in result.trace.stage_trace] == list(
        CANONICAL_STAGE_ORDER
    )
    assert result.metrics["stage_count"] == len(CANONICAL_STAGE_ORDER)


def test_contract_integrity_failure_stops_before_semantic_expansion() -> None:
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-123",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet={"jira_key": "GUIDES-123", "issue": {"issue_key": "GUIDES-123"}},
    )
    assert result.status == "blocked"
    assert [row.stage for row in result.trace.stage_trace] == list(
        CANONICAL_STAGE_ORDER[:2]
    )
    assert result.gate_decisions[0].status.value == "FAILED"


def test_whitespace_contract_value_does_not_block_the_plan() -> None:
    # Regression: a PRODUCT_CONTRACT value that is whitespace-only (e.g. a
    # non-breaking space from Jira rich text, or an empty AC line) must NOT become
    # an empty authoritative fact. Such a fact fails ContractIntegrityGate
    # ("Authoritative source wording is empty") and hard-blocks the whole plan -
    # the bug that blocked 5/8 held-out UAC_Done tickets in the eval.
    record = _record(
        source_type=EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA,
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        content={"acceptance_criteria": [" ", "   ", "The dialog opens on click."]},
    )
    bundle = build_bundle([record], tenant_id=TENANT)
    facts = CANONICAL_REASONING_SERVICE.extract_contract_facts(bundle)
    assert facts.facts, "expected at least the real contract fact"
    assert all(
        f.literal.strip() for f in facts.facts
    ), "no contract fact may have an empty literal"
    gate = CANONICAL_REASONING_SERVICE.contract_integrity_gate(facts)
    assert gate.status.value == "PASSED", gate.failures


def test_fj15_runtime_passes_resolved_scope_to_hypothesis_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}
    verifier = CANONICAL_TEST_PLAN_RUNTIME._reasoning.verify_hypotheses

    def capture_scope(*args, **kwargs):
        observed["scope"] = kwargs.get("scope")
        return verifier(*args, **kwargs)

    monkeypatch.setattr(
        CANONICAL_TEST_PLAN_RUNTIME._reasoning,
        "verify_hypotheses",
        capture_scope,
    )
    result = _canonical_result()

    assert observed["scope"] is not None
    assert observed["scope"].model_dump(mode="json") == result.output_payload["scope"]


def test_run_id_is_execution_specific_while_request_and_output_are_stable() -> None:
    first = _canonical_result()
    second = _canonical_result()
    assert first.run_id != second.run_id
    assert first.request_id == second.request_id
    assert first.output_sha256 == second.output_sha256
    assert first.trace.run_id == first.run_id
    assert first.trace.started_at
    assert first.trace.completed_at


def test_entry_point_changes_do_not_select_different_reasoning_or_gates() -> None:
    first_request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-77",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    second_request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-77",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.REST_BRIDGE,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    evidence = CANONICAL_TEST_PLAN_RUNTIME.normalize_packet(
        _canonical_packet(), request=first_request
    )
    first = CANONICAL_TEST_PLAN_RUNTIME.run(first_request, evidence)
    second = CANONICAL_TEST_PLAN_RUNTIME.run(second_request, evidence)
    assert first.request_id == second.request_id
    assert first.output_sha256 == second.output_sha256
    assert [row.stage for row in first.trace.stage_trace] == [
        row.stage for row in second.trace.stage_trace
    ]
    assert [row.model_dump(mode="json") for row in first.gate_decisions] == [
        row.model_dump(mode="json") for row in second.gate_decisions
    ]


def test_every_runtime_entry_point_uses_the_same_stage_order_and_decisions() -> None:
    baseline = None
    for entry_point in RuntimeEntryPoint:
        request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
            jira_key="GUIDES-77",
            tenant_id=TENANT,
            entry_point=entry_point,
            generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
            benchmark_version="V2"
            if entry_point == RuntimeEntryPoint.BENCHMARK_V2
            else "",
            benchmark_split="train"
            if entry_point == RuntimeEntryPoint.BENCHMARK_V2
            else "",
            benchmark_record_id="public-77"
            if entry_point == RuntimeEntryPoint.BENCHMARK_V2
            else "",
        )
        evidence = CANONICAL_TEST_PLAN_RUNTIME.normalize_packet(
            _canonical_packet(), request=request
        )
        result = CANONICAL_TEST_PLAN_RUNTIME.run(request, evidence)
        signature = (
            result.output_sha256,
            [row.stage for row in result.trace.stage_trace],
            [row.model_dump(mode="json") for row in result.gate_decisions],
        )
        baseline = baseline or signature
        assert signature == baseline


def test_legacy_prompt_shaped_diagnostics_are_not_canonical_evidence() -> None:
    bundle = normalize_legacy_packet(
        {
            "jira_key": "GUIDES-DIAGNOSTIC",
            "issue": {
                "issue_key": "GUIDES-DIAGNOSTIC",
                "summary": "The editor should display the configured title.",
            },
            "planning_seeds": {
                "regression_risk_seed": [
                    {"rationale": "bulk publish 3000 pages through a legacy prompt"}
                ]
            },
            "qa_studio_preview": {
                "generated_plan": "Use an unrelated migration performance AC."
            },
        },
        tenant_id=TENANT,
    )
    assert all(
        row.source_type != EvidenceSourceType.MODEL_INFERENCE for row in bundle.records
    )
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-DIAGNOSTIC",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.run(request, bundle)
    domains = {row["domain"] for row in result.output_payload["domains"]}
    assert IssueDomain.PERFORMANCE.value not in domains
    assert IssueDomain.MIGRATION.value not in domains


def test_contract_facts_preserve_scope_dita_ot_and_human_terminology() -> None:
    result = _canonical_result()
    facts = result.output_payload["contract_facts"]["facts"]
    types = {row["fact_type"] for row in facts}
    assert {
        ContractFactType.DIRECT_EXPECTED_BEHAVIOR.value,
        ContractFactType.IN_SCOPE.value,
        ContractFactType.OUT_OF_SCOPE.value,
        ContractFactType.DITA_OT_PROCESSING_STATE.value,
        ContractFactType.HUMAN_TERMINOLOGY.value,
    } <= types
    assert any(
        row["literal"] == 'Publishing should display the exact "Ready" status.'
        for row in facts
    )
    scope = result.output_payload["scope"]
    assert scope["enable_dita_ot_processing"] == "ON"
    assert "HTML5" in scope["out_of_scope"]
    assert not scope["primary_output_type"].startswith("Out of scope")
    assert set(result.trace.authoritative_facts_extracted) == set(
        result.trace.authoritative_facts_preserved
    )


def test_unclear_human_term_is_preserved_and_flagged_instead_of_renamed() -> None:
    packet = {
        "jira_key": "GUIDES-TERM",
        "issue": {
            "issue_key": "GUIDES-TERM",
            "summary": "Gloss alt/gloss title should work correctly.",
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-TERM",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    facts = result.output_payload["contract_facts"]["facts"]
    flagged = [
        row
        for row in facts
        if row["fact_type"] == ContractFactType.TERMINOLOGY_CLARIFICATION_REQUIRED.value
    ]
    assert flagged
    assert flagged[0]["literal"] == "Gloss alt/gloss title should work correctly."
    assert flagged[0]["preservation_state"] == "EXPLICITLY_FLAGGED_AS_AMBIGUOUS"
    assert any(
        row["blocking"] and "Gloss alt/gloss title" in row["question"]
        for row in result.output_payload["missing_questions"]
    )


def test_subject_specific_authority_uses_different_source_precedence() -> None:
    spec = _record(
        source_type=EvidenceSourceType.DITA_SPECIFICATION,
        reference="dita:spec",
        authority=AuthorityClass.SPECIFICATION_AUTHORITY,
        authority_subject=AuthoritySubject.DITA_SEMANTICS,
        ownership=ProductContractOwnership.DITA_SPECIFICATION_CONTRACT,
        claim="claim:dita",
    )
    dita_code = _record(
        source_type=EvidenceSourceType.CURRENT_CODE,
        reference="code:dita",
        authority=AuthorityClass.IMPLEMENTATION_CONFIRMED,
        authority_subject=AuthoritySubject.DITA_SEMANTICS,
        ownership=ProductContractOwnership.DITA_OT_PROCESSING_BEHAVIOR,
        claim="claim:dita",
    )
    docs = _record(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        reference="docs:implementation",
        authority=AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
        authority_subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        claim="claim:implementation",
    )
    current_code = _record(
        source_type=EvidenceSourceType.CURRENT_CODE,
        reference="code:current",
        authority=AuthorityClass.IMPLEMENTATION_CONFIRMED,
        authority_subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        claim="claim:implementation",
    )
    by_claim = {
        row.claim_key: row
        for row in resolve_authority([dita_code, spec, docs, current_code])
    }
    assert by_claim["claim:dita"].selected_evidence_ids == [spec.evidence_id]
    assert by_claim["claim:implementation"].selected_evidence_ids == [
        current_code.evidence_id
    ]


def test_semantic_closure_dispositions_are_total_and_unresolved_are_exposed() -> None:
    result = _canonical_result()
    closure = result.output_payload["semantic_closure"]
    questions = result.output_payload["missing_questions"]
    question_dimensions = {row["dimension"] for row in questions if row["dimension"]}
    assert closure
    assert all(
        row["disposition"] in {item.value for item in ClosureDisposition}
        for row in closure
    )
    assert all(
        row["dimension"] in question_dimensions
        for row in closure
        if row["disposition"] == ClosureDisposition.UNRESOLVED_AND_EXPOSED.value
    )
    assert result.trace.second_pass_retrievals
    assert all(
        row["status"] != "REJECTED"
        for row in result.output_payload["directed_retrievals"]
        if not row["matched_evidence_ids"]
    )


def test_change_surface_graph_traverses_explicit_downstream_relationships() -> None:
    result = _canonical_result()
    relations = {
        row["relation"]
        for row in result.output_payload["behavior_model"]["graph"]["edges"]
    }
    assert {
        BehaviorRelationType.READ_BY.value,
        BehaviorRelationType.CONSUMED_BY.value,
        BehaviorRelationType.GENERATED_BY.value,
    } <= relations
    assert result.trace.graph_nodes_visited
    assert result.trace.edges_visited
    assert any(
        row["node_type"] == "VERIFIED_HYPOTHESIS"
        for row in result.output_payload["behavior_model"]["graph"]["nodes"]
    )


def test_regression_dispositions_do_not_leak_into_acceptance_candidates() -> None:
    result = _canonical_result()
    dispositions = result.output_payload["coverage_dispositions"]
    assert any(
        row["disposition"] == CoverageDisposition.GENERATED_OUTPUT_VALIDATION.value
        for row in dispositions
    )
    candidate_statements = {
        row["statement"] for row in result.output_payload["acceptance_candidates"]
    }
    assert all(
        "GENERATED_OUTPUT" not in statement for statement in candidate_statements
    )


def test_unsupported_exactness_is_rejected_instead_of_promoted() -> None:
    packet = _canonical_packet()
    packet["customer_workflows"] = [
        {"id": "workflow-1", "behavior": "The system should retry exactly 7 times."}
    ]
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-77",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    candidates = {
        row["candidate_id"]: row
        for row in result.output_payload["acceptance_candidates"]
    }
    decisions = result.output_payload["promotion_decisions"]
    retry_decision = next(
        row
        for row in decisions
        if "7 times" in candidates[row["candidate_id"]]["statement"]
    )
    assert retry_decision["status"] == "REJECTED"
    assert retry_decision["exact_values_supported"] is False


def test_human_accepted_contract_is_preserved_while_scope_questions_stay_separate() -> (
    None
):
    packet = {
        "jira_key": "GUIDES-88",
        "issue": {
            "issue_key": "GUIDES-88",
            "summary": "Publishing status needs correction.",
            "description": "This affects Native PDF publishing.",
            "labels": ["accepted_uac"],
            "acceptance_criteria": [
                "The generated PDF should display the Ready status."
            ],
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-88",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    candidates = {
        row["candidate_id"]: row
        for row in result.output_payload["acceptance_candidates"]
    }
    accepted_decision = next(
        row
        for row in result.output_payload["promotion_decisions"]
        if candidates[row["candidate_id"]]["accepted_human_contract"]
    )
    assert accepted_decision["status"] == "PROMOTED"
    assert accepted_decision["resulting_disposition"] == "ACCEPTANCE_CONTRACT"
    assert (
        "The generated PDF should display the Ready status." in result.rendered_output
    )
    assert any(row["blocking"] for row in result.output_payload["missing_questions"])


def test_structured_accepted_uac_text_is_preserved_without_keyword_dependency() -> None:
    packet = {
        "jira_key": "GUIDES-AC",
        "issue": {"issue_key": "GUIDES-AC", "summary": "Friendly-name behavior"},
        "current_uac_contract": {
            "confirmed_ac_eligible": True,
            "criteria": [
                {"behaviour_statement": "Friendly names update automatically"}
            ],
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-AC",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    facts = result.output_payload["contract_facts"]["facts"]
    preserved = [
        row
        for row in facts
        if row["literal"] == "Friendly names update automatically"
        and row["fact_type"] == ContractFactType.DIRECT_EXPECTED_BEHAVIOR.value
    ]
    assert preserved
    assert any(row["authoritative"] for row in preserved)
    assert "Friendly names update automatically" in result.rendered_output


def test_explicit_out_of_scope_blocks_acceptance_promotion() -> None:
    packet = {
        "jira_key": "GUIDES-89",
        "issue": {
            "issue_key": "GUIDES-89",
            "summary": "Native PDF publishing should keep the Ready status.",
            "description": (
                "In scope: Native PDF. Out of scope: HTML5. "
                "HTML5 should also keep the Ready status. "
                "Enable DITA-OT Processing: ON. Output preset type: Native PDF."
            ),
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-89",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    assert not any(
        row["statement"].startswith("HTML5 should")
        for row in result.output_payload["acceptance_candidates"]
    )
    html5 = next(
        row
        for row in result.output_payload["coverage_dispositions"]
        if row["candidate"].startswith("HTML5 should")
    )
    assert html5["disposition"] == CoverageDisposition.OUT_OF_SCOPE.value


def test_explicit_high_cardinality_activates_performance_without_inventing_sla() -> (
    None
):
    packet = _canonical_packet()
    packet["issue"]["description"] += (
        " The API can publish 2k documents in one request."
    )
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-77",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    assert IssueDomain.PERFORMANCE.value in {
        row["domain"] for row in result.output_payload["domains"]
    }
    assert "API" in result.output_payload["scope"]["execution_interfaces"]
    nfr = [
        row
        for row in result.output_payload["coverage_dispositions"]
        if row["disposition"] == CoverageDisposition.NFR_COVERAGE.value
    ]
    assert nfr
    assert all("seconds" not in row["candidate"].casefold() for row in nfr)


def test_named_legacy_projector_cannot_change_reasoning_or_gates() -> None:
    result = _canonical_result()
    stage_hashes = [row.output_sha256 for row in result.trace.stage_trace]
    gates = [row.model_dump(mode="json") for row in result.gate_decisions]
    projection = LEGACY_COMPATIBILITY_PROJECTOR.project_result(result)
    assert projection["projector_id"] == "legacy_compatibility_projector_v2"
    assert projection["run_id"] == result.run_id
    assert stage_hashes == [row.output_sha256 for row in result.trace.stage_trace]
    assert gates == [row.model_dump(mode="json") for row in result.gate_decisions]
    assert set(result.structured_plan.coverage_disposition_ids) == {
        row["disposition_id"] for row in result.output_payload["coverage_dispositions"]
    }


def test_runtime_does_not_import_evaluator_or_sealed_answer_modules() -> None:
    source = (
        (
            Path(__file__).resolve().parents[1]
            / "app"
            / "services"
            / "canonical_test_plan_runtime.py"
        )
        .read_text(encoding="utf-8")
        .casefold()
    )
    assert "evaluator_access" not in source
    assert "blind_ground" not in source


def test_domain_routing_detects_api_scale_and_ignores_negated_scope() -> None:
    packet = {
        "jira_key": "GUIDES-ROUTING",
        "issue": {
            "issue_key": "GUIDES-ROUTING",
            "summary": "Documents are published through APIs.",
            "description": (
                "The API publishes 2,000 documents in one bulk action. "
                "Translation is out of scope."
            ),
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-ROUTING",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    domains = {row["domain"] for row in result.output_payload["domains"]}
    assert {
        IssueDomain.PUBLISHING.value,
        IssueDomain.API.value,
        IssueDomain.PERFORMANCE.value,
    } <= domains
    assert IssueDomain.TRANSLATION.value not in domains


def test_publishing_configuration_does_not_force_generated_output_oracles() -> None:
    packet = {
        "jira_key": "GUIDES-CONFIG",
        "issue": {
            "issue_key": "GUIDES-CONFIG",
            "summary": "Update the output preset field label in the preset dialog.",
            "description": (
                "This is a UI-only preset editor change. Performance is not in scope."
            ),
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-CONFIG",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    model = result.output_payload["behavior_model"]
    assert model["generated_artifact_delivery"] == "NOT_APPLICABLE"
    assert model["generated_output_oracles"] == []
    assert (
        result.output_payload["scope"]["enable_dita_ot_processing"] == "NOT_APPLICABLE"
    )
    assert not any(
        "DITA-OT" in row["question"]
        for row in result.output_payload["missing_questions"]
    )
    assert IssueDomain.PERFORMANCE.value not in {
        row["domain"] for row in result.output_payload["domains"]
    }
    assert IssueDomain.CONTENT_MANAGEMENT.value not in {
        row["domain"] for row in result.output_payload["domains"]
    }
    generated_rows = [
        row
        for row in result.output_payload["semantic_closure"]
        if row["dimension"] == "GENERATED_OUTPUT"
    ]
    assert generated_rows
    assert all(row["disposition"] == "NOT_APPLICABLE" for row in generated_rows)


def test_unknown_publishing_delivery_is_exposed_instead_of_assumed() -> None:
    packet = {
        "jira_key": "GUIDES-PRESET",
        "issue": {
            "issue_key": "GUIDES-PRESET",
            "summary": "Change an output preset setting.",
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-PRESET",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    model = result.output_payload["behavior_model"]
    assert model["generated_artifact_delivery"] == "UNRESOLVED"
    assert model["generated_output_oracles"] == []
    assert any(
        row["dimension"] == "GENERATED_OUTPUT"
        and row["disposition"] == "UNRESOLVED_AND_EXPOSED"
        for row in result.output_payload["semantic_closure"]
    )
    assert any(
        row["dimension"] == "GENERATED_OUTPUT"
        for row in result.output_payload["missing_questions"]
    )


def test_renderer_keeps_every_authoritative_contract_literal() -> None:
    result = _canonical_result()
    authoritative = [
        row["literal"]
        for row in result.output_payload["contract_facts"]["facts"]
        if row["authoritative"]
    ]
    assert authoritative
    assert all(literal in result.rendered_output for literal in authoritative)


def test_issue_identifier_digits_cannot_activate_scale_coverage() -> None:
    packet = {
        "jira_key": "FWD-7101",
        "issue": {
            "issue_key": "FWD-7101",
            "summary": "Documents display their configured title.",
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="FWD-7101",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    assert IssueDomain.PERFORMANCE.value not in {
        row["domain"] for row in result.output_payload["domains"]
    }
    assert not any(
        row["disposition"] == CoverageDisposition.NFR_COVERAGE.value
        for row in result.output_payload["coverage_dispositions"]
    )


def test_unresolved_product_decision_blocks_overall_postability() -> None:
    packet = {
        "jira_key": "FWD-72",
        "issue": {
            "issue_key": "FWD-72",
            "summary": "Change an output preset setting.",
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="FWD-72",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    promotion_gate = next(
        row
        for row in result.gate_decisions
        if row.gate.value == "AcceptancePromotionGate"
    )
    assert result.status == "blocked"
    assert promotion_gate.status.value == "BLOCKED"
    assert promotion_gate.failures
    assert LEGACY_COMPATIBILITY_PROJECTOR.is_postable(result) is False


def test_implementation_mechanics_cannot_be_promoted_to_acceptance() -> None:
    packet = {
        "jira_key": "FWD-73",
        "issue": {
            "issue_key": "FWD-73",
            "summary": "The fix should use a HashMap.",
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="FWD-73",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    candidates = {
        row["candidate_id"]: row
        for row in result.output_payload["acceptance_candidates"]
    }
    decision = next(
        row
        for row in result.output_payload["promotion_decisions"]
        if "HashMap" in candidates[row["candidate_id"]]["statement"]
    )
    assert candidates[decision["candidate_id"]]["implementation_mechanics_only"] is True
    assert decision["status"] == "REJECTED"
    assert decision["resulting_disposition"] == "UNSUPPORTED_INFERENCE"


def test_fresh_supported_contract_requires_human_review_before_posting() -> None:
    result = _canonical_result()
    assert result.status == "needs_human_review"
    assert result.validation_status == "passed"
    assert LEGACY_COMPATIBILITY_PROJECTOR.is_postable(result) is False


def test_zero_acceptance_candidates_cannot_pass_promotion_gate() -> None:
    packet = {
        "jira_key": "FWD-EMPTY",
        "issue": {
            "issue_key": "FWD-EMPTY",
            "summary": "Change an output preset setting.",
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="FWD-EMPTY",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    gate = next(
        row
        for row in result.gate_decisions
        if row.gate.value == "AcceptancePromotionGate"
    )
    assert result.status == "blocked"
    assert gate.status.value == "BLOCKED"
    assert "No supported acceptance-contract candidate" in " ".join(gate.failures)


def test_plain_publish_documents_language_activates_output_delivery() -> None:
    packet = {
        "jira_key": "FWD-PUBLISH",
        "issue": {
            "issue_key": "FWD-PUBLISH",
            "summary": "Publish documents through the API.",
            "description": (
                "Native PDF publishing should create the requested output. "
                "In scope: Native PDF. Out of scope: HTML5. "
                "Enable DITA-OT Processing: ON. Output preset type: Native PDF."
            ),
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="FWD-PUBLISH",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    model = result.output_payload["behavior_model"]
    assert model["generated_artifact_delivery"] == "APPLICABLE"
    assert "ARTIFACT_EXISTS" in model["generated_output_oracles"]


def test_contextual_publish_signal_does_not_cross_independent_facts() -> None:
    packet = {
        "jira_key": "FWD-BOUNDED-CONTEXT",
        "issue": {
            "issue_key": "FWD-BOUNDED-CONTEXT",
            "summary": "Update the preset before teams publish.",
            "description": "Documents are selected in a separate configuration field.",
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="FWD-BOUNDED-CONTEXT",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )

    assert (
        result.output_payload["behavior_model"]["generated_artifact_delivery"]
        == "UNRESOLVED"
    )


def test_tenant_identity_cannot_change_semantic_activation() -> None:
    packet = {
        "jira_key": "FWD-TENANT-INVARIANT",
        "issue": {
            "issue_key": "FWD-TENANT-INVARIANT",
            "summary": "Update the preset before teams publish.",
            "description": "Documents are selected in a separate configuration field.",
            "primary_component": "Publishing",
            "components": ["Publishing"],
            "pre_uac_evidence": {"components": ["Native_PDF"]},
        },
    }

    semantic_results: list[tuple[object, object, object, object]] = []
    for tenant_id in ("tenant-0", "tenant-1"):
        request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
            jira_key="FWD-TENANT-INVARIANT",
            tenant_id=tenant_id,
            entry_point=RuntimeEntryPoint.PYTHON_API,
            generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
        )
        result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
            request=request,
            packet=packet,
        )
        quality = result.output_payload["missing_question_quality"]
        scope = dict(result.output_payload["scope"])
        scope.pop("source_fact_ids", None)
        semantic_results.append(
            (
                scope,
                result.output_payload["behavior_model"][
                    "generated_artifact_delivery"
                ],
                [
                    (row["family_id"], row["activation_decision"])
                    for row in quality["family_satisfaction"]
                ],
                sorted(
                    (row["dimension"] or "", row["question"])
                    for row in quality["accepted_questions"]
                ),
            )
        )

    assert semantic_results[0] == semantic_results[1]
    assert semantic_results[0][0]["primary_product_area"] == "Publishing"


_SCOPE_AXIS_CASES = (
    pytest.param(
        ContractFactType.PRIMARY_PRODUCT_AREA,
        "$.primary_component",
        "$.pre_uac_evidence.components[0]",
        "Publishing",
        "Native_PDF",
        "primary_product_area",
        "PRIMARY_PRODUCT_AREA",
        id="product-area",
    ),
    pytest.param(
        ContractFactType.PRIMARY_OUTPUT_TYPE,
        "$.primary_output_type",
        "$.pre_uac_evidence.output_types[0]",
        "PDF",
        "HTML5",
        "primary_output_type",
        "PRIMARY_OUTPUT_TYPE",
        id="output-type",
    ),
    pytest.param(
        ContractFactType.PRESET_TYPE,
        "$.primary_preset_type",
        "$.pre_uac_evidence.output_presets[0]",
        "Native PDF",
        "AEM Sites",
        "primary_preset_type",
        "PRIMARY_PRESET_TYPE",
        id="preset-type",
    ),
)


@pytest.mark.parametrize(
    (
        "fact_type",
        "primary_path",
        "supporting_path",
        "primary_value",
        "supporting_value",
        "scope_attribute",
        "_unresolved_field",
    ),
    _SCOPE_AXIS_CASES,
)
def test_scope_selection_ignores_fact_order_and_provenance_ids(
    fact_type: ContractFactType,
    primary_path: str,
    supporting_path: str,
    primary_value: str,
    supporting_value: str,
    scope_attribute: str,
    _unresolved_field: str,
) -> None:
    def resolve(*, provenance_prefix: str, reverse: bool) -> ScopeResolution:
        facts = [
            ContractFact(
                fact_type=fact_type,
                literal=primary_value,
                normalized_value=primary_value,
                source_evidence_ids=[f"{provenance_prefix}:primary"],
                source_reference=f"jira:scope:{primary_path}",
                authority_class=AuthorityClass.CUSTOMER_REQUEST,
                authoritative=True,
            ),
            ContractFact(
                fact_type=fact_type,
                literal=supporting_value,
                normalized_value=supporting_value,
                source_evidence_ids=[f"{provenance_prefix}:supporting"],
                source_reference=f"jira:scope:{supporting_path}",
                authority_class=AuthorityClass.CUSTOMER_REQUEST,
                authoritative=True,
            ),
        ]
        if reverse:
            facts.reverse()
        return CANONICAL_REASONING_SERVICE.resolve_scope(
            ContractFactSet(
                contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
                facts=facts,
            ),
            [],
        )

    first = resolve(provenance_prefix="tenant-a", reverse=False)
    second = resolve(provenance_prefix="tenant-b", reverse=True)

    assert getattr(first, scope_attribute) == primary_value
    assert getattr(second, scope_attribute) == primary_value
    assert first.model_dump(exclude={"source_fact_ids"}) == second.model_dump(
        exclude={"source_fact_ids"}
    )


@pytest.mark.parametrize(
    (
        "fact_type",
        "root_direct_path",
        "nested_primary_path",
        "root_value",
        "nested_value",
        "scope_attribute",
    ),
    (
        pytest.param(
            ContractFactType.PRIMARY_PRODUCT_AREA,
            "$.components[0]",
            "$.pre_uac_evidence.primary_component",
            "Publishing",
            "Native_PDF",
            "primary_product_area",
            id="product-area",
        ),
        pytest.param(
            ContractFactType.PRIMARY_OUTPUT_TYPE,
            "$.output_types[0]",
            "$.pre_uac_evidence.primary_output_type",
            "PDF",
            "HTML5",
            "primary_output_type",
            id="output-type",
        ),
        pytest.param(
            ContractFactType.PRESET_TYPE,
            "$.output_presets[0]",
            "$.pre_uac_evidence.primary_preset_type",
            "Native PDF",
            "AEM Sites",
            "primary_preset_type",
            id="preset-type",
        ),
    ),
)
def test_root_scope_field_outweighs_nested_primary_hint(
    fact_type: ContractFactType,
    root_direct_path: str,
    nested_primary_path: str,
    root_value: str,
    nested_value: str,
    scope_attribute: str,
) -> None:
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            ContractFact(
                fact_type=fact_type,
                literal=nested_value,
                normalized_value=nested_value,
                source_evidence_ids=["nested-supporting-source"],
                source_reference=f"jira:scope:{nested_primary_path}",
                authority_class=AuthorityClass.CUSTOMER_REQUEST,
                authoritative=True,
            ),
            ContractFact(
                fact_type=fact_type,
                literal=root_value,
                normalized_value=root_value,
                source_evidence_ids=["root-direct-source"],
                source_reference=f"jira:scope:{root_direct_path}",
                authority_class=AuthorityClass.CUSTOMER_REQUEST,
                authoritative=True,
            ),
        ],
    )

    scope = CANONICAL_REASONING_SERVICE.resolve_scope(facts, [])

    assert getattr(scope, scope_attribute) == root_value


@pytest.mark.parametrize(
    (
        "fact_type",
        "primary_path",
        "_supporting_path",
        "primary_value",
        "alternate_value",
        "scope_attribute",
        "_unresolved_field",
    ),
    _SCOPE_AXIS_CASES,
)
def test_scope_selection_changes_for_a_real_semantic_change(
    fact_type: ContractFactType,
    primary_path: str,
    _supporting_path: str,
    primary_value: str,
    alternate_value: str,
    scope_attribute: str,
    _unresolved_field: str,
) -> None:
    def resolve(value: str) -> ScopeResolution:
        facts = ContractFactSet(
            contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
            facts=[
                ContractFact(
                    fact_type=fact_type,
                    literal=value,
                    normalized_value=value,
                    source_evidence_ids=["stable-provenance"],
                    source_reference=f"jira:scope:{primary_path}",
                    authority_class=AuthorityClass.CUSTOMER_REQUEST,
                    authoritative=True,
                )
            ],
        )
        return CANONICAL_REASONING_SERVICE.resolve_scope(facts, [])

    before = resolve(primary_value)
    after = resolve(alternate_value)

    assert getattr(before, scope_attribute) == primary_value
    assert getattr(after, scope_attribute) == alternate_value
    assert getattr(before, scope_attribute) != getattr(after, scope_attribute)


@pytest.mark.parametrize(
    (
        "fact_type",
        "primary_path",
        "_supporting_path",
        "primary_value",
        "accepted_value",
        "scope_attribute",
        "_unresolved_field",
    ),
    _SCOPE_AXIS_CASES,
)
def test_higher_authority_scope_fact_outweighs_source_path_priority(
    fact_type: ContractFactType,
    primary_path: str,
    _supporting_path: str,
    primary_value: str,
    accepted_value: str,
    scope_attribute: str,
    _unresolved_field: str,
) -> None:
    facts = ContractFactSet(
        contract_mode=ContractMode.HUMAN_ACCEPTED_CONTRACT,
        facts=[
            ContractFact(
                fact_type=fact_type,
                literal=primary_value,
                normalized_value=primary_value,
                source_evidence_ids=["current-jira"],
                source_reference=f"jira:scope:{primary_path}",
                authority_class=AuthorityClass.CUSTOMER_REQUEST,
                authoritative=True,
            ),
            ContractFact(
                fact_type=fact_type,
                literal=accepted_value,
                normalized_value=accepted_value,
                source_evidence_ids=["accepted-uac"],
                source_reference=f"jira:uac:$.scope.{scope_attribute}",
                authority_class=AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT,
                authoritative=True,
            ),
        ],
    )

    scope = CANONICAL_REASONING_SERVICE.resolve_scope(facts, [])

    assert getattr(scope, scope_attribute) == accepted_value


@pytest.mark.parametrize(
    (
        "fact_type",
        "primary_path",
        "_supporting_path",
        "first_value",
        "second_value",
        "scope_attribute",
        "unresolved_field",
    ),
    _SCOPE_AXIS_CASES,
)
def test_equal_precedence_scope_conflict_is_exposed_as_unresolved(
    fact_type: ContractFactType,
    primary_path: str,
    _supporting_path: str,
    first_value: str,
    second_value: str,
    scope_attribute: str,
    unresolved_field: str,
) -> None:
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            ContractFact(
                fact_type=fact_type,
                literal=first_value,
                normalized_value=first_value,
                source_evidence_ids=["source-a"],
                source_reference=f"jira:a:{primary_path}",
                authority_class=AuthorityClass.CUSTOMER_REQUEST,
                authoritative=True,
            ),
            ContractFact(
                fact_type=fact_type,
                literal=second_value,
                normalized_value=second_value,
                source_evidence_ids=["source-b"],
                source_reference=f"jira:b:{primary_path}",
                authority_class=AuthorityClass.CUSTOMER_REQUEST,
                authoritative=True,
            ),
        ],
    )

    scope = CANONICAL_REASONING_SERVICE.resolve_scope(facts, [])

    assert getattr(scope, scope_attribute) == ""
    assert unresolved_field in scope.unresolved_fields


def test_human_contract_blocks_unaccepted_scope_expansion() -> None:
    packet = {
        "jira_key": "FWD-HUMAN",
        "issue": {
            "issue_key": "FWD-HUMAN",
            "summary": "The editor should refresh the configured label.",
            "description": "The editor should also add an automatic retry.",
            "labels": ["accepted_uac"],
            "acceptance_criteria": ["The editor should refresh the configured label."],
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="FWD-HUMAN",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    candidates = {
        row["candidate_id"]: row
        for row in result.output_payload["acceptance_candidates"]
    }
    extra = next(
        row
        for row in result.output_payload["promotion_decisions"]
        if "automatic retry" in candidates[row["candidate_id"]]["statement"]
    )
    assert extra["status"] == "REJECTED"
    assert "not part of that accepted contract" in " ".join(extra["reasons"])


def test_semantically_duplicate_proposed_outcomes_collapse_once() -> None:
    packet = {
        "jira_key": "FWD-DUPLICATE",
        "issue": {
            "issue_key": "FWD-DUPLICATE",
            "summary": "AEM Sites output should use the map title.",
            "description": "The AEM Sites output should use map title.",
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="FWD-DUPLICATE",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    matching = [
        row
        for row in result.output_payload["acceptance_candidates"]
        if "map title" in row["statement"].casefold()
    ]
    assert len(matching) == 1
    assert len(result.output_payload["discovered_acceptance_candidates"]) == 3
    assert len(result.output_payload["candidate_dedup_decisions"]) == 1
    decision = result.output_payload["candidate_dedup_decisions"][0]
    assert len(decision["merged_candidate_ids"]) == 3
    assert decision["surviving_candidate_id"] == matching[0]["candidate_id"]
    assert decision["merge_reason"]
    assert decision["semantic_equivalence_basis"]
    assert len(result.output_payload["candidate_lifecycle"]) == 3
    assert all(
        row["stages"][-1] == "FINAL_DISPOSITION"
        for row in result.output_payload["candidate_lifecycle"]
    )
    assert len(result.structured_plan.renderer_decisions) == 3


def test_textually_similar_distinct_candidates_do_not_merge_or_silently_pass() -> None:
    packet = {
        "jira_key": "FWD-DISTINCT-CANDIDATES",
        "issue": {
            "issue_key": "FWD-DISTINCT-CANDIDATES",
            "summary": "AEM Sites output should use the map title.",
            "description": "AEM Sites navigation should use the map title.",
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="FWD-DISTINCT-CANDIDATES",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    payload = result.output_payload
    relevant = [
        row
        for row in payload["acceptance_candidates"]
        if "map title" in row["statement"].casefold()
    ]
    assert {row["statement"] for row in relevant} == {
        "AEM Sites output should use the map title.",
        "AEM Sites navigation should use the map title.",
    }

    resolution = AcceptanceResolutionBatch(
        discovered_candidates=[
            AcceptanceCandidate.model_validate(row)
            for row in payload["discovered_acceptance_candidates"]
        ],
        candidates=[
            AcceptanceCandidate.model_validate(row)
            for row in payload["acceptance_candidates"]
        ],
        dedup_decisions=payload["candidate_dedup_decisions"],
    )
    promotions = [
        AcceptancePromotionDecision.model_validate(row)
        for row in payload["promotion_decisions"]
    ]
    with pytest.raises(
        RuntimeError,
        match="Every finalized acceptance candidate requires exactly one terminal",
    ):
        CANONICAL_REASONING_SERVICE.build_candidate_lifecycle(
            resolution,
            promotions[:1],
        )


def test_three_material_candidates_require_three_terminal_decisions() -> None:
    source_disposition_id = "disposition:" + "1" * 32
    candidates = [
        AcceptanceCandidate(
            statement=statement,
            contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
            source_disposition_ids=[source_disposition_id],
            evidence_ids=[f"ev:CURRENT_JIRA:{index:032x}"],
            in_scope=True,
            observable=True,
        )
        for index, statement in enumerate(
            (
                "The changed value reaches the direct consumer.",
                "The changed value reaches the persisted state reader.",
                "The changed value reaches the alternate entry point.",
            ),
            start=1,
        )
    ]
    resolution = AcceptanceResolutionBatch(
        discovered_candidates=candidates,
        candidates=candidates,
    )
    promotions = [
        AcceptancePromotionDecision(
            candidate_id=candidate.candidate_id,
            status=PromotionStatus.PROMOTED,
            resulting_disposition=CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
            authority_supported=True,
            scope_established=True,
            observable=True,
            exact_values_supported=True,
        )
        for candidate in candidates
    ]

    lifecycle = CANONICAL_REASONING_SERVICE.build_candidate_lifecycle(
        resolution,
        promotions,
    )
    assert len(lifecycle) == 3
    assert {row.final_disposition.value for row in lifecycle} == {"AC"}

    with pytest.raises(
        RuntimeError,
        match="Every finalized acceptance candidate requires exactly one terminal",
    ):
        CANONICAL_REASONING_SERVICE.build_candidate_lifecycle(
            resolution,
            promotions[:1],
        )


def test_explicit_polarity_conflict_is_marked_against_human_contract() -> None:
    packet = {
        "jira_key": "FWD-CONFLICT",
        "issue": {
            "issue_key": "FWD-CONFLICT",
            "summary": "The status should remain enabled after refresh.",
            "description": "The status should not remain enabled after refresh.",
            "labels": ["accepted_uac"],
            "acceptance_criteria": ["The status should remain enabled after refresh."],
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="FWD-CONFLICT",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    candidates = {
        row["candidate_id"]: row
        for row in result.output_payload["acceptance_candidates"]
    }
    conflict = next(
        row
        for row in result.output_payload["promotion_decisions"]
        if "should not remain" in candidates[row["candidate_id"]]["statement"]
    )
    assert conflict["contradicts_human_contract"] is True
    assert conflict["status"] == "REJECTED"


def test_exact_accepted_uac_keeps_accepted_authority_and_is_postable() -> None:
    packet = {
        "jira_key": "FWD-EXACT-UAC",
        "issue": {
            "issue_key": "FWD-EXACT-UAC",
            "summary": "Job completion status",
            "labels": ["accepted_uac"],
            "acceptance_criteria": [
                "When the job finishes, display status Ready and keep Batch size 250."
            ],
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="FWD-EXACT-UAC",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    accepted = [
        row
        for row in result.output_payload["acceptance_candidates"]
        if "Batch size 250" in row["statement"]
    ]
    assert len(accepted) == 1
    assert accepted[0]["accepted_human_contract"] is True
    assert any(
        row["candidate_id"] == accepted[0]["candidate_id"]
        and row["status"] == "PROMOTED"
        for row in result.output_payload["promotion_decisions"]
    )
    assert result.status == "completed"
    assert LEGACY_COMPATIBILITY_PROJECTOR.is_postable(result) is True


def test_negated_generated_output_keeps_configuration_only_delivery_out_of_scope() -> (
    None
):
    packet = {
        "jira_key": "FWD-CONFIG-OOS",
        "issue": {
            "issue_key": "FWD-CONFIG-OOS",
            "summary": "Rename an output-preset field label.",
            "description": (
                "Only the preset configuration UI is in scope. "
                "Publishing is out of scope. Generated output is out of scope."
            ),
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="FWD-CONFIG-OOS",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    assert (
        result.output_payload["behavior_model"]["generated_artifact_delivery"]
        == "NOT_APPLICABLE"
    )
    assert result.output_payload["behavior_model"]["generated_output_oracles"] == []
    assert (
        result.output_payload["scope"]["enable_dita_ot_processing"] == "NOT_APPLICABLE"
    )
    assert not any(
        "DITA-OT" in row["question"]
        for row in result.output_payload["missing_questions"]
    )


def test_all_rejected_implementation_candidates_block_the_run() -> None:
    packet = {
        "jira_key": "FWD-MECHANICS-ONLY",
        "issue": {
            "issue_key": "FWD-MECHANICS-ONLY",
            "summary": "The fix should use a HashMap and retry exactly 7 times.",
            "description": "Implementation detail only.",
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="FWD-MECHANICS-ONLY",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    decisions = result.output_payload["promotion_decisions"]
    assert decisions
    assert all(row["status"] == "REJECTED" for row in decisions)
    assert result.status == "blocked"
    assert LEGACY_COMPATIBILITY_PROJECTOR.is_postable(result) is False


def test_fj16_material_hypotheses_are_dispositioned_exactly_once() -> None:
    result = _canonical_result()
    dispositions = result.output_payload["coverage_dispositions"]
    hypotheses = result.output_payload["hypotheses"]
    linked: dict[str, list[dict[str, object]]] = {}
    for disposition in dispositions:
        for hypothesis_id in disposition["source_hypothesis_ids"]:
            linked.setdefault(hypothesis_id, []).append(disposition)

    assert hypotheses
    assert set(linked) == {row["hypothesis_id"] for row in hypotheses}
    assert all(len(rows) == 1 for rows in linked.values())

    questions = {
        row["question_id"]: row for row in result.output_payload["missing_questions"]
    }
    for hypothesis in hypotheses:
        disposition = linked[hypothesis["hypothesis_id"]][0]
        question = questions[hypothesis["derived_from_question_id"]]
        if hypothesis["state"] == HypothesisState.UNRESOLVED.value:
            assert disposition["disposition"] == CoverageDisposition.OPEN_QUESTION.value
        elif question["dimension"] is not None:
            assert disposition["disposition"] not in {
                CoverageDisposition.ACCEPTANCE_CONTRACT.value,
                CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT.value,
                CoverageDisposition.OPEN_QUESTION.value,
                CoverageDisposition.UNSUPPORTED_INFERENCE.value,
            }

    completeness_gate = next(
        row
        for row in result.output_payload["gate_decisions"]
        if row["gate"] == "BehavioralCompletenessGate"
    )
    assert {row["derived_from_question_id"] for row in hypotheses} <= set(
        completeness_gate["checked_ids"]
    )


def test_fj16_resolved_questions_leave_open_question_sections_but_unresolved_remain() -> (
    None
):
    result = _canonical_result()
    questions = {
        row["question_id"]: row for row in result.output_payload["missing_questions"]
    }
    hypotheses = result.output_payload["hypotheses"]
    section_ids = {
        section["section_key"]: set(section["source_record_ids"])
        for section in result.output_payload["structured_plan"]["sections"]
    }
    open_ids = section_ids.get("product_decisions", set()) | section_ids.get(
        "evidence_gaps", set()
    )
    for hypothesis in hypotheses:
        question = questions[hypothesis["derived_from_question_id"]]
        if hypothesis["state"] == HypothesisState.UNRESOLVED.value:
            assert question["question_id"] in open_ids
        elif question["dimension"] is not None:
            assert question["question_id"] not in open_ids


def test_fj16_every_terminal_disposition_is_addressable_in_one_section() -> (
    None
):
    result = _canonical_result()
    visible_counts: dict[str, int] = {}
    for section in result.output_payload["structured_plan"]["sections"]:
        for record_id in section["source_record_ids"]:
            if record_id.startswith("disposition:"):
                visible_counts[record_id] = visible_counts.get(record_id, 0) + 1
    expected_ids = {
        row["disposition_id"]
        for row in result.output_payload["coverage_dispositions"]
    }
    assert set(visible_counts) == expected_ids
    assert set(visible_counts.values()) == {1}
    all_source_ids = {
        record_id
        for section in result.output_payload["structured_plan"]["sections"]
        for record_id in section["source_record_ids"]
    }
    assert set(
        result.output_payload["contract_facts"]["authoritative_fact_ids"]
    ) <= all_source_ids


def test_fj16_unresolved_closure_requires_exact_question_lineage() -> None:
    closure = ClosureDimensionResult(
        entity="Map A",
        dimension=SemanticDimension.FALLBACK,
        applicability=ApplicabilityState.APPLICABLE,
        disposition=ClosureDisposition.UNRESOLVED_AND_EXPOSED,
        rationale="Fallback is material and unresolved.",
    )
    unrelated = MissingQuestion(
        question="What fallback applies to unrelated Map B?",
        dimension=SemanticDimension.FALLBACK,
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
    )
    gate = CANONICAL_REASONING_SERVICE.behavioral_completeness_gate(
        [closure],
        [unrelated],
        ScopeResolution(),
        hypotheses=[],
        dispositions=[],
    )
    assert gate.status.value == "FAILED"
    assert closure.closure_id in " ".join(gate.failures)


def test_fj16_regression_intent_is_routed_to_qe_coverage_and_never_ac() -> None:
    packet = {
        "jira_key": "FWD-QA-REGRESSION",
        "issue": {
            "issue_key": "FWD-QA-REGRESSION",
            "summary": "The QA suite should continue covering HTML5 output.",
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="FWD-QA-REGRESSION",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    matching_dispositions = [
        row
        for row in result.output_payload["coverage_dispositions"]
        if "QA suite" in row["candidate"]
    ]
    assert matching_dispositions
    assert any(
        row["disposition"] == CoverageDisposition.SEMANTIC_REGRESSION.value
        for row in matching_dispositions
    )
    assert all(
        row["disposition"]
        not in {
            CoverageDisposition.ACCEPTANCE_CONTRACT.value,
            CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT.value,
        }
        for row in matching_dispositions
    )
    assert all(
        "QA suite" not in row["statement"]
        for row in result.output_payload["acceptance_candidates"]
    )
    semantic_section = next(
        row
        for row in result.output_payload["structured_plan"]["sections"]
        if row["section_key"] == "semantic_coverage"
    )
    assert any("QA suite" in item for item in semantic_section["items"])


def test_fj16_promotion_gate_rejects_non_acceptance_source_disposition() -> None:
    fact = ContractFact(
        fact_type=ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
        literal="The visible status remains unchanged.",
        authority_class=AuthorityClass.CURRENT_ACCEPTED_UAC,
        authoritative=True,
    )
    facts = ContractFactSet(
        contract_mode=ContractMode.HUMAN_ACCEPTED_CONTRACT,
        facts=[fact],
    )
    regression = CoverageDispositionRecord(
        candidate=fact.literal,
        disposition=CoverageDisposition.SEMANTIC_REGRESSION,
        source_fact_ids=[fact.fact_id],
        rationale="Verified regression coverage only.",
    )
    candidate = AcceptanceCandidate(
        statement=fact.literal,
        contract_mode=ContractMode.HUMAN_ACCEPTED_CONTRACT,
        accepted_human_contract=True,
        source_fact_ids=[fact.fact_id],
        source_disposition_ids=[regression.disposition_id],
        in_scope=True,
        observable=True,
    )
    gate, decisions = CANONICAL_REASONING_SERVICE.acceptance_promotion_gate(
        [candidate],
        facts,
        ScopeResolution(),
        [regression],
    )
    assert gate.status.value == "FAILED"
    assert decisions[0].status.value == "REJECTED"
    assert "Non-acceptance coverage disposition" in " ".join(decisions[0].reasons)


def test_fj16_directional_contracts_do_not_semantically_collapse() -> None:
    packet = {
        "jira_key": "FWD-DIRECTION",
        "issue": {
            "issue_key": "FWD-DIRECTION",
            "summary": "Topic title should replace map title.",
            "description": "Map title should replace topic title.",
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="FWD-DIRECTION",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    candidates = [
        row
        for row in result.output_payload["acceptance_candidates"]
        if "replace" in row["statement"].casefold()
    ]
    assert {row["statement"] for row in candidates} == {
        "Topic title should replace map title.",
        "Map title should replace topic title.",
    }
    assert all(row["source_disposition_ids"] for row in candidates)


def test_fj16_distinct_output_and_page_contracts_do_not_collapse() -> None:
    packet = {
        "jira_key": "FWD-OUTPUT-PAGE",
        "issue": {
            "issue_key": "FWD-OUTPUT-PAGE",
            "summary": "Generated PDF output includes metadata.",
            "description": "Generated PDF page includes metadata.",
        },
    }
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="FWD-OUTPUT-PAGE",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    candidates = {
        row["statement"]
        for row in result.output_payload["acceptance_candidates"]
        if "includes metadata" in row["statement"].casefold()
    }
    assert candidates == {
        "Generated PDF output includes metadata.",
        "Generated PDF page includes metadata.",
    }


def test_fj16_rejected_material_hypothesis_gets_terminal_rejected_disposition() -> (
    None
):
    hypothesis = BehaviorHypothesis(
        statement="The investigated behavior is applicable.",
        state=HypothesisState.REJECTED,
        confidence=0.0,
    )
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT
    )
    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts,
        closure=[],
        impacts=[],
        hypotheses=[hypothesis],
        scope=ScopeResolution(),
        questions=[],
    )
    linked = [
        row
        for row in dispositions
        if hypothesis.hypothesis_id in row.source_hypothesis_ids
    ]
    assert len(linked) == 1
    assert (
        linked[0].disposition
        == CoverageDisposition.INVESTIGATED_AND_REJECTED
    )
    gate = CANONICAL_REASONING_SERVICE.behavioral_completeness_gate(
        closure=[],
        questions=[],
        scope=ScopeResolution(),
        hypotheses=[hypothesis],
        dispositions=dispositions,
    )
    assert gate.status.value == "PASSED"
