from __future__ import annotations

from app.core.schemas_chat_authoring import (
    DiagramInterpretationModel,
    DiagramRelationshipItem,
    ScreenshotContentModel,
    ScreenshotFieldValueItem,
    ScreenshotNoteItem,
    ScreenshotParagraphItem,
    ScreenshotProceduralModel,
    ScreenshotProceduralStep,
    ScreenshotProceduralSubstep,
    ScreenshotRegionItem,
    ScreenshotSectionItem,
    ScreenshotSettingsReferenceModel,
    ScreenshotSettingsSection,
    ScreenshotUnresolvedBlock,
)
from app.services.screenshot_type_classifier import ScreenshotTypeClassifier, extract_screenshot_classification_features


def _base_model(**updates) -> ScreenshotContentModel:
    base = ScreenshotContentModel(
        title="Sample screenshot",
        confidence=0.86,
        regions=[
            ScreenshotRegionItem(region_id="r1", region_type="title", text="Sample screenshot", confidence=0.92),
            ScreenshotRegionItem(region_id="r2", region_type="paragraph", text="Body text", confidence=0.82),
        ],
    )
    return base.model_copy(update=updates)


def test_extract_features_collects_editor_and_list_signals():
    model = _base_model(
        ui_labels=["<topic>", "<taskbody>", "Map"],
        button_names=["Save"],
        menu_names=["File"],
        numbered_steps=["Open Output Presets", "Click Save"],
        substeps=[ScreenshotProceduralSubstep(marker="a.", command="Select PDF", confidence=0.8)],
        regions=[
            ScreenshotRegionItem(region_id="r1", region_type="title", text="Map editor", confidence=0.95),
            ScreenshotRegionItem(region_id="r2", region_type="ui_control_text", text="<topic>", confidence=0.88),
            ScreenshotRegionItem(region_id="r3", region_type="numbered_list", lines=["1. Open", "  a. Select"], confidence=0.84),
        ],
    )
    features = extract_screenshot_classification_features(model, screenshot_context="DITA editor screenshot")
    assert features.visible_dita_chip_count >= 2
    assert features.numbered_step_count == 2
    assert features.substep_count == 1
    assert features.ui_control_count >= 3
    assert "editor" in features.screenshot_context_terms


def test_classifier_identifies_editor_structure_screenshot():
    classifier = ScreenshotTypeClassifier()
    model = _base_model(
        ui_labels=["<topic>", "<taskbody>", "<shortdesc>", "Map"],
        button_names=["Save", "Cancel"],
        menu_names=["File", "Edit"],
        headings=[],
        sections=[ScreenshotSectionItem(name="Structure", purpose="", details=["topic", "taskbody"])],
        regions=[
            ScreenshotRegionItem(region_id="r1", region_type="title", text="DITA editor", confidence=0.95),
            ScreenshotRegionItem(region_id="r2", region_type="ui_control_text", text="<topic>", confidence=0.88),
            ScreenshotRegionItem(region_id="r3", region_type="ui_control_text", text="<taskbody>", confidence=0.88),
            ScreenshotRegionItem(region_id="r4", region_type="paragraph", text="Map view", confidence=0.8),
        ],
    )
    _, result = classifier.classify(model, screenshot_context="AEM Guides DITA editor screenshot")
    assert result.screenshot_type == "editor_structure_screenshot"
    assert result.confidence >= 0.6


def test_classifier_identifies_procedural_ui_screenshot():
    classifier = ScreenshotTypeClassifier()
    model = _base_model(
        numbered_steps=["Open Output Presets", "Click Save"],
        notes=[ScreenshotNoteItem(kind="note", text="Make sure the map is checked in.", confidence=0.78)],
        procedural_model=ScreenshotProceduralModel(
            title="Create preset",
            steps=[
                ScreenshotProceduralStep(
                    marker="1.",
                    command="Open Output Presets",
                    substeps=[ScreenshotProceduralSubstep(marker="a.", command="Select PDF", confidence=0.8)],
                    confidence=0.9,
                ),
                ScreenshotProceduralStep(marker="2.", command="Click Save", confidence=0.88),
            ],
            confidence=0.86,
        ),
        button_names=["Save"],
        regions=[
            ScreenshotRegionItem(region_id="r1", region_type="title", text="Create an output preset", confidence=0.95),
            ScreenshotRegionItem(region_id="r2", region_type="numbered_list", lines=["1. Open Output Presets", "  a. Select PDF", "2. Click Save"], confidence=0.88),
            ScreenshotRegionItem(region_id="r3", region_type="note", text="Save adds the preset to the list.", confidence=0.74),
        ],
    )
    _, result = classifier.classify(model, screenshot_context="How to create an output preset steps")
    assert result.screenshot_type == "procedural_ui_screenshot"
    assert result.confidence >= 0.65


def test_classifier_identifies_settings_reference_screenshot():
    classifier = ScreenshotTypeClassifier()
    model = _base_model(
        field_value_pairs=[
            ScreenshotFieldValueItem(field="Language", value="French", confidence=0.88),
            ScreenshotFieldValueItem(field="Provider", value="Adobe Translation", confidence=0.87),
            ScreenshotFieldValueItem(field="Status", value="Enabled", confidence=0.83),
        ],
        settings_reference_model=ScreenshotSettingsReferenceModel(
            title="Translation settings",
            tabs=["General", "Advanced"],
            sections=[
                ScreenshotSettingsSection(title="General", description=["Configure translation defaults"], confidence=0.85),
                ScreenshotSettingsSection(title="Advanced", description=["Fine-tune provider behavior"], confidence=0.8),
            ],
            confidence=0.84,
        ),
        ui_labels=["Language", "Provider", "Status"],
        regions=[
            ScreenshotRegionItem(region_id="r1", region_type="title", text="Translation settings", confidence=0.95),
            ScreenshotRegionItem(region_id="r2", region_type="field_value_block", lines=["Language: French", "Provider: Adobe Translation"], confidence=0.88),
            ScreenshotRegionItem(region_id="r3", region_type="field_value_block", lines=["Status: Enabled"], confidence=0.83),
            ScreenshotRegionItem(region_id="r4", region_type="heading", text="Advanced", confidence=0.8),
        ],
    )
    _, result = classifier.classify(model, screenshot_context="Settings dialog for translation configuration")
    assert result.screenshot_type == "settings_reference_screenshot"
    assert result.confidence >= 0.6


def test_classifier_identifies_conceptual_diagram():
    classifier = ScreenshotTypeClassifier()
    model = _base_model(
        diagram_interpretation=DiagramInterpretationModel(
            diagram_kind="hierarchy",
            content_orientation="conceptual",
            dominant_meaning="DITA map hierarchy",
            key_entities=["DITA map", "Concepts", "Tasks", "Reference"],
            relationships=[
                DiagramRelationshipItem(source="DITA map", target="Concepts", kind="parent_child", confidence=0.9),
                DiagramRelationshipItem(source="DITA map", target="Tasks", kind="parent_child", confidence=0.9),
                DiagramRelationshipItem(source="DITA map", target="Reference", kind="parent_child", confidence=0.9),
            ],
            confidence=0.9,
        ),
        regions=[
            ScreenshotRegionItem(region_id="r1", region_type="title", text="DITA map hierarchy", confidence=0.95),
            ScreenshotRegionItem(region_id="r2", region_type="paragraph", text="Concept, task, and reference branches", confidence=0.8),
        ],
    )
    _, result = classifier.classify(model, screenshot_context="Diagram showing DITA map hierarchy")
    assert result.screenshot_type == "conceptual_diagram"
    assert result.confidence >= 0.65


def test_classifier_identifies_mixed_content_screenshot():
    classifier = ScreenshotTypeClassifier()
    model = _base_model(
        numbered_steps=["Open settings", "Click Save"],
        procedural_model=ScreenshotProceduralModel(
            title="Update settings",
            steps=[
                ScreenshotProceduralStep(marker="1.", command="Open settings", confidence=0.86),
                ScreenshotProceduralStep(marker="2.", command="Click Save", confidence=0.85),
            ],
            confidence=0.82,
        ),
        field_value_pairs=[
            ScreenshotFieldValueItem(field="Language", value="French", confidence=0.88),
            ScreenshotFieldValueItem(field="Provider", value="Adobe Translation", confidence=0.87),
        ],
        settings_reference_model=ScreenshotSettingsReferenceModel(
            title="Translation settings",
            tabs=["General"],
            sections=[ScreenshotSettingsSection(title="General", confidence=0.8)],
            confidence=0.8,
        ),
        regions=[
            ScreenshotRegionItem(region_id="r1", region_type="title", text="Update translation settings", confidence=0.95),
            ScreenshotRegionItem(region_id="r2", region_type="numbered_list", lines=["1. Open settings", "2. Click Save"], confidence=0.86),
            ScreenshotRegionItem(region_id="r3", region_type="field_value_block", lines=["Language: French", "Provider: Adobe Translation"], confidence=0.88),
        ],
    )
    _, result = classifier.classify(model, screenshot_context="Workflow and settings panel")
    assert result.screenshot_type == "mixed_content_screenshot"
    assert result.confidence >= 0.55
    assert any(alt.screenshot_type in {"procedural_ui_screenshot", "settings_reference_screenshot"} for alt in result.ambiguous_alternatives)


def test_classifier_identifies_generic_content_screenshot():
    classifier = ScreenshotTypeClassifier()
    model = _base_model(
        headings=[],
        paragraphs=[
            ScreenshotParagraphItem(text="AEM Guides helps authors manage DITA content.", confidence=0.84),
            ScreenshotParagraphItem(text="Use output presets to publish content in multiple formats.", confidence=0.83),
        ],
        sections=[ScreenshotSectionItem(name="Overview", purpose="", details=["General description"])],
        regions=[
            ScreenshotRegionItem(region_id="r1", region_type="title", text="About output presets", confidence=0.9),
            ScreenshotRegionItem(region_id="r2", region_type="paragraph", text="AEM Guides helps authors manage DITA content.", confidence=0.84),
            ScreenshotRegionItem(region_id="r3", region_type="paragraph", text="Use output presets to publish content in multiple formats.", confidence=0.83),
        ],
    )
    _, result = classifier.classify(model, screenshot_context="Explain output presets")
    assert result.screenshot_type == "generic_content_screenshot"
    assert result.confidence >= 0.45


def test_classifier_falls_back_to_low_confidence_unknown():
    classifier = ScreenshotTypeClassifier()
    model = _base_model(
        confidence=0.24,
        regions=[
            ScreenshotRegionItem(region_id="r1", region_type="unknown", text="cropped ???", confidence=0.22, uncertain=True, uncertainty_reason="Cropped"),
        ],
        unresolved_blocks=[
            ScreenshotUnresolvedBlock(region_id="r1", candidate_type="unknown", raw_text="cropped ???", reason="Cropped", confidence=0.22)
        ],
        uncertain_region_ids=["r1"],
    )
    _, result = classifier.classify(model, screenshot_context="blurry screenshot")
    assert result.screenshot_type == "low_confidence_unknown"
    assert result.confidence >= 0.45
    assert result.reasons
