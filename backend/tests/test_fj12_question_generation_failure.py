"""FJ-12 generic question-generation recovery and isolation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    CANONICAL_STAGE_ORDER,
    AuthoritySubject,
    EvidenceSourceType,
    GenerationProfile,
    IssueDomain,
    QuestionGenerationDiagnosticTrace,
    QuestionGenerationFailureReason,
    QuestionGenerationTraceStage,
    RuntimeEntryPoint,
    stable_sha256,
)
from app.services.canonical_test_plan_runtime import CanonicalTestPlanRuntime
from app.services.reasoning_evidence_provider import (
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
)


_WORKSPACE = Path(__file__).resolve().parents[2]
_FIXTURES = Path(__file__).with_name("fixtures") / "fj12_question_generation_cases.json"
_PROVIDER = "fluffyjaws"
_CONTRACT = "fake-fj12-empty-v1"
_STAMP = "2026-08-30T00:00:00Z"


def _cases() -> list[dict[str, object]]:
    payload = json.loads(_FIXTURES.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "fj12-question-generation-fixtures-v1"
    return payload["cases"]


def _empty_provider() -> FakeEvidenceProvider:
    descriptor = EvidenceProviderDescriptor(
        provider=_PROVIDER,
        adapter_version="fake-v1",
        provider_contract_version=_CONTRACT,
        supported_domains=list(IssueDomain),
        supported_source_types=list(EvidenceSourceType),
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
        return EvidenceProviderRawResult(
            provider=_PROVIDER,
            provider_contract_version=_CONTRACT,
            provider_call_id=call_id,
            raw_provider_reference=f"fj12-empty:{query.query_id}",
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            raw_hits=[],
            discovery_syntheses=[],
            transport_outcome=ProviderTransportOutcome.COMPLETED,
            applied_filters=active_query_filters(query),
            started_at=_STAMP,
            completed_at=_STAMP,
            duration_ms=1,
            cache_state=ProviderCacheState.MISS,
        )

    return FakeEvidenceProvider(
        descriptor,
        result_factory=result_factory,
        provider_contract_version=_CONTRACT,
    )


def _runtime(
    mode: FluffyJawsRuntimeMode,
    *,
    provider_available: bool = True,
) -> CanonicalTestPlanRuntime:
    providers = (
        [_empty_provider()]
        if mode == FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS and provider_available
        else []
    )
    return CanonicalTestPlanRuntime(
        shadow_service=ReasoningEvidenceShadowService(
            config=FluffyJawsShadowConfig(mode=mode, max_questions=50),
            providers=providers,
            source_visibility_check=lambda _hit: True,
            source_verification_check=lambda _hit: True,
            query_egress_check=lambda _query, _request: True,
        )
    )


def _run(case: dict[str, object], runtime: CanonicalTestPlanRuntime):
    packet = case["packet"]
    request = runtime.build_request(
        jira_key=str(packet["jira_key"]),
        tenant_id="fj12-question-generation",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    return runtime.generate_backend_compatibility(request=request, packet=packet)


@pytest.mark.parametrize("case", _cases(), ids=lambda row: str(row["case_id"]))
def test_generic_question_family_is_identical_with_and_without_fluffyjaws(
    case: dict[str, object],
) -> None:
    disabled = _run(case, _runtime(FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED))
    enabled = _run(case, _runtime(FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS))

    disabled_trace = disabled.trace.question_generation_trace
    enabled_trace = enabled.trace.question_generation_trace
    assert disabled_trace is not None
    assert enabled_trace is not None
    assert disabled_trace == enabled_trace
    assert disabled_trace.earliest_failure is None
    assert disabled_trace.recovered_failure == (
        QuestionGenerationFailureReason.SIGNAL_MISSING
    )
    assert disabled_trace.fluffyjaws_independent is True
    assert [row.stage for row in disabled_trace.steps] == list(
        QuestionGenerationTraceStage
    )
    assert [row.stage for row in disabled.trace.stage_trace] == list(
        CANONICAL_STAGE_ORDER
    )
    assert [row.stage for row in enabled.trace.stage_trace] == list(
        CANONICAL_STAGE_ORDER
    )

    disabled_surfaces = disabled.output_payload["change_surfaces"]
    enabled_surfaces = enabled.output_payload["change_surfaces"]
    assert disabled_surfaces == enabled_surfaces
    assert len(disabled_surfaces) == 1
    assert disabled_surfaces[0]["kind"] == case["expected"]["surface_kind"]
    assert disabled_surfaces[0]["source_evidence_ids"]

    disabled_questions = disabled.output_payload["missing_questions"]
    enabled_questions = enabled.output_payload["missing_questions"]
    assert disabled_questions == enabled_questions
    governing = [
        row
        for row in disabled_questions
        if row.get("dimension") == case["expected"]["question_family"]
    ]
    expected_outcome = case["expected"]["terminal_outcome"]
    assert disabled_trace.steps[-1].outcome == expected_outcome
    if expected_outcome == "GENERATED":
        assert len(governing) == 1
        question = governing[0]["question"].casefold()
        assert all(
            anchor.casefold() in question
            for anchor in case["expected"]["question_anchors"]
        )
        assert disabled_trace.steps[3].output_ids
        assert disabled_trace.steps[4].output_ids == [governing[0]["question_id"]]
    else:
        assert governing == []

    diagnostic_json = disabled_trace.model_dump_json()
    summary = str(case["packet"]["issue"]["summary"])
    assert summary not in diagnostic_json
    assert disabled.output_sha256 == enabled.output_sha256
    assert disabled.rendered_output == enabled.rendered_output
    if case["role"] == "ORIGINAL_HUMAN_CONFIRMED":
        captured = json.loads(
            (
                _WORKSPACE / "analysis" / "fluffyjaws" / "12_after_raw_trace.json"
            ).read_text(encoding="utf-8")
        )
        assert captured["mode_comparison"]["outputs_equal"] is True
        assert (
            captured["mode_comparison"]["disabled_output_sha256"]
            == captured["mode_comparison"]["mocked_second_pass_output_sha256"]
        )
        assert (
            stable_sha256(disabled_trace.model_dump(mode="json"))
            == captured["ordered_trace"]["trace_sha256"]
        )


def test_generic_fix_survives_enabled_but_unavailable_fluffyjaws() -> None:
    case = next(row for row in _cases() if row["role"] == "ORIGINAL_HUMAN_CONFIRMED")
    disabled = _run(case, _runtime(FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED))
    unavailable = _run(
        case,
        _runtime(
            FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS,
            provider_available=False,
        ),
    )

    assert disabled.trace.question_generation_trace == (
        unavailable.trace.question_generation_trace
    )
    assert (
        disabled.output_payload["missing_questions"]
        == (unavailable.output_payload["missing_questions"])
    )
    assert any(
        row["dimension"] == "GOVERNING_SEMANTICS"
        for row in unavailable.output_payload["missing_questions"]
    )


def test_failure_taxonomy_is_complete_and_production_has_no_case_routes() -> None:
    assert {row.value for row in QuestionGenerationFailureReason} == {
        "SIGNAL_MISSING",
        "PATTERN_NOT_AVAILABLE",
        "PATTERN_NOT_ACTIVATED",
        "CLOSURE_TRAVERSAL_STOPPED",
        "QUESTION_FAMILY_NOT_GENERATED",
        "QUESTION_PRUNED",
        "QUESTION_DEDUPED_INCORRECTLY",
        "SCOPE_FILTERED",
        "BUDGET_EXHAUSTED",
    }

    production = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            _WORKSPACE
            / "backend"
            / "app"
            / "services"
            / "canonical_test_plan_reasoning_service.py",
            _WORKSPACE
            / "backend"
            / "app"
            / "services"
            / "canonical_test_plan_runtime.py",
        )
    ).casefold()
    for forbidden in (
        "guides-27478",
        "guides-29781",
        "if topichead",
        "if codeblock",
        "if assets",
        "if ditaval",
    ):
        assert forbidden not in production

    assert AuthoritySubject.DITA_SEMANTICS.value in {
        row.value for row in AuthoritySubject
    }


def test_before_and_after_raw_trace_artifacts_are_machine_valid() -> None:
    before = json.loads(
        (_WORKSPACE / "analysis" / "fluffyjaws" / "12_before_raw_trace.json").read_text(
            encoding="utf-8"
        )
    )
    after = json.loads(
        (_WORKSPACE / "analysis" / "fluffyjaws" / "12_after_raw_trace.json").read_text(
            encoding="utf-8"
        )
    )

    assert before["earliest_failure"] == "SIGNAL_MISSING"
    raw_trace = dict(after["ordered_trace"])
    expected_sha256 = raw_trace.pop("trace_sha256")
    trace = QuestionGenerationDiagnosticTrace.model_validate(raw_trace)
    assert trace.earliest_failure is None
    assert trace.recovered_failure == QuestionGenerationFailureReason.SIGNAL_MISSING
    assert stable_sha256(raw_trace) == expected_sha256
    assert len(after["fixture_matrix"]) == 3
