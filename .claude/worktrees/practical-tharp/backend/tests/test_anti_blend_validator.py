"""Tests for anti-blending validator."""
import pytest

from app.services.anti_blend_validator import validate_recipe_family_match, ValidationResult


def test_rejects_xref_for_keyref_issue():
    """Generic xref recipe must be rejected when feature is keyref."""
    result = validate_recipe_family_match("keyref", "xref_topic_basic")
    assert result.valid is False
    assert "mismatch" in result.reason.lower() or "family" in result.reason.lower()


def test_accepts_keyref_recipe_for_keyref_issue():
    """Keyref recipe is valid for keyref feature."""
    result = validate_recipe_family_match("keyref", "keys.keydef_basic")
    assert result.valid is True


def test_accepts_xref_recipe_for_xref_issue():
    """Xref recipe is valid for xref feature."""
    result = validate_recipe_family_match("xref", "xref_topic_basic")
    assert result.valid is True


def test_accepts_nested_keydef_for_keyref():
    """nested_keydef_map_map_topic is valid for keyref."""
    result = validate_recipe_family_match("keyref", "nested_keydef_map_map_topic")
    assert result.valid is True


def test_accepts_conref_for_conref_issue():
    """Conref recipe is valid for conref feature."""
    result = validate_recipe_family_match("conref", "conref_pack")
    assert result.valid is True
