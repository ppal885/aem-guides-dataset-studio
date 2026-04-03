"""Tests for glossary abbreviation dataset recipe."""
import json

import pytest

from app.generator.glossary_abbrev import generate_dita_glossary_abbrev_dataset
from app.jobs.schemas import DatasetConfig


@pytest.fixture
def config():
    return DatasetConfig(name="test", seed="test-seed", root_folder="/tmp", recipes=[])


def test_glossary_abbrev_generates_valid_structure(config):
    """Generator produces glossary-map.ditamap, glossentry files, usage topics, manifest."""
    files = generate_dita_glossary_abbrev_dataset(config, "/tmp")
    assert any("glossary-map.ditamap" in k for k in files)
    assert any("api.glossentry" in k for k in files)
    assert any("aem.glossentry" in k for k in files)
    assert any("topic_glossary_usage_01.dita" in k for k in files)
    assert any("topic_glossary_usage_10.dita" in k for k in files)
    assert any("dataset_manifest.json" in k for k in files)
    assert any("dita_glossary_dataset" in k for k in files)


def test_glossary_abbrev_entries_have_glossterm_and_abbreviation(config):
    """Glossentry files contain glossterm, glossdef, glossAbbreviation."""
    files = generate_dita_glossary_abbrev_dataset(config, "/tmp")
    gloss_keys = [k for k in files if k.endswith(".glossentry")]
    assert len(gloss_keys) >= 15
    for key in gloss_keys[:3]:
        content = files[key].decode("utf-8")
        assert "glossterm" in content
        assert "glossdef" in content
        assert "glossAbbreviation" in content or "glossalt" in content.lower()


def test_glossary_abbrev_usage_topics_have_term_and_abbreviated_form(config):
    """Usage topics contain term keyref and abbreviated-form keyref."""
    files = generate_dita_glossary_abbrev_dataset(config, "/tmp")
    usage_keys = [k for k in files if "topic_glossary_usage_" in k and k.endswith(".dita")]
    assert len(usage_keys) >= 10
    for key in usage_keys[:3]:
        content = files[key].decode("utf-8")
        assert 'keyref="' in content
        assert "term" in content or "abbreviated-form" in content


def test_glossary_abbrev_manifest_valid(config):
    """Dataset manifest contains expected fields."""
    files = generate_dita_glossary_abbrev_dataset(config, "/tmp")
    manifest_key = next((k for k in files if "dataset_manifest.json" in k), None)
    assert manifest_key
    manifest = json.loads(files[manifest_key].decode("utf-8"))
    assert manifest.get("recipe_name") == "dita_glossary_abbrev_dataset_recipe"
    assert manifest.get("dataset_name") == "dita_glossary_dataset"
    assert manifest.get("entry_count") == 15
    assert manifest.get("usage_topic_count") == 10
    assert manifest.get("dita_feature") == "glossary_abbrev"
    assert manifest["stats"].get("entry_count") == 15
    assert manifest["stats"].get("usage_topic_count") == 10


def test_glossary_abbrev_custom_counts(config):
    """Generator respects entry_count and usage_topic_count parameters."""
    files = generate_dita_glossary_abbrev_dataset(
        config, "/tmp", entry_count=5, usage_topic_count=3
    )
    gloss_keys = [k for k in files if k.endswith(".glossentry")]
    usage_keys = [k for k in files if "topic_glossary_usage_" in k and k.endswith(".dita")]
    assert len(gloss_keys) == 5
    assert len(usage_keys) == 3


def test_glossary_abbrev_map_has_keydefs_to_glossentries(config):
    """Glossary map references glossentry files with keys."""
    files = generate_dita_glossary_abbrev_dataset(config, "/tmp")
    map_key = next((k for k in files if "glossary-map.ditamap" in k), None)
    assert map_key
    content = files[map_key].decode("utf-8")
    assert "topicref" in content
    assert "keys=" in content or 'keys="' in content
    assert ".glossentry" in content
