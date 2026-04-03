"""Tests for Anthropic/Bedrock text_stream unpack hardening in llm_service."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import llm_service


class _UnpackAfterFirstChunk:
    """Async iterator: one value then SDK-style unpack error."""

    def __init__(self) -> None:
        self._n = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._n == 0:
            self._n += 1
            return "hello"
        raise ValueError("not enough values to unpack (expected 2, got 1)")


class _NonUnpackError:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise ValueError("rate limit exceeded")


def test_iter_text_stream_safe_swallows_unpack_after_first_chunk():
    async def _run():
        out: list[object] = []
        async for x in llm_service._iter_text_stream_safe(_UnpackAfterFirstChunk()):
            out.append(x)
        return out

    assert asyncio.run(_run()) == ["hello"]


def test_iter_text_stream_safe_reraises_non_unpack_valueerror():
    async def _run():
        async for _ in llm_service._iter_text_stream_safe(_NonUnpackError()):
            pass

    with pytest.raises(ValueError, match="rate limit"):
        asyncio.run(_run())


def test_stream_with_tools_anthropic_done_after_partial_non_unpack_error():
    """After streaming text, a non-unpack error from text_stream must not bubble to the client."""

    class FlakyTextStream:
        def __init__(self) -> None:
            self._n = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._n == 0:
                self._n += 1
                return "partial"
            raise ValueError("rate limit exceeded")

    class MockStream:
        def __init__(self) -> None:
            self.text_stream = FlakyTextStream()

        async def get_final_message(self):
            return SimpleNamespace(
                stop_reason="end_turn",
                content=[],
                usage=None,
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class MockMessages:
        def stream(self, **kwargs):
            return MockStream()

    class MockClient:
        messages = MockMessages()

    async def _collect():
        events: list[tuple[str, object]] = []
        async for evt in llm_service._stream_with_tools_anthropic(
            "system",
            [{"role": "user", "content": "hi"}],
            [],
            max_tokens=256,
            timeout_sec=30.0,
        ):
            events.append(evt)
        return events

    with patch("anthropic.AsyncAnthropic", return_value=MockClient()):
        events = asyncio.run(_collect())

    types = [e[0] for e in events]
    assert "chunk" in types
    assert types[-1] == "done"
    chunk_texts = [e[1] for e in events if e[0] == "chunk" and e[1]]
    assert "".join(str(t) for t in chunk_texts) == "partial"


def test_is_stream_unpack_bug_broader_phrases():
    assert llm_service._is_stream_unpack_bug(ValueError("not enough values to unpack (expected 2, got 1)"))
    assert llm_service._is_stream_unpack_bug(ValueError("too few values to unpack"))
    assert not llm_service._is_stream_unpack_bug(ValueError("unrelated"))


def test_anthropic_tool_defs_to_openai_shape():
    tools = [
        {
            "name": "generate_dita",
            "description": "Do the thing",
            "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        }
    ]
    oa = llm_service._anthropic_tool_defs_to_openai(tools)
    assert len(oa) == 1
    assert oa[0]["type"] == "function"
    assert oa[0]["function"]["name"] == "generate_dita"
    assert oa[0]["function"]["parameters"]["type"] == "object"


def test_chat_messages_anthropic_style_to_openai_tool_round():
    import json as _json

    msgs = [
        {"role": "assistant", "content": [{"type": "text", "text": "x"}, {"type": "tool_use", "id": "c1", "name": "generate_dita", "input": {"text": "a"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": _json.dumps({"ok": True})}]},
    ]
    oa = llm_service._chat_messages_anthropic_style_to_openai("system prompt", msgs)
    assert oa[0] == {"role": "system", "content": "system prompt"}
    assert oa[1]["role"] == "assistant" and oa[1]["content"] == "x"
    assert len(oa[1]["tool_calls"]) == 1
    assert oa[1]["tool_calls"][0]["id"] == "c1"
    assert oa[2]["role"] == "tool" and oa[2]["tool_call_id"] == "c1"


def test_flatten_anthropic_content_blocks_to_string():
    s = llm_service._flatten_anthropic_content_blocks_to_string(
        [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
    )
    assert s == "a\nb"
