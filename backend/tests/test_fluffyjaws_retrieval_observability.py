"""FJ-10 end-to-end retrieval observability and offline inspector tests."""

from __future__ import annotations

import asyncio
import json
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    AcceptanceCandidate,
    AcceptancePromotionDecision,
    AuthorityClass,
    AuthoritySubject,
    BehaviorHypothesis,
    CanonicalEvidenceBundle,
    CanonicalRuntimeStage,
    ContractMode,
    CoverageDisposition,
    CoverageDispositionRecord,
    CurrentnessState,
    DirectedRetrievalRecord,
    DomainActivation,
    EvidenceRecord,
    EvidenceSourceType,
    GenerationProfile,
    HypothesisState,
    IssueDomain,
    MissingQuestion,
    PlanSection,
    PromotionStatus,
    RetrievalStatus,
    RuntimeEntryPoint,
    ScopeResolution,
    SourceVisibility,
    StructuredQEPlan,
    VerificationState,
)
from app.services.canonical_test_plan_runtime import CanonicalTestPlanRuntime
from app.services.reasoning_evidence_observability import (
    QUESTION_RETRIEVAL_TRACE_SCHEMA,
    QuestionRetrievalTraceBundle,
    TraceAnswerState,
    TraceCompletionState,
    build_question_retrieval_trace,
    get_last_question_retrieval_trace,
    record_question_retrieval_trace,
    render_question_debug_report,
)
from app.services.reasoning_evidence_provider import (
    EvidenceProviderDescriptor,
    EvidenceProviderCallResult,
    EvidenceProviderExecutor,
    EvidenceProviderRawResult,
    FakeEvidenceProvider,
    ProviderTransportOutcome,
    StrictProviderHit,
)
from app.services.reasoning_evidence_shadow_service import (
    FluffyJawsRuntimeMode,
    FluffyJawsShadowConfig,
    FluffyJawsShadowRunTrace,
    ReasoningEvidenceShadowService,
)
from scripts import inspect_fluffyjaws_question_trace as trace_inspector


inspect_trace_main = trace_inspector.main


_WORKSPACE = Path(__file__).resolve().parents[2]
_BASELINE_CASES = _WORKSPACE / "analysis" / "fluffyjaws" / "00_baseline_cases.jsonl"
_STAMP = "2026-08-30T00:00:00Z"
_SHADOW_RUN_ID = "run:11111111-1111-4111-8111-111111111111"
_TASK_A_RUN_ID = "run:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
_TASK_B_RUN_ID = "run:bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
_FORBIDDEN_DEBUG_KEYS = {
    "authorization",
    "content",
    "cookie",
    "discovery_syntheses",
    "jira_key",
    "metadata",
    "password",
    "principal",
    "query",
    "question",
    "raw_provider_reference",
    "redacted_message",
    "secret",
    "source_location",
    "source_native_id",
    "source_reference",
    "tenant_id",
    "token",
}


def _disabled_service() -> ReasoningEvidenceShadowService:
    return ReasoningEvidenceShadowService(
        config=FluffyJawsShadowConfig(
            mode=FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED
        )
    )


def _baseline_fixture() -> dict[str, Any]:
    row = json.loads(
        next(
            line
            for line in _BASELINE_CASES.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    )
    fixture = row["fixture"]
    assert isinstance(fixture, dict)
    return fixture


def _run_disabled_baseline() -> tuple[Any, QuestionRetrievalTraceBundle]:
    fixture = _baseline_fixture()
    runtime = CanonicalTestPlanRuntime(shadow_service=_disabled_service())
    request = runtime.build_request(
        jira_key=str(fixture["jira_key"]),
        tenant_id="fj10-disabled",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = runtime.generate_backend_compatibility(request=request, packet=fixture)
    trace = get_last_question_retrieval_trace()
    assert trace is not None
    return result, trace


def _walk_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            child_key
            for child in value.values()
            for child_key in _walk_keys(child)
        }
    if isinstance(value, list):
        return {child_key for child in value for child_key in _walk_keys(child)}
    return set()


def _local_record(*, tenant_id: str = "fj10") -> EvidenceRecord:
    return EvidenceRecord(
        source_type=EvidenceSourceType.CURRENT_CODE,
        authority_subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        source_reference=(
            "https://internal.example/Customers/SecretCo/repo?unknown-signature="
            "never-print-this"
        ),
        source_location="C:/customer/SecretCo/private/File.java",
        tenant_id=tenant_id,
        content={
            "text": (
                "customer@example.com 10.0.0.23 Bearer never-print-this "
                "\r\nFORGED-LINE\x1b[31m"
            )
        },
        currentness=CurrentnessState.CURRENT,
        evidence_confidence=0.95,
        requirement_authority=AuthorityClass.IMPLEMENTATION_CONFIRMED,
        verification_status=VerificationState.VERIFIED_SOURCE,
        visibility=SourceVisibility(tenant_id=tenant_id),
    )


def _provider() -> FakeEvidenceProvider:
    descriptor = EvidenceProviderDescriptor(
        provider="fluffyjaws",
        adapter_version="fake-fj10-v1",
        provider_contract_version="fake-fj10-v1",
        supported_domains=list(IssueDomain),
        supported_source_types=[EvidenceSourceType.CURRENT_CODE],
        supported_filters=[
            "authority_requirement",
            "excluded_sources",
            "jira_or_context_reference",
            "max_results",
            "requested_evidence_types",
            "temporal_boundary",
        ],
    )

    def result_factory(query, context) -> EvidenceProviderRawResult:
        call_id = EvidenceProviderExecutor._call_id(
            "fluffyjaws", query.query_id, context.correlation_id
        )
        hit = StrictProviderHit(
            source_type=EvidenceSourceType.CURRENT_CODE,
            source_reference=(
                "https://internal.example/customer/SecretCo?opaque-secret="
                "never-print-this"
            ),
            source_locator="C:/customer/SecretCo/private/Provider.java",
            text=(
                "customer@example.com 10.0.0.23 Bearer never-print-this "
                "\r\nFORGED-LINE\x1b[31m"
            ),
            repository="internal/SecretCo",
            repository_revision="abc123",
            retrieved_at=_STAMP,
            raw_provider_reference=(
                "https://user:password@internal.example/result?token="
                "never-print-this"
            ),
        )
        return EvidenceProviderRawResult(
            provider="fluffyjaws",
            provider_contract_version="fake-fj10-v1",
            provider_call_id=call_id,
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            raw_hits=[hit],
            transport_outcome=ProviderTransportOutcome.COMPLETED,
            started_at=_STAMP,
            completed_at=_STAMP,
            source_snapshot_retrieved_at=_STAMP,
            attempts=1,
            attempt_outcomes=[ProviderTransportOutcome.COMPLETED],
        )

    return FakeEvidenceProvider(descriptor, result_factory=result_factory)


def _shadow_fixture() -> tuple[
    Any,
    MissingQuestion,
    DirectedRetrievalRecord,
    EvidenceRecord,
    FluffyJawsShadowRunTrace,
]:
    service = ReasoningEvidenceShadowService(
        config=FluffyJawsShadowConfig(
            mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW,
            max_questions=5,
        ),
        providers=[_provider()],
        source_visibility_check=lambda _hit: True,
        source_verification_check=lambda _hit: True,
        query_egress_check=lambda _query, _request: True,
    )
    runtime = CanonicalTestPlanRuntime(shadow_service=service)
    request = runtime.build_request(
        jira_key="GUIDES-TRACE",
        tenant_id="fj10",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    local = _local_record()
    bundle = CanonicalEvidenceBundle(tenant_id="fj10", records=[local])
    question = MissingQuestion(
        question=(
            "Inspect customer@example.com for SecretCo at 10.0.0.23 "
            "Bearer never-print-this"
        ),
        authority_subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        target_source_types=[EvidenceSourceType.CURRENT_CODE],
        blocking=True,
    )
    retrieval = DirectedRetrievalRecord(
        question_id=question.question_id,
        query=question.question,
        authority_subject=question.authority_subject,
        target_source_types=question.target_source_types,
        matched_evidence_ids=[local.evidence_id],
        status=RetrievalStatus.USED,
        reason="local source matched",
    )
    trace = service.capture(
        run_id=_SHADOW_RUN_ID,
        request=request,
        evidence=bundle,
        domains=[
            DomainActivation(
                domain=IssueDomain.AUTHORING,
                confidence=1.0,
                evidence_ids=[local.evidence_id],
            )
        ],
        scope=ScopeResolution(primary_product_area="XML Editor"),
        questions=[question],
        local_retrievals=[retrieval],
    )
    assert trace is not None
    assert trace.calls
    return request, question, retrieval, local, trace


def _project_shadow_trace() -> QuestionRetrievalTraceBundle:
    request, question, retrieval, local, shadow_trace = _shadow_fixture()
    hypothesis = BehaviorHypothesis(
        statement="The verified implementation source answers the question.",
        state=HypothesisState.CONFIRMED,
        supporting_evidence_ids=[local.evidence_id],
        derived_from_question_id=question.question_id,
        confidence=0.95,
    )
    disposition = CoverageDispositionRecord(
        candidate="Verified behavior remains regression coverage.",
        disposition=CoverageDisposition.SEMANTIC_REGRESSION,
        source_question_ids=[question.question_id],
        source_hypothesis_ids=[hypothesis.hypothesis_id],
        evidence_ids=[local.evidence_id],
        rationale="The verified hypothesis is applicable but not contract authority.",
    )
    candidate = AcceptanceCandidate(
        statement="A human decision is required before promotion.",
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        in_scope=True,
        observable=True,
        unresolved_decision_ids=[question.question_id],
    )
    promotion = AcceptancePromotionDecision(
        candidate_id=candidate.candidate_id,
        status=PromotionStatus.BLOCKED,
        resulting_disposition=CoverageDisposition.OPEN_QUESTION,
        authority_supported=False,
        scope_established=True,
        observable=True,
        exact_values_supported=True,
        reasons=["human decision required"],
    )
    plan = StructuredQEPlan(
        jira_key="GUIDES-TRACE",
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        sections=[
            PlanSection(
                section_key="product_decisions",
                title="Product decisions required",
                items=["redacted question"],
                source_record_ids=[question.question_id, candidate.candidate_id],
            ),
            PlanSection(
                section_key="semantic_coverage",
                title="Semantic coverage",
                items=["redacted verified coverage"],
                source_record_ids=[disposition.disposition_id],
            ),
        ],
        open_question_ids=[question.question_id],
    )
    return build_question_retrieval_trace(
        run_id=_SHADOW_RUN_ID,
        request=request,
        output_sha256="a" * 64,
        completion_state=TraceCompletionState.COMPLETE,
        questions=[question],
        local_retrievals=[retrieval],
        hypotheses=[hypothesis],
        dispositions=[disposition],
        candidates=[candidate],
        promotions=[promotion],
        structured_plan=plan,
        evidence_records=[local],
        fluffyjaws_mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW,
        fluffyjaws_trace=shadow_trace,
    )


def test_disabled_runtime_records_every_material_question_without_output_change() -> None:
    result, trace = _run_disabled_baseline()

    assert trace.schema_version == QUESTION_RETRIEVAL_TRACE_SCHEMA
    assert trace.run_id == result.run_id
    assert trace.request_id == result.request_id
    assert trace.output_sha256 == result.output_sha256
    assert trace.plan_id is None
    assert trace.plan_id_reason_code == "CANONICAL_PLAN_ID_NOT_DEFINED"
    assert {row.question_id for row in trace.questions} == {
        row["question_id"] for row in result.output_payload["missing_questions"]
    }
    assert trace.questions
    assert all(row.materiality.value in {"P0", "P1"} for row in trace.questions)
    assert all(
        row.question_generated.state == TraceAnswerState.YES
        and row.local_retrieval_executed.state == TraceAnswerState.YES
        and row.fluffyjaws_called.state == TraceAnswerState.NO
        and row.fluffyjaws_status.state == TraceAnswerState.NOT_APPLICABLE
        and row.final_output_location.state == TraceAnswerState.YES
        for row in trace.questions
    )
    assert "QUESTION_RETRIEVAL_TRACE_RECORD_FAILED" not in result.runtime_warnings


def test_allowlisted_projection_answers_full_journey_without_sensitive_content() -> None:
    trace = _project_shadow_trace()
    question = trace.questions[0]
    serialized = trace.model_dump_json()
    payload = trace.model_dump(mode="json")

    assert question.fluffyjaws_called.state == TraceAnswerState.YES
    assert question.fluffyjaws_transport_executed.state == TraceAnswerState.YES
    assert question.fluffyjaws_status.state == TraceAnswerState.YES
    assert question.fluffyjaws_results.state == TraceAnswerState.YES
    assert question.underlying_sources.state == TraceAnswerState.YES
    assert question.evidence_normalized.state == TraceAnswerState.YES
    assert question.evidence_used_by_verifier.state == TraceAnswerState.YES
    assert question.hypothesis_created.state == TraceAnswerState.YES
    assert question.disposition.state == TraceAnswerState.YES
    assert question.coverage_disposition_linkage.state == TraceAnswerState.YES
    assert question.final_output_location.state == TraceAnswerState.YES
    assert question.provider_call_ids
    assert question.evidence_ids
    assert question.hypothesis_ids
    assert question.candidate_ids
    assert question.disposition_ids
    assert question.coverage_dispositions[0].disposition == (
        CoverageDisposition.SEMANTIC_REGRESSION
    )
    assert any(
        row.record_type == "DISPOSITION" for row in question.output_locations
    )
    assert question.provider_calls[0].status.value in {"SUCCESS", "PARTIAL"}
    assert question.fluffyjaws_evidence[0].citation_disclosure.value == "REDACTED"
    assert question.fluffyjaws_evidence[0].used_by_verifier is False

    assert not (_walk_keys(payload) & _FORBIDDEN_DEBUG_KEYS)
    for forbidden in (
        "never-print-this",
        "SecretCo",
        "customer@example.com",
        "10.0.0.23",
        "FORGED-LINE",
        "internal.example",
        "Provider.java",
        "redacted question",
    ):
        assert forbidden not in serialized


def test_report_is_deterministic_content_free_and_marks_unretained_links_unknown() -> None:
    trace = _project_shadow_trace()
    question_id = trace.questions[0].question_id

    first = render_question_debug_report(trace, question_id)
    second = render_question_debug_report(trace, question_id)

    assert first == second
    assert "QUESTION_GENERATED: YES" in first
    assert "LOCAL_RETRIEVAL_EXECUTED: YES" in first
    assert "FLUFFYJAWS_CALLED: YES" in first
    assert "EVIDENCE_NORMALIZED: YES" in first
    assert "HYPOTHESIS_CREATED: YES" in first
    assert "COVERAGE_DISPOSITION_LINKAGE: YES" in first
    assert "disposition=OPEN_QUESTION" in first
    assert "verifier_used=false, fusion=NOT_EVALUATED" in first
    assert "Artifact authenticity: UNVERIFIED_CONTENT_HASH_ONLY" in first
    assert "FINAL_OUTPUT_LOCATION: YES" in first
    assert "Plan ID: unavailable" in first
    assert "never-print-this" not in first
    assert "customer@example.com" not in first
    assert "10.0.0.23" not in first
    assert "\x1b" not in first
    assert "\r" not in first


def test_tampered_shadow_call_linkage_fails_closed() -> None:
    request, question, retrieval, local, shadow_trace = _shadow_fixture()
    payload = shadow_trace.model_dump(mode="json")
    payload["calls"][0]["trace_sidecar"]["question_id"] = "question:" + "0" * 32
    payload["calls"][0]["trace_sidecar"]["trace_id"] = ""
    tampered = FluffyJawsShadowRunTrace.model_validate(payload)

    with pytest.raises(ValueError, match="inconsistent call linkage"):
        build_question_retrieval_trace(
            run_id=_SHADOW_RUN_ID,
            request=request,
            output_sha256="a" * 64,
            completion_state=TraceCompletionState.COMPLETE,
            questions=[question],
            local_retrievals=[retrieval],
            evidence_records=[local],
            fluffyjaws_mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW,
            fluffyjaws_trace=tampered,
        )


def test_shadow_provider_evidence_cannot_claim_verifier_use() -> None:
    request, question, retrieval, local, shadow_trace = _shadow_fixture()
    provider_evidence_id = shadow_trace.calls[0].evidence_records[0].evidence_id
    hypothesis = BehaviorHypothesis(
        statement="An invalid shadow-only claim.",
        state=HypothesisState.CONFIRMED,
        supporting_evidence_ids=[provider_evidence_id],
        derived_from_question_id=question.question_id,
        confidence=0.9,
    )

    with pytest.raises(ValueError, match="SHADOW provider evidence"):
        build_question_retrieval_trace(
            run_id=_SHADOW_RUN_ID,
            request=request,
            output_sha256="a" * 64,
            completion_state=TraceCompletionState.COMPLETE,
            questions=[question],
            local_retrievals=[retrieval],
            hypotheses=[hypothesis],
            evidence_records=[local],
            fluffyjaws_mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW,
            fluffyjaws_trace=shadow_trace,
        )


def test_trace_mode_and_tenant_visibility_mismatches_fail_closed() -> None:
    request, question, retrieval, local, shadow_trace = _shadow_fixture()

    with pytest.raises(ValueError, match="mode does not match"):
        build_question_retrieval_trace(
            run_id=_SHADOW_RUN_ID,
            request=request,
            output_sha256="a" * 64,
            completion_state=TraceCompletionState.COMPLETE,
            questions=[question],
            local_retrievals=[retrieval],
            evidence_records=[local],
            fluffyjaws_mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS,
            fluffyjaws_trace=shadow_trace,
        )

    with pytest.raises(ValueError, match="outside request visibility"):
        build_question_retrieval_trace(
            run_id=_SHADOW_RUN_ID,
            request=request,
            output_sha256="a" * 64,
            completion_state=TraceCompletionState.COMPLETE,
            questions=[question],
            local_retrievals=[retrieval],
            evidence_records=[_local_record(tenant_id="another-tenant")],
            fluffyjaws_mode=FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED,
        )


def test_local_retrieval_cannot_disclose_unavailable_evidence_id() -> None:
    request, question, retrieval, local, _shadow_trace = _shadow_fixture()
    payload = retrieval.model_dump(mode="json")
    payload["retrieval_id"] = ""
    payload["matched_evidence_ids"] = ["ev:CURRENT_CODE:" + "f" * 32]
    forged_retrieval = DirectedRetrievalRecord.model_validate(payload)

    with pytest.raises(ValueError, match="unavailable evidence"):
        build_question_retrieval_trace(
            run_id=_SHADOW_RUN_ID,
            request=request,
            output_sha256="a" * 64,
            completion_state=TraceCompletionState.COMPLETE,
            questions=[question],
            local_retrievals=[forged_retrieval],
            evidence_records=[local],
            fluffyjaws_mode=FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED,
        )


def test_unknown_upstream_error_code_is_not_echoed() -> None:
    request, question, retrieval, local, shadow_trace = _shadow_fixture()
    payload = shadow_trace.model_dump(mode="json")
    call_result_payload = payload["calls"][0]["call_result"]
    call_result_payload["redacted_error_code"] = "CUSTOMER_SECRET_CODE"
    call_result_payload["provider_result_id"] = ""
    rebuilt_result = EvidenceProviderCallResult.model_validate(call_result_payload)
    payload["calls"][0]["call_result"] = rebuilt_result.model_dump(mode="json")
    payload["calls"][0]["trace_sidecar"]["provider_result_id"] = (
        rebuilt_result.provider_result_id
    )
    payload["calls"][0]["trace_sidecar"]["trace_id"] = ""
    with_unknown_code = FluffyJawsShadowRunTrace.model_validate(payload)

    trace = build_question_retrieval_trace(
        run_id=_SHADOW_RUN_ID,
        request=request,
        output_sha256="a" * 64,
        completion_state=TraceCompletionState.COMPLETE,
        questions=[question],
        local_retrievals=[retrieval],
        evidence_records=[local],
        fluffyjaws_mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW,
        fluffyjaws_trace=with_unknown_code,
    )

    assert trace.questions[0].provider_calls[0].safe_error_code == (
        "UNSAFE_PROVIDER_ERROR_CODE_REDACTED"
    )
    assert "CUSTOMER_SECRET_CODE" not in trace.model_dump_json()


def test_persisted_trace_rejects_removed_questions_and_free_form_tokens() -> None:
    trace = _project_shadow_trace()

    removed = trace.model_dump(mode="json")
    removed["trace_id"] = ""
    removed["questions"] = []
    with pytest.raises(ValueError, match="manifest must equal"):
        QuestionRetrievalTraceBundle.model_validate(removed)

    injected = trace.model_dump(mode="json")
    injected["trace_id"] = ""
    injected["questions"][0]["why_generated"]["reason_codes"] = [
        "CUSTOMER_SECRET_CODE"
    ]
    with pytest.raises(ValueError, match="static allowlist"):
        QuestionRetrievalTraceBundle.model_validate(injected)


def test_trace_completion_state_and_failed_stage_must_agree() -> None:
    trace = _project_shadow_trace()

    complete_with_failure = trace.model_dump(mode="json")
    complete_with_failure["trace_id"] = ""
    complete_with_failure["failed_stage"] = (
        CanonicalRuntimeStage.REASONING_DIRECTED_RETRIEVER.value
    )
    with pytest.raises(ValueError, match="complete trace"):
        QuestionRetrievalTraceBundle.model_validate(complete_with_failure)

    partial_without_failure = trace.model_dump(mode="json")
    partial_without_failure["trace_id"] = ""
    partial_without_failure["completion_state"] = TraceCompletionState.PARTIAL.value
    partial_without_failure["failed_stage"] = None
    with pytest.raises(ValueError, match="partial trace"):
        QuestionRetrievalTraceBundle.model_validate(partial_without_failure)


def test_second_pass_provider_call_requires_positive_routing_record() -> None:
    request, question, retrieval, local, shadow_trace = _shadow_fixture()
    payload = shadow_trace.model_dump(mode="json")
    payload["mode"] = FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS.value
    payload["state"] = "SECOND_PASS_PARTIAL"
    second_pass_trace = FluffyJawsShadowRunTrace.model_validate(payload)

    with pytest.raises(ValueError, match="positive routing record"):
        build_question_retrieval_trace(
            run_id=_SHADOW_RUN_ID,
            request=request,
            output_sha256="a" * 64,
            completion_state=TraceCompletionState.COMPLETE,
            questions=[question],
            local_retrievals=[retrieval],
            evidence_records=[local],
            fluffyjaws_mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS,
            fluffyjaws_trace=second_pass_trace,
        )


def test_provider_evidence_cannot_be_reassigned_to_another_question() -> None:
    request, question, retrieval, local, shadow_trace = _shadow_fixture()
    provider_record = shadow_trace.calls[0].evidence_records[0]
    other_question = MissingQuestion(
        question="Which separate behavior remains unresolved?",
        authority_subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        target_source_types=[EvidenceSourceType.CURRENT_CODE],
        blocking=True,
    )
    other_retrieval = DirectedRetrievalRecord(
        question_id=other_question.question_id,
        query=other_question.question,
        authority_subject=other_question.authority_subject,
        target_source_types=other_question.target_source_types,
        matched_evidence_ids=[],
        status=RetrievalStatus.UNAVAILABLE,
        reason="no local source matched",
    )
    forged_hypothesis = BehaviorHypothesis(
        statement="Evidence from the first provider call answers a different question.",
        state=HypothesisState.CONFIRMED,
        supporting_evidence_ids=[provider_record.evidence_id],
        derived_from_question_id=other_question.question_id,
        confidence=0.9,
    )

    with pytest.raises(ValueError, match="different question/call"):
        build_question_retrieval_trace(
            run_id=_SHADOW_RUN_ID,
            request=request,
            output_sha256="a" * 64,
            completion_state=TraceCompletionState.COMPLETE,
            questions=[question, other_question],
            local_retrievals=[retrieval, other_retrieval],
            hypotheses=[forged_hypothesis],
            evidence_records=[local, provider_record],
            fluffyjaws_mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW,
            fluffyjaws_trace=shadow_trace,
        )


def test_runtime_failure_after_question_generation_retains_partial_localization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _baseline_fixture()
    runtime = CanonicalTestPlanRuntime(shadow_service=_disabled_service())
    request = runtime.build_request(
        jira_key=str(fixture["jira_key"]),
        tenant_id="fj10-partial",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )

    def fail_retrieval(*_args: object, **_kwargs: object) -> list[object]:
        raise RuntimeError("Bearer never-print-this\r\nFORGED-LINE")

    monkeypatch.setattr(runtime._reasoning, "retrieve_for_questions", fail_retrieval)
    with pytest.raises(RuntimeError):
        runtime.generate_backend_compatibility(request=request, packet=fixture)

    trace = get_last_question_retrieval_trace()
    assert trace is not None
    assert trace.completion_state == TraceCompletionState.PARTIAL
    assert trace.failed_stage == CanonicalRuntimeStage.REASONING_DIRECTED_RETRIEVER.value
    assert trace.questions
    assert all(
        row.local_retrieval_executed.state == TraceAnswerState.UNKNOWN
        and row.final_output_location.state == TraceAnswerState.UNKNOWN
        for row in trace.questions
    )
    assert "never-print-this" not in trace.model_dump_json()
    assert "FORGED-LINE" not in trace.model_dump_json()
    report = render_question_debug_report(trace, trace.questions[0].question_id)
    assert "Completion: PARTIAL" in report
    assert "Failed stage: ReasoningDirectedRetriever" in report


def test_context_snapshot_is_deep_copied_and_isolated_between_async_tasks() -> None:
    runtime = CanonicalTestPlanRuntime(shadow_service=_disabled_service())

    async def capture(jira_key: str, run_id: str) -> tuple[str, str]:
        request = runtime.build_request(
            jira_key=jira_key,
            tenant_id=f"tenant-{jira_key}",
            entry_point=RuntimeEntryPoint.PYTHON_API,
            generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
        )
        record_question_retrieval_trace(
            run_id=run_id,
            request=request,
            output_sha256="",
            completion_state=TraceCompletionState.PARTIAL,
            failed_stage=CanonicalRuntimeStage.REASONING_DIRECTED_RETRIEVER,
            fluffyjaws_mode=FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED,
        )
        await asyncio.sleep(0)
        trace = get_last_question_retrieval_trace()
        assert trace is not None
        copy = get_last_question_retrieval_trace()
        assert copy is not None and copy is not trace
        return trace.run_id, trace.request_id

    async def run_both() -> list[tuple[str, str]]:
        return list(
            await asyncio.gather(
                capture("GUIDES-A", _TASK_A_RUN_ID),
                capture("GUIDES-B", _TASK_B_RUN_ID),
            )
        )

    rows = asyncio.run(run_both())
    assert [row[0] for row in rows] == [_TASK_A_RUN_ID, _TASK_B_RUN_ID]
    assert rows[0][1] != rows[1][1]


def test_offline_cli_renders_only_valid_allowlisted_trace(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    trace = _project_shadow_trace()
    trace_path = tmp_path / "question-trace.json"
    trace_path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
    original_bytes = trace_path.read_bytes()

    status = inspect_trace_main(
        ["--trace", str(trace_path), "--question-id", trace.questions[0].question_id]
    )
    captured = capsys.readouterr()
    assert status == 0
    assert captured.err == ""
    assert "FluffyJaws question retrieval trace" in captured.out
    assert "never-print-this" not in captured.out
    assert trace_path.read_bytes() == original_bytes

    status = inspect_trace_main(
        ["--trace", str(trace_path), "--question-id", "question:" + "0" * 32]
    )
    captured = capsys.readouterr()
    assert status == 2
    assert captured.out == ""
    assert captured.err == "ERROR: QUESTION_TRACE_INPUT_INVALID\n"

    invalid = tmp_path / "generation-result.json"
    invalid.write_text(
        json.dumps(
            {
                "schema_version": "aem-guides-generation-result-v2",
                "content": "Bearer never-print-this",
            }
        ),
        encoding="utf-8",
    )
    status = inspect_trace_main(
        ["--trace", str(invalid), "--question-id", trace.questions[0].question_id]
    )
    captured = capsys.readouterr()
    assert status == 2
    assert captured.out == ""
    assert captured.err == "ERROR: QUESTION_TRACE_INPUT_INVALID\n"
    assert "never-print-this" not in captured.err
    assert str(invalid) not in captured.err

    malformed = tmp_path / "malformed.json"
    malformed.write_bytes(b"{not-json")
    status = inspect_trace_main(
        ["--trace", str(malformed), "--question-id", trace.questions[0].question_id]
    )
    captured = capsys.readouterr()
    assert status == 2
    assert captured.err == "ERROR: QUESTION_TRACE_INPUT_INVALID\n"

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * ((2 * 1024 * 1024) + 1))
    status = inspect_trace_main(
        ["--trace", str(oversized), "--question-id", trace.questions[0].question_id]
    )
    captured = capsys.readouterr()
    assert status == 2
    assert captured.err == "ERROR: QUESTION_TRACE_INPUT_INVALID\n"


def test_offline_cli_redacts_invalid_arguments(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_argument = "Bearer never-print-this\r\nFORGED-LINE"

    status = inspect_trace_main(["--unknown-secret", secret_argument])
    captured = capsys.readouterr()

    assert status == 2
    assert captured.out == ""
    assert captured.err == "ERROR: QUESTION_TRACE_INPUT_INVALID\n"
    assert secret_argument not in captured.err
    assert "FORGED-LINE" not in captured.err


def test_offline_cli_rejects_remote_drive_before_reading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    trace = _project_shadow_trace()
    trace_path = tmp_path / "question-trace.json"
    trace_path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
    open_attempted = False

    def fail_if_opened(*_args: object, **_kwargs: object) -> object:
        nonlocal open_attempted
        open_attempted = True
        raise AssertionError("remote trace must not be opened")

    monkeypatch.setattr(trace_inspector, "_is_remote_drive", lambda _path: True)
    monkeypatch.setattr(Path, "open", fail_if_opened)

    status = inspect_trace_main(
        ["--trace", str(trace_path), "--question-id", trace.questions[0].question_id]
    )
    captured = capsys.readouterr()

    assert status == 2
    assert captured.out == ""
    assert captured.err == "ERROR: QUESTION_TRACE_INPUT_INVALID\n"
    assert open_attempted is False


def test_offline_cli_rejects_posix_symlink_mode_before_reading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    trace = _project_shadow_trace()
    trace_path = tmp_path / "question-trace.json"
    trace_path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
    open_attempted = False

    class SymlinkStat:
        st_mode = stat.S_IFLNK
        st_file_attributes = 0

    def fake_lstat(_path: object) -> SymlinkStat:
        return SymlinkStat()

    def fail_if_opened(*_args: object, **_kwargs: object) -> object:
        nonlocal open_attempted
        open_attempted = True
        raise AssertionError("symlinked trace must not be opened")

    monkeypatch.setattr(trace_inspector.os, "lstat", fake_lstat)
    monkeypatch.setattr(Path, "open", fail_if_opened)

    status = inspect_trace_main(
        ["--trace", str(trace_path), "--question-id", trace.questions[0].question_id]
    )
    captured = capsys.readouterr()

    assert status == 2
    assert captured.out == ""
    assert captured.err == "ERROR: QUESTION_TRACE_INPUT_INVALID\n"
    assert open_attempted is False


def test_offline_cli_script_runs_from_repository_root(tmp_path: Path) -> None:
    trace = _project_shadow_trace()
    trace_path = tmp_path / "question-trace.json"
    trace_path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
    script = _WORKSPACE / "backend" / "scripts" / "inspect_fluffyjaws_question_trace.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--trace",
            str(trace_path),
            "--question-id",
            trace.questions[0].question_id,
        ],
        cwd=_WORKSPACE,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert "QUESTION_GENERATED" in completed.stdout
