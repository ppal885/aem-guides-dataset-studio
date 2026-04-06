"""Tool result caching — avoids redundant tool executions within a session.

Read-only tools (lookups, searches) are cached by (tool_name, params_hash).
Mutation tools (generate_dita, create_job) are never cached.

Feature flag: CHAT_TOOL_CACHE_ENABLED (default False)
"""
import hashlib
import json
import os
import time
from typing import Any, Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger("tool_result_cache")

# Tools that modify state — never cache these
_MUTATION_TOOLS = frozenset({
    "generate_dita",
    "create_job",
    "fix_dita_xml",
    "review_dita_xml",
})

_DEFAULT_TTL = int(os.getenv("CHAT_TOOL_CACHE_TTL", "300"))  # seconds


def _params_hash(params: dict) -> str:
    """Deterministic hash of tool parameters for cache key."""
    canonical = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class ToolResultCache:
    """In-memory LRU-ish cache for tool results within a chat turn/session."""

    def __init__(self, ttl: int = _DEFAULT_TTL, max_entries: int = 100):
        self._store: dict[str, tuple[Any, float]] = {}  # key -> (result, expire_time)
        self._ttl = ttl
        self._max_entries = max_entries

    def _make_key(self, tool_name: str, params: dict) -> str:
        return f"{tool_name}:{_params_hash(params)}"

    def get(self, tool_name: str, params: dict) -> Optional[dict]:
        """Return cached result if available and not expired. None on miss."""
        if tool_name in _MUTATION_TOOLS:
            return None
        key = self._make_key(tool_name, params)
        entry = self._store.get(key)
        if entry is None:
            return None
        result, expire_at = entry
        if time.monotonic() > expire_at:
            del self._store[key]
            return None
        logger.debug(f"Cache hit for {tool_name}")
        return result

    def put(self, tool_name: str, params: dict, result: Any) -> None:
        """Store a tool result in cache."""
        if tool_name in _MUTATION_TOOLS:
            return
        # Evict oldest if over limit
        if len(self._store) >= self._max_entries:
            oldest_key = min(self._store, key=lambda k: self._store[k][1])
            del self._store[oldest_key]
        key = self._make_key(tool_name, params)
        self._store[key] = (result, time.monotonic() + self._ttl)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def hit_rate_info(self) -> str:
        """Simple info string for logging."""
        return f"cache_size={len(self._store)}"
