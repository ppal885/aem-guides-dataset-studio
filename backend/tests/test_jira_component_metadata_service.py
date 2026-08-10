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
    assert service.canonical_component_names(
        [
            "Native_PDF",
            "Database",
            "Ditaval",
            "External Data Sources",
            "Baseline",
            "AEM Site",
            "UUID Migration",
        ]
    ) == ["Publishing", "Platform", "Authoring", "Integration"]
    assert service.canonical_component_names(
        [
            "Asset Management",
            "Learning",
            "Baseline_UI",
            "Citation Management",
            "Reports",
            "Oxygen",
            "Translation",
            "Homepage",
        ]
    ) == ["Platform", "Authoring", "Publishing", "Editor", "Integration"]
    assert service.component_filter_metadata(["Authoring", "Editor"]) == {
        "component_primary": "authoring",
        "component_filter_schema_version": service.COMPONENT_FILTER_SCHEMA_VERSION,
        "component_editor": True,
        "component_authoring": True,
        "component_publishing": False,
        "component_platform": False,
        "component_schematron": False,
        "component_integration": False,
    }
    inferred, signals = service.infer_component_names(
        "Native PDF publishing template toolbar fails"
    )
    assert inferred == ["Publishing", "Editor"]
    assert any(signal.startswith("summary:publishing:") for signal in signals)
    inferred, signals = service.infer_component_names(
        "Please apply the fix for Guides",
        "The deployment pipeline fails because an Oak index conflicts with damAssetLucene.",
    )
    assert inferred == ["Platform"]
    assert any(signal.startswith("description:platform:") for signal in signals)


def test_migration_updates_existing_records_without_jira_or_embeddings(monkeypatch):
    monkeypatch.setattr(
        service,
        "iter_collection_records",
        lambda _collection, **_kwargs: iter(
            [
                {"id": "one", "metadata": {"jira_key": "GUIDES-1", "components": '["Publishing"]'}},
                {
                    "id": "two",
                    "metadata": {
                        "jira_key": "GUIDES-2",
                        "components": "[]",
                        "components_raw": "[]",
                        "component_primary": "",
                        "component_filter_schema_version": service.COMPONENT_FILTER_SCHEMA_VERSION,
                        "component_classification_source": "unclassified",
                        "component_editor": False,
                        "component_authoring": False,
                        "component_publishing": False,
                        "component_platform": False,
                        "component_schematron": False,
                        "component_integration": False,
                    },
                },
            ]
        ),
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
    assert (
        captured["metadatas"][0]["component_filter_schema_version"]
        == service.COMPONENT_FILTER_SCHEMA_VERSION
    )
    assert captured["metadatas"][0]["component_publishing"] is True
    assert captured["metadatas"][0]["component_editor"] is False


def test_migration_flags_noncanonical_component_values(monkeypatch):
    monkeypatch.setattr(
        service,
        "iter_collection_records",
        lambda _collection, **_kwargs: iter(
            [
                {
                    "id": "legacy",
                    "metadata": {
                        "jira_key": "GUIDES-3",
                        "components": '["Platform and Integration"]',
                    },
                }
            ]
        ),
    )

    stats = service.migrate_jira_component_primary(dry_run=True)

    assert stats["without_component"] == 1
    assert stats["noncanonical_component_records"] == 1
    assert stats["canonicalized_component_records"] == 1


def test_migration_streams_and_flushes_in_bounded_batches(monkeypatch):
    monkeypatch.setattr(
        service,
        "iter_collection_records",
        lambda _collection, **_kwargs: (
            {
                "id": f"record-{index}",
                "metadata": {"components": '["Editor"]'},
            }
            for index in range(5)
        ),
    )
    batches: list[list[str]] = []

    def update(_collection, ids, _metadatas):
        batches.append(list(ids))
        return True

    monkeypatch.setattr(service, "update_document_metadatas", update)

    stats = service.migrate_jira_component_primary(batch_size=2)

    assert stats["scanned"] == 5
    assert stats["pending"] == 5
    assert stats["updated"] == 5
    assert batches == [
        ["record-0", "record-1"],
        ["record-2", "record-3"],
        ["record-4"],
    ]


def test_migration_propagates_incomplete_paginated_scan(monkeypatch):
    def fail_scan(_collection, **_kwargs):
        yield {"id": "record-0", "metadata": {"components": '["Editor"]'}}
        raise RuntimeError("scan count mismatch")

    monkeypatch.setattr(service, "iter_collection_records", fail_scan)

    try:
        service.migrate_jira_component_primary(dry_run=True)
    except RuntimeError as exc:
        assert "scan count mismatch" in str(exc)
    else:
        raise AssertionError("incomplete scan must fail the migration")


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


def test_migration_cli_defaults_to_dry_run_and_requires_explicit_apply(monkeypatch, capsys):
    module = _load_migration_script()
    calls: list[bool] = []

    def migrate(*, dry_run, batch_size):
        calls.append(dry_run)
        return {"dry_run": dry_run, "pending": 0, "batch_size": batch_size}

    monkeypatch.setattr(service, "migrate_jira_component_primary", migrate)

    assert module.main([]) == 0
    assert module.main(["--apply", "--batch-size", "17"]) == 0
    assert calls == [True, False]
    assert '"batch_size": 17' in capsys.readouterr().out


def test_migration_cli_require_clean_fails_when_records_are_pending(monkeypatch):
    module = _load_migration_script()
    monkeypatch.setattr(
        service,
        "migrate_jira_component_primary",
        lambda **_kwargs: {"dry_run": True, "pending": 1},
    )

    assert module.main(["--dry-run", "--require-clean"]) == 1
