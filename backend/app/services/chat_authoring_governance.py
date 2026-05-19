"""
Enterprise governance hooks for screenshot + reference DITA authoring.

Provides:
- Correlation IDs: ``authoring_trace_id`` (chat/HTTP scope) + existing ``pipeline_run_id`` (pipeline scope)
- Audit-oriented structured logs (no raw screenshots, no full prompts by default)
- Optional content hashing for reference / image provenance (see env flags)
- Redaction helpers for log fields and error strings
- Feature flags via environment variables

Log consumers (SIEM / Loki / CloudWatch) should index ``event``, ``authoring_trace_id``,
``pipeline_run_id``, ``tenant_id``, ``session_id``.

Security: do not enable full prompt logging in multi-tenant production without DLP review.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
import uuid
from typing import Any

from app.core.schemas_chat_authoring import ChatAttachmentRef, ChatDitaGenerationOptions
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

# --- Feature flags (env) ---


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw, 10)
    except ValueError:
        return default


def audit_logging_enabled() -> bool:
    return _bool_env("CHAT_AUTHORING_AUDIT_LOG_ENABLED", True)


def failure_analytics_enabled() -> bool:
    return _bool_env("CHAT_AUTHORING_FAILURE_ANALYTICS_ENABLED", True)


def store_asset_content_sha256() -> bool:
    """When true, chat asset metadata may include sha256 of uploaded bytes (reference + image)."""

    return _bool_env("CHAT_AUTHORING_STORE_ASSET_SHA256", True)


def strict_image_magic_bytes() -> bool:
    """Reject image uploads that do not match known raster signatures."""

    return _bool_env("CHAT_AUTHORING_STRICT_IMAGE_MAGIC", True)


def prompt_log_mode() -> str:
    """
    ``hash_only`` (default): log length + sha256 hex digest only.
    ``truncated``: log first N chars after redaction (see CHAT_AUTHORING_PROMPT_LOG_MAX_CHARS).
    ``off``: log no prompt-derived fields except length.
    """

    raw = (os.getenv("CHAT_AUTHORING_PROMPT_LOG_MODE") or "hash_only").strip().lower()
    if raw in {"hash_only", "truncated", "off"}:
        return raw
    return "hash_only"


def prompt_log_max_chars() -> int:
    return max(0, _int_env("CHAT_AUTHORING_PROMPT_LOG_MAX_CHARS", 0))


# --- Redaction ---

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
# Loose API-key style tokens (conservative redaction for logs)
_TOKEN_RE = re.compile(r"\b(?:sk|pk|api)[-_][A-Za-z0-9]{16,}\b", re.IGNORECASE)


def redact_free_text(value: str, *, max_len: int = 500) -> str:
    """Remove common PII patterns and cap length for failure/analytics strings."""

    s = (value or "").strip()
    if not s:
        return ""
    s = _EMAIL_RE.sub("[REDACTED_EMAIL]", s)
    s = _TOKEN_RE.sub("[REDACTED_TOKEN]", s)
    if len(s) > max_len:
        return s[:max_len] + "…"
    return s


def describe_user_prompt_for_audit(prompt: str) -> dict[str, Any]:
    """Fields safe for structured logs (no raw prompt unless explicitly configured)."""

    raw = prompt or ""
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
    base: dict[str, Any] = {
        "user_prompt_length": len(raw),
        "user_prompt_sha256": digest,
    }
    mode = prompt_log_mode()
    if mode == "off":
        return base
    if mode == "hash_only":
        return base
    if mode == "truncated":
        n = prompt_log_max_chars()
        if n <= 0:
            return base
        snippet = redact_free_text(raw[:n], max_len=n)
        base["user_prompt_preview_redacted"] = snippet
    return base


def sha256_hex_bytes(content: bytes) -> str:
    """Content digest for provenance metadata (not a secret)."""

    return hashlib.sha256(content).hexdigest()


def new_authoring_trace_id() -> str:
    return str(uuid.uuid4())


def attachment_provenance(attachments: list[ChatAttachmentRef]) -> list[dict[str, Any]]:
    """Stable, log-safe attachment summary (ids, kinds, sizes — no content)."""

    out: list[dict[str, Any]] = []
    for a in attachments:
        out.append(
            {
                "asset_id": a.asset_id,
                "kind": a.kind,
                "filename": a.filename,
                "size_bytes": a.size_bytes,
                "mime_type": a.mime_type,
            }
        )
    return out


def generation_options_audit_summary(opts: ChatDitaGenerationOptions) -> dict[str, Any]:
    return {
        "dita_type": opts.dita_type,
        "style_strictness": opts.style_strictness,
        "strict_validation": opts.strict_validation,
        "output_mode": opts.output_mode,
        "has_save_path": bool((opts.save_path or "").strip()),
        "auto_ids": opts.auto_ids,
        "xref_placeholders": opts.xref_placeholders,
        "preserve_prolog": opts.preserve_prolog,
    }


def log_authoring_trace_started(
    *,
    authoring_trace_id: str,
    session_id: str,
    user_id: str,
    tenant_id: str,
    attachments: list[ChatAttachmentRef],
    generation_options: ChatDitaGenerationOptions,
    user_prompt: str,
) -> None:
    if not audit_logging_enabled():
        return
    fields: dict[str, Any] = {
        "event": "chat_authoring_trace_started",
        "authoring_trace_id": authoring_trace_id,
        "session_id": session_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "attachment_provenance": attachment_provenance(attachments),
        "generation_options": generation_options_audit_summary(generation_options),
    }
    fields.update(describe_user_prompt_for_audit(user_prompt))
    logger.info_structured("chat_authoring_trace_started", extra_fields=fields)


def log_authoring_trace_completed(
    *,
    authoring_trace_id: str,
    session_id: str,
    user_id: str,
    tenant_id: str,
    pipeline_run_id: str | None,
    pipeline_version: str | None,
    status: str,
    dita_type: str,
    validation_valid: bool,
    validation_error_count: int,
    validation_warning_count: int,
    had_reference_dita: bool,
    parse_reference_ok: bool | None,
    vision_provider: str | None,
    serialization_mode: str | None,
    duration_ms: float,
    generated_asset_id: str | None,
) -> None:
    if not audit_logging_enabled():
        return
    logger.info_structured(
        "chat_authoring_trace_completed",
        extra_fields={
            "event": "chat_authoring_trace_completed",
            "authoring_trace_id": authoring_trace_id,
            "pipeline_run_id": pipeline_run_id,
            "pipeline_version": pipeline_version,
            "session_id": session_id,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "result_status": status,
            "dita_type": dita_type,
            "validation_valid": validation_valid,
            "validation_error_count": validation_error_count,
            "validation_warning_count": validation_warning_count,
            "had_reference_dita": had_reference_dita,
            "parse_reference_ok": parse_reference_ok,
            "vision_provider": vision_provider,
            "serialization_mode": serialization_mode,
            "duration_ms": round(duration_ms, 2),
            "generated_asset_id": generated_asset_id,
        },
    )


def log_authoring_trace_failed(
    *,
    authoring_trace_id: str,
    session_id: str,
    user_id: str,
    tenant_id: str,
    error_stage: str,
    error_message_redacted: str,
    duration_ms: float | None = None,
) -> None:
    if not failure_analytics_enabled():
        return
    fields: dict[str, Any] = {
        "event": "chat_authoring_trace_failed",
        "authoring_trace_id": authoring_trace_id,
        "session_id": session_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "error_stage": error_stage,
        "error_message_redacted": redact_free_text(error_message_redacted, max_len=800),
    }
    if duration_ms is not None:
        fields["duration_ms"] = round(duration_ms, 2)
    logger.warning_structured("chat_authoring_trace_failed", extra_fields=fields)


def log_authoring_intent_rejected(
    *,
    authoring_trace_id: str,
    session_id: str,
    user_id: str,
    tenant_id: str,
    reason: str,
    confidence: float,
) -> None:
    if not audit_logging_enabled():
        return
    logger.info_structured(
        "chat_authoring_intent_rejected",
        extra_fields={
            "event": "chat_authoring_intent_rejected",
            "authoring_trace_id": authoring_trace_id,
            "session_id": session_id,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "classification_reason_redacted": redact_free_text(reason, max_len=400),
            "classification_confidence": confidence,
        },
    )


class AuthoringRunTimer:
    """Simple wall-clock timer for audit duration fields."""

    def __init__(self) -> None:
        self._t0 = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._t0) * 1000.0
