"""Tests for nested_keydef recipe (GUIDES-42533)."""
import tempfile
from pathlib import Path

from app.generator.nested_keydef import generate_nested_keydef_dataset
from app.jobs.schemas import DatasetConfig


def test_nested_keydef_generates_valid_structure():
    """Verify nested keydef dataset matches Map A → Map B → Topic C structure."""
    config = DatasetConfig(name="test", seed="test", root_folder="/tmp", recipes=[])
    with tempfile.TemporaryDirectory() as tmp:
        result = generate_nested_keydef_dataset(config, tmp, id_prefix="t")
    assert isinstance(result, dict)
    paths = list(result.keys())
    assert any("map_a.ditamap" in p for p in paths)
    assert any("keymap.ditamap" in p for p in paths)
    assert any("static_content.dita" in p for p in paths)
    assert any("consumer_overview.dita" in p for p in paths)

    map_a_path = next(p for p in paths if "map_a.ditamap" in p)
    map_a = result[map_a_path]
    assert b'keydef' in map_a
    assert b'staticKeyMap' in map_a
    assert b'keymap.ditamap' in map_a
    assert b'format="ditamap"' in map_a

    map_b_path = next(p for p in paths if "keymap.ditamap" in p)
    map_b = result[map_b_path]
    assert b'productName' in map_b
    assert b'keywordFile' in map_b
    assert b'static_content.dita' in map_b
    assert b'topicmeta' in map_b or b'keyword' in map_b

    topic_c_path = next(p for p in paths if "static_content.dita" in p)
    topic_c = result[topic_c_path]
    assert b'versionString' in topic_c
    assert b'keywords' in topic_c

    topic_d_path = next(p for p in paths if "consumer_overview.dita" in p)
    topic_d = result[topic_d_path]
    assert b'keyref="productName"' in topic_d
    assert b'keyref="versionString"' in topic_d


def test_nested_keydef_recipe_spec():
    """Verify RECIPE_SPECS has correct metadata for retrieval."""
    from app.generator.nested_keydef import RECIPE_SPECS

    spec = RECIPE_SPECS[0]
    assert spec["id"] == "nested_keydef_map_map_topic"
    assert "nested keydef" in spec.get("use_when", [])
    assert "recursive key resolution" in spec.get("use_when", [])
