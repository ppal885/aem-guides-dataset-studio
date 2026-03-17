"""Retrieve relevant AEM Guides documentation chunks for RAG augmentation.

Uses ChromaDB when available; falls back to JSON + embedding; then lexical matching.
"""
import json
import re
from pathlib import Path
from typing import Optional

from backend.app.storage import get_storage
from backend.app.services.embedding_service import embed_query, is_embedding_available
from backend.app.services.vector_store_service import (
    is_chroma_available,
    query_collection,
    get_collection_count,
    CHROMA_COLLECTION_AEM_GUIDES,
    CHROMA_COLLECTION_DITA_SPEC,
)
from backend.app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

DOC_CHUNKS_FILENAME = "aem_guides_doc_chunks.json"
MAX_SNIPPET_CHARS = 1500


def _get_doc_chunks_path() -> Path:
    storage = get_storage()
    return storage.base_path / DOC_CHUNKS_FILENAME


def _load_chunks() -> list[dict]:
    """Load doc chunks from JSON. Returns empty list if not found."""
    path = _get_doc_chunks_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as e:
        logger.warning_structured("Failed to load doc chunks", extra_fields={"error": str(e)})
        return []


def check_rag_readiness() -> dict:
    """
    Verify at least one RAG source (AEM Guides or DITA spec) has content.
    Returns dict with aem_guides_ready, dita_spec_ready, any_ready, message.
    """
    aem_guides_ready = False
    dita_spec_ready = False

    if is_chroma_available():
        aem_count = get_collection_count(CHROMA_COLLECTION_AEM_GUIDES)
        dita_count = get_collection_count(CHROMA_COLLECTION_DITA_SPEC)
        aem_guides_ready = aem_count > 0
        dita_spec_ready = dita_count > 0

    if not aem_guides_ready:
        chunks = _load_chunks()
        aem_guides_ready = len(chunks) > 0

    any_ready = aem_guides_ready or dita_spec_ready
    if any_ready:
        message = "RAG sources ready"
    else:
        message = (
            "No RAG sources populated. Run POST /api/v1/ai/crawl-aem-guides to index Experience League docs, "
            "and POST /api/v1/ai/index-dita-pdf to index DITA spec. Then retry plan or generate."
        )
    return {
        "aem_guides_ready": aem_guides_ready,
        "dita_spec_ready": dita_spec_ready,
        "any_ready": any_ready,
        "message": message,
    }


def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    text = re.sub(r"[^\w\s-]", " ", str(text).lower())
    return {t for t in text.split() if len(t) >= 2}


def _lexical_score(query_tokens: set[str], content: str) -> float:
    content_tokens = _tokenize(content)
    if not query_tokens:
        return 0.0
    matches = sum(1 for t in query_tokens if t in content_tokens)
    return matches / len(query_tokens) if query_tokens else 0.0


def retrieve_relevant_docs(
    query: str,
    k: int = 5,
    max_snippet_chars: int = MAX_SNIPPET_CHARS,
) -> list[dict]:
    """
    Retrieve top-k relevant AEM Guides doc chunks for the query.
    Returns list of dicts: url, title, snippet.
    Tries ChromaDB first, then JSON+embedding, then lexical.
    """
    query = (query or "").strip()
    if not query:
        return []

    # ChromaDB retrieval (preferred when available)
    if is_chroma_available() and is_embedding_available():
        query_emb = embed_query(query)
        if query_emb is not None:
            rows = query_collection(
                CHROMA_COLLECTION_AEM_GUIDES,
                query_embedding=query_emb.tolist() if hasattr(query_emb, "tolist") else list(query_emb),
                k=k,
            )
            if rows:
                result = []
                for row in rows:
                    meta = row.get("metadata") or {}
                    doc = row.get("document") or ""
                    snippet = doc[:max_snippet_chars]
                    result.append({
                        "url": meta.get("url", ""),
                        "title": meta.get("title", ""),
                        "snippet": snippet,
                    })
                logger.info_structured(
                    "AEM Guides docs from ChromaDB (Experience League)",
                    extra_fields={"source": "chromadb", "count": len(result)},
                )
                return result

    # JSON + embedding fallback (supports partial embeddings when some chunks lack them)
    chunks = _load_chunks()
    if chunks and is_embedding_available():
        query_emb = embed_query(query)
        if query_emb is not None:
            indexed = [(i, c, c.get("embedding")) for i, c in enumerate(chunks) if c.get("embedding")]
            if indexed:
                try:
                    import numpy as np
                    query_arr = np.array(query_emb)
                    emb_list = [x[2] for x in indexed]
                    chunk_arr = np.array(emb_list)
                    scores = np.dot(chunk_arr, query_arr)
                    order = np.argsort(scores)[::-1][:k]
                    result = []
                    for idx in order:
                        c = indexed[idx][1]
                        snippet = (c.get("content") or "")[:max_snippet_chars]
                        result.append({
                            "url": c.get("url", ""),
                            "title": c.get("title", ""),
                            "snippet": snippet,
                        })
                    if result:
                        logger.info_structured(
                            "AEM Guides docs from JSON fallback (ChromaDB empty or unavailable)",
                            extra_fields={
                                "source": "json_fallback",
                                "count": len(result),
                                "chunks_with_embeddings": len(indexed),
                                "total_chunks": len(chunks),
                            },
                        )
                        return result
                except Exception as e:
                    logger.warning_structured(
                        "Embedding retrieval failed, using lexical",
                        extra_fields={"error": str(e)},
                    )

    # Lexical fallback (requires chunks from JSON)
    if not chunks:
        logger.info_structured(
            "AEM Guides: no docs available (run POST /api/v1/ai/crawl-aem-guides to populate)",
            extra_fields={"source": "none"},
        )
        return []
    query_tokens = _tokenize(query)
    scored = []
    for c in chunks:
        content = c.get("content") or ""
        score = _lexical_score(query_tokens, content)
        scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    result = []
    for score, c in scored[:k]:
        if score <= 0:
            break
        snippet = (c.get("content") or "")[:max_snippet_chars]
        result.append({
            "url": c.get("url", ""),
            "title": c.get("title", ""),
            "snippet": snippet,
        })
    return result


def format_docs_for_prompt(docs: list[dict]) -> str:
    """Format retrieved docs for inclusion in LLM prompt."""
    if not docs:
        return ""
    parts = []
    for i, d in enumerate(docs, 1):
        url = d.get("url", "")
        title = d.get("title", "")
        snippet = d.get("snippet", "")
        parts.append(f"[{i}] {title or url}\n{snippet}")
    return "\n\n".join(parts)
