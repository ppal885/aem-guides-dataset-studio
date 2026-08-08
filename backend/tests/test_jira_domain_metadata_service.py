"""Tests for conservative unknown-domain backfill."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from app.services import jira_domain_metadata_service
from app.services.jira_domain_metadata_service import (
    build_jira_domain_backfill_plan,
    infer_domain_for_issue_records,
)


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "migrate_unknown_jira_domains.py"


def _load_migration_script():
    spec = importlib.util.spec_from_file_location("migrate_unknown_jira_domains_script", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record(record_id: str, jira_key: str, document: str, **metadata):
    return {
        "id": record_id,
        "document": document,
        "metadata": {"jira_key": jira_key, **metadata},
    }


def test_component_backfill_assigns_unknown_issue_without_overwriting_known_domain():
    records = [
        _record(
            "G-1::summary::0",
            "G-1",
            "Unexpected behavior after save",
            enrich_domain="unknown",
            components='["Editor"]',
        ),
        _record(
            "G-2::summary::0",
            "G-2",
            "Publishing failure",
            enrich_domain="publishing",
            components='["Publishing"]',
        ),
    ]

    plan = build_jira_domain_backfill_plan(records)

    assert plan["assignments"]["G-1"]["domain"] == "editor"
    assert plan["assignments"]["G-1"]["method"] == "jira_component"
    assert plan["pending_chunk_update_count"] == 1
    pending = plan["pending_chunk_updates"][0]
    assert pending["metadata"]["enrich_domain"] == "editor"
    assert pending["metadata"]["domain_ranking_policy"] == "soft_boost_only"


def test_each_canonical_component_can_repair_unknown_domain():
    records = [
        _record(
            f"G-{index}::summary::0",
            f"G-{index}",
            "Unexpected behavior",
            enrich_domain="unknown",
            components=f'["{component}"]',
        )
        for index, component in enumerate(
            ("Editor", "Authoring", "Publishing", "Platform", "Schematron", "Integration"),
            start=10,
        )
    ]

    plan = build_jira_domain_backfill_plan(records)

    assert {
        assignment["domain"] for assignment in plan["assignments"].values()
    } == {"editor", "authoring", "publishing", "platform", "schematron", "integration"}


def test_existing_known_domain_harmonizes_unknown_chunks_for_same_issue():
    plan = build_jira_domain_backfill_plan([
        _record("G-3::summary::0", "G-3", "Summary", enrich_domain="keyref"),
        _record("G-3::comment::0", "G-3", "Comment", enrich_domain="unknown"),
    ])

    assert plan["assignments"]["G-3"]["domain"] == "keyref"
    assert plan["assignments"]["G-3"]["method"] == "existing_issue_domain"
    assert plan["pending_chunk_update_count"] == 1


def test_conflicting_known_domains_are_blocked_not_guessed():
    inference = infer_domain_for_issue_records([
        _record("G-4::summary::0", "G-4", "Summary", enrich_domain="editor"),
        _record("G-4::comment::0", "G-4", "Comment", enrich_domain="publishing"),
    ])

    assert inference["domain"] == ""
    assert inference["method"] == "conflicting_existing_domains"
    assert inference["confidence"] == "blocked"


def test_weak_generic_evidence_stays_unknown():
    inference = infer_domain_for_issue_records([
        _record("G-5::summary::0", "G-5", "Unexpected behavior with no product-area evidence")
    ])

    assert inference["domain"] == ""
    assert inference["method"] == "insufficient_evidence"


def test_migration_refuses_partial_chroma_scan(monkeypatch):
    monkeypatch.setattr(jira_domain_metadata_service, "is_chroma_available", lambda: True)
    monkeypatch.setattr(jira_domain_metadata_service, "get_collection_count", lambda collection: 10)
    monkeypatch.setattr(jira_domain_metadata_service, "get_collection_records", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        jira_domain_metadata_service,
        "update_document_metadatas",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("partial scan wrote metadata")),
    )

    report = jira_domain_metadata_service.migrate_unknown_jira_domains(dry_run=False)

    assert report["available"] is False
    assert "Partial Chroma scan" in report["error"]


def test_migration_dry_run_builds_plan_without_writes(monkeypatch):
    records = [
        _record(
            "G-6::summary::0",
            "G-6",
            "Unexpected behavior",
            enrich_domain="unknown",
            component_primary="editor",
        )
    ]
    monkeypatch.setattr(jira_domain_metadata_service, "is_chroma_available", lambda: True)
    monkeypatch.setattr(jira_domain_metadata_service, "get_collection_count", lambda collection: 1)
    monkeypatch.setattr(
        jira_domain_metadata_service,
        "get_collection_records",
        lambda *args, **kwargs: records,
    )
    monkeypatch.setattr(
        jira_domain_metadata_service,
        "update_document_metadatas",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dry run wrote metadata")),
    )

    report = jira_domain_metadata_service.migrate_unknown_jira_domains(dry_run=True)

    assert report["available"] is True
    assert report["pending_chunk_update_count"] == 1
    assert report["updated_chunk_count"] == 0
    assert report["sql_sync"]["skipped"] is True


def test_vm_domain_migration_loads_service_environment(monkeypatch, tmp_path):
    module = _load_migration_script()
    env_file = tmp_path / ".env.docker"
    env_file.write_text('CHROMA_DB_PATH="/srv/aem data/chroma"\n', encoding="utf-8")
    monkeypatch.delenv("CHROMA_DB_PATH", raising=False)

    assert module._load_env_file(env_file) is None
    assert os.environ["CHROMA_DB_PATH"] == "/srv/aem data/chroma"
