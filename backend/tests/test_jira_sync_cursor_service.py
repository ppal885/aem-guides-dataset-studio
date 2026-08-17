"""Tests for Jira incremental cursor inspection and corpus bootstrap."""

from __future__ import annotations

from app.services import jira_sync_cursor_service, jira_sync_state
from app.services.jira_sync_cursor_service import (
    bootstrap_jira_sync_cursor,
    build_corpus_cursor_candidate,
)
from app.services.jira_sync_state import JiraQaIndexSyncState, merge_failed_keys, sync_cursor_health


def _record(record_id: str, jira_key: str, updated_at: str = "") -> dict:
    return {
        "id": record_id,
        "metadata": {
            "jira_key": jira_key,
            "jira_updated_at": updated_at,
        },
    }


def test_empty_sync_state_reports_all_required_cursor_fields():
    health = sync_cursor_health(JiraQaIndexSyncState(), project_key="DXML")

    assert health["valid"] is False
    assert health["missing_or_invalid_fields"] == [
        "last_successful_sync_time",
        "last_indexed_jira_key",
        "total_indexed",
    ]


def test_failed_key_state_discards_search_level_errors():
    assert merge_failed_keys(["search", "DXML-1"], ["SEARCH", "DXML-2"]) == [
        "DXML-1",
        "DXML-2",
    ]


def test_bootstrap_rejects_invalid_state_identifier():
    report = bootstrap_jira_sync_cursor(
        "DXML",
        sync_state_id="../../bad",
        dry_run=True,
        records=[],
        collection_count=0,
        include_sql=False,
    )

    assert report["available"] is False
    assert "sync_state_id" in report["error"]


def test_corpus_candidate_uses_latest_actual_jira_update_and_sql_fill():
    records = [
        _record("DXML-1::summary::0", "DXML-1", "10/Jan/25 10:00 AM"),
        _record("DXML-2::summary::0", "DXML-2"),
        _record("GUIDES-9::summary::0", "GUIDES-9", "2028-01-01T00:00:00Z"),
    ]

    candidate = build_corpus_cursor_candidate(
        records,
        project_key="DXML",
        collection_count=3,
        sql_updated_by_key={"DXML-2": "2026-08-06T18:40:07+00:00"},
    )

    assert candidate["candidate_ready"] is True
    assert candidate["unique_project_issue_count"] == 2
    assert candidate["updated_at_coverage_percent"] == 100.0
    assert candidate["last_indexed_jira_key"] == "DXML-2"
    assert candidate["latest_indexed_jira_updated_at"] == "2026-08-06T18:40:07+00:00"
    assert candidate["latest_timestamp_source"] == "sql_jira_updated_at"
    assert candidate["historical_backfill_complete"] is False


def test_corpus_candidate_ignores_malformed_project_issue_keys():
    candidate = build_corpus_cursor_candidate(
        [
            _record("DXML-bad::summary::0", "DXML-bad", "2028-01-01T00:00:00Z"),
            _record("DXML-4::summary::0", "DXML-4", "2026-01-01T00:00:00Z"),
        ],
        project_key="DXML",
        collection_count=2,
    )

    assert candidate["candidate_ready"] is True
    assert candidate["unique_project_issue_count"] == 1
    assert candidate["last_indexed_jira_key"] == "DXML-4"


def test_corpus_candidate_refuses_partial_chroma_scan():
    candidate = build_corpus_cursor_candidate(
        [_record("DXML-1::summary::0", "DXML-1", "2026-01-01T00:00:00Z")],
        project_key="DXML",
        collection_count=2,
    )

    assert candidate["candidate_ready"] is False
    assert "Partial Chroma scan" in candidate["error"]


def test_bootstrap_dry_run_does_not_write(monkeypatch):
    monkeypatch.setattr(
        jira_sync_cursor_service,
        "load_jira_qa_sync_state",
        lambda _sid: JiraQaIndexSyncState(),
    )
    monkeypatch.setattr(
        jira_sync_cursor_service,
        "save_jira_qa_sync_state",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("dry run wrote state")),
    )

    report = bootstrap_jira_sync_cursor(
        "DXML",
        dry_run=True,
        records=[_record("DXML-1::summary::0", "DXML-1", "2026-01-01T00:00:00Z")],
        collection_count=1,
        include_sql=False,
    )

    assert report["valid"] is True
    assert report["applied"] is False
    assert report["proposed_state"]["last_indexed_jira_key"] == "DXML-1"
    assert report["proposed_state"]["total_indexed"] == 1
    assert report["proposed_state"]["last_successful_sync_time"] == "2025-12-31T00:00:00+00:00"
    assert report["proposed_state"]["bootstrap_overlap_hours"] == 24


def test_bootstrap_apply_persists_and_validates_atomically(monkeypatch, tmp_path):
    state_path = tmp_path / "project-DXML.json"
    monkeypatch.setattr(jira_sync_state, "_state_path", lambda _sid: state_path)

    report = bootstrap_jira_sync_cursor(
        "DXML",
        sync_state_id="project:DXML",
        dry_run=False,
        records=[_record("DXML-7::summary::0", "DXML-7", "2026-08-07T12:30:00Z")],
        collection_count=1,
        include_sql=False,
    )

    assert report["applied"] is True
    assert report["valid"] is True
    assert report["state"]["last_indexed_jira_key"] == "DXML-7"
    assert report["state"]["cursor_source"] == "indexed_corpus_bootstrap"
    assert report["state"]["historical_backfill_complete"] is False
    assert state_path.is_file()
    assert list(tmp_path.glob("*.tmp")) == []


def test_force_bootstrap_never_regresses_newer_existing_watermark(monkeypatch):
    prior = JiraQaIndexSyncState(
        last_successful_sync_time="2027-01-01T00:00:00Z",
        last_indexed_jira_key="DXML-99",
        total_indexed=99,
        cursor_source="jira_search_index",
    )
    monkeypatch.setattr(jira_sync_cursor_service, "load_jira_qa_sync_state", lambda _sid: prior)

    report = bootstrap_jira_sync_cursor(
        "DXML",
        dry_run=True,
        force=True,
        records=[_record("DXML-1::summary::0", "DXML-1", "2026-01-01T00:00:00Z")],
        collection_count=1,
        include_sql=False,
    )

    assert report["proposed_state"]["last_successful_sync_time"] == "2027-01-01T00:00:00+00:00"
    assert report["proposed_state"]["last_indexed_jira_key"] == "DXML-99"
    assert report["proposed_state"]["total_indexed"] == 99


def test_incremental_auto_bootstraps_instead_of_backfill(monkeypatch):
    from app.services import jira_qa_index_service

    empty = JiraQaIndexSyncState()
    valid = JiraQaIndexSyncState(
        last_successful_sync_time="2026-08-07T12:30:00Z",
        last_indexed_jira_key="DXML-7",
        total_indexed=7,
        cursor_source="indexed_corpus_bootstrap",
    )
    states = iter([empty, valid])
    monkeypatch.setattr(jira_qa_index_service, "load_jira_qa_sync_state", lambda _sid: next(states))
    monkeypatch.setattr(
        jira_sync_cursor_service,
        "bootstrap_jira_sync_cursor",
        lambda *args, **kwargs: {"valid": True, "applied": True},
    )
    monkeypatch.setattr(
        jira_qa_index_service,
        "index_jira_project_backfill",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected backfill")),
    )
    captured: dict = {}

    def fake_index(jql, **kwargs):
        captured["jql"] = jql
        captured["kwargs"] = kwargs
        return {"issues_indexed": 0, "chunks": 0}

    monkeypatch.setattr(jira_qa_index_service, "index_jql_to_chroma", fake_index)
    monkeypatch.setenv("JIRA_QA_AUTO_BOOTSTRAP_CURSOR", "true")

    result = jira_qa_index_service.index_jira_project_incremental("DXML", limit=100)

    assert 'updated >= "2026-08-07 12:30"' in captured["jql"]
    assert captured["kwargs"]["persist_sync_state"] is True
    assert result["cursor_bootstrap"]["applied"] is True


def test_admin_cursor_bootstrap_endpoint_delegates_safely(monkeypatch):
    from app.api.v1.routes import admin

    captured: dict = {}

    def fake_bootstrap(project_key, **kwargs):
        captured["project_key"] = project_key
        captured.update(kwargs)
        return {"available": True, "valid": True, "applied": True}

    monkeypatch.setattr(
        "app.services.jira_sync_cursor_service.bootstrap_jira_sync_cursor",
        fake_bootstrap,
    )
    request = admin.JiraSyncCursorBootstrapRequest(
        project_key="DXML",
        dry_run=False,
        force=False,
    )

    result = admin.bootstrap_jira_rag_sync_cursor(request, user=object())

    assert result["valid"] is True
    assert captured == {
        "project_key": "DXML",
        "sync_state_id": None,
        "dry_run": False,
        "force": False,
    }
