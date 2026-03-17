"""Tests for deterministic recipe router."""
import pytest

from app.services.recipe_router import route_recipe
from app.services.recipe_scoring_service import ROUTE_TABLE


def test_route_keyref_map_hierarchy():
    """keyref + map_hierarchy_key_resolution -> nested_keydef_map_map_topic."""
    result = route_recipe("keyref", "map_hierarchy_key_resolution")
    assert result.selected_recipe == "nested_keydef_map_map_topic"
    assert result.selected_feature == "keyref"
    assert "routed" in result.route_reason


def test_route_keyref_basic():
    """keyref + basic_key_resolution -> keys.keydef_basic."""
    result = route_recipe("keyref", "basic_key_resolution")
    assert result.selected_recipe == "keys.keydef_basic"


def test_route_xref_internal():
    """xref + xref_internal_topic -> xref_topic_basic."""
    result = route_recipe("xref", "xref_internal_topic")
    assert result.selected_recipe == "xref_topic_basic"


def test_route_table_has_keyref_routes():
    """ROUTE_TABLE contains keyref mappings."""
    keyref_routes = [(f, p) for (f, p) in ROUTE_TABLE if f == "keyref"]
    assert len(keyref_routes) >= 5
