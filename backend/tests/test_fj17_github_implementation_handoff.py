"""FJ-17 discovery-to-GitHub-MCP implementation verification contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.schemas_canonical_test_plan_runtime import (
    AuthorityClass,
    AuthoritySubject,
    BehaviorHypothesis,
    ChangeSurface,
    ChangeSurfaceKind,
    ContractFactSet,
    ContractMode,
    CoverageDisposition,
    CurrentnessState,
    EvidenceLifecycleStatus,
    EvidenceRecord,
    EvidenceSourceType,
    GenerationProfile,
    GitHubBlastRadiusTarget,
    GitHubImplementationInspection,
    GitHubImplementationVerificationHandoff,
    GitHubImplementationVerificationResult,
    GitHubImplementationVerificationStatus,
    GitHubInspectionOutcome,
    GitHubInspectionTarget,
    HypothesisState,
    MissingQuestion,
    ProductContractOwnership,
    ProductOwnership,
    RuntimeEntryPoint,
    RuntimePrincipal,
    ScopeResolution,
    SemanticDimension,
    SourceVisibility,
    VerificationState,
    VersionScope,
)
from app.services.canonical_evidence_service import (
    build_bundle,
    merge_bundles,
    normalize_legacy_packet,
    normalize_trusted_github_implementation_results,
)
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE,
)
from app.services.github_implementation_verification import (
    GITHUB_IMPLEMENTATION_VERIFICATION_SERVICE,
    GitHubImplementationVerificationService,
)
from app.services.canonical_test_plan_runtime import (
    CANONICAL_TEST_PLAN_RUNTIME,
    CanonicalTestPlanRuntime,
)
from app.services.reasoning_evidence_observability import (
    QuestionRetrievalTraceBundle,
    TraceAnswerState,
    get_last_question_retrieval_trace,
    render_question_debug_report,
)
from app.services.test_plan_runtime_adapters import LEGACY_COMPATIBILITY_PROJECTOR


TENANT = "tenant-fj17"
FULL_REVISION = "a" * 40


def _authorized_github_service() -> GitHubImplementationVerificationService:
    return GitHubImplementationVerificationService(
        result_authorizer=lambda record, result, handoff, tenant_id: bool(
            tenant_id == TENANT
            and record.metadata.get("github_mcp_result") is True
            and result.handoff_id == handoff.handoff_id
        )
    )


def _request():
    from app.core.schemas_canonical_test_plan_runtime import GenerationRequest

    return GenerationRequest(
        jira_key="GUIDES-17000",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.CODEX_CANONICAL,
        principal=RuntimePrincipal(
            principal_id="qe-user",
            tenant_id=TENANT,
            roles=["authenticated"],
        ),
        allowed_sources=list(EvidenceSourceType),
    )


def _implementation_record(
    *,
    content: object | None = None,
    revision: str = FULL_REVISION,
    product_version: str = "5.0",
) -> EvidenceRecord:
    return EvidenceRecord(
        source_type=EvidenceSourceType.IMPLEMENTATION_DIFF,
        authority_subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        source_reference="github:AdobeStarling/starling:pull/17000",
        tenant_id=TENANT,
        content=content
        or {
            "changed_files": ["src/main/java/com/adobe/guides/SharedResolver.java"],
            "changed_methods": ["SharedResolver.resolve"],
        },
        product_version=product_version,
        deployment_model="on-prem",
        currentness=CurrentnessState.CURRENT,
        evidence_confidence=1.0,
        requirement_authority=AuthorityClass.IMPLEMENTATION_CONFIRMED,
        verification_status=VerificationState.VERIFIED_REVISION,
        lifecycle_status=EvidenceLifecycleStatus.INSPECTED,
        inspected=True,
        retrieval_pass="repository-inspection",
        version_scope=VersionScope(
            product_versions=[product_version] if product_version else [],
            repository="AdobeStarling/starling",
            repository_revision=revision,
            deployment_model="on-prem",
        ),
        ownership=ProductOwnership(
            product="AEM Guides",
            repository="AdobeStarling/starling",
            contract_ownership=(
                ProductContractOwnership.CURRENT_IMPLEMENTATION_EVIDENCE
            ),
        ),
        visibility=SourceVisibility(tenant_id=TENANT),
    )


def _question_and_hypothesis() -> tuple[MissingQuestion, BehaviorHypothesis]:
    question = MissingQuestion(
        question="Which consumers read or use SharedResolver.resolve?",
        dimension=SemanticDimension.DIRECT_CONSUMERS,
        authority_subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        target_source_types=[
            EvidenceSourceType.CURRENT_PR,
            EvidenceSourceType.IMPLEMENTATION_DIFF,
            EvidenceSourceType.CURRENT_CODE,
        ],
        source_closure_ids=["closure:11111111111111111111111111111111"],
    )
    hypothesis = BehaviorHypothesis(
        statement=question.question,
        state=HypothesisState.UNRESOLVED,
        derived_from_question_id=question.question_id,
    )
    return question, hypothesis


def _handoff() -> GitHubImplementationVerificationHandoff:
    question, hypothesis = _question_and_hypothesis()
    evidence = _implementation_record()
    return GITHUB_IMPLEMENTATION_VERIFICATION_SERVICE.create_handoffs(
        request=_request(),
        scope=ScopeResolution(
            product_versions=["5.0"], deployment_modes=["on-prem"]
        ),
        surfaces=[
            ChangeSurface(
                kind=ChangeSurfaceKind.CHANGED_ENTITY,
                entity="src/main/java/com/adobe/guides/SharedResolver.java",
                source_evidence_ids=[evidence.evidence_id],
                confidence=1.0,
            )
        ],
        evidence=build_bundle([evidence], tenant_id=TENANT),
        questions=[question],
        hypotheses=[hypothesis],
    )[0]


def _inspection(*, shared: bool = False) -> GitHubImplementationInspection:
    negative_targets = (
        set()
        if shared
        else {GitHubInspectionTarget.SHARED_RESOLVER_USAGE}
    )
    return GitHubImplementationInspection(
        pr_diff_refs=[f"AdobeStarling/starling#17000@{FULL_REVISION}"],
        changed_files=["src/main/java/com/adobe/guides/SharedResolver.java"],
        changed_classes=["SharedResolver"],
        changed_methods=["SharedResolver.resolve"],
        blast_radius_contract="VALUE_DATA_STATE_FLOW_V2",
        changed_symbols=["SharedResolver.resolve"],
        produced_values=["ResolvedPreset"],
        state_writes=["PublishState.resolvedPreset"],
        state_reads=["NativePdfConsumer reads PublishState.resolvedPreset"],
        data_flow_edges=[
            "SharedResolver.resolve -> PublishState.resolvedPreset -> NativePdfConsumer"
        ],
        direct_callers=["PublishService.publish"],
        transitive_callers=["PublishApi -> PublishService.publish"],
        upstream_callers=["PublishService.publish"],
        downstream_consumers=["NativePdfConsumer.consume"],
        shared_resolver_usage=(
            ["NativePdfConsumer -> SharedResolver.resolve"] if shared else []
        ),
        shared_abstractions=[
            "SharedResolver" if shared else "SeparateResolver"
        ],
        sibling_implementations=["AemSitesConsumer.consume"],
        alternate_entry_points=["PublishApi.bulkPublish"],
        output_type_consumers=["Native PDF"],
        configuration_branches=["on-prem"],
        feature_flags=["none"],
        role_branches=["publisher-role"],
        cross_repo_consumers=["BlueJay/jui-app:NativePdfConsumer"],
        tests_changed_or_added=["SharedResolverTest"],
        missing_tests=["AEM Sites shared resolver regression"],
        tests_found=["SharedResolverTest"],
        missing_test_areas=["AEM Sites shared resolver regression"],
        shared_path_evidence=(
            ["NativePdfConsumer calls the changed shared path"] if shared else []
        ),
        unrelated_path_evidence=(
            [] if shared else ["The target consumer calls SeparateResolver.resolve"]
        ),
        completed_targets=list(GitHubInspectionTarget),
        target_outcomes={
            target: (
                GitHubInspectionOutcome.NONE_FOUND
                if target in negative_targets
                else GitHubInspectionOutcome.FOUND
            )
            for target in GitHubInspectionTarget
        },
        negative_search_evidence={
            target: ["No matching shared-resolver call was found in the pinned revision."]
            for target in negative_targets
        },
        blast_radius_completed_targets=list(GitHubBlastRadiusTarget),
        blast_radius_target_outcomes={
            target: (
                GitHubInspectionOutcome.NONE_FOUND
                if target == GitHubBlastRadiusTarget.UNCERTAIN_RELATIONSHIPS
                else GitHubInspectionOutcome.FOUND
            )
            for target in GitHubBlastRadiusTarget
        },
        blast_radius_negative_search_evidence={
            GitHubBlastRadiusTarget.UNCERTAIN_RELATIONSHIPS: [
                "No unresolved traversal edge remained at the pinned revision."
            ]
        },
    )


def _result_record(
    status: GitHubImplementationVerificationStatus,
) -> tuple[GitHubImplementationVerificationHandoff, EvidenceRecord]:
    handoff = _handoff()
    result = GitHubImplementationVerificationResult(
        handoff_id=handoff.handoff_id,
        question_id=handoff.question_id,
        hypothesis_id=handoff.hypothesis_id,
        trace_id=handoff.trace_id,
        status=status,
        applicability_rationale=(
            "The requested output reaches the changed shared resolver."
            if status
            == GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED
            else "The requested output uses a separate resolver path."
            if status == GitHubImplementationVerificationStatus.UNRELATED_PATH
            else "The relationship could not be proven from the available revision."
        ),
        inspection=_inspection(
            shared=(
                status
                == GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED
            )
        ),
        verified_context=handoff.jira_pr_context,
        source_references=(
            ["github:AdobeStarling/starling:pull/17000"]
            if status
            in {
                GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED,
                GitHubImplementationVerificationStatus.UNRELATED_PATH,
            }
            else []
        ),
        repository_revisions=(
            [FULL_REVISION]
            if status
            in {
                GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED,
                GitHubImplementationVerificationStatus.UNRELATED_PATH,
            }
            else []
        ),
        primary_repository_revision=(
            FULL_REVISION
            if status
            in {
                GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED,
                GitHubImplementationVerificationStatus.UNRELATED_PATH,
            }
            else ""
        ),
        implementation_truth=(
            status
            in {
                GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED,
                GitHubImplementationVerificationStatus.UNRELATED_PATH,
            }
        ),
    )
    record = _implementation_record(
        content=result.model_dump(mode="json", by_alias=True),
    ).model_copy(
        update={
            "retrieval_pass": "github-mcp-implementation-verification",
            "metadata": {"github_mcp_result": True},
        }
    )
    return handoff, record


def test_fj17_handoff_serializes_full_contract_and_is_deterministic() -> None:
    first = _handoff()
    second = _handoff()
    payload = first.model_dump(mode="json", by_alias=True)

    assert first.handoff_id == second.handoff_id
    assert first.trace_id == second.trace_id
    assert {
        "QUESTION_ID",
        "HYPOTHESIS_ID",
        "IMPLEMENTATION_QUESTION",
        "EXPECTED_CHANGE_SURFACE",
        "SYMBOLS_OR_PATHS_IF_KNOWN",
        "WHY_CODE_VERIFICATION_REQUIRED",
        "JIRA_PR_CONTEXT",
        "TRACE_ID",
    } <= set(payload)
    assert set(payload["INSPECTION_SCOPE"]) == {
        target.value for target in GitHubInspectionTarget
    }
    assert payload["BLAST_RADIUS_CONTRACT"] == "VALUE_DATA_STATE_FLOW_V2"
    assert set(payload["BLAST_RADIUS_SCOPE"]) == {
        target.value for target in GitHubBlastRadiusTarget
    }
    assert payload["ACCEPTANCE_AUTHORITY"] is False
    assert payload["AUTHORITY_SUBJECT"] == "ACTUAL_IMPLEMENTATION"
    assert set(payload["SYMBOLS_OR_PATHS_IF_KNOWN"]) == {
        "SharedResolver.resolve",
        "src/main/java/com/adobe/guides/SharedResolver.java",
    }
    round_tripped = GitHubImplementationVerificationHandoff.model_validate(
        json.loads(json.dumps(payload))
    )
    assert round_tripped.handoff_id == first.handoff_id
    assert round_tripped.model_dump(mode="json") == first.model_dump(mode="json")


def test_legacy_v1_handoff_identity_remains_backward_compatible() -> None:
    payload = _handoff().model_dump(mode="json", by_alias=True)
    payload["HANDOFF_ID"] = ""
    payload.pop("BLAST_RADIUS_CONTRACT")
    payload.pop("BLAST_RADIUS_SCOPE")
    legacy = GitHubImplementationVerificationHandoff.model_validate(payload)
    legacy_payload = legacy.model_dump(mode="json", by_alias=True)
    legacy_payload.pop("BLAST_RADIUS_CONTRACT")
    legacy_payload.pop("BLAST_RADIUS_SCOPE")

    round_tripped = GitHubImplementationVerificationHandoff.model_validate(
        legacy_payload
    )
    assert round_tripped.handoff_id == legacy.handoff_id
    assert round_tripped.blast_radius_contract == "LEGACY_V1"


def test_legacy_v1_result_identity_remains_backward_compatible() -> None:
    handoff_payload = _handoff().model_dump(mode="json", by_alias=True)
    handoff_payload["HANDOFF_ID"] = ""
    handoff_payload.pop("BLAST_RADIUS_CONTRACT")
    handoff_payload.pop("BLAST_RADIUS_SCOPE")
    handoff = GitHubImplementationVerificationHandoff.model_validate(
        handoff_payload
    )
    inspection_payload = _inspection(shared=True).model_dump(
        mode="json", by_alias=True
    )
    v2_fields = {
        "BLAST_RADIUS_CONTRACT",
        "CHANGED_SYMBOLS",
        "PRODUCED_VALUES",
        "STATE_WRITES",
        "STATE_READS",
        "DATA_FLOW_EDGES",
        "DIRECT_CALLERS",
        "TRANSITIVE_CALLERS",
        "SHARED_ABSTRACTIONS",
        "SIBLING_IMPLEMENTATIONS",
        "ALTERNATE_ENTRY_POINTS",
        "ROLE_BRANCHES",
        "CROSS_REPO_CONSUMERS",
        "TESTS_FOUND",
        "MISSING_TEST_AREAS",
        "UNCERTAIN_RELATIONSHIPS",
        "BLAST_RADIUS_COMPLETED_TARGETS",
        "BLAST_RADIUS_TARGET_OUTCOMES",
        "BLAST_RADIUS_NEGATIVE_SEARCH_EVIDENCE",
    }
    for field in v2_fields:
        inspection_payload.pop(field)
    inspection = GitHubImplementationInspection.model_validate(inspection_payload)
    legacy = GitHubImplementationVerificationResult(
        handoff_id=handoff.handoff_id,
        question_id=handoff.question_id,
        hypothesis_id=handoff.hypothesis_id,
        trace_id=handoff.trace_id,
        status=GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED,
        applicability_rationale="The shared path is proven at the pinned revision.",
        inspection=inspection,
        verified_context=handoff.jira_pr_context,
        source_references=handoff.jira_pr_context.pull_request_references,
        repository_revisions=[FULL_REVISION],
        primary_repository_revision=FULL_REVISION,
        implementation_truth=True,
    )
    payload = legacy.model_dump(mode="json", by_alias=True)
    for field in v2_fields:
        payload["INSPECTION"].pop(field)

    round_tripped = GitHubImplementationVerificationResult.model_validate(payload)
    assert round_tripped.result_id == legacy.result_id
    assert round_tripped.inspection.blast_radius_contract == "LEGACY_V1"


def test_pfix05_value_data_state_flow_contract_is_complete_and_typed() -> None:
    inspection = _inspection(shared=True)
    payload = inspection.model_dump(mode="json", by_alias=True)

    assert set(payload["BLAST_RADIUS_TARGET_OUTCOMES"]) == {
        target.value for target in GitHubBlastRadiusTarget
    }
    assert payload["CHANGED_SYMBOLS"]
    assert payload["PRODUCED_VALUES"]
    assert payload["STATE_WRITES"]
    assert payload["STATE_READS"]
    assert payload["DATA_FLOW_EDGES"]
    assert payload["DIRECT_CALLERS"]
    assert payload["TRANSITIVE_CALLERS"]
    assert payload["DOWNSTREAM_CONSUMERS"]
    assert payload["SHARED_ABSTRACTIONS"]
    assert payload["SIBLING_IMPLEMENTATIONS"]
    assert payload["ALTERNATE_ENTRY_POINTS"]
    assert payload["CONFIGURATION_BRANCHES"]
    assert payload["FEATURE_FLAGS"]
    assert payload["ROLE_BRANCHES"]
    assert payload["CROSS_REPO_CONSUMERS"]
    assert payload["TESTS_FOUND"]
    assert payload["MISSING_TEST_AREAS"]


def test_pfix05_not_found_requires_completed_bounded_negative_search() -> None:
    payload = _inspection(shared=True).model_dump(mode="json", by_alias=True)
    payload["BLAST_RADIUS_TARGET_OUTCOMES"]["DIRECT_CALLERS"] = "NONE_FOUND"
    payload["DIRECT_CALLERS"] = []

    with pytest.raises(
        ValidationError,
        match="NONE_FOUND blast-radius outcome requires bounded negative search",
    ):
        GitHubImplementationInspection.model_validate(payload)


@pytest.mark.parametrize(
    "credential_shaped_text",
    [
        "Bearer abcdefghijklmnop",
        "github_pat_0123456789abcdef",
        "https://user:password@example.invalid/repo",
        "https://example.invalid/repo?X-Amz-Signature=abcdef",
    ],
)
def test_fj17_handoff_rejects_credential_shaped_text(
    credential_shaped_text: str,
) -> None:
    payload = _handoff().model_dump(mode="json", by_alias=True)
    payload["HANDOFF_ID"] = ""
    payload["IMPLEMENTATION_QUESTION"] = credential_shaped_text

    with pytest.raises(ValidationError, match="cannot contain credentials"):
        GitHubImplementationVerificationHandoff.model_validate(payload)


def test_fj17_only_material_actual_implementation_question_creates_handoff() -> None:
    question, hypothesis = _question_and_hypothesis()
    product_question = MissingQuestion(
        question="What visible behavior is accepted?",
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
    )
    product_hypothesis = BehaviorHypothesis(
        statement=product_question.question,
        state=HypothesisState.UNRESOLVED,
        derived_from_question_id=product_question.question_id,
    )
    evidence = _implementation_record()
    handoffs = GITHUB_IMPLEMENTATION_VERIFICATION_SERVICE.create_handoffs(
        request=_request(),
        scope=ScopeResolution(),
        surfaces=[],
        evidence=build_bundle([evidence], tenant_id=TENANT),
        questions=[question, product_question],
        hypotheses=[hypothesis, product_hypothesis],
    )
    assert [row.question_id for row in handoffs] == [question.question_id]


def test_fj17_unknown_change_surface_still_emits_a_bounded_handoff() -> None:
    question, hypothesis = _question_and_hypothesis()

    handoffs = GITHUB_IMPLEMENTATION_VERIFICATION_SERVICE.create_handoffs(
        request=_request(),
        scope=ScopeResolution(),
        surfaces=[],
        evidence=build_bundle([], tenant_id=TENANT),
        questions=[question],
        hypotheses=[hypothesis],
    )

    assert len(handoffs) == 1
    assert handoffs[0].expected_change_surface == []
    assert handoffs[0].symbols_or_paths_if_known == []


@pytest.mark.parametrize(
    ("status", "expected_state", "expected_disposition"),
    [
        (
            GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED,
            HypothesisState.CONFIRMED,
            CoverageDisposition.IMPLEMENTATION_ORACLE,
        ),
        (
            GitHubImplementationVerificationStatus.UNRELATED_PATH,
            HypothesisState.REJECTED,
            CoverageDisposition.INVESTIGATED_AND_REJECTED,
        ),
        (
            GitHubImplementationVerificationStatus.AMBIGUOUS,
            HypothesisState.UNRESOLVED,
            CoverageDisposition.OPEN_QUESTION,
        ),
        (
            GitHubImplementationVerificationStatus.UNAVAILABLE,
            HypothesisState.UNRESOLVED,
            CoverageDisposition.OPEN_QUESTION,
        ),
    ],
)
def test_fj17_result_maps_to_terminal_qe_disposition_but_never_acceptance(
    status: GitHubImplementationVerificationStatus,
    expected_state: HypothesisState,
    expected_disposition: CoverageDisposition,
) -> None:
    question, hypothesis = _question_and_hypothesis()
    handoff, result_record = _result_record(status)
    batch = _authorized_github_service().apply_results(
        scope=ScopeResolution(
            product_versions=["5.0"], deployment_modes=["on-prem"]
        ),
        evidence=build_bundle([result_record], tenant_id=TENANT),
        handoffs=[handoff],
        hypotheses=[hypothesis],
    )
    updated = batch.hypotheses[0]
    assert updated.state == expected_state
    assert result_record.evidence_id in updated.verification_evidence_ids
    assert updated.verification_origin_hypothesis_id == hypothesis.hypothesis_id

    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        ContractFactSet(contract_mode=ContractMode.HUMAN_ACCEPTED_CONTRACT),
        closure=[],
        impacts=[],
        hypotheses=batch.hypotheses,
        scope=ScopeResolution(),
        questions=[question],
    )
    assert len(dispositions) == 1
    assert dispositions[0].disposition == expected_disposition
    candidates = CANONICAL_REASONING_SERVICE.resolve_acceptance_contract(
        ContractFactSet(contract_mode=ContractMode.HUMAN_ACCEPTED_CONTRACT),
        dispositions,
        [question],
    )
    assert candidates == []


def test_fj17_result_identity_or_authority_mismatch_fails_closed() -> None:
    question, hypothesis = _question_and_hypothesis()
    handoff, result_record = _result_record(
        GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED
    )
    spoofed = result_record.model_copy(
        update={
            "requirement_authority": AuthorityClass.TECHNICALLY_INFERRED,
            "retrieval_pass": "reasoning-directed-provider",
        }
    )
    batch = _authorized_github_service().apply_results(
        scope=ScopeResolution(product_versions=["5.0"]),
        evidence=build_bundle([spoofed], tenant_id=TENANT),
        handoffs=[handoff],
        hypotheses=[hypothesis],
    )
    assert batch.hypotheses[0].state == HypothesisState.UNRESOLVED
    assert batch.applied_results == []
    assert batch.unresolved_handoff_ids == [handoff.handoff_id]


def test_fj17_result_cannot_switch_the_requested_pr_context() -> None:
    question, hypothesis = _question_and_hypothesis()
    handoff, result_record = _result_record(
        GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED
    )
    payload = dict(result_record.content)
    payload["RESULT_ID"] = ""
    payload["VERIFIED_CONTEXT"] = {
        **payload["VERIFIED_CONTEXT"],
        "PULL_REQUEST_REFERENCES": [
            "github:AdobeStarling/unrelated:pull/99999"
        ],
    }
    payload["SOURCE_REFERENCES"] = [
        "github:AdobeStarling/unrelated:pull/99999"
    ]
    switched = GitHubImplementationVerificationResult.model_validate(payload)
    switched_record = _implementation_record(
        content=switched.model_dump(mode="json", by_alias=True)
    ).model_copy(
        update={
            "retrieval_pass": "github-mcp-implementation-verification",
            "metadata": {"github_mcp_result": True},
        }
    )

    batch = _authorized_github_service().apply_results(
        scope=ScopeResolution(
            product_versions=["5.0"], deployment_modes=["on-prem"]
        ),
        evidence=build_bundle([switched_record], tenant_id=TENANT),
        handoffs=[handoff],
        hypotheses=[hypothesis],
    )

    assert batch.applied_results == []
    assert batch.hypotheses[0].state == HypothesisState.UNRESOLVED
    assert switched_record.evidence_id in batch.rejected_result_evidence_ids


def test_fj17_schema_rejects_terminal_claim_without_revision_proof() -> None:
    handoff = _handoff()
    with pytest.raises(ValidationError):
        GitHubImplementationVerificationResult(
            handoff_id=handoff.handoff_id,
            question_id=handoff.question_id,
            hypothesis_id=handoff.hypothesis_id,
            trace_id=handoff.trace_id,
            status=(
                GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED
            ),
            applicability_rationale="A shared path was claimed.",
            inspection=_inspection(shared=True),
            verified_context=handoff.jira_pr_context,
            implementation_truth=True,
        )


def test_fj17_shared_path_requires_positive_structural_findings() -> None:
    handoff = _handoff()
    negative_inspection = GitHubImplementationInspection(
        completed_targets=list(GitHubInspectionTarget),
        target_outcomes={
            target: GitHubInspectionOutcome.NONE_FOUND
            for target in GitHubInspectionTarget
        },
        negative_search_evidence={
            target: [f"No {target.value.casefold()} evidence was found at the revision."]
            for target in GitHubInspectionTarget
        },
        shared_path_evidence=["Uncorroborated shared-path assertion."],
    )

    with pytest.raises(ValidationError, match="found shared resolver and consumer"):
        GitHubImplementationVerificationResult(
            handoff_id=handoff.handoff_id,
            question_id=handoff.question_id,
            hypothesis_id=handoff.hypothesis_id,
            trace_id=handoff.trace_id,
            status=GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED,
            applicability_rationale="A shared path was claimed without code findings.",
            inspection=negative_inspection,
            verified_context=handoff.jira_pr_context,
            source_references=handoff.jira_pr_context.pull_request_references,
            repository_revisions=[FULL_REVISION],
            primary_repository_revision=FULL_REVISION,
            implementation_truth=True,
        )


def test_fj17_terminal_result_requires_full_revision_and_exact_pr_binding() -> None:
    handoff = _handoff()
    common = {
        "handoff_id": handoff.handoff_id,
        "question_id": handoff.question_id,
        "hypothesis_id": handoff.hypothesis_id,
        "trace_id": handoff.trace_id,
        "status": GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED,
        "applicability_rationale": "The shared path is present in the pinned revision.",
        "inspection": _inspection(shared=True),
        "verified_context": handoff.jira_pr_context,
        "implementation_truth": True,
    }

    with pytest.raises(ValidationError, match="full immutable commit hashes"):
        GitHubImplementationVerificationResult(
            **common,
            source_references=handoff.jira_pr_context.pull_request_references,
            repository_revisions=["abc1234"],
            primary_repository_revision="abc1234",
        )

    with pytest.raises(ValidationError, match="match the verified PR context"):
        GitHubImplementationVerificationResult(
            **common,
            source_references=["github:AdobeStarling/unrelated:pull/99999"],
            repository_revisions=[FULL_REVISION],
            primary_repository_revision=FULL_REVISION,
        )


def test_fj17_handoff_bounds_large_change_surface_sets_without_crashing() -> None:
    question, hypothesis = _question_and_hypothesis()
    evidence = _implementation_record()
    surfaces = [
        ChangeSurface(
            kind=ChangeSurfaceKind.CHANGED_ENTITY,
            entity=f"src/main/java/com/adobe/guides/Changed{index:02d}.java",
            source_evidence_ids=[evidence.evidence_id],
            confidence=1.0 - (index / 100),
        )
        for index in range(25)
    ]

    handoff = GITHUB_IMPLEMENTATION_VERIFICATION_SERVICE.create_handoffs(
        request=_request(),
        scope=ScopeResolution(product_versions=["5.0"], deployment_modes=["on-prem"]),
        surfaces=surfaces,
        evidence=build_bundle([evidence], tenant_id=TENANT),
        questions=[question],
        hypotheses=[hypothesis],
    )[0]

    assert len(handoff.expected_change_surface) == 20
    assert handoff.omitted_change_surface_count == 5


def test_fj17_result_candidates_are_quarantined_from_behavior_graph() -> None:
    candidate = _implementation_record(
        content={
            "SCHEMA_VERSION": (
                "aem-guides-github-implementation-verification-result-v1"
            ),
            "entity": "InjectedSource",
            "callers": ["InjectedCaller"],
        }
    ).model_copy(
        update={
            "retrieval_pass": "github-mcp-implementation-verification",
            "metadata": {"github_mcp_result": True},
        }
    )

    graph = CANONICAL_REASONING_SERVICE.build_behavior_graph(
        build_bundle([candidate], tenant_id=TENANT),
        ContractFactSet(
            contract_mode=ContractMode.INSUFFICIENT_EVIDENCE_FOR_CONTRACT
        ),
        [],
    )

    assert not any(
        candidate.evidence_id in node.source_evidence_ids for node in graph.nodes
    )
    assert graph.edges == []


def test_fj17_preexisting_v1_trace_is_migrated_without_trusting_stale_identity() -> None:
    sample = (
        Path(__file__).resolve().parents[2]
        / "analysis"
        / "fluffyjaws"
        / "10_sample_redacted_trace_disabled.json"
    )

    trace = QuestionRetrievalTraceBundle.model_validate_json(
        sample.read_text(encoding="utf-8")
    )

    assert trace.questions
    assert all(
        question.implementation_verification.state
        == TraceAnswerState.NOT_APPLICABLE
        for question in trace.questions
    )


def _accepted_runtime_packet() -> dict[str, object]:
    return {
        "jira_key": "GUIDES-17000",
        "issue": {
            "issue_key": "GUIDES-17000",
            "summary": "The generated output remains correct after the publishing change.",
            "labels": ["accepted_uac"],
            "acceptance_criteria": [
                "The generated output remains correct after the publishing change."
            ],
            "affected_versions": ["5.0"],
            "deployment_model": "on-prem",
        },
        "implementation_diff_evidence": {
            "id": "starling-pr-17000",
            "url": "https://git.example.test/example/repository/pull/17000",
            "commit_sha": FULL_REVISION,
            "changed_files": [
                "src/main/java/com/adobe/guides/SharedResolver.java"
            ],
            "changed_methods": ["SharedResolver.resolve"],
        },
    }


def _runtime_request():
    return CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-17000",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )


def _runtime_result_rows(first_result) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for payload in first_result.output_payload[
        "github_implementation_verification_handoffs"
    ]:
        handoff = GitHubImplementationVerificationHandoff.model_validate(payload)
        result = GitHubImplementationVerificationResult(
            handoff_id=handoff.handoff_id,
            question_id=handoff.question_id,
            hypothesis_id=handoff.hypothesis_id,
            trace_id=handoff.trace_id,
            status=(
                GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED
            ),
            applicability_rationale=(
                "The requested behavior reaches the changed shared implementation path."
            ),
            inspection=_inspection(shared=True),
            verified_context=handoff.jira_pr_context,
            source_references=handoff.jira_pr_context.pull_request_references,
            repository_revisions=[FULL_REVISION],
            primary_repository_revision=FULL_REVISION,
            implementation_truth=True,
        )
        rows.append(result.model_dump(mode="json", by_alias=True))
    return rows


def test_fj17_runtime_emits_deterministic_handoffs_and_pending_review() -> None:
    packet = _accepted_runtime_packet()
    first = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=_runtime_request(), packet=packet
    )
    replay = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=_runtime_request(), packet=packet
    )

    handoffs = first.output_payload[
        "github_implementation_verification_handoffs"
    ]
    assert handoffs
    assert first.status == "needs_human_review"
    assert LEGACY_COMPATIBILITY_PROJECTOR.is_postable(first) is False
    assert first.output_sha256 == replay.output_sha256
    assert handoffs == replay.output_payload[
        "github_implementation_verification_handoffs"
    ]
    assert first.trace.unresolved_implementation_handoff_ids


def test_fj17_trace_retains_only_opaque_implementation_lineage() -> None:
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=_runtime_request(), packet=_accepted_runtime_packet()
    )
    trace = get_last_question_retrieval_trace()

    assert trace is not None
    expected_handoff_ids = {
        row["HANDOFF_ID"]
        for row in result.output_payload[
            "github_implementation_verification_handoffs"
        ]
    }
    traced = [row for row in trace.questions if row.implementation_handoff_ids]
    assert {
        handoff_id
        for row in traced
        for handoff_id in row.implementation_handoff_ids
    } == expected_handoff_ids
    assert all(row.implementation_trace_ids for row in traced)

    serialized = trace.model_dump_json()
    report = render_question_debug_report(trace, traced[0].question_id)
    assert traced[0].implementation_handoff_ids[0] in report
    assert "status=pending" in report
    for private_text in (
        "GUIDES-17000",
        "SharedResolver",
        "src/main/java",
        FULL_REVISION,
    ):
        assert private_text not in serialized
        assert private_text not in report


def test_fj17_normalized_terminal_results_resolve_qe_scope_without_new_ac() -> None:
    packet = _accepted_runtime_packet()
    request = _runtime_request()
    first = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request, packet=packet
    )
    result_rows = _runtime_result_rows(first)

    base = normalize_legacy_packet(packet, tenant_id=TENANT)
    trusted = normalize_trusted_github_implementation_results(
        result_rows,
        tenant_id=TENANT,
        result_verifier=lambda _result, tenant_id: tenant_id == TENANT,
    )
    normalized = merge_bundles([base, trusted], tenant_id=TENANT)
    result_records = [
        row
        for row in normalized.records
        if row.retrieval_pass == "github-mcp-implementation-verification"
    ]
    assert result_records
    assert all(
        row.source_type == EvidenceSourceType.IMPLEMENTATION_DIFF
        and row.authority_subject == AuthoritySubject.ACTUAL_IMPLEMENTATION
        and row.requirement_authority == AuthorityClass.IMPLEMENTATION_CONFIRMED
        and row.verification_status == VerificationState.VERIFIED_REVISION
        for row in result_records
    )

    default_runtime = CANONICAL_TEST_PLAN_RUNTIME.run(request, normalized)
    assert default_runtime.status == "needs_human_review"
    assert default_runtime.output_payload[
        "github_implementation_verification_results"
    ] == []
    assert default_runtime.output_payload[
        "rejected_github_implementation_result_evidence_ids"
    ]

    resolved = CanonicalTestPlanRuntime(
        github_verification_service=_authorized_github_service()
    ).run(request, normalized)
    assert resolved.status == "completed"
    assert not resolved.output_payload[
        "unresolved_github_implementation_handoff_ids"
    ]
    assert len(
        resolved.output_payload["github_implementation_verification_results"]
    ) == len(first.output_payload["github_implementation_verification_handoffs"])
    first_acceptance = {
        row["statement"] for row in first.output_payload["acceptance_candidates"]
    }
    resolved_acceptance = {
        row["statement"]
        for row in resolved.output_payload["acceptance_candidates"]
    }
    assert resolved_acceptance == first_acceptance
    assert all(
        row["disposition"]
        not in {
            CoverageDisposition.ACCEPTANCE_CONTRACT.value,
            CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT.value,
        }
        for row in resolved.output_payload["coverage_dispositions"]
        if row["source_hypothesis_ids"]
    )
    trace = get_last_question_retrieval_trace()
    assert trace is not None
    resolved_questions = [
        row
        for row in trace.questions
        if row.implementation_verifications
        and row.implementation_verification.state == TraceAnswerState.YES
    ]
    assert resolved_questions
    for traced_question in resolved_questions:
        verification_ids = {
            evidence_id
            for hypothesis in traced_question.hypotheses
            for evidence_id in hypothesis.verification_evidence_ids
        }
        references = {
            row.evidence_id: row
            for row in traced_question.local_evidence
            + traced_question.fluffyjaws_evidence
        }
        assert verification_ids
        assert set(traced_question.evidence_used_by_verifier.record_ids) >= (
            verification_ids
        )
        assert all(
            references[evidence_id].used_by_verifier
            for evidence_id in verification_ids
        )


def test_fj17_raw_packet_result_cannot_self_attest_implementation_truth() -> None:
    packet = _accepted_runtime_packet()
    first = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=_runtime_request(), packet=packet
    )
    packet["github_mcp_implementation_verification"] = _runtime_result_rows(first)

    normalized = normalize_legacy_packet(packet, tenant_id=TENANT)

    assert not any(
        row.retrieval_pass == "github-mcp-implementation-verification"
        for row in normalized.records
    )
    assert (
        "GITHUB_MCP_IMPLEMENTATION_VERIFICATION_UNTRUSTED_INPUT"
        in normalized.unavailable_sources
    )


@pytest.mark.parametrize(
    "credential_shaped_proof",
    [
        "Bearer never-print-this",
        "eyJabcdefghijk.abcdefghijk.abcdefghijk",
        "-----BEGIN PRIVATE KEY-----abc-----END PRIVATE KEY-----",
        "[REDACTED]",
    ],
)
def test_fj17_trusted_normalizer_rejects_credential_shaped_proof_before_callback(
    credential_shaped_proof: str,
) -> None:
    first = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=_runtime_request(), packet=_accepted_runtime_packet()
    )
    payload = _runtime_result_rows(first)[0]
    payload["RESULT_ID"] = ""
    payload["SOURCE_REFERENCES"] = [credential_shaped_proof]
    verifier_calls: list[str] = []

    normalized = normalize_trusted_github_implementation_results(
        [payload],
        tenant_id=TENANT,
        result_verifier=lambda result, _tenant_id: (
            verifier_calls.append(result.result_id) or True
        ),
    )

    assert verifier_calls == []
    assert normalized.records == []
    assert normalized.unavailable_sources == [
        "GITHUB_MCP_IMPLEMENTATION_VERIFICATION_REJECTED"
    ]
    assert "never-print-this" not in normalized.model_dump_json()


@pytest.mark.parametrize(
    "status",
    [
        GitHubImplementationVerificationStatus.AMBIGUOUS,
        GitHubImplementationVerificationStatus.UNAVAILABLE,
    ],
)
def test_fj17_ambiguous_or_unavailable_runtime_result_stays_open_and_needs_review(
    status: GitHubImplementationVerificationStatus,
) -> None:
    packet = _accepted_runtime_packet()
    first = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=_runtime_request(), packet=packet
    )
    rows: list[dict[str, object]] = []
    for payload in first.output_payload[
        "github_implementation_verification_handoffs"
    ]:
        handoff = GitHubImplementationVerificationHandoff.model_validate(payload)
        result = GitHubImplementationVerificationResult(
            handoff_id=handoff.handoff_id,
            question_id=handoff.question_id,
            hypothesis_id=handoff.hypothesis_id,
            trace_id=handoff.trace_id,
            status=status,
            applicability_rationale="The code relationship remains unresolved.",
            inspection=GitHubImplementationInspection(
                completed_targets=list(GitHubInspectionTarget),
                target_outcomes={
                    target: GitHubInspectionOutcome.UNAVAILABLE
                    for target in GitHubInspectionTarget
                },
            ),
            verified_context=handoff.jira_pr_context,
            implementation_truth=False,
        )
        rows.append(result.model_dump(mode="json", by_alias=True))
    packet["github_mcp_implementation_verification"] = rows

    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=_runtime_request(), packet=packet
    )
    assert result.status == "needs_human_review"
    assert result.output_payload["unresolved_github_implementation_handoff_ids"]
    assert any(
        row["disposition"] == CoverageDisposition.OPEN_QUESTION.value
        and row["source_hypothesis_ids"]
        for row in result.output_payload["coverage_dispositions"]
    )
    assert LEGACY_COMPATIBILITY_PROJECTOR.is_postable(result) is False
