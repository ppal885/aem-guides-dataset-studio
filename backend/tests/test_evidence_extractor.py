"""Tests for evidence extractor."""
from app.utils.evidence_extractor import extract_evidence_context


def test_extract_includes_representative_sample():
    """Representative Sample and keydef/Map A should be in context."""
    primary = {
        "summary": "[SLA3] Nested keydefs (Map to Map to Topic) not resolved",
        "description": (
            "Customer Context\nIMS Org ID: D10F27705ED7F5130A495C99\n\n"
            "Issue Summary\n"
            "Authors cannot see or use keys defined through nested keydef chains. "
            "Map A -> Map B -> Topic C fails in Authoring modes.\n\n"
            "Steps to Reproduce\n"
            "Create a ditamap (Map A) with keydef pointing to Map B.\n\n"
            "Representative Sample\n"
            "<!-- Map A -->\n"
            "<map>\n"
            '  <keydef keys="staticKeyMap" href="kdp610_keymap.ditamap" format="ditamap"/>\n'
            '  <topicref href="topics/kdp_overview_whatsnew.dita"/>\n'
            "</map>\n"
            "Support Investigation\n"
            "Confirmed customer content is valid.\n"
        ),
    }
    ctx = extract_evidence_context(primary)
    assert "Representative Sample" in ctx
    assert "keydef" in ctx
    assert "Map A" in ctx
    assert "staticKeyMap" in ctx
    assert len(ctx) > 400


def test_extract_summary_only_when_no_description():
    """When description is empty, return summary."""
    primary = {"summary": "Nested keydefs not resolved", "description": ""}
    ctx = extract_evidence_context(primary)
    assert ctx == "Nested keydefs not resolved"
