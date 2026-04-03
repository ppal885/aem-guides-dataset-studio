"""Integration tests for media_rich_content recipe execution."""
import pytest
import tempfile
from pathlib import Path

from app.core.schemas_ai import GeneratorInvocationPlan, SelectedRecipe
from app.generator.recipe_manifest import discover_recipe_specs
from app.services.ai_executor_service import execute_plan


def test_media_rich_content_is_discoverable():
    """Verify media_rich_content is in discovered recipe specs."""
    specs = discover_recipe_specs()
    media_specs = [s for s in specs if s.id == "media_rich_content"]
    assert len(media_specs) == 1, "media_rich_content should be discoverable"
    assert media_specs[0].module == "app.generator.media"
    assert media_specs[0].function == "generate_media_rich_dataset"


def test_execute_plan_media_rich_content_produces_files():
    """Execute plan with media_rich_content and assert output contains topics, assets, map."""
    plan = GeneratorInvocationPlan(
        recipes=[
            SelectedRecipe(
                recipe_id="media_rich_content",
                params={"topic_count": 2, "images_per_topic": 1, "generate_images": True},
                evidence_used=["image_reference", "media_rich"],
            )
        ],
        selection_rationale=["override:feedback_keyword:insert image and multimedia"],
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        result = execute_plan(plan, tmpdir, seed="test-media-seed")
        assert "media_rich_content" in result["recipes_executed"]
        assert not result["warnings"], f"Unexpected warnings: {result['warnings']}"
        scenario_path = Path(result["scenario_dir"])
        topics_dir = scenario_path / "topics" / "pool"
        assets_dir = scenario_path / "assets" / "images"
        map_files = list(scenario_path.glob("*.ditamap"))
        assert topics_dir.exists(), f"Expected topics/pool dir at {topics_dir}"
        assert list(topics_dir.glob("*.dita")), "Expected at least one .dita topic"
        assert assets_dir.exists(), f"Expected assets/images dir at {assets_dir}"
        assert list(assets_dir.glob("*.png")), "Expected at least one placeholder image"
        assert map_files, f"Expected .ditamap file in {scenario_path}"
