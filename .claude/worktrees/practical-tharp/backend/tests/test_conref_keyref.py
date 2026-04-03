"""Tests for conref + keyref dataset recipe."""
import json

import pytest

from app.generator.conref_keyref import (
    generate_dita_conref_keyref_dataset,
    validate_dita_structure,
)
from app.jobs.schemas import DatasetConfig


@pytest.fixture
def config():
    return DatasetConfig(name="test", seed="test-seed", root_folder="/tmp", recipes=[])


def test_conref_keyref_generates_valid_structure(config):
    """Generator produces keydef-map.ditamap, variables.dita, topic_conref_keyref_01-15, manifest."""
    files = generate_dita_conref_keyref_dataset(config, "/tmp")
    assert any("keydef-map.ditamap" in k for k in files)
    assert any("variables.dita" in k for k in files)
    assert any("topic_conref_keyref_01.dita" in k for k in files)
    assert any("topic_conref_keyref_15.dita" in k for k in files)
    assert any("dataset_manifest.json" in k for k in files)
    assert any("dita_conref_keyref_dataset" in k for k in files)


def test_conref_keyref_variables_topic_has_ph_elements(config):
    """Variables topic contains ph elements for product_name, release_name."""
    files = generate_dita_conref_keyref_dataset(config, "/tmp")
    vars_key = next((k for k in files if "variables.dita" in k), None)
    assert vars_key
    content = files[vars_key].decode("utf-8")
    assert "product_name" in content
    assert "release_name" in content
    assert "<ph " in content
    assert "AEM Guides" in content or "Build-2026" in content


def test_conref_keyref_topics_have_conref_or_keyref(config):
    """Target topics have conref or keyref attributes."""
    files = generate_dita_conref_keyref_dataset(config, "/tmp")
    topic_keys = [k for k in files if "topic_conref_keyref_" in k and k.endswith(".dita")]
    assert len(topic_keys) >= 15
    for key in topic_keys[:5]:
        content = files[key].decode("utf-8")
        assert 'conref="' in content or 'keyref="' in content


def test_conref_keyref_manifest_valid(config):
    """Dataset manifest contains expected fields."""
    files = generate_dita_conref_keyref_dataset(config, "/tmp")
    manifest_key = next((k for k in files if "dataset_manifest.json" in k), None)
    assert manifest_key
    manifest = json.loads(files[manifest_key].decode("utf-8"))
    assert manifest.get("recipe_name") == "dita_conref_keyref_dataset_recipe"
    assert manifest.get("dataset_name") == "dita_conref_keyref_dataset"
    assert manifest.get("generated_topics") == 15
    assert manifest.get("dita_feature") == "conref_keyref"
    assert manifest["stats"].get("topic_count") == 15
    assert manifest["stats"].get("variable_count") == 2


def test_conref_keyref_custom_topic_count(config):
    """Generator respects topic_count parameter."""
    files = generate_dita_conref_keyref_dataset(config, "/tmp", topic_count=5)
    topic_keys = [k for k in files if "topic_conref_keyref_" in k and k.endswith(".dita")]
    assert len(topic_keys) == 5


def test_conref_keyref_validate_dita_structure_valid(config):
    """validate_dita_structure returns no errors for valid dataset."""
    files = generate_dita_conref_keyref_dataset(config, "/tmp", topic_count=3)
    errors = validate_dita_structure(files)
    assert errors == []
