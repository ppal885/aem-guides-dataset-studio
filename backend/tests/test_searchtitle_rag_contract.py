import json
from pathlib import Path

from app.services import chat_service, doc_retriever_service
from app.services.dita_query_interpreter import extract_attribute_names, extract_element_names


def _searchtitle_chunk_path() -> Path:
    return Path(__file__).resolve().parents[1] / "storage" / "manual_searchtitle_behavior_chunks.json"


def test_searchtitle_behavior_chunks_define_mapping_and_boundaries():
    chunks = json.loads(_searchtitle_chunk_path().read_text(encoding="utf-8"))

    assert len(chunks) == 4
    assert {chunk["id"] for chunk in chunks} == {
        "aem-guides-searchtitle-dita-contract-v1",
        "aem-guides-searchtitle-legacy-sites-mapping-v1",
        "aem-guides-searchtitle-legacy-sites-qa-v1",
        "aem-guides-searchtitle-evidence-boundary-v1",
    }

    corpus = "\n".join(chunk["content"] for chunk in chunks)
    assert 'meta name="searchtitle"' in corpus
    assert "legacy AEM Sites component mapping" in corpus
    assert "do not verify that searchtitle replaces the HTML <title>" in corpus
    assert "is indexed by a specific AEM search implementation" in corpus
    assert "composite or newer component mapping" in corpus


def test_searchtitle_behavior_chunks_are_loaded_before_general_corpus():
    chunks = doc_retriever_service._load_chunks()

    assert [chunk["id"] for chunk in chunks[:4]] == [
        "aem-guides-searchtitle-dita-contract-v1",
        "aem-guides-searchtitle-legacy-sites-mapping-v1",
        "aem-guides-searchtitle-legacy-sites-qa-v1",
        "aem-guides-searchtitle-evidence-boundary-v1",
    ]


def test_compact_prompt_blocks_unsupported_dita_to_aem_mapping_inference():
    prompt = chat_service._build_compact_chat_system_prompt()

    assert "Never infer concrete HTML tags, JCR properties" in prompt
    assert "title fallback or override precedence" in prompt
    assert "search indexing, search-result behavior" in prompt
    assert "legacy versus composite component mapping" in prompt


def test_searchtitle_queries_enable_exact_match_supplement():
    assert doc_retriever_service._query_needs_exact_match_supplement(
        "Is searchtitle indexed by AEM search?"
    )
    assert "searchtitle" in doc_retriever_service._exact_match_fragments(
        "How can searchtitle be verified in AEM Sites?"
    )


def test_searchtitle_is_not_misclassified_as_search_attribute():
    query = "How can searchtitle be verified in AEM Sites, including search indexing behavior?"

    assert extract_attribute_names(query) == []
    assert extract_element_names(query) == ["searchtitle"]


def test_explicit_search_attribute_remains_supported_with_searchtitle():
    query = "Compare the @search attribute with the searchtitle element."

    assert extract_attribute_names(query) == ["search"]


def test_bounded_searchtitle_evidence_can_cross_product_doc_host_filter():
    query = "How can searchtitle be verified in AEM Sites?"
    docs = [
        {
            "chunk_id": "aem-guides-searchtitle-legacy-sites-mapping-v1",
            "url": "https://git.corp.adobe.com/AdobeStarling/starling/searchtitle.jsp",
            "title": "AEM Guides legacy AEM Sites searchtitle mapping",
            "snippet": 'Renders <meta name="searchtitle"> in the page head.',
        },
        {
            "chunk_id": "untrusted-searchtitle-note",
            "url": "https://example.com/searchtitle",
            "title": "Untrusted searchtitle note",
            "snippet": "Unsupported claim.",
        },
    ]

    ranked = doc_retriever_service._filter_and_rank_docs(
        query,
        docs,
        k=5,
        allowed_host_suffixes=("experienceleague.adobe.com",),
    )

    assert [item["chunk_id"] for item in ranked] == ["aem-guides-searchtitle-legacy-sites-mapping-v1"]


def test_searchtitle_product_facts_render_verified_oracle_and_boundaries():
    question = (
        "How can searchtitle be verified in AEM Sites in AEM Guides? "
        "Also explain fallback and AEM search indexing behavior."
    )
    tool_results = {
        "lookup_dita_spec": {
            "query_type": "element_definition",
            "element_name": "searchtitle",
            "text_content": "The <searchtitle> element is an alternative title displayed by search tools.",
        },
        "lookup_aem_guides": {
            "count": 2,
            "results": [
                {"chunk_id": "aem-guides-searchtitle-legacy-sites-mapping-v1"},
                {"chunk_id": "aem-guides-searchtitle-evidence-boundary-v1"},
            ],
        },
    }

    answer, facts = chat_service._build_grounded_tool_draft_answer(
        answer_mode="grounded_dita_answer",
        question=question,
        tool_results_by_name=tool_results,
    )

    assert facts is not None
    assert '<meta name="searchtitle" content="...">' in answer
    assert "<titlealts><searchtitle>qa-searchtitle-marker" in answer
    assert "fallback precedence or AEM search indexing/ranking" in answer
    assert "legacy AEM Sites component mapping only" in answer
    assert "@searchtitle" not in answer
    assert "<topicref searchtitle=" not in answer


def test_searchtitle_contract_outranks_generic_aem_search_content():
    query = "Is searchtitle indexed by AEM search and does it change search result ranking?"
    targeted = doc_retriever_service._document_relevance_score(
        query,
        title="Searchtitle AEM Sites evidence boundaries",
        url="https://git.corp.adobe.com/AdobeStarling/starling/searchtitle.jsp",
        content="The sources do not verify AEM search indexing or ranking for searchtitle.",
        evidence_type="enriched_evidence_boundary",
        allowed_host_suffixes=None,
    )
    generic = doc_retriever_service._document_relevance_score(
        query,
        title="Configure search for AEM Assets UI",
        url="https://experienceleague.adobe.com/en/docs/experience-manager-guides/search",
        content="Configure AEM search indexes and search result behavior.",
        evidence_type="",
        allowed_host_suffixes=None,
    )

    assert targeted > generic
