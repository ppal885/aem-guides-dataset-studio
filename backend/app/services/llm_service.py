"""LLM service for JSON generation and chat streaming via Anthropic, AWS Bedrock, or Groq API."""
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator, Optional, Tuple

from app.core.agentic_config import agentic_config
from app.core.observability import get_observability_logger
from app.utils.rate_limiter import get_llm_limiter
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)
obs_log = get_observability_logger("llm")

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
ANTHROPIC_FALLBACK_MODEL = os.getenv("ANTHROPIC_FALLBACK_MODEL", "").strip() or None
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Bedrock (Claude Code setup at Adobe: Shared Bedrock or Project Turnkey)
# Uses AWS credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) or default chain
BEDROCK_MODEL = os.getenv("BEDROCK_MODEL", "anthropic.claude-3-5-sonnet-20241022-v2:0")
BEDROCK_REGION = os.getenv("AWS_REGION", os.getenv("BEDROCK_REGION", "us-west-2"))
USE_BEDROCK = os.getenv("CLAUDE_CODE_USE_BEDROCK", "").lower() in ("1", "true", "yes")

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower().strip()
LLM_FALLBACK_PROVIDER = os.getenv("LLM_FALLBACK_PROVIDER", "").lower().strip()
# Provider chain: comma-separated ordered list e.g. "openai,anthropic,groq"
# Each provider is tried in order; first with valid credentials wins.
LLM_PROVIDER_CHAIN = os.getenv("LLM_PROVIDER_CHAIN", "").lower().strip()

# Reasoning / quality tuning — configurable via .env
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))           # generation (JSON, text)
LLM_TEMPERATURE_CHAT = float(os.getenv("LLM_TEMPERATURE_CHAT", "0.15"))  # chat streaming
LLM_TOP_P = float(os.getenv("LLM_TOP_P", "0.85"))                     # nucleus sampling
LLM_FREQUENCY_PENALTY = float(os.getenv("LLM_FREQUENCY_PENALTY", "0.1"))  # reduce repetition

# Circuit breaker (env-gated, default off)
CIRCUIT_BREAKER_ENABLED = os.getenv("LLM_CIRCUIT_BREAKER_ENABLED", "").lower() in ("true", "1", "yes")
CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("LLM_CIRCUIT_BREAKER_THRESHOLD", "5"))
CIRCUIT_BREAKER_WINDOW_SEC = float(os.getenv("LLM_CIRCUIT_BREAKER_WINDOW_SEC", "60"))

_llm_failure_count = 0
_llm_last_failure_time: float = 0.0
_circuit_lock = threading.Lock()


def _circuit_breaker_record_failure() -> None:
    """Record an LLM failure. Call on exception."""
    global _llm_failure_count, _llm_last_failure_time
    if not CIRCUIT_BREAKER_ENABLED:
        return
    with _circuit_lock:
        _llm_failure_count += 1
        _llm_last_failure_time = time.monotonic()


def _circuit_breaker_record_success() -> None:
    """Reset circuit on successful LLM call."""
    global _llm_failure_count
    if not CIRCUIT_BREAKER_ENABLED:
        return
    with _circuit_lock:
        _llm_failure_count = 0


def _circuit_breaker_is_open() -> bool:
    """Return True if circuit is open (too many failures in window)."""
    if not CIRCUIT_BREAKER_ENABLED:
        return False
    with _circuit_lock:
        if _llm_failure_count < CIRCUIT_BREAKER_THRESHOLD:
            return False
        elapsed = time.monotonic() - _llm_last_failure_time
        if elapsed > CIRCUIT_BREAKER_WINDOW_SEC:
            _llm_failure_count = 0
            return False
        return True


def _is_bedrock_available() -> bool:
    """Bedrock uses AWS credential chain. For Adobe: Project Turnkey gives AWS keys from CAMP."""
    has_explicit = bool(
        os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY")
    )
    has_bearer = bool(os.getenv("AWS_BEARER_TOKEN_BEDROCK", "").strip())
    has_profile = bool(os.getenv("AWS_PROFILE"))
    # Allow if explicit creds, bearer (Adobe shared), profile, or default chain (~/.aws/credentials)
    if has_explicit or has_bearer or has_profile:
        return True
    # Check for default credentials file
    aws_creds = Path.home() / ".aws" / "credentials"
    return aws_creds.exists()


def _effective_provider() -> str:
    """Resolve provider using chain, explicit setting, or bedrock override.

    Priority:
    1. LLM_PROVIDER_CHAIN (comma-separated, first with credentials wins)
    2. LLM_PROVIDER=bedrock or CLAUDE_CODE_USE_BEDROCK=1
    3. LLM_PROVIDER (single provider)
    """
    # Provider chain: try each in order, pick first with valid credentials
    if LLM_PROVIDER_CHAIN:
        chain = [p.strip() for p in LLM_PROVIDER_CHAIN.split(",") if p.strip()]
        for provider in chain:
            if _provider_has_credentials(provider):
                return provider
        # If no provider in chain has credentials, fall through to single provider
        logger.warning(
            f"No provider in chain [{LLM_PROVIDER_CHAIN}] has valid credentials, "
            f"falling back to LLM_PROVIDER={LLM_PROVIDER}"
        )
    if LLM_PROVIDER == "bedrock" or USE_BEDROCK:
        return "bedrock"
    return LLM_PROVIDER


def get_active_llm_provider() -> str:
    """Public accessor for the resolved LLM provider name."""
    return _effective_provider()


def is_llm_available() -> bool:
    """Return True if the configured LLM provider has credentials; False enables mock mode.
    Set AI_USE_MOCK_LLM=true to force mock mode (no API key needed).
    Use LLM_PROVIDER=anthropic|bedrock|groq|openai. For Bedrock (Claude Code setup): LLM_PROVIDER=bedrock + AWS_REGION."""
    if os.getenv("AI_USE_MOCK_LLM", "").lower() in ("true", "1", "yes"):
        return False
    provider = _effective_provider()
    if provider == "groq":
        return bool(GROQ_API_KEY and GROQ_API_KEY.strip())
    if provider == "openai":
        return bool(OPENAI_API_KEY and OPENAI_API_KEY.strip())
    if provider == "bedrock":
        return _is_bedrock_available()
    return bool(ANTHROPIC_API_KEY and ANTHROPIC_API_KEY.strip())

PROMPTS_VERSIONS_PATH = str(Path(__file__).resolve().parent.parent / "templates" / "prompts" / "versions.json")

_prompt_versions_cache: Optional[dict] = None


def _get_prompt_versions() -> dict:
    global _prompt_versions_cache
    if _prompt_versions_cache is None:
        try:
            with open(PROMPTS_VERSIONS_PATH, encoding="utf-8") as f:
                _prompt_versions_cache = json.load(f)
        except Exception as e:
            logger.warning_structured("Failed to load prompt versions", extra_fields={"path": PROMPTS_VERSIONS_PATH, "error": str(e)})
            _prompt_versions_cache = {}
    return _prompt_versions_cache


def _extract_json(text: str) -> Optional[dict]:
    """Extract JSON object from response text."""
    text = text.strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError as e:
            logger.debug("JSON decode failed in LLM response", extra_fields={"error": str(e), "snippet": match.group()[:200]})
    return None


def _store_llm_run(
    trace_id: Optional[str],
    jira_id: Optional[str],
    step_name: str,
    model: str,
    prompt: str,
    response: Optional[str],
    tokens_input: Optional[int],
    tokens_output: Optional[int],
    latency_ms: Optional[int],
    error_type: Optional[str] = None,
    prompt_version: Optional[str] = None,
    retry_count: Optional[int] = None,
) -> None:
    """Store LLMRun row. Non-fatal on failure."""
    try:
        from app.db.session import SessionLocal
        from app.db.llm_models import LLMRun
        db = SessionLocal()
        try:
            run = LLMRun(
                trace_id=trace_id,
                jira_id=jira_id,
                step_name=step_name,
                prompt_version=prompt_version,
                model=model,
                prompt=prompt[:50000] if prompt else None,
                response=response[:50000] if response else None,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                latency_ms=latency_ms,
                retry_count=retry_count,
                error_type=error_type,
            )
            db.add(run)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning_structured(
            "Failed to store LLMRun",
            extra_fields={"step_name": step_name, "error": str(e)},
        )


def store_chat_llm_run(
    session_id: str,
    tokens_input: int,
    tokens_output: int,
    model: str = "chat",
) -> None:
    """Store chat LLM usage for observability. Non-fatal on failure."""
    _store_llm_run(
        trace_id=session_id,
        jira_id=None,
        step_name="chat_turn",
        model=model,
        prompt=None,
        response=None,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        latency_ms=None,
    )


def _is_retryable_llm_error(e: Exception) -> bool:
    """Return True if error is rate limit (429), too large (413), or server error (503) and fallback may help."""
    err_str = str(e).lower()
    if "429" in err_str or "rate" in err_str or "overloaded" in err_str:
        return True
    if "413" in err_str or "too large" in err_str or "request too large" in err_str:
        return True
    if "503" in err_str or "service" in err_str or "unavailable" in err_str:
        return True
    status = getattr(e, "status_code", None)
    if status in (413, 429, 503):
        return True
    return False


def _flatten_exception_messages(exc: BaseException | None) -> str:
    """Collect nested exception messages into one searchable string."""
    seen: set[int] = set()
    parts: list[str] = []
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current).strip()
        if text:
            parts.append(text)
        current = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
    return " | ".join(parts)


def _is_stream_unpack_bug(e: Exception) -> bool:
    """Detect the Anthropic/Bedrock streaming unpack bug so we can retry non-streaming."""
    lowered = _flatten_exception_messages(e).lower()
    return (
        "not enough values to unpack" in lowered
        and "expected 2" in lowered
        and "got 1" in lowered
    )


def _anthropic_usage_to_dict(usage) -> dict[str, int] | None:
    if not usage:
        return None
    return {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0,
    }


def _anthropic_message_parts(message) -> tuple[list[str], list[dict[str, object]]]:
    texts: list[str] = []
    tool_blocks: list[dict[str, object]] = []
    for block in getattr(message, "content", None) or []:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text = getattr(block, "text", None)
            if text:
                texts.append(str(text))
        elif block_type == "tool_use":
            tool_blocks.append(
                {
                    "id": getattr(block, "id", ""),
                    "name": getattr(block, "name", ""),
                    "input": getattr(block, "input", {}) or {},
                }
            )
    return texts, tool_blocks


def _provider_has_credentials(provider: str) -> bool:
    provider = (provider or "").lower().strip()
    if provider == "groq":
        return bool(GROQ_API_KEY and GROQ_API_KEY.strip())
    if provider == "openai":
        return bool(OPENAI_API_KEY and OPENAI_API_KEY.strip())
    if provider == "bedrock":
        return _is_bedrock_available()
    if provider == "anthropic":
        return bool(ANTHROPIC_API_KEY and ANTHROPIC_API_KEY.strip())
    return False


def _provider_label(provider: str | None) -> str:
    labels = {
        "anthropic": "Anthropic",
        "bedrock": "AWS Bedrock",
        "groq": "Groq",
        "openai": "OpenAI",
    }
    return labels.get((provider or "").lower().strip(), "the AI provider")


def _get_chat_fallback_provider(primary_provider: str) -> str | None:
    # If provider chain is set, fallback is the next provider in chain after primary
    if LLM_PROVIDER_CHAIN:
        chain = [p.strip() for p in LLM_PROVIDER_CHAIN.split(",") if p.strip()]
        found_primary = False
        for provider in chain:
            if provider == primary_provider:
                found_primary = True
                continue
            if found_primary and _provider_has_credentials(provider):
                return provider
    # Legacy single fallback
    candidate = (LLM_FALLBACK_PROVIDER or "").lower().strip()
    if not candidate or candidate == primary_provider:
        return None
    if _provider_has_credentials(candidate):
        return candidate
    return None


def _get_generation_fallback(primary_provider: str) -> tuple[str | None, object | None, str | None]:
    """Resolve explicit fallback for JSON/text generation only when configured."""
    candidate = (LLM_FALLBACK_PROVIDER or "").lower().strip()
    if not candidate or candidate == primary_provider:
        return None, None, None
    if candidate == "groq" and GROQ_API_KEY and GROQ_API_KEY.strip():
        return GROQ_MODEL, _generate_groq, None
    if candidate == "openai" and OPENAI_API_KEY and OPENAI_API_KEY.strip():
        return OPENAI_MODEL, _generate_openai, None
    if candidate == "bedrock" and _is_bedrock_available():
        return BEDROCK_MODEL, _generate_bedrock, None
    if candidate == "anthropic" and ANTHROPIC_API_KEY and ANTHROPIC_API_KEY.strip():
        model = ANTHROPIC_FALLBACK_MODEL or ANTHROPIC_MODEL
        return model, _generate_anthropic, model
    return None, None, None


def format_llm_error_for_user(
    e: Exception,
    *,
    primary_provider: str | None = None,
    fallback_provider: str | None = None,
    fallback_attempted: bool = False,
) -> str:
    """Return a user-safe explanation for common provider failures."""
    err_str = str(e or "").strip()
    lowered = err_str.lower()
    primary_label = _provider_label(primary_provider)
    fallback_label = _provider_label(fallback_provider) if fallback_provider else None

    if "quota is exhausted" in lowered or lowered.startswith("the assistant is temporarily") or "is rate-limited" in lowered:
        return err_str

    if "insufficient_quota" in lowered or ("quota" in lowered and "429" in lowered):
        if fallback_attempted and fallback_label:
            return (
                "The assistant is temporarily unavailable because the configured AI providers are out of quota. "
                "Please try again later or update the provider billing/settings."
            )
        return "The assistant is temporarily unavailable because the configured AI provider quota is exhausted."

    if "429" in lowered or "rate limit" in lowered or "overloaded" in lowered:
        if fallback_attempted and fallback_label:
            return "The assistant is temporarily busy because the configured AI providers are rate-limited. Please try again in a moment."
        return "The assistant is temporarily busy because the configured AI provider is rate-limited. Please try again in a moment."

    if "api key" in lowered or "not set" in lowered or "authentication" in lowered:
        return "The chat provider is not configured correctly in backend/.env."

    if "circuit open" in lowered:
        return "The assistant is temporarily paused after repeated provider failures. Please wait a moment and retry."

    return "The assistant is temporarily unavailable. Please try again in a moment."


def _is_langsmith_tracing_enabled() -> bool:
    """Return True when LangSmith tracing should be used."""
    return (
        os.getenv("LANGSMITH_TRACING", "").lower() in ("true", "1", "yes")
        and bool(os.getenv("LANGSMITH_API_KEY", "").strip())
    )


def _wrap_for_tracing(client):
    """Wrap Anthropic/Bedrock client for LangSmith tracing when enabled."""
    if not _is_langsmith_tracing_enabled():
        return client
    try:
        from langsmith.wrappers import wrap_anthropic
        return wrap_anthropic(client)
    except ImportError:
        return client


def _get_bedrock_client():
    """Create AsyncAnthropicBedrock client. Uses AWS creds or default chain."""
    from anthropic import AsyncAnthropicBedrock
    kwargs = {"aws_region": BEDROCK_REGION, "timeout": 120.0}
    if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
        kwargs["aws_access_key"] = os.getenv("AWS_ACCESS_KEY_ID")
        kwargs["aws_secret_key"] = os.getenv("AWS_SECRET_ACCESS_KEY")
    if os.getenv("AWS_SESSION_TOKEN"):
        kwargs["aws_session_token"] = os.getenv("AWS_SESSION_TOKEN")
    client = AsyncAnthropicBedrock(**kwargs)
    return _wrap_for_tracing(client)


async def _generate_bedrock(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    timeout_sec: float,
    model: Optional[str] = None,
) -> Tuple[str, Optional[int], Optional[int]]:
    """Call Claude via AWS Bedrock with streaming. Collects full response. Returns (content, input_tokens, output_tokens)."""
    client = _get_bedrock_client()
    model_to_use = model or BEDROCK_MODEL
    chunks: list[str] = []
    input_tok = output_tok = None
    async with client.messages.stream(
        model=model_to_use,
        max_tokens=max_tokens,
        temperature=LLM_TEMPERATURE,
        top_p=LLM_TOP_P,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        timeout=timeout_sec,
    ) as stream:
        async for text in stream.text_stream:
            if text:
                chunks.append(text)
        msg = await stream.get_final_message()
        usage = getattr(msg, "usage", None)
        if usage:
            input_tok = getattr(usage, "input_tokens", None)
            output_tok = getattr(usage, "output_tokens", None)
    return "".join(chunks), input_tok, output_tok


async def _generate_anthropic(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    timeout_sec: float,
    model: Optional[str] = None,
) -> Tuple[str, Optional[int], Optional[int]]:
    """Call Anthropic API with streaming. Collects full response. Returns (content, input_tokens, output_tokens)."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package is required. Install with: pip install anthropic")

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY, timeout=timeout_sec)
    client = _wrap_for_tracing(client)
    model_to_use = model or ANTHROPIC_MODEL
    chunks: list[str] = []
    input_tok = output_tok = None
    async with client.messages.stream(
        model=model_to_use,
        max_tokens=max_tokens,
        temperature=LLM_TEMPERATURE,
        top_p=LLM_TOP_P,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        timeout=timeout_sec,
    ) as stream:
        async for text in stream.text_stream:
            if text:
                chunks.append(text)
        msg = await stream.get_final_message()
        usage = getattr(msg, "usage", None)
        if usage:
            input_tok = getattr(usage, "input_tokens", None)
            output_tok = getattr(usage, "output_tokens", None)

    return "".join(chunks), input_tok, output_tok


async def _generate_groq(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    timeout_sec: float,
) -> Tuple[str, Optional[int], Optional[int]]:
    """Call Groq API (OpenAI-compatible) with streaming. Collects full response. Returns (content, input_tokens, output_tokens)."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        raise ImportError("openai package is required for Groq. Install with: pip install openai")

    client = AsyncOpenAI(
        base_url=GROQ_BASE_URL,
        api_key=GROQ_API_KEY,
        timeout=timeout_sec,
    )
    if _is_langsmith_tracing_enabled():
        try:
            from langsmith.wrappers import wrap_openai
            client = wrap_openai(client)
        except ImportError:
            pass

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    chunks: list[str] = []
    input_tok = output_tok = None
    stream = await client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=LLM_TEMPERATURE,
        top_p=LLM_TOP_P,
        frequency_penalty=LLM_FREQUENCY_PENALTY,
        stream=True,
        stream_options={"include_usage": True},
    )
    async for chunk in stream:
        if hasattr(chunk, "usage") and chunk.usage:
            input_tok = getattr(chunk.usage, "prompt_tokens", None)
            output_tok = getattr(chunk.usage, "completion_tokens", None)
        if chunk.choices and len(chunk.choices) > 0:
            delta = chunk.choices[0].delta
            if delta and hasattr(delta, "content") and delta.content:
                chunks.append(delta.content)

    return "".join(chunks), input_tok, output_tok


async def _generate_openai(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    timeout_sec: float,
) -> Tuple[str, Optional[int], Optional[int]]:
    """Call OpenAI API with streaming. Collects full response. Returns (content, input_tokens, output_tokens)."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        raise ImportError("openai package is required for OpenAI. Install with: pip install openai")

    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        timeout=timeout_sec,
    )
    if _is_langsmith_tracing_enabled():
        try:
            from langsmith.wrappers import wrap_openai
            client = wrap_openai(client)
        except ImportError:
            pass

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    chunks: list[str] = []
    input_tok = output_tok = None
    stream = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=LLM_TEMPERATURE,
        top_p=LLM_TOP_P,
        frequency_penalty=LLM_FREQUENCY_PENALTY,
        stream=True,
        stream_options={"include_usage": True},
    )
    async for chunk in stream:
        if hasattr(chunk, "usage") and chunk.usage:
            input_tok = getattr(chunk.usage, "prompt_tokens", None)
            output_tok = getattr(chunk.usage, "completion_tokens", None)
        if chunk.choices and len(chunk.choices) > 0:
            delta = chunk.choices[0].delta
            if delta and hasattr(delta, "content") and delta.content:
                chunks.append(delta.content)

    return "".join(chunks), input_tok, output_tok


async def generate_chat_stream(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = 4096,
    timeout_sec: float | None = None,
) -> AsyncGenerator[str, None]:
    """
    Stream chat completion. Yields text chunks as they arrive.
    messages: list of {"role": "user"|"assistant", "content": str}
    """
    if not is_llm_available():
        raise RuntimeError(
            "LLM unavailable: set ANTHROPIC_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, or LLM_PROVIDER=bedrock with AWS credentials. "
            "For Bedrock (Claude Code setup): LLM_PROVIDER=bedrock, AWS_REGION=us-west-2."
        )
    if _circuit_breaker_is_open():
        raise RuntimeError(
            "LLM temporarily unavailable (circuit open). Set LLM_CIRCUIT_BREAKER_ENABLED=false to disable, or wait and retry."
        )
    timeout_sec = timeout_sec or agentic_config.llm_timeout_seconds
    await get_llm_limiter().acquire_async()

    provider = _effective_provider()
    fallback_provider = _get_chat_fallback_provider(provider)

    async def _stream_from(active_provider: str) -> AsyncGenerator[str, None]:
        if active_provider == "groq":
            async for chunk in _generate_chat_stream_groq(system_prompt, messages, max_tokens, timeout_sec):
                yield chunk
            return
        if active_provider == "openai":
            async for chunk in _generate_chat_stream_openai(system_prompt, messages, max_tokens, timeout_sec):
                yield chunk
            return
        if active_provider == "bedrock":
            async for chunk in _generate_chat_stream_bedrock(system_prompt, messages, max_tokens, timeout_sec):
                yield chunk
            return
        async for chunk in _generate_chat_stream_anthropic(system_prompt, messages, max_tokens, timeout_sec):
            yield chunk

    yielded_any = False
    try:
        async for chunk in _stream_from(provider):
            yielded_any = True
            yield chunk
        _circuit_breaker_record_success()
    except Exception as e:
        if not yielded_any and fallback_provider and _is_retryable_llm_error(e):
            logger.warning_structured(
                "Primary chat stream provider failed; retrying fallback",
                extra_fields={
                    "primary_provider": provider,
                    "fallback_provider": fallback_provider,
                    "error": str(e),
                },
            )
            try:
                async for chunk in _stream_from(fallback_provider):
                    yield chunk
                _circuit_breaker_record_success()
                return
            except Exception as fallback_exc:
                _circuit_breaker_record_failure()
                raise RuntimeError(
                    format_llm_error_for_user(
                        fallback_exc,
                        primary_provider=provider,
                        fallback_provider=fallback_provider,
                        fallback_attempted=True,
                    )
                ) from fallback_exc
        _circuit_breaker_record_failure()
        raise RuntimeError(
            format_llm_error_for_user(
                e,
                primary_provider=provider,
                fallback_provider=fallback_provider,
                fallback_attempted=False,
            )
        ) from e


async def generate_chat_stream_with_tools(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int = 4096,
    timeout_sec: float | None = None,
) -> AsyncGenerator[Tuple[str, object], None]:
    """
    Stream chat with tool support. Yields ("chunk", text) for text, then ("tool_use_blocks", [blocks])
    if model requested tools, or ("done",) when finished.
    Only supports Anthropic and Bedrock; Groq falls back to no tools.
    """
    if not is_llm_available():
        raise RuntimeError(
            "LLM unavailable: set ANTHROPIC_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, or LLM_PROVIDER=bedrock with AWS credentials."
        )
    if _circuit_breaker_is_open():
        raise RuntimeError(
            "LLM temporarily unavailable (circuit open). Set LLM_CIRCUIT_BREAKER_ENABLED=false to disable, or wait and retry."
        )
    timeout_sec = timeout_sec or agentic_config.llm_timeout_seconds
    await get_llm_limiter().acquire_async()

    provider = _effective_provider()
    fallback_provider = _get_chat_fallback_provider(provider)

    async def _stream_from(active_provider: str) -> AsyncGenerator[Tuple[str, object], None]:
        if active_provider == "groq":
            async for evt in _stream_with_tools_groq(system_prompt, messages, tools, max_tokens, timeout_sec):
                yield evt
            return

        if active_provider == "openai":
            async for evt in _stream_with_tools_openai(system_prompt, messages, tools, max_tokens, timeout_sec):
                yield evt
            return

        if active_provider == "bedrock":
            async for evt in _stream_with_tools_bedrock(system_prompt, messages, tools, max_tokens, timeout_sec):
                yield evt
            return

        async for evt in _stream_with_tools_anthropic(system_prompt, messages, tools, max_tokens, timeout_sec):
            yield evt

    emitted_any = False
    try:
        async for evt in _stream_from(provider):
            emitted_any = True
            yield evt
        _circuit_breaker_record_success()
    except Exception as e:
        if not emitted_any and fallback_provider and _is_retryable_llm_error(e):
            logger.warning_structured(
                "Primary chat-with-tools provider failed; retrying fallback",
                extra_fields={
                    "primary_provider": provider,
                    "fallback_provider": fallback_provider,
                    "error": str(e),
                },
            )
            try:
                async for evt in _stream_from(fallback_provider):
                    yield evt
                _circuit_breaker_record_success()
                return
            except Exception as fallback_exc:
                _circuit_breaker_record_failure()
                raise RuntimeError(
                    format_llm_error_for_user(
                        fallback_exc,
                        primary_provider=provider,
                        fallback_provider=fallback_provider,
                        fallback_attempted=True,
                    )
                ) from fallback_exc
        _circuit_breaker_record_failure()
        raise RuntimeError(
            format_llm_error_for_user(
                e,
                primary_provider=provider,
                fallback_provider=fallback_provider,
                fallback_attempted=False,
            )
        ) from e


async def _stream_with_tools_anthropic(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int,
    timeout_sec: float,
) -> AsyncGenerator[Tuple[str, object], None]:
    """Stream with tools via Anthropic API. Yields (chunk, text) or (tool_use_blocks, blocks) or (done,)."""
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY, timeout=timeout_sec)
    request_kwargs = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "temperature": LLM_TEMPERATURE_CHAT,
        "top_p": LLM_TOP_P,
        "system": system_prompt,
        "messages": messages,
        "tools": tools,
        "tool_choice": {"type": "auto"},
        "timeout": timeout_sec,
    }
    emitted_any = False
    try:
        async with client.messages.stream(**request_kwargs) as stream:
            async for text in stream.text_stream:
                if text:
                    emitted_any = True
                    yield ("chunk", text)
            msg = await stream.get_final_message()
    except Exception as exc:
        if emitted_any or not _is_stream_unpack_bug(exc):
            raise
        logger.warning_structured(
            "Anthropic stream hit unpack bug; retrying non-streaming request",
            extra_fields={"error": _flatten_exception_messages(exc)},
        )
        msg = await client.messages.create(**request_kwargs)

    usage = _anthropic_usage_to_dict(getattr(msg, "usage", None))
    text_parts, tool_blocks = _anthropic_message_parts(msg)
    for text in text_parts:
        if text:
            yield ("chunk", text)
    if getattr(msg, "stop_reason", None) == "tool_use" and tool_blocks:
        if usage:
            yield ("usage", usage)
        yield ("tool_use_blocks", tool_blocks)
        return
    if usage:
        yield ("usage", usage)
    yield ("done", None)


async def _stream_with_tools_bedrock(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int,
    timeout_sec: float,
) -> AsyncGenerator[Tuple[str, object], None]:
    """Stream with tools via Bedrock. Same yield format as Anthropic."""
    client = _get_bedrock_client()
    request_kwargs = {
        "model": BEDROCK_MODEL,
        "max_tokens": max_tokens,
        "temperature": LLM_TEMPERATURE_CHAT,
        "top_p": LLM_TOP_P,
        "system": system_prompt,
        "messages": messages,
        "tools": tools,
        "tool_choice": {"type": "auto"},
        "timeout": timeout_sec,
    }
    emitted_any = False
    try:
        async with client.messages.stream(**request_kwargs) as stream:
            async for text in stream.text_stream:
                if text:
                    emitted_any = True
                    yield ("chunk", text)
            msg = await stream.get_final_message()
    except Exception as exc:
        if emitted_any or not _is_stream_unpack_bug(exc):
            raise
        logger.warning_structured(
            "Bedrock stream hit unpack bug; retrying non-streaming request",
            extra_fields={"error": _flatten_exception_messages(exc)},
        )
        msg = await client.messages.create(**request_kwargs)

    usage = _anthropic_usage_to_dict(getattr(msg, "usage", None))
    text_parts, tool_blocks = _anthropic_message_parts(msg)
    for text in text_parts:
        if text:
            yield ("chunk", text)
    if getattr(msg, "stop_reason", None) == "tool_use" and tool_blocks:
        if usage:
            yield ("usage", usage)
        yield ("tool_use_blocks", tool_blocks)
        return
    if usage:
        yield ("usage", usage)
    yield ("done", None)


async def _generate_chat_stream_anthropic(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int,
    timeout_sec: float,
) -> AsyncGenerator[str, None]:
    """Stream via Anthropic API."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package is required. Install with: pip install anthropic")

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY, timeout=timeout_sec)
    model_to_use = ANTHROPIC_MODEL
    request_kwargs = {
        "model": model_to_use,
        "max_tokens": max_tokens,
        "temperature": LLM_TEMPERATURE_CHAT,
        "top_p": LLM_TOP_P,
        "system": system_prompt,
        "messages": messages,
        "timeout": timeout_sec,
    }
    emitted_any = False
    try:
        async with client.messages.stream(**request_kwargs) as stream:
            async for text in stream.text_stream:
                if text:
                    emitted_any = True
                    yield text
            return
    except Exception as exc:
        if emitted_any or not _is_stream_unpack_bug(exc):
            raise
        logger.warning_structured(
            "Anthropic chat stream hit unpack bug; retrying non-streaming request",
            extra_fields={"error": _flatten_exception_messages(exc)},
        )
    msg = await client.messages.create(**request_kwargs)
    text_parts, _tool_blocks = _anthropic_message_parts(msg)
    for text in text_parts:
        if text:
            yield text


async def _generate_chat_stream_bedrock(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int,
    timeout_sec: float,
) -> AsyncGenerator[str, None]:
    """Stream via AWS Bedrock (Claude Code setup at Adobe)."""
    client = _get_bedrock_client()
    model_to_use = BEDROCK_MODEL
    request_kwargs = {
        "model": model_to_use,
        "max_tokens": max_tokens,
        "temperature": LLM_TEMPERATURE_CHAT,
        "top_p": LLM_TOP_P,
        "system": system_prompt,
        "messages": messages,
        "timeout": timeout_sec,
    }
    emitted_any = False
    try:
        async with client.messages.stream(**request_kwargs) as stream:
            async for text in stream.text_stream:
                if text:
                    emitted_any = True
                    yield text
            return
    except Exception as exc:
        if emitted_any or not _is_stream_unpack_bug(exc):
            raise
        logger.warning_structured(
            "Bedrock chat stream hit unpack bug; retrying non-streaming request",
            extra_fields={"error": _flatten_exception_messages(exc)},
        )
    msg = await client.messages.create(**request_kwargs)
    text_parts, _tool_blocks = _anthropic_message_parts(msg)
    for text in text_parts:
        if text:
            yield text


def _anthropic_tools_to_openai(tools: list[dict]) -> list[dict]:
    """Convert Anthropic-style tool definitions to OpenAI/Groq function calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {}),
            },
        }
        for t in tools
    ]


def _flatten_anthropic_content(content) -> str:
    """Flatten Anthropic-style content blocks (list of dicts) to a plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text") or block.get("content") or str(block))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content) if content else ""


def _coerce_llm_text_response(value: object) -> str:
    """Normalize provider completion payloads to a string (avoids .strip() on dict/list)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)
    if isinstance(value, list):
        return _flatten_anthropic_content(value)
    return str(value)


def _build_openai_messages(system_prompt: str, messages: list[dict]) -> list[dict]:
    """Convert Anthropic-style messages to OpenAI format, including tool call/result messages.

    Handles:
    - Regular user/assistant text messages
    - Assistant messages with tool_use blocks → OpenAI tool_calls format
    - User messages with tool_result blocks → OpenAI role=tool messages
    """
    openai_messages = [{"role": "system", "content": system_prompt}]
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")

        # Handle assistant messages with Anthropic tool_use blocks
        if role == "assistant" and isinstance(content, list):
            text_parts = []
            tool_calls = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_use":
                        tool_calls.append({
                            "id": block.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": json.dumps(block.get("input", {})),
                            },
                        })
                    else:
                        text_parts.append(block.get("text") or block.get("content") or "")
                else:
                    text_parts.append(str(block))
            msg: dict = {"role": "assistant", "content": "\n".join(text_parts) or None}
            if tool_calls:
                msg["tool_calls"] = tool_calls
            openai_messages.append(msg)
            continue

        # Handle user messages with Anthropic tool_result blocks
        if role == "user" and isinstance(content, list):
            has_tool_results = any(
                isinstance(block, dict) and block.get("type") == "tool_result"
                for block in content
            )
            if has_tool_results:
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        openai_messages.append({
                            "role": "tool",
                            "tool_call_id": block.get("tool_use_id", ""),
                            "content": block.get("content", ""),
                        })
                continue
            # Regular user message with content blocks
            content = _flatten_anthropic_content(content)

        content = _flatten_anthropic_content(content)
        if role in ("user", "assistant") and content:
            openai_messages.append({"role": role, "content": content})
    return openai_messages


async def _stream_with_tools_groq(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int,
    timeout_sec: float,
) -> AsyncGenerator[Tuple[str, object], None]:
    """Stream with tool support via Groq API (OpenAI-compatible). Same yield format as Anthropic."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        raise ImportError("openai package is required for Groq. Install with: pip install openai")

    client = AsyncOpenAI(
        base_url=GROQ_BASE_URL,
        api_key=GROQ_API_KEY,
        timeout=timeout_sec,
    )

    openai_messages = _build_openai_messages(system_prompt, messages)
    openai_tools = _anthropic_tools_to_openai(tools) if tools else None

    kwargs = {
        "model": GROQ_MODEL,
        "messages": openai_messages,
        "max_tokens": max_tokens,
        "temperature": LLM_TEMPERATURE_CHAT,
        "top_p": LLM_TOP_P,
        "frequency_penalty": LLM_FREQUENCY_PENALTY,
        "stream": True,
    }
    if openai_tools:
        kwargs["tools"] = openai_tools
        kwargs["tool_choice"] = "auto"

    stream = await client.chat.completions.create(**kwargs)

    # Accumulate tool calls across streamed chunks
    tool_calls_acc: dict[int, dict] = {}  # index -> {id, name, arguments}
    input_tok = output_tok = None
    # Accumulate text to detect inline <function> XML that Groq/Llama sometimes emits
    _text_acc_parts: list[str] = []
    _text_chunks_yielded: list[str] = []

    async for chunk in stream:
        if hasattr(chunk, "usage") and chunk.usage:
            input_tok = getattr(chunk.usage, "prompt_tokens", None)
            output_tok = getattr(chunk.usage, "completion_tokens", None)

        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        delta = choice.delta

        # Stream text content (but buffer to detect inline function XML)
        if delta and hasattr(delta, "content") and delta.content:
            _text_acc_parts.append(delta.content)
            # Only yield text chunks that are clearly not inline function XML.
            # We buffer and check periodically. If we see <function start, hold back.
            full_so_far = "".join(_text_acc_parts)
            if "<function" not in full_so_far and "</function>" not in full_so_far:
                # Safe to yield buffered text
                to_yield = "".join(_text_acc_parts)
                _text_acc_parts.clear()
                _text_chunks_yielded.append(to_yield)
                yield ("chunk", to_yield)

        # Accumulate tool calls
        if delta and hasattr(delta, "tool_calls") and delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls_acc:
                    tool_calls_acc[idx] = {
                        "id": getattr(tc, "id", None) or f"call_{idx}",
                        "name": "",
                        "arguments": "",
                    }
                if tc.function:
                    if tc.function.name:
                        tool_calls_acc[idx]["name"] = tc.function.name
                    if tc.function.arguments:
                        tool_calls_acc[idx]["arguments"] += tc.function.arguments

        # Check for finish reason
        if choice.finish_reason == "tool_calls":
            break

    # Emit usage if available
    if input_tok is not None or output_tok is not None:
        yield ("usage", {
            "input_tokens": input_tok or 0,
            "output_tokens": output_tok or 0,
        })

    # Emit tool_use_blocks if any tool calls were accumulated via API
    if tool_calls_acc:
        from app.services.tool_arg_parser import parse_tool_arguments
        blocks = []
        for idx in sorted(tool_calls_acc.keys()):
            tc = tool_calls_acc[idx]
            args, parse_err = parse_tool_arguments(
                tc["arguments"] or "",
                tool_name=tc["name"],
                attempt_repair=True,
            )
            block: dict = {
                "id": tc["id"],
                "name": tc["name"],
                "input": args,
            }
            if parse_err:
                block["_parse_error"] = parse_err
            blocks.append(block)
        if blocks:
            # Flush any remaining buffered text that was clean
            remaining = "".join(_text_acc_parts)
            clean_part = re.sub(r'<function\s+[^>]*?/>', '', remaining).strip()
            if clean_part:
                yield ("chunk", clean_part)
            yield ("tool_use_blocks", blocks)
            return

    # ── Groq/Llama inline <function> XML recovery ──
    # Sometimes Groq outputs tool calls as raw XML text instead of API tool_calls.
    # Detect and convert: <function name="tool_name" parameters="{...}" />
    remaining_text = "".join(_text_acc_parts)
    if remaining_text:
        inline_blocks = _parse_inline_function_xml(remaining_text)
        if inline_blocks:
            # Don't yield the raw XML to the user; yield a friendly note instead
            clean_text = re.sub(
                r'<function\s+name=["\'][^"\']*["\']\s+parameters=["\'].*?["\']\s*/?>',
                '', remaining_text, flags=re.DOTALL,
            ).strip()
            if clean_text:
                yield ("chunk", clean_text)
            yield ("chunk", "\n⏳ Executing tool...\n")
            yield ("tool_use_blocks", inline_blocks)
            return
        else:
            # No inline function XML — just yield the buffered text
            yield ("chunk", remaining_text)

    yield ("done", None)


def _parse_inline_function_xml(text: str) -> list[dict] | None:
    """Parse inline <function name="..." parameters="..."/> XML emitted by Groq/Llama.

    Returns list of tool_use blocks or None if no match found.
    """
    import html
    from app.services.tool_arg_parser import parse_tool_arguments

    # Match patterns like: <function name="generate_dita" parameters="{&quot;text&quot;: ...}" />
    pattern = re.compile(
        r'<function\s+name=["\']([^"\']+)["\']\s+parameters=["\'](.+?)["\']\s*/?>',
        re.DOTALL,
    )
    matches = pattern.findall(text)
    if not matches:
        return None

    blocks = []
    for i, (name, raw_params) in enumerate(matches):
        # Unescape HTML entities (Groq often encodes quotes as &quot;)
        params_str = html.unescape(raw_params)
        args, parse_err = parse_tool_arguments(
            params_str,
            tool_name=name,
            attempt_repair=True,
        )
        block: dict = {
            "id": f"inline_call_{i}",
            "name": name,
            "input": args,
        }
        if parse_err:
            block["_parse_error"] = parse_err
        blocks.append(block)

    return blocks if blocks else None


async def _stream_with_tools_openai(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int,
    timeout_sec: float,
) -> AsyncGenerator[Tuple[str, object], None]:
    """Stream with tool support via OpenAI API. Same yield format as Anthropic."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        raise ImportError("openai package is required for OpenAI. Install with: pip install openai")

    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        timeout=timeout_sec,
    )
    if _is_langsmith_tracing_enabled():
        try:
            from langsmith.wrappers import wrap_openai
            client = wrap_openai(client)
        except ImportError:
            pass

    openai_messages = _build_openai_messages(system_prompt, messages)
    openai_tools = _anthropic_tools_to_openai(tools) if tools else None

    kwargs = {
        "model": OPENAI_MODEL,
        "messages": openai_messages,
        "max_tokens": max_tokens,
        "temperature": LLM_TEMPERATURE_CHAT,
        "top_p": LLM_TOP_P,
        "frequency_penalty": LLM_FREQUENCY_PENALTY,
        "stream": True,
    }
    if openai_tools:
        kwargs["tools"] = openai_tools
        kwargs["tool_choice"] = "auto"

    stream = await client.chat.completions.create(**kwargs)

    tool_calls_acc: dict[int, dict] = {}
    input_tok = output_tok = None

    async for chunk in stream:
        if hasattr(chunk, "usage") and chunk.usage:
            input_tok = getattr(chunk.usage, "prompt_tokens", None)
            output_tok = getattr(chunk.usage, "completion_tokens", None)

        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        delta = choice.delta

        if delta and hasattr(delta, "content") and delta.content:
            yield ("chunk", delta.content)

        if delta and hasattr(delta, "tool_calls") and delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls_acc:
                    tool_calls_acc[idx] = {
                        "id": getattr(tc, "id", None) or f"call_{idx}",
                        "name": "",
                        "arguments": "",
                    }
                if tc.function:
                    if tc.function.name:
                        tool_calls_acc[idx]["name"] = tc.function.name
                    if tc.function.arguments:
                        tool_calls_acc[idx]["arguments"] += tc.function.arguments

        if choice.finish_reason == "tool_calls":
            break

    if input_tok is not None or output_tok is not None:
        yield ("usage", {
            "input_tokens": input_tok or 0,
            "output_tokens": output_tok or 0,
        })

    if tool_calls_acc:
        from app.services.tool_arg_parser import parse_tool_arguments
        blocks = []
        for idx in sorted(tool_calls_acc.keys()):
            tc = tool_calls_acc[idx]
            args, parse_err = parse_tool_arguments(
                tc["arguments"] or "",
                tool_name=tc["name"],
                attempt_repair=True,
            )
            block: dict = {
                "id": tc["id"],
                "name": tc["name"],
                "input": args,
            }
            if parse_err:
                block["_parse_error"] = parse_err
            blocks.append(block)
        if blocks:
            yield ("tool_use_blocks", blocks)
            return

    yield ("done", None)


async def _generate_chat_stream_groq(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int,
    timeout_sec: float,
) -> AsyncGenerator[str, None]:
    """Stream via Groq API (OpenAI-compatible) without tools."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        raise ImportError("openai package is required for Groq. Install with: pip install openai")

    client = AsyncOpenAI(
        base_url=GROQ_BASE_URL,
        api_key=GROQ_API_KEY,
        timeout=timeout_sec,
    )

    openai_messages = _build_openai_messages(system_prompt, messages)

    stream = await client.chat.completions.create(
        model=GROQ_MODEL,
        messages=openai_messages,
        max_tokens=max_tokens,
        temperature=LLM_TEMPERATURE_CHAT,
        top_p=LLM_TOP_P,
        frequency_penalty=LLM_FREQUENCY_PENALTY,
        stream=True,
    )

    async for chunk in stream:
        if chunk.choices and len(chunk.choices) > 0:
            delta = chunk.choices[0].delta
            if delta and hasattr(delta, "content") and delta.content:
                yield delta.content


async def _generate_chat_stream_openai(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int,
    timeout_sec: float,
) -> AsyncGenerator[str, None]:
    """Stream via OpenAI API without tools."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        raise ImportError("openai package is required for OpenAI. Install with: pip install openai")

    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        timeout=timeout_sec,
    )
    if _is_langsmith_tracing_enabled():
        try:
            from langsmith.wrappers import wrap_openai
            client = wrap_openai(client)
        except ImportError:
            pass

    openai_messages = _build_openai_messages(system_prompt, messages)

    stream = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=openai_messages,
        max_tokens=max_tokens,
        temperature=LLM_TEMPERATURE_CHAT,
        top_p=LLM_TOP_P,
        frequency_penalty=LLM_FREQUENCY_PENALTY,
        stream=True,
    )

    async for chunk in stream:
        if chunk.choices and len(chunk.choices) > 0:
            delta = chunk.choices[0].delta
            if delta and hasattr(delta, "content") and delta.content:
                yield delta.content


async def _generate_json_impl(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    step_name: str,
    trace_id: Optional[str],
    jira_id: Optional[str],
) -> dict:
    """Internal implementation of generate_json."""
    trace_id = trace_id or str(uuid.uuid4())
    provider = _effective_provider()

    def _get_primary():
        if provider == "groq":
            if not GROQ_API_KEY or not GROQ_API_KEY.strip():
                raise ValueError("GROQ_API_KEY is not set (LLM_PROVIDER=groq)")
            return GROQ_MODEL, _generate_groq, None
        if provider == "openai":
            if not OPENAI_API_KEY or not OPENAI_API_KEY.strip():
                raise ValueError("OPENAI_API_KEY is not set (LLM_PROVIDER=openai)")
            return OPENAI_MODEL, _generate_openai, None
        if provider == "bedrock":
            if not _is_bedrock_available():
                raise ValueError("Bedrock: set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION (or AWS_PROFILE)")
            return BEDROCK_MODEL, _generate_bedrock, None
        if not ANTHROPIC_API_KEY or not ANTHROPIC_API_KEY.strip():
            raise ValueError("ANTHROPIC_API_KEY is not set")
        return ANTHROPIC_MODEL, _generate_anthropic, None

    def _get_fallback():
        return _get_generation_fallback(provider)

    model_name, generate_fn, model_override = _get_primary()
    fallback_model, fallback_fn, fallback_override = _get_fallback()

    timeout_sec = agentic_config.llm_timeout_seconds
    last_error = None
    trace_id = trace_id or str(uuid.uuid4())
    full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"
    prompt_version = _get_prompt_versions().get(step_name)
    used_fallback = False

    async def _try_generate(fn, mname: str, model_param: Optional[str] = None):
        await get_llm_limiter().acquire_async()
        if model_param and fn in (_generate_anthropic, _generate_bedrock):
            return await fn(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                timeout_sec=timeout_sec,
                model=model_param,
            )
        return await fn(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            timeout_sec=timeout_sec,
        )

    for attempt in range(3):
        start_time = time.perf_counter()
        input_tok = output_tok = None
        try:
            content, input_tok, output_tok = await _try_generate(
                generate_fn, model_name, model_override
            )
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            result = _extract_json(content)
            if result is not None:
                _store_llm_run(
                    trace_id=trace_id,
                    jira_id=jira_id,
                    step_name=step_name,
                    model=model_name,
                    prompt=full_prompt,
                    response=content,
                    tokens_input=input_tok,
                    tokens_output=output_tok,
                    latency_ms=elapsed_ms,
                    prompt_version=prompt_version,
                    retry_count=attempt,
                )
                logger.info_structured(
                    "LLM run completed",
                    extra_fields={
                        "trace_id": trace_id,
                        "step_name": step_name,
                        "tokens_input": input_tok,
                        "tokens_output": output_tok,
                        "latency_ms": elapsed_ms,
                        "used_fallback": used_fallback,
                    },
                )
                if _is_langsmith_tracing_enabled():
                    try:
                        from langsmith.run_helpers import set_run_metadata
                        set_run_metadata(
                            prompt_tokens=input_tok,
                            completion_tokens=output_tok,
                            latency_ms=elapsed_ms,
                            retry_count=attempt,
                            step_name=step_name,
                        )
                    except Exception:
                        pass
                return result

            last_error = ValueError("No valid JSON in response")
            _store_llm_run(
                trace_id=trace_id,
                jira_id=jira_id,
                step_name=step_name,
                model=model_name,
                prompt=full_prompt,
                response=content,
                tokens_input=input_tok,
                tokens_output=output_tok,
                latency_ms=elapsed_ms,
                error_type=type(last_error).__name__,
                prompt_version=prompt_version,
                retry_count=attempt,
            )
            logger.warning_structured(
                "LLM run invalid JSON",
                extra_fields={
                    "trace_id": trace_id,
                    "step_name": step_name,
                    "latency_ms": elapsed_ms,
                    "error_type": type(last_error).__name__,
                },
            )
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            last_error = e
            _store_llm_run(
                trace_id=trace_id,
                jira_id=jira_id,
                step_name=step_name,
                model=model_name,
                prompt=full_prompt,
                response=None,
                tokens_input=None,
                tokens_output=None,
                latency_ms=elapsed_ms,
                error_type=type(e).__name__,
                prompt_version=prompt_version,
                retry_count=attempt,
            )
            logger.error_structured(
                "LLM run failed",
                extra_fields={
                    "trace_id": trace_id,
                    "step_name": step_name,
                    "latency_ms": elapsed_ms,
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                exc_info=True,
            )
            if (
                not used_fallback
                and _is_retryable_llm_error(e)
                and fallback_fn is not None
                and fallback_model
            ):
                logger.info_structured(
                    "LLM fallback: retrying with fallback model",
                    extra_fields={
                        "trace_id": trace_id,
                        "step_name": step_name,
                        "fallback_model": fallback_model,
                    },
                )
                used_fallback = True
                model_name = fallback_model
                generate_fn = fallback_fn
                model_override = fallback_override
                last_error = None
                continue

        if attempt < 2:
            time.sleep(0.5 * (attempt + 1))

    raise last_error or ValueError("Failed to get valid JSON from LLM")


async def generate_json(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1200,
    step_name: str = "llm_generate",
    trace_id: Optional[str] = None,
    jira_id: Optional[str] = None,
) -> dict:
    """
    Call configured LLM provider (Anthropic, Bedrock, or Groq) and return parsed JSON.
    Retries up to 2 times on invalid JSON. On 429/503, falls back to fallback model/provider.
    When LANGSMITH_TRACING=true, traces each call with tokens, latency, retry_count.
    """
    impl = _generate_json_impl
    if _is_langsmith_tracing_enabled():
        try:
            from langsmith.run_helpers import traceable
            impl = traceable(run_type="llm", name="LLM generate_json")(_generate_json_impl)
        except ImportError:
            pass
    return await impl(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
        step_name=step_name,
        trace_id=trace_id,
        jira_id=jira_id,
    )


async def _generate_text_impl(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    step_name: str,
    trace_id: Optional[str],
    jira_id: Optional[str],
) -> str:
    """Internal implementation of generate_text."""
    trace_id = trace_id or str(uuid.uuid4())
    provider = _effective_provider()

    def _get_primary():
        if provider == "groq":
            if not GROQ_API_KEY or not GROQ_API_KEY.strip():
                raise ValueError("GROQ_API_KEY is not set (LLM_PROVIDER=groq)")
            return GROQ_MODEL, _generate_groq, None
        if provider == "openai":
            if not OPENAI_API_KEY or not OPENAI_API_KEY.strip():
                raise ValueError("OPENAI_API_KEY is not set (LLM_PROVIDER=openai)")
            return OPENAI_MODEL, _generate_openai, None
        if provider == "bedrock":
            if not _is_bedrock_available():
                raise ValueError("Bedrock: set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION (or AWS_PROFILE)")
            return BEDROCK_MODEL, _generate_bedrock, None
        if not ANTHROPIC_API_KEY or not ANTHROPIC_API_KEY.strip():
            raise ValueError("ANTHROPIC_API_KEY is not set")
        return ANTHROPIC_MODEL, _generate_anthropic, None

    def _get_fallback():
        return _get_generation_fallback(provider)

    model_name, generate_fn, model_override = _get_primary()
    fallback_model, fallback_fn, fallback_override = _get_fallback()

    timeout_sec = agentic_config.llm_timeout_seconds
    last_error = None
    full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"
    prompt_version = _get_prompt_versions().get(step_name)
    used_fallback = False

    async def _try_generate(fn, model_param: Optional[str] = None):
        await get_llm_limiter().acquire_async()
        if model_param and fn in (_generate_anthropic, _generate_bedrock):
            return await fn(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                timeout_sec=timeout_sec,
                model=model_param,
            )
        return await fn(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            timeout_sec=timeout_sec,
        )

    for attempt in range(3):
        start_time = time.perf_counter()
        input_tok = output_tok = None
        try:
            content, input_tok, output_tok = await _try_generate(generate_fn, model_override)
            text_out = _coerce_llm_text_response(content).strip()
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            _store_llm_run(
                trace_id=trace_id,
                jira_id=jira_id,
                step_name=step_name,
                model=model_name,
                prompt=full_prompt,
                response=text_out or None,
                tokens_input=input_tok,
                tokens_output=output_tok,
                latency_ms=elapsed_ms,
                prompt_version=prompt_version,
                retry_count=attempt,
            )
            logger.info_structured(
                "LLM text run completed",
                extra_fields={
                    "trace_id": trace_id,
                    "step_name": step_name,
                    "tokens_input": input_tok,
                    "tokens_output": output_tok,
                    "latency_ms": elapsed_ms,
                    "used_fallback": used_fallback,
                },
            )
            return text_out
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            last_error = e
            _store_llm_run(
                trace_id=trace_id,
                jira_id=jira_id,
                step_name=step_name,
                model=model_name,
                prompt=full_prompt,
                response=None,
                tokens_input=None,
                tokens_output=None,
                latency_ms=elapsed_ms,
                error_type=type(e).__name__,
                prompt_version=prompt_version,
                retry_count=attempt,
            )
            logger.error_structured(
                "LLM text run failed",
                extra_fields={
                    "trace_id": trace_id,
                    "step_name": step_name,
                    "latency_ms": elapsed_ms,
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                exc_info=True,
            )
            if (
                not used_fallback
                and _is_retryable_llm_error(e)
                and fallback_fn is not None
                and fallback_model
            ):
                used_fallback = True
                model_name = fallback_model
                generate_fn = fallback_fn
                model_override = fallback_override
                last_error = None
                continue
        if attempt < 2:
            time.sleep(0.5 * (attempt + 1))

    raise last_error or ValueError("Failed to generate text from LLM")


async def generate_text(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1200,
    step_name: str = "llm_generate_text",
    trace_id: Optional[str] = None,
    jira_id: Optional[str] = None,
) -> str:
    """Call configured LLM provider and return raw text."""
    impl = _generate_text_impl
    if _is_langsmith_tracing_enabled():
        try:
            from langsmith.run_helpers import traceable
            impl = traceable(run_type="llm", name="LLM generate_text")(_generate_text_impl)
        except ImportError:
            pass
    return await impl(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
        step_name=step_name,
        trace_id=trace_id,
        jira_id=jira_id,
    )
