"""
Per-IP rate limiting for API endpoints.
Uses sliding-window in-memory store. For multi-instance deployments, use Redis-backed limiter.
"""
import os
import threading
import time
from collections import defaultdict
from typing import Optional

# Configurable via env
CHAT_SESSIONS_RPM = int(os.getenv("RATE_LIMIT_CHAT_SESSIONS_RPM", "30"))  # POST /chat/sessions
CHAT_MESSAGES_RPM = int(os.getenv("RATE_LIMIT_CHAT_MESSAGES_RPM", "60"))  # POST /chat/sessions/{id}/messages
GENERATE_FROM_TEXT_RPM = int(os.getenv("RATE_LIMIT_GENERATE_FROM_TEXT_RPM", "10"))  # POST /ai/generate-from-text

# Sliding window: keep timestamps for last 60 seconds
WINDOW_SECONDS = 60

_store: dict[str, list[float]] = defaultdict(list)
_lock = threading.Lock()


def _get_client_ip(request) -> str:
    """Extract client IP from request. Handles X-Forwarded-For when behind proxy."""
    forwarded = getattr(request, "headers", None) and request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = getattr(request, "client", None)
    if client and getattr(client, "host", None):
        return client.host
    return "unknown"


def _prune(key: str) -> None:
    """Remove timestamps outside the sliding window."""
    cutoff = time.monotonic() - WINDOW_SECONDS
    _store[key] = [t for t in _store[key] if t >= cutoff]


def check_rate_limit(key: str, limit: int) -> bool:
    """
    Check if request is within rate limit. If so, record the request and return True.
    If over limit, return False. Caller should return 429.
    """
    with _lock:
        _prune(key)
        if len(_store[key]) >= limit:
            return False
        _store[key].append(time.monotonic())
        return True


def get_retry_after(key: str, limit: int) -> int:
    """Return seconds until a slot is available (for Retry-After header)."""
    with _lock:
        _prune(key)
        if len(_store[key]) < limit:
            return 0
        oldest = min(_store[key])
        return max(1, int(WINDOW_SECONDS - (time.monotonic() - oldest)))


def rate_limit_key(prefix: str, client_ip: str) -> str:
    return f"{prefix}:{client_ip}"


def check_chat_sessions_limit(request) -> Optional[str]:
    """
    Check rate limit for POST /chat/sessions.
    Returns error message if over limit, None if OK.
    """
    ip = _get_client_ip(request)
    key = rate_limit_key("chat_sessions", ip)
    if check_rate_limit(key, CHAT_SESSIONS_RPM):
        return None
    retry = get_retry_after(key, CHAT_SESSIONS_RPM)
    return f"Rate limit exceeded. Try again in {retry} seconds."


def check_chat_messages_limit(request) -> Optional[str]:
    """
    Check rate limit for POST /chat/sessions/{id}/messages.
    Returns error message if over limit, None if OK.
    """
    ip = _get_client_ip(request)
    key = rate_limit_key("chat_messages", ip)
    if check_rate_limit(key, CHAT_MESSAGES_RPM):
        return None
    retry = get_retry_after(key, CHAT_MESSAGES_RPM)
    return f"Rate limit exceeded. Try again in {retry} seconds."


def check_generate_from_text_limit(request) -> Optional[str]:
    """
    Check rate limit for POST /ai/generate-from-text.
    Returns error message if over limit, None if OK.
    """
    ip = _get_client_ip(request)
    key = rate_limit_key("generate_from_text", ip)
    if check_rate_limit(key, GENERATE_FROM_TEXT_RPM):
        return None
    retry = get_retry_after(key, GENERATE_FROM_TEXT_RPM)
    return f"Rate limit exceeded. Try again in {retry} seconds."
