"""Tests for AI dataset RAG status payloads."""

from __future__ import annotations

from unittest.mock import MagicMock


def test_rag_status_exposes_jira_and_dita_ot_metadata(client, auth_headers: dict, monkeypatch):
    dummy_session = MagicMock()
    monkeypatch.setattr(
        "app.api.v1.routes.ai_dataset.SessionLocal",
        lambda: dummy_session,
    )
    monkeypatch.setattr(
        "app.api.v1.routes.ai_dataset.get_authorized_tenant_id",
        lambda request, user, requested_tenant=None: requested_tenant,
    )
    monkeypatch.setattr(
        "app.services.vector_store_service.is_chroma_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.vector_store_service.get_collection_count",
        lambda name: {
            "aem_guides": 11,
            "dita_spec": 22,
            "dita_ot_github": 0,
            "jira_qa": 37,
        }.get(name, 0),
    )
    monkeypatch.setattr(
        "app.services.github_dita_examples_service.get_github_dita_rag_summary",
        lambda tenant_id=None: {
            "source": "stub github dita",
            "indexed_subtrees": 1,
            "merged_into_aem_guides_chunks": 5,
            "merge_into_aem_guides_enabled": True,
            "source_labels": ["oxygen"],
            "last_indexed_at": "2026-06-16T10:00:00+00:00",
            "populate_via": "POST /api/v1/ai/index-github-dita-examples",
        },
    )
    monkeypatch.setattr(
        "app.services.tavily_search_service.get_tavily_rag_status",
        lambda: {
            "configured": False,
            "chat_enabled": False,
            "hint": "stub",
        },
    )
    monkeypatch.setattr(
        "app.services.dita_ot_github_rag_service.get_dita_ot_github_reference_issues",
        lambda: (
            {"issue_number": 4768, "title": "one", "snippet": "one", "url": "https://github.com/dita-ot/dita-ot/issues/4768"},
            {"issue_number": 4769, "title": "two", "snippet": "two", "url": "https://github.com/dita-ot/dita-ot/issues/4769"},
        ),
    )
    monkeypatch.setattr(
        "app.services.jira_index_dashboard_service.build_jira_index_status",
        lambda session: {
            "total_indexed_jira": 12,
            "last_sync_time": "2026-06-16T11:00:00+00:00",
            "recent_failure_count": 2,
        },
    )
    monkeypatch.setattr(
        "app.services.jira_qa_index_service.resolve_jira_qa_project_key",
        lambda: "GUIDES",
    )
    monkeypatch.setattr(
        "app.services.jira_qa_index_service.default_jira_qa_backfill_limit",
        lambda: 1000,
    )

    response = client.get("/api/v1/ai/rag-status?tenant_id=default", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["jira_qa"]["chunk_count"] == 37
    assert payload["jira_qa"]["issue_count"] == 12
    assert payload["jira_qa"]["last_sync_time"] == "2026-06-16T11:00:00+00:00"
    assert payload["jira_qa"]["recent_failure_count"] == 2
    assert "multiple RAG chunks" in payload["jira_qa"]["count_scope"]
    assert payload["dita_ot_github"]["chunk_count"] == 0
    assert payload["dita_ot_github"]["reference_issue_count"] == 2
    assert "Curated reference issues" in payload["dita_ot_github"]["count_scope"]
    dummy_session.close.assert_called_once()
