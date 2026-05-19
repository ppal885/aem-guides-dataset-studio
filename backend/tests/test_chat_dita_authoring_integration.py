"""Integration-style tests for chat DITA authoring (mocked IO and review)."""

from unittest.mock import AsyncMock

import pytest

from app.core.schemas_chat_authoring import (
    ChatAttachmentRef,
    ChatAuthoringRequestPayload,
    ChatDitaGenerationOptions,
    ChatImageContext,
    ChatReferenceDitaSummary,
    ChatSemanticPlan,
    ChatSemanticPlanSection,
    ChatDitaValidationResult,
    ScreenshotContentModel,
    ScreenshotFieldValueItem,
    ScreenshotIntentRouteDecision,
    ScreenshotParagraphItem,
    ScreenshotProceduralContentItem,
    ScreenshotProceduralModel,
    ScreenshotProceduralStep,
    DiagramInterpretationModel,
    DiagramRelationshipItem,
    DiagramGroupItem,
    ReferenceStyleProfile,
    ScreenshotSettingsReferenceModel,
    ScreenshotTableItem,
    ScreenshotTypeClassification,
)
from app.services.chat_dita_authoring_service import ChatDitaAuthoringService, get_chat_dita_authoring_service
from app.services.dita_authoring_pipeline import (
    AuthoringPipelineTrace,
    MergedPlanResult,
    ReferenceAnalysisResult,
    ScreenshotAnalysisResult,
    SemanticPlanResult,
    SerializationResult,
    StructuredDraftResult,
    TopicTypeResult,
    ValidationStageResult,
)
from app.services.dita_topic_draft import build_topic_draft


@pytest.fixture
def service() -> ChatDitaAuthoringService:
    return get_chat_dita_authoring_service()


@pytest.mark.anyio
async def test_generate_topic_programmatic_path(monkeypatch, service: ChatDitaAuthoringService):
    from app.services import chat_dita_authoring_service as mod

    async def fake_vision(*, image, image_bytes, user_prompt):
        return ChatImageContext(
            summary="Configure the widget",
            structured=ScreenshotContentModel(
                numbered_steps=["Open panel", "Set value", "Save"],
                confidence=0.85,
                uncertainty_warnings=[],
            ),
        )

    monkeypatch.setattr(
        "app.services.topic_generation.screenshot_understanding_service.extract_screenshot_context",
        fake_vision,
    )

    def fake_read(_asset_id: str):
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, {}

    monkeypatch.setattr(mod, "read_asset_bytes", fake_read)

    monkeypatch.setattr(
        "app.services.topic_generation.dita_validation_service.build_review_snapshot",
        AsyncMock(return_value={"validation": [], "aem_guides_validation_errors": [], "quality_score": 85}),
    )

    monkeypatch.setattr(
        "app.services.topic_generation.dita_validation_service.validate_dita_folder",
        lambda _p: {"errors": [], "warnings": []},
    )
    monkeypatch.setattr(
        "app.services.topic_generation.dita_validation_service.DitaValidationService._folder_validate",
        lambda self, xml, *, file_name: {"errors": [], "warnings": []},
    )

    def fake_save(**kwargs):
        return ChatAttachmentRef(
            asset_id="gen-1",
            kind="generated_dita",
            filename=kwargs.get("filename") or "out.dita",
            mime_type="application/xml",
            size_bytes=100,
            url="/api/v1/chat/assets/gen-1",
            storage_path="/tmp/gen-1",
        )

    monkeypatch.setattr(mod, "save_text_asset", fake_save)

    monkeypatch.setattr(mod, "is_llm_available", lambda: False)

    img = ChatAttachmentRef(
        asset_id="img-1",
        kind="image",
        filename="s.png",
        mime_type="image/png",
        size_bytes=40,
        url="/api/v1/chat/assets/img-1",
    )
    payload = ChatAuthoringRequestPayload(
        content="generate a DITA task topic from this screenshot",
        attachments=[img],
        generation_options=ChatDitaGenerationOptions(
            style_strictness="high",
            strict_validation=True,
            output_mode="xml_validation",
        ),
    )

    result = await service.generate_topic_from_request(
        payload=payload,
        session_id="sess-1",
        user_id="user-1",
        tenant_id="kone",
    )

    assert result.status in ("valid", "saved", "repaired", "invalid")
    assert result.dita_type == "task"
    assert result.title
    assert "<task" in (result.xml_preview or "")
    assert result.screenshot_confidence is not None
    assert result.validation_result.structural_issues is not None
    assert result.debug.pipeline_run_id
    assert isinstance(result.debug.pipeline_stages, list)
    assert result.debug.serialization_mode == "programmatic"


@pytest.mark.anyio
async def test_reference_profile_attached(monkeypatch, service: ChatDitaAuthoringService):
    from app.services import chat_dita_authoring_service as mod

    async def fake_vision(*, image, image_bytes, user_prompt):
        return ChatImageContext(summary="UI", structured=ScreenshotContentModel())

    monkeypatch.setattr(
        "app.services.topic_generation.screenshot_understanding_service.extract_screenshot_context",
        fake_vision,
    )

    ref_xml = """<?xml version="1.0"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
<concept id="r1" xml:lang="fr-FR"><title>Ref</title><conbody><p>x</p></conbody></concept>"""

    def fake_read(aid: str):
        if aid == "img-1":
            return b"\x89PNG\r\n\x1a\n", {}
        if aid == "ref-1":
            return ref_xml.encode(), {}
        return b"", {}

    monkeypatch.setattr(mod, "read_asset_bytes", fake_read)

    monkeypatch.setattr(
        "app.services.topic_generation.dita_validation_service.build_review_snapshot",
        AsyncMock(return_value={"validation": [], "aem_guides_validation_errors": [], "quality_score": 80}),
    )
    monkeypatch.setattr(
        "app.services.topic_generation.dita_validation_service.validate_dita_folder",
        lambda _p: {"errors": [], "warnings": []},
    )
    monkeypatch.setattr(
        "app.services.topic_generation.dita_validation_service.DitaValidationService._folder_validate",
        lambda self, xml, *, file_name: {"errors": [], "warnings": []},
    )
    monkeypatch.setattr(
        mod,
        "save_text_asset",
        lambda **k: ChatAttachmentRef(
            asset_id="g",
            kind="generated_dita",
            filename="f.dita",
            mime_type="application/xml",
            size_bytes=1,
            url="/u",
        ),
    )
    monkeypatch.setattr(mod, "is_llm_available", lambda: False)

    payload = ChatAuthoringRequestPayload(
        content="create concept from screenshot using reference",
        attachments=[
            ChatAttachmentRef(
                asset_id="img-1",
                kind="image",
                filename="s.png",
                mime_type="image/png",
                size_bytes=10,
                url="/i",
            ),
            ChatAttachmentRef(
                asset_id="ref-1",
                kind="reference_dita",
                filename="ref.dita",
                mime_type="application/xml",
                size_bytes=len(ref_xml),
                url="/r",
            ),
        ],
        generation_options=ChatDitaGenerationOptions(style_strictness="high", dita_type="concept"),
    )
    result = await service.generate_topic_from_request(
        payload=payload, session_id="s", user_id="u", tenant_id="kone"
    )
    assert result.reference_summary
    assert result.reference_summary.style_profile is not None
    assert result.reference_summary.style_profile.root_local_name == "concept"


@pytest.mark.anyio
async def test_build_semantic_plan_uses_structure_reconstruction_route_without_generic_filler(service: ChatDitaAuthoringService):
    plan = await service._build_semantic_plan(
        user_prompt="Generate a topic from this editor screenshot",
        image_context=ChatImageContext(
            summary="Screen title: DITA topic structure.",
            visible_text=["<topic>", "<body>", "Overview", "Important editor note"],
            structured=ScreenshotContentModel(
                title="DITA topic structure",
                paragraphs=[ScreenshotParagraphItem(text="Important editor note", confidence=0.82)],
                ui_labels=["<topic>", "<body>", "Overview"],
                screenshot_intent_route_decision=ScreenshotIntentRouteDecision(
                    chosenRoute="structure_reconstruction_mode",
                    routeConfidence=0.88,
                    reasons=["editor chips"],
                    downstreamConstraints=["Preserve visible structure"],
                ),
                confidence=0.86,
            ),
        ),
        reference_summary=ChatReferenceDitaSummary(),
        options=ChatDitaGenerationOptions(),
    )
    assert plan.dita_type == "concept"
    assert any(section.name.lower() == "visible structure" for section in plan.sections)
    assert any("<topic>" in detail for section in plan.sections for detail in section.details)
    assert all(not section.purpose for section in plan.sections)


@pytest.mark.anyio
async def test_build_semantic_plan_uses_reference_extraction_route(service: ChatDitaAuthoringService):
    plan = await service._build_semantic_plan(
        user_prompt="Generate a reference topic from this settings screenshot",
        image_context=ChatImageContext(
            summary="Translation settings dialog.",
            structured=ScreenshotContentModel(
                title="Translation settings",
                field_value_pairs=[
                    ScreenshotFieldValueItem(field="Language", value="French", confidence=0.88),
                    ScreenshotFieldValueItem(field="Provider", value="Adobe Translation", confidence=0.84),
                ],
                screenshot_intent_route_decision=ScreenshotIntentRouteDecision(
                    chosenRoute="reference_extraction_mode",
                    routeConfidence=0.9,
                    reasons=["field/value density"],
                    downstreamConstraints=["Preserve field-value associations"],
                ),
                confidence=0.87,
            ),
        ),
        reference_summary=ChatReferenceDitaSummary(),
        options=ChatDitaGenerationOptions(),
    )
    assert plan.dita_type == "reference"
    assert any(section.name.lower() == "field details" for section in plan.sections)
    assert any("Language: French" in detail for section in plan.sections for detail in section.details)


@pytest.mark.anyio
async def test_build_semantic_plan_uses_procedural_route(service: ChatDitaAuthoringService):
    plan = await service._build_semantic_plan(
        user_prompt="Generate a task topic from this screenshot",
        image_context=ChatImageContext(
            summary="Create an output preset.",
            structured=ScreenshotContentModel(
                title="Create an output preset",
                procedural_model=ScreenshotProceduralModel(
                    title="Create an output preset",
                    context=[
                        ScreenshotProceduralContentItem(
                            text="Use this procedure to create a PDF preset.",
                            kind="context",
                            confidence=0.8,
                        )
                    ],
                    steps=[
                        ScreenshotProceduralStep(marker="1.", command="Open Output Presets", confidence=0.9),
                        ScreenshotProceduralStep(marker="2.", command="Click Save", confidence=0.88),
                    ],
                    confidence=0.86,
                ),
                screenshot_intent_route_decision=ScreenshotIntentRouteDecision(
                    chosenRoute="procedural_authoring_mode",
                    routeConfidence=0.91,
                    reasons=["numbered steps"],
                    downstreamConstraints=["Preserve step order"],
                ),
                confidence=0.88,
            ),
        ),
        reference_summary=ChatReferenceDitaSummary(),
        options=ChatDitaGenerationOptions(),
    )
    assert plan.dita_type == "task"
    steps = next(section for section in plan.sections if section.name.lower() == "steps")
    assert steps.details == ["Open Output Presets", "Click Save"]


@pytest.mark.anyio
async def test_build_semantic_plan_procedural_route_adopts_task_reference_sequence(service: ChatDitaAuthoringService):
    plan = await service._build_semantic_plan(
        user_prompt="Generate a task topic from this screenshot",
        image_context=ChatImageContext(
            summary="Create an output preset.",
            structured=ScreenshotContentModel(
                title="Create an output preset",
                procedural_model=ScreenshotProceduralModel(
                    title="Create an output preset",
                    prerequisites=[
                        ScreenshotProceduralContentItem(text="You must have author access.", kind="prerequisite", confidence=0.8)
                    ],
                    context=[
                        ScreenshotProceduralContentItem(text="Use this to configure PDF output.", kind="context", confidence=0.8)
                    ],
                    steps=[
                        ScreenshotProceduralStep(marker="1.", command="Open Output Presets", confidence=0.9),
                    ],
                    result=[
                        ScreenshotProceduralContentItem(text="The preset is available for publishing.", kind="result", confidence=0.82)
                    ],
                    examples=[
                        ScreenshotProceduralContentItem(text="dita -i map.ditamap -f pdf", kind="code", confidence=0.76)
                    ],
                    confidence=0.86,
                ),
                screenshot_intent_route_decision=ScreenshotIntentRouteDecision(
                    chosenRoute="procedural_authoring_mode",
                    routeConfidence=0.91,
                    reasons=["numbered steps"],
                    downstreamConstraints=["Preserve step order"],
                ),
                confidence=0.88,
            ),
        ),
        reference_summary=ChatReferenceDitaSummary(
            style_profile=ReferenceStyleProfile(
                root_local_name="task",
                taskbody_top_level_sequence=["prereq", "context", "steps", "result", "example"],
                structural_habits=["uses_steps", "uses_result"],
                uses_prolog=True,
                inline_element_usage={"uicontrol": 2},
            )
        ),
        options=ChatDitaGenerationOptions(),
    )
    assert plan.reference_adoption is not None
    assert plan.reference_adoption.mode == "compatible_adoption"
    assert [section.name for section in plan.sections[:5]] == [
        "Prerequisites",
        "Context",
        "Steps",
        "Result",
        "Examples",
    ]


@pytest.mark.anyio
async def test_build_semantic_plan_reference_route_preserves_content_first_on_conflict(service: ChatDitaAuthoringService):
    plan = await service._build_semantic_plan(
        user_prompt="Generate a reference topic from this screenshot",
        image_context=ChatImageContext(
            summary="Translation settings dialog.",
            structured=ScreenshotContentModel(
                title="Translation settings",
                field_value_pairs=[
                    ScreenshotFieldValueItem(field="Language", value="French", confidence=0.88),
                    ScreenshotFieldValueItem(field="Provider", value="Adobe Translation", confidence=0.84),
                ],
                screenshot_intent_route_decision=ScreenshotIntentRouteDecision(
                    chosenRoute="reference_extraction_mode",
                    routeConfidence=0.9,
                    reasons=["field/value density"],
                    downstreamConstraints=["Preserve field-value associations"],
                ),
                confidence=0.87,
            ),
        ),
        reference_summary=ChatReferenceDitaSummary(
            style_profile=ReferenceStyleProfile(
                root_local_name="task",
                taskbody_top_level_sequence=["context", "steps", "result"],
                structural_habits=["uses_steps"],
                uses_prolog=True,
            )
        ),
        options=ChatDitaGenerationOptions(),
    )
    assert plan.dita_type == "reference"
    assert plan.reference_adoption is not None
    assert plan.reference_adoption.mode == "conflict_preserve_content"
    assert any("conflicts" in warning.lower() for warning in plan.reference_adoption.warnings)


def test_reference_serializer_policy_uses_reference_section_titles(service: ChatDitaAuthoringService):
    policy = service._build_reference_serializer_policy(
        profile=ReferenceStyleProfile(
            root_local_name="reference",
            body_section_titles=["Dialog layout", "Settings fields", "Parameter tables"],
            structural_habits=["uses_properties", "uses_table"],
        ),
        target_root_type="reference",
    )
    assert policy is not None
    assert policy.preferred_section_names[:3] == ["Dialog layout", "Settings fields", "Parameter tables"]
    assert policy.preferred_section_name_map["dialog layout"] == "Dialog layout"
    assert policy.preferred_section_name_map["field details"] == "Settings fields"
    assert policy.preferred_section_name_map["parameter tables"] == "Parameter tables"
    assert policy.prefer_properties_layout is True


@pytest.mark.anyio
async def test_generate_topic_from_request_keeps_reference_screenshot_meaning_and_adopts_reference_structure(
    monkeypatch,
    service: ChatDitaAuthoringService,
):
    from app.services import chat_dita_authoring_service as mod

    async def fake_vision(*, image, image_bytes, user_prompt):
        return ChatImageContext(
            summary="Translation settings dialog with tabs, fields, and a provider table.",
            structured=ScreenshotContentModel(
                title="Translation settings",
                field_value_pairs=[
                    ScreenshotFieldValueItem(field="Language", value="French", confidence=0.88),
                    ScreenshotFieldValueItem(field="Provider", value="Adobe Translation", confidence=0.84),
                ],
                tables=[
                    ScreenshotTableItem(
                        caption="Provider limits",
                        headers=["Provider", "Concurrent jobs"],
                        rows=[["Adobe Translation", "10"]],
                        confidence=0.8,
                    )
                ],
                settings_reference_model=ScreenshotSettingsReferenceModel(
                    title="Translation settings",
                    tabs=["General", "Advanced"],
                    active_tab="General",
                    sections=[],
                    confidence=0.85,
                ),
                screenshot_type_classification=ScreenshotTypeClassification(
                    screenshot_type="settings_reference_screenshot",
                    confidence=0.9,
                    reasons=["field/value density", "settings tabs"],
                ),
                screenshot_intent_route_decision=ScreenshotIntentRouteDecision(
                    chosenRoute="reference_extraction_mode",
                    routeConfidence=0.92,
                    reasons=["settings layout and field/value structure"],
                    downstreamConstraints=["Preserve field-value associations and parameter tables"],
                ),
                confidence=0.87,
            ),
        )

    monkeypatch.setattr(
        "app.services.topic_generation.screenshot_understanding_service.extract_screenshot_context",
        fake_vision,
    )

    ref_xml = """<?xml version="1.0"?>
<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "technicalContent/dtd/reference.dtd">
<reference id="translation-settings-ref" xml:lang="fr-FR" outputclass="panel-ref">
  <title>Translation settings</title>
  <refbody>
    <section><title>Dialog layout</title><p>Tabs and panels.</p></section>
    <section>
      <title>Settings fields</title>
      <properties>
        <property><proptype>Language</proptype><propvalue>French</propvalue></property>
      </properties>
    </section>
    <section>
      <title>Parameter tables</title>
      <simpletable>
        <strow><stentry>Provider</stentry><stentry>Concurrent jobs</stentry></strow>
        <strow><stentry>Adobe Translation</stentry><stentry>10</stentry></strow>
      </simpletable>
    </section>
  </refbody>
</reference>"""

    def fake_read(aid: str):
        if aid == "img-1":
            return b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, {}
        if aid == "ref-1":
            return ref_xml.encode(), {}
        return b"", {}

    monkeypatch.setattr(mod, "read_asset_bytes", fake_read)
    monkeypatch.setattr(
        "app.services.topic_generation.dita_validation_service.build_review_snapshot",
        AsyncMock(return_value={"validation": [], "aem_guides_validation_errors": [], "quality_score": 88}),
    )
    monkeypatch.setattr(
        "app.services.topic_generation.dita_validation_service.validate_dita_folder",
        lambda _p: {"errors": [], "warnings": []},
    )
    monkeypatch.setattr(
        "app.services.topic_generation.dita_validation_service.DitaValidationService._folder_validate",
        lambda self, xml, *, file_name: {"errors": [], "warnings": []},
    )
    monkeypatch.setattr(
        mod,
        "save_text_asset",
        lambda **k: ChatAttachmentRef(
            asset_id="generated-1",
            kind="generated_dita",
            filename="translation-settings.dita",
            mime_type="application/xml",
            size_bytes=512,
            url="/api/v1/chat/assets/generated-1",
        ),
    )
    monkeypatch.setattr(mod, "is_llm_available", lambda: False)

    payload = ChatAuthoringRequestPayload(
        content="Generate a DITA reference topic from this screenshot and use the reference style.",
        attachments=[
            ChatAttachmentRef(
                asset_id="img-1",
                kind="image",
                filename="translation-settings.png",
                mime_type="image/png",
                size_bytes=40,
                url="/api/v1/chat/assets/img-1",
            ),
            ChatAttachmentRef(
                asset_id="ref-1",
                kind="reference_dita",
                filename="reference.dita",
                mime_type="application/xml",
                size_bytes=len(ref_xml),
                url="/api/v1/chat/assets/ref-1",
            ),
        ],
        generation_options=ChatDitaGenerationOptions(
            dita_type="reference",
            style_strictness="high",
            output_mode="xml_style_diff",
        ),
    )

    result = await service.generate_topic_from_request(
        payload=payload,
        session_id="sess-ref",
        user_id="user-ref",
        tenant_id="kone",
    )

    assert result.status in {"valid", "saved", "repaired"}
    assert result.dita_type == "reference"
    assert result.reference_adoption_decision is not None
    assert result.reference_adoption_decision.mode == "compatible_adoption"
    assert result.debug.screenshot_type == "settings_reference_screenshot"
    assert result.debug.screenshot_intent_route == "reference_extraction_mode"
    assert result.debug.reference_adoption_mode == "compatible_adoption"
    assert "compatible adoption" in (result.style_profile_diff_summary or "").lower()
    section_names = [section.name for section in result.semantic_plan.sections]
    assert section_names[:3] == ["Dialog layout", "Settings fields", "Parameter tables"]
    assert "xml:lang=\"fr-FR\"" in (result.xml_preview or "")
    assert "<reference" in (result.xml_preview or "")
    assert "<properties>" in (result.xml_preview or "")


@pytest.mark.anyio
async def test_build_semantic_plan_uses_conceptual_diagram_route(service: ChatDitaAuthoringService):
    plan = await service._build_semantic_plan(
        user_prompt="Create a concept topic from this hierarchy diagram",
        image_context=ChatImageContext(
            summary="DITA map hierarchy showing parent-child relationships.",
            structured=ScreenshotContentModel(
                title="DITA map hierarchy",
                diagram_interpretation=DiagramInterpretationModel(
                    diagram_kind="hierarchy",
                    content_orientation="conceptual",
                    dominant_meaning="Show how the root map branches into concept, task, and reference topics.",
                    key_entities=["DITA map", "Concept topics", "Task topics", "Reference topics"],
                    relationships=[
                        DiagramRelationshipItem(source="DITA map", target="Concept topics", kind="parent_child", confidence=0.9),
                        DiagramRelationshipItem(source="DITA map", target="Task topics", kind="parent_child", confidence=0.89),
                    ],
                    groups=[
                        DiagramGroupItem(name="Topic branches", members=["Concept topics", "Task topics", "Reference topics"], confidence=0.82)
                    ],
                    confidence=0.9,
                ),
                screenshot_intent_route_decision=ScreenshotIntentRouteDecision(
                    chosenRoute="conceptual_diagram_mode",
                    routeConfidence=0.92,
                    reasons=["diagram relationships"],
                    downstreamConstraints=["Preserve conceptual structure"],
                ),
                confidence=0.9,
            ),
        ),
        reference_summary=ChatReferenceDitaSummary(),
        options=ChatDitaGenerationOptions(),
    )
    assert plan.dita_type == "concept"
    assert any(section.name.lower() == "relationships" for section in plan.sections)
    assert any("DITA map -> Concept topics" in detail for section in plan.sections for detail in section.details)
    assert all(not section.purpose for section in plan.sections)


@pytest.mark.anyio
async def test_build_semantic_plan_uses_mixed_content_route(service: ChatDitaAuthoringService):
    plan = await service._build_semantic_plan(
        user_prompt="Create a topic from this mixed screenshot",
        image_context=ChatImageContext(
            summary="Screenshot contains settings fields and a short procedure.",
            structured=ScreenshotContentModel(
                title="Configure translation profile",
                procedural_model=ScreenshotProceduralModel(
                    title="Configure translation profile",
                    steps=[
                        ScreenshotProceduralStep(marker="1.", command="Open User Preferences", confidence=0.89),
                        ScreenshotProceduralStep(marker="2.", command="Select Translation", confidence=0.88),
                    ],
                    confidence=0.87,
                ),
                field_value_pairs=[
                    ScreenshotFieldValueItem(field="Language", value="French", confidence=0.84),
                    ScreenshotFieldValueItem(field="Provider", value="Adobe Translation", confidence=0.82),
                ],
                diagram_interpretation=DiagramInterpretationModel(
                    diagram_kind="relationship",
                    content_orientation="mixed",
                    dominant_meaning="Profile settings and translation workflow are shown together.",
                    key_entities=["Profile", "Translation provider"],
                    confidence=0.7,
                ),
                screenshot_intent_route_decision=ScreenshotIntentRouteDecision(
                    chosenRoute="mixed_content_mode",
                    routeConfidence=0.83,
                    reasons=["procedure and settings both visible"],
                    downstreamConstraints=["Preserve multiple evidence types"],
                ),
                confidence=0.85,
            ),
        ),
        reference_summary=ChatReferenceDitaSummary(),
        options=ChatDitaGenerationOptions(),
    )
    assert plan.dita_type in {"topic", "concept", "reference", "task"}
    assert any(section.name.lower() == "procedure evidence" for section in plan.sections)
    assert any(section.name.lower() == "reference evidence" for section in plan.sections)
    assert not any(section.name.lower() == "body" for section in plan.sections)


@pytest.mark.anyio
async def test_generate_topic_blocks_placeholder_output_when_screenshot_signal_is_too_weak(
    monkeypatch,
    service: ChatDitaAuthoringService,
):
    from app.services import chat_dita_authoring_service as mod

    image_context = ChatImageContext(
        summary="Screenshot understanding ran in fallback mode and preserved only minimal safe context.",
        warnings=["Vision provider unavailable; screenshot understanding returned only a conservative fallback."],
        vision_provider="fallback",
        structured=ScreenshotContentModel(
            confidence=0.12,
            uncertainty_warnings=["Vision provider unavailable; screenshot understanding returned only a conservative fallback."],
            screenshot_intent_route_decision=ScreenshotIntentRouteDecision(
                chosenRoute="safe_fallback_mode",
                routeConfidence=0.24,
                reasons=["Low-confidence unknown screenshot"],
                downstreamConstraints=["Do not over-structure weak evidence"],
            ),
        ),
    )
    merged_plan = ChatSemanticPlan(
        title="Configure Radware vDP Cluster",
        dita_type="task",
        shortdesc="Configure a Radware vDP cluster",
        sections=[
            ChatSemanticPlanSection(
                name="Introduction",
                purpose="",
                details=["Briefly introduce the task of configuring a Radware vDP cluster."],
            ),
            ChatSemanticPlanSection(
                name="Prerequisites",
                purpose="",
                details=["List the requirements for configuring a Radware vDP cluster."],
            ),
            ChatSemanticPlanSection(
                name="Configuration Steps",
                purpose="",
                details=[
                    "Use the user interface to configure the cluster",
                    "Configure the cluster settings",
                ],
            ),
            ChatSemanticPlanSection(
                name="Verification",
                purpose="",
                details=["Verify that the cluster has been configured correctly."],
            ),
        ],
        source_notes=["Built from the attached screenshot and prompt without LLM plan generation."],
    )

    async def fake_pipeline(**kwargs):
        draft = build_topic_draft(plan=merged_plan, image_context=image_context)
        return (
            ScreenshotAnalysisResult(image_context=image_context),
            ReferenceAnalysisResult(reference_summary=ChatReferenceDitaSummary(), parse_reference_ok=True),
            TopicTypeResult(
                dita_type="task",
                effective_options=ChatDitaGenerationOptions(dita_type="task"),
                topic_type_overridden=False,
            ),
            SemanticPlanResult(semantic_plan=merged_plan),
            MergedPlanResult(merged_plan=merged_plan),
            StructuredDraftResult(topic_draft=draft),
            SerializationResult(
                xml="""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "technicalContent/dtd/task.dtd">
<task id="configure-radware-vdp-cluster"><title>Configure Radware vDP Cluster</title></task>""",
                mode="programmatic",
            ),
            ValidationStageResult(
                normalized_xml="""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "technicalContent/dtd/task.dtd">
<task id="configure-radware-vdp-cluster"><title>Configure Radware vDP Cluster</title></task>""",
                validation_result=ChatDitaValidationResult(valid=True),
                review_snapshot={"quality_score": 24},
            ),
            None,
            AuthoringPipelineTrace(run_id="run-1"),
        )

    def fake_read(_asset_id: str):
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, {}

    def fail_if_saved(**kwargs):
        raise AssertionError("Weak screenshot generations should not persist placeholder XML artifacts")

    monkeypatch.setattr(mod, "run_screenshot_guided_pipeline", fake_pipeline)
    monkeypatch.setattr(mod, "read_asset_bytes", fake_read)
    monkeypatch.setattr(mod, "save_text_asset", fail_if_saved)

    payload = ChatAuthoringRequestPayload(
        content="Generate a DITA task topic from this screenshot",
        attachments=[
            ChatAttachmentRef(
                asset_id="img-1",
                kind="image",
                filename="screen.png",
                mime_type="image/png",
                size_bytes=32,
                url="/api/v1/chat/assets/img-1",
            )
        ],
        generation_options=ChatDitaGenerationOptions(
            dita_type="task",
            style_strictness="high",
            strict_validation=True,
        ),
    )

    result = await service.generate_topic_from_request(
        payload=payload,
        session_id="sess-weak",
        user_id="user-weak",
        tenant_id="kone",
    )

    assert result.status == "invalid"
    assert result.xml_preview == ""
    assert result.validation_result.valid is False
    assert any("vision analysis is unavailable" in issue.lower() for issue in result.validation_result.structural_issues)
    assert any("placeholder scaffolding" in issue.lower() for issue in result.validation_result.structural_issues)
    assert "Screenshot review required" in (result.message or "")
    assert all(action.key != "open_in_editor" for action in (result.actions or []))
