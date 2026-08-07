from types import SimpleNamespace

from app.services.jira_rag_reconciliation_service import build_reconciliation_rows


def _issue(**changes):
    values = {
        "jira_key": "GUIDES-123",
        "summary": "Publishing queue remains blocked",
        "description": "A later output remains waiting.",
        "raw_text": "",
        "source_type": None,
        "status": "Closed",
        "resolution": "Fixed",
        "domain": "publishing",
        "components": ["AEM Sites"],
        "affected_outputs": ["AEM Sites"],
        "affected_features": ["Post-Publishing"],
        "dita_entities": ["ditamap"],
        "qa_risk_tags": ["workflow"],
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_reconciliation_rows_preserve_sql_chunks_and_deterministic_ids():
    chunks = [
        SimpleNamespace(chunk_type="comment_chunk", chunk_text="First"),
        SimpleNamespace(chunk_type="comment_chunk", chunk_text="Second"),
    ]

    rows = build_reconciliation_rows(_issue(), chunks)

    assert [row["chunk_id"] for row in rows] == [
        "GUIDES-123::comment_chunk::0",
        "GUIDES-123::comment_chunk::1",
    ]
    assert all(row["metadata"]["jira_key"] == "GUIDES-123" for row in rows)
    assert all(row["metadata"]["source_type"] == "jira" for row in rows)


def test_reconciliation_rows_create_safe_fallbacks_when_sql_chunks_are_absent():
    rows = build_reconciliation_rows(_issue(), [])

    assert {row["metadata"]["chunk_type"] for row in rows} == {
        "summary_chunk",
        "problem_chunk",
        "domain_entity_chunk",
    }
    assert all("GUIDES-123" in row["chunk_id"] for row in rows)


def test_reconciliation_endpoint_runs_admin_dry_run(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.jira_rag_reconciliation_service.reconcile_jira_sql_chroma",
        lambda **kwargs: {"dry_run": kwargs["dry_run"], "remaining_missing_keys": 0},
    )

    response = client.post(
        "/api/v1/admin/jira-rag/reconcile?dry_run=true",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == {"dry_run": True, "remaining_missing_keys": 0}


def test_reconciliation_endpoint_requires_admin(client, monkeypatch):
    monkeypatch.setenv(
        "AUTH_TOKENS_JSON",
        '{"writer-token":{"id":"writer","roles":["writer"],"allowed_tenants":["*"]}}',
    )

    response = client.post(
        "/api/v1/admin/jira-rag/reconcile?dry_run=true",
        headers={"Authorization": "Bearer writer-token"},
    )

    assert response.status_code == 403
