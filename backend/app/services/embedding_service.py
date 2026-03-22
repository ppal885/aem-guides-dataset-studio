"""Embedding service for semantic retrieval - DITA chunks and recipes.

Uses sentence-transformers (e.g. all-MiniLM-L6-v2) with lazy loading.
Supports custom fine-tuned model via DITA_EMBEDDING_MODEL_PATH.
"""
import os
from typing import Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

_embedding_model = None
_embedding_available: Optional[bool] = None

DITA_EMBEDDING_MODEL = os.getenv("DITA_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
DITA_EMBEDDING_MODEL_PATH = os.getenv("DITA_EMBEDDING_MODEL_PATH", "").strip()


def _load_model():
    """Load embedding model lazily (singleton)."""
    global _embedding_model, _embedding_available
    if _embedding_available is False:
        return None
    if _embedding_model is not None:
        return _embedding_model
    try:
        from sentence_transformers import SentenceTransformer

        if DITA_EMBEDDING_MODEL_PATH:
            _embedding_model = SentenceTransformer(DITA_EMBEDDING_MODEL_PATH)
            logger.info_structured(
                "Loaded fine-tuned DITA embedding model",
                extra_fields={"path": DITA_EMBEDDING_MODEL_PATH},
            )
        else:
            _embedding_model = SentenceTransformer(DITA_EMBEDDING_MODEL)
            logger.info_structured(
                "Loaded DITA embedding model",
                extra_fields={"model": DITA_EMBEDDING_MODEL},
            )
        _embedding_available = True
        return _embedding_model
    except Exception as e:
        _embedding_available = False
        logger.warning_structured(
            "Embedding model failed to load, using lexical fallback",
            extra_fields={"error": str(e)},
        )
        return None


def is_embedding_available() -> bool:
    """Return True if embedding model is loaded and usable."""
    model = _load_model()
    return model is not None


EMBED_BATCH_SIZE = 64


def embed_texts(texts: list[str]):
    """
    Embed a batch of texts. Returns numpy array of shape (n, dim).
    Returns None if model unavailable.
    """
    model = _load_model()
    if model is None or not texts:
        return None
    try:
        return model.encode(texts, convert_to_numpy=True)
    except Exception as e:
        logger.warning_structured(
            "Embedding batch failed",
            extra_fields={"error": str(e), "count": len(texts)},
        )
        return None


def embed_texts_batched(texts: list[str], batch_size: int = EMBED_BATCH_SIZE):
    """
    Embed texts in batches to avoid OOM for large corpora (e.g. DITA PDF ~1000+ chunks).
    Returns numpy array of shape (n, dim). Returns None if model unavailable.
    """
    model = _load_model()
    if model is None or not texts:
        return None
    try:
        import numpy as np
        results = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            emb = model.encode(batch, convert_to_numpy=True)
            results.append(emb)
        if not results:
            return None
        return np.vstack(results)
    except Exception as e:
        logger.warning_structured(
            "Embedding batched failed",
            extra_fields={"error": str(e), "count": len(texts), "batch_size": batch_size},
        )
        return None


def embed_query(text: str):
    """
    Embed a single query text. Returns numpy array of shape (dim,) or None.
    """
    if not text or not str(text).strip():
        return None
    result = embed_texts([text])
    if result is None:
        return None
    return result[0]
