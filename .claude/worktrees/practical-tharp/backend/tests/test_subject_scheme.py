"""Tests for subject scheme dataset recipe."""
import json

import pytest

from app.generator.subject_scheme import generate_dita_subject_scheme_dataset
from app.jobs.schemas import DatasetConfig


@pytest.fixture
def config():
    return DatasetConfig(name="test", seed="test-seed", root_folder="/tmp", recipes=[])


def test_subject_scheme_generates_valid_structure(config):
    """Generator produces subject-scheme.ditamap, root-map.ditamap, valid/invalid topics, manifest."""
    files = generate_dita_subject_scheme_dataset(config, "/tmp")
    assert any("subject-scheme.ditamap" in k for k in files)
    assert any("root-map.ditamap" in k for k in files)
    assert any("topic_valid_01.dita" in k for k in files)
    assert any("topic_valid_10.dita" in k for k in files)
    assert any("topic_invalid_01.dita" in k for k in files)
    assert any("topic_invalid_10.dita" in k for k in files)
    assert any("dataset_manifest.json" in k for k in files)
    assert any("dita_subject_scheme_dataset" in k for k in files)


def test_subject_scheme_valid_topics_use_valid_audience(config):
    """Valid topics use audience values from subject scheme (beginner, intermediate, advanced)."""
    files = generate_dita_subject_scheme_dataset(config, "/tmp")
    valid_keys = [k for k in files if "topic_valid_" in k and k.endswith(".dita")]
    assert len(valid_keys) >= 10
    for key in valid_keys[:5]:
        content = files[key].decode("utf-8")
        assert 'audience="' in content
        assert any(v in content for v in ["beginner", "intermediate", "advanced"])


def test_subject_scheme_invalid_topics_use_invalid_audience(config):
    """Invalid topics use audience values not in subject scheme (expert, invalid, foo, etc.)."""
    files = generate_dita_subject_scheme_dataset(config, "/tmp")
    invalid_keys = [k for k in files if "topic_invalid_" in k and k.endswith(".dita")]
    assert len(invalid_keys) >= 10
    for key in invalid_keys[:5]:
        content = files[key].decode("utf-8")
        assert 'audience="' in content
        assert "intentionally violates" in content or "invalid" in content.lower()


def test_subject_scheme_manifest_valid(config):
    """Dataset manifest contains expected fields."""
    files = generate_dita_subject_scheme_dataset(config, "/tmp")
    manifest_key = next((k for k in files if "dataset_manifest.json" in k), None)
    assert manifest_key
    manifest = json.loads(files[manifest_key].decode("utf-8"))
    assert manifest.get("recipe_name") == "dita_subject_scheme_dataset_recipe"
    assert manifest.get("dataset_name") == "dita_subject_scheme_dataset"
    assert manifest.get("valid_topics") == 10
    assert manifest.get("invalid_topics") == 10
    assert manifest.get("dita_feature") == "subject_scheme"
    assert manifest["stats"].get("valid_count") == 10
    assert manifest["stats"].get("invalid_count") == 10


def test_subject_scheme_custom_counts(config):
    """Generator respects valid_count and invalid_count parameters."""
    files = generate_dita_subject_scheme_dataset(
        config, "/tmp", valid_count=5, invalid_count=3
    )
    valid_keys = [k for k in files if "topic_valid_" in k and k.endswith(".dita")]
    invalid_keys = [k for k in files if "topic_invalid_" in k and k.endswith(".dita")]
    assert len(valid_keys) == 5
    assert len(invalid_keys) == 3


def test_subject_scheme_subject_scheme_has_enumerationdef(config):
    """Subject scheme map contains subjectScheme, subjectdef, enumerationdef."""
    files = generate_dita_subject_scheme_dataset(config, "/tmp")
    scheme_key = next((k for k in files if "subject-scheme.ditamap" in k), None)
    assert scheme_key
    content = files[scheme_key].decode("utf-8")
    assert "subjectScheme" in content or "subjectscheme" in content.lower()
    assert "subjectdef" in content
    assert "enumerationdef" in content or "enumerationDef" in content
    assert "audience-values" in content
