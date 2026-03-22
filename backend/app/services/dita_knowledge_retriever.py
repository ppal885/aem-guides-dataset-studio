"""DITA knowledge retriever - lexical and embedding-based search over DITA spec chunks.

Uses ChromaDB dita_spec collection when available and populated; otherwise embedding
similarity over DB/seed (USE_DITA_EMBEDDING=true), with lexical fallback.
"""
import json
import os
import re
from pathlib import Path
from typing import Optional

from app.db.dita_spec_models import DitaSpecChunk
from app.db.session import SessionLocal
from app.services.dita_graph_service import get_graph_summary_for_elements
from app.services.embedding_service import embed_query, embed_texts, is_embedding_available
from app.services.vector_store_service import (
    is_chroma_available,
    query_collection,
    get_collection_count,
    CHROMA_COLLECTION_DITA_SPEC,
)
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

USE_DITA_EMBEDDING = os.getenv("USE_DITA_EMBEDDING", "true").lower() in ("true", "1", "yes")

# In-memory cache: (chunks, embeddings) for embedding retrieval
_dita_embedding_cache: Optional[tuple[list[dict], object]] = None

DITA_BOOST_TERMS = {
    "conref": 2.0,
    "keyref": 2.0,
    "keydef": 2.0,
    "keyscope": 2.0,
    "topicref": 1.5,
    "ditamap": 1.5,
    "topic": 1.2,
    "map": 1.2,
    "section": 1.2,
    "example": 1.2,
    "body": 1.2,
    "nesting": 1.5,
    "attribute": 1.2,
    "reltable": 1.5,
    "relrow": 1.5,
    "relcolspec": 1.5,
    "collection": 1.5,
    "linking": 1.5,
    "hierarchy": 1.5,
    "note": 1.5,
    "sectiondiv": 1.5,
    "bodydiv": 1.5,
    "ditaval": 1.5,
    "subjectScheme": 1.5,
    "subjectscheme": 1.5,
    "prereq": 1.5,
    "chunk": 1.5,
    "topichead": 1.8,
    "glossentry": 1.5,
    "abbreviated-form": 1.5,
}

USE_DITA_HYBRID_SEARCH = os.getenv("USE_DITA_HYBRID_SEARCH", "true").lower() in ("true", "1", "yes")

SEED_PATH = Path(__file__).resolve().parent.parent / "storage" / "dita_spec_seed.json"
DITA_KNOWLEDGE_RETRIEVAL_K = int(os.getenv("DITA_KNOWLEDGE_RETRIEVAL_K", "4"))


def _tokenize(text: str) -> list[str]:
    """Extract searchable tokens."""
    if not text or not isinstance(text, str):
        return []
    text = re.sub(r"[^\w\s-]", " ", text.lower())
    return [t for t in text.split() if len(t) >= 2]


def _load_seed() -> list[dict]:
    """Load seed corpus from JSON."""
    if not SEED_PATH.exists():
        return []
    try:
        with open(SEED_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning_structured("Failed to load DITA seed", extra_fields={"error": str(e)})
        return []


def _search_seed(query_text: str, k: int) -> list[dict]:
    """Lexical search over seed corpus."""
    seed = _load_seed()
    if not seed:
        return []
    tokens = _tokenize(query_text)
    if not tokens:
        return seed[:k]
    scored = []
    for chunk in seed:
        text = (chunk.get("text_content") or "") + " " + (chunk.get("element_name") or "")
        text_lower = text.lower()
        score = 0.0
        for t in tokens:
            if t in text_lower:
                score += 1.0
                if t in DITA_BOOST_TERMS:
                    score += DITA_BOOST_TERMS[t] - 1.0
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:k]]


def _get_dita_chunks_for_embedding(session=None) -> list[dict]:
    """Get all DITA chunks (from DB or seed) as dicts for embedding."""
    db_session = session
    own_session = False
    if db_session is None:
        db_session = SessionLocal()
        own_session = True
    try:
        count = db_session.query(DitaSpecChunk).count()
        if count > 0:
            chunks = db_session.query(DitaSpecChunk).filter(
                DitaSpecChunk.text_content.isnot(None)
            ).all()
            result = [
                {
                    "element_name": c.element_name,
                    "content_type": c.content_type,
                    "text_content": c.text_content,
                    "source_url": c.source_url,
                }
                for c in chunks
            ]
            return result
    except Exception as e:
        logger.warning_structured(
            "DITA DB load failed for embedding, using seed",
            extra_fields={"error": str(e)},
        )
    finally:
        if own_session and db_session:
            db_session.close()
    return _load_seed()


def _retrieve_dita_chromadb(query_text: str, k: int) -> Optional[list[dict]]:
    """Retrieve DITA chunks from ChromaDB dita_spec collection. Returns None if unavailable or empty."""
    if not is_chroma_available() or not is_embedding_available():
        return None
    if get_collection_count(CHROMA_COLLECTION_DITA_SPEC) == 0:
        return None
    try:
        query_emb = embed_query(query_text)
        if query_emb is None:
            return None
        emb_list = query_emb.tolist() if hasattr(query_emb, "tolist") else list(query_emb)
        rows = query_collection(
            CHROMA_COLLECTION_DITA_SPEC,
            query_embedding=emb_list,
            k=k,
        )
        if not rows:
            return None
        result = []
        for row in rows:
            doc = row.get("document") or ""
            meta = row.get("metadata") or {}
            source_url = meta.get("source_url", "")
            page = meta.get("page", "")
            if page and source_url:
                source_url = f"{source_url}#page={page}"
            result.append({
                "element_name": "dita_spec",
                "content_type": "spec",
                "text_content": doc,
                "source_url": source_url or "https://docs.oasis-open.org/dita/v1.2/spec/DITA1.2-spec.pdf",
            })
        logger.info_structured(
            "DITA knowledge from ChromaDB (DITA 1.2 PDF)",
            extra_fields={"source": "chromadb_dita_spec", "count": len(result)},
        )
        return result
    except Exception as e:
        logger.warning_structured(
            "DITA ChromaDB retrieval failed, falling back",
            extra_fields={"error": str(e)},
        )
        return None


def _retrieve_dita_embedding(query_text: str, k: int) -> Optional[list[dict]]:
    """Retrieve DITA chunks by embedding similarity. Returns None on failure."""
    global _dita_embedding_cache
    if not is_embedding_available() or not USE_DITA_EMBEDDING:
        return None
    try:
        import numpy as np

        chunks = _get_dita_chunks_for_embedding()
        if not chunks:
            return None

        if _dita_embedding_cache is None:
            texts = [
                f"{c.get('element_name', '')} {c.get('text_content', '')}"
                for c in chunks
            ]
            embs = embed_texts(texts)
            if embs is None:
                return None
            _dita_embedding_cache = (chunks, embs)

        cached_chunks, chunk_embeddings = _dita_embedding_cache
        if len(cached_chunks) != len(chunks):
            _dita_embedding_cache = None
            return _retrieve_dita_embedding(query_text, k)

        query_emb = embed_query(query_text)
        if query_emb is None:
            return None

        scores = np.dot(chunk_embeddings, query_emb)
        top_indices = np.argsort(-scores)[:k]
        return [cached_chunks[i] for i in top_indices]
    except Exception as e:
        logger.warning_structured(
            "DITA embedding retrieval failed, falling back to lexical",
            extra_fields={"error": str(e)},
        )
        return None


def retrieve_dita_knowledge(
    query_text: str,
    k: Optional[int] = None,
    session=None,
) -> list[dict]:
    """
    Retrieve DITA spec chunks relevant to query.
    Uses embedding similarity when USE_DITA_EMBEDDING=true and model loads.
    Otherwise uses lexical search. DB if populated, else seed JSON.
    Returns [{element_name, content_type, text_content, source_url}].
    """
    k = k or DITA_KNOWLEDGE_RETRIEVAL_K
    if not query_text or not str(query_text).strip():
        return []

    chroma_results = _retrieve_dita_chromadb(query_text, k)
    if chroma_results is not None:
        if USE_DITA_HYBRID_SEARCH and chroma_results:
            tokens = _tokenize(query_text)
            if tokens:
                scored = []
                for i, chunk in enumerate(chroma_results):
                    text = (chunk.get("text_content") or "") + " " + (chunk.get("element_name") or "")
                    text_lower = text.lower()
                    lexical_boost = 0.0
                    for t in tokens:
                        if t in text_lower:
                            lexical_boost += DITA_BOOST_TERMS.get(t, 1.0)
                    embedding_rank = 1.0 / (1.0 + i)
                    combined = embedding_rank + lexical_boost * 0.5
                    scored.append((combined, chunk))
                scored.sort(key=lambda x: -x[0])
                chroma_results = [c for _, c in scored]
        return chroma_results

    logger.info_structured(
        "DITA knowledge from DB/seed fallback (run POST /api/v1/ai/index-dita-pdf to use DITA 1.2 PDF)",
        extra_fields={"source": "db_seed_fallback"},
    )
    emb_results = _retrieve_dita_embedding(query_text, k)
    if emb_results is not None:
        return emb_results

    db_session = session
    own_session = False
    if db_session is None:
        db_session = SessionLocal()
        own_session = True

    try:
        count = db_session.query(DitaSpecChunk).count()
        if count > 0:
            tokens = _tokenize(query_text)
            all_chunks = db_session.query(DitaSpecChunk).filter(
                DitaSpecChunk.text_content.isnot(None)
            ).all()
            scored = []
            for chunk in all_chunks:
                text = (chunk.text_content or "") + " " + (chunk.element_name or "")
                text_lower = text.lower()
                score = 0.0
                for t in tokens:
                    if t in text_lower:
                        score += 1.0
                        if t in DITA_BOOST_TERMS:
                            score += DITA_BOOST_TERMS[t] - 1.0
                if score > 0:
                    scored.append((score, chunk))
            scored.sort(key=lambda x: -x[0])
            results = []
            for _, c in scored[:k]:
                results.append({
                    "element_name": c.element_name,
                    "content_type": c.content_type,
                    "text_content": c.text_content,
                    "source_url": c.source_url,
                })
            return results
    except Exception as e:
        logger.warning_structured(
            "DITA DB retrieval failed, using seed",
            extra_fields={"error": str(e)},
        )
    finally:
        if own_session and db_session:
            db_session.close()

    return _search_seed(query_text, k)


# Known DITA elements for hint extraction (subset from seed; graph has full set at runtime)
DITA_ELEMENT_NAMES = [
    "topic", "map", "topicref", "conref", "keyref", "keydef", "keyscope",
    "body", "section", "example", "prolog", "shortdesc", "xref", "fig",
    "table", "codeblock", "ditamap", "mapref", "conrefend", "ph", "keyword",
    "topicmeta", "navtitle", "image", "steps", "step", "concept", "task", "reference",
    "div", "simpletable", "desc", "taskbody", "conbody", "refbody",
    "reltable", "relrow", "relcolspec", "collection-type", "linking",
    "note", "sectiondiv", "bodydiv", "p", "ul", "ol", "li", "dl", "dlentry", "dt", "dd", "dlhead", "dthd", "ddhd",
    "prereq", "context", "result", "cmd", "info", "stepresult",
    "subjectScheme", "subjectdef", "schemeref", "ditaval", "chunk",
    "audience", "platform", "otherprops", "properties", "related-links",
]


def _extract_elements_from_hint(hint: str) -> list[str]:
    """Extract DITA element names mentioned in hint text (case-insensitive)."""
    if not hint or not isinstance(hint, str):
        return []
    hint_lower = hint.lower()
    found = []
    for el in DITA_ELEMENT_NAMES:
        if el.lower() in hint_lower:
            found.append(el)
    return found


def retrieve_dita_graph_knowledge(
    element_hint: Optional[str] = None,
    elements: Optional[list[str]] = None,
    session=None,
) -> str:
    """
    Retrieve graph-based DITA structure: nesting and attributes for elements.
    Returns structured text block for prompt injection.
    Use element_hint (free text) or elements (explicit list) to specify which elements.
    """
    if elements:
        el_list = [e for e in elements if e and str(e).strip()]
    elif element_hint:
        el_list = _extract_elements_from_hint(element_hint)
        if not el_list:
            el_list = ["topic", "map", "conref", "keyref"]  # default fallback
    else:
        return ""
    return get_graph_summary_for_elements(el_list, session)
