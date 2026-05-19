"""RAG readiness and compact chat RAG query cap."""

from __future__ import annotations

from unittest.mock import patch

from app.services.vector_store_service import (
    CHROMA_COLLECTION_ENTERPRISE_QA,
    CHROMA_COLLECTION_JIRA_QA,
)


@patch("app.services.doc_retriever_service._load_chunks", return_value=[])
@patch("app.services.doc_retriever_service.get_collection_count")
@patch("app.services.doc_retriever_service.is_chroma_available", return_value=True)
def test_check_rag_readiness_jira_only_any_ready_false(_mock_chroma, mock_get_count, _mock_load):
    """any_ready must stay False when only Jira QA is indexed (generate-from-text gate)."""

    def _gc(coll: str) -> int:
        if coll == CHROMA_COLLECTION_JIRA_QA:
            return 50
        return 0

    mock_get_count.side_effect = _gc

    from app.services.doc_retriever_service import check_rag_readiness

    r = check_rag_readiness()
    assert r["jira_qa_ready"] is True
    assert r["enterprise_qa_ready"] is False
    assert r["any_ready"] is False
    assert "crawl-aem-guides" in r["message"]


@patch("app.services.doc_retriever_service._load_chunks", return_value=[{"url": "https://experienceleague.adobe.com/x"}])
@patch("app.services.doc_retriever_service.get_collection_count")
@patch("app.services.doc_retriever_service.is_chroma_available", return_value=True)
def test_check_rag_readiness_flags_when_aem_json_fallback(_mock_chroma, mock_get_count, _mock_load):
    def _gc(coll: str) -> int:
        if coll == CHROMA_COLLECTION_ENTERPRISE_QA:
            return 3
        return 0

    mock_get_count.side_effect = _gc

    from app.services.doc_retriever_service import check_rag_readiness

    r = check_rag_readiness()
    assert r["aem_guides_ready"] is True
    assert r["any_ready"] is True
    assert r["jira_qa_ready"] is False
    assert r["enterprise_qa_ready"] is True
    assert "jira-rag" in r["message"].lower()


@patch("app.services.chat_service.retrieve_claude_code_context", return_value="")
@patch("app.services.chat_service.retrieve_tenant_examples", return_value=[])
@patch("app.services.chat_service.retrieve_tenant_context", return_value=[])
@patch("app.services.chat_service.retrieve_dita_knowledge", return_value=[])
@patch("app.services.chat_service.retrieve_relevant_docs", return_value=[])
def test_build_rag_context_truncates_query(mock_docs, _dita, _tenant, _ex, _claude):
    from app.services import chat_service as cs

    cap = 200
    with patch.object(cs, "RAG_QUERY_MAX_CHARS", cap):
        long_q = "z" * (cap + 500)
        out = cs._build_rag_context(long_q, tenant_id="kone")
    assert isinstance(out, str)
    mock_docs.assert_called_once()
    passed = mock_docs.call_args[0][0]
    assert len(passed) == cap
    assert passed == "z" * cap
