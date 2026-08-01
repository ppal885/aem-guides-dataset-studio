import json
from pathlib import Path

from app.services import chat_service, doc_retriever_service


def _chunk_path() -> Path:
    return Path(__file__).resolve().parents[1] / "storage" / "manual_copy_to_chunk_behavior_chunks.json"


def test_copy_to_chunk_chunks_capture_normative_rules_and_boundaries():
    chunks = json.loads(_chunk_path().read_text(encoding="utf-8"))

    assert len(chunks) == 4
    corpus = "\n".join(chunk["content"] for chunk in chunks)
    assert "resource name MUST be taken from the copy-to value" in corpus
    assert "output-format specific and implementation specific" in corpus
    assert "processor MAY recover by creating alternate resource identifiers" in corpus
    assert "effective scope is peer or external" in corpus
    assert "single physical DITA source document" in corpus
    assert "does not prove by-topic splitting" in corpus


def test_copy_to_chunk_chunks_load_before_general_corpus():
    chunks = doc_retriever_service._load_chunks()
    ids = [chunk.get("id") or chunk.get("chunk_id") for chunk in chunks]

    assert ids[4:8] == [
        "dita-copy-to-chunk-naming-v1",
        "dita-copy-to-chunk-by-topic-fixture-v1",
        "dita-copy-to-chunk-boundaries-v1",
        "dita-copy-to-chunk-evidence-contract-v1",
    ]


def test_copy_to_chunk_query_enables_exact_match_supplement():
    query = 'Explain copy-to combined with chunk="to-content" and chunk="by-topic".'

    assert doc_retriever_service._query_needs_exact_match_supplement(query)
    assert {"copy-to", "to-content", "by-topic"}.issubset(
        doc_retriever_service._exact_match_fragments(query)
    )


def test_copy_to_chunk_prompt_blocks_cross_format_generalization():
    hint = chat_service._question_shape_hint(
        'Explain copy-to combined with chunk="to-content" and chunk="by-topic" for Sites, HTML5, and PDF.'
    )

    assert "output resource name comes from `copy-to`" in hint
    assert "nested topics in one physical source document" in hint
    assert "never claim identical AEM Sites, HTML5, and PDF behavior" in hint
    assert "XML catalog" not in hint


def test_copy_to_chunk_curated_evidence_crosses_product_host_filter_only_for_matching_query():
    docs = [
        {
            "chunk_id": "dita-copy-to-chunk-naming-v1",
            "url": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/archSpec/base/chunkingdetails.html",
            "title": "DITA 1.3 copy-to and chunk output naming",
            "snippet": "When copy-to is specified, the chunk resource name comes from copy-to.",
        }
    ]

    matching = doc_retriever_service._filter_and_rank_docs(
        'Explain copy-to with chunk="to-content".',
        docs,
        k=5,
        allowed_host_suffixes=("experienceleague.adobe.com",),
    )
    unrelated = doc_retriever_service._filter_and_rank_docs(
        "Explain an AEM publishing preset.",
        docs,
        k=5,
        allowed_host_suffixes=("experienceleague.adobe.com",),
    )

    assert [item["chunk_id"] for item in matching] == ["dita-copy-to-chunk-naming-v1"]
    assert unrelated == []
