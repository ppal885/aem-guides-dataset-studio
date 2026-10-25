"""Regression tests for the retrieval and grounding fixes from the RAG review.

Each test names the behaviour that was wrong before: a filter that let the wrong customer through, a
score that depended on unrelated earlier requests, a rerank that counted stop words, evidence that was
cut before ranking, and a verifier that called an answer with no evidence "partial".
"""
from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from app.rag.hybrid_search import HybridJiraSearch
from app.rag.metadata_filtering import JiraMetadataCriteria, matches_metadata, metadata_contains
from app.services import corrective_rag_service, grounding_service
from app.services import dita_knowledge_retriever as dita
from app.services import jira_history_search_service as history
from app.services import jira_retrieval_service as retrieval
from app.services.corrective_rag_service import RetrievalCandidate
from app.services.dita_pdf_index_service import _page_label
from app.services.dita_spec_index_service import _chunk_identity
from app.services.doc_pdf_index_service import CHUNK_SIZE, _chunk_pages, _file_hash
from app.services.jira_history_match_service import build_historical_match_contract
from app.evidence_gateway import rag_adapter
from app.evidence_gateway.config import CorpusConfig, EvidenceGatewaySettings


# --- metadata filter: the requested value must be inside the metadata, never the reverse ----------------

def test_short_label_in_metadata_does_not_satisfy_a_customer_filter():
    meta = {"customer": "Acme Corp", "labels": '["Triaged","ID","Bugs"]'}
    assert matches_metadata(JiraMetadataCriteria(customer="Fidelity"), meta) is False
    assert matches_metadata(JiraMetadataCriteria(customer="Acme"), meta) is True
    assert metadata_contains("EY", {"labels": '["keyref"]'}, fields=("labels",)) is False
    assert metadata_contains("Cloud", {"labels": '["cloud_ready"]'}, fields=("labels",)) is True


# --- hybrid search: the source ticket is excluded and an unfiltered fallback says so ---------------------

class _FakeSemantic:
    def __init__(self, hits):
        self.hits = hits
        self.calls = []

    def search(self, query, criteria, *, top_k):
        self.calls.append((query, top_k))
        return list(self.hits)


def test_hybrid_fallback_reports_when_no_metadata_filter_applied():
    hits = [{"jira_key": "GUIDES-1", "document": "x", "metadata": {"issue_type": "Bug", "customer": "Acme"}, "score": 0.9}]
    search = HybridJiraSearch(semantic_search=_FakeSemantic(hits))
    out = search.search(JiraMetadataCriteria(customer="Zebra", issue_type="Story"), limit=5)
    assert out.hits, "callers still get the best unfiltered candidates"
    assert out.semantic_fallback_used is True
    assert out.metadata_filter_used is False, "no constraint survived, and the output must not claim one did"
    assert out.debug["fallback_reason"] == "all_metadata_filters_relaxed"

    relaxed_only = HybridJiraSearch(semantic_search=_FakeSemantic(hits))
    out = relaxed_only.search(JiraMetadataCriteria(customer="Zebra", issue_type="Bug"), limit=5)
    assert out.metadata_filter_used is True
    assert out.debug["fallback_reason"] == "metadata_filter_returned_zero_candidates"


def test_copilot_semantic_search_excludes_the_source_jira(monkeypatch):
    from app.rag import semantic_search

    seen = {}

    def fake(query, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(semantic_search, "semantic_search_jira_qa", fake)
    semantic_search.SemanticJiraSearch().search("q", JiraMetadataCriteria(source_jira_key="GUIDES-123"), top_k=5)
    assert seen["exclude_jira_key"] == "GUIDES-123"


# --- history match: stop words are not "specific shared terms" -------------------------------------------

def test_stopwords_do_not_qualify_an_unrelated_verified_fix():
    result = build_historical_match_contract(
        "The toolbar is not visible when the user opens a topic and the save button is disabled",
        {
            "summary": "Images are missing from the PDF and the index is empty",
            "root_cause": "The PDF index was not generated and the images were not copied",
            "learning": {"is_verified_fix": True},
        },
    )
    assert result["qualified"] is False
    assert not ({"and", "the", "not", "was"} & set(result["shared_specific_terms"]))

    related = build_historical_match_contract(
        "xref scope is dropped by the serializer",
        {"summary": "Published xref loses scope", "root_cause": "Scope omitted by the shared serializer",
         "learning": {"is_verified_fix": True}},
    )
    assert related["qualified"] is True


# --- customer matching: whole names, the same rule in retrieval and in the history post-filter ----------

def test_customer_names_match_requires_a_whole_name():
    assert retrieval.customer_names_match("ciena", "ciena corporation")
    assert retrieval.customer_names_match("Zebra Technologies", "zebra")
    assert retrieval.customer_names_match("Ciena", "ciena")
    assert not retrieval.customer_names_match("ey", "honeywell")
    assert not retrieval.customer_names_match("gm", "pgm")
    assert not retrieval.customer_names_match("dow", "dow jones"), "three letters is too short to contain"
    assert not retrieval.customer_names_match("", "acme")


def test_history_post_filter_keeps_alias_matches_that_retrieval_accepted():
    assert history._customer_matches("Ciena", "Ciena Corporation")
    assert history._customer_matches("ciena corporation", "Ciena")
    assert not history._customer_matches("EY", "Honeywell")


def test_metadata_match_details_customer_overlap_is_not_a_substring_match():
    meta = {"customer": "Honeywell", "enrich_customers": '["Honeywell"]'}
    wrong = retrieval._metadata_match_details(meta, domain=None, dita_entities=[], affected_outputs=[],
                                              customer_names=["EY"])
    assert wrong["customer_overlap"] == []
    right = retrieval._metadata_match_details(meta, domain=None, dita_entities=[], affected_outputs=[],
                                              customer_names=["Honeywell Inc"])
    assert right["customer_overlap"] == ["honeywell inc"] or right["customer_overlap"], right


# --- recent-repeat penalty: no process-global state in scores ----------------------------------------------

def test_recent_penalty_ignores_the_shared_deque():
    retrieval._RECENT_RETURNED_JIRA_KEYS.append("GUIDES-1")
    assert retrieval._recent_penalty("GUIDES-1", None) == 0.0
    assert retrieval._recent_penalty("GUIDES-1", ["GUIDES-1"]) == retrieval.JIRA_RECENT_REPEAT_PENALTY
    assert retrieval._recent_penalty("GUIDES-1", []) == 0.0


# --- DITA hybrid rerank: whole-word, distinct, stop-word free, on the rank scale ---------------------------

def test_dita_rerank_tokens_drop_stopwords_short_and_duplicate_terms():
    tokens = dita._rerank_tokens("How do I define a key with keydef in a DITA map so the keyref resolves in the map?")
    assert "keydef" in tokens and "keyref" in tokens
    assert "the" not in tokens and "in" not in tokens and "dita" not in tokens
    assert tokens.count("map") == 1


def test_dita_rerank_keeps_the_semantic_leader_over_a_long_generic_seed_chunk(monkeypatch):
    keydef = {"element_name": "keydef", "content_type": "spec",
              "text_content": "The keydef element defines a key. A keyref on a topic resolves to it."}
    keyref = {"element_name": "keyref", "content_type": "spec",
              "text_content": "The keyref attribute refers to a key defined by keydef."}
    seed = {"element_name": "map", "content_type": "seed",
            "text_content": " ".join(["The map is in the other theme of the thing, defining"] * 30)}
    monkeypatch.setattr(dita, "USE_DITA_HYBRID_SEARCH", True)
    monkeypatch.setattr(dita, "_retrieve_dita_chromadb", lambda *a, **k: [keydef, keyref])
    monkeypatch.setattr(dita, "_search_seed", lambda *a, **k: [seed])
    out = dita.retrieve_dita_knowledge(
        "How do I define a key with keydef in a DITA map so that the keyref resolves correctly?", k=2)
    assert [c["element_name"] for c in out] == ["keydef", "keyref"]


# --- indexers --------------------------------------------------------------------------------------------

def test_pdf_page_anchor_is_one_based_and_keeps_the_first_page():
    assert _page_label(0) == "1"
    assert _page_label(4) == "5"
    assert _page_label("") == ""
    assert _page_label(None) == ""
    assert _page_label("7") == "7"


def test_spec_chunk_identity_is_deterministic_per_content():
    a = {"source_url": "u", "element_name": "keydef", "content_type": "spec", "text_content": "t"}
    assert _chunk_identity(a) == _chunk_identity(dict(a))
    assert _chunk_identity(a) != _chunk_identity({**a, "text_content": "other"})


def test_pdf_file_hash_covers_the_whole_file(tmp_path):
    first = tmp_path / "a.pdf"
    second = tmp_path / "b.pdf"
    shared = b"%PDF-1.4 " + b"x" * (600 * 1024)
    first.write_bytes(shared + b"version one")
    second.write_bytes(shared + b"version two")
    assert _file_hash(first) != _file_hash(second)
    assert _file_hash(first) == hashlib.sha256(first.read_bytes()).hexdigest()[:24]


def test_documents_indexed_under_the_legacy_hash_are_still_recognised(tmp_path, monkeypatch):
    from app.services import doc_pdf_index_service as svc

    pdf = tmp_path / "manual.pdf"
    pdf.write_bytes(b"%PDF-1.4 manual " * 100)
    legacy = svc._legacy_file_hash(pdf)
    monkeypatch.setattr(svc, "_load_registry", lambda: {f"kone:{legacy}": {"file_hash": legacy, "filename": "manual.pdf"}})
    assert svc.is_already_indexed(pdf, "kone") == {"file_hash": legacy, "filename": "manual.pdf"}
    assert svc.is_already_indexed(pdf, "other") is None


def test_pdf_chunker_records_the_first_heading_and_cuts_on_whitespace():
    pages = [{"page_num": 1, "has_text": True, "text": "1 Introduction\n" + "word " * 700}]
    chunks = _chunk_pages(pages, {"source": "pdf_upload"})
    assert chunks and chunks[0]["section"] == "1 Introduction"
    for chunk in chunks:
        assert not chunk["text"].endswith("wor"), "a cut inside a word"
    unbroken = [{"page_num": 1, "has_text": True, "text": "A" * (CHUNK_SIZE * 6)}]
    assert all(len(c["text"]) >= 80 for c in _chunk_pages(unbroken, {})), "separator-less text still chunks"


# --- corrective RAG ---------------------------------------------------------------------------------------

def test_prioritised_candidates_keep_tenant_sources_ahead_of_bulk_docs():
    docs = [RetrievalCandidate(source="aem_guides", label="Doc", text=f"doc {i}") for i in range(10)]
    spec = [RetrievalCandidate(source="dita_spec", label="Spec", text=f"spec {i}") for i in range(6)]
    tenant = [RetrievalCandidate(source="tenant_context", label="Tenant", text="tenant rule")]
    example = [RetrievalCandidate(source="tenant_examples", label="Example", text="approved topic")]
    kept = corrective_rag_service._prioritised_candidates(docs + spec + tenant + example)
    assert kept[0].source == "tenant_context" and kept[1].source == "tenant_examples"
    assert len(kept) == corrective_rag_service.MAX_RESULT_CANDIDATES
    assert [c.text for c in kept if c.source == "aem_guides"] == [f"doc {i}" for i in range(10)], "stable order"


@pytest.mark.anyio
async def test_query_variants_are_graded_against_the_seed_query(monkeypatch):
    graded: list[str] = []
    hit = [RetrievalCandidate(source="aem_guides", label="Doc", text="hover behaviour in the AEM Guides DITA editor")]
    monkeypatch.setattr(corrective_rag_service, "_retrieve_mode_candidates", lambda q, **k: list(hit))
    monkeypatch.setattr(corrective_rag_service, "_persist_trace", lambda *a, **k: None)
    monkeypatch.setattr(corrective_rag_service, "record_query_result", lambda *a, **k: None)

    async def no_llm(*a, **k):
        return ""

    monkeypatch.setattr(corrective_rag_service, "_llm_refined_query", no_llm)
    real_grade = corrective_rag_service._grade_candidates

    def spy(query, candidates, *, issue=None):
        graded.append(query)
        return real_grade(query, candidates, issue=issue)

    monkeypatch.setattr(corrective_rag_service, "_grade_candidates", spy)
    result = await corrective_rag_service.run_chat_corrective_rag("hover issue", tenant_id="kone")
    assert set(graded) == {"hover issue"}, "every candidate set is graded against what the user asked"
    assert result.correction_applied is False, "identical evidence is not a correction"


# --- grounding --------------------------------------------------------------------------------------------

def _candidate(source: str, text: str, title: str = ""):
    return SimpleNamespace(source=source, label=title or source, text=text, url="", metadata={"title": title}, score=0.0)


def test_spec_only_evidence_can_ground_an_answer():
    pack = grounding_service.build_evidence_pack(
        query="What does the conkeyref attribute do on a topicref",
        tenant_id="kone",
        candidates=[
            _candidate("dita_spec", "The conkeyref attribute on topicref resolves a key to the conref target.", "conkeyref"),
            _candidate("dita_spec", "conkeyref combines a key reference with a content reference on topicref.", "topicref"),
            _candidate("dita_spec", "A conkeyref attribute names a key and an optional element id.", "keys"),
        ],
    )
    assert pack.decision.status != "abstain", pack.decision.reason
    assert pack.decision.thin_evidence is False


@pytest.mark.anyio
async def test_substantive_draft_with_no_evidence_is_not_called_partial():
    pack = grounding_service.build_evidence_pack(query="enable baseline v2 on prem", tenant_id="kone", candidates=[])
    assert pack.decision.evidence_count == 0
    answer = await grounding_service.verify_grounded_answer(
        question="enable baseline v2 on prem",
        draft_answer="Open the configuration console, find the baseline settings and switch version two on.",
        evidence_pack=pack,
    )
    assert answer.grounding_status == "abstain"
    assert answer.citation_ids == []


# --- evidence gateway -------------------------------------------------------------------------------------

class _Collection:
    def __init__(self, rows):
        self.rows = rows

    def count(self):
        return len(self.rows)

    def get(self, ids=None, limit=None, include=None):
        rows = self.rows if ids is None else [r for r in self.rows if r["id"] in ids]
        return {"ids": [r["id"] for r in rows], "documents": [r["document"] for r in rows],
                "metadatas": [r["metadata"] for r in rows]}


class _Client:
    def __init__(self, collections):
        self.collections = collections

    def get_collection(self, name):
        return self.collections[name]


def _settings():
    settings = EvidenceGatewaySettings()
    settings.corpora = {
        "dita_spec": CorpusConfig("dita_spec", "dita_spec", "DITA", "specification"),
        "aem_guides": CorpusConfig("aem_guides", "aem_guides", "AEM", "documentation"),
    }
    return settings


def test_gateway_returns_several_chunks_of_one_document_and_applies_filters(monkeypatch):
    spec_rows = [
        {"id": f"spec_{i}", "document": f"topicref conkeyref rule {i}",
         "metadata": {"source_url": "https://docs.oasis-open.org/dita.pdf", "page": str(i), "version": "1.3"}}
        for i in range(6)
    ]
    aem_rows = [{"id": "aem_1", "document": "topicref in the map editor",
                 "metadata": {"url": "https://experienceleague.adobe.com/x", "version": "2024"}}]
    client = _Client({"dita_spec": _Collection(spec_rows), "aem_guides": _Collection(aem_rows)})
    monkeypatch.setattr(rag_adapter, "is_chroma_available", lambda: True)
    monkeypatch.setattr(rag_adapter, "is_embedding_available", lambda: False)
    monkeypatch.setattr(rag_adapter, "_get_client", lambda: client)
    settings = _settings()

    results = rag_adapter.search_knowledge("topicref conkeyref", ["dita_spec"], top_k=5, mode="exact", settings=settings)
    assert len(results) == 5, "chunks of one PDF are distinct results"

    by_type = rag_adapter.search_knowledge("topicref", ["dita_spec", "aem_guides"], top_k=10, mode="exact",
                                           settings=settings, source_types=["documentation"])
    assert {r.corpus for r in by_type} == {"aem_guides"}

    by_version = rag_adapter.search_knowledge("topicref", ["dita_spec", "aem_guides"], top_k=10, mode="exact",
                                              settings=settings, source_versions=["2024"])
    assert [r.chunk_id for r in by_version] == ["aem_1"]


def test_fetch_chunks_keeps_a_requested_chunk_selected_when_it_is_also_a_neighbour(monkeypatch):
    rows = {f"x_{i}": {"id": f"x_{i}", "document": f"chunk {i}", "metadata": {}} for i in range(4)}
    monkeypatch.setattr(rag_adapter, "_locate_chunk",
                        lambda chunk_id, corpora, settings: ("dita_spec", rows[chunk_id]) if chunk_id in rows else None)
    chunks, missing = rag_adapter.fetch_chunks(["x_1", "x_2"], neighbor_window=1, authorized_corpora={"dita_spec"},
                                               settings=_settings())
    assert missing == []
    flags = {c.chunk_id: c.selected for c in chunks}
    assert flags["x_1"] is True and flags["x_2"] is True
    assert flags["x_0"] is False and flags["x_3"] is False
    assert len(chunks) == 4
