"""Tests for conref in title dataset recipe."""
import json
import tempfile
from pathlib import Path

import pytest

from app.generator.conref_title import (
    generate_dita_conref_title_dataset,
    generate_variable_topic,
    generate_conref_topic,
    validate_dita_structure,
    write_dataset_files,
)
from app.jobs.schemas import DatasetConfig


@pytest.fixture
def config():
    return DatasetConfig(name="test", seed="test-seed", root_folder="/tmp", recipes=[])


def test_conref_title_generates_valid_structure(config):
    """Generator produces variables.dita, topic_1 through topic_10, and manifest."""
    files = generate_dita_conref_title_dataset(config, "/tmp")
    assert any("variables.dita" in k for k in files)
    assert any("topic_1.dita" in k for k in files)
    assert any("topic_10.dita" in k for k in files)
    assert any("dataset_manifest.json" in k for k in files)
    assert any("dita_conref_titles" in k for k in files)


def test_conref_title_variables_topic_has_ph_elements(config):
    """Variables topic contains ph elements with build_version, release_name, product_name."""
    files = generate_dita_conref_title_dataset(config, "/tmp")
    vars_key = next((k for k in files if "variables.dita" in k), None)
    assert vars_key
    content = files[vars_key].decode("utf-8")
    assert "build_version" in content
    assert "release_name" in content
    assert "product_name" in content
    assert "<ph " in content
    assert "Build-2026" in content or "Release-A" in content or "AEM-Guides" in content


def test_conref_title_target_topics_have_conref_in_title(config):
    """Target topics have title conref attribute pointing to variables."""
    files = generate_dita_conref_title_dataset(config, "/tmp")
    topic_keys = [k for k in files if "topic_" in k and k.endswith(".dita")]
    assert len(topic_keys) >= 10
    for key in topic_keys[:5]:
        content = files[key].decode("utf-8")
        assert 'conref="' in content
        assert "variables.dita" in content
        assert "build_version" in content or "release_name" in content or "product_name" in content
        assert "<title " in content
        assert "Topic demonstrating title conref resolution" in content


def test_conref_title_manifest_valid(config):
    """Dataset manifest contains dataset_name, generated_topics, dita_feature, purpose."""
    files = generate_dita_conref_title_dataset(config, "/tmp")
    manifest_key = next((k for k in files if "dataset_manifest.json" in k), None)
    assert manifest_key
    manifest = json.loads(files[manifest_key].decode("utf-8"))
    assert manifest.get("recipe_name") == "dita_conref_title_dataset_recipe"
    assert manifest.get("dataset_name") == "dita_conref_title_dataset"
    assert manifest.get("generated_topics") == 10
    assert manifest.get("dita_feature") == "conref_title"
    assert manifest.get("purpose") == "AEM Guides conref resolution testing"
    assert manifest["stats"].get("topic_count") == 10
    assert manifest["stats"].get("variable_count") == 3


def test_conref_title_custom_topic_count(config):
    """Generator respects topic_count parameter."""
    files = generate_dita_conref_title_dataset(config, "/tmp", topic_count=5)
    topic_keys = [k for k in files if "topic_" in k and k.endswith(".dita") and "variables" not in k]
    assert len(topic_keys) == 5


def test_validate_dita_structure_valid(config):
    """validate_dita_structure returns no errors for valid dataset."""
    files = generate_dita_conref_title_dataset(config, "/tmp", topic_count=3)
    errors = validate_dita_structure(files)
    assert errors == []


def test_validate_dita_structure_detects_duplicate_id(config):
    """validate_dita_structure detects duplicate IDs."""
    files = generate_dita_conref_title_dataset(config, "/tmp", topic_count=2)
    # Corrupt: add duplicate id in one topic
    key = next(k for k in files if "topic_1" in k and k.endswith(".dita"))
    content = files[key].decode("utf-8").replace('id="topic_001"', 'id="variables_topic"')
    files[key] = content.encode("utf-8")
    errors = validate_dita_structure(files)
    assert any("Duplicate ID" in e for e in errors)


def test_write_dataset_files(config):
    """write_dataset_files writes all files to output directory."""
    files = generate_dita_conref_title_dataset(config, "dataset", topic_count=2)
    with tempfile.TemporaryDirectory() as tmp:
        write_dataset_files(files, tmp)
        base = Path(tmp)
        out_dir = base / "dataset" / "dita_conref_titles"
        assert (out_dir / "variables.dita").exists()
        assert (out_dir / "topic_1.dita").exists()
        assert (out_dir / "dataset_manifest.json").exists()


def test_generate_variable_topic(config):
    """generate_variable_topic produces topic with ph elements."""
    topic = generate_variable_topic(config, "vars_001", [("ph1", "Content1"), ("ph2", "Content2")])
    assert topic.get("id") == "vars_001"
    body = topic.find("body")
    assert body is not None
    phs = list(body.iter("ph"))
    assert len(phs) == 2
    assert phs[0].get("id") == "ph1" and phs[0].text == "Content1"


def test_generate_conref_topic(config):
    """generate_conref_topic produces topic with title conref."""
    topic = generate_conref_topic(
        config, "t001", "build_version", "variables.dita", "vars_001"
    )
    assert topic.get("id") == "t001"
    title = topic.find("title")
    assert title is not None
    assert title.get("conref") == "variables.dita#vars_001/build_version"


def test_ai_executor_can_run_recipe(config):
    """AI executor can run dita_conref_title_dataset_recipe (AI-generated dataset flow)."""
    from app.services.ai_executor_service import execute_plan
    from app.core.schemas_ai import GeneratorInvocationPlan, SelectedRecipe

    plan = GeneratorInvocationPlan(
        recipes=[
            SelectedRecipe(
                recipe_id="dita_conref_title_dataset_recipe",
                params={"topic_count": 3},
                evidence_used=[],
            ),
        ],
        selection_rationale=[],
    )
    with tempfile.TemporaryDirectory() as tmp:
        result = execute_plan(plan, tmp, seed="ai-test")
        warnings = result.get("warnings", [])
        bad = [w for w in warnings if "dita_conref_title" in w and ("Unknown" in w or "failed" in w)]
        assert not bad, f"Recipe should run: {bad}"
        out_dir = Path(tmp)
        assert (out_dir / "dita_conref_titles" / "variables.dita").exists()
        assert (out_dir / "dita_conref_titles" / "topic_1.dita").exists()
        assert (out_dir / "dita_conref_titles" / "dataset_manifest.json").exists()
