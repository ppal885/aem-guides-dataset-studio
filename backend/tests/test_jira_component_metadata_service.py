"""Tests for scalar Jira component metadata migration."""

from __future__ import annotations

from app.services import jira_component_metadata_service as service


def test_component_primary_normalization_and_json_fallback():
    assert service.normalize_component_token("  Platform   and Integration ") == "platform and integration"
    assert service.component_primary_from_names(["", "Publishing"]) == "publishing"
    assert service.component_primary_from_metadata({"components": '["Editor", "Authoring"]'}) == "editor"


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
                    "component_primary": "",
                    "component_filter_schema_version": 1,
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
    }
    assert captured["ids"] == ["one"]
    assert captured["metadatas"][0]["component_primary"] == "publishing"
    assert captured["metadatas"][0]["component_filter_schema_version"] == 1
