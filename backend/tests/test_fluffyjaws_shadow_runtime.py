"""FJ-06 feature-mode, shadow-sidecar, and plan-neutrality tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    AuthoritySubject,
    CanonicalEvidenceBundle,
    DirectedRetrievalRecord,
    DomainActivation,
    EvidenceSourceType,
    GenerationProfile,
    GenerationRequest,
    IssueDomain,
    MissingQuestion,
    RetrievalStatus,
    RuntimeEntryPoint,
    ScopeResolution,
)
from app.services.canonical_test_plan_runtime import CanonicalTestPlanRuntime
from app.services.reasoning_evidence_provider import (
    DiscoverySynthesis,
    EvidenceProviderDescriptor,
    EvidenceProviderExecutionContext,
    EvidenceProviderExecutor,
    EvidenceProviderRawResult,
    EvidenceProviderRegistry,
    EvidenceProviderStatus,
    FakeEvidenceProvider,
    ProviderCacheState,
    ProviderTransportOutcome,
    StrictProviderHit,
    active_query_filters,
)
from app.services.reasoning_evidence_shadow_service import (
    FLUFFYJAWS_SHADOW_TRACE_SCHEMA,
    FluffyJawsRuntimeMode,
    FluffyJawsShadowConfig,
    ReasoningEvidenceShadowService,
    clear_last_fluffyjaws_shadow_trace,
    get_last_fluffyjaws_shadow_trace,
)


_WORKSPACE = Path(__file__).resolve().parents[2]
_BASELINE_CASES = _WORKSPACE / "analysis" / "fluffyjaws" / "00_baseline_cases.jsonl"
_STAMP = "2026-08-30T00:00:00Z"
_PROVIDER = "fluffyjaws"
_CONTRACT = "fake-fluffyjaws-v1"


def _baseline_record(index: int = 0) -> dict[str, object]:
    records = [
        json.loads(line)
        for line in _BASELINE_CASES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return records[index]


def _disabled_service() -> ReasoningEvidenceShadowService:
    return ReasoningEvidenceShadowService(
        config=FluffyJawsShadowConfig(
            mode=FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED
        )
    )


def _runtime_inputs(index: int = 0):
    record = _baseline_record(index)
    fixture = record["fixture"]
    assert isinstance(fixture, dict)
    runtime = CanonicalTestPlanRuntime(shadow_service=_disabled_service())
    request = runtime.build_request(
        jira_key=str(fixture["jira_key"]),
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    evidence = runtime.normalize_packet(fixture, request=request)
    questions = [
        MissingQuestion.model_validate(row) for row in record["generated_questions"]
    ]
    retrievals = [
        DirectedRetrievalRecord.model_validate(row)
        for row in record["retrieval_queries"]
    ]
    domains = [DomainActivation.model_validate(row) for row in record["domains"]]
    scope = ScopeResolution.model_validate(record["scope"])
    return record, fixture, request, evidence, questions, retrievals, domains, scope


def _descriptor(
    *,
    supported_source_types: list[EvidenceSourceType] | None = None,
    supports_discovery_synthesis: bool = True,
) -> EvidenceProviderDescriptor:
    return EvidenceProviderDescriptor(
        provider=_PROVIDER,
        adapter_version="fake-v1",
        provider_contract_version=_CONTRACT,
        supported_domains=list(IssueDomain),
        supported_source_types=(
            list(EvidenceSourceType)
            if supported_source_types is None
            else supported_source_types
        ),
        supports_discovery_synthesis=supports_discovery_synthesis,
        supported_filters=[
            "authority_requirement",
            "excluded_sources",
            "jira_or_context_reference",
            "max_results",
            "requested_evidence_types",
            "temporal_boundary",
        ],
        maximum_results=100,
    )


def _subject_matches(source_type: EvidenceSourceType, subject: str) -> bool:
    if source_type in {
        EvidenceSourceType.DITA_SPECIFICATION,
        EvidenceSourceType.DITA_OT_DOCUMENTATION,
    }:
        return subject == "DITA_SEMANTICS"
    if source_type in {
        EvidenceSourceType.CURRENT_CODE,
        EvidenceSourceType.CURRENT_PR,
        EvidenceSourceType.IMPLEMENTATION_DIFF,
        EvidenceSourceType.CODE_DIFF,
        EvidenceSourceType.EXISTING_AUTOMATION,
    }:
        return subject == "ACTUAL_IMPLEMENTATION"
    if source_type in {
        EvidenceSourceType.UI_OBSERVATION,
        EvidenceSourceType.OBSERVED_UI_FLOW,
        EvidenceSourceType.SCREENSHOT_REPRODUCTION,
    }:
        return subject == "CURRENT_UI"
    return subject == "PRODUCT_CONTRACT"


def _fake_raw_result(query, context) -> EvidenceProviderRawResult:
    call_id = EvidenceProviderExecutor._call_id(
        _PROVIDER, query.query_id, context.correlation_id
    )
    forbidden_human_types = {
        EvidenceSourceType.ACCEPTED_UAC,
        EvidenceSourceType.ENGINEERING_DECISION,
        EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA,
        EvidenceSourceType.JIRA_DESCRIPTION,
        EvidenceSourceType.PRODUCT_DECISION,
        EvidenceSourceType.CURRENT_JIRA,
        EvidenceSourceType.USER_FEEDBACK,
    }
    source_type = next(
        (
            candidate
            for candidate in query.requested_evidence_types
            if candidate not in forbidden_human_types
            and _subject_matches(
                candidate, query.authority_requirement.subject.value
            )
        ),
        None,
    )
    hits = []
    if source_type is not None:
        source_version = next(
            iter(query.temporal_boundary.version_scope.product_versions), ""
        )
        hits.append(
            StrictProviderHit(
                source_type=source_type,
                source_reference=f"fj-source:{query.question_id}",
                source_locator=f"fj-citation:{query.question_id}",
                text=f"Independent source for {query.question_id}.",
                source_version=source_version,
                rank=1,
                retrieval_score=0.9,
                raw_provider_reference=f"fj-item:{query.question_id}",
            )
        )
    synthesis = DiscoverySynthesis(
        provider=_PROVIDER,
        provider_contract_version=_CONTRACT,
        provider_call_id=call_id,
        query_id=query.query_id,
        correlation_id=context.correlation_id,
        text=f"Discovery-only synthesis for {query.question_id}.",
        raw_provider_reference=f"fj-synthesis:{query.question_id}",
        confidence=0.5,
    )
    return EvidenceProviderRawResult(
        provider=_PROVIDER,
        provider_contract_version=_CONTRACT,
        provider_call_id=call_id,
        raw_provider_reference=f"fj-call:{query.question_id}",
        query_id=query.query_id,
        correlation_id=context.correlation_id,
        raw_hits=hits,
        discovery_syntheses=[synthesis],
        transport_outcome=ProviderTransportOutcome.COMPLETED,
        applied_filters=active_query_filters(query),
        started_at=_STAMP,
        completed_at=_STAMP,
        duration_ms=7,
        cache_state=ProviderCacheState.MISS,
    )


def _fake_provider(*, error: Exception | None = None) -> FakeEvidenceProvider:
    return FakeEvidenceProvider(
        _descriptor(),
        result_factory=None if error is not None else _fake_raw_result,
        error=error,
        provider_contract_version=_CONTRACT,
    )


def _shadow_service(provider: FakeEvidenceProvider) -> ReasoningEvidenceShadowService:
    return ReasoningEvidenceShadowService(
        config=FluffyJawsShadowConfig(
            mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW,
            max_questions=50,
        ),
        providers=[provider],
        source_visibility_check=lambda _hit: True,
        source_verification_check=lambda _hit: True,
        query_egress_check=lambda _query, _request: True,
    )


def test_feature_mode_defaults_to_disabled_and_rejects_invalid_values() -> None:
    assert FluffyJawsShadowConfig.from_environment({}).mode == (
        FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED
    )
    for mode in FluffyJawsRuntimeMode:
        assert FluffyJawsShadowConfig.from_environment(
            {"FLUFFYJAWS_MODE": mode.value}
        ).mode == mode

    for invalid in ("", "shadow", "FLUFFYJAWS_UNKNOWN"):
        with pytest.raises(ValueError):
            FluffyJawsShadowConfig.from_environment({"FLUFFYJAWS_MODE": invalid})


def test_invalid_environment_fails_disabled_without_breaking_the_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FLUFFYJAWS_MODE", "not-a-supported-mode")
    (
        _record,
        _fixture,
        request,
        evidence,
        questions,
        retrievals,
        domains,
        scope,
    ) = _runtime_inputs()
    service = ReasoningEvidenceShadowService()

    trace = service.capture(
        run_id="run-fj06-invalid-config",
        request=request,
        evidence=evidence,
        domains=domains,
        scope=scope,
        questions=questions,
        local_retrievals=retrievals,
    )

    assert service.mode == FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED
    assert trace is not None
    assert trace.state == "CONFIG_UNAVAILABLE"
    assert trace.warning_codes == ["INVALID_SHADOW_CONFIGURATION"]
    assert "not-a-supported-mode" not in trace.model_dump_json()


def test_shadow_rejects_non_fluffyjaws_providers() -> None:
    descriptor = _descriptor().model_copy(update={"provider": "unrelated-provider"})
    provider = FakeEvidenceProvider(
        descriptor,
        result_factory=_fake_raw_result,
        provider_contract_version=_CONTRACT,
    )

    with pytest.raises(ValueError, match="only the fluffyjaws provider"):
        ReasoningEvidenceShadowService(
            config=FluffyJawsShadowConfig(
                mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW
            ),
            providers=[provider],
        )


def test_disabled_mode_never_routes_provider_calls() -> None:
    (
        _record,
        _fixture,
        request,
        evidence,
        questions,
        retrievals,
        domains,
        scope,
    ) = _runtime_inputs()

    provider = _fake_provider()
    service = ReasoningEvidenceShadowService(
        config=FluffyJawsShadowConfig(
            mode=FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED
        ),
        providers=[provider],
        source_visibility_check=lambda _hit: True,
        source_verification_check=lambda _hit: True,
    )
    clear_last_fluffyjaws_shadow_trace()
    trace = service.capture(
        run_id="run-fj06-no-routing",
        request=request,
        evidence=evidence,
        domains=domains,
        scope=scope,
        questions=questions,
        local_retrievals=retrievals,
    )

    assert provider.calls == []
    assert trace is None
    assert get_last_fluffyjaws_shadow_trace() is None


def test_registry_requires_explicit_discovery_only_opt_in() -> None:
    provider = FakeEvidenceProvider(
        _descriptor(supported_source_types=[]),
        result_factory=_fake_raw_result,
        provider_contract_version=_CONTRACT,
    )
    (
        _record,
        _fixture,
        request,
        evidence,
        questions,
        retrievals,
        domains,
        scope,
    ) = _runtime_inputs()
    service = _shadow_service(provider)
    query = service._build_query(
        request=request,
        evidence=evidence,
        scope=scope,
        domains=domains,
        question=questions[0],
        local=retrievals[0],
        materiality=service._materiality(questions[0]),
    )
    registry = EvidenceProviderRegistry([provider], enabled=True)

    assert registry.eligible(query) == []
    assert registry.eligible(query, allow_discovery_only=True) == [provider]


def test_shadow_query_egress_is_denied_by_default() -> None:
    (
        _record,
        _fixture,
        request,
        evidence,
        questions,
        retrievals,
        domains,
        scope,
    ) = _runtime_inputs()
    provider = _fake_provider()
    service = ReasoningEvidenceShadowService(
        config=FluffyJawsShadowConfig(
            mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW
        ),
        providers=[provider],
        source_visibility_check=lambda _hit: True,
        source_verification_check=lambda _hit: True,
    )

    trace = service.capture(
        run_id="run-fj06-egress-denied",
        request=request,
        evidence=evidence,
        domains=domains,
        scope=scope,
        questions=questions,
        local_retrievals=retrievals,
    )

    assert trace is not None
    assert provider.calls == []
    assert trace.metrics.provider_call_count == 0
    assert trace.metrics.recorded_call_count == 0
    assert trace.metrics.internal_error_count == 0
    assert set(trace.skip_reasons.values()) == {"QUERY_EGRESS_POLICY_DENIED"}


@pytest.mark.parametrize("malformed_allow", ["true", 1, object()])
def test_shadow_query_egress_requires_literal_true(malformed_allow) -> None:
    (
        _record,
        _fixture,
        request,
        evidence,
        questions,
        retrievals,
        domains,
        scope,
    ) = _runtime_inputs()
    provider = _fake_provider()
    service = ReasoningEvidenceShadowService(
        config=FluffyJawsShadowConfig(
            mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW
        ),
        providers=[provider],
        source_visibility_check=lambda _hit: True,
        source_verification_check=lambda _hit: True,
        query_egress_check=lambda _query, _request: malformed_allow,
    )

    trace = service.capture(
        run_id="run-fj18-malformed-egress",
        request=request,
        evidence=evidence,
        domains=domains,
        scope=scope,
        questions=questions,
        local_retrievals=retrievals,
    )

    assert trace is not None
    assert provider.calls == []
    assert set(trace.skip_reasons.values()) == {"QUERY_EGRESS_POLICY_DENIED"}


def test_exhausted_source_allowlist_never_becomes_an_unrestricted_query() -> None:
    (
        _record,
        _fixture,
        request,
        evidence,
        _questions,
        _retrievals,
        domains,
        scope,
    ) = _runtime_inputs()
    payload = request.model_dump(
        mode="json",
        exclude={"request_id", "logical_fingerprint"},
    )
    payload["allowed_sources"] = [EvidenceSourceType.CURRENT_CODE.value]
    restricted_request = GenerationRequest.model_validate(payload)
    question = MissingQuestion(
        question="Which official product document defines this behavior?",
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        target_source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    provider = _fake_provider()
    service = _shadow_service(provider)

    trace = service.capture(
        run_id="run-fj06-source-allowlist",
        request=restricted_request,
        evidence=evidence,
        domains=domains,
        scope=scope,
        questions=[question],
        local_retrievals=[],
    )

    assert trace is not None
    assert provider.calls == []
    assert trace.state == "SHADOW_PARTIAL"
    assert trace.skip_reasons == {
        question.question_id: "NO_ALLOWED_TARGET_SOURCE"
    }


def test_missing_provider_is_the_only_config_unavailable_state() -> None:
    (
        _record,
        _fixture,
        request,
        evidence,
        questions,
        retrievals,
        domains,
        scope,
    ) = _runtime_inputs()
    service = ReasoningEvidenceShadowService(
        config=FluffyJawsShadowConfig(
            mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW
        ),
        query_egress_check=lambda _query, _request: True,
    )

    trace = service.capture(
        run_id="run-fj06-provider-unavailable",
        request=request,
        evidence=evidence,
        domains=domains,
        scope=scope,
        questions=questions,
        local_retrievals=retrievals,
    )

    assert trace is not None
    assert trace.state == "CONFIG_UNAVAILABLE"
    assert set(trace.skip_reasons.values()) == {"NO_ELIGIBLE_PROVIDER"}
    assert trace.metrics.provider_call_count == 0


def test_blind_replay_never_dispatches_shadow_queries() -> None:
    record = _baseline_record()
    fixture = record["fixture"]
    assert isinstance(fixture, dict)
    runtime = CanonicalTestPlanRuntime(shadow_service=_disabled_service())
    request = runtime.build_request(
        jira_key=str(fixture["jira_key"]),
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.BENCHMARK_V2,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
        benchmark_version="V2",
        benchmark_split="blind",
        benchmark_record_id="FJ06-BLIND-001",
    )
    evidence = runtime.normalize_packet(fixture, request=request)
    questions = [
        MissingQuestion.model_validate(row) for row in record["generated_questions"]
    ]
    provider = _fake_provider()
    service = _shadow_service(provider)

    trace = service.capture(
        run_id="run-fj06-blind",
        request=request,
        evidence=evidence,
        domains=[],
        scope=ScopeResolution(),
        questions=questions,
        local_retrievals=[],
    )

    assert trace is not None
    assert trace.state == "BLIND_REPLAY_BLOCKED"
    assert trace.warning_codes == ["BLIND_COLLECTOR_NOT_CERTIFIED"]
    assert provider.calls == []


def test_synthesis_success_is_visible_even_without_accepted_source_evidence() -> None:
    (
        _record,
        _fixture,
        request,
        evidence,
        questions,
        retrievals,
        domains,
        scope,
    ) = _runtime_inputs()
    descriptor = _descriptor(
        supported_source_types=[],
        supports_discovery_synthesis=True,
    ).model_copy(update={"supported_filters": []})

    def synthesis_only_result(query, context) -> EvidenceProviderRawResult:
        call_id = EvidenceProviderExecutor._call_id(
            _PROVIDER, query.query_id, context.correlation_id
        )
        synthesis = DiscoverySynthesis(
            provider=_PROVIDER,
            provider_contract_version=_CONTRACT,
            provider_call_id=call_id,
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            text="Trace-only discovery result.",
            raw_provider_reference="fj-synthesis-only",
        )
        return EvidenceProviderRawResult(
            provider=_PROVIDER,
            provider_contract_version=_CONTRACT,
            provider_call_id=call_id,
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            discovery_syntheses=[synthesis],
            transport_outcome=ProviderTransportOutcome.COMPLETED,
            unsupported_filters=active_query_filters(query),
            started_at=_STAMP,
            completed_at=_STAMP,
            duration_ms=11,
        )

    provider = FakeEvidenceProvider(
        descriptor,
        result_factory=synthesis_only_result,
        provider_contract_version=_CONTRACT,
    )
    service = _shadow_service(provider)

    trace = service.capture(
        run_id="run-fj06-synthesis-only",
        request=request,
        evidence=evidence,
        domains=domains,
        scope=scope,
        questions=[questions[0]],
        local_retrievals=[retrievals[0]],
    )

    assert trace is not None
    assert trace.state == "SHADOW_PARTIAL"
    assert trace.metrics.provider_call_count == 1
    assert trace.metrics.error_count == 1
    assert trace.metrics.discovery_success_count == 1
    assert trace.metrics.synthesis_only_call_count == 1
    assert trace.metrics.synthesis_count == 1
    assert trace.calls[0].discovery_syntheses[0].text == (
        "Trace-only discovery result."
    )


def test_shadow_trace_records_metrics_without_entering_the_plan() -> None:
    _record, fixture, _request, _evidence, _questions, *_rest = _runtime_inputs()
    disabled_runtime = CanonicalTestPlanRuntime(shadow_service=_disabled_service())
    disabled_request = disabled_runtime.build_request(
        jira_key=str(fixture["jira_key"]),
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    disabled = disabled_runtime.generate_backend_compatibility(
        request=disabled_request, packet=fixture
    )
    questions = disabled.output_payload["missing_questions"]
    provider = _fake_provider()
    runtime = CanonicalTestPlanRuntime(shadow_service=_shadow_service(provider))
    request = runtime.build_request(
        jira_key=str(fixture["jira_key"]),
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = runtime.generate_backend_compatibility(request=request, packet=fixture)
    trace = get_last_fluffyjaws_shadow_trace()

    assert trace is not None
    assert trace.mode == FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW
    assert trace.metrics.provider_call_count == len(questions)
    assert trace.metrics.provider_call_count == len(provider.calls)
    assert trace.metrics.recorded_call_count == len(questions)
    assert trace.metrics.internal_error_count == 0
    assert trace.metrics.success_count + trace.metrics.empty_count == len(questions)
    assert trace.metrics.error_count == 0
    assert trace.metrics.source_count >= 1
    assert trace.metrics.citation_count >= 1
    assert trace.metrics.unique_evidence_count >= 1
    assert trace.metrics.synthesis_count == len(questions)
    assert trace.metrics.discovery_success_count == len(questions)
    assert trace.metrics.synthesis_only_call_count == trace.metrics.empty_count
    # The resilience boundary reports the greater of adapter-reported and
    # locally measured wall-clock latency.  Scheduler overhead can therefore
    # make a deterministic 7 ms fake appear slower, but never faster.
    assert trace.metrics.total_latency_ms >= len(questions) * 7
    assert trace.metrics.minimum_latency_ms >= 7
    assert trace.metrics.maximum_latency_ms >= trace.metrics.minimum_latency_ms
    assert trace.metrics.mean_latency_ms >= 7.0
    assert trace.metrics.mean_latency_ms <= trace.metrics.maximum_latency_ms
    shadow_ids = {
        evidence_id
        for call in trace.calls
        for evidence_id in call.call_result.accepted_evidence_ids
    }
    assert shadow_ids
    assert shadow_ids.isdisjoint(
        row.evidence_id for row in result.evidence_bundle.records
    )
    serialized = result.model_dump_json()
    assert FLUFFYJAWS_SHADOW_TRACE_SCHEMA not in serialized
    assert all(
        evidence_id not in serialized for evidence_id in shadow_ids
    )
    assert result.output_sha256 == disabled.output_sha256
    assert result.rendered_output == disabled.rendered_output


def test_shadow_metrics_distinguish_local_overlap_from_unique_evidence() -> None:
    provider = _fake_provider()
    service = _shadow_service(provider)
    runtime = CanonicalTestPlanRuntime(shadow_service=_disabled_service())
    request = runtime.build_request(
        jira_key="FJ-OVERLAP-001",
        tenant_id="fluffyjaws-overlap",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    empty = CanonicalEvidenceBundle(
        tenant_id=request.tenant_id,
        records=[],
    )
    question = MissingQuestion(
        question="Which official source defines the current behavior?",
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        target_source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    domains = [
        DomainActivation(
            domain=IssueDomain.AUTHORING,
            confidence=1.0,
        )
    ]
    scope = ScopeResolution()
    seed_query = service._build_query(
        request=request,
        evidence=empty,
        scope=scope,
        domains=domains,
        question=question,
        local=None,
        materiality=service._materiality(question),
    )
    seed = EvidenceProviderExecutor().execute(
        provider,
        seed_query,
        EvidenceProviderExecutionContext(
            principal=request.principal,
            run_id="run-fj06-overlap-seed",
            request_id=request.request_id,
            correlation_id=seed_query.correlation_id,
            source_visibility_check=lambda _hit: True,
            source_verification_check=lambda _hit: True,
        ),
        base_bundle=empty,
    )
    assert seed.call_result.accepted_evidence_count == 1
    overlap_id = seed.call_result.accepted_evidence_ids[0]
    local = DirectedRetrievalRecord(
        question_id=question.question_id,
        query=question.question,
        authority_subject=question.authority_subject,
        target_source_types=question.target_source_types,
        matched_evidence_ids=[overlap_id],
        status=RetrievalStatus.USED,
    )

    trace = service.capture(
        run_id="run-fj06-overlap",
        request=request,
        evidence=seed.evidence_bundle,
        domains=domains,
        scope=scope,
        questions=[question],
        local_retrievals=[local],
    )

    assert trace is not None
    assert trace.metrics.provider_call_count == 1
    assert trace.metrics.accepted_evidence_count == 1
    assert trace.metrics.overlap_with_local_retrieval_count == 1
    assert trace.metrics.unique_evidence_count == 0
    assert trace.calls[0].overlap_evidence_ids == [overlap_id]
    assert trace.calls[0].unique_evidence_ids == []


def test_provider_timeout_is_trace_only_and_plan_neutral() -> None:
    _record, fixture, *_rest = _runtime_inputs()
    disabled_runtime = CanonicalTestPlanRuntime(shadow_service=_disabled_service())
    disabled_request = disabled_runtime.build_request(
        jira_key=str(fixture["jira_key"]),
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    disabled = disabled_runtime.generate_backend_compatibility(
        request=disabled_request, packet=fixture
    )

    provider = _fake_provider(error=TimeoutError("simulated secret-bearing timeout"))
    shadow_runtime = CanonicalTestPlanRuntime(
        shadow_service=_shadow_service(provider)
    )
    shadow_request = shadow_runtime.build_request(
        jira_key=str(fixture["jira_key"]),
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    shadow = shadow_runtime.generate_backend_compatibility(
        request=shadow_request, packet=fixture
    )
    trace = get_last_fluffyjaws_shadow_trace()

    assert trace is not None
    assert trace.state == "SHADOW_PARTIAL"
    assert trace.metrics.provider_call_count == len(provider.calls)
    assert trace.metrics.logical_call_count == trace.metrics.recorded_call_count
    assert trace.metrics.internal_error_count == 0
    assert trace.metrics.error_count == trace.metrics.logical_call_count
    assert trace.metrics.retry_count == 3
    assert trace.metrics.status_counts[EvidenceProviderStatus.TIMEOUT.value] == 3
    assert trace.metrics.suppressed_call_count == (
        trace.metrics.logical_call_count - 3
    )
    assert trace.metrics.provider_call_count == 6
    assert all(call.call_result.accepted_evidence_ids == [] for call in trace.calls)
    assert "simulated secret-bearing timeout" not in trace.model_dump_json()
    assert trace.metrics.discovery_success_count == 0
    assert trace.metrics.synthesis_only_call_count == 0
    assert shadow.request_id == disabled.request_id
    assert shadow.evidence_bundle_id == disabled.evidence_bundle_id
    assert shadow.output_sha256 == disabled.output_sha256
    assert shadow.rendered_output == disabled.rendered_output


def test_internal_executor_error_is_counted_and_plan_neutral() -> None:
    _record, fixture, _request, _evidence, _questions, *_rest = _runtime_inputs()
    disabled_runtime = CanonicalTestPlanRuntime(shadow_service=_disabled_service())
    disabled_request = disabled_runtime.build_request(
        jira_key=str(fixture["jira_key"]),
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    disabled = disabled_runtime.generate_backend_compatibility(
        request=disabled_request, packet=fixture
    )
    questions = disabled.output_payload["missing_questions"]

    class RaisingExecutor:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("internal secret-bearing failure")

    provider = _fake_provider()
    service = ReasoningEvidenceShadowService(
        config=FluffyJawsShadowConfig(
            mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW,
            max_questions=50,
        ),
        providers=[provider],
        executor=RaisingExecutor(),
        source_visibility_check=lambda _hit: True,
        source_verification_check=lambda _hit: True,
        query_egress_check=lambda _query, _request: True,
    )
    runtime = CanonicalTestPlanRuntime(shadow_service=service)
    request = runtime.build_request(
        jira_key=str(fixture["jira_key"]),
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )

    result = runtime.generate_backend_compatibility(request=request, packet=fixture)
    trace = get_last_fluffyjaws_shadow_trace()

    assert trace is not None
    assert trace.state == "SHADOW_PARTIAL"
    assert trace.metrics.provider_call_count == 0
    assert trace.metrics.logical_call_count == len(questions)
    assert trace.metrics.recorded_call_count == 0
    assert trace.metrics.internal_error_count == len(questions)
    assert trace.metrics.error_count == len(questions)
    assert provider.calls == []
    assert "internal secret-bearing failure" not in trace.model_dump_json()
    assert result.output_sha256 == disabled.output_sha256
    assert result.rendered_output == disabled.rendered_output


def test_disabled_run_clears_a_previous_shadow_sidecar() -> None:
    _record, fixture, *_rest = _runtime_inputs()
    provider = _fake_provider()
    shadow_runtime = CanonicalTestPlanRuntime(shadow_service=_shadow_service(provider))
    shadow_request = shadow_runtime.build_request(
        jira_key=str(fixture["jira_key"]),
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    shadow_runtime.generate_backend_compatibility(
        request=shadow_request, packet=fixture
    )
    assert get_last_fluffyjaws_shadow_trace() is not None

    disabled_runtime = CanonicalTestPlanRuntime(shadow_service=_disabled_service())
    disabled_request = disabled_runtime.build_request(
        jira_key=str(fixture["jira_key"]),
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    disabled_runtime.generate_backend_compatibility(
        request=disabled_request, packet=fixture
    )

    assert get_last_fluffyjaws_shadow_trace() is None
