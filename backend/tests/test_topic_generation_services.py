"""Unit tests for modular topic generation services and orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.schemas_chat_authoring import (
    ChatAttachmentRef,
    ChatDitaGenerationOptions,
    ChatDitaValidationResult,
    ChatImageContext,
    ChatReferenceDitaSummary,
    ChatSemanticPlan,
    ChatSemanticPlanSection,
    ReferenceStyleProfile,
    ScreenshotContentModel,
    ScreenshotIntentRouteDecision,
    ScreenshotProceduralContentItem,
    ScreenshotProceduralModel,
    ScreenshotProceduralStep,
    ScreenshotProceduralSubstep,
)
from app.core.schemas_topic_generation import ReferenceAdoptionDecision, ReferenceSerializerPolicy
from app.services.dita_authoring_pipeline import SerializationResult, ValidationStageResult
from app.services.dita_topic_draft import build_topic_draft, merge_structured_into_plan
from app.services.dita_topic_serializer import serialize_topic_draft
from app.services.topic_generation.dita_serializer_service import DitaSerializerService
from app.services.topic_generation.dita_style_profile_builder import DitaStyleProfileBuilder
from app.services.topic_generation.dita_validation_service import DitaValidationService
from app.services.topic_generation.reference_dita_analyzer import ReferenceDitaAnalyzer
from app.services.topic_generation.topic_generation_orchestrator import TopicGenerationOrchestrator
from app.services.topic_generation.topic_type_inference_service import TopicTypeInferenceService


def test_dita_style_profile_builder_never_puts_topic_id_in_profile():
    raw = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "technicalContent/dtd/task.dtd">
<task id="secret-ref-id" xml:lang="en-US">
<title>T</title>
<shortdesc>S</shortdesc>
<taskbody><steps><step><cmd>Go</cmd></step></steps></taskbody>
</task>"""
    builder = DitaStyleProfileBuilder()
    profile, warnings = builder.build(raw)
    assert "secret-ref-id" not in (profile.root_attributes_sample or {}).get("id", "")
    assert "id" not in profile.root_attributes_sample
    assert not warnings or all("parse" not in w.lower() for w in warnings if "error" in w.lower())


@pytest.mark.anyio
async def test_reference_dita_analyzer_no_attachment():
    ana = ReferenceDitaAnalyzer()
    out = await ana.summarize_attachment(reference_attachment=None, reference_text="")
    assert out.style_profile is None
    assert "No reference" in (out.structure_summary or "")


def test_topic_type_inference_respects_explicit_option():
    svc = TopicTypeInferenceService()
    opts = ChatDitaGenerationOptions(dita_type="concept")
    ic = ChatImageContext(structured=ScreenshotContentModel(numbered_steps=["a", "b", "c"]))
    t = svc.infer(options=opts, user_prompt="anything", image_context=ic, profile=None)
    assert t == "concept"


def test_topic_type_inference_prefers_intent_route_over_reference_profile():
    svc = TopicTypeInferenceService()
    ic = ChatImageContext(
        structured=ScreenshotContentModel(
            screenshot_intent_route_decision=ScreenshotIntentRouteDecision(
                chosenRoute="structure_reconstruction_mode",
                routeConfidence=0.84,
                reasons=["editor screenshot"],
                downstreamConstraints=["Preserve visible structure"],
            ),
            numbered_steps=["1. misleading step"],
            confidence=0.82,
        )
    )
    profile = ReferenceStyleProfile(root_local_name="task")
    t = svc.infer(options=ChatDitaGenerationOptions(), user_prompt="generate from screenshot", image_context=ic, profile=profile)
    assert t == "concept"


def test_dita_serializer_collects_ui_hints():
    ic = ChatImageContext(
        structured=ScreenshotContentModel(ui_labels=[" Save "], button_names=["OK"]),
        ui_elements=[{"label": "Cancel"}],
    )
    hints = DitaSerializerService.collect_ui_label_hints(ic)
    assert "Save" in hints
    assert "OK" in hints
    assert "Cancel" in hints


@pytest.mark.anyio
async def test_topic_generation_orchestrator_runs_stages_with_mocks(monkeypatch):
    image = ChatAttachmentRef(
        asset_id="img-1",
        kind="image",
        filename="s.png",
        mime_type="image/png",
        size_bytes=10,
        url="/a/img-1",
    )

    class _FakeShot:
        async def understand(self, **kwargs):
            return ChatImageContext(
                summary="UI",
                structured=ScreenshotContentModel(title="From screen", confidence=0.9),
            )

    class _FakeRef:
        async def summarize_attachment(self, **kwargs):
            return ChatReferenceDitaSummary(
                root_type="task",
                style_profile=ReferenceStyleProfile(root_local_name="task", parse_warnings=[]),
            )

    executor = MagicMock()
    executor.build_semantic_plan = AsyncMock(
        return_value=ChatSemanticPlan(
            title="T",
            dita_type="task",
            shortdesc="S",
            sections=[ChatSemanticPlanSection(name="steps", purpose="", details=["One"])],
        )
    )
    executor.render_dita_xml = AsyncMock(
        return_value=SerializationResult(xml="<task id='gen'><title>T</title></task>", mode="programmatic")
    )
    executor.validate_candidate = AsyncMock(
        return_value=ValidationStageResult(
            normalized_xml="<task id='gen'><title>T</title></task>",
            validation_result=ChatDitaValidationResult(valid=True),
            review_snapshot={},
        )
    )

    orch = TopicGenerationOrchestrator(
        screenshot_service=_FakeShot(),
        reference_analyzer=_FakeRef(),
    )

    s1, s2, s3, s4, s5, s6, s7, val, s9, trace = await orch.run_screenshot_guided_pipeline(
        executor=executor,
        user_prompt="Generate a task from screenshot",
        tenant_id="t1",
        image=image,
        image_bytes=b"fake",
        reference_attachment=None,
        reference_text="",
        base_options=ChatDitaGenerationOptions(),
        strictness="high",
        reference_guided_enabled=True,
    )

    assert s1.image_context.structured.confidence == 0.9
    assert s6.topic_draft.dita_type == "task"
    assert trace.run_id
    assert any(s.stage == "resolve_authoring_pattern" for s in trace.stages)
    assert any(s.stage == "analyze_screenshot" for s in trace.stages)
    assert any(s.detail.get("service") == "ScreenshotUnderstandingService" for s in trace.stages)
    executor.build_semantic_plan.assert_awaited_once()
    executor.render_dita_xml.assert_awaited_once()
    executor.validate_candidate.assert_awaited_once()
    assert s9 is None


def test_merge_structured_into_plan_adds_field_details_section():
    plan = ChatSemanticPlan(
        title="Configure translation",
        dita_type="reference",
        shortdesc="Base shortdesc",
        sections=[],
    )
    structured = ScreenshotContentModel(
        title="Configure translation settings",
        field_value_pairs=[
            {"field": "Language", "value": "French"},
            {"field": "Provider", "value": "Adobe Translation Integration"},
        ],
        acceptance_criteria=["Translation job created"],
    )
    merged = merge_structured_into_plan(plan, structured)
    names = [section.name.lower() for section in merged.sections]
    assert "field details" in names
    assert "acceptance criteria" in names


def test_merge_structured_into_plan_uses_reference_policy_names_and_order():
    plan = ChatSemanticPlan(
        title="Configure translation",
        dita_type="reference",
        shortdesc="Base shortdesc",
        sections=[],
        reference_adoption=ReferenceAdoptionDecision(
            mode="compatible_adoption",
            target_root_type="reference",
            serializer_policy=ReferenceSerializerPolicy(
                target_root_type="reference",
                preferred_top_level_order=["dialog layout", "field details", "parameter tables", "acceptance criteria"],
                preferred_section_name_map={
                    "dialog layout": "Visible tabs",
                    "field details": "Settings fields",
                    "parameter tables": "Configuration tables",
                    "acceptance criteria": "Validation checks",
                },
            ),
        ),
    )
    structured = ScreenshotContentModel(
        title="Configure translation settings",
        field_value_pairs=[
            {"field": "Language", "value": "French"},
        ],
        tables=[
            {"caption": "Parameters", "headers": ["Field", "Value"], "rows": [["Language", "French"]]},
        ],
        acceptance_criteria=["Translation job created"],
        settings_reference_model={
            "tabs": ["General", "Advanced"],
            "sections": [],
            "confidence": 0.8,
        },
    )
    merged = merge_structured_into_plan(plan, structured)
    names = [section.name for section in merged.sections[:4]]
    assert names == ["Visible tabs", "Settings fields", "Configuration tables", "Validation checks"]


def test_build_topic_draft_creates_table_from_field_value_pairs():
    plan = ChatSemanticPlan(
        title="Translation configuration",
        dita_type="reference",
        shortdesc="How to configure translation.",
        sections=[ChatSemanticPlanSection(name="field details", purpose="Recovered settings", details=["Language: French"])],
    )
    image_context = ChatImageContext(
        structured=ScreenshotContentModel(
            field_value_pairs=[
                {"field": "Language", "value": "French"},
                {"field": "Provider", "value": "Adobe Translation Integration"},
            ]
        )
    )
    draft = build_topic_draft(plan=plan, image_context=image_context)
    assert draft.tables
    assert draft.tables[0].rows[0] == ["Field", "Value"]
    assert ["Language", "French"] in draft.tables[0].rows


def test_build_topic_draft_preserves_procedural_model_for_task_generation():
    plan = ChatSemanticPlan(
        title="Create an output preset",
        dita_type="task",
        shortdesc="Create a new output preset.",
        sections=[],
    )
    image_context = ChatImageContext(
        structured=ScreenshotContentModel(
            procedural_model=ScreenshotProceduralModel(
                title="Create an output preset",
                prerequisites=[
                    ScreenshotProceduralContentItem(text="Make sure you have map author permissions.", kind="prerequisite", confidence=0.82)
                ],
                context=[
                    ScreenshotProceduralContentItem(text="Use this procedure to create a PDF preset.", kind="context", confidence=0.8)
                ],
                steps=[
                    ScreenshotProceduralStep(
                        marker="1.",
                        command="Open Output Presets",
                        substeps=[ScreenshotProceduralSubstep(marker="1.", command="Select PDF", confidence=0.78)],
                        confidence=0.88,
                    ),
                    ScreenshotProceduralStep(
                        marker="2.",
                        command="Click Save",
                        info_lines=["The preset is added to the list."],
                        ui_controls=["Save"],
                        confidence=0.9,
                    ),
                ],
                notes=[],
                result=[
                    ScreenshotProceduralContentItem(text="The preset appears in the output preset panel.", kind="result", confidence=0.79)
                ],
                examples=[
                    ScreenshotProceduralContentItem(text="dita -i map.ditamap -f pdf", kind="code", confidence=0.76)
                ],
                confidence=0.84,
            )
        )
    )
    draft = build_topic_draft(plan=plan, image_context=image_context)
    assert len(draft.procedural_steps) == 2
    xml = serialize_topic_draft(
        draft,
        profile=None,
        options=ChatDitaGenerationOptions(dita_type="task"),
        ui_label_hints={"Save", "Output Presets", "PDF"},
    )
    assert "<substeps>" in xml
    assert "<cmd>Select PDF</cmd>" in xml
    assert "The preset is added to the list." in xml
    assert "<result>" in xml


def test_serializer_does_not_emit_generic_section_purpose_filler():
    plan = ChatSemanticPlan(
        title="About output presets",
        dita_type="concept",
        shortdesc="Visible structure and text recovered from the screenshot.",
        sections=[
            ChatSemanticPlanSection(
                name="overview",
                purpose="Explain what the screen or feature is for.",
                details=["Output presets let authors publish content in multiple formats."],
            )
        ],
    )
    draft = build_topic_draft(plan=plan, image_context=ChatImageContext(structured=ScreenshotContentModel()))
    xml = serialize_topic_draft(
        draft,
        profile=None,
        options=ChatDitaGenerationOptions(dita_type="concept"),
        ui_label_hints=set(),
    )
    assert "Output presets let authors publish content in multiple formats." in xml
    assert "Explain what the screen or feature is for." not in xml


@pytest.mark.anyio
async def test_validation_flags_missing_reference_properties_layout(monkeypatch):
    svc = DitaValidationService()
    monkeypatch.setattr(
        "app.services.topic_generation.dita_validation_service.build_review_snapshot",
        AsyncMock(return_value={"validation": [], "aem_guides_validation_errors": [], "quality_score": 81}),
    )
    monkeypatch.setattr(
        svc,
        "_folder_validate",
        lambda xml, *, file_name: {"errors": [], "warnings": []},
    )
    semantic_plan = ChatSemanticPlan(
        title="Translation settings",
        dita_type="reference",
        shortdesc="Reference details.",
        sections=[ChatSemanticPlanSection(name="Properties", purpose="", details=["Language: French"])],
        reference_adoption=ReferenceAdoptionDecision(
            mode="compatible_adoption",
            target_root_type="reference",
            serializer_policy=ReferenceSerializerPolicy(
                target_root_type="reference",
                prefer_properties_layout=True,
            ),
        ),
    )
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "technicalContent/dtd/reference.dtd">
<reference id="translation-settings"><title>Translation settings</title><shortdesc>Reference details.</shortdesc><refbody><section><title>Properties</title><p>Language: French</p></section></refbody></reference>"""
    _, result, _ = await svc.validate_candidate(xml=xml, semantic_plan=semantic_plan, tenant_id="kone")
    assert any("properties or parameter tables" in issue for issue in result.structural_issues)
