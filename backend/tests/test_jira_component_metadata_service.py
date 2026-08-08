"""Tests for scalar Jira component metadata migration."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from app.services import jira_component_metadata_service as service


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "migrate_jira_component_metadata.py"


def _load_migration_script():
    spec = importlib.util.spec_from_file_location("migrate_jira_component_metadata_script", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_component_primary_normalization_and_json_fallback():
    assert service.CANONICAL_JIRA_COMPONENTS == (
        "Editor",
        "Authoring",
        "Publishing",
        "Platform",
        "Schematron",
        "Integration",
    )
    assert service.normalize_component_token("  Schematron  ") == "schematron"
    assert service.normalize_component_token("Platform and Integration") == ""
    assert service.component_primary_from_names(["", "Publishing"]) == "publishing"
    assert service.component_primary_from_metadata({"components": '["Editor", "Authoring"]'}) == "editor"
    assert service.canonical_component_names(["editor", "Editor", "Integration"]) == [
        "Editor",
        "Integration",
    ]


def test_migration_updates_existing_records_without_jira_or_embeddings(monkeypatch):
    monkeypatch.setattr(
        service,
        "get_collection_records",
        lambda _collection: [
            {"id": "one", "metadata": {"jira_key": "GUIDES-1", "components": '["Publishing"]'}},
            {
                "id": "two",
                "metadata": {
                    "jira_key": "GUIDES-2",
                    "components": "[]",
                    "components_raw": "[]",
                    "component_primary": "",
                    "component_filter_schema_version": 2,
                },
            },
        ],
    )
    captured: dict = {}

    def update(_collection, ids, metadatas):
        captured["ids"] = ids
        captured["metadatas"] = metadatas
        return True

    monkeypatch.setattr(service, "update_document_metadatas", update)

    stats = service.migrate_jira_component_primary(batch_size=10)

    assert stats == {
        "dry_run": False,
        "scanned": 2,
        "pending": 1,
        "updated": 1,
        "unchanged": 1,
        "without_component": 1,
        "noncanonical_component_records": 0,
        "canonicalized_component_records": 0,
        "raw_component_metadata_added": 1,
        "canonical_component_record_counts": {
            "Editor": 0,
            "Authoring": 0,
            "Publishing": 1,
            "Platform": 0,
            "Schematron": 0,
            "Integration": 0,
        },
    }
    assert captured["ids"] == ["one"]
    assert captured["metadatas"][0]["components"] == '["Publishing"]'
    assert captured["metadatas"][0]["components_raw"] == '["Publishing"]'
    assert captured["metadatas"][0]["component_primary"] == "publishing"
    assert captured["metadatas"][0]["component_filter_schema_version"] == 2


def test_migration_flags_noncanonical_component_values(monkeypatch):
    monkeypatch.setattr(
        service,
        "get_collection_records",
        lambda _collection: [
            {
                "id": "legacy",
                "metadata": {
                    "jira_key": "GUIDES-3",
                    "components": '["Platform and Integration"]',
                },
            }
        ],
    )

    stats = service.migrate_jira_component_primary(dry_run=True)

    assert stats["without_component"] == 1
    assert stats["noncanonical_component_records"] == 1
    assert stats["canonicalized_component_records"] == 1


def test_component_list_order_overrides_stale_scalar_primary():
    assert service.component_primary_from_metadata(
        {
            "components": '["Integration", "Platform"]',
            "component_primary": "platform",
        }
    ) == "integration"


def test_vm_migration_loads_chroma_path_from_service_environment(monkeypatch, tmp_path):
    module = _load_migration_script()
    env_file = tmp_path / ".env.docker"
    env_file.write_text('CHROMA_DB_PATH="/srv/aem data/chroma"\n', encoding="utf-8")
    monkeypatch.delenv("CHROMA_DB_PATH", raising=False)

    assert module._load_env_file(env_file) is None
    assert os.environ["CHROMA_DB_PATH"] == "/srv/aem data/chroma"
