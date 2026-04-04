"""
Vector Store Service — ChromaDB interface for all RAG operations.

Single place for all ChromaDB interactions.
Every service that needs to store or query embeddings goes through here.

Collections used:
  CHROMA_COLLECTION_AEM_GUIDES  — Experience League crawl data
  CHROMA_COLLECTION_DITA_SPEC   — DITA 1.2/1.3 spec PDFs
  "dita_examples"               — approved expert DITA topics
  "research_cache"              — Tavily search results (persistent)
  "{tenant_id}_rag"             — per-tenant RAG (multi-tenant)

Place at: backend/app/services/vector_store_service.py
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

CHROMA_HOST = os.getenv("CHROMA_HOST", "")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8001"))
CHROMA_PATH = os.getenv(
    "CHROMA_PATH",
    str(Path(__file__).resolve().parent.parent / "storage" / "chroma_db"),
)

CHROMA_COLLECTION_AEM_GUIDES = os.getenv("CHROMA_COLLECTION_AEM_GUIDES", "aem_guides")
CHROMA_COLLECTION_DITA_SPEC  = os.getenv("CHROMA_COLLECTION_DITA_SPEC",  "dita_spec")

# ── Client singleton ──────────────────────────────────────────────────────────

_chroma_client = None


def _get_client():
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client

    try:
        import chromadb

        if CHROMA_HOST:
            # Remote ChromaDB server
            _chroma_client = chromadb.HttpClient(
                host=CHROMA_HOST,
                port=CHROMA_PORT,
            )
        else:
            # Local persistent ChromaDB
            Path(CHROMA_PATH).mkdir(parents=True, exist_ok=True)
            _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

        return _chroma_client

    except ImportError:
        raise RuntimeError("chromadb not installed. Run: pip install chromadb")
    except Exception as e:
        logger.warning_structured(
            "ChromaDB client init failed",
            extra_fields={"error": str(e)},
        )
        raise


def is_chroma_available() -> bool:
    """Return True if ChromaDB is available and reachable."""
    try:
        client = _get_client()
        client.heartbeat()
        return True
    except Exception:
        return False


# ── Collection helpers ────────────────────────────────────────────────────────

def _get_or_create_collection(name: str):
    """Get collection by name, creating it if it doesn't exist."""
    client = _get_client()
    try:
        return client.get_or_create_collection(
            name     = name,
            metadata = {"hnsw:space": "cosine"},
        )
    except Exception as e:
        logger.warning_structured(
            "Collection get/create failed",
            extra_fields={"name": name, "error": str(e)},
        )
        raise


def get_collection_count(collection_name: str) -> int:
    """Return number of documents in a collection. 0 if not found."""
    try:
        col = _get_or_create_collection(collection_name)
        return col.count()
    except Exception:
        return 0


# ── Core operations ───────────────────────────────────────────────────────────

def add_documents(
    collection_name: str,
    ids:             list[str],
    documents:       list[str],
    metadatas:       list[dict],
    embeddings:      Optional[list[list[float]]] = None,
) -> bool:
    """
    Add documents to a ChromaDB collection.

    If embeddings provided: uses them directly (fast, no re-embedding).
    If embeddings=None: ChromaDB will embed using its default model.

    Returns True on success, False on failure.
    """
    if not ids or not documents:
        return True

    try:
        col = _get_or_create_collection(collection_name)

        kwargs: dict = {
            "ids":       ids,
            "documents": documents,
            "metadatas": metadatas,
        }
        if embeddings is not None:
            kwargs["embeddings"] = embeddings

        col.upsert(**kwargs)

        logger.debug_structured(
            "Documents added to ChromaDB",
            extra_fields={
                "collection": collection_name,
                "count":      len(ids),
            },
        )
        return True

    except Exception as e:
        logger.warning_structured(
            "add_documents failed",
            extra_fields={"collection": collection_name, "error": str(e)[:200]},
        )
        return False


def query_collection(
    collection_name:  str,
    query_embedding:  list[float],
    k:                int = 5,
    where:            Optional[dict] = None,
) -> list[dict]:
    """
    Query a collection by embedding similarity.

    Returns list of dicts:
    [
      {
        "id":       "doc_id",
        "document": "text content",
        "metadata": {...},
        "distance": 0.12,   # lower = more similar (cosine)
      },
      ...
    ]
    """
    try:
        col = _get_or_create_collection(collection_name)

        query_kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results":        min(k, max(1, col.count())),
            "include":          ["documents", "metadatas", "distances"],
        }
        if where:
            query_kwargs["where"] = where

        results = col.query(**query_kwargs)

        rows = []
        ids       = results.get("ids", [[]])[0]
        docs      = results.get("documents", [[]])[0]
        metas     = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, doc_id in enumerate(ids):
            rows.append({
                "id":       doc_id,
                "document": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
                "distance": distances[i] if i < len(distances) else 1.0,
            })

        return rows

    except Exception as e:
        logger.debug_structured(
            "query_collection failed",
            extra_fields={"collection": collection_name, "error": str(e)[:200]},
        )
        return []


def query_collection_by_text(
    collection_name: str,
    query_text:      str,
    k:               int = 5,
    where:           Optional[dict] = None,
) -> list[dict]:
    """
    Query using text (ChromaDB embeds internally).
    Useful when you don't have a pre-computed embedding.
    """
    try:
        col = _get_or_create_collection(collection_name)

        query_kwargs: dict = {
            "query_texts": [query_text],
            "n_results":   min(k, max(1, col.count())),
            "include":     ["documents", "metadatas", "distances"],
        }
        if where:
            query_kwargs["where"] = where

        results = col.query(**query_kwargs)

        rows = []
        ids       = results.get("ids", [[]])[0]
        docs      = results.get("documents", [[]])[0]
        metas     = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, doc_id in enumerate(ids):
            rows.append({
                "id":       doc_id,
                "document": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
                "distance": distances[i] if i < len(distances) else 1.0,
            })

        return rows

    except Exception as e:
        logger.debug_structured(
            "query_collection_by_text failed",
            extra_fields={"collection": collection_name, "error": str(e)[:200]},
        )
        return []


def delete_documents(
    collection_name: str,
    ids:             list[str],
) -> bool:
    """Delete specific documents by ID."""
    try:
        col = _get_or_create_collection(collection_name)
        col.delete(ids=ids)
        return True
    except Exception as e:
        logger.warning_structured(
            "delete_documents failed",
            extra_fields={"collection": collection_name, "error": str(e)[:200]},
        )
        return False


def delete_collection(collection_name: str) -> bool:
    """Delete entire collection. Used for re-indexing."""
    try:
        client = _get_client()
        client.delete_collection(collection_name)
        logger.info_structured(
            "Collection deleted",
            extra_fields={"collection": collection_name},
        )
        return True
    except Exception as e:
        logger.warning_structured(
            "delete_collection failed",
            extra_fields={"collection": collection_name, "error": str(e)[:200]},
        )
        return False


def list_collections() -> list[str]:
    """List all collection names."""
    try:
        client = _get_client()
        return [c.name for c in client.list_collections()]
    except Exception:
        return []


def get_document_by_id(collection_name: str, doc_id: str) -> Optional[dict]:
    """Get a specific document by ID."""
    try:
        col = _get_or_create_collection(collection_name)
        results = col.get(
            ids     = [doc_id],
            include = ["documents", "metadatas"],
        )
        ids  = results.get("ids", [])
        docs = results.get("documents", [])
        meta = results.get("metadatas", [])
        if ids:
            return {
                "id":       ids[0],
                "document": docs[0] if docs else "",
                "metadata": meta[0] if meta else {},
            }
        return None
    except Exception:
        return None
