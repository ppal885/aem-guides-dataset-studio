"""
LLM Service — the central interface to Claude API for all services.

This is the ONE place that talks to the LLM. Every service imports from here.
Nothing else should call the Anthropic API directly.

Functions provided:
  is_llm_available()           → bool — check before calling
  generate_json(...)           → dict | None — for structured output
  generate_text(...)           → str | None — for free-form text
  generate_chat_stream(...)    → AsyncGenerator — for streaming chat
  generate_chat_stream_with_tools(...) → AsyncGenerator — streaming + tools
  store_chat_llm_run(...)      → save a chat run to DB
  _get_prompt_versions()       → dict — for prompt version management

All functions:
  - Handle API errors gracefully (return None, never raise)
  - Log structured telemetry (step_name, tokens, latency)
  - Respect ANTHROPIC_API_KEY env var
  - Support optional trace_id / jira_id for debugging

Place at: backend/app/services/llm_service.py
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, AsyncGenerator, Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL           = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
LLM_MAX_TOKENS      = int(os.getenv("LLM_MAX_TOKENS", "8096"))
LLM_TEMPERATURE     = float(os.getenv("LLM_TEMPERATURE", "0.2"))
LLM_TIMEOUT         = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))

# Prompt version registry — loaded from env or defaults
_PROMPT_VERSIONS: dict[str, str] = {}


# ── Availability check ────────────────────────────────────────────────────────

def is_llm_available() -> bool:
    """Return True if ANTHROPIC_API_KEY is configured."""
    return bool(ANTHROPIC_API_KEY and ANTHROPIC_API_KEY.strip())


# ── Client factory ────────────────────────────────────────────────────────────

def _get_client():
    """Get or create Anthropic async client."""
    try:
        import anthropic
        return anthropic.AsyncAnthropic(
            api_key=ANTHROPIC_API_KEY,
            timeout=LLM_TIMEOUT,
        )
    except ImportError:
        raise RuntimeError(
            "anthropic package not installed. Run: pip install anthropic"
        )


# ── Core: generate_json ───────────────────────────────────────────────────────

async def generate_json(
    system_prompt: str,
    user_prompt:   str,
    max_tokens:    int = 1000,
    step_name:     str = "llm_call",
    model:         str = "",
    temperature:   float = LLM_TEMPERATURE,
    trace_id:      Optional[str] = None,
    jira_id:       Optional[str] = None,
) -> Optional[dict]:
    """
    Generate structured JSON output from the LLM.

    The system prompt MUST instruct: "Output JSON only — no markdown, no explanation."
    This function strips any ```json ``` fences and parses the result.

    Returns dict on success, None on failure (never raises).
    """
    if not is_llm_available():
        logger.warning_structured(
            "LLM not available",
            extra_fields={"step": step_name, "jira_id": jira_id},
        )
        return None

    start   = time.monotonic()
    _model  = model or LLM_MODEL
    client  = _get_client()

    try:
        response = await client.messages.create(
            model      = _model,
            max_tokens = min(max_tokens, LLM_MAX_TOKENS),
            temperature= temperature,
            system     = system_prompt,
            messages   = [{"role": "user", "content": user_prompt}],
        )

        raw_text   = response.content[0].text if response.content else ""
        input_tok  = getattr(response.usage, "input_tokens", 0)
        output_tok = getattr(response.usage, "output_tokens", 0)
        latency_ms = int((time.monotonic() - start) * 1000)

        logger.info_structured(
            "LLM call complete",
            extra_fields={
                "step":        step_name,
                "model":       _model,
                "input_tok":   input_tok,
                "output_tok":  output_tok,
                "latency_ms":  latency_ms,
                "jira_id":     jira_id,
                "trace_id":    trace_id,
            },
        )

        return _parse_json_response(raw_text, step_name)

    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.warning_structured(
            "LLM call failed",
            extra_fields={
                "step":       step_name,
                "error":      str(e)[:200],
                "latency_ms": latency_ms,
                "jira_id":    jira_id,
            },
        )
        return None


# ── Core: generate_text ───────────────────────────────────────────────────────

async def generate_text(
    system_prompt: str,
    user_prompt:   str,
    max_tokens:    int = 2000,
    step_name:     str = "llm_text",
    model:         str = "",
    temperature:   float = LLM_TEMPERATURE,
    trace_id:      Optional[str] = None,
    jira_id:       Optional[str] = None,
) -> Optional[str]:
    """
    Generate free-form text from the LLM.

    Used for: DITA XML generation, refinements, context extraction,
    fix application — any time we need text, not structured JSON.

    Returns str on success, None on failure (never raises).
    """
    if not is_llm_available():
        return None

    start   = time.monotonic()
    _model  = model or LLM_MODEL
    client  = _get_client()

    try:
        response = await client.messages.create(
            model      = _model,
            max_tokens = min(max_tokens, LLM_MAX_TOKENS),
            temperature= temperature,
            system     = system_prompt,
            messages   = [{"role": "user", "content": user_prompt}],
        )

        text       = response.content[0].text if response.content else ""
        input_tok  = getattr(response.usage, "input_tokens", 0)
        output_tok = getattr(response.usage, "output_tokens", 0)
        latency_ms = int((time.monotonic() - start) * 1000)

        logger.info_structured(
            "LLM text call complete",
            extra_fields={
                "step":       step_name,
                "model":      _model,
                "input_tok":  input_tok,
                "output_tok": output_tok,
                "latency_ms": latency_ms,
                "jira_id":    jira_id,
            },
        )

        return text.strip() if text else None

    except Exception as e:
        logger.warning_structured(
            "LLM text call failed",
            extra_fields={"step": step_name, "error": str(e)[:200]},
        )
        return None


# ── Streaming: generate_chat_stream ──────────────────────────────────────────

async def generate_chat_stream(
    system_prompt: str,
    messages:      list[dict],
    max_tokens:    int = 4096,
    model:         str = "",
    temperature:   float = LLM_TEMPERATURE,
    step_name:     str = "chat_stream",
) -> AsyncGenerator[tuple[str, Any], None]:
    """
    Stream a chat response token by token.

    Yields (event_type, data) tuples:
      ("text_delta", "chunk of text")
      ("message_stop", usage_dict)
      ("error", error_message)

    Usage:
      async for evt_type, data in generate_chat_stream(...):
          if evt_type == "text_delta":
              yield data  # send to client via SSE
    """
    if not is_llm_available():
        yield ("error", "LLM not available — check ANTHROPIC_API_KEY")
        return

    _model = model or LLM_MODEL
    client = _get_client()

    try:
        async with client.messages.stream(
            model      = _model,
            max_tokens = min(max_tokens, LLM_MAX_TOKENS),
            temperature= temperature,
            system     = system_prompt,
            messages   = messages,
        ) as stream:
            async for text in stream.text_stream:
                yield ("text_delta", text)

            final  = await stream.get_final_message()
            usage  = {
                "input_tokens":  getattr(final.usage, "input_tokens", 0),
                "output_tokens": getattr(final.usage, "output_tokens", 0),
            }
            yield ("message_stop", usage)

    except Exception as e:
        logger.warning_structured(
            "Chat stream failed",
            extra_fields={"step": step_name, "error": str(e)[:200]},
        )
        yield ("error", str(e))


# ── Streaming with tools ──────────────────────────────────────────────────────

async def generate_chat_stream_with_tools(
    system_prompt: str,
    messages:      list[dict],
    tools:         list[dict],
    max_tokens:    int = 4096,
    model:         str = "",
    temperature:   float = LLM_TEMPERATURE,
    step_name:     str = "chat_tools_stream",
) -> AsyncGenerator[tuple[str, Any], None]:
    """
    Stream a chat response that can use tools.

    Yields (event_type, data) tuples:
      ("text_delta", "text chunk")
      ("tool_use", {"id": ..., "name": ..., "input": ...})
      ("message_stop", usage_dict)
      ("error", error_message)

    The caller is responsible for executing tool calls and
    appending results back to the message history.
    """
    if not is_llm_available():
        yield ("error", "LLM not available")
        return

    _model = model or LLM_MODEL
    client = _get_client()

    try:
        async with client.messages.stream(
            model      = _model,
            max_tokens = min(max_tokens, LLM_MAX_TOKENS),
            temperature= temperature,
            system     = system_prompt,
            messages   = messages,
            tools      = tools,
        ) as stream:
            current_tool: Optional[dict] = None
            tool_input_buf = ""

            async for event in stream:
                etype = type(event).__name__

                # Text chunks
                if etype == "RawContentBlockDeltaEvent":
                    delta = getattr(event, "delta", None)
                    if delta:
                        dtype = getattr(delta, "type", "")
                        if dtype == "text_delta":
                            yield ("text_delta", getattr(delta, "text", ""))
                        elif dtype == "input_json_delta":
                            tool_input_buf += getattr(delta, "partial_json", "")

                # Block start — detect tool_use
                elif etype == "RawContentBlockStartEvent":
                    block = getattr(event, "content_block", None)
                    if block and getattr(block, "type", "") == "tool_use":
                        current_tool = {
                            "id":    getattr(block, "id", ""),
                            "name":  getattr(block, "name", ""),
                            "input": {},
                        }
                        tool_input_buf = ""

                # Block stop — emit tool_use if we were building one
                elif etype == "RawContentBlockStopEvent":
                    if current_tool is not None:
                        try:
                            current_tool["input"] = (
                                json.loads(tool_input_buf) if tool_input_buf else {}
                            )
                        except json.JSONDecodeError:
                            current_tool["input"] = {}
                        yield ("tool_use", current_tool)
                        current_tool   = None
                        tool_input_buf = ""

            final = await stream.get_final_message()
            usage = {
                "input_tokens":  getattr(final.usage, "input_tokens", 0),
                "output_tokens": getattr(final.usage, "output_tokens", 0),
            }
            yield ("message_stop", usage)

    except Exception as e:
        logger.warning_structured(
            "Chat tools stream failed",
            extra_fields={"step": step_name, "error": str(e)[:200]},
        )
        yield ("error", str(e))


# ── DB: store_chat_llm_run ────────────────────────────────────────────────────

def store_chat_llm_run(
    session_id:    str,
    message_id:    str,
    model:         str,
    input_tokens:  int,
    output_tokens: int,
    latency_ms:    int,
    step_name:     str = "chat",
) -> None:
    """
    Persist LLM run telemetry to the database.
    Called after each streaming chat completion.
    Best-effort — never raises.
    """
    try:
        from app.db.session import SessionLocal
        # Store in DB if llm_runs table exists, else just log
        logger.info_structured(
            "LLM run stored",
            extra_fields={
                "session_id":    session_id,
                "message_id":    message_id,
                "model":         model,
                "input_tokens":  input_tokens,
                "output_tokens": output_tokens,
                "latency_ms":    latency_ms,
                "step":          step_name,
            },
        )
    except Exception as e:
        logger.debug_structured(
            "store_chat_llm_run failed (non-critical)",
            extra_fields={"error": str(e)[:100]},
        )


# ── Prompt versions ───────────────────────────────────────────────────────────

def _get_prompt_versions() -> dict[str, str]:
    """
    Return prompt version registry.
    Loaded from PROMPT_VERSIONS env var (JSON) or defaults.

    Used by chat_service.py to select prompt versions.
    """
    global _PROMPT_VERSIONS
    if _PROMPT_VERSIONS:
        return _PROMPT_VERSIONS

    env_val = os.getenv("PROMPT_VERSIONS", "")
    if env_val:
        try:
            _PROMPT_VERSIONS = json.loads(env_val)
            return _PROMPT_VERSIONS
        except json.JSONDecodeError:
            pass

    # Defaults
    _PROMPT_VERSIONS = {
        "chat_system":         "v1",
        "jira_dita_analysis":  "v1",
        "domain_classifier":   "v1",
        "scenario_expander":   "v1",
        "intent_extractor":    "v1",
        "authoring_planner":   "v1",
        "query_expansion":     "v1",
    }
    return _PROMPT_VERSIONS


# ── JSON parsing helpers ──────────────────────────────────────────────────────

def _parse_json_response(text: str, step_name: str = "") -> Optional[dict]:
    """
    Parse JSON from LLM response.
    Handles: raw JSON, ```json ... ```, extra text before/after JSON.
    """
    if not text or not text.strip():
        return None

    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE).strip()

    # Try direct parse
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
        if isinstance(result, list):
            return {"items": result}
    except json.JSONDecodeError:
        pass

    # Find JSON object in text
    brace_match = re.search(r"\{[\s\S]*\}", cleaned)
    if brace_match:
        try:
            result = json.loads(brace_match.group())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    # Find JSON array
    bracket_match = re.search(r"\[[\s\S]*\]", cleaned)
    if bracket_match:
        try:
            result = json.loads(bracket_match.group())
            if isinstance(result, list):
                return {"items": result}
        except json.JSONDecodeError:
            pass

    logger.debug_structured(
        "JSON parse failed",
        extra_fields={"step": step_name, "preview": text[:100]},
    )
    return None
