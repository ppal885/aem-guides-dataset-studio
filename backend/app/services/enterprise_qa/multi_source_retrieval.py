"""Merge Jira QA RAG with Experience League (aem_guides) and optional enterprise_qa collection."""

from __future__ import annotations

from typing import Any

from app.services.embedding_service import embed_query, is_embedding_available
from app.services.vector_store_service import (
    CHROMA_COLLECTION_AEM_GUIDES,
    CHROMA_COLLECTION_ENTERPRISE_QA,
    get_collection_count,
    is_chroma_available,
    query_collection,
)


def _row_to_chunk(row: dict[str, Any], *, source_type: str) -> dict[str, Any]:
    meta = row.get("metadata") or {}
    sk = str(meta.get("source_key") or meta.get("page_id") or "DOCS")
    kind = str(meta.get("chunk_type") or meta.get("section") or "chunk")
    return {
        "jira_key": sk[:120],
        "chunk_type": f"{source_type}:{kind}",
        "document": (row.get("document") or "")[:8000],
        "metadata": {**meta, "source_type": source_type},
    }


def augment_chunks_with_multi_source(
    query_text: str,
    base_chunks: list[dict[str, Any]],
    *,
    top_k_aem_guides: int = 3,
    top_k_enterprise: int = 4,
) -> list[dict[str, Any]]:
    """Append semantic hits from non-Jira collections; preserves RAG infra (single embed pipeline)."""
    out = list(base_chunks)
    if not query_text.strip() or not is_chroma_available() or not is_embedding_available():
        return out
    qv = embed_query(query_text[:12_000])
    if qv is None:
        return out
    emb = qv.tolist() if hasattr(qv, "tolist") else list(qv)

    if top_k_aem_guides > 0 and get_collection_count(CHROMA_COLLECTION_AEM_GUIDES) > 0:
        for row in query_collection(CHROMA_COLLECTION_AEM_GUIDES, emb, k=top_k_aem_guides):
            out.append(_row_to_chunk(row, source_type="docs"))

    if top_k_enterprise > 0 and get_collection_count(CHROMA_COLLECTION_ENTERPRISE_QA) > 0:
        for row in query_collection(CHROMA_COLLECTION_ENTERPRISE_QA, emb, k=top_k_enterprise):
            out.append(_row_to_chunk(row, source_type="automation"))

    return out
