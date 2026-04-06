"""Tool argument parser with JSON repair for streaming tool calls.

Groq and OpenAI stream tool call arguments character-by-character.
If the stream is interrupted, the accumulated JSON may be truncated.
This module provides validated parsing with heuristic repair so that
tool calls don't silently fall back to empty parameters.

Feature flag: CHAT_TOOL_PARSE_VALIDATION (default True)
"""
import json
import re
from typing import Optional


def parse_tool_arguments(
    raw: str,
    tool_name: str = "",
    *,
    attempt_repair: bool = True,
) -> tuple[dict, Optional[str]]:
    """Parse tool call arguments JSON with optional repair.

    Returns:
        (parsed_dict, error_or_none)
        - On success: (dict, None)
        - On repair success: (dict, None) — repaired JSON parsed OK
        - On failure: ({}, "description of parse error")
    """
    if not raw or not raw.strip():
        return {}, None  # Empty args is valid (tool with no required params)

    stripped = raw.strip()

    # Fast path: valid JSON
    try:
        result = json.loads(stripped)
        if isinstance(result, dict):
            return result, None
        # Got a non-dict (list, string, number) — wrap error
        return {}, f"Tool '{tool_name}' arguments parsed as {type(result).__name__}, expected object"
    except json.JSONDecodeError:
        pass

    # Attempt repair if enabled
    if attempt_repair:
        repaired = repair_truncated_json(stripped)
        if repaired is not None:
            try:
                result = json.loads(repaired)
                if isinstance(result, dict):
                    return result, None
            except json.JSONDecodeError:
                pass

    return {}, f"Tool '{tool_name}' arguments are malformed JSON: {stripped[:120]}..."


def repair_truncated_json(raw: str) -> Optional[str]:
    """Attempt to repair truncated JSON by closing unclosed structures.

    Handles common streaming truncation patterns:
    - Unclosed strings: {"text": "hello wor  ->  {"text": "hello wor"}
    - Unclosed objects: {"text": "hello"     ->  {"text": "hello"}
    - Unclosed arrays:  {"items": ["a", "b"  ->  {"items": ["a", "b"]}
    - Trailing comma:   {"a": 1,             ->  {"a": 1}

    Returns repaired JSON string or None if repair is not possible.
    """
    if not raw or not raw.strip():
        return None

    text = raw.strip()

    # Must start with { for a tool argument object
    if not text.startswith("{"):
        return None

    # Track open structures
    in_string = False
    escape_next = False
    stack: list[str] = []  # tracks { and [

    i = 0
    while i < len(text):
        ch = text[i]

        if escape_next:
            escape_next = False
            i += 1
            continue

        if ch == "\\":
            if in_string:
                escape_next = True
            i += 1
            continue

        if ch == '"':
            in_string = not in_string
            i += 1
            continue

        if in_string:
            i += 1
            continue

        # Outside string
        if ch == "{":
            stack.append("{")
        elif ch == "[":
            stack.append("[")
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()

        i += 1

    # If already balanced, return as-is
    if not stack and not in_string:
        return text

    # Build repair suffix
    suffix = ""

    # Close unclosed string first
    if in_string:
        suffix += '"'

    # Remove trailing comma before closing (common truncation pattern)
    trimmed = text.rstrip()
    if in_string:
        trimmed = trimmed  # Don't trim inside string
    else:
        trimmed = re.sub(r",\s*$", "", trimmed)
        text = trimmed

    # Close structures in reverse order
    for bracket in reversed(stack):
        if bracket == "{":
            suffix += "}"
        elif bracket == "[":
            suffix += "]"

    repaired = text + suffix
    return repaired
