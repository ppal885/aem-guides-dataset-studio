"""Governance helpers for screenshot DITA authoring (audit fields, redaction, prompt hashing)."""

from app.services.chat_authoring_governance import (
    describe_user_prompt_for_audit,
    redact_free_text,
    sha256_hex_bytes,
)


def test_describe_user_prompt_hash_only_has_digest():
    d = describe_user_prompt_for_audit("Generate a task from this UI.")
    assert d["user_prompt_length"] > 0
    assert len(d["user_prompt_sha256"]) == 64
    assert "user_prompt_preview_redacted" not in d


def test_redact_email_in_error_string():
    s = redact_free_text("Contact admin@example.com for help.")
    assert "admin@example.com" not in s
    assert "[REDACTED_EMAIL]" in s


def test_sha256_hex_stable():
    assert sha256_hex_bytes(b"a") == sha256_hex_bytes(b"a")
    assert sha256_hex_bytes(b"a") != sha256_hex_bytes(b"b")
