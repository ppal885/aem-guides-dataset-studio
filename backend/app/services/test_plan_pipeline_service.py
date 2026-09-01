"""Canonical Test Plan entry point with one-way legacy response projection.

This module intentionally contains no acceptance authoring, scoring, plan
composition, or alternate validation pipeline. Entry points collect evidence
once, call ``CanonicalTestPlanRuntime`` once, and mechanically project the
result for clients that still consume ``TestPlanPipelineResult``.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from app.core.schemas_test_plan_pipeline import (
    TestPlanPipelineRequest,
    TestPlanPipelineResult,
)
from app.core.structured_logging import get_structured_logger
from app.services.guides_test_plan_generator_service import (
    build_guides_test_plan_evidence_packet,
    normalize_jira_key,
)


logger = get_structured_logger(__name__)


def run_test_plan_pipeline(
    request: TestPlanPipelineRequest,
    user: Any | None = None,
    *,
    entry_point: str = "python_api",
    benchmark_input: dict[str, Any] | None = None,
    benchmark_split: str = "",
    benchmark_source_path: str = "",
) -> TestPlanPipelineResult:
    """Run the fixed canonical engine once and project its result once."""

    from app.core.schemas_canonical_test_plan_runtime import RuntimeEntryPoint
    from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME
    from app.services.test_plan_runtime_adapters import (
        LEGACY_COMPATIBILITY_PROJECTOR,
        generation_request_from_pipeline_request,
    )

    selected_entry = RuntimeEntryPoint(entry_point)
    if benchmark_input is not None and selected_entry != RuntimeEntryPoint.BENCHMARK_V2:
        raise ValueError(
            "benchmark_input is valid only for the benchmark_v2 entry point"
        )
    canonical_request = generation_request_from_pipeline_request(
        request,
        entry_point=selected_entry,
        user=user,
        benchmark_version=(
            "V2" if selected_entry == RuntimeEntryPoint.BENCHMARK_V2 else ""
        ),
        benchmark_split=(
            benchmark_split or "train"
            if selected_entry == RuntimeEntryPoint.BENCHMARK_V2
            else ""
        ),
        benchmark_record_id=(
            str((benchmark_input or {}).get("record_id") or request.jira_key)
            if selected_entry == RuntimeEntryPoint.BENCHMARK_V2
            else ""
        ),
    )
    started = time.perf_counter()
    correlation_id = str(uuid.uuid4())
    logger.info_structured(
        "test_plan_pipeline_start",
        extra_fields={
            "jira_key": request.jira_key,
            "correlation_id": correlation_id,
        },
    )
    packet = _build_pipeline_packet(request, user=user)
    envelope = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=canonical_request,
        packet=packet,
        benchmark_input=benchmark_input,
        benchmark_source_path=benchmark_source_path,
        claude_question_submission=request.claude_question_submission,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    projected = LEGACY_COMPATIBILITY_PROJECTOR.project_pipeline_result(
        envelope,
        request=request,
        legacy_packet=packet,
        correlation_id=correlation_id,
        elapsed_ms=elapsed_ms,
    )
    _persist_postable_pipeline_result(
        request=request,
        envelope=envelope,
        projected=projected,
    )
    logger.info_structured(
        "test_plan_pipeline_done",
        extra_fields={
            "jira_key": request.jira_key,
            "correlation_id": correlation_id,
            "run_id": envelope.run_id,
            "status": envelope.status,
            "postable": LEGACY_COMPATIBILITY_PROJECTOR.is_postable(envelope),
            "elapsed_ms": elapsed_ms,
        },
    )
    return projected


def _build_pipeline_packet(
    request: TestPlanPipelineRequest,
    *,
    user: Any | None = None,
) -> dict[str, Any]:
    """Retrieve evidence once; the canonical runtime owns normalization."""

    key = normalize_jira_key(request.jira_key)
    roles = {str(role).strip().casefold() for role in getattr(user, "roles", [])}
    allow_cross_customer_graph_details = bool(
        getattr(user, "is_admin", False) or "knowledge_reader" in roles
    )
    return build_guides_test_plan_evidence_packet(
        key,
        tenant_id=request.tenant_id,
        evidence_k=request.evidence_k,
        include_repository_evidence=request.include_repository_evidence,
        max_repo_matches=request.max_repo_matches,
        skip_uac_label_gate=request.skip_uac_label_gate,
        full_rag=request.full_rag,
        include_evidence_graph=request.include_evidence_graph,
        graph_max_paths=request.graph_max_paths,
        allow_cross_customer_graph_details=allow_cross_customer_graph_details,
    )


def _persist_postable_pipeline_result(
    *,
    request: TestPlanPipelineRequest,
    envelope: Any,
    projected: TestPlanPipelineResult,
) -> None:
    """Persist only after every canonical gate passes; benchmarks never write."""

    from app.services.test_plan_runtime_adapters import LEGACY_COMPATIBILITY_PROJECTOR

    if (
        envelope.trace.entry_point.value == "benchmark_v2"
        or not LEGACY_COMPATIBILITY_PROJECTOR.is_postable(envelope)
    ):
        return

    if request.write_starling_artifacts:
        projected.artifacts_written.extend(
            _write_canonical_starling_artifacts(
                _resolve_starling_path(request.starling_repo_path),
                envelope,
            )
        )
        projected.stages_completed.append("write_starling_artifacts")

    if request.publish_to_team_ui and envelope.rendered_output:
        from app.services import test_plan_artifact_service as artifacts

        saved = artifacts.save_test_plan(request.jira_key, envelope.rendered_output)
        projected.artifacts_written.append(
            str(saved.get("filename") or f"{request.jira_key}-test-plan.md")
        )
        projected.stages_completed.append("publish_team_ui")

    try:
        from app.services import test_plan_artifact_service as artifacts

        memory_entry = artifacts.record_pipeline_memory(projected)
        projected.artifacts_written.append(
            str(memory_entry.get("memory_path") or "pipeline-memory")
        )
        projected.stages_completed.append("pipeline_memory")
    except Exception as exc:  # persistence is non-authoritative after a passed run
        logger.warning_structured(
            "test_plan_pipeline_memory_failed",
            extra_fields={
                "jira_key": request.jira_key,
                "correlation_id": projected.correlation_id,
                "run_id": envelope.run_id,
                "error": str(exc),
            },
        )


def _write_canonical_starling_artifacts(
    starling_root: Path,
    envelope: Any,
) -> list[str]:
    """Write only the already-gated canonical plan and its trace envelope."""

    jira_key = str(envelope.output_payload.get("jira_key") or "UNKNOWN")
    plans_dir = starling_root / "docs" / "qa" / "test-plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plans_dir / f"{jira_key}-test-plan-pipeline-draft.md"
    plan_path.write_text(envelope.rendered_output, encoding="utf-8")
    result_path = plans_dir / f"{jira_key}-canonical-runtime-result.json"
    result_path.write_text(
        json.dumps(envelope.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return [str(plan_path), str(result_path)]


def _resolve_starling_path(override: str | None) -> Path:
    raw = (override or os.getenv("STARLING_REPO_PATH") or "C:/starling").strip()
    return Path(raw)


__all__ = ["run_test_plan_pipeline"]
