"""Coordinated token budget manager for chat context window.

Replaces the dual truncation strategy (token-based OR message-count) with a
single budget allocator that tracks per-section token usage.

Feature flag: CHAT_TOKEN_BUDGET (default False — opt-in)
"""
import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Provider-specific default context limits (conservative estimates leaving room for output)
_PROVIDER_DEFAULTS: dict[str, int] = {
    "groq": 10_000,       # Groq Llama 3.3 has ~12K TPM; leave headroom
    "openai": 60_000,     # GPT-4o context
    "anthropic": 80_000,  # Claude context
    "bedrock": 80_000,    # Claude via Bedrock
}

# XML density threshold: if more than 8% of chars are '<', treat as XML-heavy
_XML_DENSITY_THRESHOLD = 0.08


def _estimate_tokens(text: str) -> int:
    """Estimate token count with XML-density awareness.

    Regular text: ~3.5 chars per token
    XML-heavy content: ~2.5 chars per token (more tokens due to tag syntax)
    """
    if not text:
        return 0
    length = len(text)
    # Count angle brackets to detect XML density
    bracket_count = text.count("<") + text.count(">")
    density = bracket_count / max(length, 1)
    if density > _XML_DENSITY_THRESHOLD:
        return max(1, int(length / 2.5))
    return max(1, int(length / 3.5))


def _estimate_message_tokens(messages: list[dict]) -> int:
    """Estimate total tokens in a message list."""
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total += _estimate_tokens(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total += _estimate_tokens(block.get("text", "") or block.get("content", "") or "")
                elif isinstance(block, str):
                    total += _estimate_tokens(block)
        # Add overhead per message (role, metadata)
        total += 4
    return total


@dataclass
class TokenBudgetManager:
    """Manages token budget allocation across context sections."""

    provider: str = "anthropic"
    total_limit: int = 0  # 0 = auto-detect from provider
    _allocated: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.total_limit <= 0:
            self.total_limit = _PROVIDER_DEFAULTS.get(
                self.provider.lower(), _PROVIDER_DEFAULTS["anthropic"]
            )

    @property
    def total_allocated(self) -> int:
        """Total tokens allocated so far across all sections."""
        return sum(self._allocated.values())

    @property
    def remaining(self) -> int:
        """Tokens remaining in the budget."""
        return max(0, self.total_limit - self.total_allocated)

    @property
    def allocation_breakdown(self) -> dict[str, int]:
        """Current allocation by section."""
        return dict(self._allocated)

    def allocate_system(self, system_prompt: str) -> int:
        """Allocate tokens for the system prompt. Returns tokens used."""
        tokens = _estimate_tokens(system_prompt)
        self._allocated["system_prompt"] = tokens
        return tokens

    def allocate_rag(self, rag_context: str) -> int:
        """Allocate tokens for RAG context. Returns tokens used."""
        tokens = _estimate_tokens(rag_context)
        self._allocated["rag_context"] = tokens
        return tokens

    def allocate_tool_results(self, tool_results_text: str) -> int:
        """Allocate tokens for tool results in this round. Returns tokens used."""
        tokens = _estimate_tokens(tool_results_text)
        prev = self._allocated.get("tool_results", 0)
        self._allocated["tool_results"] = prev + tokens
        return tokens

    def budget_for_messages(self) -> int:
        """Return available token budget for conversation messages."""
        return self.remaining

    def truncate_messages(self, messages: list[dict]) -> list[dict]:
        """Truncate message history to fit within remaining budget.

        Strategy: keep the most recent messages that fit.
        Always preserves the first message (system context) and last message (current user query).
        """
        if not messages:
            return messages

        budget = self.budget_for_messages()
        if budget <= 0:
            # Emergency: at least keep the last user message
            return messages[-1:] if messages else []

        # Check if everything fits
        total = _estimate_message_tokens(messages)
        if total <= budget:
            self._allocated["messages"] = total
            return messages

        # Keep first + last, fill from the end
        if len(messages) <= 2:
            self._allocated["messages"] = _estimate_message_tokens(messages)
            return messages

        first = messages[0]
        last = messages[-1]
        first_tokens = _estimate_message_tokens([first])
        last_tokens = _estimate_message_tokens([last])
        available = budget - first_tokens - last_tokens

        if available <= 0:
            result = [first, last]
            self._allocated["messages"] = first_tokens + last_tokens
            return result

        # Fill middle from most recent backward
        middle: list[dict] = []
        middle_tokens = 0
        for msg in reversed(messages[1:-1]):
            msg_tokens = _estimate_message_tokens([msg])
            if middle_tokens + msg_tokens > available:
                break
            middle.insert(0, msg)
            middle_tokens += msg_tokens

        result = [first] + middle + [last]
        self._allocated["messages"] = first_tokens + middle_tokens + last_tokens
        return result

    def to_dict(self) -> dict[str, Any]:
        """Export budget state for logging/SSE."""
        return {
            "provider": self.provider,
            "total_limit": self.total_limit,
            "total_allocated": self.total_allocated,
            "remaining": self.remaining,
            "breakdown": self.allocation_breakdown,
        }
