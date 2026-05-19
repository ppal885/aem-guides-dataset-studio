"""Shared RAG tuning (query length caps, etc.) for chat and corrective RAG."""

from __future__ import annotations

import os


def _safe_int(name: str, default: int, *, min_v: int, max_v: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        v = default
    else:
        try:
            v = int(raw)
        except ValueError:
            v = default
    return max(min_v, min(v, max_v))


# Max characters of user query passed into embedding-based retrievers (AEM/DITA/tenant/claude snippets).
RAG_QUERY_MAX_CHARS = _safe_int("RAG_QUERY_MAX_CHARS", 4000, min_v=256, max_v=32000)
