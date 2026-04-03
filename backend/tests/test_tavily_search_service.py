"""Tests for Tavily web search helpers used by chat and corrective RAG."""
import pytest

from app.services import tavily_search_service as tss


def test_is_chat_tavily_enabled_requires_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("CHAT_TAVILY_ENABLED", raising=False)
    assert tss.is_chat_tavily_enabled() is False


def test_is_chat_tavily_enabled_true_when_key_and_not_disabled(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.delenv("CHAT_TAVILY_ENABLED", raising=False)
    assert tss.is_chat_tavily_enabled() is True


def test_is_chat_tavily_enabled_false_when_explicitly_off(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setenv("CHAT_TAVILY_ENABLED", "false")
    assert tss.is_chat_tavily_enabled() is False


def test_tavily_search_sync_returns_none_without_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert tss.tavily_search_sync("hello", category="aem_guides") is None


def test_format_tavily_block_for_chat():
    payload = {
        "answer": "Short answer",
        "results": [
            {"title": "T1", "url": "https://example.com/a", "content": "Body one"},
        ],
    }
    out = tss.format_tavily_block_for_chat(payload, max_chars=5000)
    assert "WEB SEARCH (Tavily):" in out
    assert "Short answer" in out
    assert "https://example.com/a" in out


def test_merge_tavily_into_rag_context_truncates():
    rag = "x" * 100
    tavily = "y" * 200
    merged = tss.merge_tavily_into_rag_context(rag, tavily, max_total_chars=150)
    assert len(merged) <= 150
    assert "[truncated]" in merged


def test_get_tavily_api_key_prefers_tavily_api_key_then_tavily_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_KEY", raising=False)
    assert tss.get_tavily_api_key() == ""
    monkeypatch.setenv("TAVILY_KEY", "from-alias")
    assert tss.get_tavily_api_key() == "from-alias"
    monkeypatch.setenv("TAVILY_API_KEY", "primary")
    assert tss.get_tavily_api_key() == "primary"


def test_get_tavily_rag_status_no_secrets(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_KEY", raising=False)
    s = tss.get_tavily_rag_status()
    assert s["configured"] is False
    assert s["chat_enabled"] is False
    assert s.get("hint")
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setenv("CHAT_TAVILY_ENABLED", "true")
    s2 = tss.get_tavily_rag_status()
    assert s2["configured"] is True
    assert s2["chat_enabled"] is True
    assert s2.get("hint") is None


def test_get_tavily_api_key_strips_quotes(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", '"tvly-quoted"')
    assert tss.get_tavily_api_key() == "tvly-quoted"


def test_resolve_include_domains_override(monkeypatch):
    monkeypatch.setenv("TAVILY_INCLUDE_DOMAINS", "foo.com, bar.org")
    assert tss.resolve_include_domains("anything") == ["foo.com", "bar.org"]


def test_chat_tavily_max_results_bounds(monkeypatch):
    monkeypatch.setenv("CHAT_TAVILY_MAX_RESULTS", "99")
    assert tss.chat_tavily_max_results() == 10
    monkeypatch.setenv("CHAT_TAVILY_MAX_RESULTS", "0")
    assert tss.chat_tavily_max_results() == 1
