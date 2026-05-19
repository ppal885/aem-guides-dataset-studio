"""
Tool-oriented orchestration for screenshot-guided DITA authoring.

Stages run in order; each produces typed outputs consumed by the next.
Telemetry: structured logs + ``AuthoringPipelineTrace`` for debug/audit.

Execution trace example (see ``docs/dita-authoring-pipeline-traces.md``):

    run_id=uuid
    1 analyze_screenshot        ok  duration_ms=1200  detail={vision_provider, confidence}
    2 analyze_reference_topic   ok  duration_ms=4      detail={had_reference, parse_ok}
    3 infer_topic_type          ok  detail={dita_type, override}
    4 build_semantic_plan       ok  duration_ms=800    detail={llm_step: chat_dita_authoring_plan}
    5 merge_screenshot_ir       ok  detail={section_count}
    6 build_structured_draft    ok  detail={draft_sections, tables, notes}
    7 serialize_xml             ok  detail={mode: programmatic|llm}
    8 validate                  ok  detail={valid, error_count, warning_count}
    9 repair_optional           ok  detail={repaired}
"""

from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.core.schemas_chat_authoring import (
    ChatAttachmentRef,
    ChatDitaGenerationOptions,
    ChatDitaType,
    ChatDitaValidationResult,
    ChatImageContext,
    ChatReferenceDitaSummary,
    ChatSemanticPlan,
)
from app.core.structured_logging import get_structured_logger
from app.services.dita_topic_draft import TopicDraft

logger = get_structured_logger(__name__)


class StageRecord(BaseModel):
    """One completed pipeline stage (serializable for debug payloads)."""

    stage: str
    order: int
    duration_ms: float = 0.0
    ok: bool = True
    detail: dict[str, Any] = Field(default_factory=dict)


class AuthoringPipelineTrace(BaseModel):
    """Full run trace; attach to ``ChatDitaAuthoringResult.debug``."""

    run_id: str
    pipeline_version: str = "screenshot_guided_v1"
    stages: list[StageRecord] = Field(default_factory=list)

    def to_debug_list(self) -> list[dict[str, Any]]:
        return [s.model_dump(mode="json") for s in self.stages]


class ScreenshotAnalysisResult(BaseModel):
    """Stage 1 output."""

    image_context: ChatImageContext


class ReferenceAnalysisResult(BaseModel):
    """Stage 2 output."""

    reference_summary: ChatReferenceDitaSummary
    parse_reference_ok: bool


class TopicTypeResult(BaseModel):
    """Stage 3 output."""

    dita_type: ChatDitaType
    effective_options: ChatDitaGenerationOptions
    topic_type_overridden: bool


class SemanticPlanResult(BaseModel):
    """Stage 4 output (LLM or fallback semantic plan, before IR merge)."""

    semantic_plan: ChatSemanticPlan


class MergedPlanResult(BaseModel):
    """Stage 5 output."""

    merged_plan: ChatSemanticPlan


class StructuredDraftResult(BaseModel):
    """Stage 6 output."""

    topic_draft: TopicDraft


class SerializationResult(BaseModel):
    """Stage 7 output."""

    xml: str
    mode: str  # programmatic | llm


class ValidationStageResult(BaseModel):
    """Stage 8 output."""

    normalized_xml: str
    validation_result: ChatDitaValidationResult
    review_snapshot: dict[str, Any]


class RepairStageResult(BaseModel):
    """Stage 9 output (optional)."""

    xml: str
    validation_result: ChatDitaValidationResult
    review_snapshot: dict[str, Any]
    repaired: bool


@runtime_checkable
class ScreenshotGuidedPipelineExecutor(Protocol):
    """Executor hooks for stages that need service-local helpers (LLM, folder validate, repair)."""

    async def summarize_reference_dita(
        self,
        *,
        reference_attachment: ChatAttachmentRef | None,
        reference_text: str,
    ) -> ChatReferenceDitaSummary: ...

    async def build_semantic_plan(
        self,
        *,
        user_prompt: str,
        image_context: ChatImageContext,
        reference_summary: ChatReferenceDitaSummary,
        options: ChatDitaGenerationOptions,
    ) -> ChatSemanticPlan: ...

    async def render_dita_xml(
        self,
        *,
        semantic_plan: ChatSemanticPlan,
        image_context: ChatImageContext,
        reference_summary: ChatReferenceDitaSummary,
        options: ChatDitaGenerationOptions,
        effective_strictness: str,
    ) -> SerializationResult: ...

    async def validate_candidate(
        self,
        *,
        xml: str,
        semantic_plan: ChatSemanticPlan,
        tenant_id: str,
    ) -> ValidationStageResult: ...

    async def repair_once_if_needed(
        self,
        *,
        xml: str,
        semantic_plan: ChatSemanticPlan,
        tenant_id: str,
    ) -> RepairStageResult: ...


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _record(trace: AuthoringPipelineTrace, order: int, stage: str, t0: float, ok: bool, **detail: Any) -> None:
    rec = StageRecord(
        stage=stage,
        order=order,
        duration_ms=round(_now_ms() - t0, 2),
        ok=ok,
        detail={k: v for k, v in detail.items() if v is not None},
    )
    trace.stages.append(rec)
    logger.info_structured(
        "authoring_pipeline_stage",
        extra_fields={
            "event": "authoring_pipeline_stage",
            "pipeline_run_id": trace.run_id,
            "stage": stage,
            "stage_order": order,
            "duration_ms": rec.duration_ms,
            "ok": ok,
            **{f"detail_{k}": v for k, v in rec.detail.items() if isinstance(v, (str, int, float, bool))},
        },
    )


async def run_screenshot_guided_pipeline(
    *,
    executor: ScreenshotGuidedPipelineExecutor,
    user_prompt: str,
    tenant_id: str,
    image: ChatAttachmentRef,
    image_bytes: bytes,
    reference_attachment: ChatAttachmentRef | None,
    reference_text: str,
    base_options: ChatDitaGenerationOptions,
    strictness: str,
    reference_guided_enabled: bool,
) -> tuple[
    ScreenshotAnalysisResult,
    ReferenceAnalysisResult,
    TopicTypeResult,
    SemanticPlanResult,
    MergedPlanResult,
    StructuredDraftResult,
    SerializationResult,
    ValidationStageResult,
    RepairStageResult | None,
    AuthoringPipelineTrace,
]:
    """
    Run ordered stages via :class:`TopicGenerationOrchestrator` (modular services + executor hooks).

    Does not persist artifacts or build ``ChatDitaAuthoringResult`` — the chat service does that.
    """
    # Lazy import avoids circular module initialization with ``topic_generation``.
    from app.services.topic_generation.topic_generation_orchestrator import TopicGenerationOrchestrator

    return await TopicGenerationOrchestrator().run_screenshot_guided_pipeline(
        executor=executor,
        user_prompt=user_prompt,
        tenant_id=tenant_id,
        image=image,
        image_bytes=image_bytes,
        reference_attachment=reference_attachment,
        reference_text=reference_text,
        base_options=base_options,
        strictness=strictness,
        reference_guided_enabled=reference_guided_enabled,
    )
