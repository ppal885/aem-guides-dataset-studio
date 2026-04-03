"""Golden tests: keyref Jira issue -> keyref recipe, not xref."""
import pytest

from app.core.schemas_pipeline import IssueEvidence, normalize_evidence_from_pack
from app.services.recipe_scoring_service import score_and_route, GENERIC_XREF_RECIPES


GOLDEN_KEYREF_JIRA = {
    "issue_key": "GUIDES-42533",
    "summary": "Key resolution fails when Map A references Map B",
    "description": """
Issue Summary:
When Map A has keydef pointing to Map B (ditamap), and Map B has keydefs to Topic C,
the keyref in Topic D does not resolve when Map A is opened as context in AEM Guides Author.

Representative Sample:
<!-- Map A -->
<map id="map_a">
  <keydef keys="staticKeyMap" href="keymap.ditamap" format="ditamap"/>
  <topicref href="../topics/consumer_overview.dita"/>
</map>
<!-- Map B (keymap.ditamap) -->
<map id="keymap">
  <keydef keys="productName" topicmeta><keyword>Product</keyword></keydef>
  <keydef keys="keywordFile" href="../topics/static_content.dita"/>
</map>

Steps to Reproduce:
1. Open Map A in AEM Guides Author
2. Open consumer topic that uses keyref="productName"
3. Key does not resolve (expected: resolves to keyword)
""",
    "attachments": [],
}


def test_golden_keyref_issue_returns_keyref_recipe():
    """Sample Jira about nested key resolution must return keyref recipe, not xref."""
    evidence = normalize_evidence_from_pack(GOLDEN_KEYREF_JIRA, "GUIDES-42533")
    result = score_and_route(evidence)

    assert result.selected_feature == "keyref"
    assert result.selected_recipe not in GENERIC_XREF_RECIPES
    assert "keydef" in result.selected_recipe or "keyref" in result.selected_recipe or "nested" in result.selected_recipe
    assert result.cross_feature_blocked is True


def test_golden_keyref_issue_selects_map_hierarchy_or_nested():
    """Nested key/map hierarchy evidence should route to nested_keydef or keyscope recipe."""
    evidence = IssueEvidence(
        jira_id="GUIDES-100",
        summary="Nested keydef resolution fails",
        raw_text="Map A Map B Topic keydef keyref nested keymap map hierarchy recursive key resolution",
    )
    result = score_and_route(evidence)

    assert result.selected_feature == "keyref"
    assert result.selected_recipe in (
        "nested_keydef_map_map_topic",
        "keys.keyscope_nested_resolution",
        "keys.keydef_basic",
        "keys.keyscope_shadow_2level",
    )
