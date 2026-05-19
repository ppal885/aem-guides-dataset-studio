from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.schemas_chat_authoring import (
    ChatAction,
    ChatAttachmentRef,
    ChatAuthoringIntentDecision,
    ChatAuthoringRequestPayload,
    ChatBundleArtifact,
    ChatDitaAuthoringResult,
    ChatDitaGenerationOptions,
    ChatDitaValidationResult,
    ChatImageContext,
    ChatReferenceDitaSummary,
    ChatSemanticPlan,
    ChatSemanticPlanSection,
    GenerationAssumption,
    ReferenceStyleProfile,
    TopicGenerationDebug,
    TopicGenerationValidation,
)
from app.core.schemas_topic_generation import ReferenceAdoptionDecision, ReferenceSerializerPolicy
from app.core.structured_logging import get_structured_logger
from app.services.aem_upload_service import get_upload_service
from app.services.chat_asset_service import read_asset_bytes, save_text_asset
from app.services.chat_authoring_governance import (
    AuthoringRunTimer,
    log_authoring_trace_completed,
    log_authoring_trace_started,
    new_authoring_trace_id,
)
from app.services.dita_authoring_pipeline import (
    AuthoringPipelineTrace,
    RepairStageResult,
    SerializationResult,
    ValidationStageResult,
    run_screenshot_guided_pipeline,
)
from app.services.dita_link_recommendations import build_link_recommendations
from app.services.dita_topic_draft import build_topic_draft
from app.services.dita_xml_headers import build_dita_header, normalize_dita_document
from app.services.llm_service import generate_json, generate_text, is_llm_available
from app.services.cisco_task_authoring import (
    cisco_reference_semantic_plan_instructions,
    cisco_semantic_plan_instructions,
)
from app.services.topic_generation.dita_serializer_service import DitaSerializerService
from app.services.topic_generation.dita_validation_service import DitaValidationService
from app.services.topic_generation.reference_dita_analyzer import ReferenceDitaAnalyzer

logger = get_structured_logger(__name__)

_dita_validation = DitaValidationService()
_reference_dita_analyzer = ReferenceDitaAnalyzer()
_dita_serializer = DitaSerializerService()

_MERGED_JIRA_MAX_CHARS = 20_000
_MIN_SCREENSHOT_CONFIDENCE_FOR_SAFE_FALLBACK = float(
    os.getenv("CHAT_SCREENSHOT_MIN_CONFIDENCE_FOR_SAFE_FALLBACK") or "0.55"
)
_MIN_SCREENSHOT_CONFIDENCE_FOR_LOW_SIGNAL = float(
    os.getenv("CHAT_SCREENSHOT_MIN_CONFIDENCE_FOR_LOW_SIGNAL") or "0.42"
)
_PLACEHOLDER_SECTION_NAMES = frozenset(
    {
        "introduction",
        "overview",
        "prerequisites",
        "configuration steps",
        "verification",
        "body",
        "conclusion",
        "summary",
    }
)
_PLACEHOLDER_DETAIL_PATTERNS = (
    re.compile(r"^briefly introduce\b", re.IGNORECASE),
    re.compile(r"^list the requirements\b", re.IGNORECASE),
    re.compile(r"^use the user interface to\b", re.IGNORECASE),
    re.compile(r"^configure the .+ settings\b", re.IGNORECASE),
    re.compile(r"^verify that .+\b", re.IGNORECASE),
    re.compile(r"^provide an overview\b", re.IGNORECASE),
    re.compile(r"^present detailed information\b", re.IGNORECASE),
    re.compile(r"^summarize the key points\b", re.IGNORECASE),
)


def _resolved_authoring_pattern_from_trace(trace: AuthoringPipelineTrace) -> str | None:
    for rec in trace.stages:
        if rec.stage == "resolve_authoring_pattern":
            rp = rec.detail.get("resolved_pattern")
            return str(rp) if rp is not None else None
    return None


def merge_jira_into_authoring_prompt(content: str, jira_context: str | None) -> str:
    """Append optional Jira/issue text to the user prompt for vision + planning (bounded)."""
    base = (content or "").strip()
    jc = (jira_context or "").strip()
    if not jc:
        return base
    jc = jc[:_MERGED_JIRA_MAX_CHARS]
    return f"{base}\n\n---\nJira / ticket context:\n{jc}"


class _ScreenshotGuidedPipelineExecutor:
    """Adapts ``ChatDitaAuthoringService`` private steps to :class:`ScreenshotGuidedPipelineExecutor`."""

    def __init__(self, svc: ChatDitaAuthoringService) -> None:
        self._svc = svc

    async def summarize_reference_dita(
        self,
        *,
        reference_attachment: ChatAttachmentRef | None,
        reference_text: str,
    ) -> ChatReferenceDitaSummary:
        return await self._svc._summarize_reference_dita(
            reference_attachment=reference_attachment,
            reference_text=reference_text,
        )

    async def build_semantic_plan(
        self,
        *,
        user_prompt: str,
        image_context: ChatImageContext,
        reference_summary: ChatReferenceDitaSummary,
        options: ChatDitaGenerationOptions,
    ) -> ChatSemanticPlan:
        return await self._svc._build_semantic_plan(
            user_prompt=user_prompt,
            image_context=image_context,
            reference_summary=reference_summary,
            options=options,
        )

    async def render_dita_xml(
        self,
        *,
        semantic_plan: ChatSemanticPlan,
        image_context: ChatImageContext,
        reference_summary: ChatReferenceDitaSummary,
        options: ChatDitaGenerationOptions,
        effective_strictness: str,
    ) -> SerializationResult:
        xml, mode = await self._svc._render_dita_xml_with_mode(
            semantic_plan=semantic_plan,
            image_context=image_context,
            reference_summary=reference_summary,
            options=options,
            effective_strictness=effective_strictness,
        )
        return SerializationResult(xml=xml, mode=mode)

    async def validate_candidate(
        self,
        *,
        xml: str,
        semantic_plan: ChatSemanticPlan,
        tenant_id: str,
    ) -> ValidationStageResult:
        normalized_xml, validation_result, review_snapshot = await self._svc._validate_candidate(
            xml=xml,
            semantic_plan=semantic_plan,
            tenant_id=tenant_id,
        )
        return ValidationStageResult(
            normalized_xml=normalized_xml,
            validation_result=validation_result,
            review_snapshot=review_snapshot,
        )

    async def repair_once_if_needed(
        self,
        *,
        xml: str,
        semantic_plan: ChatSemanticPlan,
        tenant_id: str,
    ) -> RepairStageResult:
        repaired_xml, validation_result, review_snapshot = await self._svc._repair_once_if_needed(
            xml=xml,
            semantic_plan=semantic_plan,
            tenant_id=tenant_id,
        )
        return RepairStageResult(
            xml=repaired_xml,
            validation_result=validation_result,
            review_snapshot=review_snapshot,
            repaired=bool(validation_result.repaired),
        )

_AUTHORING_INTENT_PATTERN = re.compile(
    r"\b(generate|create|write|draft|author|build|produce|convert|turn)\b.*\b(dita|topic|task|concept|reference|xml)\b|"
    r"\b(dita|topic|task|concept|reference|xml)\b.*\b(from|using|based on)\b.*\b(screenshot|image|screen|ui|mockup)\b",
    re.IGNORECASE,
)
_SCREENSHOT_PATTERN = re.compile(r"\b(screenshot|screen|image|mockup|ui|page|dialog|panel|view)\b", re.IGNORECASE)
_AEM_BASE_URL = (os.getenv("CHAT_AUTHORING_AEM_BASE_URL") or "").strip()
_AEM_USERNAME = (os.getenv("CHAT_AUTHORING_AEM_USERNAME") or "").strip()
_AEM_PASSWORD = (os.getenv("CHAT_AUTHORING_AEM_PASSWORD") or "").strip()
_REFERENCE_GUIDED_FLAG = (os.getenv("CHAT_REFERENCE_GUIDED_TOPIC_GEN_ENABLED") or "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


@dataclass
class _CollectedAttachments:
    image: ChatAttachmentRef | None
    image_bytes: bytes | None
    reference_dita: ChatAttachmentRef | None
    reference_text: str


def _shorten(value: str, limit: int = 1800) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[truncated]"


def _default_file_name(title: str, dita_type: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", (title or dita_type or "generated-topic").strip().lower()).strip(".-")
    return f"{base or 'generated-topic'}.dita"


def _default_map_file_name(title: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", (title or "map").strip().lower()).strip(".-")
    return f"{base or 'generated-map'}.ditamap"


def _slug(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip().lower()).strip(".-")
    return cleaned or fallback


def _style_profile_diff_hint(profile: ReferenceStyleProfile | None, dita_type: str) -> str:
    if not profile:
        return "No reference style profile was available."
    parts = [
        f"Reference root pattern: <{profile.root_local_name}>; inferred output: <{dita_type}>.",
        f"Tone hint from reference: {profile.tone_hint or 'neutral'}.",
        f"Structural habits observed: {', '.join(profile.structural_habits[:6]) or 'none'}.",
    ]
    return " ".join(parts)


def _reference_adoption_summary(decision: ReferenceAdoptionDecision | None) -> str:
    if not decision:
        return "No reference adoption decision was available."
    parts = [
        f"Reference adoption: {decision.mode.replace('_', ' ')}.",
        f"Effective output root: <{decision.target_root_type}>.",
    ]
    if decision.adopted_constraints:
        parts.append("Applied: " + ", ".join(decision.adopted_constraints[:8]) + ".")
    if decision.rejected_constraints:
        parts.append("Rejected: " + ", ".join(decision.rejected_constraints[:6]) + ".")
    if decision.warnings:
        parts.append("Warnings: " + " ".join(decision.warnings[:3]))
    return " ".join(parts)


def _title_contains_any_token(title: str, *tokens: str) -> bool:
    words = {piece for piece in re.split(r"[^a-z0-9]+", (title or "").lower()) if piece}
    return any(token.lower() in words for token in tokens if token)


class ChatDitaAuthoringService:
    async def should_handle_request(
        self,
        *,
        user_prompt: str,
        attachments: list[ChatAttachmentRef],
        generation_options: ChatDitaGenerationOptions,
    ) -> ChatAuthoringIntentDecision:
        has_image = any(item.kind == "image" for item in attachments)
        if not has_image:
            return ChatAuthoringIntentDecision(
                is_authoring_request=False,
                confidence=0.0,
                reason="No image attachment was provided.",
            )

        if getattr(generation_options, "screenshot_deliverable", "single_topic") == "map_hierarchy":
            return ChatAuthoringIntentDecision(
                is_authoring_request=True,
                confidence=0.96,
                reason="Map hierarchy mode is selected; the screenshot will be interpreted as a DITA map diagram when possible.",
                dita_type_hint="map",
            )

        prompt = (user_prompt or "").strip()
        if _AUTHORING_INTENT_PATTERN.search(prompt):
            dita_hint = generation_options.dita_type or self._dita_type_hint_from_prompt(prompt)
            return ChatAuthoringIntentDecision(
                is_authoring_request=True,
                confidence=0.98,
                reason="The prompt explicitly asks to generate or convert content into a DITA topic from the attachment.",
                dita_type_hint=dita_hint,
            )

        if not _SCREENSHOT_PATTERN.search(prompt):
            return ChatAuthoringIntentDecision(
                is_authoring_request=False,
                confidence=0.2,
                reason="The prompt does not mention generating DITA from the image or screenshot.",
            )

        if not is_llm_available():
            return ChatAuthoringIntentDecision(
                is_authoring_request=False,
                confidence=0.35,
                reason="The prompt mentions a screenshot, but the authoring intent is too ambiguous without the LLM classifier.",
            )

        try:
            raw = await generate_json(
                system_prompt=(
                    "You classify whether a chat request is asking to author a NEW DITA topic from an attached image "
                    "and optional reference DITA file.\n"
                    "Return JSON only with keys: is_authoring_request, confidence, reason, dita_type_hint.\n"
                    "Use dita_type_hint only if the user explicitly or implicitly points to topic, task, concept, or reference."
                ),
                user_prompt=json.dumps(
                    {
                        "user_prompt": prompt,
                        "attachment_kinds": [item.kind for item in attachments],
                        "generation_options": generation_options.model_dump(mode="json"),
                    },
                    ensure_ascii=True,
                    indent=2,
                ),
                max_tokens=320,
                step_name="chat_dita_authoring_classify",
            )
            return ChatAuthoringIntentDecision(
                is_authoring_request=bool(raw.get("is_authoring_request")),
                confidence=float(raw.get("confidence") or 0.0),
                reason=str(raw.get("reason") or "").strip(),
                dita_type_hint=self._clean_dita_type(str(raw.get("dita_type_hint") or "")) or generation_options.dita_type,
            )
        except Exception as exc:
            logger.warning_structured(
                "Attachment authoring classification fell back to deterministic logic",
                extra_fields={"error": str(exc)},
            )
            return ChatAuthoringIntentDecision(
                is_authoring_request=False,
                confidence=0.3,
                reason="The prompt might refer to the screenshot, but it does not clearly ask for a new DITA topic.",
            )

    async def generate_topic_from_request(
        self,
        *,
        payload: ChatAuthoringRequestPayload,
        session_id: str,
        user_id: str,
        tenant_id: str,
    ) -> ChatDitaAuthoringResult:
        run_timer = AuthoringRunTimer()
        authoring_trace_id = payload.authoring_trace_id or new_authoring_trace_id()
        opts = payload.generation_options
        if not _REFERENCE_GUIDED_FLAG:
            opts = opts.model_copy(update={"style_strictness": "low"})

        if payload.authoring_trace_id is None:
            log_authoring_trace_started(
                authoring_trace_id=authoring_trace_id,
                session_id=session_id,
                user_id=user_id,
                tenant_id=tenant_id,
                attachments=payload.attachments,
                generation_options=opts,
                user_prompt=payload.content,
            )

        logger.info_structured(
            "chat_topic_gen_started",
            extra_fields={
                "event": "chat_topic_gen_started",
                "authoring_trace_id": authoring_trace_id,
                "session_id": session_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "attachment_count": len(payload.attachments),
                "requested_dita_type": opts.dita_type,
                "style_strictness": opts.style_strictness,
                "save_path": opts.save_path,
            },
        )

        collected = self._collect_attachments(payload.attachments)
        if not collected.image or not collected.image_bytes:
            raise ValueError("An image attachment is required to generate a DITA topic from a screenshot.")

        effective_user_prompt = merge_jira_into_authoring_prompt(payload.content, payload.jira_context)
        if opts.screenshot_deliverable == "map_hierarchy":
            return await self._generate_map_hierarchy_bundle(
                session_id=session_id,
                user_id=user_id,
                tenant_id=tenant_id,
                collected=collected,
                effective_user_prompt=effective_user_prompt,
                authoring_trace_id=authoring_trace_id,
                opts=opts,
                run_timer=run_timer,
            )

        strictness = opts.style_strictness if _REFERENCE_GUIDED_FLAG else "low"
        executor = _ScreenshotGuidedPipelineExecutor(self)
        s1, s2, _s3, _s4, s5, _s6, s7, val, s9, trace = await run_screenshot_guided_pipeline(
            executor=executor,
            user_prompt=effective_user_prompt,
            tenant_id=tenant_id,
            image=collected.image,
            image_bytes=collected.image_bytes,
            reference_attachment=collected.reference_dita,
            reference_text=collected.reference_text,
            base_options=opts,
            strictness=strictness,
            reference_guided_enabled=_REFERENCE_GUIDED_FLAG,
        )

        merged_plan = s5.merged_plan
        image_context = s1.image_context
        reference_summary = s2.reference_summary
        parse_ref_ok = s2.parse_reference_ok
        reference_adoption = merged_plan.reference_adoption

        assumption_objs: list[GenerationAssumption] = []
        for note in list(merged_plan.source_notes)[:8]:
            assumption_objs.append(GenerationAssumption(text=note, source="semantic_plan"))
        if reference_adoption:
            for note in reference_adoption.warnings[:6]:
                assumption_objs.append(GenerationAssumption(text=note, source="reference_style"))
            for adopted in reference_adoption.adopted_constraints[:6]:
                assumption_objs.append(
                    GenerationAssumption(text=f"Applied reference guidance: {adopted}.", source="reference_style")
                )
            for rejected in reference_adoption.rejected_constraints[:4]:
                assumption_objs.append(
                    GenerationAssumption(text=f"Skipped incompatible reference guidance: {rejected}.", source="reference_style")
                )
        for w in image_context.structured.uncertainty_warnings[:6]:
            assumption_objs.append(
                GenerationAssumption(
                    text=w,
                    source="vision",
                    confidence=image_context.structured.confidence,
                )
            )
        if image_context.warnings:
            for w in image_context.warnings[:4]:
                assumption_objs.append(GenerationAssumption(text=f"Vision: {w}", source="vision"))

        block_reasons = self._generation_blockers(
            image_context=image_context,
            semantic_plan=merged_plan,
        )
        if block_reasons:
            topic_validation = TopicGenerationValidation.from_chat_dita_validation(
                ChatDitaValidationResult(
                    valid=False,
                    structural_issues=block_reasons,
                    review_issues=image_context.warnings[:8] + image_context.structured.uncertainty_warnings[:8],
                )
            )
            for reason in block_reasons:
                assumption_objs.append(
                    GenerationAssumption(
                        text=reason,
                        source="pipeline",
                        confidence=image_context.structured.confidence,
                    )
                )
            message = self._build_screenshot_review_required_message(
                title=merged_plan.title,
                dita_type=merged_plan.dita_type,
                reasons=block_reasons,
            image_context=image_context,
            )
            debug = TopicGenerationDebug(
                review_quality_score=val.review_snapshot.get("quality_score")
                if isinstance(val.review_snapshot, dict)
                else None,
                strict_validation=opts.strict_validation,
                style_strictness=strictness,
                output_mode=opts.output_mode,
                reference_guided_enabled=_REFERENCE_GUIDED_FLAG,
                authoring_trace_id=authoring_trace_id,
                pipeline_run_id=trace.run_id,
                pipeline_version=trace.pipeline_version,
                pipeline_stages=trace.to_debug_list(),
                serialization_mode=s7.mode,
                had_jira_context=bool((payload.jira_context or "").strip()),
                link_recommendation_count=0,
                resolved_authoring_pattern=_resolved_authoring_pattern_from_trace(trace),
                screenshot_type=(
                    image_context.structured.screenshot_type_classification.screenshot_type
                    if image_context.structured.screenshot_type_classification
                    else None
                ),
                screenshot_type_confidence=(
                    image_context.structured.screenshot_type_classification.confidence
                    if image_context.structured.screenshot_type_classification
                    else None
                ),
                screenshot_intent_route=(
                    image_context.structured.screenshot_intent_route_decision.chosen_route
                    if image_context.structured.screenshot_intent_route_decision
                    else None
                ),
                reference_adoption_mode=reference_adoption.mode if reference_adoption else None,
                reference_adoption_warnings=list(reference_adoption.warnings[:6]) if reference_adoption else [],
            )
            log_authoring_trace_completed(
                authoring_trace_id=authoring_trace_id,
                session_id=session_id,
                user_id=user_id,
            tenant_id=tenant_id,
                pipeline_run_id=trace.run_id,
                pipeline_version=trace.pipeline_version,
                status="invalid",
                dita_type=str(merged_plan.dita_type),
                validation_valid=False,
                validation_error_count=len(block_reasons),
                validation_warning_count=min(
                    len(image_context.warnings) + len(image_context.structured.uncertainty_warnings),
                    16,
                ),
                had_reference_dita=bool(collected.reference_dita),
                parse_reference_ok=parse_ref_ok,
                vision_provider=image_context.vision_provider,
                serialization_mode=s7.mode,
                duration_ms=run_timer.elapsed_ms(),
                generated_asset_id=None,
            )
            logger.warning_structured(
                "chat_topic_gen_blocked_for_low_signal_screenshot",
                extra_fields={
                    "event": "chat_topic_gen_blocked_for_low_signal_screenshot",
                    "authoring_trace_id": authoring_trace_id,
                    "pipeline_run_id": trace.run_id,
                    "session_id": session_id,
                    "tenant_id": tenant_id,
                    "vision_provider": image_context.vision_provider,
                    "route": self._intent_route_from_image_context(image_context),
                    "confidence": image_context.structured.confidence,
                    "block_reason_count": len(block_reasons),
                },
            )
            return ChatDitaAuthoringResult(
                status="invalid",
                title=merged_plan.title,
                dita_type=merged_plan.dita_type,
                xml_preview="",
                validation=topic_validation,
                saved_asset_path=None,
                artifact_url=None,
                actions=[
                    ChatAction(
                        key="regenerate",
                        label="Regenerate",
                        description="Retry with a clearer screenshot or configure a vision-capable model before regenerating.",
                    )
                ],
                message=message,
                semantic_plan=None,
                image_context=image_context,
                reference_summaries=[reference_summary],
                assumptions=assumption_objs[:16],
                style_profile_diff_summary=None,
                screenshot_confidence=image_context.structured.confidence,
                explanation="The screenshot evidence was too weak to generate reliable DITA XML safely.",
                link_recommendations=[],
                debug=debug,
                reference_adoption_decision=reference_adoption,
            )

        final_xml = val.normalized_xml
        validation_result = val.validation_result
        review_snapshot = val.review_snapshot
        repaired = False
        if s9 is not None:
            final_xml = s9.xml
            validation_result = s9.validation_result
            review_snapshot = s9.review_snapshot
            repaired = bool(s9.repaired)

        link_recommendations = build_link_recommendations(final_xml)
        topic_validation = TopicGenerationValidation.from_chat_dita_validation(validation_result)

        artifact_ref: ChatAttachmentRef | None = None
        saved_asset_path: str | None = None
        # Persist full XML whenever we have body content so the UI workspace can fetch it
        # even when validation failed (user may fix issues in the editor).
        if final_xml.strip():
            artifact_ref = save_text_asset(
                session_id=session_id,
                user_id=user_id,
                kind="generated_dita",
                filename=opts.file_name or _default_file_name(merged_plan.title, merged_plan.dita_type),
                content=final_xml,
            )
        if validation_result.valid and opts.save_path and artifact_ref:
                saved_asset_path = self._save_to_aem(
                    xml=final_xml,
                    file_name=artifact_ref.filename,
                save_path=opts.save_path,
                )

        status = "invalid"
        if validation_result.valid and saved_asset_path:
            status = "saved"
        elif validation_result.valid and repaired:
            status = "repaired"
        elif validation_result.valid:
            status = "valid"

        actions = [
            ChatAction(
                key="open_in_editor",
                label="Open XML",
                url=artifact_ref.url if artifact_ref else None,
                description="Open the generated XML artifact in the browser.",
            ),
            ChatAction(
                key="regenerate",
                label="Regenerate",
                description="Edit the prompt or attachments and resend to generate a fresh topic.",
            ),
        ]
        if saved_asset_path:
            actions.append(
                ChatAction(
                    key="saved_to_aem",
                    label="Saved to AEM",
                    description=saved_asset_path,
                )
            )

        style_diff = None
        if opts.output_mode == "xml_style_diff":
            style_diff = _reference_adoption_summary(reference_adoption)
        elif reference_adoption and reference_adoption.warnings:
            style_diff = _reference_adoption_summary(reference_adoption)

        explanation = None
        if opts.output_mode in ("xml_explanation", "xml_validation", "xml_style_diff"):
            explanation = (
                f"Topic type: {merged_plan.dita_type} (screenshot confidence {image_context.structured.confidence:.2f}). "
                f"Serialization: {s7.mode}."
            )

        message = self._build_result_message(
            status=status,
            title=merged_plan.title,
            dita_type=merged_plan.dita_type,
            saved_asset_path=saved_asset_path,
            validation=validation_result,
        )

        logger.info_structured(
            "chat_topic_gen_succeeded" if status != "invalid" else "chat_topic_gen_failed",
            extra_fields={
                "event": "chat_topic_gen_succeeded" if status != "invalid" else "chat_topic_gen_failed",
                "authoring_trace_id": authoring_trace_id,
                "pipeline_run_id": trace.run_id,
                "session_id": session_id,
                "inferred_topic_type": merged_plan.dita_type,
                "topic_type_override": bool(opts.dita_type),
                "style_strictness": strictness,
                "validation_error_count": len(validation_result.validator_errors)
                + len(validation_result.aem_guides_validation_errors)
                + len(validation_result.structural_issues),
                "warning_count": len(validation_result.validator_warnings),
                "vision_provider": image_context.vision_provider,
                "had_reference_dita": bool(collected.reference_dita),
                "parse_reference_ok": parse_ref_ok,
            },
        )

        err_ct = (
            len(validation_result.validator_errors)
            + len(validation_result.aem_guides_validation_errors)
            + len(validation_result.structural_issues)
        )
        warn_ct = len(validation_result.validator_warnings)
        log_authoring_trace_completed(
            authoring_trace_id=authoring_trace_id,
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            pipeline_run_id=trace.run_id,
            pipeline_version=trace.pipeline_version,
            status=status,
            dita_type=str(merged_plan.dita_type),
            validation_valid=bool(validation_result.valid),
            validation_error_count=err_ct,
            validation_warning_count=warn_ct,
            had_reference_dita=bool(collected.reference_dita),
            parse_reference_ok=parse_ref_ok,
            vision_provider=image_context.vision_provider,
            serialization_mode=s7.mode,
            duration_ms=run_timer.elapsed_ms(),
            generated_asset_id=artifact_ref.asset_id if artifact_ref else None,
        )

        debug = TopicGenerationDebug(
            review_quality_score=review_snapshot.get("quality_score")
            if isinstance(review_snapshot, dict)
            else None,
            strict_validation=opts.strict_validation,
            style_strictness=strictness,
            output_mode=opts.output_mode,
            reference_guided_enabled=_REFERENCE_GUIDED_FLAG,
            authoring_trace_id=authoring_trace_id,
            pipeline_run_id=trace.run_id,
            pipeline_version=trace.pipeline_version,
            pipeline_stages=trace.to_debug_list(),
            serialization_mode=s7.mode,
            had_jira_context=bool((payload.jira_context or "").strip()),
            link_recommendation_count=len(link_recommendations),
            resolved_authoring_pattern=_resolved_authoring_pattern_from_trace(trace),
            screenshot_type=(
                image_context.structured.screenshot_type_classification.screenshot_type
                if image_context.structured.screenshot_type_classification
                else None
            ),
            screenshot_type_confidence=(
                image_context.structured.screenshot_type_classification.confidence
                if image_context.structured.screenshot_type_classification
                else None
            ),
            screenshot_intent_route=(
                image_context.structured.screenshot_intent_route_decision.chosen_route
                if image_context.structured.screenshot_intent_route_decision
                else None
            ),
            reference_adoption_mode=reference_adoption.mode if reference_adoption else None,
            reference_adoption_warnings=list(reference_adoption.warnings[:6]) if reference_adoption else [],
            extensions={
                "reference_adoption_mode": reference_adoption.mode if reference_adoption else "",
                "reference_target_root": reference_adoption.target_root_type if reference_adoption else "",
            },
        )

        return ChatDitaAuthoringResult(
            status=status,
            title=merged_plan.title,
            dita_type=merged_plan.dita_type,
            xml_preview=_shorten(final_xml, limit=3200),
            validation=topic_validation,
            saved_asset_path=saved_asset_path,
            artifact_url=artifact_ref.url if artifact_ref else None,
            actions=actions,
            message=message,
            semantic_plan=merged_plan,
            image_context=image_context,
            reference_summaries=[reference_summary],
            reference_adoption_decision=reference_adoption,
            assumptions=assumption_objs[:12],
            style_profile_diff_summary=style_diff,
            screenshot_confidence=image_context.structured.confidence,
            explanation=explanation,
            link_recommendations=link_recommendations,
            debug=debug,
        )

    def _collect_attachments(self, attachments: list[ChatAttachmentRef]) -> _CollectedAttachments:
        image = next((item for item in attachments if item.kind == "image"), None)
        reference = next((item for item in attachments if item.kind == "reference_dita"), None)
        image_bytes = None
        reference_text = ""
        if image:
            image_bytes, _ = read_asset_bytes(image.asset_id)
        if reference:
            reference_bytes, _ = read_asset_bytes(reference.asset_id)
            reference_text = reference_bytes.decode("utf-8", errors="ignore")
        return _CollectedAttachments(
            image=image,
            image_bytes=image_bytes,
            reference_dita=reference,
            reference_text=reference_text,
        )

    async def _summarize_reference_dita(
        self,
        *,
        reference_attachment: ChatAttachmentRef | None,
        reference_text: str,
    ) -> ChatReferenceDitaSummary:
        return await _reference_dita_analyzer.summarize_attachment(
            reference_attachment=reference_attachment,
            reference_text=reference_text,
        )

    def _content_first_route_type(
        self,
        *,
        route: str,
        options: ChatDitaGenerationOptions,
        image_context: ChatImageContext,
    ) -> str:
        explicit = self._clean_dita_type(str(options.dita_type or ""))
        if explicit and explicit != "map":
            return explicit

        structured = image_context.structured
        if route == "procedural_authoring_mode":
            return "task"
        if route == "reference_extraction_mode":
            return "reference"
        if route in {"structure_reconstruction_mode", "conceptual_diagram_mode"}:
            return "concept"
        if route == "mixed_content_mode":
            if structured.settings_reference_model or structured.field_value_pairs or structured.tables:
                return "reference"
            if structured.procedural_model or structured.numbered_steps:
                return "task"
            if structured.diagram_interpretation and structured.diagram_interpretation.content_orientation == "conceptual":
                return "concept"
            return "topic"
        if structured.settings_reference_model or structured.field_value_pairs or structured.tables:
            return "reference"
        if structured.procedural_model or structured.numbered_steps:
            return "task"
        if structured.diagram_interpretation and structured.diagram_interpretation.content_orientation == "conceptual":
            return "concept"
        return "topic"

    def _build_reference_serializer_policy(
        self,
        *,
        profile: ReferenceStyleProfile | None,
        target_root_type: str,
    ) -> ReferenceSerializerPolicy | None:
        if not profile:
            return None

        habits = set(profile.structural_habits or [])
        inline = profile.inline_element_usage or {}
        preferred_section_name_map: dict[str, str] = {}
        preferred_section_names: list[str] = []
        body_titles = [title.strip() for title in (profile.body_section_titles or []) if title and title.strip()]

        if target_root_type == "task":
            preferred_section_name_map = {
                "prereq": "Prerequisites",
                "context": "Context",
                "steps": "Steps",
                "examples": "Examples",
                "example": "Examples",
                "result": "Result",
            }
            preferred_section_names = [
                name for name in ("Prerequisites", "Context", "Steps", "Examples", "Result")
            ]
        elif target_root_type == "reference":
            preferred_section_name_map = {
                "field details": "Properties",
                "properties": "Properties",
                "parameter tables": "Parameter tables",
                "properties tables": "Parameter tables",
                "dialog layout": "Dialog layout",
            }
            preferred_section_names = [
                name for name in ("Dialog layout", "Properties", "Parameter tables") if name
            ]
            for title in body_titles:
                lower = title.lower()
                if _title_contains_any_token(lower, "property", "properties", "field", "fields", "setting", "settings"):
                    preferred_section_name_map["field details"] = title
                    preferred_section_name_map["properties"] = title
                if _title_contains_any_token(lower, "parameter", "parameters", "option", "options", "table", "tables"):
                    preferred_section_name_map["parameter tables"] = title
                    preferred_section_name_map["properties tables"] = title
                if _title_contains_any_token(lower, "dialog", "layout", "tab", "tabs", "panel", "panels"):
                    preferred_section_name_map["dialog layout"] = title
            if body_titles:
                preferred_section_names = body_titles[:8]
        elif target_root_type == "concept":
            preferred_section_name_map = {
                "overview": "Overview",
                "key entities": "Key entities",
                "relationships": "Relationships",
            }
            preferred_section_names = ["Overview", "Key entities", "Relationships"]
            for title in body_titles:
                lower = title.lower()
                if _title_contains_any_token(lower, "overview", "introduction", "summary", "about"):
                    preferred_section_name_map["overview"] = title
                if _title_contains_any_token(lower, "relationship", "relationships", "workflow", "flow"):
                    preferred_section_name_map["relationships"] = title
                if _title_contains_any_token(lower, "entity", "entities", "component", "components", "hierarchy"):
                    preferred_section_name_map["key entities"] = title
            if body_titles:
                preferred_section_names = body_titles[:8]
        elif target_root_type == "topic" and body_titles:
            preferred_section_names = body_titles[:8]

        seq = list(profile.taskbody_top_level_sequence or []) if target_root_type == "task" else []
        prefer_properties = target_root_type == "reference" and bool(
            {"uses_properties", "uses_table", "uses_tgroup", "uses_dl"} & habits
        )
        prefer_cals = target_root_type == "reference" and bool({"uses_table", "uses_tgroup"} & habits)
        prefer_examples_before_result = False
        if seq:
            try:
                prefer_examples_before_result = seq.index("example") < seq.index("result")
            except ValueError:
                prefer_examples_before_result = False

        return ReferenceSerializerPolicy(
            target_root_type=target_root_type,
            preferred_top_level_order=list(profile.child_order_top_level or []),
            preferred_taskbody_sequence=seq,
            preferred_section_names=preferred_section_names,
            preferred_section_name_map=preferred_section_name_map,
            preferred_structural_habits=list(profile.structural_habits or []),
            prefer_prolog=bool(profile.uses_prolog),
            prefer_properties_layout=prefer_properties,
            prefer_cals_tables=prefer_cals,
            prefer_task_examples_before_result=prefer_examples_before_result,
            prefer_uicontrol=bool((inline.get("uicontrol") or 0) > 0),
            prefer_menucascade=bool((inline.get("menucascade") or 0) > 0),
            prefer_ui_type_attributes=bool(profile.reference_uses_ui_type_attributes),
            tone_hint=profile.tone_hint or "",
        )

    def _resolve_reference_adoption_decision(
        self,
        *,
        route: str,
        options: ChatDitaGenerationOptions,
        reference_summary: ChatReferenceDitaSummary,
        image_context: ChatImageContext,
    ) -> ReferenceAdoptionDecision:
        target_root_type = self._content_first_route_type(
            route=route,
            options=options,
            image_context=image_context,
        )
        profile = reference_summary.style_profile
        if not profile:
            return ReferenceAdoptionDecision(
                mode="partial_adoption",
                target_root_type=target_root_type,
                warnings=["No reference style profile was available, so only screenshot and prompt evidence were used."],
            )

        ref_root = self._clean_dita_type(profile.root_local_name or "") or "topic"
        if ref_root == target_root_type:
            mode = "compatible_adoption"
        elif ref_root == "topic":
            mode = "partial_adoption"
        else:
            mode = "conflict_preserve_content"

        policy = self._build_reference_serializer_policy(profile=profile, target_root_type=target_root_type)
        adopted_constraints: list[str] = []
        rejected_constraints: list[str] = []
        warnings: list[str] = []

        if ref_root == target_root_type:
            adopted_constraints.append(f"reference root <{ref_root}> matches the routed content type")
        elif ref_root == "topic":
            adopted_constraints.append("generic topic reference used as a structural style guide only")
            warnings.append(
                "The reference uses a generic topic root, so only compatible structure and serializer habits will be adopted."
            )
        else:
            rejected_constraints.append(
                f"reference root <{ref_root}> was not allowed to override the routed <{target_root_type}> content intent"
            )
            warnings.append(
                f"Reference root <{ref_root}> conflicts with screenshot/prompt intent, so content meaning stays <{target_root_type}>."
            )

        if policy:
            if policy.preferred_taskbody_sequence:
                if target_root_type == "task":
                    adopted_constraints.append("taskbody sequence from the reference")
                else:
                    rejected_constraints.append("taskbody sequence (incompatible with the chosen output root)")
            if policy.prefer_properties_layout:
                if target_root_type == "reference":
                    adopted_constraints.append("properties/table-oriented reference body layout")
                else:
                    rejected_constraints.append("properties layout bias (incompatible with the chosen output root)")
            if policy.prefer_cals_tables:
                adopted_constraints.append("CALS-style table formatting")
            if policy.prefer_prolog:
                adopted_constraints.append("prolog presence and metadata shape")
            if policy.prefer_uicontrol:
                adopted_constraints.append("uicontrol inline formatting")
            if policy.prefer_menucascade:
                adopted_constraints.append("menucascade inline formatting")
            if policy.prefer_ui_type_attributes:
                adopted_constraints.append("ui-type attribute usage")
            if policy.preferred_top_level_order:
                adopted_constraints.append("top-level child ordering hints")
            if policy.preferred_section_name_map:
                adopted_constraints.append("reference-compatible section naming")

        return ReferenceAdoptionDecision(
            mode=mode,
            target_root_type=target_root_type,
            adopted_constraints=adopted_constraints,
            rejected_constraints=rejected_constraints,
            warnings=warnings,
            effective_serializer_habits=list(policy.preferred_structural_habits or []) if policy else [],
            serializer_policy=policy,
        )

    async def _build_semantic_plan(
        self,
        *,
        user_prompt: str,
        image_context: ChatImageContext,
        reference_summary: ChatReferenceDitaSummary,
        options: ChatDitaGenerationOptions,
    ) -> ChatSemanticPlan:
        route = self._intent_route_from_image_context(image_context)
        reference_adoption = self._resolve_reference_adoption_decision(
            route=route,
            options=options,
            reference_summary=reference_summary,
            image_context=image_context,
        )
        route_specific_plan = self._build_route_specific_plan(
            route=route,
            user_prompt=user_prompt,
            image_context=image_context,
            reference_summary=reference_summary,
            options=options,
            reference_adoption=reference_adoption,
        )
        if route_specific_plan is not None:
            return route_specific_plan

        dita_type = reference_adoption.target_root_type or self._content_first_route_type(
            route=route,
            options=options,
            image_context=image_context,
        )
        if not is_llm_available():
            return self._fallback_plan(
                user_prompt=user_prompt,
                dita_type=dita_type,
                image_context=image_context,
                reference_summary=reference_summary,
                reference_adoption=reference_adoption,
            )

        profile_payload = {}
        if reference_summary.style_profile:
            profile_payload = reference_summary.style_profile.model_dump(mode="json")

        plan_system = (
                "You create intermediate semantic plans for enterprise DITA authoring.\n"
                "Return JSON only with keys: title, dita_type, shortdesc, audience, purpose, style_notes, source_notes, sections.\n"
            "sections must be an array of {name, purpose, details}. Keep it conservative and validation-safe.\n"
            "Honor reference_adoption.serializer_policy and reference_style_profile structural habits when choosing section names and body shape; do not copy reference ids or hrefs.\n"
            "Do not invent business/domain content that is not directly visible in the screenshot, prompt, or reference style profile.\n"
            "Use route-specific evidence from screenshot_intent_route_decision when deciding structure."
        )
        ap = getattr(options, "authoring_pattern", "default")
        if ap == "cisco_task":
            plan_system += "\n\n" + cisco_semantic_plan_instructions(
                reference_summary.style_profile,
                xref_placeholders=bool(getattr(options, "xref_placeholders", False)),
            )
        elif ap == "cisco_reference":
            plan_system += "\n\n" + cisco_reference_semantic_plan_instructions()

        raw = await generate_json(
            system_prompt=plan_system,
            user_prompt=json.dumps(
                {
                    "user_prompt": user_prompt,
                    "screenshot_intent_route": route,
                    "generation_options": options.model_dump(mode="json"),
                    "image_context": image_context.model_dump(mode="json"),
                    "reference_summary": reference_summary.model_dump(mode="json"),
                    "reference_adoption": reference_adoption.model_dump(mode="json"),
                    "reference_style_profile": profile_payload,
                    "allowed_dita_types": ["topic", "task", "concept", "reference"],
                },
                ensure_ascii=True,
                indent=2,
            ),
            max_tokens=1600 if ap == "cisco_task" else 1200,
            step_name="chat_dita_authoring_plan",
        )
        resolved_type = self._clean_dita_type(str(raw.get("dita_type") or dita_type)) or dita_type
        if reference_adoption and reference_adoption.target_root_type in {"task", "concept", "reference", "topic"}:
            resolved_type = reference_adoption.target_root_type
        sections: list[ChatSemanticPlanSection] = []
        for item in raw.get("sections") or []:
            if not isinstance(item, dict):
                continue
            details = [str(detail).strip() for detail in (item.get("details") or []) if str(detail).strip()]
            sections.append(
                ChatSemanticPlanSection(
                    name=str(item.get("name") or "").strip() or "section",
                    purpose=str(item.get("purpose") or "").strip() or "Document the relevant content from the screenshot.",
                    details=details[:8],
                )
            )
        if not sections:
            sections = self._fallback_sections(resolved_type, image_context)
        return ChatSemanticPlan(
            title=str(raw.get("title") or image_context.summary or "Generated topic").strip() or "Generated topic",
            dita_type=resolved_type,
            shortdesc=str(raw.get("shortdesc") or "Use this topic to document the captured workflow.").strip(),
            audience=str(raw.get("audience") or "AEM Guides authors").strip(),
            purpose=str(raw.get("purpose") or user_prompt).strip(),
            sections=sections,
            style_notes=[str(item).strip() for item in (raw.get("style_notes") or reference_summary.style_notes or []) if str(item).strip()][:8],
            source_notes=[str(item).strip() for item in (raw.get("source_notes") or []) if str(item).strip()][:8],
            reference_adoption=reference_adoption,
        )

    def _intent_route_from_image_context(self, image_context: ChatImageContext) -> str:
        decision = image_context.structured.screenshot_intent_route_decision
        return decision.chosen_route if decision is not None else "safe_fallback_mode"

    def _build_route_specific_plan(
        self,
        *,
        route: str,
        user_prompt: str,
        image_context: ChatImageContext,
        reference_summary: ChatReferenceDitaSummary,
        options: ChatDitaGenerationOptions,
        reference_adoption: ReferenceAdoptionDecision,
    ) -> ChatSemanticPlan | None:
        if route == "structure_reconstruction_mode":
            return self._build_structure_reconstruction_plan(
                user_prompt=user_prompt,
                image_context=image_context,
                reference_summary=reference_summary,
                options=options,
                reference_adoption=reference_adoption,
            )
        if route == "procedural_authoring_mode":
            return self._build_procedural_route_plan(
                user_prompt=user_prompt,
                image_context=image_context,
                reference_summary=reference_summary,
                options=options,
                reference_adoption=reference_adoption,
            )
        if route == "reference_extraction_mode":
            return self._build_reference_route_plan(
                user_prompt=user_prompt,
                image_context=image_context,
                reference_summary=reference_summary,
                options=options,
                reference_adoption=reference_adoption,
            )
        if route == "conceptual_diagram_mode":
            return self._build_conceptual_diagram_plan(
                user_prompt=user_prompt,
                image_context=image_context,
                reference_summary=reference_summary,
                options=options,
                reference_adoption=reference_adoption,
            )
        if route == "mixed_content_mode":
            return self._build_mixed_content_plan(
                user_prompt=user_prompt,
                image_context=image_context,
                reference_summary=reference_summary,
                options=options,
                reference_adoption=reference_adoption,
            )
        if route == "safe_fallback_mode":
            return self._build_safe_fallback_route_plan(
                user_prompt=user_prompt,
                image_context=image_context,
                reference_summary=reference_summary,
                options=options,
                reference_adoption=reference_adoption,
            )
        return None

    def _route_default_dita_type(
        self,
        *,
        route: str,
        options: ChatDitaGenerationOptions,
        reference_summary: ChatReferenceDitaSummary,
        image_context: ChatImageContext,
    ) -> str:
        explicit = self._clean_dita_type(str(options.dita_type or ""))
        if explicit and explicit != "map":
            return explicit

        profile_root = self._clean_dita_type(
            reference_summary.style_profile.root_local_name if reference_summary.style_profile else ""
        )
        structured = image_context.structured

        if route == "procedural_authoring_mode":
            return "task"
        if route == "reference_extraction_mode":
            return profile_root if profile_root in {"reference", "topic"} else "reference"
        if route in {"structure_reconstruction_mode", "conceptual_diagram_mode"}:
            return profile_root if profile_root in {"concept", "topic"} else "concept"
        if route == "mixed_content_mode":
            return profile_root if profile_root in {"task", "concept", "reference", "topic"} else "topic"
        if structured.settings_reference_model or structured.field_value_pairs or structured.tables:
            return "reference"
        if structured.procedural_model or structured.numbered_steps:
            return "task"
        return profile_root if profile_root in {"concept", "reference", "topic"} else "concept"

    def _build_structure_reconstruction_plan(
        self,
        *,
        user_prompt: str,
        image_context: ChatImageContext,
        reference_summary: ChatReferenceDitaSummary,
        options: ChatDitaGenerationOptions,
        reference_adoption: ReferenceAdoptionDecision,
    ) -> ChatSemanticPlan:
        structured = image_context.structured
        dita_type = reference_adoption.target_root_type or "concept"
        title = (structured.title or reference_summary.title or "Visible structure").strip() or "Visible structure"

        hierarchy_lines: list[str] = []
        for node in structured.semantic_hierarchy[:12]:
            if node.title.strip():
                hierarchy_lines.append(f"Level {node.level}: {node.title.strip()}")

        visible_elements = self._visible_structure_elements(structured)
        visible_text_blocks = self._visible_structure_text(structured, image_context)

        sections: list[ChatSemanticPlanSection] = []
        if visible_elements:
            sections.append(
                ChatSemanticPlanSection(
                    name="visible structure",
                    purpose="",
                    details=visible_elements[:18],
                )
            )
        if hierarchy_lines:
            sections.append(
                ChatSemanticPlanSection(
                    name="hierarchy",
                    purpose="",
                    details=hierarchy_lines[:18],
                )
            )
        if visible_text_blocks:
            sections.append(
                ChatSemanticPlanSection(
                    name="visible authored text",
                    purpose="",
                    details=visible_text_blocks[:18],
                )
            )
        if not sections:
            sections.append(
                ChatSemanticPlanSection(
                    name="visible structure",
                    purpose="",
                    details=[image_context.summary or "Visible structure could be only partially recovered from the screenshot."],
                )
            )

        return ChatSemanticPlan(
            title=title,
            dita_type=dita_type,  # type: ignore[arg-type]
            shortdesc="Visible DITA structure and authored text recovered from the screenshot.",
            audience="AEM Guides authors",
            purpose=user_prompt,
            sections=sections,
            style_notes=[
                "Preserve visible DITA hierarchy and text exactly where possible.",
                "Avoid inventing domain or business content beyond what the screenshot shows.",
            ],
            source_notes=[
                "Built from editor-structure screenshot evidence using structure_reconstruction_mode.",
            ],
            reference_adoption=reference_adoption,
        )

    def _build_procedural_route_plan(
        self,
        *,
        user_prompt: str,
        image_context: ChatImageContext,
        reference_summary: ChatReferenceDitaSummary,
        options: ChatDitaGenerationOptions,
        reference_adoption: ReferenceAdoptionDecision,
    ) -> ChatSemanticPlan:
        structured = image_context.structured
        proc = structured.procedural_model
        dita_type = reference_adoption.target_root_type or "task"
        title = (structured.title or (proc.title if proc else "") or reference_summary.title or "Recovered procedure").strip()
        title = title or "Recovered procedure"

        sections_by_name: dict[str, ChatSemanticPlanSection] = {}
        name_map = (reference_adoption.serializer_policy.preferred_section_name_map if reference_adoption.serializer_policy else {}) or {}

        def add_section(name: str, details: list[str]) -> None:
            clean = [item for item in details if item and item.strip()]
            if not clean:
                return
            display = name_map.get(name.lower(), name)
            sections_by_name[name.lower()] = ChatSemanticPlanSection(
                name=display,
                purpose="",
                details=clean,
            )

        if proc and proc.prerequisites:
            add_section("prereq", [item.text for item in proc.prerequisites[:10]])
        if proc and proc.context:
            add_section("context", [item.text for item in proc.context[:10]])

        step_details: list[str] = []
        if proc and proc.steps:
            for step in proc.steps[:20]:
                info = " ".join(line.strip() for line in step.info_lines[:2] if line.strip()).strip()
                detail = f"{step.command} || {info}" if info else step.command
                if detail.strip():
                    step_details.append(detail.strip())
        elif structured.numbered_steps:
            step_details.extend([item.strip() for item in structured.numbered_steps[:20] if item.strip()])
        if step_details:
            add_section("steps", step_details)

        if proc and proc.result:
            add_section("result", [item.text for item in proc.result[:10]])
        if proc and proc.examples:
            add_section("examples", [item.text for item in proc.examples[:8]])
        if structured.acceptance_criteria:
            add_section("acceptance criteria", [item.strip() for item in structured.acceptance_criteria[:12]])
        ordered_sections: list[ChatSemanticPlanSection] = []
        preferred_seq = (reference_adoption.serializer_policy.preferred_taskbody_sequence if reference_adoption.serializer_policy else []) or []
        for key in preferred_seq:
            if key.lower() == "postreq" and "acceptance criteria" in sections_by_name:
                ordered_sections.append(sections_by_name.pop("acceptance criteria"))
                continue
            section = sections_by_name.pop(key.lower(), None)
            if section:
                ordered_sections.append(section)
        ordered_sections.extend(sections_by_name.values())
        sections = ordered_sections or self._fallback_sections("task", image_context)

        return ChatSemanticPlan(
            title=title,
            dita_type=dita_type,  # type: ignore[arg-type]
            shortdesc="Procedure recovered from the screenshot with preserved step structure.",
            audience="AEM Guides authors",
            purpose=user_prompt,
            sections=sections,
            style_notes=[
                "Preserve visible step order, substeps, notes, and UI control names.",
                "Do not infer missing actions from weak evidence.",
            ],
            source_notes=["Built from procedural screenshot evidence using procedural_authoring_mode."],
            reference_adoption=reference_adoption,
        )

    def _build_reference_route_plan(
        self,
        *,
        user_prompt: str,
        image_context: ChatImageContext,
        reference_summary: ChatReferenceDitaSummary,
        options: ChatDitaGenerationOptions,
        reference_adoption: ReferenceAdoptionDecision,
    ) -> ChatSemanticPlan:
        structured = image_context.structured
        settings = structured.settings_reference_model
        dita_type = reference_adoption.target_root_type or "reference"
        title = (structured.title or (settings.title if settings else "") or reference_summary.title or "Recovered reference information").strip()
        title = title or "Recovered reference information"
        name_map = (reference_adoption.serializer_policy.preferred_section_name_map if reference_adoption.serializer_policy else {}) or {}
        properties_name = name_map.get("field details", "field details")
        tables_name = name_map.get("parameter tables", "parameter tables")
        dialog_name = name_map.get("dialog layout", "dialog layout")

        sections: list[ChatSemanticPlanSection] = []
        if settings and settings.tabs:
            tab_line = "Visible tabs: " + ", ".join(settings.tabs[:12])
            if settings.active_tab:
                tab_line += f". Active tab: {settings.active_tab}"
            sections.append(ChatSemanticPlanSection(name=dialog_name, purpose="", details=[tab_line]))

        if settings:
            for sec in settings.sections[:15]:
                details: list[str] = []
                details.extend([line.strip() for line in sec.description[:4] if line.strip()])
                for fld in sec.fields[:30]:
                    row = f"{fld.label}: {fld.value}".strip(": ")
                    if fld.helper_text:
                        row += " - " + " ".join(item.strip() for item in fld.helper_text[:3] if item.strip())
                    if fld.options:
                        opts = ", ".join(
                            f"{opt.label}{' (selected)' if opt.selected else ''}"
                            for opt in fld.options[:12]
                            if opt.label.strip()
                        )
                        if opts:
                            row += f" [{opts}]"
                    if row.strip():
                        details.append(row.strip())
                for table in sec.parameter_tables[:2]:
                    table_summary = self._summarize_table_for_plan(table.rows, table.headers, table.caption)
                    if table_summary:
                        details.append(table_summary)
                if details:
                    sections.append(
                        ChatSemanticPlanSection(
                            name=(sec.title or "settings").strip()[:120] or "settings",
                            purpose="",
                            details=details[:40],
                        )
                    )

        if structured.field_value_pairs and not any(s.name.lower() in {"field details", properties_name.lower()} for s in sections):
            sections.append(
                ChatSemanticPlanSection(
                    name=properties_name,
                    purpose="",
                    details=[
                        f"{pair.field}: {pair.value}".strip(": ")
                        for pair in structured.field_value_pairs[:20]
                        if pair.field.strip() or pair.value.strip()
                    ],
                )
            )
        if structured.tables and not any(s.name.lower() in {"parameter tables", tables_name.lower()} for s in sections):
            table_lines = [
                self._summarize_table_for_plan(table.rows, table.headers, table.caption)
                for table in structured.tables[:4]
            ]
            table_lines = [line for line in table_lines if line]
            if table_lines:
                sections.append(ChatSemanticPlanSection(name=tables_name, purpose="", details=table_lines[:8]))

        if not sections:
            sections = self._fallback_sections("reference", image_context)

        return ChatSemanticPlan(
            title=title,
            dita_type=dita_type,  # type: ignore[arg-type]
            shortdesc="Reference-style settings and field information recovered from the screenshot.",
            audience="AEM Guides authors",
            purpose=user_prompt,
            sections=sections,
            style_notes=[
                "Preserve field/value associations, settings groups, tabs, and parameter tables.",
                "Avoid converting settings panels into narrative or procedural prose.",
            ],
            source_notes=["Built from settings/reference screenshot evidence using reference_extraction_mode."],
            reference_adoption=reference_adoption,
        )

    def _build_conceptual_diagram_plan(
        self,
        *,
        user_prompt: str,
        image_context: ChatImageContext,
        reference_summary: ChatReferenceDitaSummary,
        options: ChatDitaGenerationOptions,
        reference_adoption: ReferenceAdoptionDecision,
    ) -> ChatSemanticPlan:
        structured = image_context.structured
        diagram = structured.diagram_interpretation
        dita_type = reference_adoption.target_root_type or "concept"
        title = (structured.title or reference_summary.title or "Recovered conceptual structure").strip() or "Recovered conceptual structure"

        sections: list[ChatSemanticPlanSection] = []
        overview_details = [
            item
            for item in [
                diagram.dominant_meaning if diagram else "",
                image_context.summary,
            ]
            if str(item).strip()
        ]
        if overview_details:
            sections.append(ChatSemanticPlanSection(name="overview", purpose="", details=overview_details[:4]))

        if diagram and diagram.key_entities:
            sections.append(
                ChatSemanticPlanSection(
                    name="key entities",
                    purpose="",
                    details=[entity.strip() for entity in diagram.key_entities[:24] if entity.strip()],
                )
            )

        if diagram and diagram.relationships:
            relationship_lines: list[str] = []
            for rel in diagram.relationships[:24]:
                source = rel.source.strip()
                target = rel.target.strip()
                if not source or not target:
                    continue
                link = f"{source} -> {target}"
                if rel.kind and rel.kind != "unknown":
                    link += f" ({rel.kind.replace('_', ' ')})"
                if rel.label.strip():
                    link += f": {rel.label.strip()}"
                relationship_lines.append(link)
            if relationship_lines:
                sections.append(ChatSemanticPlanSection(name="relationships", purpose="", details=relationship_lines))

        if diagram and diagram.groups:
            group_lines = [
                f"{group.name}: {', '.join(member for member in group.members[:12] if member.strip())}".strip(": ")
                for group in diagram.groups[:16]
                if group.name.strip() or any(member.strip() for member in group.members)
            ]
            group_lines = [line for line in group_lines if line]
            if group_lines:
                sections.append(ChatSemanticPlanSection(name="grouping", purpose="", details=group_lines))

        visible_labels = [
            text for text in self._visible_structure_text(structured, image_context)[:16] if text.strip()
        ]
        if visible_labels and not any(section.name == "visible labels" for section in sections):
            sections.append(ChatSemanticPlanSection(name="visible labels", purpose="", details=visible_labels))

        if not sections:
            sections = self._fallback_sections(dita_type, image_context)

        return ChatSemanticPlan(
            title=title,
            dita_type=dita_type,  # type: ignore[arg-type]
            shortdesc="Conceptual structure and relationships recovered from the attached image.",
            audience="AEM Guides authors",
            purpose=user_prompt,
            sections=sections,
            style_notes=[
                "Preserve entities, hierarchy, grouping, and relationships before adding explanatory prose.",
                "Do not force conceptual diagrams into procedural steps without explicit step evidence.",
            ],
            source_notes=["Built from conceptual diagram evidence using conceptual_diagram_mode."],
            reference_adoption=reference_adoption,
        )

    def _build_mixed_content_plan(
        self,
        *,
        user_prompt: str,
        image_context: ChatImageContext,
        reference_summary: ChatReferenceDitaSummary,
        options: ChatDitaGenerationOptions,
        reference_adoption: ReferenceAdoptionDecision,
    ) -> ChatSemanticPlan:
        structured = image_context.structured
        proc = structured.procedural_model
        settings = structured.settings_reference_model
        diagram = structured.diagram_interpretation
        dita_type = reference_adoption.target_root_type or "topic"
        title = (structured.title or reference_summary.title or "Recovered mixed screenshot content").strip() or "Recovered mixed screenshot content"

        sections: list[ChatSemanticPlanSection] = []
        if proc and proc.steps:
            sections.append(
                ChatSemanticPlanSection(
                    name="procedure evidence",
                    purpose="",
                    details=[
                        f"{step.command} || {' '.join(line.strip() for line in step.info_lines[:2] if line.strip()).strip()}".rstrip(" |")
                        if any(line.strip() for line in step.info_lines[:2])
                        else step.command
                        for step in proc.steps[:16]
                        if step.command.strip()
                    ],
                )
            )
        elif structured.numbered_steps:
            sections.append(
                ChatSemanticPlanSection(
                    name="procedure evidence",
                    purpose="",
                    details=[item.strip() for item in structured.numbered_steps[:16] if item.strip()],
                )
            )

        if settings and settings.sections:
            ref_lines: list[str] = []
            for section in settings.sections[:10]:
                if section.title.strip():
                    ref_lines.append(section.title.strip())
                ref_lines.extend(
                    f"{field.label}: {field.value}".strip(": ")
                    for field in section.fields[:12]
                    if field.label.strip() or field.value.strip()
                )
            if ref_lines:
                sections.append(
                    ChatSemanticPlanSection(
                        name="reference evidence",
                        purpose="",
                        details=ref_lines[:32],
                    )
                )
        elif structured.field_value_pairs:
            sections.append(
                ChatSemanticPlanSection(
                    name="reference evidence",
                    purpose="",
                    details=[
                        f"{pair.field}: {pair.value}".strip(": ")
                        for pair in structured.field_value_pairs[:20]
                        if pair.field.strip() or pair.value.strip()
                    ],
                )
            )

        if diagram and (diagram.key_entities or diagram.relationships):
            conceptual_lines = [item.strip() for item in diagram.key_entities[:16] if item.strip()]
            conceptual_lines.extend(
                f"{rel.source} -> {rel.target}".strip()
                for rel in diagram.relationships[:12]
                if rel.source.strip() and rel.target.strip()
            )
            if conceptual_lines:
                sections.append(
                    ChatSemanticPlanSection(
                        name="conceptual evidence",
                        purpose="",
                        details=conceptual_lines[:28],
                    )
                )

        visible_evidence = [
            text for text in self._visible_structure_text(structured, image_context)[:12] if text.strip()
        ]
        if visible_evidence:
            sections.append(ChatSemanticPlanSection(name="visible content", purpose="", details=visible_evidence))

        if structured.unresolved_blocks:
            sections.append(
                ChatSemanticPlanSection(
                    name="uncertain content",
                    purpose="",
                    details=[
                        f"{block.raw_text} ({block.reason})".strip()
                        for block in structured.unresolved_blocks[:8]
                        if block.raw_text.strip()
                    ],
                )
            )

        sections = [section for section in sections if any(detail.strip() for detail in section.details)]
        if not sections:
            sections = self._fallback_sections(dita_type, image_context)

        return ChatSemanticPlan(
            title=title,
            dita_type=dita_type,  # type: ignore[arg-type]
            shortdesc="Mixed procedural, reference, and structural evidence recovered from the attached image.",
            audience="AEM Guides authors",
            purpose=user_prompt,
            sections=sections,
            style_notes=[
                "Keep procedural, reference, and conceptual evidence separated until final authoring shape is clear.",
                "Do not flatten mixed screenshots into one generic narrative section.",
            ],
            source_notes=["Built from mixed screenshot evidence using mixed_content_mode."],
            reference_adoption=reference_adoption,
        )

    def _build_safe_fallback_route_plan(
        self,
        *,
        user_prompt: str,
        image_context: ChatImageContext,
        reference_summary: ChatReferenceDitaSummary,
        options: ChatDitaGenerationOptions,
        reference_adoption: ReferenceAdoptionDecision,
    ) -> ChatSemanticPlan:
        structured = image_context.structured
        dita_type = reference_adoption.target_root_type or "topic"
        title = (structured.title or reference_summary.title or "Recovered screenshot evidence").strip() or "Recovered screenshot evidence"

        visible_evidence = [
            text for text in self._visible_structure_text(structured, image_context)[:16] if text.strip()
        ]
        if not visible_evidence:
            visible_evidence = [item.strip() for item in image_context.visible_text[:16] if str(item).strip()]
        sections: list[ChatSemanticPlanSection] = []
        if visible_evidence:
            sections.append(ChatSemanticPlanSection(name="visible evidence", purpose="", details=visible_evidence))
        if structured.field_value_pairs:
            sections.append(
                ChatSemanticPlanSection(
                    name="field details",
                    purpose="",
                    details=[
                        f"{pair.field}: {pair.value}".strip(": ")
                        for pair in structured.field_value_pairs[:16]
                        if pair.field.strip() or pair.value.strip()
                    ],
                )
            )
        if structured.unresolved_blocks:
            sections.append(
                ChatSemanticPlanSection(
                    name="uncertain content",
                    purpose="",
                    details=[
                        f"{block.raw_text} ({block.reason})".strip()
                        for block in structured.unresolved_blocks[:8]
                        if block.raw_text.strip()
                    ],
                )
            )
        if not sections:
            sections = self._fallback_sections(dita_type, image_context)

        return ChatSemanticPlan(
            title=title,
            dita_type=dita_type,  # type: ignore[arg-type]
            shortdesc="Conservative summary built from visible screenshot evidence.",
            audience="AEM Guides authors",
            purpose=user_prompt,
            sections=sections,
            style_notes=[
                "Preserve ambiguity and unresolved evidence instead of inferring missing structure.",
                "Prefer conservative structure until the screenshot evidence is stronger.",
            ],
            source_notes=["Built from safe_fallback_mode to avoid over-generating from weak or mixed evidence."],
            reference_adoption=reference_adoption,
        )

    def _visible_structure_elements(self, structured) -> list[str]:
        sc = structured
        lines: list[str] = []
        seen: set[str] = set()
        for label in list(sc.ui_labels) + list(sc.menu_names) + list(sc.button_names):
            value = " ".join(str(label or "").split()).strip()
            if not value:
                continue
            lower = value.casefold()
            if lower in seen:
                continue
            seen.add(lower)
            if value.startswith("<") and value.endswith(">"):
                lines.append(f"Visible DITA element: {value}")
            elif any(token in lower for token in ("topic", "taskbody", "shortdesc", "prolog", "map", "topicref", "conref", "keyref")):
                lines.append(f"Visible structure label: {value}")
        for node in sc.semantic_hierarchy[:10]:
            if node.title.strip():
                item = f"Hierarchy node: {node.title.strip()}"
                if item.casefold() not in seen:
                    seen.add(item.casefold())
                    lines.append(item)
        return lines

    def _visible_structure_text(self, structured, image_context: ChatImageContext) -> list[str]:
        lines: list[str] = []
        seen: set[str] = set()
        for paragraph in structured.paragraphs[:12]:
            text = " ".join(paragraph.text.split()).strip()
            if text and text.casefold() not in seen:
                seen.add(text.casefold())
                lines.append(text)
        if not lines:
            for item in image_context.visible_text[:12]:
                text = " ".join(str(item or "").split()).strip()
                if text and text.casefold() not in seen:
                    seen.add(text.casefold())
                    lines.append(text)
        return lines

    def _summarize_table_for_plan(self, rows: list[list[str]], headers: list[str], caption: str) -> str:
        header_text = " | ".join(item.strip() for item in headers[:8] if item.strip())
        body_text = "; ".join(" / ".join(cell.strip() for cell in row[:8] if cell.strip()) for row in rows[:4] if any(cell.strip() for cell in row))
        summary = " ".join(part for part in [caption.strip(), header_text, body_text] if part).strip()
        return summary[:500]

    async def _render_dita_xml_with_mode(
        self,
        *,
        semantic_plan: ChatSemanticPlan,
        image_context: ChatImageContext,
        reference_summary: ChatReferenceDitaSummary,
        options: ChatDitaGenerationOptions,
        effective_strictness: str,
    ) -> tuple[str, str]:
        """Return ``(xml, mode)`` where mode is ``programmatic`` or ``llm``."""
        profile = reference_summary.style_profile
        ui_hints = _dita_serializer.collect_ui_label_hints(image_context)

        if effective_strictness in ("high", "medium"):
            draft = build_topic_draft(plan=semantic_plan, image_context=image_context)
            xml = _dita_serializer.serialize_structured_draft(
                draft,
                profile=profile,
                options=options,
                ui_label_hints=ui_hints,
            )
            return xml, "programmatic"

        ap = getattr(options, "authoring_pattern", "default")
        xref_allowlist_active = (
            ap == "cisco_task"
            and bool(getattr(options, "xref_placeholders", False))
            and profile
            and bool(getattr(profile, "reference_xref_basenames", None))
        )
        ref_policy = (
            "You may use empty <xref href=\"basename.xml\"/> only when basename appears in "
            "reference_summary.style_profile.reference_xref_basenames (no paths, no #fragments, no conref).\n"
            if xref_allowlist_active
            else "Do not invent xref hrefs or conrefs; omit xref or use placeholder text in ph.\n"
        )
        system_prompt = (
            "You write production-ready DITA 1.3 XML.\n"
            "Return XML only.\n"
            "Use conservative, validation-safe structures.\n"
            f"{ref_policy}"
            "Use the provided semantic plan exactly; do not output markdown or explanations."
        )
        if ap == "cisco_task":
            system_prompt += "\n\n" + cisco_semantic_plan_instructions(
                profile,
                xref_placeholders=bool(getattr(options, "xref_placeholders", False)),
            )
        elif ap == "cisco_reference":
            system_prompt += "\n\n" + cisco_reference_semantic_plan_instructions()
        user_prompt = json.dumps(
            {
                "header": build_dita_header(semantic_plan.dita_type),
                "semantic_plan": semantic_plan.model_dump(mode="json"),
                "image_context": image_context.model_dump(mode="json"),
                "reference_summary": reference_summary.model_dump(mode="json"),
                "reference_style_profile": profile.model_dump(mode="json") if profile else {},
                "generation_options": options.model_dump(mode="json"),
                "requirements": {
                    "valid_dita_1_3": True,
                    "single_topic_only": True,
                    "no_broken_refs": True,
                    "xml_only": True,
                },
            },
            ensure_ascii=True,
            indent=2,
        )
        if not is_llm_available():
            draft = build_topic_draft(plan=semantic_plan, image_context=image_context)
            xml = _dita_serializer.serialize_structured_draft(
                draft, profile=profile, options=options, ui_label_hints=ui_hints
            )
            return xml, "programmatic"

        try:
            xml = await generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=2600,
                step_name="chat_dita_authoring_render",
            )
            normalized, _ = normalize_dita_document(xml, semantic_plan.dita_type)
            return normalized, "llm"
        except Exception as exc:
            logger.warning_structured(
                "LLM DITA rendering failed; using deterministic serializer",
                extra_fields={"error": str(exc), "dita_type": semantic_plan.dita_type},
                exc_info=True,
            )
            draft = build_topic_draft(plan=semantic_plan, image_context=image_context)
            xml = _dita_serializer.serialize_structured_draft(
                draft, profile=profile, options=options, ui_label_hints=ui_hints
            )
            return xml, "programmatic"

    async def _validate_candidate(
        self,
        *,
        xml: str,
        semantic_plan: ChatSemanticPlan,
        tenant_id: str,
    ) -> tuple[str, ChatDitaValidationResult, dict[str, Any]]:
        return await _dita_validation.validate_candidate(
            xml=xml,
            semantic_plan=semantic_plan,
            tenant_id=tenant_id,
        )

    async def _repair_once_if_needed(
        self,
        *,
        xml: str,
        semantic_plan: ChatSemanticPlan,
        tenant_id: str,
    ) -> tuple[str, ChatDitaValidationResult, dict[str, Any]]:
        return await _dita_validation.repair_once(
            xml=xml,
            semantic_plan=semantic_plan,
            tenant_id=tenant_id,
        )

    def _save_to_aem(self, *, xml: str, file_name: str, save_path: str) -> str | None:
        if not (_AEM_BASE_URL and _AEM_USERNAME and _AEM_PASSWORD):
            logger.info_structured(
                "Skipping AEM save because chat authoring AEM credentials are not configured",
                extra_fields={"save_path": save_path},
            )
            return None
        upload_service = get_upload_service()
        with tempfile.TemporaryDirectory(prefix="chat-aem-upload-") as tmpdir:
            Path(tmpdir, file_name).write_text(xml, encoding="utf-8")
            result = upload_service.upload_dataset(
                source_path=tmpdir,
                aem_base_url=_AEM_BASE_URL,
                target_path=save_path,
                username=_AEM_USERNAME,
                password=_AEM_PASSWORD,
            )
        if not isinstance(result, dict) or not result.get("success"):
            logger.warning_structured(
                "AEM save for chat-authored DITA did not succeed",
                extra_fields={"save_path": save_path, "result": result},
            )
            return None
        return save_path.rstrip("/") + "/" + file_name

    def _fallback_plan(
        self,
        *,
        user_prompt: str,
        dita_type: str,
        image_context: ChatImageContext,
        reference_summary: ChatReferenceDitaSummary,
        reference_adoption: ReferenceAdoptionDecision,
    ) -> ChatSemanticPlan:
        return ChatSemanticPlan(
            title=(reference_summary.title or image_context.summary or "Generated topic").strip() or "Generated topic",
            dita_type=dita_type,  # type: ignore[arg-type]
            shortdesc="Use this topic to document the workflow shown in the attached screenshot.",
            audience="AEM Guides authors",
            purpose=user_prompt,
            sections=self._fallback_sections(dita_type, image_context),
            style_notes=reference_summary.style_notes or ["Use conservative, validation-safe DITA 1.3 structure."],
            source_notes=["Built from the attached screenshot and prompt without LLM plan generation."],
            reference_adoption=reference_adoption,
        )

    async def _generate_map_hierarchy_bundle(
        self,
        *,
        session_id: str,
        user_id: str,
        tenant_id: str,
        collected: _CollectedAttachments,
        effective_user_prompt: str,
        authoring_trace_id: str,
        opts: ChatDitaGenerationOptions,
        run_timer: AuthoringRunTimer,
    ) -> ChatDitaAuthoringResult:
        from app.services.map_hierarchy_bundle import build_map_bundle_files, parse_map_outline_payload
        from app.services.screenshot_understanding_service import extract_map_hierarchy_outline_from_image

        img = collected.image
        assert img is not None and collected.image_bytes is not None

        raw, vision_model = await extract_map_hierarchy_outline_from_image(
            image_bytes=collected.image_bytes,
            mime_type=img.mime_type or "image/png",
            user_prompt=effective_user_prompt,
        )
        outline, map_title, vconf, warns = parse_map_outline_payload(raw)
        assumption_objs: list[GenerationAssumption] = [
            GenerationAssumption(text=w, source="vision", confidence=vconf) for w in warns[:16]
        ]

        fail_debug = TopicGenerationDebug(
            authoring_trace_id=authoring_trace_id,
            pipeline_version="map_hierarchy_v1",
            pipeline_stages=[
                {"stage": "map_hierarchy_vision", "ok": bool(raw), "detail": {"model": vision_model}},
            ],
            extensions={"screenshot_deliverable": "map_hierarchy"},
        )

        if vision_model == "fallback":
            msg = (
                "Map hierarchy generation needs a configured vision provider (OpenAI or Anthropic API key). "
                "Set OPENAI_API_KEY or ANTHROPIC_API_KEY and LLM_PROVIDER."
            )
            return ChatDitaAuthoringResult(
                status="error",
                title=map_title,
                dita_type="map",
                xml_preview="",
                validation=TopicGenerationValidation(valid=False, issues=[]),
                message=msg,
                assumptions=assumption_objs,
                screenshot_confidence=0.0,
                debug=fail_debug,
            )

        if outline is None:
            msg = (
                "Could not extract a DITA hierarchy from the image. "
                "Use a clear diagram (boxes linked as parent/child) with topic types visible, "
                "or describe the tree in the prompt and try again."
            )
            return ChatDitaAuthoringResult(
                status="invalid",
                title=map_title,
                dita_type="map",
                xml_preview="",
                validation=TopicGenerationValidation(
                    valid=False,
                    issues=[],
                ),
                message=msg,
                assumptions=assumption_objs,
                screenshot_confidence=vconf,
                debug=fail_debug,
            )

        map_basename = (opts.file_name or "").strip()
        if not map_basename.lower().endswith(".ditamap"):
            map_basename = _default_map_file_name(map_title)

        files, gen_warns = build_map_bundle_files(outline, map_title=map_title, map_basename=map_basename)
        for gw in gen_warns:
            assumption_objs.append(GenerationAssumption(text=gw, source="pipeline"))

        if not files:
            return ChatDitaAuthoringResult(
                status="invalid",
                title=map_title,
                dita_type="map",
                xml_preview="",
                validation=TopicGenerationValidation(valid=False, issues=[]),
                message="Map bundle serialization produced no files. Check the outline and try again.",
                assumptions=assumption_objs[:20],
                screenshot_confidence=vconf,
                debug=fail_debug,
            )

        bundle_rows: list[ChatBundleArtifact] = []
        map_xml = ""
        primary_ref: ChatAttachmentRef | None = None
        for rel_path, xml_text in files:
            is_map = rel_path.lower().endswith(".ditamap")
            fname = rel_path.split("/")[-1]
            ref = save_text_asset(
                session_id=session_id,
                user_id=user_id,
                kind="generated_dita",
                filename=fname,
                content=xml_text,
            )
            if is_map:
                role = "map"
                dt = "map"
                map_xml = xml_text
            else:
                role = "topic"
                if rel_path.startswith("tasks/"):
                    dt = "task"
                elif rel_path.startswith("concepts/"):
                    dt = "concept"
                elif rel_path.startswith("references/"):
                    dt = "reference"
                else:
                    dt = "topic"
            bundle_rows.append(
                ChatBundleArtifact(
                    role=role,
                    dita_type=dt,
                    filename=ref.filename,
                    href=rel_path,
                    asset_id=ref.asset_id,
                    url=ref.url,
                    xml_preview=_shorten(xml_text, limit=900),
                )
            )
            if primary_ref is None:
                primary_ref = ref

        topic_validation = TopicGenerationValidation(valid=True, issues=[])
        actions = [
            ChatAction(
                key="open_in_editor",
                label="Open map (XML)",
                url=primary_ref.url if primary_ref else None,
                description="Primary artifact is the DITA map.",
            )
        ]
        for art in bundle_rows[1:8]:
            actions.append(
                ChatAction(
                    key=f"open_{art.asset_id or art.filename}",
                    label=f"Open {art.filename}",
                    url=art.url,
                    description=art.href,
                )
            )

        file_lines = "\n".join(f"- `{b.href}` → {b.dita_type}" for b in bundle_rows[:24])
        message = (
            "## DITA map bundle\n"
            f"- Status: valid\n"
            f"- Map title: {map_title}\n"
            f"- Files: {len(bundle_rows)}\n"
            f"- Vision model: {vision_model}\n\n"
            f"{file_lines}\n\n"
            "Relationships are in nested `topicref` elements in the map. Topic files are stubs—replace with product content."
        )

        log_authoring_trace_completed(
            authoring_trace_id=authoring_trace_id,
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            pipeline_run_id=None,
            pipeline_version="map_hierarchy_v1",
            status="valid",
            dita_type="map",
            validation_valid=True,
            validation_error_count=0,
            validation_warning_count=0,
            had_reference_dita=bool(collected.reference_dita),
            parse_reference_ok=True,
            vision_provider=vision_model,
            serialization_mode="map_hierarchy_bundle",
            duration_ms=run_timer.elapsed_ms(),
            generated_asset_id=primary_ref.asset_id if primary_ref else None,
        )

        dbg = TopicGenerationDebug(
            authoring_trace_id=authoring_trace_id,
            pipeline_version="map_hierarchy_v1",
            pipeline_stages=[
                {"stage": "map_hierarchy_vision", "ok": True, "detail": {"model": vision_model, "confidence": vconf}},
                {"stage": "map_hierarchy_serialize", "ok": True, "detail": {"file_count": len(bundle_rows)}},
            ],
            serialization_mode="map_hierarchy_bundle",
            extensions={"screenshot_deliverable": "map_hierarchy", "vision_model": vision_model},
        )

        return ChatDitaAuthoringResult(
            status="valid",
            title=map_title,
            dita_type="map",
            xml_preview=_shorten(map_xml, limit=3200),
            validation=topic_validation,
            saved_asset_path=None,
            artifact_url=primary_ref.url if primary_ref else None,
            actions=actions,
            message=message,
            semantic_plan=None,
            image_context=None,
            reference_summaries=[],
            assumptions=assumption_objs[:20],
            screenshot_confidence=vconf,
            link_recommendations=[],
            debug=dbg,
            bundle_artifacts=bundle_rows,
        )

    def _fallback_sections(self, dita_type: str, image_context: ChatImageContext) -> list[ChatSemanticPlanSection]:
        vis = image_context.visible_text[:8]
        if not vis and image_context.structured.numbered_steps:
            vis = image_context.structured.numbered_steps[:8]
        if dita_type == "task":
            return [
                ChatSemanticPlanSection(
                    name="context",
                    purpose="",
                    details=[image_context.summary or "Visible task context recovered from the screenshot."],
                ),
                ChatSemanticPlanSection(name="steps", purpose="", details=vis or ["Visible ordered actions could only be partially recovered."]),
                ChatSemanticPlanSection(
                    name="result",
                    purpose="",
                    details=["Visible result or completion state was not confidently recovered from the screenshot."],
                ),
            ]
        if dita_type == "concept":
            return [
                ChatSemanticPlanSection(
                    name="overview",
                    purpose="",
                    details=[image_context.summary or "Visible feature summary recovered from the screenshot."],
                ),
                ChatSemanticPlanSection(name="details", purpose="", details=vis),
            ]
        if dita_type == "reference":
            return [
                ChatSemanticPlanSection(
                    name="overview",
                    purpose="",
                    details=[image_context.summary or "Visible UI or configuration context recovered from the screenshot."],
                ),
                ChatSemanticPlanSection(name="details", purpose="", details=vis),
            ]
        return [
            ChatSemanticPlanSection(name="body", purpose="", details=vis or [image_context.summary or "Visible content recovered from the screenshot."]),
        ]

    def _build_result_message(
        self,
        *,
        status: str,
        title: str,
        dita_type: str,
        saved_asset_path: str | None,
        validation: ChatDitaValidationResult,
    ) -> str:
        lines = [
            "## DITA topic generation",
            f"- Status: {status.replace('_', ' ')}",
            f"- Title: {title}",
            f"- DITA type: {dita_type}",
        ]
        if saved_asset_path:
            lines.append(f"- Saved asset path: {saved_asset_path}")
        if validation.structural_issues:
            lines.append(f"- Structural notes: {len(validation.structural_issues)} issue(s) — see validation panel.")
        return "\n".join(lines)

    def _build_screenshot_review_required_message(
        self,
        *,
        title: str,
        dita_type: str,
        reasons: list[str],
        image_context: ChatImageContext,
    ) -> str:
        lines = [
            "## Screenshot review required",
            "- Status: invalid",
            f"- Title: {title}",
            f"- DITA type: {dita_type}",
        ]
        for reason in reasons[:4]:
            lines.append(f"- Reason: {reason}")
        if image_context.vision_provider == "fallback":
            lines.append(
                "- Next step: configure an OpenAI or Anthropic vision-capable provider; text-only chat generation cannot reliably interpret the screenshot."
            )
        else:
            lines.append(
                "- Next step: retry with a clearer, less cropped screenshot or add a stronger reference topic before regenerating."
            )
        return "\n".join(lines)

    def _generation_blockers(
        self,
        *,
        image_context: ChatImageContext,
        semantic_plan: ChatSemanticPlan,
    ) -> list[str]:
        structured = image_context.structured
        route = self._intent_route_from_image_context(image_context)
        warnings_blob = " ".join(
            [*(image_context.warnings or []), *(structured.uncertainty_warnings or [])]
        ).lower()
        reasons: list[str] = []
        actionable = self._has_actionable_screenshot_evidence(structured)

        if image_context.vision_provider == "fallback" or "vision provider unavailable" in warnings_blob:
            reasons.append(
                "Screenshot vision analysis is unavailable, so the image could not be interpreted from visual evidence."
            )

        if route == "safe_fallback_mode" and (
            structured.confidence < _MIN_SCREENSHOT_CONFIDENCE_FOR_SAFE_FALLBACK or not actionable
        ):
            reasons.append(
                "The screenshot could not be classified with enough confidence to generate reliable DITA content."
            )

        if structured.confidence < _MIN_SCREENSHOT_CONFIDENCE_FOR_LOW_SIGNAL and not actionable:
            reasons.append(
                "The extracted screenshot signal is too weak; unresolved or uncertain regions outweigh reliable structure."
            )

        if self._plan_looks_placeholder_like(semantic_plan) and (
            image_context.vision_provider == "fallback"
            or route == "safe_fallback_mode"
            or structured.confidence < _MIN_SCREENSHOT_CONFIDENCE_FOR_SAFE_FALLBACK
        ):
            reasons.append(
                "The generated plan is mostly placeholder scaffolding, which indicates the screenshot evidence was too weak."
            )

        return list(dict.fromkeys(reason for reason in reasons if reason.strip()))

    def _has_actionable_screenshot_evidence(self, structured) -> bool:
        settings = structured.settings_reference_model
        has_settings = bool(
            settings
            and (settings.sections or settings.tabs or settings.parameter_tables or settings.helper_text)
        )
        has_diagram = bool(
            structured.diagram_interpretation
            and (
                structured.diagram_interpretation.key_entities
                or structured.diagram_interpretation.relationships
            )
        )
        return any(
            (
                bool((structured.title or "").strip()),
                bool(structured.paragraphs),
                bool(structured.sections),
                bool(structured.headings),
                bool(structured.numbered_steps),
                bool(structured.procedural_model and structured.procedural_model.steps),
                bool(structured.field_value_pairs),
                has_settings,
                has_diagram,
                bool(structured.semantic_hierarchy),
                bool(structured.ui_labels),
                bool(structured.tables),
            )
        )

    def _plan_looks_placeholder_like(self, plan: ChatSemanticPlan) -> bool:
        if not plan.sections:
            return True
        generic_names = 0
        placeholder_details = 0
        detail_count = 0
        for section in plan.sections:
            name = (section.name or "").strip().lower()
            if name in _PLACEHOLDER_SECTION_NAMES:
                generic_names += 1
            for detail in section.details:
                text = " ".join(str(detail or "").split()).strip()
                if not text:
                    continue
                detail_count += 1
                if any(pattern.search(text) for pattern in _PLACEHOLDER_DETAIL_PATTERNS):
                    placeholder_details += 1
        if detail_count == 0:
            return True
        return generic_names >= 2 and placeholder_details >= 2

    def _dita_type_hint_from_prompt(self, prompt: str) -> str | None:
        text = (prompt or "").lower()
        for candidate in ("task", "concept", "reference", "topic"):
            if re.search(rf"\b{candidate}\b", text):
                return candidate
        return None

    def _clean_dita_type(self, value: str) -> str | None:
        candidate = (value or "").strip().lower()
        if candidate in {"task", "concept", "reference", "topic", "map"}:
            return candidate
        return None


_authoring_service: ChatDitaAuthoringService | None = None


def get_chat_dita_authoring_service() -> ChatDitaAuthoringService:
    global _authoring_service
    if _authoring_service is None:
        _authoring_service = ChatDitaAuthoringService()
    return _authoring_service
