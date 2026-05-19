"""Jira QA RAG tests."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np

from app.services.jira_qa_automation_rubric import score_automation_fit
from app.services.jira_qa_chunking_service import build_jira_qa_chunks
from app.services.jira_qa_intent_service import classify_jira_qa_intent_rules
from app.services.jira_qa_retrieval_service import semantic_search_jira_qa


def test_intent_rules_related():
    assert classify_jira_qa_intent_rules("Give me related tickets for paste in editor", None) == "related_tickets"


def test_intent_rules_gherkin():
    assert classify_jira_qa_intent_rules("Write behave scenarios", None) == "gherkin_generation"


def test_intent_rules_uac():
    assert classify_jira_qa_intent_rules("What QA points for UAC?", None) == "uac_preparation"


def test_chunking_long_description_emits_windows(monkeypatch):
    monkeypatch.setenv("JIRA_SMART_CHUNKING", "false")
    long_desc = "DITA body paragraph.\n\n" * 400
    assert len(long_desc) > 6000
    issue = {
        "fields": {
            "summary": "Long body",
            "description": long_desc,
            "issuetype": {"name": "Bug"},
            "status": {"name": "Open"},
            "priority": {"name": "High"},
            "components": [],
            "labels": [],
            "updated": "2024-01-01T00:00:00.000+0000",
        }
    }
    chunks = build_jira_qa_chunks("GUIDES-99", issue, comments=[], linked_issues=[])
    types = [c["metadata"]["chunk_type"] for c in chunks]
    assert types.count("description_long_part") >= 1


def test_chunking_emits_types(monkeypatch):
    monkeypatch.setenv("JIRA_SMART_CHUNKING", "false")
    issue = {
        "fields": {
            "summary": "PDF publish fails for map",
            "description": "Expected: PDF generates.\nActual: error 500.\nSteps to reproduce: 1. open map",
            "issuetype": {"name": "Bug"},
            "status": {"name": "Open"},
            "priority": {"name": "High"},
            "components": [{"name": "Publishing"}],
            "labels": ["customer-abc"],
            "updated": "2024-01-01T00:00:00.000+0000",
            "attachment": [{"filename": "error.log", "size": 12, "mimeType": "text/plain"}],
        }
    }
    chunks = build_jira_qa_chunks("GUIDES-1", issue, comments=[], linked_issues=[])
    types = {c["metadata"]["chunk_type"] for c in chunks}
    assert "full_ticket_summary" in types
    assert "similar_ticket_signals" in types
    assert "attachment_log_signals" in types


def test_automation_rubric_range():
    text = """
    Steps to reproduce:
    1. Open Web Editor
    2. Save map
    Expected: success
    Actual: API returns 500 with JSON error
    Regression in publish flow for customer content
    """
    r = score_automation_fit(text)
    assert 0 <= r.score_0_10 <= 10
    assert r.fit_label in {"Yes", "No", "Partial"}


@patch("app.services.jira_retrieval_service.query_collection")
@patch("app.services.jira_qa_retrieval_service.embed_query")
@patch("app.services.jira_qa_retrieval_service.is_embedding_available")
@patch("app.services.jira_qa_retrieval_service.is_chroma_available")
def test_semantic_search_dedupes_by_jira_key(mock_chroma, mock_emb_avail, mock_embed, mock_q):
    mock_chroma.return_value = True
    mock_emb_avail.return_value = True
    mock_vec = MagicMock()
    mock_vec.tolist.return_value = [0.1, 0.2, 0.3]
    mock_embed.return_value = mock_vec
    mock_q.return_value = [
        {
            "id": "GUIDES-2::full_ticket_summary::0",
            "document": "aaa",
            "metadata": {"jira_key": "GUIDES-2", "chunk_type": "full_ticket_summary", "labels": "[]", "components": "[]", "title": "T", "customer": ""},
            "distance": 0.2,
        },
        {
            "id": "GUIDES-2::customer_problem::0",
            "document": "bbb",
            "metadata": {"jira_key": "GUIDES-2", "chunk_type": "customer_problem", "labels": "[]", "components": "[]", "title": "T", "customer": ""},
            "distance": 0.1,
        },
    ]
    hits = semantic_search_jira_qa("query", top_k=5, exclude_jira_key="GUIDES-1")
    assert len(hits) == 1
    assert hits[0]["jira_key"] == "GUIDES-2"


@patch("app.services.jira_retrieval_service.query_collection")
@patch("app.services.jira_qa_retrieval_service.embed_query")
@patch("app.services.jira_qa_retrieval_service.cache_get_embedding_vector")
@patch("app.services.jira_qa_retrieval_service.is_embedding_available")
@patch("app.services.jira_qa_retrieval_service.is_chroma_available")
def test_semantic_search_embedding_cache_hit_skips_embed(
    mock_chroma, mock_emb_avail, mock_cache_get, mock_embed, mock_q
):
    mock_chroma.return_value = True
    mock_emb_avail.return_value = True
    mock_cache_get.return_value = [0.4, 0.5, 0.6]
    mock_q.return_value = []
    semantic_search_jira_qa("cached query text", top_k=2)
    mock_cache_get.assert_called()
    mock_embed.assert_not_called()


def test_suggested_questions_when_llm_off():
    from app.services.jira_qa_synthesis_service import generate_suggested_questions
    from app.services.llm_service import is_llm_available

    if is_llm_available():
        return
    qs = asyncio.run(
        generate_suggested_questions(
            jira_key="GUIDES-99",
            user_message="hi",
            answer_preview="ans",
            intent="ticket_summary",
        )
    )
    assert any("GUIDES-99" in q for q in qs)


@patch("app.services.jira_qa_index_service.fetch_issue_bundle")
@patch("app.services.jira_qa_index_service.is_chroma_available", return_value=True)
@patch("app.services.jira_qa_index_service.is_embedding_available", return_value=True)
@patch("app.services.jira_qa_index_service.embed_texts_batched")
@patch("app.services.jira_qa_index_service.add_documents", return_value=True)
def test_index_jql_to_chroma_stats_partial_failure(
    mock_add, mock_emb, mock_emb_avail, mock_chroma, mock_bundle, monkeypatch
):
    from app.services.jira_qa_index_service import index_jql_to_chroma

    # Isolate from DB + smart chunking so partial-index stats stay deterministic.
    monkeypatch.setenv("JIRA_SQL_ENRICHMENT", "false")
    monkeypatch.setenv("JIRA_SMART_CHUNKING", "false")

    def _bundle(client, key: str):
        if key == "GUIDES-1":
            return {
                "issue": {
                    "fields": {
                        "summary": "Ok",
                        "description": "desc",
                        "issuetype": {"name": "Bug"},
                        "status": {"name": "Open"},
                        "priority": {"name": "High"},
                        "components": [],
                        "labels": [],
                        "updated": "2024-01-01T00:00:00.000+0000",
                    }
                },
                "comments": [],
                "linked_issues": [],
            }
        raise RuntimeError("permission denied")

    mock_bundle.side_effect = _bundle

    jc = MagicMock()
    jc.base_url = "https://jira.example"
    jc.username = "u"
    jc.password = "p"
    jc.email = ""
    jc.api_token = ""
    def _search_page(jql, start_at=0, page_size=100):
        _ = (jql, page_size)
        if start_at == 0:
            return (
                [
                    {"key": "GUIDES-1", "fields": {"updated": "2024-01-01T00:00:00.000+0000"}},
                    {"key": "GUIDES-2", "fields": {"updated": "2024-01-02T00:00:00.000+0000"}},
                ],
                500,
            )
        return [], 500

    jc.search_issues_key_page.side_effect = _search_page

    rows = build_jira_qa_chunks(
        "GUIDES-1",
        _bundle(None, "GUIDES-1")["issue"],
        comments=[],
        linked_issues=[],
    )
    n = len(rows)
    mock_emb.return_value = np.ones((n, 4), dtype=np.float32)

    out = index_jql_to_chroma("project = GUIDES", limit=10, jira_client=jc)

    assert out.get("jira_total") == 500
    assert out["keys_returned"] == 2
    assert out["keys_requested"] == 10
    assert out["issues_indexed"] == 1
    assert out["indexed_issues"] == 1
    assert out["indexed_issues"] == out["issues_indexed"]
    assert out["indexed_issues"] != out["keys_returned"]
    assert out["issues_failed"] == 1
    assert out["errors_count"] == 1
    assert out["chunks"] == n
    assert out["chunks_avg_per_indexed_issue"] == round(n / 1, 3)
    assert "collection" in out
    json.dumps(out)


def test_jira_rag_validate_key_api():
    from fastapi.testclient import TestClient
    from app.main import app

    with patch("app.api.v1.routes.jira_rag.index_jql_to_chroma", return_value={"chunks": 0}):
        client = TestClient(app)
        r = client.post(
            "/api/v1/jira-rag/index",
            json={"jql": "project = FOO", "limit": 1, "force_reindex": False},
            headers={"Authorization": "Bearer test-token"},
        )
        assert r.status_code == 200

    r2 = client.get("/api/v1/jira-rag/bad-key/summary", headers={"Authorization": "Bearer test-token"})
    assert r2.status_code == 400


def test_recover_failed_jira_keys_builds_key_jql(monkeypatch):
    from app.services.jira_qa_index_service import recover_failed_jira_keys
    from app.services.jira_sync_state import JiraQaIndexSyncState

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "app.services.jira_qa_index_service.load_jira_qa_sync_state",
        lambda _sid: JiraQaIndexSyncState(failed_keys=["GUIDES-1", "GUIDES-2"]),
    )

    def _fake_index(jql, **kwargs):
        captured["jql"] = jql
        captured["kwargs"] = kwargs
        return {"issues_indexed": 1, "issues_failed": 0, "chunks": 4}

    monkeypatch.setattr("app.services.jira_qa_index_service.index_jql_to_chroma", _fake_index)

    out = recover_failed_jira_keys("project:GUIDES", limit=1)

    assert 'key in ("GUIDES-1")' in captured["jql"]
    assert captured["kwargs"]["persist_sync_state"] is True
    assert out["recovery"]["requested_failed_keys"] == ["GUIDES-1"]


@patch("app.services.jira_qa_synthesis_service.generate_text", new_callable=AsyncMock)
def test_suggested_questions_dynamic_from_llm(mock_gen):
    from app.services.jira_qa_synthesis_service import generate_suggested_questions
    from app.services import jira_qa_synthesis_service as m

    mock_gen.return_value = '{"questions": ["What about GUIDES-777 baseline impact?", "API vs UI for publish?"]}'
    with patch.object(m, "is_llm_available", return_value=True):
        qs = asyncio.run(
            generate_suggested_questions(
                jira_key="GUIDES-777",
                user_message="test",
                answer_preview="done",
                intent="testing_scope",
            )
        )
    assert any("GUIDES-777" in q for q in qs)
    assert len(qs) >= 2


def test_dynamic_questions_skip_avoid_normalized():
    from app.services import dynamic_question_engine as dyn_mod
    from app.services.dynamic_question_engine import DynamicQuestionEngine

    avoid = {"which aem guides versions are in scope?"}

    async def _run():
        eng = DynamicQuestionEngine()
        with patch.object(dyn_mod, "is_llm_available", return_value=False):
            return await eng.next_questions(
                answer="ok",
                reasoning={},
                gaps={"gaps": []},
                risk={"risk_areas": []},
                history=[],
                intent="testing_scope",
                avoid_normalized=avoid,
            )

    qs = asyncio.run(_run())
    assert qs
    assert qs[0].startswith("What exact acceptance")


def test_jira_index_search_error_403_message():
    import httpx

    from app.services.jira_qa_index_service import _format_jira_index_search_error

    req = httpx.Request("GET", "https://jira.example/rest/api/2/search")
    resp = httpx.Response(403, request=req)
    exc = httpx.HTTPStatusError("forbidden", request=req, response=resp)
    msg = _format_jira_index_search_error(exc)
    assert "403" in msg
    assert "JIRA_PROJECT_KEY" in msg
