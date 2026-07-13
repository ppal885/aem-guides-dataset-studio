"""Embedding service for semantic retrieval - DITA chunks and recipes.

Uses sentence-transformers (for example ``all-MiniLM-L6-v2``) with lazy
loading, and supports a local fine-tuned model via ``DITA_EMBEDDING_MODEL_PATH``.
The service also exposes runtime diagnostics so callers can distinguish true
semantic retrieval from lexical fallback.
"""
import os
from pathlib import Path
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

# Azure OpenAI embedding fallback — used when sentence_transformers fails
_AZURE_EMBED_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
_AZURE_EMBED_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
_AZURE_EMBED_MODEL = os.getenv("AZURE_EMBEDDING_MODEL", "text-embedding-ada-002")
_AZURE_EMBED_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
_USE_AZURE_EMBEDDING = os.getenv("USE_AZURE_EMBEDDING", "false").lower() in ("1", "true", "yes", "on")

EMBED_DIM = 384  # all-MiniLM-L6-v2 output dimension; Azure ada-002 is 1536


def _try_azure_embedding(texts: list) -> Optional[list]:
    """Embed texts using Azure OpenAI when sentence_transformers is unavailable."""
    if not (_AZURE_EMBED_ENDPOINT and _AZURE_EMBED_KEY):
        return None
    try:
        import requests
        url = f"{_AZURE_EMBED_ENDPOINT}/openai/deployments/{_AZURE_EMBED_MODEL}/embeddings?api-version={_AZURE_EMBED_VERSION}"
        results = []
        for i in range(0, len(texts), 16):
            batch = texts[i:i + 16]
            r = requests.post(url, headers={"api-key": _AZURE_EMBED_KEY, "Content-Type": "application/json"},
                              json={"input": batch}, timeout=30)
            if not r.ok:
                return None
            data = r.json().get("data", [])
            results.extend([d["embedding"] for d in sorted(data, key=lambda x: x["index"])])
        return results
    except Exception as e:
        logger.debug_structured("azure_embedding_failed", extra_fields={"error": str(e)})
        return None


def _resolve_embedding_source() -> tuple[str, str]:
    """Pick the embedding model source, portably across machines/containers.

    Order: (1) DITA_EMBEDDING_MODEL_PATH if it exists on THIS host, (2) the model bundled
    under ``backend/models/<name>`` (relative — survives a VM/container move), (3) the model
    NAME so sentence-transformers downloads/caches it. This means a stale absolute path in
    .env (e.g. a Windows path baked in, then deployed to a Linux VM) no longer disables
    embeddings — it transparently falls back instead of failing.
    """
    if DITA_EMBEDDING_MODEL_PATH and Path(DITA_EMBEDDING_MODEL_PATH).exists():
        return DITA_EMBEDDING_MODEL_PATH, "local_path"

    bundled = Path(__file__).resolve().parent.parent.parent / "models" / DITA_EMBEDDING_MODEL
    if bundled.exists():
        return str(bundled), "local_path_relative"

    if DITA_EMBEDDING_MODEL_PATH:
        logger.warning_structured(
            "DITA_EMBEDDING_MODEL_PATH not found on this host; falling back to model name",
            extra_fields={"configured_path": DITA_EMBEDDING_MODEL_PATH, "model": DITA_EMBEDDING_MODEL},
        )
    return DITA_EMBEDDING_MODEL, "model_name"


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

        identifier, mode = _resolve_embedding_source()
        _embedding_model = SentenceTransformer(identifier)
        _embedding_load_mode = mode
        _embedding_active_model_identifier = identifier
        logger.info_structured(
            "Loaded DITA embedding model",
            extra_fields={"identifier": identifier, "mode": mode},
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
    """Return True if embedding model is loaded OR Azure OpenAI embedding is configured."""
    model = _load_model()
    if model is not None:
        return True
    # Azure OpenAI fallback counts as available
    return bool(_AZURE_EMBED_ENDPOINT and _AZURE_EMBED_KEY)


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


def _azure_embedding_preferred() -> bool:
    """True when Azure embeddings should be used ahead of the local model.

    Needed when the Chroma collections were indexed with Azure embeddings
    (1536-dim ``ada-002``): the query vector MUST come from the same backend or
    the dimensions won't align (``shapes (n,1536) and (384,) not aligned``).
    Set ``USE_AZURE_EMBEDDING=true`` to pin queries to Azure.
    """
    return _USE_AZURE_EMBEDDING and bool(_AZURE_EMBED_ENDPOINT and _AZURE_EMBED_KEY)


def embed_texts(texts: list[str]):
    """
    Embed a batch of texts. Returns numpy array of shape (n, dim).
    Falls back to Azure OpenAI if local model unavailable.
    Returns None if both unavailable.
    """
    model = _load_model()
    if not texts:
        return None
    if _azure_embedding_preferred():
        import numpy as np
        azure_embs = _try_azure_embedding(list(texts))
        if azure_embs:
            return np.array(azure_embs)
        logger.warning_structured("Azure embedding preferred but failed, falling back to local model")
    if model is not None:
        try:
            return model.encode(texts, convert_to_numpy=True)
        except Exception as e:
            logger.warning_structured("Embedding batch failed, trying Azure", extra_fields={"error": str(e)})
    # Azure OpenAI fallback
    import numpy as np
    azure_embs = _try_azure_embedding(texts)
    if azure_embs:
        return np.array(azure_embs)
    return None


def embed_texts_batched(texts: list[str], batch_size: int = EMBED_BATCH_SIZE):
    """
    Embed texts in batches. Returns numpy array of shape (n, dim).
    Falls back to Azure OpenAI if local model unavailable.
    Returns None if both unavailable.
    """
    model = _load_model()
    if not texts:
        return None
    # Blank/None entries can make the local encoder or Azure reject the whole batch; replace
    # them with a single space to keep index alignment (n_embeddings == n_texts) intact.
    texts = [t if (isinstance(t, str) and t.strip()) else " " for t in texts]
    if _azure_embedding_preferred():
        import numpy as np
        all_embs = []
        for i in range(0, len(texts), 16):
            azure_embs = _try_azure_embedding(texts[i:i + 16])
            if not azure_embs:
                all_embs = []
                break
            all_embs.extend(azure_embs)
        if all_embs:
            return np.array(all_embs)
        logger.warning_structured("Azure embedding preferred but failed, falling back to local model")
    if model is not None:
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
            logger.warning_structured("Embedding batched failed, trying Azure", extra_fields={"error": str(e)})
    # Azure OpenAI fallback (batch in groups of 16)
    import numpy as np
    all_embs = []
    for i in range(0, len(texts), 16):
        batch = texts[i:i + 16]
        azure_embs = _try_azure_embedding(batch)
        if azure_embs:
            all_embs.extend(azure_embs)
        else:
            return None
    return np.array(all_embs) if all_embs else None


def embed_texts_batched_ORIGINAL(texts: list[str], batch_size: int = EMBED_BATCH_SIZE):
    """[Kept for reference] Original batched embedding without Azure fallback."""
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
