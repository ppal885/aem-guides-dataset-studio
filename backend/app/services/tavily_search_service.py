"""Tavily web search — shared by corrective RAG and chat RAG context.

Set the API key in **backend/.env** (loaded at startup by app/main.py), not in the frontend:
  TAVILY_API_KEY=tvly-...
Optional alias: TAVILY_KEY (used only if TAVILY_API_KEY is empty).

Chat mode: ``is_chat_tavily_enabled()`` gates **all** Tavily usage in chat corrective RAG — both the
general web fallback and the Experience League–filtered search. Set ``CHAT_TAVILY_ENABLED=false`` to
disable entirely while keeping the key for other features, if any.
"""
from __future__ import annotations

import os
from typing import Any

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

# Default domain filters by category (align with corrective RAG / research flows)
TAVILY_CATEGORY_DOMAINS: dict[str, list[str]] = {
    "aem_guides": ["experienceleague.adobe.com", "helpx.adobe.com"],
    "bugs_fixes": ["experienceleague.adobe.com", "helpx.adobe.com", "adobe.com"],
    "default": ["experienceleague.adobe.com", "docs.oasis-open.org"],
}


def _strip_key_value(raw: str | None) -> str:
    if not raw:
        return ""
    s = raw.strip()
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        s = s[1:-1]
    return s.strip()


def get_tavily_api_key() -> str:
    """Primary: TAVILY_API_KEY. Fallback: TAVILY_KEY (same Tavily dashboard key)."""
    for name in ("TAVILY_API_KEY", "TAVILY_KEY"):
        v = _strip_key_value(os.getenv(name))
        if v:
            return v
    return ""


def resolve_include_domains(category: str) -> list[str]:
    override = (os.getenv("TAVILY_INCLUDE_DOMAINS") or "").strip()
    if override:
        return [d.strip() for d in override.split(",") if d.strip()]
    return TAVILY_CATEGORY_DOMAINS.get(category, TAVILY_CATEGORY_DOMAINS["default"])


def is_chat_tavily_enabled() -> bool:
    """When TAVILY_API_KEY is set, chat uses Tavily unless CHAT_TAVILY_ENABLED is explicitly false."""
    if not get_tavily_api_key():
        return False
    raw = (os.getenv("CHAT_TAVILY_ENABLED") or "").strip().lower()
    if raw in ("false", "0", "no"):
        return False
    return True


def chat_tavily_max_results() -> int:
    try:
        return max(1, min(10, int(os.getenv("CHAT_TAVILY_MAX_RESULTS", "4"))))
    except ValueError:
        return 4


def tavily_search_sync(
    query: str,
    *,
    category: str = "aem_guides",
    max_results: int | None = None,
) -> dict[str, Any] | None:
    """
    Run Tavily search synchronously (call from asyncio.to_thread in async code).
    Returns the API response dict, or None if skipped / error.
    """
    api_key = get_tavily_api_key()
    if not api_key:
        return None
    q = (query or "").strip()
    if not q:
        return None
    mr = max_results if max_results is not None else chat_tavily_max_results()
    try:
        from tavily import TavilyClient

        domains = resolve_include_domains(category)
        client = TavilyClient(api_key=api_key)
        return client.search(
            query=q,
            search_depth="advanced",
            include_domains=domains,
            include_answer=True,
            max_results=mr,
        )
    except ImportError:
        logger.warning_structured(
            "tavily-python not installed",
            extra_fields={"hint": "pip install tavily-python"},
        )
        return None
    except Exception as exc:
        logger.warning_structured(
            "Tavily search failed",
            extra_fields={"error": str(exc), "category": category},
        )
        return None


def format_tavily_block_for_chat(payload: dict[str, Any], *, max_chars: int) -> str:
    """Format Tavily API response for the chat system prompt."""
    parts: list[str] = []
    answer = str(payload.get("answer") or "").strip()
    if answer:
        parts.append(f"Summary: {answer}")
    for i, item in enumerate(payload.get("results") or [], 1):
        title = str(item.get("title") or "Result").strip()
        url = str(item.get("url") or "").strip()
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        block = f"[{i}] {title}\n{url}\n{content[:1200]}"
        parts.append(block)
    text = "\n\n".join(parts).strip()
    if not text:
        return ""
    if len(text) > max_chars:
        text = text[: max(0, max_chars - 30)] + "\n\n[truncated]"
    return "WEB SEARCH (Tavily):\n" + text


def merge_tavily_into_rag_context(rag_context: str, tavily_block: str, *, max_total_chars: int) -> str:
    """Append Tavily block and enforce max length on the combined string."""
    if not tavily_block:
        return rag_context
    sep = "\n\n"
    head = rag_context or ""
    combined = head + sep + tavily_block
    if len(combined) <= max_total_chars:
        return combined
    avail = max_total_chars - len(head) - len(sep)
    if avail <= 0:
        return head[:max_total_chars]
    marker = "\n[truncated]"
    if len(tavily_block) > avail:
        take = max(0, avail - len(marker))
        tail = (tavily_block[:take] + marker) if take else marker[:avail]
    else:
        tail = tavily_block
    out = head + sep + tail
    return out[:max_total_chars]


def get_tavily_rag_status() -> dict[str, Any]:
    """For GET /rag-status — booleans only, no secrets."""
    configured = bool(get_tavily_api_key())
    chat_on = configured and is_chat_tavily_enabled()
    return {
        "configured": configured,
        "chat_enabled": chat_on,
        # Hints for Settings UI when key seems missing (no secret values)
        "hint": (
            None
            if configured
            else "Set TAVILY_API_KEY in backend/.env or project-root .env, then restart the backend."
        ),
    }
