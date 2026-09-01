"""PFIX-19 post-generation QE miss diagnostic tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    GenerationProfile,
    RuntimeEntryPoint,
    SemanticDimension,
)
from app.services.canonical_test_plan_runtime import CanonicalTestPlanRuntime
from app.services.qe_miss_diagnostic_service import (
    QE_MISS_STAGE_ORDER,
    DiagnosticFieldState,
    QeMissStage,
    QeMissStageObservation,
    QeMissStageState,
    classify_earliest_qe_failure,
    clear_last_qe_miss_debug_snapshot,
    debug_qe_miss,
)
from app.services.reasoning_evidence_shadow_service import (
    FluffyJawsRuntimeMode,
    FluffyJawsShadowConfig,
    ReasoningEvidenceShadowService,
)


_WORKSPACE = Path(__file__).resolve().parents[2]
_BASELINE_CASES = _WORKSPACE / "analysis" / "fluffyjaws" / "00_baseline_cases.jsonl"


def _fixture() -> dict[str, Any]:
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


def _runtime() -> CanonicalTestPlanRuntime:
    return CanonicalTestPlanRuntime(
        shadow_service=ReasoningEvidenceShadowService(
            config=FluffyJawsShadowConfig(
                mode=FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED
            )
        )
    )


def _run(*, tenant_id: str = "pfix19") -> Any:
    fixture = _fixture()
    runtime = _runtime()
    request = runtime.build_request(
        jira_key=str(fixture["jira_key"]),
        tenant_id=tenant_id,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    return runtime.generate_backend_compatibility(request=request, packet=fixture)


def _controlled_miss(stage: QeMissStage) -> tuple[QeMissStageObservation, ...]:
    target = QE_MISS_STAGE_ORDER.index(stage)
    return tuple(
        QeMissStageObservation(
            stage=current,
            state=(
                QeMissStageState.PASS
                if index < target
                else QeMissStageState.FAIL
            ),
            reason_codes=((
                "CONTROLLED_PRECONDITION_PASSED"
                if index < target
                else "CONTROLLED_MISS"
            ),),
        )
        for index, current in enumerate(QE_MISS_STAGE_ORDER)
    )


@pytest.mark.parametrize("stage", QE_MISS_STAGE_ORDER)
def test_classifier_returns_exactly_one_earliest_stage_for_every_taxonomy_stage(
    stage: QeMissStage,
) -> None:
    result = classify_earliest_qe_failure(_controlled_miss(stage))

    assert result.earliest_failed_stage == stage
    assert [
        row.stage for row in result.observations if row.state == QeMissStageState.FAIL
    ] == [stage]
    assert all(
        row.state != QeMissStageState.FAIL
        for row in result.observations[QE_MISS_STAGE_ORDER.index(stage) + 1 :]
    )


@pytest.mark.parametrize(
    ("case_name", "expected_stage"),
    [
        ("evidence omitted", QeMissStage.EVIDENCE_INTAKE),
        ("change surface wrong", QeMissStage.CHANGE_SURFACE),
        ("Pattern MCP not matched", QeMissStage.PATTERN_LOOKUP),
        (
            "pattern applicability rejected incorrectly",
            QeMissStage.PATTERN_APPLICABILITY,
        ),
        ("family not activated", QeMissStage.FAMILY_ACTIVATION),
        ("Claude question absent", QeMissStage.CLAUDE_QUESTION),
        ("question rejected incorrectly", QeMissStage.QUESTION_VALIDATOR),
        ("provider not routed", QeMissStage.ROUTING),
        ("retrieval empty", QeMissStage.RETRIEVAL),
        ("GitHub consumer missed", QeMissStage.GITHUB_BLAST_RADIUS),
        ("candidate applicability wrong", QeMissStage.APPLICABILITY),
        ("wrong disposition", QeMissStage.DISPOSITION),
        ("completeness missed absence", QeMissStage.FAMILY_COMPLETENESS),
        ("dedup removed distinct candidate", QeMissStage.DEDUP),
        ("renderer omitted accepted candidate", QeMissStage.RENDERER),
    ],
)
def test_required_controlled_miss_maps_to_exact_root(
    case_name: str,
    expected_stage: QeMissStage,
) -> None:
    result = classify_earliest_qe_failure(_controlled_miss(expected_stage))

    assert case_name
    assert result.earliest_failed_stage == expected_stage
    assert sum(
        row.state == QeMissStageState.FAIL for row in result.observations
    ) == 1


def test_debugger_uses_frozen_run_and_hashes_human_reference_without_leakage() -> None:
    result = _run()
    frozen_payload = result.model_dump(mode="json")
    human_reference = "Human-confirmed private missing role/profile branch"

    diagnosis = debug_qe_miss(
        result.run_id,
        SemanticDimension.ROLE_PROFILE_APPLICABILITY,
        human_reference,
    )

    assert diagnosis.PLAN_ID == result.run_id
    assert diagnosis.PLAN_ID_KIND == "CANONICAL_RUN_ID"
    assert diagnosis.PLAN_ID_NOTE == "CANONICAL_PLAN_ID_NOT_DEFINED"
    assert diagnosis.WAS_DISCOVERED == "YES"
    assert diagnosis.EARLIEST_FAILED_STAGE == QeMissStage.APPLICABILITY
    assert diagnosis.HUMAN_REFERENCE_STATE == "POST_GENERATION_HASH_ONLY"
    assert len(diagnosis.HUMAN_REFERENCE_SHA256) == 64
    assert human_reference not in diagnosis.model_dump_json()
    assert result.model_dump(mode="json") == frozen_payload
    assert sum(
        row.state == QeMissStageState.FAIL for row in diagnosis.STAGE_OBSERVATIONS
    ) == 1
    assert diagnosis.AUTO_MUTATION is False


def test_debugger_reports_unavailable_stages_without_fabricating_them() -> None:
    result = _run(tenant_id="pfix19-not-implemented")

    diagnosis = debug_qe_miss(
        result.run_id,
        SemanticDimension.ROLE_PROFILE_APPLICABILITY,
    )

    assert diagnosis.CLAUDE_QUESTIONS.state == DiagnosticFieldState.NOT_IMPLEMENTED
    assert diagnosis.QUESTION_GATE_RESULTS.state == DiagnosticFieldState.NOT_IMPLEMENTED
    assert diagnosis.SCORING.state == DiagnosticFieldState.NOT_IMPLEMENTED
    assert diagnosis.CANDIDATE_COMPLETENESS.state == DiagnosticFieldState.PRESENT
    assert diagnosis.DEDUP_DECISIONS.state in {
        DiagnosticFieldState.PRESENT,
        DiagnosticFieldState.NOT_APPLICABLE,
    }
    assert diagnosis.RENDERER_DECISIONS.state == DiagnosticFieldState.PRESENT
    assert diagnosis.ACTIVE_REASONERS.state == DiagnosticFieldState.NOT_IMPLEMENTED
    assert diagnosis.DITA_SEMANTIC_TRACE.state == DiagnosticFieldState.NOT_IMPLEMENTED
    assert diagnosis.AUTHORING_CAPABILITY_TRACE.state == DiagnosticFieldState.NOT_IMPLEMENTED
    assert diagnosis.CONFIGURATION_BRANCHES.state == DiagnosticFieldState.NOT_IMPLEMENTED
    assert diagnosis.BEHAVIOR_TRACE.state == DiagnosticFieldState.NOT_IMPLEMENTED
    assert diagnosis.ORACLE.state == DiagnosticFieldState.NOT_IMPLEMENTED
    assert diagnosis.SEMANTIC_BLAST_RADIUS.state == DiagnosticFieldState.NOT_IMPLEMENTED


def test_debugger_fails_closed_for_present_dimension_wrong_run_and_unknown_dimension() -> None:
    result = _run(tenant_id="pfix19-closed")

    with pytest.raises(ValueError, match="already has a final-output lineage"):
        debug_qe_miss(result.run_id, SemanticDimension.GOVERNING_SEMANTICS)
    with pytest.raises(LookupError, match="unavailable"):
        debug_qe_miss(
            "run:00000000-0000-4000-8000-000000000000",
            SemanticDimension.ROLE_PROFILE_APPLICABILITY,
        )
    with pytest.raises(ValueError, match="canonical dimension enum"):
        debug_qe_miss(result.run_id, "JIRA_SPECIFIC_LITERAL")


def test_debugger_requires_a_frozen_generation_and_rejects_unsafe_reference() -> None:
    clear_last_qe_miss_debug_snapshot()
    with pytest.raises(LookupError, match="frozen canonical generation"):
        debug_qe_miss(
            "run:00000000-0000-4000-8000-000000000000",
            SemanticDimension.ROLE_PROFILE_APPLICABILITY,
        )

    result = _run(tenant_id="pfix19-reference")
    with pytest.raises(ValueError, match="invalid or too large"):
        debug_qe_miss(
            result.run_id,
            SemanticDimension.ROLE_PROFILE_APPLICABILITY,
            "unsafe\x00reference",
        )


def test_diagnostic_capture_and_debug_call_do_not_change_baseline_output() -> None:
    first = _run(tenant_id="pfix19-regression")
    before = first.output_sha256
    debug_qe_miss(first.run_id, SemanticDimension.ROLE_PROFILE_APPLICABILITY)
    assert first.output_sha256 == before

    second = _run(tenant_id="pfix19-regression")
    assert second.output_sha256 == before
    assert second.output_payload == first.output_payload
