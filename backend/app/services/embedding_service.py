"""Embedding service for semantic retrieval - DITA chunks and recipes.

Uses sentence-transformers (for example ``all-MiniLM-L6-v2``) with lazy
loading, and supports a local fine-tuned model via ``DITA_EMBEDDING_MODEL_PATH``.
The service also exposes runtime diagnostics so callers can distinguish true
semantic retrieval from lexical fallback.
"""
import os
from typing import Any, Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

_embedding_model = None
_embedding_available: Optional[bool] = None
_embedding_failure_reason = ""
_embedding_load_mode = "uninitialized"
_embedding_active_model_identifier = ""

DITA_EMBEDDING_MODEL = os.getenv("DITA_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
DITA_EMBEDDING_MODEL_PATH = os.getenv("DITA_EMBEDDING_MODEL_PATH", "").strip()


def _load_model():
    """Load embedding model lazily (singleton)."""
    global _embedding_model, _embedding_available
    global _embedding_failure_reason, _embedding_load_mode, _embedding_active_model_identifier
    if _embedding_available is False:
        return None
    if _embedding_model is not None:
        return _embedding_model
    try:
        from sentence_transformers import SentenceTransformer

        if DITA_EMBEDDING_MODEL_PATH:
            _embedding_model = SentenceTransformer(DITA_EMBEDDING_MODEL_PATH)
            _embedding_load_mode = "local_path"
            _embedding_active_model_identifier = DITA_EMBEDDING_MODEL_PATH
            logger.info_structured(
                "Loaded fine-tuned DITA embedding model",
                extra_fields={"path": DITA_EMBEDDING_MODEL_PATH},
            )
        else:
            _embedding_model = SentenceTransformer(DITA_EMBEDDING_MODEL)
            _embedding_load_mode = "model_name"
            _embedding_active_model_identifier = DITA_EMBEDDING_MODEL
            logger.info_structured(
                "Loaded DITA embedding model",
                extra_fields={"model": DITA_EMBEDDING_MODEL},
            )
        _embedding_available = True
        _embedding_failure_reason = ""
        return _embedding_model
    except Exception as e:
        _embedding_available = False
        _embedding_failure_reason = str(e)
        _embedding_load_mode = "fallback_none"
        _embedding_active_model_identifier = DITA_EMBEDDING_MODEL_PATH or DITA_EMBEDDING_MODEL
        logger.warning_structured(
            "Embedding model failed to load, using lexical fallback",
            extra_fields={"error": str(e)},
        )
        return None


def is_embedding_available() -> bool:
    """Return True if embedding model is loaded and usable."""
    model = _load_model()
    return model is not None


def get_embedding_diagnostics() -> dict[str, Any]:
    """Return the current embedding runtime state for retrieval diagnostics."""
    _load_model()
    return {
        "configured_model": DITA_EMBEDDING_MODEL,
        "configured_model_path": DITA_EMBEDDING_MODEL_PATH,
        "active_model_identifier": _embedding_active_model_identifier or (DITA_EMBEDDING_MODEL_PATH or DITA_EMBEDDING_MODEL),
        "using_local_path": bool(DITA_EMBEDDING_MODEL_PATH),
        "available": bool(_embedding_available),
        "load_mode": _embedding_load_mode,
        "error": _embedding_failure_reason,
    }


def reset_embedding_runtime_state() -> None:
    """Reset cached embedding runtime state.

    This is mainly intended for tests that monkeypatch model loading or env-like
    module constants and need a clean lazy-load attempt.
    """
    global _embedding_model, _embedding_available
    global _embedding_failure_reason, _embedding_load_mode, _embedding_active_model_identifier
    _embedding_model = None
    _embedding_available = None
    _embedding_failure_reason = ""
    _embedding_load_mode = "uninitialized"
    _embedding_active_model_identifier = ""


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
