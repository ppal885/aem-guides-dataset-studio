"""Tests for token_budget — coordinated token allocation."""
import pytest
from app.services.token_budget import TokenBudgetManager, _estimate_tokens


class TestEstimateTokens:
    def test_empty_string(self):
        assert _estimate_tokens("") == 0

    def test_regular_text(self):
        text = "This is a regular text without XML."
        tokens = _estimate_tokens(text)
        # ~35 chars / 3.5 = ~10 tokens
        assert 8 <= tokens <= 12

    def test_xml_heavy_text(self):
        xml = "<task id='t1'><title>Configure PDF</title><taskbody><steps><step><cmd>Click</cmd></step></steps></taskbody></task>"
        tokens = _estimate_tokens(xml)
        # XML dense, should use ~2.5 chars/token
        expected_lower = len(xml) / 3.0
        expected_upper = len(xml) / 2.0
        assert expected_lower <= tokens <= expected_upper


class TestTokenBudgetManager:
    def test_auto_detect_provider_limits(self):
        groq = TokenBudgetManager(provider="groq")
        assert groq.total_limit == 10_000

        anthropic = TokenBudgetManager(provider="anthropic")
        assert anthropic.total_limit == 80_000

    def test_custom_limit_overrides(self):
        mgr = TokenBudgetManager(provider="groq", total_limit=5000)
        assert mgr.total_limit == 5000

    def test_allocate_system(self):
        mgr = TokenBudgetManager(provider="anthropic")
        tokens = mgr.allocate_system("You are a helpful assistant.")
        assert tokens > 0
        assert mgr.total_allocated == tokens
        assert mgr.remaining == mgr.total_limit - tokens

    def test_allocate_rag(self):
        mgr = TokenBudgetManager(provider="anthropic")
        mgr.allocate_system("System prompt")
        rag_tokens = mgr.allocate_rag("RAG context about DITA elements...")
        assert rag_tokens > 0
        assert mgr.allocation_breakdown["rag_context"] == rag_tokens

    def test_budget_for_messages_returns_remaining(self):
        mgr = TokenBudgetManager(provider="groq")
        mgr.allocate_system("Short prompt")
        budget = mgr.budget_for_messages()
        assert budget < mgr.total_limit
        assert budget > 0

    def test_truncate_messages_all_fit(self):
        mgr = TokenBudgetManager(provider="anthropic")
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = mgr.truncate_messages(messages)
        assert len(result) == 2

    def test_truncate_messages_overflow(self):
        mgr = TokenBudgetManager(provider="groq", total_limit=50)
        mgr.allocate_system("x" * 100)  # Over-allocate
        messages = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "Long " * 100},
            {"role": "user", "content": "Last message"},
        ]
        result = mgr.truncate_messages(messages)
        # Should keep at least last message
        assert len(result) >= 1
        assert result[-1]["content"] == "Last message"

    def test_truncate_keeps_first_and_last(self):
        mgr = TokenBudgetManager(provider="groq", total_limit=200)
        messages = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Middle " * 50},
            {"role": "user", "content": "Middle2 " * 50},
            {"role": "user", "content": "Last"},
        ]
        result = mgr.truncate_messages(messages)
        assert result[0]["content"] == "First"
        assert result[-1]["content"] == "Last"

    def test_allocate_tool_results_cumulative(self):
        mgr = TokenBudgetManager(provider="anthropic")
        t1 = mgr.allocate_tool_results("result1")
        t2 = mgr.allocate_tool_results("result2")
        assert mgr.allocation_breakdown["tool_results"] == t1 + t2

    def test_to_dict(self):
        mgr = TokenBudgetManager(provider="groq")
        mgr.allocate_system("prompt")
        d = mgr.to_dict()
        assert d["provider"] == "groq"
        assert "remaining" in d
        assert "breakdown" in d

    def test_empty_messages(self):
        mgr = TokenBudgetManager(provider="anthropic")
        assert mgr.truncate_messages([]) == []
