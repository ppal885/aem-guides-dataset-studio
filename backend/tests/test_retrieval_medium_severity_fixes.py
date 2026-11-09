"""Regression tests for the medium-severity retrieval/RAG fixes."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.services import embedding_service as embeddings
from app.services import jira_qa_retrieval_service as jqr
from app.services import vector_store_service as vs
from app.services.doc_retriever_service import _semantic_score_from_distance
from app.services.jira_retrieval_service import _metadata_where_plan
from app.services.rag_query_rewrite_service import drop_negative_term_docs
from app.services.retrieval_context_assembly_service import _rerank_docs_for_xml_examples


# --- Chroma collection discovery ------------------------------------------------------------


def test_collection_exists_accepts_chroma_06_name_strings():
    client = SimpleNamespace(list_collections=lambda: ["jira_qa", "aem_guides"])
    assert vs._collection_exists(client, "jira_qa") is True
    assert vs._collection_exists(client, "dita_spec") is False


def test_collection_exists_still_accepts_collection_objects():
    client = SimpleNamespace(list_collections=lambda: [SimpleNamespace(name="jira_qa")])
    assert vs._collection_exists(client, "jira_qa") is True


# --- component + customer query plan --------------------------------------------------------


def test_component_plan_adds_customer_passes_inside_the_component_filter():
    plan = _metadata_where_plan(
        domain=None, sub_domain=None, issue_type=None,
        customer_names=["Cisco"], components=["Editor"],
    )
    assert plan[0] == {"label": "component_membership_filtered", "where": {"component_editor": True}}
    assert plan[1] == {
        "label": "component_customer_filtered",
        "where": {"$and": [{"component_editor": True}, {"customer": "Cisco"}]},
    }
    # Never an unfiltered or customer-only pass: components stay strict.
    assert all("component_" in str(p["where"]) for p in plan)


def test_multi_component_customer_pass_uses_or():
    plan = _metadata_where_plan(
        domain=None, sub_domain=None, issue_type=None,
        customer_names=["Cisco"], components=["Editor", "Publishing"],
    )
    customer_pass = [p for p in plan if p["label"] == "component_customer_filtered"][0]
    assert customer_pass["where"]["$and"][0] == {
        "$or": [{"component_editor": True}, {"component_publishing": True}]
    }


# --- related tickets for an issue with no indexed text --------------------------------------


def test_related_tickets_does_not_search_with_a_bare_jira_key(monkeypatch):
    monkeypatch.setattr(jqr, "get_chunks_for_jira_key", lambda key, **_: [])
    search = Mock()
    monkeypatch.setattr(jqr, "semantic_search_jira_qa", search)
    hits, signal = jqr.related_tickets_for_issue("GUIDES-12345")
    assert hits == []
    assert signal == "GUIDES-12345"
    search.assert_not_called()


def test_signal_text_falls_back_to_any_indexed_chunk():
    rows = [{"chunk_type": "comments_discussion", "document": "Conref breaks after move."}]
    assert jqr._signal_text_from_rows(rows) == "Conref breaks after move."
    rows.append({"chunk_type": "full_ticket_summary", "document": "Summary text"})
    assert jqr._signal_text_from_rows(rows) == "Summary text"


# --- customer aliases that are ordinary words -----------------------------------------------


def test_common_words_are_not_customers():
    text = "pan the canvas, swift response, crown element, abs value, dow of week, intel on the ey"
    assert jqr._customer_names_from_query(text) == []


def test_ambiguous_aliases_still_match_in_their_written_form():
    assert sorted(jqr._customer_names_from_query("Swift and PAN publishing issues")) == ["PAN", "Swift"]
    assert jqr._customer_names_from_query("crown equipment pdf bug") == ["Crown Equipment"]


# --- negative terms and gold-example ranking ------------------------------------------------


def test_negative_terms_drop_docs_unless_user_asked_about_them():
    docs = [{"title": "Keyref resolution", "snippet": "keys"}, {"title": "Tables", "snippet": "tgroup"}]
    assert drop_negative_term_docs(docs, ["keyref resolution"], "table alignment") == [docs[1]]
    assert drop_negative_term_docs(docs, ["keyref resolution"], "keyref resolution in tables") == docs


def test_gold_examples_keep_retrieval_relevance():
    relevant = {"snippet": "<table><tgroup>", "_retrieval_rank": 0}
    noisy = {"snippet": "<topic>" + "<p>x</p>" * 80, "_retrieval_rank": 5}
    assert _rerank_docs_for_xml_examples([noisy, relevant])[0] is relevant


def test_semantic_score_from_distance():
    assert _semantic_score_from_distance(0.25) == 0.75
    assert _semantic_score_from_distance(None) == 0.0
    assert _semantic_score_from_distance(float("nan")) == 0.0
    assert _semantic_score_from_distance(1.5) == 0.0


# --- Azure embeddings: input cap and bounded retry ------------------------------------------


def _azure(post):
    return patch.multiple(
        embeddings,
        _USE_AZURE_EMBEDDING=True,
        _AZURE_EMBED_ENDPOINT="https://embedding.invalid",
        _AZURE_EMBED_KEY="nonfunctional-unit-test-placeholder",
        _AZURE_EMBED_MODEL="m",
        _AZURE_EMBED_VERSION="v",
    ), patch.dict(sys.modules, {"requests": SimpleNamespace(post=post)})


def _ok(n=1):
    r = Mock(ok=True, status_code=200)
    r.json.return_value = {"data": [{"index": i, "embedding": [0.1]} for i in range(n)]}
    return r


def test_azure_retries_rate_limit_then_succeeds():
    limited = Mock(ok=False, status_code=429, headers={"Retry-After": "0"})
    post = Mock(side_effect=[limited, _ok()])
    a, b = _azure(post)
    with a, b, patch("time.sleep") as sleep:
        assert embeddings._try_azure_embedding(["one"]) == [[0.1]]
    assert post.call_count == 2
    sleep.assert_called_once_with(0.0)


def test_azure_does_not_retry_client_errors():
    post = Mock(return_value=Mock(ok=False, status_code=400, headers={}))
    a, b = _azure(post)
    with a, b, patch("time.sleep"):
        assert embeddings._try_azure_embedding(["one"]) is None
    assert post.call_count == 1


def test_azure_retry_is_bounded():
    post = Mock(return_value=Mock(ok=False, status_code=503, headers={}))
    a, b = _azure(post)
    with a, b, patch("time.sleep"):
        assert embeddings._try_azure_embedding(["one"]) is None
    assert post.call_count == embeddings._AZURE_MAX_ATTEMPTS


def test_azure_caps_over_long_inputs():
    post = Mock(return_value=_ok())
    a, b = _azure(post)
    with a, b:
        embeddings._try_azure_embedding(["x" * 100_000])
    assert len(post.call_args.kwargs["json"]["input"][0]) == embeddings._AZURE_MAX_INPUT_CHARS
