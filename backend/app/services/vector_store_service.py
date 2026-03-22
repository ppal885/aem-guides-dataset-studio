"""Unified vector store service using ChromaDB.

Provides persistent storage for embeddings with metadata filtering.
Collections: aem_guides, dita_spec, dita_examples, recipes, jira_issues.
"""
from pathlib import Path
from typing import Optional

from app.storage import get_storage
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

CHROMA_COLLECTION_AEM_GUIDES = "aem_guides"
CHROMA_COLLECTION_DITA_SPEC = "dita_spec"
CHROMA_COLLECTION_DITA_EXAMPLES = "dita_examples"
CHROMA_COLLECTION_RESEARCH_CACHE = "research_cache"
CHROMA_DB_DIR = "chroma_db"

_chroma_client = None


def _get_chroma_path() -> Path:
    """Path for ChromaDB persistent storage."""
    storage = get_storage()
    path = storage.base_path / CHROMA_DB_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_client():
    """Get or create ChromaDB persistent client. Returns None if ChromaDB unavailable."""
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client
    try:
        import chromadb

        path = _get_chroma_path()
        _chroma_client = chromadb.PersistentClient(path=str(path))
        return _chroma_client
    except ImportError as e:
        logger.warning_structured(
            "ChromaDB not installed",
            extra_fields={"error": str(e), "hint": "pip install chromadb"},
        )
        return None
    except Exception as e:
        logger.warning_structured(
            "ChromaDB init failed",
            extra_fields={"error": str(e)},
        )
        return None


def is_chroma_available() -> bool:
    """Return True if ChromaDB is available and usable."""
    return _get_client() is not None


def add_documents(
    collection_name: str,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict],
    embeddings: list[list[float]],
) -> bool:
    """
    Add or upsert documents to a ChromaDB collection.
    All lists must have the same length.
    Returns True on success, False on failure.
    """
    client = _get_client()
    if not client or not ids:
        return False
    if not (len(ids) == len(documents) == len(metadatas) == len(embeddings)):
        return False
    try:
        coll = client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        coll.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        return True
    except Exception as e:
        logger.warning_structured(
            "ChromaDB add_documents failed",
            extra_fields={"collection": collection_name, "error": str(e), "count": len(ids)},
        )
        return False


def _collection_exists(client, collection_name: str) -> bool:
    """Check if collection exists without raising. Returns False if not found."""
    try:
        names = [c.name for c in client.list_collections()]
        return collection_name in names
    except Exception:
        return False


def query_collection(
    collection_name: str,
    query_embedding: list[float],
    k: int = 5,
    where: Optional[dict] = None,
) -> list[dict]:
    """
    Query ChromaDB collection by embedding.
    Returns list of dicts with keys: id, document, metadata, distance.
    Returns [] when collection does not exist (expected before first index).
    """
    client = _get_client()
    if not client or not query_embedding:
        return []
    if not _collection_exists(client, collection_name):
        return []
    # Ensure embedding is list of floats (ChromaDB expects list)
    emb = query_embedding
    if hasattr(emb, "tolist"):
        emb = emb.tolist()
    emb = list(emb) if emb else []
    if not emb:
        return []
    try:
        coll = client.get_collection(name=collection_name)
        count = coll.count()
        if count == 0:
            return []
        result = coll.query(
            query_embeddings=[emb],
            n_results=min(k, count),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        if not result or not result["ids"] or not result["ids"][0]:
            return []
        rows = []
        for i, doc_id in enumerate(result["ids"][0]):
            doc = (result["documents"][0][i] or "") if result["documents"] else ""
            meta = (result["metadatas"][0][i] or {}) if result["metadatas"] else {}
            dist = (result["distances"][0][i] or 0.0) if result.get("distances") else 0.0
            rows.append({
                "id": doc_id,
                "document": doc,
                "metadata": meta,
                "distance": dist,
            })
        return rows
    except Exception as e:
        logger.warning_structured(
            "ChromaDB query failed",
            extra_fields={"collection": collection_name, "error": str(e)},
        )
        return []


def delete_collection(collection_name: str) -> bool:
    """Delete a ChromaDB collection. Returns True on success. No-op if collection does not exist."""
    client = _get_client()
    if not client:
        return False
    if not _collection_exists(client, collection_name):
        return True
    try:
        client.delete_collection(name=collection_name)
        return True
    except Exception as e:
        logger.warning_structured(
            "ChromaDB delete_collection failed",
            extra_fields={"collection": collection_name, "error": str(e)},
        )
        return False


def delete_documents(collection_name: str, ids: list[str]) -> bool:
    """Delete specific documents from a ChromaDB collection by ID."""
    client = _get_client()
    if not client or not ids:
        return False
    if not _collection_exists(client, collection_name):
        return True
    try:
        coll = client.get_collection(name=collection_name)
        coll.delete(ids=ids)
        return True
    except Exception as e:
        logger.warning_structured(
            "ChromaDB delete_documents failed",
            extra_fields={"collection": collection_name, "error": str(e), "count": len(ids)},
        )
        return False


def get_collection_count(collection_name: str) -> int:
    """Return number of documents in collection. Returns 0 if unavailable or collection does not exist."""
    client = _get_client()
    if not client:
        return 0
    if not _collection_exists(client, collection_name):
        return 0
    try:
        coll = client.get_collection(name=collection_name)
        return coll.count()
    except Exception:
        return 0
