"""
Content validation for chat messages and generate-from-text.
Enforces max length, blocks prompt-injection/jailbreak patterns, and filters PII.
"""
import os
import re
from typing import Optional

# Max lengths (configurable via env)
CHAT_MESSAGE_MAX_LEN = int(os.getenv("CHAT_MESSAGE_MAX_LEN", "50000"))
GENERATE_TEXT_MAX_LEN = int(os.getenv("GENERATE_TEXT_MAX_LEN", "100000"))
GENERATE_INSTRUCTIONS_MAX_LEN = int(os.getenv("GENERATE_INSTRUCTIONS_MAX_LEN", "10000"))
# Optional Jira / ticket paste for screenshot authoring (separate from main chat prompt)
AUTHORING_JIRA_CONTEXT_MAX_LEN = int(os.getenv("AUTHORING_JIRA_CONTEXT_MAX_LEN", "32000"))

# Prompt-injection / jailbreak / system-prompt override patterns (case-insensitive)
# Block inputs that attempt to override instructions or jailbreak the model
INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?",
    r"disregard\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?",
    r"forget\s+(?:everything|all\s+(?:previous|prior|above))",
    r"you\s+are\s+now\s+(?:a|an)\s+",
    r"new\s+instructions?\s*:",
    r"system\s*:\s*",
    r"system\s+prompt\s*:",
    r"###\s*system\s*:",
    r"\[system\]",
    r"<\|system\|>",
    r"jailbreak",
    r"DAN\s+mode",
    r"developer\s+mode",
    r"bypass\s+(?:safety|restrictions)",
    r"pretend\s+you\s+have\s+no\s+restrictions",
    r"act\s+as\s+if\s+you\s+(?:are|were)\s+unrestricted",
    r"from\s+now\s+on\s+you\s+will",
    r"override\s+(?:your|the)\s+(?:instructions|prompt)",
]

# PII patterns - block inputs containing likely sensitive data
PII_PATTERNS = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "SSN-like pattern"),
    (r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b", "Credit card-like pattern"),
]

# Control characters and null bytes
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _check_patterns(text: str, patterns: list, flags: int = re.IGNORECASE) -> Optional[str]:
    """Return first matching pattern description, or None."""
    for item in patterns:
        if isinstance(item, tuple):
            pat, desc = item
        else:
            pat, desc = item, "blocked pattern"
        if re.search(pat, text, flags):
            return desc
    return None


def _check_injection(text: str) -> Optional[str]:
    """Return error message if injection pattern detected, else None."""
    return _check_patterns(text, [(p, "Input contains blocked content") for p in INJECTION_PATTERNS])


def _check_pii(text: str) -> Optional[str]:
    """Return error message if PII pattern detected, else None."""
    return _check_patterns(text, PII_PATTERNS)


def _strip_control_chars(text: str) -> str:
    """Remove control characters and null bytes."""
    return CONTROL_CHAR_PATTERN.sub("", text)


def validate_authoring_jira_context(raw: str | None) -> Optional[str]:
    """
    Validate optional Jira/issue text attached to screenshot authoring.
    Empty or whitespace-only input is valid (returns None).
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        return "Jira context must be a string"
    text = raw.strip()
    if not text:
        return None
    if len(text) > AUTHORING_JIRA_CONTEXT_MAX_LEN:
        return f"Jira context exceeds maximum length of {AUTHORING_JIRA_CONTEXT_MAX_LEN} characters"
    if CONTROL_CHAR_PATTERN.search(text):
        return "Jira context contains invalid control characters"
    err = _check_injection(text)
    if err:
        return err
    return None


def validate_chat_content(content: str) -> Optional[str]:
    """
    Validate chat message content.
    Returns error message if invalid, None if valid.
    """
    if not isinstance(content, str):
        return "Content must be a string"
    content = content.strip()
    if not content:
        return "Message cannot be empty"
    if len(content) > CHAT_MESSAGE_MAX_LEN:
        return f"Message exceeds maximum length of {CHAT_MESSAGE_MAX_LEN} characters"
    if CONTROL_CHAR_PATTERN.search(content):
        return "Message contains invalid control characters"
    err = _check_injection(content)
    if err:
        return err
    err = _check_pii(content)
    if err:
        return f"Message may contain sensitive data ({err})"
    return None


def validate_generate_text(text: str, instructions: Optional[str] = None) -> Optional[str]:
    """
    Validate generate-from-text request body.
    Returns error message if invalid, None if valid.
    """
    if not isinstance(text, str):
        return "text must be a string"
    text = text.strip()
    if not text:
        return "text cannot be empty"
    if len(text) > GENERATE_TEXT_MAX_LEN:
        return f"text exceeds maximum length of {GENERATE_TEXT_MAX_LEN} characters"
    if CONTROL_CHAR_PATTERN.search(text):
        return "text contains invalid control characters"
    err = _check_injection(text)
    if err:
        return err
    err = _check_pii(text)
    if err:
        return f"text may contain sensitive data ({err})"

    if instructions is not None and isinstance(instructions, str):
        instructions = instructions.strip()
        if instructions and len(instructions) > GENERATE_INSTRUCTIONS_MAX_LEN:
            return f"instructions exceeds maximum length of {GENERATE_INSTRUCTIONS_MAX_LEN} characters"
        if instructions and CONTROL_CHAR_PATTERN.search(instructions):
            return "instructions contains invalid control characters"
        if instructions:
            err = _check_injection(instructions)
            if err:
                return err
            err = _check_pii(instructions)
            if err:
                return f"instructions may contain sensitive data ({err})"

    return None


def sanitize_for_llm(text: str) -> str:
    """
    Sanitize user input before passing to LLM.
    Strips control characters; does not modify content otherwise.
    """
    if not text or not isinstance(text, str):
        return ""
    return _strip_control_chars(text)


CONTEXT_FIELD_MAX_LEN = 500


def validate_chat_context(context: Optional[dict]) -> Optional[str]:
    """
    Validate chat context dict (source_page, issue_key, issue_summary).
    Returns error message if invalid, None if valid.
    """
    if not context or not isinstance(context, dict):
        return None
    for key in ("source_page", "source", "issue_key", "issue_summary"):
        val = context.get(key)
        if val is None:
            continue
        if not isinstance(val, str):
            return f"context.{key} must be a string"
        if len(val) > CONTEXT_FIELD_MAX_LEN:
            return f"context.{key} exceeds maximum length of {CONTEXT_FIELD_MAX_LEN} characters"
        if _check_injection(val):
            return f"context.{key} contains blocked content"
    return None
