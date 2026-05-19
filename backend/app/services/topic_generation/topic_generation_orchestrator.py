"""
TopicGenerationOrchestrator — ordered pipeline for screenshot + reference DITA → new topic.

Stages match ``dita_authoring_pipeline`` (telemetry via :class:`AuthoringPipelineTrace`).
LLM-bound steps (semantic plan, optional LLM XML render, repair already in validation service)
use the injected :class:`ScreenshotGuidedPipelineExecutor` protocol.
"""

from __future__ import annotations

import uuid

from app.core.schemas_chat_authoring import (
    ChatAttachmentRef,
    ChatDitaGenerationOptions,
)
from app.core.structured_logging import get_structured_logger
from app.services.dita_authoring_pipeline import (
    AuthoringPipelineTrace,
    MergedPlanResult,
    ReferenceAnalysisResult,
    RepairStageResult,
    ScreenshotAnalysisResult,
    ScreenshotGuidedPipelineExecutor,
    SemanticPlanResult,
    SerializationResult,
    StructuredDraftResult,
    TopicTypeResult,
    ValidationStageResult,
    _now_ms,
    _record,
)
from app.services.cisco_task_authoring import resolve_effective_authoring_pattern
from app.services.topic_generation.reference_dita_analyzer import ReferenceDitaAnalyzer
from app.services.topic_generation.screenshot_understanding_service import ScreenshotUnderstandingService
from app.services.topic_generation.structured_topic_draft_builder import StructuredTopicDraftBuilder
from app.services.topic_generation.topic_type_inference_service import TopicTypeInferenceService

logger = get_structured_logger(__name__)


class TopicGenerationOrchestrator:
    """
    Composes modular services for deterministic stages; executor handles plan/render/repair hooks.

    Override services in tests via constructor injection.
    """

    def __init__(
        self,
        *,
        screenshot_service: ScreenshotUnderstandingService | None = None,
        reference_analyzer: ReferenceDitaAnalyzer | None = None,
        topic_type_service: TopicTypeInferenceService | None = None,
        draft_builder: StructuredTopicDraftBuilder | None = None,
    ) -> None:
        self._screenshot = screenshot_service or ScreenshotUnderstandingService()
        self._reference = reference_analyzer or ReferenceDitaAnalyzer()
        self._topic_type = topic_type_service or TopicTypeInferenceService()
        self._draft_builder = draft_builder or StructuredTopicDraftBuilder()

    async def run_screenshot_guided_pipeline(
        self,
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
        trace = AuthoringPipelineTrace(run_id=str(uuid.uuid4()))
        order = 0

        # --- Stage 1: screenshot understanding (vision → structured IR) ---
        t0 = _now_ms()
        try:
            image_context = await self._screenshot.understand(
                image=image,
                image_bytes=image_bytes,
                user_prompt=user_prompt,
            )
            s1 = ScreenshotAnalysisResult(image_context=image_context)
            order += 1
            _record(
                trace,
                order,
                "analyze_screenshot",
                t0,
                True,
                vision_provider=image_context.vision_provider,
                screenshot_confidence=image_context.structured.confidence,
                uncertainty_count=len(image_context.structured.uncertainty_warnings),
                service="ScreenshotUnderstandingService",
            )
        except Exception:
            order += 1
            _record(trace, order, "analyze_screenshot", t0, False, service="ScreenshotUnderstandingService")
            raise

        # --- Stage 2: reference DITA analyzer (safe profile + summary) ---
        t0 = _now_ms()
        reference_summary = await self._reference.summarize_attachment(
            reference_attachment=reference_attachment,
            reference_text=reference_text,
        )
        profile = reference_summary.style_profile
        parse_ref_ok = not (
            profile
            and profile.parse_warnings
            and any("parse" in w.lower() or "empty" in w.lower() for w in profile.parse_warnings)
        )
        s2 = ReferenceAnalysisResult(reference_summary=reference_summary, parse_reference_ok=parse_ref_ok)
        order += 1
        _record(
            trace,
            order,
            "analyze_reference_topic",
            t0,
            True,
            had_reference=bool(reference_attachment and reference_text.strip()),
            parse_reference_ok=parse_ref_ok,
            service="ReferenceDitaAnalyzer",
        )

        # --- Resolve authoring pattern (auto → cisco_task|cisco_reference|default) before type/plan ---
        t_res = _now_ms()
        eff_ap = resolve_effective_authoring_pattern(
            base_options.authoring_pattern,
            reference_text=reference_text,
            style_profile=profile,
        )
        pipeline_opts = base_options.model_copy(update={"authoring_pattern": eff_ap})
        if eff_ap == "cisco_task" and not pipeline_opts.dita_type:
            pipeline_opts = pipeline_opts.model_copy(update={"dita_type": "task"})
        if eff_ap == "cisco_reference" and not pipeline_opts.dita_type:
            pipeline_opts = pipeline_opts.model_copy(update={"dita_type": "reference"})
        order += 1
        _record(
            trace,
            order,
            "resolve_authoring_pattern",
            t_res,
            True,
            resolved_pattern=eff_ap,
            input_pattern=base_options.authoring_pattern,
        )

        # --- Stage 3: topic type inference ---
        t0 = _now_ms()
        inferred = self._topic_type.infer(
            options=pipeline_opts,
            user_prompt=user_prompt,
            image_context=s1.image_context,
            profile=profile,
        )
        topic_type_overridden = bool(base_options.dita_type)
        effective = pipeline_opts.model_copy(update={"dita_type": pipeline_opts.dita_type or inferred})
        s3 = TopicTypeResult(
            dita_type=effective.dita_type or inferred,
            effective_options=effective,
            topic_type_overridden=topic_type_overridden,
        )
        order += 1
        _record(
            trace,
            order,
            "infer_topic_type",
            t0,
            True,
            dita_type=s3.dita_type,
            user_override=topic_type_overridden,
            reference_guided_enabled=reference_guided_enabled,
            service="TopicTypeInferenceService",
        )

        # --- Stage 4: semantic plan (LLM JSON, not raw topic XML) ---
        t0 = _now_ms()
        semantic_plan = await executor.build_semantic_plan(
            user_prompt=user_prompt,
            image_context=s1.image_context,
            reference_summary=s2.reference_summary,
            options=s3.effective_options,
        )
        semantic_plan = semantic_plan.model_copy(update={"dita_type": semantic_plan.dita_type or s3.dita_type})
        s4 = SemanticPlanResult(semantic_plan=semantic_plan)
        order += 1
        _record(
            trace,
            order,
            "build_semantic_plan",
            t0,
            True,
            section_count=len(semantic_plan.sections),
            dita_type=semantic_plan.dita_type,
            service="ChatDitaAuthoringService.build_semantic_plan",
        )

        # --- Stage 5: merge screenshot IR into plan ---
        t0 = _now_ms()
        merged_plan = self._draft_builder.merge_screenshot_ir(semantic_plan, s1.image_context.structured)
        merged_plan = merged_plan.model_copy(update={"dita_type": merged_plan.dita_type or s3.dita_type})
        s5 = MergedPlanResult(merged_plan=merged_plan)
        order += 1
        _record(
            trace,
            order,
            "merge_screenshot_structured",
            t0,
            True,
            merged_section_count=len(merged_plan.sections),
            service="StructuredTopicDraftBuilder.merge_screenshot_ir",
        )

        # --- Stage 6: structured topic draft (internal model) ---
        t0 = _now_ms()
        topic_draft = self._draft_builder.build_draft(plan=merged_plan, image_context=s1.image_context)
        s6 = StructuredDraftResult(topic_draft=topic_draft)
        order += 1
        _record(
            trace,
            order,
            "build_structured_draft",
            t0,
            True,
            draft_sections=len(topic_draft.sections),
            draft_tables=len(topic_draft.tables),
            draft_notes=len(topic_draft.notes),
            service="StructuredTopicDraftBuilder.build_draft",
        )

        # --- Stage 7: serialize (programmatic or LLM via executor) ---
        t0 = _now_ms()
        ser = await executor.render_dita_xml(
            semantic_plan=merged_plan,
            image_context=s1.image_context,
            reference_summary=s2.reference_summary,
            options=s3.effective_options,
            effective_strictness=strictness,
        )
        s7 = ser
        order += 1
        _record(
            trace,
            order,
            "serialize_xml",
            t0,
            True,
            serialization_mode=ser.mode,
            xml_chars=len(ser.xml or ""),
            service="DitaSerializerService_or_llm_render",
        )

        # --- Stage 8: validate ---
        t0 = _now_ms()
        val = await executor.validate_candidate(xml=s7.xml, semantic_plan=merged_plan, tenant_id=tenant_id)
        order += 1
        vr = val.validation_result
        err_n = len(getattr(vr, "validator_errors", []) or []) + len(getattr(vr, "aem_guides_validation_errors", []) or [])
        warn_n = len(getattr(vr, "validator_warnings", []) or []) + len(getattr(vr, "structural_issues", []) or [])
        _record(
            trace,
            order,
            "validate",
            t0,
            True,
            valid=getattr(vr, "valid", False),
            validation_error_count=err_n,
            validation_warning_count=warn_n,
            service="DitaValidationService",
        )

        # --- Stage 9: optional repair (up to 2 passes) ---
        # First pass fires whenever validation fails and strict_validation is enabled.
        # A second pass fires if the first repair produced a different (still-invalid) XML
        # — this handles cases where the initial fix exposed a secondary structural error
        # (e.g. fixing a <section> in <taskbody> reveals a missing <steps> wrapper).
        _MAX_PIPELINE_REPAIR_PASSES = max(
            1,
            int(__import__("os").environ.get("DITA_PIPELINE_MAX_REPAIRS", "2")),
        )
        s9: RepairStageResult | None = None
        if not vr.valid and pipeline_opts.strict_validation:
            current_xml = val.normalized_xml
            for repair_pass in range(_MAX_PIPELINE_REPAIR_PASSES):
                t0 = _now_ms()
                rep = await executor.repair_once_if_needed(
                    xml=current_xml,
                    semantic_plan=merged_plan,
                    tenant_id=tenant_id,
                )
                s9 = rep
                order += 1
                _record(
                    trace,
                    order,
                    f"repair_pass_{repair_pass + 1}",
                    t0,
                    True,
                    repaired=rep.repaired,
                    valid_after=getattr(rep.validation_result, "valid", False),
                    repair_pass=repair_pass + 1,
                    service="DitaValidationService.repair",
                )
                if getattr(rep.validation_result, "valid", False):
                    break
                next_xml = getattr(rep, "xml", None) or current_xml
                if next_xml.strip() == current_xml.strip():
                    # Repair made no change — further passes won't help.
                    break
                current_xml = next_xml

        logger.info_structured(
            "authoring_pipeline_complete",
            extra_fields={
                "event": "authoring_pipeline_complete",
                "pipeline_run_id": trace.run_id,
                "orchestrator": "TopicGenerationOrchestrator",
                "stage_count": len(trace.stages),
                "final_dita_type": merged_plan.dita_type,
            },
        )

        return s1, s2, s3, s4, s5, s6, s7, val, s9, trace
