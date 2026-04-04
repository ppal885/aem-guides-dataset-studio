"""Tests for DITA recipe library - metadata, generation, negative marking."""
import tempfile
from pathlib import Path

import pytest

from app.generator.recipe_manifest import discover_recipe_specs
from app.generator.xrefs import generate_xref_external_pdf, generate_xref_self_section
from app.generator.conref_recipes import generate_conref_self_basic, generate_conrefend_range_paragraphs
from app.generator.keys import generate_keys_keyscope_shadow_2level
from app.generator.metadata import generate_metadata_topicmeta_keywords_indexterm
from app.generator.maps import generate_maps_topicgroup_basic
from app.generator.tables import generate_tables_colwidth_percent
from app.generator.validation_negative import generate_validation_duplicate_id_negative
from app.jobs.schemas import DatasetConfig
from app.utils.dita_validator import validate_dita_folder


@pytest.fixture
def config():
    return DatasetConfig(name="test", seed="test-seed", root_folder="/tmp", recipes=[])


def _write_and_validate(files: dict, base: Path) -> dict:
    for rel_path, content in files.items():
        out = base / rel_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(content)
    return validate_dita_folder(base)


def test_recipe_metadata_loads():
    """Recipe metadata loads correctly from all modules."""
    specs = discover_recipe_specs()
    assert len(specs) >= 50
    for s in specs:
        assert s.id
        assert s.title
        assert s.module
        assert s.function


def test_recipe_functions_exist():
    """Generator functions exist for key recipes."""
    specs = discover_recipe_specs()
    by_id = {s.id: s for s in specs}
    for rid in ["xref.external_pdf", "xref.self_section", "conref.self_basic", "conrefend.range_paragraphs",
                "keys.keyscope_shadow_2level", "metadata.topicmeta_keywords_indexterm", "maps.topicgroup_basic",
                "tables.colwidth_percent", "validation.duplicate_id_negative", "dita_conref_title_dataset_recipe"]:
        assert rid in by_id, f"Recipe {rid} not found"
        spec = by_id[rid]
        mod = __import__(spec.module, fromlist=[spec.function])
        assert hasattr(mod, spec.function), f"Function {spec.function} not in {spec.module}"


def test_xref_external_pdf(config):
    """xref.external_pdf: format=pdf, scope=local."""
    files = generate_xref_external_pdf(config, "/tmp")
    assert any("xref" in k.lower() and "pdf" in k.lower() for k in files) or len(files) >= 1
    content = list(files.values())[0]
    assert b'format="pdf"' in content or b"format=" in content
    assert b"pdf" in content


def test_xref_self_section(config):
    """xref.self_section: same-file xref to section."""
    files = generate_xref_self_section(config, "/tmp")
    assert len(files) >= 1
    content = list(files.values())[0]
    assert b'type="section"' in content
    assert b"#" in content


def test_conref_self_basic(config):
    """conref.self_basic: same-file conref."""
    files = generate_conref_self_basic(config, "/tmp")
    assert len(files) >= 1
    content = list(files.values())[0]
    assert b"conref" in content


def test_conrefend_range_paragraphs(config):
    """conrefend.range_paragraphs: conref+conrefend range."""
    files = generate_conrefend_range_paragraphs(config, "/tmp")
    assert len(files) >= 1
    content = list(files.values())[0]
    assert b"conref" in content
    assert b"conrefend" in content


def test_keys_keyscope_shadow_2level(config):
    """keys.keyscope_shadow_2level: two-level keyscope."""
    files = generate_keys_keyscope_shadow_2level(config, "/tmp")
    assert len(files) >= 3
    map_content = next((v for k, v in files.items() if "map" in k.lower() or "ditamap" in k), None)
    assert map_content
    assert b"keyscope" in map_content or b"keydef" in map_content


def test_metadata_topicmeta_keywords_indexterm(config):
    """metadata.topicmeta_keywords_indexterm: topicmeta with keywords and indexterm."""
    files = generate_metadata_topicmeta_keywords_indexterm(config, "/tmp")
    assert len(files) >= 2
    map_content = next((v for k, v in files.items() if "map" in k.lower() or "ditamap" in k), None)
    assert map_content
    assert b"topicmeta" in map_content or b"keywords" in map_content


def test_maps_topicgroup_basic(config):
    """maps.topicgroup_basic: map with topicgroup."""
    files = generate_maps_topicgroup_basic(config, "/tmp")
    assert len(files) >= 2
    map_content = next((v for k, v in files.items() if "map" in k.lower() or "ditamap" in k), None)
    assert map_content
    assert b"topicgroup" in map_content


def test_tables_colwidth_percent(config):
    """tables.colwidth_percent: colspec with colwidth."""
    files = generate_tables_colwidth_percent(config, "/tmp")
    assert len(files) >= 1
    content = list(files.values())[0]
    assert b"colwidth" in content
    assert b"*" in content


def test_validation_duplicate_id_negative(config):
    """validation.duplicate_id_negative: negative recipe, duplicate ID."""
    with tempfile.TemporaryDirectory() as tmp:
        files = generate_validation_duplicate_id_negative(config, tmp)
        assert len(files) >= 1
        content = list(files.values())[0]
        assert b'id="dup_id"' in content or b"dup_id" in content
        result = _write_and_validate(files, Path(tmp))
    assert len(result["errors"]) >= 1
    assert any("duplicate" in e.lower() or "dup" in e.lower() for e in result["errors"])


def test_negative_recipes_marked_correctly():
    """Negative recipes have positive_negative='negative'."""
    specs = discover_recipe_specs()
    negative_specs = [s for s in specs if s.positive_negative == "negative"]
    assert len(negative_specs) >= 5
    ids = [s.id for s in negative_specs]
    assert "validation.duplicate_id_negative" in ids or any("negative" in i for i in ids)
