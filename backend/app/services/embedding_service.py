"""Embedding service for semantic retrieval - DITA chunks and recipes.

Uses sentence-transformers (for example ``all-MiniLM-L6-v2``) with lazy
loading, and supports a local fine-tuned model via ``DITA_EMBEDDING_MODEL_PATH``.
The service also exposes runtime diagnostics so callers can distinguish true
semantic retrieval from lexical fallback.
"""
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

_embedding_model = None
_embedding_available: Optional[bool] = None
_embedding_failure_reason = ""
_embedding_load_mode = "uninitialized"
_embedding_active_model_identifier = ""
_embedding_generation = 0
_last_embedding_status = "UNTESTED"
_last_embedding_error = ""
_last_embedding_dimension = None

DITA_EMBEDDING_MODEL = os.getenv("DITA_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
DITA_EMBEDDING_MODEL_PATH = os.getenv("DITA_EMBEDDING_MODEL_PATH", "").strip()

# Explicit provider selection. Different encoders are NOT interchangeable, even
# when they happen to return vectors of the same dimension.
_AZURE_EMBED_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
_AZURE_EMBED_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
_AZURE_EMBED_MODEL = os.getenv("AZURE_EMBEDDING_MODEL", "text-embedding-ada-002")
_AZURE_EMBED_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
_USE_AZURE_EMBEDDING = os.getenv("USE_AZURE_EMBEDDING", "false").lower() in ("1", "true", "yes", "on")

EMBED_DIM = 384  # all-MiniLM-L6-v2 output dimension; Azure ada-002 is 1536


def _try_azure_embedding(texts: list) -> Optional[list]:
    """Call only the explicitly selected Azure provider; never a local fallback."""
    if not _azure_embedding_preferred():
        return None
    try:
        import requests
        url = f"{_AZURE_EMBED_ENDPOINT}/openai/deployments/{_AZURE_EMBED_MODEL}/embeddings?api-version={_AZURE_EMBED_VERSION}"
        results = []
        for i in range(0, len(texts), 16):
            batch = texts[i:i + 16]
            r = requests.post(url, headers={"api-key": _AZURE_EMBED_KEY, "Content-Type": "application/json"},
                              json={"input": batch}, timeout=30, allow_redirects=False)
            if not r.ok:
                return None
            data = r.json().get("data", [])
            if (not isinstance(data, list) or len(data) != len(batch)
                    or any(not isinstance(d, dict) or type(d.get("index")) is not int for d in data)
                    or sorted(d["index"] for d in data) != list(range(len(batch)))):
                return None
            results.extend([d["embedding"] for d in sorted(data, key=lambda x: x["index"])])
        return results
    except Exception:
        # Transport exceptions can contain credential-bearing URLs. Log only a
        # fixed event, never the exception, payload, query text or vector.
        logger.debug_structured("azure_embedding_failed")
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
        if sys.version_info.releaselevel != "final":
            raise RuntimeError("PYTHON_PRERELEASE_UNSUPPORTED")
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
    except Exception:
        _embedding_available = False
        _embedding_failure_reason = ("PYTHON_PRERELEASE_UNSUPPORTED"
                                     if sys.version_info.releaselevel != "final"
                                     else "LOCAL_MODEL_LOAD_FAILED")
        _embedding_load_mode = "fallback_none"
        _embedding_active_model_identifier = DITA_EMBEDDING_MODEL_PATH or DITA_EMBEDDING_MODEL
        logger.warning_structured(
            "Local embedding unavailable; semantic retrieval cannot encode queries",
            extra_fields={"reason": _embedding_failure_reason},
        )
        return None


def is_embedding_available() -> bool:
    """Selected-provider readiness, not proof of successful/index-compatible encoding.

    Azure configuration allows an initial attempt (and recovery after an outage).
    Last-request success is separately exposed by get_embedding_diagnostics.
    """
    if _USE_AZURE_EMBEDDING:
        return _azure_embedding_preferred()
    return _load_model() is not None


def get_embedding_diagnostics() -> dict[str, Any]:
    """Return the current embedding runtime state for retrieval diagnostics."""
    ready = is_embedding_available()
    azure = _USE_AZURE_EMBEDDING
    identifier = _AZURE_EMBED_MODEL if azure else (
        _embedding_active_model_identifier or DITA_EMBEDDING_MODEL_PATH or DITA_EMBEDDING_MODEL)
    return {
        "configured_model": DITA_EMBEDDING_MODEL,
        "configured_model_path": DITA_EMBEDDING_MODEL_PATH,
        "active_model_identifier": identifier,
        "using_local_path": not azure and bool(DITA_EMBEDDING_MODEL_PATH),
        "available": ready and _last_embedding_status != "FAILED",
        "load_mode": ("azure_configured" if ready else "azure_unconfigured") if azure else _embedding_load_mode,
        "error": _last_embedding_error or ("" if azure else _embedding_failure_reason),
        "load_error": "" if azure else _embedding_failure_reason,
        "provider": "AZURE" if azure else "LOCAL",
        "ready": ready,
        "last_request_status": _last_embedding_status,
        "availability_verified": _last_embedding_status == "SUCCESS",
        "last_vector_dimension": _last_embedding_dimension,
    }


def reset_embedding_runtime_state() -> None:
    """Reset cached embedding runtime state.

    This is mainly intended for tests that monkeypatch model loading or env-like
    module constants and need a clean lazy-load attempt.
    """
    global _embedding_model, _embedding_available
    global _embedding_failure_reason, _embedding_load_mode, _embedding_active_model_identifier
    global _embedding_generation, _last_embedding_status, _last_embedding_error, _last_embedding_dimension
    _embedding_model = None
    _embedding_available = None
    _embedding_failure_reason = ""
    _embedding_load_mode = "uninitialized"
    _embedding_active_model_identifier = ""
    _embedding_generation += 1
    _last_embedding_status = "UNTESTED"
    _last_embedding_error = ""
    _last_embedding_dimension = None


def embedding_cache_namespace() -> str:
    """Non-secret provider/config/reset identity; does not load or call a model.

    This prevents cached vectors crossing a provider change or runtime reset. It
    is NOT an artifact hash or proof of historical ingestion-model parity. Replace
    model files only with a backend restart/reset, never underneath a live model.
    """
    identity = (["AZURE", _AZURE_EMBED_ENDPOINT, _AZURE_EMBED_MODEL, _AZURE_EMBED_VERSION]
                if _USE_AZURE_EMBEDDING else ["LOCAL", DITA_EMBEDDING_MODEL, DITA_EMBEDDING_MODEL_PATH])
    return hashlib.sha256(json.dumps([identity, _embedding_generation]).encode("utf-8")).hexdigest()


EMBED_BATCH_SIZE = 64


def _azure_embedding_preferred() -> bool:
    """True when Azure is explicitly selected and configured (exclusive, not fallback).

    Needed when the Chroma collections were indexed with Azure embeddings
    (1536-dim ``ada-002``): the query vector MUST come from the same backend or
    the dimensions won't align (``shapes (n,1536) and (384,) not aligned``).
    Set ``USE_AZURE_EMBEDDING=true`` to pin queries to Azure.
    """
    return _USE_AZURE_EMBEDDING and bool(_AZURE_EMBED_ENDPOINT and _AZURE_EMBED_KEY)


def embed_texts(texts: list[str]):
    """Embed with the selected provider only; return None on its failure."""
    if not texts:
        return None
    return _encode_selected(texts, None)


def embed_texts_batched(texts: list[str], batch_size: int = EMBED_BATCH_SIZE):
    """All-or-nothing batches from one provider; never mix vector spaces."""
    if not texts:
        return None
    # Blank/None entries can make the local encoder or Azure reject the whole batch; replace
    # them with a single space to keep index alignment (n_embeddings == n_texts) intact.
    texts = [t if (isinstance(t, str) and t.strip()) else " " for t in texts]
    if type(batch_size) is not int or batch_size < 1:
        _record_embedding_failure("INVALID_BATCH_SIZE")
        return None
    return _encode_selected(texts, batch_size)


def _record_embedding_failure(reason: str) -> None:
    global _last_embedding_status, _last_embedding_error, _last_embedding_dimension
    _last_embedding_status, _last_embedding_error, _last_embedding_dimension = "FAILED", reason, None
    logger.warning_structured("Embedding request failed; no provider fallback",
                              extra_fields={"provider": "AZURE" if _USE_AZURE_EMBEDDING else "LOCAL",
                                            "reason": reason})


def _validated_embeddings(value, rows: int):
    import numpy as np
    array = np.asarray(value)
    if (array.ndim != 2 or array.shape[0] != rows or array.shape[1] < 1
            or array.dtype.kind not in "fiu" or not np.isfinite(array).all()):
        raise ValueError("INVALID_EMBEDDING_RESPONSE")
    return array


def _encode_selected(texts: list[str], batch_size: Optional[int]):
    global _last_embedding_status, _last_embedding_error, _last_embedding_dimension
    try:
        if _USE_AZURE_EMBEDDING:
            if not _azure_embedding_preferred():
                _record_embedding_failure("AZURE_NOT_CONFIGURED")
                return None
            value = _try_azure_embedding(list(texts))
        else:
            model = _load_model()
            if model is None:
                _record_embedding_failure("LOCAL_MODEL_UNAVAILABLE")
                return None
            if batch_size is None:
                value = model.encode(texts, convert_to_numpy=True)
            else:
                import numpy as np
                batches = []
                for i in range(0, len(texts), batch_size):
                    batch = texts[i:i + batch_size]
                    batches.append(_validated_embeddings(model.encode(batch, convert_to_numpy=True), len(batch)))
                value = np.vstack(batches)
        result = _validated_embeddings(value, len(texts))
    except Exception:
        _record_embedding_failure("ENCODE_OR_RESPONSE_FAILED")
        return None
    _last_embedding_status, _last_embedding_error = "SUCCESS", ""
    _last_embedding_dimension = int(result.shape[1])
    return result


def embed_texts_batched_ORIGINAL(texts: list[str], batch_size: int = EMBED_BATCH_SIZE):
    """Legacy callable retained without allowing it to bypass provider selection."""
    return embed_texts_batched(texts, batch_size)


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
