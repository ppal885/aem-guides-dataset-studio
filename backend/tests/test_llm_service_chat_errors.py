import json

import pytest

from app.services import chat_service, llm_service
from app.services.llm_service import (
    _coerce_llm_text_response,
    _is_stream_unpack_bug,
    format_llm_error_for_user,
)


def test_format_llm_error_for_user_explains_quota_and_fallback():
    exc = RuntimeError(
        "Error code: 429 - {'error': {'message': 'You exceeded your current quota', 'type': 'insufficient_quota', 'code': 'insufficient_quota'}}"
    )

    message = format_llm_error_for_user(
        exc,
        primary_provider="openai",
        fallback_provider="groq",
        fallback_attempted=True,
    )

    assert "temporarily unavailable" in message
    assert "out of quota" in message


def test_is_stream_unpack_bug_detects_nested_provider_error():
    root = ValueError("not enough values to unpack (expected 2, got 1)")
    exc = RuntimeError("provider stream failed")
    exc.__cause__ = root

    assert _is_stream_unpack_bug(exc) is True


def test_chat_fallback_provider_is_disabled_when_unset(monkeypatch):
    monkeypatch.setattr(llm_service, "LLM_FALLBACK_PROVIDER", "")
    monkeypatch.setattr(llm_service, "GROQ_API_KEY", "test-groq-key")

    assert llm_service._get_chat_fallback_provider("openai") is None


def test_get_llm_provider_configuration_supports_azure_openai(monkeypatch):
    monkeypatch.setattr(llm_service, "LLM_PROVIDER", "azure_openai")
    monkeypatch.setattr(llm_service, "USE_BEDROCK", False)
    monkeypatch.setattr(llm_service, "AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setattr(llm_service, "AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setattr(llm_service, "AZURE_OPENAI_API_VERSION", "2024-02-01")
    monkeypatch.setattr(llm_service, "AZURE_OPENAI_MODEL", "gpt-4.1-deployment")

    config = llm_service.get_llm_provider_configuration()

    assert config["provider"] == "azure_openai"
    assert config["provider_label"] == "Azure OpenAI"
    assert config["model"] == "gpt-4.1-deployment"
    assert config["available"] is True


def test_generation_fallback_supports_azure_openai(monkeypatch):
    monkeypatch.setattr(llm_service, "LLM_FALLBACK_PROVIDER", "azure_openai")
    monkeypatch.setattr(llm_service, "AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setattr(llm_service, "AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setattr(llm_service, "AZURE_OPENAI_API_VERSION", "2024-02-01")
    monkeypatch.setattr(llm_service, "AZURE_OPENAI_MODEL", "gpt-4.1-deployment")

    model, fn, override = llm_service._get_generation_fallback("groq")

    assert model == "gpt-4.1-deployment"
    assert fn is llm_service._generate_openai
    assert override is None


def test_chat_fallback_is_disabled_when_primary_provider_is_azure(monkeypatch):
    monkeypatch.setattr(llm_service, "LLM_PROVIDER", "azure_openai")
    monkeypatch.setattr(llm_service, "LLM_FALLBACK_PROVIDER", "anthropic")
    monkeypatch.setattr(llm_service, "USE_BEDROCK", False)
    monkeypatch.setattr(llm_service, "ANTHROPIC_API_KEY", "anthropic-key")

    assert llm_service._get_chat_fallback_provider("azure_openai") is None


def test_generation_fallback_is_disabled_when_primary_provider_is_azure(monkeypatch):
    monkeypatch.setattr(llm_service, "LLM_PROVIDER", "azure_openai")
    monkeypatch.setattr(llm_service, "LLM_FALLBACK_PROVIDER", "openai")
    monkeypatch.setattr(llm_service, "USE_BEDROCK", False)
    monkeypatch.setattr(llm_service, "OPENAI_API_KEY", "openai-key")

    model, fn, override = llm_service._get_generation_fallback("azure_openai")

    assert model is None
    assert fn is None
    assert override is None


def test_generation_fallback_requires_explicit_provider(monkeypatch):
    monkeypatch.setattr(llm_service, "LLM_FALLBACK_PROVIDER", "")
    monkeypatch.setattr(llm_service, "ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setattr(llm_service, "ANTHROPIC_FALLBACK_MODEL", "claude-test")

    model, fn, override = llm_service._get_generation_fallback("openai")

    assert model is None
    assert fn is None
    assert override is None


def test_coerce_llm_text_response_handles_non_string_payloads():
    assert _coerce_llm_text_response(None) == ""
    assert _coerce_llm_text_response({"a": 1}) == json.dumps({"a": 1}, ensure_ascii=False)
    assert _coerce_llm_text_response([{"text": "hello"}]) == "hello"
    assert _coerce_llm_text_response("plain") == "plain"


def test_stream_text_chunks_accepts_dict_payload():
    chunks = chat_service._stream_text_chunks({"k": "v"})
    assert isinstance(chunks, list)
    assert chunks
    merged = "".join(chunks).strip()
    assert json.loads(merged) == {"k": "v"}


@pytest.mark.anyio
async def test_generate_text_impl_coerces_dict_provider_content(monkeypatch):
    class _NoopLimiter:
        async def acquire_async(self):
            return None

    async def fake_anthropic(**_kwargs):
        return ({"unexpected": "object"}, None, None)

    monkeypatch.setattr(llm_service, "get_llm_limiter", lambda: _NoopLimiter())
    monkeypatch.setattr(llm_service, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(llm_service, "USE_BEDROCK", False)
    monkeypatch.setattr(llm_service, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(llm_service, "_generate_anthropic", fake_anthropic)

    out = await llm_service._generate_text_impl(
        "sys",
        "user",
        100,
        "test_step",
        None,
        None,
    )
    assert isinstance(out, str)
    assert json.loads(out) == {"unexpected": "object"}
