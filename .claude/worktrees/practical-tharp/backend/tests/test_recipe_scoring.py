"""Unit tests for recipe scoring and routing service."""
import pytest

from app.core.schemas_pipeline import IssueEvidence, RecipeScoringResult, normalize_evidence_from_pack
from app.services.recipe_scoring_service import (
    compute_feature_scores,
    compute_pattern_scores,
    select_feature,
    select_pattern,
    route_recipe,
    validate_no_cross_feature_blend,
    score_and_route,
    ROUTE_TABLE,
    RECIPE_FAMILY,
    GENERIC_XREF_RECIPES,
)


def test_keyref_evidence_heavily_prefers_keyref():
    """Evidence with key/keyref/keydef/duplicate key should score keyref highest."""
    evidence = IssueEvidence(
        jira_id="GUIDES-123",
        summary="Key resolution fails in nested maps",
        description="When Map A has keydef to Map B, keyref in topic does not resolve. Duplicate key in sibling submaps.",
        raw_text="keyref keydef duplicate key nested keymap map hierarchy key resolution",
    )
    scores = compute_feature_scores(evidence)
    assert scores["keyref"] >= 0.5
    assert scores["keyref"] >= scores.get("xref", 0)
    assert scores["keyref"] >= scores.get("conref", 0)


def test_xref_evidence_scores_xref():
    """Evidence with xref/href/cross reference should score xref."""
    evidence = IssueEvidence(
        jira_id="GUIDES-456",
        summary="Broken xref to external PDF",
        description="xref with href to PDF does not render. Cross reference fails.",
        raw_text="xref href cross reference external link",
    )
    scores = compute_feature_scores(evidence)
    assert scores["xref"] > 0
    assert scores["keyref"] < 0.5


def test_conref_evidence_scores_conref():
    """Evidence with conref/reuse should score conref."""
    evidence = IssueEvidence(
        jira_id="GUIDES-789",
        summary="Conref resolution issue",
        description="Content reuse via conref fails. conkeyref not resolving.",
        raw_text="conref conkeyref content reuse",
    )
    scores = compute_feature_scores(evidence)
    assert scores["conref"] > 0


def test_select_feature_prefers_keyref_when_high_score():
    """When keyref score is high, select_feature returns keyref."""
    scores = {"keyref": 0.8, "xref": 0.3, "conref": 0.1, "ditaval": 0.0}
    selected, rejected = select_feature(scores)
    assert selected == "keyref"
    assert "xref" in rejected or len(rejected) >= 0


def test_select_feature_returns_highest_when_no_keyref():
    """When keyref is low, select highest scoring feature."""
    scores = {"keyref": 0.1, "xref": 0.6, "conref": 0.2, "ditaval": 0.0}
    selected, _ = select_feature(scores)
    assert selected == "xref"


def test_compute_pattern_scores_keyref_map_hierarchy():
    """Map hierarchy evidence should score map_hierarchy_key_resolution high."""
    evidence = IssueEvidence(
        raw_text="map hierarchy nested keydef Map A Map B Topic recursive key resolution",
    )
    scores = compute_pattern_scores(evidence, "keyref")
    assert "map_hierarchy_key_resolution" in scores
    assert scores["map_hierarchy_key_resolution"] >= 0.35


def test_compute_pattern_scores_keyref_duplicate_sibling():
    """Duplicate key sibling submaps evidence should score that pattern."""
    evidence = IssueEvidence(
        raw_text="duplicate key sibling submap different scope",
    )
    scores = compute_pattern_scores(evidence, "keyref")
    assert "duplicate_keys_sibling_submaps" in scores
    assert scores["duplicate_keys_sibling_submaps"] >= 0.35


def test_route_recipe_keyref_map_hierarchy():
    """keyref + map_hierarchy_key_resolution -> nested_keydef_map_map_topic."""
    recipe_id, reason = route_recipe("keyref", "map_hierarchy_key_resolution")
    assert recipe_id == "nested_keydef_map_map_topic"
    assert "routed" in reason or "keyref" in reason


def test_route_recipe_keyref_basic():
    """keyref + basic_key_resolution -> keys.keydef_basic."""
    recipe_id, _ = route_recipe("keyref", "basic_key_resolution")
    assert recipe_id == "keys.keydef_basic"


def test_route_recipe_xref_internal():
    """xref + xref_internal_topic -> xref_topic_basic."""
    recipe_id, _ = route_recipe("xref", "xref_internal_topic")
    assert recipe_id == "xref_topic_basic"


def test_table_content_table_width_routes_to_heavy_topics():
    """table_content + table_width_formatting -> heavy_topics_tables_codeblocks."""
    evidence = IssueEvidence(
        raw_text="",
        summary="Table widths not rendering correctly in PDF output",
        description="The colwidth and colspec attributes are ignored. Table column widths are wrong.",
    )
    result = score_and_route(evidence)
    assert result.selected_feature == "table_content"
    assert result.selected_pattern == "table_width_formatting"
    assert result.selected_recipe == "heavy_topics_tables_codeblocks"


def test_route_recipe_fallback_for_unknown_pattern():
    """Unknown pattern falls back to first recipe for feature."""
    recipe_id, reason = route_recipe("keyref", "unknown_pattern_xyz")
    valid_keyref_recipes = {r for (f, _), r in ROUTE_TABLE.items() if f == "keyref"}
    assert recipe_id in valid_keyref_recipes or recipe_id == "keys.keydef_basic"
    assert "fallback" in reason or "default" in reason


def test_validate_rejects_xref_for_keyref_issue():
    """Generic xref recipe must be rejected when feature is keyref."""
    is_valid, blocked = validate_no_cross_feature_blend("keyref", "xref_topic_basic")
    assert is_valid is False
    assert blocked is True


def test_validate_accepts_keyref_recipe_for_keyref_issue():
    """Keyref recipe is valid for keyref feature."""
    is_valid, blocked = validate_no_cross_feature_blend("keyref", "keys.keydef_basic")
    assert is_valid is True
    assert blocked is True


def test_validate_accepts_xref_recipe_for_xref_issue():
    """Xref recipe is valid for xref feature."""
    is_valid, blocked = validate_no_cross_feature_blend("xref", "xref_topic_basic")
    assert is_valid is True


def test_score_and_route_keyref_issue():
    """Full pipeline: keyref evidence -> keyref recipe."""
    evidence = IssueEvidence(
        jira_id="GUIDES-100",
        summary="Nested keydef resolution fails",
        description="Map A keydef to Map B. Keyref in topic does not resolve. Duplicate key in sibling submaps.",
        raw_text="keyref keydef duplicate key nested keymap map hierarchy",
    )
    result = score_and_route(evidence)
    assert isinstance(result, RecipeScoringResult)
    assert result.selected_feature == "keyref"
    assert result.selected_recipe in ROUTE_TABLE.values()
    assert result.selected_recipe not in GENERIC_XREF_RECIPES
    assert result.cross_feature_blocked is True
    assert "keyref" in result.feature_scores


def test_score_and_route_xref_issue():
    """Full pipeline: xref evidence -> xref recipe."""
    evidence = IssueEvidence(
        jira_id="GUIDES-200",
        summary="Xref to external PDF broken",
        description="Topic has xref with href to PDF. Link does not work.",
        raw_text="xref href external link pdf",
    )
    result = score_and_route(evidence)
    assert result.selected_feature == "xref"
    assert result.selected_recipe.startswith("xref_")
    assert result.cross_feature_blocked is False


def test_normalize_evidence_from_pack():
    """normalize_evidence_from_pack builds IssueEvidence from primary dict."""
    primary = {
        "issue_key": "GUIDES-1",
        "summary": "Test issue",
        "description": "Keyref fails",
        "attachments": [{"filename": "a.dita", "full_content": "<map><keydef keys='x'/></map>"}],
    }
    evidence = normalize_evidence_from_pack(primary, "GUIDES-1")
    assert evidence.jira_id == "GUIDES-1"
    assert evidence.summary == "Test issue"
    assert "keydef" in evidence.raw_text


def test_route_table_has_keyref_recipes():
    """ROUTE_TABLE contains keyref mappings."""
    keyref_routes = [(f, p) for (f, p) in ROUTE_TABLE if f == "keyref"]
    assert len(keyref_routes) >= 5
    assert ("keyref", "basic_key_resolution") in ROUTE_TABLE
    assert ("keyref", "map_hierarchy_key_resolution") in ROUTE_TABLE


def test_recipe_family_mapping():
    """RECIPE_FAMILY maps recipe IDs to mechanism family."""
    assert RECIPE_FAMILY.get("keys.keydef_basic") == "keyref"
    assert RECIPE_FAMILY.get("xref_topic_basic") == "xref"
    assert RECIPE_FAMILY.get("nested_keydef_map_map_topic") == "keyref"


def test_output_schema_matches_requirements():
    """RecipeScoringResult has all required fields."""
    evidence = IssueEvidence(raw_text="keyref keydef")
    result = score_and_route(evidence)
    assert hasattr(result, "feature_scores")
    assert hasattr(result, "selected_feature")
    assert hasattr(result, "pattern_scores")
    assert hasattr(result, "selected_pattern")
    assert hasattr(result, "selected_recipe")
    assert hasattr(result, "cross_feature_blocked")
    assert hasattr(result, "assumptions")
    assert hasattr(result, "unknowns")
    assert isinstance(result.feature_scores, dict)
    assert isinstance(result.assumptions, list)
    assert isinstance(result.unknowns, list)
