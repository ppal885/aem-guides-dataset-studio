"""Tests for enterprise-safe Builder recipe additions."""
import json

from app.generator.enterprise_dita_recipes import (
    generate_compact_parent_child_key_resolution,
    generate_large_root_map_1000_topics_100kb,
    generate_parent_child_maps_keys_conref_conkeyref_selfrefs,
)
from app.generator.generate import safe_join
from app.generator.recipe_manifest import discover_recipe_specs
from app.jobs.schemas import DatasetConfig
from app.tasks.generate_dataset import run_generate_dataset


def _config() -> DatasetConfig:
    return DatasetConfig(
        name="enterprise-test",
        seed="enterprise-seed",
        root_folder="/content/dam/enterprise-test",
        recipes=[],
    )


def test_recipe_manifest_exposes_enterprise_recipe_specs():
    spec_ids = {spec.id for spec in discover_recipe_specs()}
    assert "parent_child_maps_keys_conref_conkeyref_selfrefs" in spec_ids
    assert "compact_parent_child_key_resolution" in spec_ids
    assert "large_root_map_1000_topics_100kb" in spec_ids


def test_parent_child_recipe_generates_expected_structure_and_resolved_summary():
    config = _config()
    files = generate_parent_child_maps_keys_conref_conkeyref_selfrefs(config, "/tmp")

    expected_paths = [
        "/tmp/parent_child_maps_keys_conref_conkeyref_selfrefs/maps/parent-root.ditamap",
        "/tmp/parent_child_maps_keys_conref_conkeyref_selfrefs/maps/child-a.ditamap",
        "/tmp/parent_child_maps_keys_conref_conkeyref_selfrefs/maps/child-b.ditamap",
        "/tmp/parent_child_maps_keys_conref_conkeyref_selfrefs/maps/child-c.ditamap",
        "/tmp/parent_child_maps_keys_conref_conkeyref_selfrefs/topics/common-intro.dita",
        "/tmp/parent_child_maps_keys_conref_conkeyref_selfrefs/topics/shared-content.dita",
        "/tmp/parent_child_maps_keys_conref_conkeyref_selfrefs/topics/child-a-topic-01.dita",
        "/tmp/parent_child_maps_keys_conref_conkeyref_selfrefs/topics/child-a-topic-02.dita",
        "/tmp/parent_child_maps_keys_conref_conkeyref_selfrefs/topics/child-b-topic-01.dita",
        "/tmp/parent_child_maps_keys_conref_conkeyref_selfrefs/topics/child-b-topic-02.dita",
        "/tmp/parent_child_maps_keys_conref_conkeyref_selfrefs/topics/child-c-topic-01.dita",
        "/tmp/parent_child_maps_keys_conref_conkeyref_selfrefs/topics/child-c-topic-02.dita",
    ]
    for expected in expected_paths:
        assert expected in files

    child_a_details = files[
        "/tmp/parent_child_maps_keys_conref_conkeyref_selfrefs/topics/child-a-topic-02.dita"
    ].decode("utf-8")
    assert 'conref="shared-content.dita#shared-content/shared-intro-copy"' in child_a_details
    assert 'conkeyref="child-a-overview/child-a-overview-summary"' in child_a_details

    summary = json.loads(
        files[
            "/tmp/parent_child_maps_keys_conref_conkeyref_selfrefs/meta/validation-summary.json"
        ].decode("utf-8")
    )
    assert summary["all_references_resolved"] is True
    assert summary["validation_errors"] == []
    assert summary["parent_level_keys_created"] == ["parent-common", "parent-shared-content"]


def test_compact_parent_child_recipe_generates_clean_key_resolution_bundle():
    config = _config()
    files = generate_compact_parent_child_key_resolution(config, "/tmp")

    root_map = files["/tmp/compact_parent_child_key_resolution/maps/compact-root.ditamap"].decode("utf-8")
    assert 'keydef keys="compact-parent-common"' in root_map
    assert 'mapref href="compact-child.ditamap"' in root_map

    summary = json.loads(
        files["/tmp/compact_parent_child_key_resolution/meta/validation-summary.json"].decode("utf-8")
    )
    assert summary["all_references_resolved"] is True
    assert summary["validation_errors"] == []
    assert summary["child_level_keys_created"] == ["compact-child-overview", "compact-child-details"]


def test_large_root_map_recipe_smoke_with_reduced_size():
    config = _config()
    files = generate_large_root_map_1000_topics_100kb(
        config,
        "/tmp",
        topic_count=3,
        approx_topic_size_kb=12,
    )

    assert "/tmp/large_root_map_1000_topics_100kb/maps/root-map.ditamap" in files
    topic_keys = [
        path for path in files if path.endswith(".dita") and "/topics/" in path
    ]
    assert len(topic_keys) == 3
    for topic_key in topic_keys:
        assert len(files[topic_key]) > 10_000

    summary = json.loads(
        files["/tmp/large_root_map_1000_topics_100kb/meta/validation-summary.json"].decode("utf-8")
    )
    assert summary["all_references_resolved"] is True
    assert summary["validation_errors"] == []


def test_dataset_config_and_dispatch_accept_enterprise_recipe_types():
    raw = {
        "name": "enterprise-wire",
        "seed": "enterprise-seed",
        "root_folder": "/content/dam/enterprise-test",
        "windows_safe_filenames": True,
        "doctype_topic": '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">',
        "doctype_map": '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">',
        "recipes": [
            {"type": "parent_child_maps_keys_conref_conkeyref_selfrefs", "pretty_print": True},
            {"type": "compact_parent_child_key_resolution", "pretty_print": True},
            {
                "type": "large_root_map_1000_topics_100kb",
                "topic_count": 2,
                "approx_topic_size_kb": 10,
                "pretty_print": False,
            },
        ],
    }
    cfg = DatasetConfig.model_validate(raw)
    assert len(cfg.recipes) == 3
    assert cfg.recipes[0].type == "parent_child_maps_keys_conref_conkeyref_selfrefs"

    out = run_generate_dataset(raw, "job-enterprise-wire")
    base = "content/dam/enterprise-test"
    assert safe_join(
        base,
        "parent_child_maps_keys_conref_conkeyref_selfrefs/maps/parent-root.ditamap",
    ) in out
    assert safe_join(
        base,
        "compact_parent_child_key_resolution/maps/compact-root.ditamap",
    ) in out
    assert safe_join(
        base,
        "large_root_map_1000_topics_100kb/maps/root-map.ditamap",
    ) in out
