"""Tests for Jira index dashboard aggregates."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.jira_enrichment_models import JiraEnrichedIssue, JiraEnrichmentReviewQueue, JiraIssueChunk
from app.services.jira_index_dashboard_service import (
    append_jira_index_failure,
    build_jira_index_status,
    read_recent_failure_log,
)

_WORKDIR_ROOT = Path(__file__).resolve().parent / "_jira_index_dashboard_workdir"


def _unique_subdir() -> Path:
    _WORKDIR_ROOT.mkdir(parents=True, exist_ok=True)
    p = _WORKDIR_ROOT / uuid.uuid4().hex[:12]
    p.mkdir(parents=True, exist_ok=True)
    return p


def _session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=eng,
        tables=[
            JiraEnrichedIssue.__table__,
            JiraIssueChunk.__table__,
            JiraEnrichmentReviewQueue.__table__,
        ],
    )
    return sessionmaker(bind=eng, autoflush=False, autocommit=False)()


def test_status_counts_domain_and_missing_ea(monkeypatch):
    work = _unique_subdir()
    try:
        monkeypatch.setattr(
            "app.services.jira_index_dashboard_service.get_collection_count",
            lambda _name: 42,
        )
        monkeypatch.setattr(
            "app.services.jira_index_dashboard_service.is_chroma_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "app.services.jira_index_dashboard_service._sync_state_dir",
            lambda: work,
        )
        monkeypatch.setattr(
            "app.services.jira_index_dashboard_service._failure_log_path",
            lambda: work / "failure_log.jsonl",
        )

        s = _session()
        try:
            s.add(
                JiraEnrichedIssue(
                    jira_key="G-1",
                    domain="unknown",
                    customer_names=["Acme"],
                    expected_behavior="",
                    actual_behavior="broken",
                    indexed_at=None,
                )
            )
            s.add(
                JiraEnrichedIssue(
                    jira_key="G-2",
                    domain="publishing",
                    customer_names=["Acme", "Beta"],
                    expected_behavior="ok",
                    actual_behavior="ok",
                    indexed_at=None,
                )
            )
            s.add(JiraIssueChunk(jira_key="G-1", chunk_type="t", chunk_text="x", domain="unknown"))
            s.add(JiraIssueChunk(jira_key="G-2", chunk_type="t", chunk_text="y", domain="publishing"))
            s.commit()

            st = build_jira_index_status(s)
            assert st["total_enriched_jira"] == 2
            assert st["total_indexed_jira"] == 2
            assert st["total_chunks"] == 42
            assert st["totals"]["total_enriched_jira"] == 2
            assert st["totals"]["total_indexed_jira"] == 2
            assert st["totals"]["total_chunks"] == 42
            assert st["totals"]["total_chroma_chunk_documents"] == 42
            assert st["totals"]["total_indexed_jira_sql_distinct"] == 2
            assert st["unknown_domain_total"] == 1
            assert st["tickets_with_unknown_domain"] == 1
            assert st["tickets_missing_expected_or_actual"] == 1
            assert st["tickets_with_unknown_domain_sample"][0]["jira_key"] == "G-1"
            assert st["tickets_missing_expected_or_actual_sample"][0]["jira_key"] == "G-1"
            assert any(d["domain"] == "unknown" for d in st["domain_distribution"])
            names = {c["customer"] for c in st["customer_distribution"]}
            assert "Acme" in names
            assert "Beta" in names
        finally:
            s.close()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_failure_log_roundtrip(monkeypatch):
    work = _unique_subdir()
    try:
        monkeypatch.setattr(
            "app.services.jira_index_dashboard_service._failure_log_path",
            lambda: work / "failure_log.jsonl",
        )
        append_jira_index_failure(jira_key="G-9", error="boom", sync_state_id="project:GUIDES")
        append_jira_index_failure(jira_key="G-8", error="nope", sync_state_id="project:GUIDES")
        items = read_recent_failure_log(limit=10)
        assert len(items) == 2
        assert items[0]["jira_key"] in ("G-8", "G-9")
        path = work / "failure_log.jsonl"
        assert path.is_file()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["jira_key"] == "G-9"
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_recent_failures_payload_combines_logged_keys(monkeypatch):
    from app.services.jira_index_dashboard_service import build_recent_failures_payload

    work = _unique_subdir()
    try:
        monkeypatch.setattr(
            "app.services.jira_index_dashboard_service._failure_log_path",
            lambda: work / "failure_log.jsonl",
        )
        monkeypatch.setattr(
            "app.services.jira_index_dashboard_service.merged_failed_keys_from_sync_states",
            lambda cap=200: ["G-1"],
        )
        append_jira_index_failure(jira_key="G-2", error="boom", sync_state_id="project:GUIDES")
        payload = build_recent_failures_payload(limit=10)
        assert payload["total_failed_jira_keys"] == 2
        assert payload["failed_jira_keys"] == ["G-1", "G-2"]
        assert payload["failed_keys_from_failure_log_sample"] == ["G-2"]
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_admin_jira_index_dashboard_endpoints(client: TestClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.routes.admin.build_jira_index_status",
        lambda session: {
            "total_indexed_jira": 3,
            "total_enriched_jira": 4,
            "total_chunks": 12,
            "last_sync_time": "2026-05-15T10:00:00+00:00",
            "failed_jira_keys": ["G-1"],
            "domain_distribution": [{"domain": "publishing", "count": 3}],
            "customer_distribution": [{"customer": "Acme", "count": 2}],
            "tickets_with_unknown_domain": 1,
            "tickets_missing_expected_or_actual": 2,
            "totals": {},
        },
    )
    monkeypatch.setattr(
        "app.api.v1.routes.admin.build_recent_failures_payload",
        lambda limit=100: {"failed_jira_keys": ["G-1"], "total_failed_jira_keys": 1, "failure_log_items": []},
    )
    monkeypatch.setattr(
        "app.api.v1.routes.admin.index_jira_project_backfill",
        lambda project_key, **kwargs: {"mode": "backfill", "project_key": project_key, **kwargs},
    )
    monkeypatch.setattr(
        "app.api.v1.routes.admin.index_jira_project_incremental",
        lambda project_key, **kwargs: {"mode": "incremental", "project_key": project_key, **kwargs},
    )

    status = client.get("/api/v1/admin/jira-index/status", headers=auth_headers)
    assert status.status_code == 200
    assert status.json()["total_indexed_jira"] == 3

    failures = client.get("/api/v1/admin/jira-index/recent-failures?limit=5", headers=auth_headers)
    assert failures.status_code == 200
    assert failures.json()["failed_jira_keys"] == ["G-1"]

    backfill = client.post(
        "/api/v1/admin/jira-index/backfill",
        json={"project_key": "GUIDES", "limit": 5, "force_reindex": True},
        headers=auth_headers,
    )
    assert backfill.status_code == 200
    assert backfill.json()["mode"] == "backfill"
    assert backfill.json()["project_key"] == "GUIDES"
    assert backfill.json()["limit"] == 5
    assert backfill.json()["force_reindex"] is True

    incremental = client.post(
        "/api/v1/admin/jira-index/sync-incremental",
        json={"project_key": "GUIDES", "limit": 2},
        headers=auth_headers,
    )
    assert incremental.status_code == 200
    assert incremental.json()["mode"] == "incremental"
