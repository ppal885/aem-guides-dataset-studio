"""Tests for structured settings / form screenshot extraction (no live vision calls)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from app.core.schemas_chat_authoring import (
    ChatDitaGenerationOptions,
    ChatImageContext,
    ChatSemanticPlan,
)
from app.services.dita_topic_draft import build_topic_draft, infer_topic_type, merge_structured_into_plan
from app.services.dita_topic_serializer import serialize_topic_draft
from app.services.screenshot_understanding_service import (
    _build_structured_from_parsed,
    _derive_settings_reference_model,
    _parse_settings_reference_payload,
    _settings_reference_nonempty,
)


def test_parse_settings_reference_payload_full():
    raw = {
        "title": "Output Preset",
        "tabs": ["General", "Advanced", "PDF"],
        "active_tab": "General",
        "helper_text": ["Changes apply after you save the preset."],
        "sections": [
            {
                "title": "PDF layout",
                "tab": "PDF",
                "description": ["Controls page size and margins."],
                "fields": [
                    {
                        "label": "Page size",
                        "value": "A4",
                        "control_type": "dropdown",
                        "helper_text": ["ISO standard paper size."],
                        "options": [
                            {"label": "A4", "selected": True},
                            {"label": "Letter", "selected": False},
                        ],
                    },
                    {
                        "label": "Embed fonts",
                        "value": "On",
                        "control_type": "checkbox",
                        "options": [{"label": "Embed fonts", "selected": True}],
                    },
                ],
                "parameter_tables": [
                    {
                        "caption": "Margin presets",
                        "headers": ["Name", "Top", "Bottom"],
                        "rows": [["Normal", "1in", "1in"], ["Narrow", "0.5in", "0.5in"]],
                    }
                ],
            }
        ],
        "confidence": 0.88,
    }
    model = _parse_settings_reference_payload(raw)
    assert model is not None
    assert _settings_reference_nonempty(model)
    assert model.tabs == ["General", "Advanced", "PDF"]
    assert model.active_tab == "General"
    assert len(model.sections) == 1
    sec = model.sections[0]
    assert sec.title == "PDF layout"
    assert sec.tab == "PDF"
    assert len(sec.fields) == 2
    assert sec.fields[0].control_type == "dropdown"
    assert len(sec.fields[0].options) == 2
    assert sec.fields[0].options[0].selected is True
    assert len(sec.parameter_tables) == 1
    assert sec.parameter_tables[0].headers == ["Name", "Top", "Bottom"]


def test_derive_settings_from_regions_groups_by_heading():
    regions = [
        {
            "region_id": "h1",
            "region_type": "heading",
            "text": "Repository",
            "confidence": 0.9,
        },
        {
            "region_id": "f1",
            "region_type": "field_value_block",
            "field_values": [
                {"field": "Path", "value": "/content/dam", "confidence": 0.85},
                {"field": "Read-only", "value": "[x] Enabled", "confidence": 0.8},
            ],
            "confidence": 0.82,
        },
        {
            "region_id": "h2",
            "region_type": "heading",
            "text": "Indexing",
            "confidence": 0.88,
        },
        {
            "region_id": "t1",
            "region_type": "table",
            "label": "Solr fields",
            "table_rows": [["Field", "Type"], ["id", "string"], ["path", "text"]],
            "confidence": 0.77,
        },
    ]
    parsed = {"regions": regions, "reading_order": ["h1", "f1", "h2", "t1"]}
    structured = _build_structured_from_parsed(parsed)
    assert structured.settings_reference_model is not None
    sm = structured.settings_reference_model
    assert sm is not None
    assert len(sm.sections) >= 2
    titles = [s.title for s in sm.sections]
    assert any("Repository" in t for t in titles)
    assert any("Indexing" in t for t in titles)
    repo = next(s for s in sm.sections if "Repository" in s.title)
    assert len(repo.fields) >= 1
    assert repo.fields[0].label == "Path"
    idx = next(s for s in sm.sections if "Indexing" in s.title)
    assert len(idx.parameter_tables) == 1


def test_reference_serialization_uses_properties_not_flat_paragraphs():
    parsed = {
        "title": "Admin Console",
        "settings_reference": {
            "tabs": ["Settings", "Security"],
            "active_tab": "Settings",
            "sections": [
                {
                    "title": "Session",
                    "fields": [
                        {"label": "Timeout (min)", "value": "30", "control_type": "text", "helper_text": ["Idle timeout."]}
                    ],
                }
            ],
        },
    }
    structured = _build_structured_from_parsed(parsed)
    plan = ChatSemanticPlan(
        title="Admin Console",
        dita_type="reference",
        shortdesc="Configuration reference from UI.",
        sections=[],
    )
    merged = merge_structured_into_plan(plan, structured)
    ctx = ChatImageContext(structured=structured)
    draft = build_topic_draft(plan=merged, image_context=ctx)
    assert draft.settings_reference_model is not None
    xml = serialize_topic_draft(
        draft,
        profile=None,
        options=ChatDitaGenerationOptions(),
        ui_label_hints=set(),
    )
    assert "<properties>" in xml
    assert "<proptype>" in xml and "Timeout" in xml
    assert "<propvalue>" in xml and "30" in xml
    assert "<refsyn>" in xml
    root = ET.fromstring(xml)
    assert root.tag == "reference"


def test_infer_topic_type_prefers_reference_for_settings_ir():
    structured = _build_structured_from_parsed(
        {
            "regions": [],
            "settings_reference": {
                "sections": [{"title": "Options", "fields": [{"label": "A", "value": "1", "control_type": "text"}]}],
            },
        }
    )
    ctx = ChatImageContext(summary="x", structured=structured)
    t = infer_topic_type(options=ChatDitaGenerationOptions(), user_prompt="", image_context=ctx, profile=None)
    assert t == "reference"
