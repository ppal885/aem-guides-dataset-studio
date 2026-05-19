"""Tests for ScreenshotUnderstandingService IR, heuristics, and input-quality edge cases."""

import base64

import pytest

from app.core.schemas_chat_authoring import (
    ChatAttachmentRef,
    ScreenshotBoundingBox,
    ScreenshotContentModel,
    ScreenshotLayoutRegion,
    ScreenshotTextBlock,
)
from app.services.screenshot_understanding_service import (
    ScreenshotUnderstandingService,
    _build_structured_from_parsed,
    _choose_vision_provider,
    _image_context_from_parsed,
    _parse_json_loose,
    _parsed_from_multi_pass,
    _png_dimensions,
    _screenshot_vision_diagnostics,
    apply_ir_heuristics,
    assess_screenshot_input_quality,
    extract_screenshot_context,
    get_screenshot_understanding_service,
)

# 1x1 transparent PNG (very small file and dimensions — triggers quality heuristics)
MINI_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_parse_json_loose_fenced():
    text = 'Here is JSON:\n```json\n{"summary": "S", "visible_text": ["a"], "confidence": 0.7}\n```'
    d = _parse_json_loose(text)
    assert d.get("summary") == "S"
    assert d.get("confidence") == 0.7


def test_screenshot_vision_diagnostics_supports_azure_openai(monkeypatch):
    monkeypatch.setenv("SCREENSHOT_VISION_PROVIDER", "azure_openai")
    monkeypatch.setattr("app.services.screenshot_understanding_service._AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setattr("app.services.screenshot_understanding_service._AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setattr("app.services.screenshot_understanding_service._AZURE_OPENAI_API_VERSION", "2024-02-01")
    monkeypatch.setattr("app.services.screenshot_understanding_service._AZURE_OPENAI_MODEL", "gpt-4.1-vision")

    provider, warning = _screenshot_vision_diagnostics()

    assert provider == "azure_openai"
    assert warning is None


@pytest.mark.anyio
async def test_screenshot_understanding_hard_fails_when_azure_required_but_unavailable(monkeypatch):
    import app.services.screenshot_understanding_service as su

    monkeypatch.setenv("LLM_PROVIDER", "azure_openai")
    monkeypatch.setenv("SCREENSHOT_VISION_PROVIDER", "azure_openai")
    monkeypatch.setattr(su, "_AZURE_OPENAI_API_KEY", "")
    monkeypatch.setattr(su, "_AZURE_OPENAI_ENDPOINT", "")
    monkeypatch.setattr(su, "_AZURE_OPENAI_API_VERSION", "")
    monkeypatch.setattr(su, "_AZURE_OPENAI_MODEL", "")

    service = ScreenshotUnderstandingService()
    image = ChatAttachmentRef(
        asset_id="asset-1",
        kind="image",
        filename="screen.png",
        mime_type="image/png",
        url="https://example.test/screen.png",
    )

    with pytest.raises(RuntimeError, match="Azure OpenAI vision is required"):
        await service.understand(image=image, image_bytes=MINI_PNG_1X1, user_prompt="Explain this screen")


@pytest.mark.anyio
async def test_map_outline_hard_fails_when_azure_required_but_unavailable(monkeypatch):
    import app.services.screenshot_understanding_service as su

    monkeypatch.setenv("LLM_PROVIDER", "azure_openai")
    monkeypatch.setenv("SCREENSHOT_VISION_PROVIDER", "azure_openai")
    monkeypatch.setattr(su, "_AZURE_OPENAI_API_KEY", "")
    monkeypatch.setattr(su, "_AZURE_OPENAI_ENDPOINT", "")
    monkeypatch.setattr(su, "_AZURE_OPENAI_API_VERSION", "")
    monkeypatch.setattr(su, "_AZURE_OPENAI_MODEL", "")

    service = ScreenshotUnderstandingService()

    with pytest.raises(RuntimeError, match="Azure OpenAI vision is required"):
        await service.extract_map_hierarchy_outline(
            image_bytes=MINI_PNG_1X1,
            mime_type="image/png",
            user_prompt="Generate a map outline from this screenshot",
        )


def test_build_structured_full_ir():
    d = {
        "title": "Deploy guide",
        "headings": [{"level": 2, "text": "Prerequisites"}, {"level": 2, "text": "Steps"}],
        "numbered_steps": ["Open console", "Run script"],
        "sections": [{"name": "Overview", "details": ["One-time setup"]}],
        "menu_names": ["File", "Edit"],
        "button_names": ["Save", "Cancel"],
        "ui_labels": ["Server name", "Save", "Cancel"],
        "emphasis_cues": [{"text": "admin", "cue": "monospace"}, {"text": "Important", "cue": "bold"}],
        "acceptance_criteria": ["Service responds 200"],
        "field_confidence": {"title": 0.9, "steps": 0.85},
        "confidence": 0.88,
        "uncertainty_warnings": [],
    }
    sc = _build_structured_from_parsed(d)
    assert sc.title == "Deploy guide"
    assert len(sc.headings) == 2
    assert sc.headings[0].level == 2
    assert sc.menu_names == ["File", "Edit"]
    assert sc.button_names == ["Save", "Cancel"]
    assert sc.field_confidence.get("title") == 0.9
    assert len(sc.emphasis_cues) == 2
    assert sc.emphasis_cues[0].cue == "monospace"


def test_build_structured_regions_preserves_order_and_field_values():
    parsed = {
        "regions": [
            {
                "region_id": "r-title",
                "region_type": "title",
                "text": "Configure Translation Settings",
                "confidence": 0.95,
                "order_hint": 1,
            },
            {
                "region_id": "r-steps",
                "region_type": "numbered_list",
                "items": ["Open User Preferences", "Select Translation", "Save the profile"],
                "confidence": 0.9,
                "order_hint": 3,
            },
            {
                "region_id": "r-fields",
                "region_type": "field_value_block",
                "field_values": [
                    {"field": "Language", "value": "French", "confidence": 0.88},
                    {"field": "Provider", "value": "Adobe Translation Integration", "confidence": 0.83},
                ],
                "confidence": 0.87,
                "order_hint": 2,
            },
        ],
        "confidence": 0.91,
    }
    sc = _build_structured_from_parsed(parsed)
    assert sc.title == "Configure Translation Settings"
    assert sc.reading_order == ["r-title", "r-fields", "r-steps"]
    assert [(pair.field, pair.value) for pair in sc.field_value_pairs] == [
        ("Language", "French"),
        ("Provider", "Adobe Translation Integration"),
    ]
    assert sc.numbered_steps == ["Open User Preferences", "Select Translation", "Save the profile"]
    assert any(section.name == "Overview" or section.name == "Field details" for section in sc.sections)


def test_build_structured_preserves_paragraphs_and_unresolved_blocks():
    parsed = {
        "regions": [
            {
                "region_id": "r-paragraph",
                "region_type": "paragraph",
                "text": "Use the Output Presets panel to configure PDF output.",
                "confidence": 0.88,
                "order_hint": 1,
            },
            {
                "region_id": "r-unknown",
                "region_type": "unknown",
                "lines": ["??? profile option", "cropped on right"],
                "confidence": 0.31,
                "uncertain": True,
                "uncertainty_reason": "Right side of the screenshot is cropped.",
                "order_hint": 2,
            },
        ],
        "confidence": 0.82,
    }
    sc = _build_structured_from_parsed(parsed)
    assert [p.text for p in sc.paragraphs] == ["Use the Output Presets panel to configure PDF output."]
    assert len(sc.unresolved_blocks) == 1
    assert sc.unresolved_blocks[0].region_id == "r-unknown"
    assert "cropped" in sc.unresolved_blocks[0].reason.lower()
    assert any("cropped" in warning.lower() for warning in sc.uncertainty_warnings)


def test_build_structured_keeps_low_confidence_explicit_field_blocks_without_forcing_certainty():
    parsed = {
        "regions": [
            {
                "region_id": "r-title",
                "region_type": "title",
                "text": "Translation settings",
                "confidence": 0.9,
                "order_hint": 1,
            },
            {
                "region_id": "r-fields",
                "region_type": "field_value_block",
                "field_values": [
                    {"field": "Language", "value": "French", "confidence": 0.39},
                    {"field": "Provider", "value": "Adobe Translation", "confidence": 0.37},
                ],
                "confidence": 0.38,
                "uncertain": True,
                "uncertainty_reason": "OCR was faint but the visible field labels were recoverable.",
                "order_hint": 2,
            },
        ],
        "confidence": 0.58,
    }
    sc = _build_structured_from_parsed(parsed)
    assert [(pair.field, pair.value) for pair in sc.field_value_pairs] == [
        ("Language", "French"),
        ("Provider", "Adobe Translation"),
    ]
    assert any("Language: French" in detail for section in sc.sections for detail in section.details)
    assert any(block.region_id == "r-fields" for block in sc.unresolved_blocks)
    assert "r-fields" in sc.uncertain_region_ids


def test_build_structured_preserves_substeps_from_procedural_model():
    parsed = {
        "regions": [
            {
                "region_id": "r-steps",
                "region_type": "numbered_list",
                "lines": ["1. Open Output Presets", "   a. Select PDF", "2. Click Save"],
                "confidence": 0.89,
            }
        ],
        "procedural_model": {
            "title": "Create an output preset",
            "steps": [
                {
                    "marker": "1.",
                    "command": "Open Output Presets",
                    "substeps": [
                        {
                            "marker": "a.",
                            "command": "Select PDF",
                            "confidence": 0.84,
                            "source_region_id": "r-steps",
                        }
                    ],
                    "confidence": 0.9,
                    "source_region_id": "r-steps",
                }
            ],
            "confidence": 0.9,
        },
        "confidence": 0.9,
    }
    sc = _build_structured_from_parsed(parsed)
    assert len(sc.substeps) == 1
    assert sc.substeps[0].command == "Select PDF"
    assert sc.substeps[0].source_region_id == "r-steps"


def test_build_structured_merges_wrapped_paragraphs_and_recovers_stacked_field_values():
    parsed = {
        "regions": [
            {
                "region_id": "r-paragraph",
                "region_type": "paragraph",
                "lines": [
                    "Use the Output Presets panel",
                    "to configure PDF output for publishing.",
                ],
                "confidence": 0.88,
                "order_hint": 1,
            },
            {
                "region_id": "r-fields",
                "region_type": "field_value_block",
                "lines": [
                    "Language",
                    "French",
                    "Provider",
                    "Adobe Translation Integration",
                ],
                "confidence": 0.84,
                "order_hint": 2,
            },
        ],
        "confidence": 0.86,
    }
    sc = _build_structured_from_parsed(parsed)
    assert [p.text for p in sc.paragraphs] == [
        "Use the Output Presets panel to configure PDF output for publishing."
    ]
    assert [(pair.field, pair.value) for pair in sc.field_value_pairs] == [
        ("Language", "French"),
        ("Provider", "Adobe Translation Integration"),
    ]


def test_multi_pass_fallback_keeps_text_regions_and_infers_structure_without_semantic_block():
    parsed = _parsed_from_multi_pass(
        layout_regions=[
            ScreenshotLayoutRegion(
                region_id="r-steps",
                layout_type="paragraph",
                bbox=ScreenshotBoundingBox(x=0.1, y=0.2, width=0.7, height=0.2),
                order_hint=2,
                confidence=0.72,
            )
        ],
        text_blocks=[
            ScreenshotTextBlock(
                region_id="r-steps",
                layout_type="paragraph",
                bbox=ScreenshotBoundingBox(x=0.1, y=0.2, width=0.7, height=0.2),
                raw_text="1. Open Output Presets\n   a. Select PDF\n2. Click Save",
                lines=["1. Open Output Presets", "   a. Select PDF", "2. Click Save"],
                confidence=0.81,
            )
        ],
        semantic_blocks=[],
        initial_summary="Procedural screenshot with a missing semantic classification response.",
    )
    sc = _build_structured_from_parsed(parsed)
    region = next(region for region in sc.regions if region.region_id == "r-steps")
    assert region.region_type == "numbered_list"
    assert region.uncertain is True
    assert "semantic classification" in (region.uncertainty_reason or "").lower()
    assert sc.numbered_steps == ["1. Open Output Presets", "a. Select PDF", "2. Click Save"]
    assert any(substep.command == "Select PDF" for substep in sc.substeps)


def test_build_structured_derives_settings_tabs_and_parameter_tables_from_regions():
    parsed = {
        "regions": [
            {
                "region_id": "r-tabs",
                "region_type": "ui_control_text",
                "items": ["General", "Advanced", "Save"],
                "confidence": 0.86,
                "order_hint": 1,
            },
            {
                "region_id": "r-table",
                "region_type": "field_value_block",
                "lines": [
                    "Property  Value  Description",
                    "Language  French  UI locale for the translator profile",
                    "Provider  Adobe Translation  Translation service used for jobs",
                ],
                "confidence": 0.84,
                "order_hint": 2,
            },
        ],
        "confidence": 0.85,
    }
    sc = _build_structured_from_parsed(parsed)
    assert sc.settings_reference_model is not None
    assert sc.settings_reference_model.tabs == ["General", "Advanced"]
    section = sc.settings_reference_model.sections[0]
    assert len(section.parameter_tables) == 1
    assert section.parameter_tables[0].headers == ["Property", "Value", "Description"]
    assert section.parameter_tables[0].rows[0] == ["Language", "French", "UI locale for the translator profile"]


def test_build_structured_filters_short_ui_control_noise_from_sections():
    parsed = {
        "regions": [
            {
                "region_id": "r-heading",
                "region_type": "heading",
                "text": "Translation settings",
                "heading_level": 2,
                "confidence": 0.9,
                "order_hint": 1,
            },
            {
                "region_id": "r-controls",
                "region_type": "ui_control_text",
                "items": ["Save", "Cancel", "Provider settings panel"],
                "confidence": 0.83,
                "order_hint": 2,
            },
        ],
        "confidence": 0.85,
    }
    sc = _build_structured_from_parsed(parsed)
    section = next(section for section in sc.sections if section.name == "Overview")
    assert "Provider settings panel" in section.details
    assert "Save" not in section.details
    assert "Cancel" not in section.details


def test_build_structured_derives_diagram_interpretation_from_hierarchy_graphic():
    parsed = {
        "title": "DITA map hierarchy",
        "image_characterization": {
            "primary_scene": "Hierarchy diagram of DITA content",
            "author_intent_hypothesis": "Explain conceptual structure",
        },
        "embedded_graphics": [
            {
                "kind": "dita_map_hierarchy",
                "label": "DITA map",
                "description": "Root map with concept, task, and reference branches",
                "root": {
                    "title": "DITA map",
                    "dita_type": "map_root",
                    "confidence": 0.93,
                    "children": [
                        {"title": "Concepts", "dita_type": "concept", "confidence": 0.9},
                        {
                            "title": "Tasks",
                            "dita_type": "task",
                            "confidence": 0.89,
                            "children": [
                                {"title": "Create preset", "dita_type": "task", "confidence": 0.86}
                            ],
                        },
                        {"title": "Reference", "dita_type": "reference", "confidence": 0.88},
                    ],
                },
            }
        ],
        "regions": [
            {"region_id": "r1", "region_type": "title", "text": "DITA map hierarchy", "confidence": 0.94}
        ],
        "confidence": 0.9,
    }
    sc = _build_structured_from_parsed(parsed)
    assert sc.diagram_interpretation is not None
    assert sc.diagram_interpretation.diagram_kind == "hierarchy"
    assert sc.diagram_interpretation.content_orientation == "conceptual"
    assert "DITA map" in sc.diagram_interpretation.key_entities
    assert any(
        rel.source == "DITA map" and rel.target == "Tasks" and rel.kind == "parent_child"
        for rel in sc.diagram_interpretation.relationships
    )


def test_acceptance_criteria_region_not_flattened_into_generic_bullets():
    parsed = {
        "regions": [
            {"region_id": "r1", "region_type": "heading", "text": "Acceptance criteria", "heading_level": 2, "confidence": 0.88},
            {"region_id": "r2", "region_type": "acceptance_criteria", "items": ["Translation job created", "Reviewer can open translated map"], "confidence": 0.85},
            {"region_id": "r3", "region_type": "bullet_list", "items": ["Use staging content first"], "confidence": 0.82},
        ],
        "confidence": 0.86,
    }
    sc = _build_structured_from_parsed(parsed)
    assert sc.acceptance_criteria == ["Translation job created", "Reviewer can open translated map"]
    assert sc.bullet_lists == [["Use staging content first"]]


def test_uncertain_regions_and_small_image_reduce_confidence():
    parsed = {
        "regions": [
            {
                "region_id": "r1",
                "region_type": "paragraph",
                "text": "Partially cropped body text",
                "confidence": 0.52,
                "uncertain": True,
                "uncertainty_reason": "Bottom half of the screenshot is cropped.",
            }
        ],
        "confidence": 0.9,
    }
    ctx = _image_context_from_parsed(
        parsed,
        raw_model="test-vision",
        provider="openai",
        image_bytes=MINI_PNG_1X1,
        mime_type="image/png",
    )
    assert ctx.structured.uncertain_region_ids == ["r1"]
    assert ctx.structured.confidence < 0.9
    assert any("cropped" in item.lower() for item in ctx.structured.uncertainty_warnings)


def test_png_dimensions_mini():
    assert _png_dimensions(MINI_PNG_1X1) == (1, 1)


def test_assess_quality_tiny_png_warns():
    qf, w = assess_screenshot_input_quality(MINI_PNG_1X1, "image/png")
    assert qf < 1.0
    assert any("small" in x.lower() or "dimension" in x.lower() for x in w)


def test_assess_quality_small_bytecount():
    qf, w = assess_screenshot_input_quality(b"abc", "image/jpeg")
    assert qf < 1.0
    assert w


def test_choose_vision_provider_can_use_openai_for_screenshots_while_general_llm_is_groq(monkeypatch):
    import app.services.screenshot_understanding_service as su

    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("SCREENSHOT_VISION_PROVIDER", "openai")
    monkeypatch.setattr(su, "_OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setattr(su, "_ANTHROPIC_API_KEY", "")

    provider, warning = _screenshot_vision_diagnostics()
    assert provider == "openai"
    assert warning is None
    assert _choose_vision_provider() == "openai"


def test_choose_vision_provider_reports_clean_warning_for_missing_explicit_provider(monkeypatch):
    import app.services.screenshot_understanding_service as su

    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("SCREENSHOT_VISION_PROVIDER", "anthropic")
    monkeypatch.setattr(su, "_OPENAI_API_KEY", "")
    monkeypatch.setattr(su, "_ANTHROPIC_API_KEY", "")

    provider, warning = _screenshot_vision_diagnostics()
    assert provider == "fallback"
    assert warning is not None
    assert "SCREENSHOT_VISION_PROVIDER is set to anthropic" in warning


def test_choose_vision_provider_explains_groq_without_supported_vision_key(monkeypatch):
    import app.services.screenshot_understanding_service as su

    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.delenv("SCREENSHOT_VISION_PROVIDER", raising=False)
    monkeypatch.setattr(su, "_AZURE_OPENAI_API_KEY", "")
    monkeypatch.setattr(su, "_AZURE_OPENAI_ENDPOINT", "")
    monkeypatch.setattr(su, "_AZURE_OPENAI_API_VERSION", "")
    monkeypatch.setattr(su, "_AZURE_OPENAI_MODEL", "")
    monkeypatch.setattr(su, "_OPENAI_API_KEY", "")
    monkeypatch.setattr(su, "_ANTHROPIC_API_KEY", "")

    provider, warning = _screenshot_vision_diagnostics()
    assert provider == "fallback"
    assert warning is not None
    assert "LLM_PROVIDER is set to groq" in warning


def test_apply_ir_heuristics_dedupes_ui_vs_buttons():
    base = ScreenshotContentModel(
        title="T",
        ui_labels=["OK", "OK", "Cancel"],
        button_names=["Cancel"],
        confidence=0.9,
    )
    parsed = {"ui_elements": [{"label": "Submit", "kind": "button"}]}
    out = apply_ir_heuristics(base, parsed=parsed, image_bytes=MINI_PNG_1X1, mime_type="image/png")
    assert "Submit" in out.button_names
    assert out.ui_labels.count("OK") == 1
    assert "Cancel" not in out.ui_labels  # moved to typed list


def test_apply_ir_heuristics_headings_to_sections_when_empty():
    from app.core.schemas_chat_authoring import ScreenshotHeadingItem

    base = ScreenshotContentModel(
        headings=[ScreenshotHeadingItem(level=2, text="Setup")],
        sections=[],
        confidence=0.8,
    )
    out = apply_ir_heuristics(base, parsed={}, image_bytes=b"\xff" * 5000, mime_type="image/jpeg")
    assert any(s.name == "Setup" for s in out.sections)


def test_image_context_from_parsed_blurry_model_warning():
    parsed = {
        "summary": "",
        "title": "",
        "confidence": 0.95,
        "uncertainty_warnings": ["Bottom of dialog cropped"],
        "visible_text": [],
    }
    ctx = _image_context_from_parsed(
        parsed,
        raw_model="test",
        provider="openai",
        image_bytes=MINI_PNG_1X1,
        mime_type="image/png",
    )
    assert ctx.structured.confidence < 0.95
    assert ctx.structured.uncertainty_warnings


def test_image_context_from_parsed_attaches_screenshot_type_classification():
    parsed = {
        "title": "Translation settings",
        "regions": [
            {"region_id": "r1", "region_type": "title", "text": "Translation settings", "confidence": 0.94},
            {
                "region_id": "r2",
                "region_type": "field_value_block",
                "field_values": [
                    {"field": "Language", "value": "French", "confidence": 0.88},
                    {"field": "Provider", "value": "Adobe Translation", "confidence": 0.86},
                ],
                "confidence": 0.87,
            },
        ],
        "settings_reference": {
            "title": "Translation settings",
            "tabs": ["General"],
            "sections": [{"title": "General", "confidence": 0.82}],
            "confidence": 0.83,
        },
        "confidence": 0.86,
    }
    ctx = _image_context_from_parsed(
        parsed,
        raw_model="test",
        provider="openai",
        image_bytes=MINI_PNG_1X1,
        mime_type="image/png",
        screenshot_context="Settings dialog for translation configuration",
    )
    assert ctx.structured.screenshot_type_classification is not None
    assert ctx.structured.screenshot_type_classification.screenshot_type == "settings_reference_screenshot"
    assert ctx.structured.screenshot_intent_route_decision is not None
    assert ctx.structured.screenshot_intent_route_decision.chosen_route == "reference_extraction_mode"


@pytest.mark.anyio
async def test_inspect_runs_multi_pass_and_returns_typed_stage_outputs(monkeypatch):
    import app.services.screenshot_understanding_service as su

    monkeypatch.setattr(su, "is_llm_available", lambda: True)
    monkeypatch.setattr(su, "_screenshot_vision_diagnostics", lambda: ("openai", None))

    async def fake_layout(self, **kwargs):
        return (
            {
                "regions": [
                    {
                        "region_id": "r1",
                        "layout_type": "title",
                        "bbox": {"x": 0.1, "y": 0.05, "width": 0.8, "height": 0.1},
                        "order_hint": 1,
                        "confidence": 0.93,
                    },
                    {
                        "region_id": "r2",
                        "layout_type": "field_value_block",
                        "bbox": {"x": 0.1, "y": 0.2, "width": 0.7, "height": 0.2},
                        "order_hint": 2,
                        "confidence": 0.84,
                    },
                ]
            },
            "test-vision-model",
        )

    async def fake_text(self, **kwargs):
        return (
            {
                "text_blocks": [
                    {"region_id": "r1", "raw_text": "Configure translation", "lines": ["Configure translation"], "confidence": 0.95},
                    {"region_id": "r2", "raw_text": "Language: French", "lines": ["Language: French"], "confidence": 0.86},
                ]
            },
            "test-vision-model",
        )

    async def fake_classify(self, **kwargs):
        return (
            {
                "semantic_blocks": [
                    {"region_id": "r1", "semantic_type": "title", "text": "Configure translation", "confidence": 0.95},
                    {
                        "region_id": "r2",
                        "semantic_type": "field_value_block",
                        "field_values": [{"field": "Language", "value": "French", "confidence": 0.88}],
                        "confidence": 0.86,
                    },
                ]
            },
            "test-vision-model",
        )

    monkeypatch.setattr(ScreenshotUnderstandingService, "_run_layout_pass", fake_layout)
    monkeypatch.setattr(ScreenshotUnderstandingService, "_run_text_pass", fake_text)
    monkeypatch.setattr(ScreenshotUnderstandingService, "_run_classification_pass", fake_classify)

    trace = await ScreenshotUnderstandingService().inspect(
        image=ChatAttachmentRef(
            asset_id="img-1",
            kind="image",
            filename="screen.png",
            mime_type="image/png",
            size_bytes=100,
            url="/asset/img-1",
        ),
        image_bytes=MINI_PNG_1X1,
        user_prompt="Generate a reference topic from this screenshot",
    )

    assert trace.model == "test-vision-model"
    assert len(trace.layout_regions) == 2
    assert len(trace.text_blocks) == 2
    assert len(trace.semantic_blocks) == 2
    assert [stage.pass_name for stage in trace.stages] == [
        "detect_layout_regions",
        "extract_text_per_block",
        "classify_semantic_blocks",
        "reconstruct_structure",
        "normalize_screenshot_content_model",
        "classify_screenshot_type",
        "route_screenshot_intent",
    ]
    assert trace.reading_order == ["r1", "r2"]
    assert trace.screenshot_type_classification is not None
    assert trace.screenshot_intent_route_decision is not None
    assert trace.classification_features is not None
    normalize_payload = trace.stages[4].payload
    assert normalize_payload["classification"]["screenshot_type"] == "settings_reference_screenshot"
    assert normalize_payload["features"]["field_value_pair_count"] == 1
    route_payload = trace.stages[-1].payload
    assert route_payload["chosenRoute"] == "reference_extraction_mode"


@pytest.mark.anyio
async def test_understand_attaches_trace_and_preserves_ambiguity(monkeypatch):
    import app.services.screenshot_understanding_service as su

    monkeypatch.setattr(su, "is_llm_available", lambda: True)
    monkeypatch.setattr(su, "_screenshot_vision_diagnostics", lambda: ("openai", None))

    async def fake_layout(self, **kwargs):
        return (
            {
                "regions": [
                    {"region_id": "r1", "layout_type": "paragraph", "order_hint": 1, "confidence": 0.5, "uncertain": True, "uncertainty_reason": "Right edge is cropped."}
                ]
            },
            "test-vision-model",
        )

    async def fake_text(self, **kwargs):
        return (
            {
                "text_blocks": [
                    {"region_id": "r1", "raw_text": "Partial acceptance...", "lines": ["Partial acceptance..."], "confidence": 0.48, "uncertain": True, "uncertainty_reason": "Text is incomplete."}
                ]
            },
            "test-vision-model",
        )

    async def fake_classify(self, **kwargs):
        return (
            {
                "semantic_blocks": [
                    {"region_id": "r1", "semantic_type": "unknown", "text": "Partial acceptance...", "confidence": 0.4, "uncertain": True, "uncertainty_reason": "Could be acceptance criteria or a note."}
                ]
            },
            "test-vision-model",
        )

    monkeypatch.setattr(ScreenshotUnderstandingService, "_run_layout_pass", fake_layout)
    monkeypatch.setattr(ScreenshotUnderstandingService, "_run_text_pass", fake_text)
    monkeypatch.setattr(ScreenshotUnderstandingService, "_run_classification_pass", fake_classify)

    ctx = await ScreenshotUnderstandingService().understand(
        image=ChatAttachmentRef(
            asset_id="img-2",
            kind="image",
            filename="screen.png",
            mime_type="image/png",
            size_bytes=100,
            url="/asset/img-2",
        ),
        image_bytes=MINI_PNG_1X1,
        user_prompt="Generate a topic from this screenshot",
    )

    assert ctx.understanding_trace is not None
    assert ctx.structured.uncertain_region_ids == ["r1"]
    assert any("acceptance criteria" in item.lower() or "note" in item.lower() for item in ctx.structured.uncertainty_warnings)


@pytest.mark.anyio
async def test_understand_recovers_procedural_model_from_procedural_blocks(monkeypatch):
    import app.services.screenshot_understanding_service as su

    monkeypatch.setattr(su, "is_llm_available", lambda: True)
    monkeypatch.setattr(su, "_screenshot_vision_diagnostics", lambda: ("openai", None))

    async def fake_layout(self, **kwargs):
        return (
            {
                "regions": [
                    {"region_id": "t", "layout_type": "title", "order_hint": 1, "confidence": 0.95},
                    {"region_id": "p", "layout_type": "paragraph", "order_hint": 2, "confidence": 0.8},
                    {"region_id": "s", "layout_type": "numbered_list", "order_hint": 3, "confidence": 0.9},
                    {"region_id": "n", "layout_type": "warning", "order_hint": 4, "confidence": 0.85},
                    {"region_id": "r", "layout_type": "paragraph", "order_hint": 5, "confidence": 0.82},
                    {"region_id": "c", "layout_type": "code", "order_hint": 6, "confidence": 0.8},
                ]
            },
            "test-vision-model",
        )

    async def fake_text(self, **kwargs):
        return (
            {
                "text_blocks": [
                    {"region_id": "t", "raw_text": "Create an output preset", "lines": ["Create an output preset"], "confidence": 0.95},
                    {"region_id": "p", "raw_text": "Before you begin\nMake sure you have map author permissions.", "lines": ["Before you begin", "Make sure you have map author permissions."], "confidence": 0.84},
                    {"region_id": "s", "raw_text": "1. Open Output Presets\n   1. Select PDF\n2. Click Save\nThe preset is added to the list.", "lines": ["1. Open Output Presets", "   1. Select PDF", "2. Click Save", "The preset is added to the list."], "confidence": 0.91},
                    {"region_id": "n", "raw_text": "Important: Existing presets are not overwritten.", "lines": ["Important: Existing presets are not overwritten."], "confidence": 0.86},
                    {"region_id": "r", "raw_text": "Result\nThe new preset appears in the output preset panel.", "lines": ["Result", "The new preset appears in the output preset panel."], "confidence": 0.83},
                    {"region_id": "c", "raw_text": "dita -i map.ditamap -f pdf", "lines": ["dita -i map.ditamap -f pdf"], "confidence": 0.81},
                ]
            },
            "test-vision-model",
        )

    async def fake_classify(self, **kwargs):
        return (
            {
                "semantic_blocks": [
                    {"region_id": "t", "semantic_type": "title", "text": "Create an output preset", "confidence": 0.95},
                    {"region_id": "p", "semantic_type": "heading", "text": "Before you begin", "heading_level": 2, "confidence": 0.84},
                    {"region_id": "s", "semantic_type": "numbered_list", "items": ["1. Open Output Presets", "   1. Select PDF", "2. Click Save", "The preset is added to the list."], "confidence": 0.91},
                    {"region_id": "n", "semantic_type": "warning", "text": "Existing presets are not overwritten.", "confidence": 0.86},
                    {"region_id": "r", "semantic_type": "heading", "text": "Result", "heading_level": 2, "confidence": 0.83},
                    {"region_id": "c", "semantic_type": "code", "text": "dita -i map.ditamap -f pdf", "confidence": 0.81},
                ],
                "ui_labels": ["Output Presets", "PDF", "Save"],
                "button_names": ["Save"],
            },
            "test-vision-model",
        )

    monkeypatch.setattr(ScreenshotUnderstandingService, "_run_layout_pass", fake_layout)
    monkeypatch.setattr(ScreenshotUnderstandingService, "_run_text_pass", fake_text)
    monkeypatch.setattr(ScreenshotUnderstandingService, "_run_classification_pass", fake_classify)

    ctx = await ScreenshotUnderstandingService().understand(
        image=ChatAttachmentRef(
            asset_id="img-proc",
            kind="image",
            filename="proc.png",
            mime_type="image/png",
            size_bytes=100,
            url="/asset/proc",
        ),
        image_bytes=MINI_PNG_1X1,
        user_prompt="Generate a task topic from this screenshot",
    )

    proc = ctx.structured.procedural_model
    assert proc is not None
    assert proc.title == "Create an output preset"
    assert proc.prerequisites
    assert proc.steps and len(proc.steps) == 2
    assert proc.steps[0].substeps and proc.steps[0].substeps[0].command == "Select PDF"
    assert "The preset is added to the list." in proc.steps[1].info_lines
    assert proc.notes and proc.notes[0].kind == "warning"
    assert proc.examples and "dita -i map.ditamap -f pdf" in proc.examples[0].text


@pytest.mark.anyio
async def test_understand_preserves_hierarchy_diagram_as_conceptual(monkeypatch):
    import app.services.screenshot_understanding_service as su

    monkeypatch.setattr(su, "is_llm_available", lambda: True)
    monkeypatch.setattr(su, "_screenshot_vision_diagnostics", lambda: ("openai", None))

    async def fake_layout(self, **kwargs):
        return (
            {
                "regions": [
                    {"region_id": "r-title", "layout_type": "title", "order_hint": 1, "confidence": 0.94},
                    {"region_id": "r-diagram", "layout_type": "unknown", "order_hint": 2, "confidence": 0.9},
                ]
            },
            "test-vision-model",
        )

    async def fake_text(self, **kwargs):
        return (
            {
                "text_blocks": [
                    {"region_id": "r-title", "raw_text": "DITA map hierarchy", "lines": ["DITA map hierarchy"], "confidence": 0.94},
                    {"region_id": "r-diagram", "raw_text": "DITA map\nConcepts\nTasks\nReference", "lines": ["DITA map", "Concepts", "Tasks", "Reference"], "confidence": 0.9},
                ]
            },
            "test-vision-model",
        )

    async def fake_classify(self, **kwargs):
        return (
            {
                "semantic_blocks": [
                    {"region_id": "r-title", "semantic_type": "title", "text": "DITA map hierarchy", "confidence": 0.94},
                    {"region_id": "r-diagram", "semantic_type": "unknown", "text": "DITA map Concepts Tasks Reference", "confidence": 0.9},
                ],
                "image_characterization": {
                    "primary_scene": "Hierarchy diagram of DITA content",
                    "author_intent_hypothesis": "Explain conceptual structure",
                },
                "embedded_graphics": [
                    {
                        "kind": "dita_map_hierarchy",
                        "label": "DITA map",
                        "root": {
                            "title": "DITA map",
                            "dita_type": "map_root",
                            "confidence": 0.92,
                            "children": [
                                {"title": "Concepts", "dita_type": "concept", "confidence": 0.9},
                                {"title": "Tasks", "dita_type": "task", "confidence": 0.89},
                                {"title": "Reference", "dita_type": "reference", "confidence": 0.88},
                            ],
                        },
                    }
                ],
            },
            "test-vision-model",
        )

    monkeypatch.setattr(ScreenshotUnderstandingService, "_run_layout_pass", fake_layout)
    monkeypatch.setattr(ScreenshotUnderstandingService, "_run_text_pass", fake_text)
    monkeypatch.setattr(ScreenshotUnderstandingService, "_run_classification_pass", fake_classify)

    ctx = await ScreenshotUnderstandingService().understand(
        image=ChatAttachmentRef(
            asset_id="img-hierarchy",
            kind="image",
            filename="hierarchy.png",
            mime_type="image/png",
            size_bytes=100,
            url="/asset/hierarchy",
        ),
        image_bytes=MINI_PNG_1X1,
        user_prompt="Generate a concept topic from this hierarchy diagram",
    )

    assert ctx.structured.diagram_interpretation is not None
    assert ctx.structured.diagram_interpretation.diagram_kind == "hierarchy"
    assert ctx.structured.diagram_interpretation.content_orientation == "conceptual"
    assert "Diagram:" in ctx.summary
    assert ctx.understanding_trace is not None
    assert ctx.understanding_trace.diagram_interpretation is not None


@pytest.mark.anyio
async def test_extract_delegates_to_singleton(monkeypatch):
    from app.core.schemas_chat_authoring import ChatImageContext

    import app.services.screenshot_understanding_service as su

    su._service = None

    async def fake_understand(self, **kwargs):
        return ChatImageContext(summary="ok", vision_provider="unit")

    monkeypatch.setattr(ScreenshotUnderstandingService, "understand", fake_understand)
    img = ChatAttachmentRef(
        asset_id="a",
        kind="image",
        filename="x.png",
        mime_type="image/png",
        size_bytes=10,
        url="/u",
    )
    ctx = await extract_screenshot_context(image=img, image_bytes=b"x", user_prompt="hi")
    assert ctx.summary == "ok"
    assert get_screenshot_understanding_service() is not None
