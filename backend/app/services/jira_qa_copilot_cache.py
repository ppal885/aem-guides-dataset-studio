"""Lightweight in-process caches for Jira QA Copilot (embeddings, context blobs)."""

from __future__ import annotations

import hashlib
import os
import time
from threading import Lock
from typing import Any, Optional

_LOCK = Lock()
_EMBEDDING_CACHE: dict[str, tuple[list[float], float]] = {}
_CONTEXT_CACHE: dict[str, tuple[str, float]] = {}
_MAX_EMB = int(os.getenv("JIRA_QA_COPILOT_EMBED_CACHE_MAX", "384"))
_MAX_CTX = int(os.getenv("JIRA_QA_COPILOT_CONTEXT_CACHE_MAX", "256"))
_TTL_EMB = float(os.getenv("JIRA_QA_COPILOT_EMBED_CACHE_TTL", "600"))
_TTL_CTX = float(os.getenv("JIRA_QA_COPILOT_CONTEXT_CACHE_TTL", "300"))


def _hash_key(prefix: str, text: str) -> str:
    h = hashlib.sha256(f"{prefix}:{text[:24000]}".encode("utf-8", errors="ignore")).hexdigest()[:32]
    return f"{prefix}:{h}"


def _evict_oldest(store: dict[str, Any], n: int) -> None:
    if not store or n <= 0:
        return
    items = sorted(store.items(), key=lambda x: x[1][1])[: max(1, n)]
    for k, _ in items:
        store.pop(k, None)


def cache_get_embedding_vector(text: str) -> Optional[list[float]]:
    key = _hash_key("emb", text)
    now = time.monotonic()
    with _LOCK:
        item = _EMBEDDING_CACHE.get(key)
        if item and now - item[1] < _TTL_EMB:
            return item[0]
    return None


def cache_set_embedding_vector(text: str, vector: list[float]) -> None:
    key = _hash_key("emb", text)
    now = time.monotonic()
    with _LOCK:
        if len(_EMBEDDING_CACHE) >= _MAX_EMB:
            _evict_oldest(_EMBEDDING_CACHE, _MAX_EMB // 4)
        _EMBEDDING_CACHE[key] = (vector, now)


def cache_get_context(jira_key: str, chunk_sig: str) -> Optional[str]:
    key = _hash_key("ctx", f"{jira_key}:{chunk_sig}")
    now = time.monotonic()
    with _LOCK:
        item = _CONTEXT_CACHE.get(key)
        if item and now - item[1] < _TTL_CTX:
            return item[0]
    return None


def cache_set_context(jira_key: str, chunk_sig: str, blob: str) -> None:
    key = _hash_key("ctx", f"{jira_key}:{chunk_sig}")
    now = time.monotonic()
    with _LOCK:
        if len(_CONTEXT_CACHE) >= _MAX_CTX:
            _evict_oldest(_CONTEXT_CACHE, _MAX_CTX // 4)
        _CONTEXT_CACHE[key] = (blob, now)


def clear_copilot_caches_for_tests() -> None:
    with _LOCK:
        _EMBEDDING_CACHE.clear()
        _CONTEXT_CACHE.clear()
