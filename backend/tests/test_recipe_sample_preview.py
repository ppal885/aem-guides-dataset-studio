"""Tests for generator-backed recipe catalog samples."""

from app.services.recipe_sample_preview_service import generate_recipe_sample_preview, get_recipe_sample_preview
from app.generator.recipe_manifest import discover_recipe_specs


def _spec_by_id(recipe_id: str):
    for spec in discover_recipe_specs():
        if spec.id == recipe_id:
            return spec
    raise AssertionError(f"Missing spec: {recipe_id}")


def test_audience_platform_basic_sample_has_real_attributes():
    preview = generate_recipe_sample_preview(_spec_by_id("metadata.audience_platform_basic"))
    assert preview is not None
    assert 'audience="admin"' in preview.xml
    assert 'platform="windows"' in preview.xml
    assert "Representative output for this recipe" not in preview.xml


def test_choicetable_tasks_sample_has_choicetable():
    preview = generate_recipe_sample_preview(_spec_by_id("choicetable_tasks"))
    assert preview is not None
    assert "choicetable" in preview.xml
    assert "Representative output for this recipe" not in preview.xml


def test_get_recipe_sample_preview_cached_for_audience_platform():
    sample = get_recipe_sample_preview("metadata.audience_platform_basic")
    assert sample is not None
    xml, summary = sample
    assert "Audience Platform" in xml
    assert "metadata.audience_platform_basic" in summary
