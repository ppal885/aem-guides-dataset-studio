"""FJ-00 replay proving FJ-06 shadow mode cannot change canonical plans."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.schemas_canonical_test_plan_runtime import (
    GenerationProfile,
    IssueDomain,
    RuntimeEntryPoint,
    stable_sha256,
)
from app.services.canonical_test_plan_runtime import CanonicalTestPlanRuntime
from app.services.reasoning_evidence_provider import (
    DiscoverySynthesis,
    EvidenceProviderDescriptor,
    EvidenceProviderExecutor,
    EvidenceProviderRawResult,
    FakeEvidenceProvider,
    ProviderCacheState,
    ProviderTransportOutcome,
    active_query_filters,
)
from app.services.reasoning_evidence_shadow_service import (
    FluffyJawsRuntimeMode,
    FluffyJawsShadowConfig,
    ReasoningEvidenceShadowService,
    get_last_fluffyjaws_shadow_trace,
)


_WORKSPACE = Path(__file__).resolve().parents[2]
_BASELINE_CASES = _WORKSPACE / "analysis" / "fluffyjaws" / "00_baseline_cases.jsonl"
_PROVIDER = "fluffyjaws"
_CONTRACT = "fake-fluffyjaws-replay-v1"
_STAMP = "2026-08-30T00:00:00Z"


def _stable_stage_trace(result: object) -> list[dict[str, object]]:
    return [
        {
            "stage": str(stage.stage),
            "sequence": stage.sequence,
            "input_sha256": stage.input_sha256,
            "output_sha256": stage.output_sha256,
            "status": stage.status,
            "item_count": stage.item_count,
            "warnings": stage.warnings,
        }
        for stage in result.trace.stage_trace
    ]


def _provider() -> FakeEvidenceProvider:
    descriptor = EvidenceProviderDescriptor(
        provider=_PROVIDER,
        adapter_version="fake-v1",
        provider_contract_version=_CONTRACT,
        supported_domains=list(IssueDomain),
        supported_source_types=[],
        supports_discovery_synthesis=True,
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

    def result_factory(query, context) -> EvidenceProviderRawResult:
        call_id = EvidenceProviderExecutor._call_id(
            _PROVIDER, query.query_id, context.correlation_id
        )
        synthesis = DiscoverySynthesis(
            provider=_PROVIDER,
            provider_contract_version=_CONTRACT,
            provider_call_id=call_id,
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            text=f"Trace-only discovery for {query.question_id}.",
            raw_provider_reference=f"fj-replay-synthesis:{query.question_id}",
            confidence=0.5,
        )
        return EvidenceProviderRawResult(
            provider=_PROVIDER,
            provider_contract_version=_CONTRACT,
            provider_call_id=call_id,
            raw_provider_reference=f"fj-replay-call:{query.question_id}",
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            discovery_syntheses=[synthesis],
            transport_outcome=ProviderTransportOutcome.COMPLETED,
            applied_filters=active_query_filters(query),
            started_at=_STAMP,
            completed_at=_STAMP,
            duration_ms=7,
            cache_state=ProviderCacheState.MISS,
        )

    return FakeEvidenceProvider(
        descriptor,
        result_factory=result_factory,
        provider_contract_version=_CONTRACT,
    )


def _shadow_runtime(provider: FakeEvidenceProvider) -> CanonicalTestPlanRuntime:
    service = ReasoningEvidenceShadowService(
        config=FluffyJawsShadowConfig(
            mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW,
            max_questions=50,
        ),
        providers=[provider],
        source_visibility_check=lambda _hit: True,
        source_verification_check=lambda _hit: True,
        query_egress_check=lambda _query, _request: True,
    )
    return CanonicalTestPlanRuntime(shadow_service=service)


def _disabled_runtime() -> CanonicalTestPlanRuntime:
    return CanonicalTestPlanRuntime(
        shadow_service=ReasoningEvidenceShadowService(
            config=FluffyJawsShadowConfig(
                mode=FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED,
                max_questions=50,
            ),
            providers=[],
        )
    )


def test_all_fj00_cases_are_current_runtime_equivalent_in_shadow_mode() -> None:
    records = [
        json.loads(line)
        for line in _BASELINE_CASES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) == 5

    for record in records:
        fixture = record["fixture"]
        provider = _provider()
        runtime = _shadow_runtime(provider)
        disabled_runtime = _disabled_runtime()
        disabled_request = disabled_runtime.build_request(
            jira_key=fixture["jira_key"],
            tenant_id="fluffyjaws-baseline",
            entry_point=RuntimeEntryPoint.PYTHON_API,
            generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
        )
        disabled = disabled_runtime.generate_backend_compatibility(
            request=disabled_request,
            packet=fixture,
        )
        request = runtime.build_request(
            jira_key=fixture["jira_key"],
            tenant_id="fluffyjaws-baseline",
            entry_point=RuntimeEntryPoint.PYTHON_API,
            generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
        )
        result = runtime.generate_backend_compatibility(
            request=request,
            packet=fixture,
        )
        stable_trace = _stable_stage_trace(result)
        disabled_stable_trace = _stable_stage_trace(disabled)
        shadow_trace = get_last_fluffyjaws_shadow_trace()
        expected_question_ids = sorted(
            row["question_id"]
            for row in disabled.output_payload["missing_questions"]
        )

        assert stable_sha256(record["fixture"]) == record["fixture_sha256"]
        assert stable_sha256(record["stable_stage_trace"]) == record[
            "stable_stage_trace_sha256"
        ]
        assert result.request_id == record["request_id"]
        assert result.evidence_bundle_id == record["evidence_bundle_id"]
        assert result.output_sha256 == disabled.output_sha256
        assert result.rendered_output == disabled.rendered_output
        assert stable_trace == disabled_stable_trace
        assert stable_sha256(stable_trace) == stable_sha256(disabled_stable_trace)

        assert shadow_trace is not None
        assert shadow_trace.mode == FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW
        assert shadow_trace.request_id == result.request_id
        assert shadow_trace.evidence_bundle_id == result.evidence_bundle_id
        assert shadow_trace.eligible_question_ids == expected_question_ids
        assert shadow_trace.dispatched_question_ids == expected_question_ids
        assert shadow_trace.metrics.provider_call_count == len(expected_question_ids)
        assert shadow_trace.metrics.recorded_call_count == len(expected_question_ids)
        assert shadow_trace.metrics.internal_error_count == 0
        assert shadow_trace.metrics.empty_count == len(expected_question_ids)
        assert shadow_trace.metrics.error_count == 0
        assert shadow_trace.metrics.synthesis_count == len(expected_question_ids)
        assert shadow_trace.metrics.discovery_success_count == len(
            expected_question_ids
        )
        assert shadow_trace.metrics.synthesis_only_call_count == len(
            expected_question_ids
        )
        # The resilience boundary keeps the greater of adapter-reported and
        # locally measured latency, so real scheduler overhead is allowed.
        assert shadow_trace.metrics.total_latency_ms >= (
            len(expected_question_ids) * 7
        )
        assert shadow_trace.metrics.minimum_latency_ms >= (
            7 if expected_question_ids else 0
        )
        assert (
            shadow_trace.metrics.maximum_latency_ms
            >= shadow_trace.metrics.minimum_latency_ms
        )
        assert shadow_trace.metrics.mean_latency_ms >= (
            7.0 if expected_question_ids else 0.0
        )
        assert (
            shadow_trace.metrics.mean_latency_ms
            <= shadow_trace.metrics.maximum_latency_ms
        )
        assert len(provider.calls) == len(expected_question_ids)

        shadow_texts = [
            synthesis.text
            for call in shadow_trace.calls
            for synthesis in call.discovery_syntheses
        ]
        assert (
            bool(shadow_texts) if expected_question_ids else shadow_texts == []
        )
        serialized_result = result.model_dump_json()
        assert all(text not in serialized_result for text in shadow_texts)


def test_straightforward_fj00_case_makes_zero_shadow_calls() -> None:
    records = [
        json.loads(line)
        for line in _BASELINE_CASES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    record = next(row for row in records if row["name"] == "straightforward_no_second_pass")
    fixture = record["fixture"]
    provider = _provider()
    runtime = _shadow_runtime(provider)
    disabled_runtime = _disabled_runtime()
    disabled_request = disabled_runtime.build_request(
        jira_key=fixture["jira_key"],
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    disabled = disabled_runtime.generate_backend_compatibility(
        request=disabled_request,
        packet=fixture,
    )
    request = runtime.build_request(
        jira_key=fixture["jira_key"],
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )

    result = runtime.generate_backend_compatibility(request=request, packet=fixture)
    trace = get_last_fluffyjaws_shadow_trace()

    assert trace is not None
    assert trace.state == "SHADOW_COMPLETED"
    assert trace.calls == []
    assert trace.metrics.provider_call_count == 0
    assert trace.metrics.recorded_call_count == 0
    assert trace.metrics.internal_error_count == 0
    assert trace.metrics.discovery_success_count == 0
    assert trace.metrics.synthesis_only_call_count == 0
    assert not any(trace.metrics.status_counts.values())
    assert provider.calls == []
    assert result.output_sha256 == disabled.output_sha256
    assert result.rendered_output == disabled.rendered_output
