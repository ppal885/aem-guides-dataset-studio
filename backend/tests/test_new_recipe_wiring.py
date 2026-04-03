"""Smoke tests for newly wired DITA recipe types (schemas + generate_dataset dispatch)."""
from app.generator.generate import safe_join
from app.jobs.schemas import DatasetConfig
from app.tasks.generate_dataset import run_generate_dataset


def _minimal_config(recipes: list) -> dict:
    return {
        "name": "wire-smoke",
        "seed": "wire-seed",
        "root_folder": "/content/dam/wire-test",
        "windows_safe_filenames": True,
        "doctype_topic": '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">',
        "doctype_map": '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">',
        "recipes": recipes,
    }


def test_dataset_config_parses_new_recipe_types():
    raw = _minimal_config(
        [
            {"type": "table_semantics_reference", "id_prefix": "tbl", "issue_summary": "Align bug"},
            {"type": "inline_formatting_nested", "id_prefix": "t", "pretty_print": True},
            {"type": "self_conrefend_range", "id_prefix": "t", "pretty_print": True},
            {"type": "self_xref_conref_positive", "id_prefix": "t", "pretty_print": True},
            {"type": "validation_duplicate_id_negative", "id_prefix": "t"},
            {"type": "validation_invalid_child_negative", "id_prefix": "t"},
            {"type": "validation_missing_body_negative", "id_prefix": "t"},
        ]
    )
    cfg = DatasetConfig.model_validate(raw)
    assert len(cfg.recipes) == 7
    assert cfg.recipes[0].type == "table_semantics_reference"


def test_run_generate_inline_formatting_nested_keys():
    base = "content/dam/wire-test"
    raw = _minimal_config([{"type": "inline_formatting_nested", "id_prefix": "t", "pretty_print": True}])
    out = run_generate_dataset(raw, "job-wire-inline")
    topic_key = safe_join(base, "topics/inline_formatting_nested.dita")
    assert topic_key in out
    assert any(k.endswith(".ditamap") for k in out)


def test_run_generate_self_xref_conref_positive_key():
    base = "content/dam/wire-test"
    raw = _minimal_config([{"type": "self_xref_conref_positive", "id_prefix": "t", "pretty_print": True}])
    out = run_generate_dataset(raw, "job-wire-self")
    key = safe_join(base, "topics/self_xref_conref_positive.dita")
    assert key in out
    assert b"xref" in out[key].lower()


def test_dataset_config_parses_properties_table_reference():
    raw = _minimal_config(
        [
            {
                "type": "properties_table_reference",
                "topic_count": 5,
                "rows_per_table": 6,
                "include_prophead": True,
                "include_map": True,
                "pretty_print": True,
            },
        ]
    )
    cfg = DatasetConfig.model_validate(raw)
    assert len(cfg.recipes) == 1
    assert cfg.recipes[0].type == "properties_table_reference"


def test_run_generate_properties_table_reference_produces_topics_and_map():
    base = "content/dam/wire-test"
    raw = _minimal_config(
        [
            {
                "type": "properties_table_reference",
                "topic_count": 5,
                "rows_per_table": 4,
                "include_prophead": True,
                "include_map": True,
                "pretty_print": True,
            },
        ]
    )
    out = run_generate_dataset(raw, "job-wire-properties-table")
    assert any("properties_ref_" in k and k.endswith(".dita") for k in out)
    assert any(k.endswith("properties_table_reference.ditamap") for k in out)
    sample = next(v for k, v in out.items() if "properties_ref_" in k and k.endswith(".dita"))
    assert b"proptype" in sample and b"propvalue" in sample and b"properties" in sample
    assert b"reference.dtd" in sample and b"<reference" in sample
    assert b"DITA Reference//EN" in sample
    assert b"DITA Topic//EN" not in sample.split(b"<reference", 1)[0]


def test_run_generate_validation_duplicate_id_negative_path():
    raw = _minimal_config([{"type": "validation_duplicate_id_negative", "id_prefix": "t"}])
    out = run_generate_dataset(raw, "job-wire-val")
    assert any(k.endswith("validation_duplicate_id_negative/topics/main.dita") for k in out)
