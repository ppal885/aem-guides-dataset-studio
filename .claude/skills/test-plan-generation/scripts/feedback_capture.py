#!/usr/bin/env python3
"""Capture and review Human UAC feedback through the shared Dataset Studio API.

This module is intentionally stdlib-only so Claude Desktop, Codex, and the skill CLI
can use the same transport contract.  Only capture requests may be queued, and the
queue contains a redacted correction plus immutable binding identifiers.  Drafts,
credentials, AI classifications, and review/approval requests are never queued.

The API remains the authority for persistence, binding, approval, indexing, and actor
identity.  A local queue record is not saved feedback and is never learning truth.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import http.server
import ipaddress
import json
import os
import re
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

try:  # pragma: no cover - platform-specific branches are exercised on their host OS.
    import fcntl
except ImportError:  # Windows
    fcntl = None  # type: ignore[assignment]
try:  # pragma: no cover - platform-specific branches are exercised on their host OS.
    import msvcrt
except ImportError:  # POSIX
    msvcrt = None  # type: ignore[assignment]


API_PREFIX = "/api/v1/test-plan-learning"
QUEUE_SCHEMA = "shared-uac-feedback-queue-v1"
CAPTURE_CONTRACT = "shared-uac-feedback-v1"
MAX_RESPONSE_BYTES = 2_000_000
MAX_QUEUE_BYTES = 4_000_000
MAX_QUEUE_RECORDS = 1_000
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
DELTA_TYPES = frozenset({
    "UNCLASSIFIED",
    "COVERAGE_ADDED",
    "COVERAGE_REMOVED",
    "SCOPE_NARROWED",
    "SCOPE_EXPANDED",
    "DISPOSITION_CHANGED",
    "OPEN_QUESTION_ADDED",
    "OPEN_QUESTION_REMOVED",
    "LANGUAGE_SIMPLIFIED",
    "AC_MERGED",
    "AC_SPLIT",
    "ORACLE_CHANGED",
    "PRIORITY_CHANGED",
    "IMPLEMENTATION_DETAIL_REMOVED",
})
SOURCE_KINDS = frozenset({"HUMAN_CORRECTION", "AI_PROPOSAL", "UNCONFIRMED"})

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_HEX_64 = re.compile(r"^[a-f0-9]{64}$")
_BEARER = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]+")
_NAMED_SECRET = re.compile(
    r"(?i)\b(api[\s_-]?key|access[\s_-]?token|auth[\s_-]?token|token|password|passwd|secret)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_URL_USERINFO = re.compile(r"(?i)(https?://)([^/@\s:]+):([^/@\s]+)@")


class FeedbackTransportError(RuntimeError):
    """A sanitized transport error suitable for CLI/MCP reporting."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Prevent Authorization from following redirects to another origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def redact_text(value: object, *, limit: int = 12_000) -> str:
    """Redact common credential shapes without claiming semantic anonymization."""

    text = str(value or "")[:limit]
    text = _BEARER.sub(r"\1[REDACTED]", text)
    text = _NAMED_SECRET.sub(r"\1\2[REDACTED]", text)
    text = _URL_USERINFO.sub(r"\1[REDACTED]@", text)
    return text


def _clean_text(value: object, name: str, *, required: bool, limit: int) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{name} is required")
    if len(text) > limit:
        raise ValueError(f"{name} exceeds {limit} characters")
    if "\r" in text or "\n" in text:
        if name.endswith("_id") or name in {"jira_key", "tenant_id", "idempotency_key"}:
            raise ValueError(f"{name} must be a single line")
    return text


def _bounded_text_preserve(value: object, name: str, *, required: bool, limit: int) -> str:
    """Bound content while preserving exact bytes represented by the input string."""

    text = str(value or "")
    if required and not text.strip():
        raise ValueError(f"{name} is required")
    if len(text) > limit:
        raise ValueError(f"{name} exceeds {limit} characters")
    return text


def _clean_identifier(value: object, name: str, *, required: bool, limit: int) -> str:
    text = _clean_text(value, name, required=required, limit=limit)
    if text and not _SAFE_ID.fullmatch(text):
        raise ValueError(f"{name} contains unsupported characters")
    return text


def _normalize_base_url(value: str) -> str:
    url = str(value or "").strip().rstrip("/")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("AEM Studio URL must be an absolute http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("AEM Studio URL must not contain credentials, query, or fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("AEM Studio URL must not contain a path")
    if parsed.scheme == "http" and not _http_allowed(parsed.hostname):
        raise ValueError(
            "Plain HTTP is allowed automatically only for loopback; use HTTPS or set "
            "AEM_STUDIO_ALLOW_INSECURE_HTTP=true for an explicitly accepted dev/VPN host"
        )
    return url


def _http_allowed(hostname: str) -> bool:
    if hostname.lower() == "localhost":
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and address.is_loopback:
        return True
    # Private/VPN HTTP is still plaintext.  It requires an explicit local opt-in;
    # production/team deployments should use TLS or a loopback tunnel.
    return os.environ.get("AEM_STUDIO_ALLOW_INSECURE_HTTP", "").lower() in {
        "1", "true", "yes",
    }


def _personal_token(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        raise ValueError("AEM_STUDIO_TOKEN is required")
    if token == "dev-bypass":
        raise ValueError(
            "Shared UAC feedback requires a personal token; dev-bypass cannot establish "
            "a named Human author or reviewer"
        )
    if any(ch in token for ch in "\r\n"):
        raise ValueError("AEM_STUDIO_TOKEN contains invalid control characters")
    return token


def _client_context(value: object) -> dict[str, str]:
    source = value if isinstance(value, Mapping) else {}
    client = str(source.get("client", "unknown"))
    if client not in {"claude_desktop", "codex", "api", "unknown"}:
        client = "unknown"
    return {
        "client": client,
        "session_id": _clean_text(source.get("session_id"), "session_id", required=False, limit=160),
        "message_id": _clean_text(source.get("message_id"), "message_id", required=False, limit=160),
    }


def normalize_draft_registration(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a draft registration independently from a feedback capture."""

    if not isinstance(payload, Mapping):
        raise ValueError("draft registration payload must be an object")
    criteria = payload.get("criteria") or {}
    if not isinstance(criteria, Mapping) or len(criteria) > 200:
        raise ValueError("criteria must be an object with at most 200 entries")
    safe_criteria: dict[str, str] = {}
    for key, text in criteria.items():
        clean_key = _clean_text(key, "criterion id", required=True, limit=120)
        safe_criteria[clean_key] = _bounded_text_preserve(
            text, "criterion text", required=True, limit=12_000
        )
    draft_markdown = _bounded_text_preserve(
        payload.get("draft_markdown"), "draft_markdown", required=True, limit=100_000
    )
    if any(text not in draft_markdown for text in safe_criteria.values()):
        raise ValueError("each criterion must be an exact substring of draft_markdown")
    fingerprint = _clean_text(
        payload.get("plan_fingerprint"), "plan_fingerprint", required=False, limit=64
    ).lower()
    if fingerprint and not _HEX_64.fullmatch(fingerprint):
        raise ValueError("plan_fingerprint must be 64 lowercase hexadecimal characters")
    return {
        "tenant_id": _clean_identifier(
            payload.get("tenant_id", "kone"), "tenant_id", required=True, limit=120
        ),
        "jira_key": _clean_identifier(
            payload.get("jira_key"), "jira_key", required=True, limit=64
        ),
        "plan_fingerprint": fingerprint,
        "idempotency_key": _clean_text(
            payload.get("idempotency_key"), "idempotency_key", required=True, limit=240
        ),
        "draft_markdown": draft_markdown,
        "criteria": safe_criteria,
        "evidence_bundle_id": _clean_text(
            payload.get("evidence_bundle_id"),
            "evidence_bundle_id",
            required=False,
            limit=180,
        ),
        "run_id": _clean_identifier(
            payload.get("run_id"), "run_id", required=False, limit=160
        ),
        "client_context": _client_context(payload.get("client_context")),
    }


def normalize_capture(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the public capture DTO before it reaches disk or the network."""

    if not isinstance(payload, Mapping):
        raise ValueError("capture payload must be an object")
    delta_type = str(payload.get("delta_type", "UNCLASSIFIED"))
    if delta_type not in DELTA_TYPES:
        raise ValueError("delta_type is unsupported")
    source_kind = str(payload.get("source_kind", "UNCONFIRMED"))
    if source_kind not in SOURCE_KINDS:
        raise ValueError("source_kind is unsupported")
    fingerprint = _clean_text(
        payload.get("plan_fingerprint"), "plan_fingerprint", required=False, limit=64
    ).lower()
    if fingerprint and not _HEX_64.fullmatch(fingerprint):
        raise ValueError("plan_fingerprint must be 64 lowercase hexadecimal characters")

    normalized: dict[str, Any] = {
        "contract_version": CAPTURE_CONTRACT,
        "tenant_id": _clean_identifier(
            payload.get("tenant_id", "kone"), "tenant_id", required=True, limit=120
        ),
        "jira_key": _clean_identifier(payload.get("jira_key"), "jira_key", required=True, limit=64),
        "idempotency_key": _clean_text(
            payload.get("idempotency_key"), "idempotency_key", required=True, limit=240
        ),
        "raw_feedback": _bounded_text_preserve(
            payload.get("raw_feedback"), "raw_feedback", required=True, limit=12_000
        ),
        "source_kind": source_kind,
        "proposed_correction": _bounded_text_preserve(
            payload.get("proposed_correction"),
            "proposed_correction",
            required=False,
            limit=12_000,
        ),
        "delta_type": delta_type,
        # Classification produced by a model remains advisory and never Human truth.
        "ai_classification": dict(payload.get("ai_classification") or {}),
        "draft_id": _clean_identifier(
            payload.get("draft_id"), "draft_id", required=False, limit=36
        ),
        "plan_fingerprint": fingerprint,
        "evidence_bundle_id": _clean_text(
            payload.get("evidence_bundle_id"),
            "evidence_bundle_id",
            required=False,
            limit=180,
        ),
        "run_id": _clean_identifier(payload.get("run_id"), "run_id", required=False, limit=160),
        "ac_id": _clean_identifier(payload.get("ac_id"), "ac_id", required=False, limit=120),
        "client_context": _client_context(payload.get("client_context")),
    }
    if len(normalized["ai_classification"]) > 20:
        raise ValueError("ai_classification exceeds 20 entries")
    draft = payload.get("draft")
    if draft is not None:
        if not isinstance(draft, Mapping):
            raise ValueError("draft must be an object")
        criteria = draft.get("criteria") or {}
        if not isinstance(criteria, Mapping) or len(criteria) > 200:
            raise ValueError("draft.criteria must be an object with at most 200 entries")
        safe_criteria: dict[str, str] = {}
        for key, text in criteria.items():
            clean_key = _clean_text(key, "criterion id", required=True, limit=120)
            safe_criteria[clean_key] = _bounded_text_preserve(
                text, "criterion text", required=True, limit=12_000
            )
        draft_markdown = _bounded_text_preserve(
            draft.get("draft_markdown"), "draft.draft_markdown", required=True, limit=100_000
        )
        if any(text not in draft_markdown for text in safe_criteria.values()):
            raise ValueError("each draft criterion must be an exact substring of draft_markdown")
        normalized["draft"] = {
            "draft_markdown": draft_markdown,
            "criteria": safe_criteria,
            "evidence_bundle_id": _clean_text(
                draft.get("evidence_bundle_id"),
                "draft.evidence_bundle_id",
                required=False,
                limit=180,
            ),
            "run_id": _clean_identifier(
                draft.get("run_id"), "draft.run_id", required=False, limit=160
            ),
            "client_context": _client_context(draft.get("client_context")),
        }
    return normalized


def queue_safe_capture(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce a capture to the only content allowed in the local retry queue."""

    normalized = normalize_capture(payload)
    raw_feedback = redact_text(normalized["raw_feedback"])
    proposed_correction = redact_text(normalized["proposed_correction"])
    if not raw_feedback.strip():
        raise ValueError("redacted correction is empty")
    return {
        "contract_version": CAPTURE_CONTRACT,
        "tenant_id": normalized["tenant_id"],
        "jira_key": normalized["jira_key"],
        "idempotency_key": normalized["idempotency_key"],
        # Keep Human source text and any proposed rewrite separate so a model-authored
        # proposal can never replace the Human quote while retaining HUMAN_CORRECTION.
        "raw_feedback": raw_feedback,
        "source_kind": normalized["source_kind"],
        "proposed_correction": proposed_correction,
        "delta_type": normalized["delta_type"],
        # AI classification is deliberately omitted from durable/retryable transport.
        # The caller reports this omission explicitly; it can never become Human truth.
        "ai_classification": {},
        "draft_id": normalized["draft_id"],
        "plan_fingerprint": normalized["plan_fingerprint"],
        "evidence_bundle_id": normalized["evidence_bundle_id"],
        "run_id": normalized["run_id"],
        "ac_id": normalized["ac_id"],
        "client_context": {
            "client": normalized["client_context"]["client"],
            "session_id": "",
            "message_id": "",
        },
    }


def _default_queue_path() -> Path:
    configured = os.environ.get("AEM_UAC_FEEDBACK_QUEUE", "").strip()
    return (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".aem-guides" / "uac-feedback-queue.jsonl"
    )


@contextlib.contextmanager
def _queue_lock(path: Path):
    """Use the host OS file lock; never steal a lock based on elapsed wall time."""

    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    with contextlib.suppress(OSError):
        os.chmod(lock_path, 0o600)
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    deadline = time.monotonic() + 5.0
    locked = False
    while not locked:
        try:
            handle.seek(0)
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            elif msvcrt is not None:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:  # Defensive: supported CPython hosts provide one of these modules.
                raise FeedbackTransportError("QUEUE_LOCK_UNAVAILABLE", "OS file locking is unavailable")
            locked = True
        except (BlockingIOError, OSError):
            if time.monotonic() >= deadline:
                handle.close()
                raise FeedbackTransportError("QUEUE_BUSY", "feedback retry queue is busy")
            time.sleep(0.02)
    try:
        yield
    finally:
        handle.seek(0)
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        elif msvcrt is not None:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        handle.close()


def _read_queue(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.stat().st_size > MAX_QUEUE_BYTES:
        raise FeedbackTransportError("QUEUE_TOO_LARGE", "feedback retry queue exceeds its safe limit")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FeedbackTransportError(
                "QUEUE_INVALID", f"feedback retry queue has invalid JSON at line {line_number}"
            ) from exc
        if not isinstance(record, dict) or record.get("schema_version") != QUEUE_SCHEMA:
            raise FeedbackTransportError("QUEUE_INVALID", "feedback retry queue schema is invalid")
        records.append(record)
    if len(records) > MAX_QUEUE_RECORDS:
        raise FeedbackTransportError("QUEUE_TOO_LARGE", "feedback retry queue has too many records")
    return records


def _write_queue(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        return
    encoded = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in records)
    if len(encoded.encode("utf-8")) > MAX_QUEUE_BYTES:
        raise FeedbackTransportError("QUEUE_TOO_LARGE", "feedback retry queue exceeds its safe limit")
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        with contextlib.suppress(OSError):
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _queue_capture(
    path: Path, payload: Mapping[str, Any], *, context_fingerprint: str
) -> int:
    safe_payload = queue_safe_capture(payload)
    with _queue_lock(path):
        records = _read_queue(path)
        for position, record in enumerate(records, 1):
            queued = record.get("payload") or {}
            if queued.get("idempotency_key") == safe_payload["idempotency_key"]:
                if (
                    record.get("context_fingerprint") == context_fingerprint
                    and queued == safe_payload
                ):
                    return position
                raise FeedbackTransportError(
                    "QUEUE_IDEMPOTENCY_CONFLICT",
                    "the idempotency key is already queued with different content or context",
                )
        if len(records) >= MAX_QUEUE_RECORDS:
            raise FeedbackTransportError("QUEUE_FULL", "feedback retry queue is full")
        records.append({
            "schema_version": QUEUE_SCHEMA,
            "queued_at": _utc_now(),
            "attempts": 0,
            "context_fingerprint": context_fingerprint,
            "payload": safe_payload,
        })
        _write_queue(path, records)
        return len(records)


def _delivery_result(server: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(server)
    if str(result.get("index_status", "")).upper() == "INDEXED":
        status = "INDEXED"
    elif result.get("persisted") is True:
        status = "SAVED_REMOTE"
    else:
        status = "REMOTE_RESPONSE"
    result["delivery_status"] = status
    result["queued"] = False
    return result


class FeedbackClient:
    """Authenticated HTTP client for the shared Human-feedback ledger."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        *,
        timeout: float = 15.0,
        queue_path: Path | str | None = None,
    ) -> None:
        self.base_url = _normalize_base_url(base_url or os.environ.get("AEM_STUDIO_URL", ""))
        self._token = _personal_token(token or os.environ.get("AEM_STUDIO_TOKEN", ""))
        self._queue_context_fingerprint = hashlib.sha256(
            (self.base_url + "\0" + self._token).encode("utf-8")
        ).hexdigest()
        if timeout <= 0 or timeout > 120:
            raise ValueError("timeout must be between 0 and 120 seconds")
        self.timeout = float(timeout)
        self.queue_path = Path(queue_path).expanduser() if queue_path else _default_queue_path()
        self._opener = urllib.request.build_opener(_NoRedirect())

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        query: Mapping[str, object] | None = None,
    ) -> Any:
        url = self.base_url + path
        if query:
            clean_query = {key: value for key, value in query.items() if value not in {None, ""}}
            if clean_query:
                url += "?" + urllib.parse.urlencode(clean_query)
        body = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "aem-guides-uac-feedback/1",
        }
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            response = self._opener.open(request, timeout=self.timeout)
            with response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            retryable = exc.code in RETRYABLE_HTTP_STATUSES
            raise FeedbackTransportError(
                f"HTTP_{exc.code}",
                f"shared feedback service returned HTTP {exc.code}",
                retryable=retryable,
            ) from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
            raise FeedbackTransportError(
                "NETWORK_ERROR", "shared feedback service is unavailable", retryable=True
            ) from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise FeedbackTransportError("RESPONSE_TOO_LARGE", "shared feedback response is too large")
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FeedbackTransportError("INVALID_RESPONSE", "shared feedback response is not valid JSON") from exc
        if not isinstance(decoded, (dict, list)):
            raise FeedbackTransportError("INVALID_RESPONSE", "shared feedback response has invalid shape")
        return decoded

    def register_draft(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """Register an authored draft. Draft registration is never locally queued."""

        body = normalize_draft_registration(payload)
        response = self._request("POST", f"{API_PREFIX}/drafts", payload=body)
        if not isinstance(response, Mapping):
            raise FeedbackTransportError("INVALID_RESPONSE", "draft response must be an object")
        draft_id = str(response.get("draft_id", "")).strip()
        _clean_identifier(draft_id, "draft_id", required=True, limit=36)
        if response.get("persisted") is not True:
            raise FeedbackTransportError(
                "INVALID_RESPONSE", "draft response did not confirm remote persistence"
            )
        return response

    def capture(self, payload: Mapping[str, Any], *, queue_on_failure: bool = True) -> dict[str, Any]:
        normalized = normalize_capture(payload)
        omitted_fields: list[str] = []
        if normalized["ai_classification"]:
            omitted_fields.append("ai_classification")
        if normalized["client_context"]["session_id"] or normalized["client_context"]["message_id"]:
            omitted_fields.extend(["client_context.session_id", "client_context.message_id"])
        # Redact and minimize BEFORE the first wire attempt.  The exact same DTO and
        # idempotency key can then be replayed after a response-lost ambiguity.
        wire_payload = queue_safe_capture(normalized)
        try:
            if normalized.get("draft") is not None:
                draft = dict(normalized["draft"])
                draft_receipt = self.register_draft({
                    **draft,
                    "tenant_id": normalized["tenant_id"],
                    "jira_key": normalized["jira_key"],
                    "plan_fingerprint": normalized["plan_fingerprint"],
                    "idempotency_key": "capture:" + hashlib.sha256(
                        normalized["idempotency_key"].encode("utf-8")
                    ).hexdigest(),
                    "evidence_bundle_id": (
                        draft["evidence_bundle_id"] or normalized["evidence_bundle_id"]
                    ),
                    "run_id": draft["run_id"] or normalized["run_id"],
                })
                registered_id = str(draft_receipt.get("draft_id", ""))
                if wire_payload["draft_id"] and wire_payload["draft_id"] != registered_id:
                    raise ValueError(
                        "inline draft registration conflicts with the supplied draft_id"
                    )
                wire_payload["draft_id"] = registered_id
            result = self._request("POST", f"{API_PREFIX}/feedback", payload=wire_payload)
        except FeedbackTransportError as exc:
            if not queue_on_failure or not exc.retryable:
                raise
            position = _queue_capture(
                self.queue_path,
                wire_payload,
                context_fingerprint=self._queue_context_fingerprint,
            )
            return {
                "delivery_status": "QUEUED_LOCAL",
                "queued": True,
                "queue_position": position,
                "persisted": False,
                "binding_status": "NOT_SENT",
                "learning_status": "NOT_SENT",
                "index_status": "NOT_SENT",
                "error_code": exc.code,
                "client_omitted_fields": omitted_fields,
                "message": (
                    "A redacted correction was queued locally. It is not saved, bound, "
                    "approved, or indexed until flush succeeds."
                ),
            }
        if not isinstance(result, Mapping):
            raise FeedbackTransportError("INVALID_RESPONSE", "capture response must be an object")
        _clean_identifier(result.get("feedback_id"), "feedback_id", required=True, limit=80)
        if result.get("persisted") is not True:
            raise FeedbackTransportError(
                "INVALID_RESPONSE", "capture response did not confirm remote persistence"
            )
        delivered = _delivery_result(result)
        delivered["client_omitted_fields"] = omitted_fields
        return delivered

    def list_feedback(
        self,
        *,
        tenant_id: str = "kone",
        jira_key: str = "",
        plan_fingerprint: str = "",
        limit: int = 100,
    ) -> Any:
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        tenant_id = _clean_identifier(tenant_id, "tenant_id", required=True, limit=120)
        jira_key = _clean_identifier(jira_key, "jira_key", required=False, limit=64)
        plan_fingerprint = _clean_text(
            plan_fingerprint, "plan_fingerprint", required=False, limit=64
        ).lower()
        if plan_fingerprint and not _HEX_64.fullmatch(plan_fingerprint):
            raise ValueError("plan_fingerprint must be 64 lowercase hexadecimal characters")
        return self._request(
            "GET",
            f"{API_PREFIX}/feedback",
            query={
                "tenant_id": tenant_id,
                "jira_key": jira_key,
                "plan_fingerprint": plan_fingerprint,
                "limit": limit,
            },
        )

    def status(self, feedback_id: str, *, tenant_id: str = "kone") -> Any:
        feedback_id = _clean_identifier(feedback_id, "feedback_id", required=True, limit=80)
        tenant_id = _clean_identifier(tenant_id, "tenant_id", required=True, limit=120)
        return self._request(
            "GET",
            f"{API_PREFIX}/feedback/{urllib.parse.quote(feedback_id, safe='')}",
            query={"tenant_id": tenant_id},
        )

    def bind(
        self,
        feedback_id: str,
        *,
        tenant_id: str,
        draft_id: str,
        idempotency_key: str,
    ) -> Any:
        feedback_id = _clean_identifier(feedback_id, "feedback_id", required=True, limit=80)
        body = {
            "tenant_id": _clean_identifier(tenant_id, "tenant_id", required=True, limit=120),
            "draft_id": _clean_identifier(draft_id, "draft_id", required=True, limit=36),
            "idempotency_key": _clean_text(
                idempotency_key, "idempotency_key", required=True, limit=240
            ),
        }
        return self._request(
            "POST",
            f"{API_PREFIX}/feedback/{urllib.parse.quote(feedback_id, safe='')}/bind",
            payload=body,
        )

    def review(self, feedback_id: str, payload: Mapping[str, Any]) -> Any:
        """Submit a review once. Reviews are deliberately never queued or retried."""

        feedback_id = _clean_identifier(feedback_id, "feedback_id", required=True, limit=80)
        if not isinstance(payload, Mapping):
            raise ValueError("review payload must be an object")
        decision = str(payload.get("decision", "")).upper()
        if decision not in {"APPROVE", "REJECT", "REVOKE", "SUPERSEDE"}:
            raise ValueError("decision must be APPROVE, REJECT, REVOKE, or SUPERSEDE")
        try:
            expected_revision = int(payload.get("expected_revision"))
        except (TypeError, ValueError) as exc:
            raise ValueError("expected_revision must be an integer") from exc
        if expected_revision < 1:
            raise ValueError("expected_revision must be at least 1")
        body: dict[str, Any] = {
            "tenant_id": _clean_identifier(
                payload.get("tenant_id", "kone"), "tenant_id", required=True, limit=120
            ),
            "idempotency_key": _clean_text(
                payload.get("idempotency_key"), "idempotency_key", required=True, limit=240
            ),
            "expected_revision": expected_revision,
            "decision": decision,
            "note": _clean_text(payload.get("note"), "note", required=True, limit=2_000),
            "origin_confirmed": payload.get("origin_confirmed") is True,
            "applicability_confirmed": payload.get("applicability_confirmed") is True,
            "counterexamples_checked": payload.get("counterexamples_checked") is True,
        }
        if payload.get("lesson") is not None:
            if not isinstance(payload["lesson"], Mapping):
                raise ValueError("lesson must be an object")
            body["lesson"] = dict(payload["lesson"])
            scope = body["lesson"].get("scope")
            if isinstance(scope, Mapping) and scope.get("jira_keys"):
                raise ValueError("lesson.scope.jira_keys cannot be a production selector")
        if decision in {"APPROVE", "SUPERSEDE"}:
            if "lesson" not in body:
                raise ValueError(f"{decision} requires a reviewed lesson definition")
            if not all((body["origin_confirmed"], body["applicability_confirmed"],
                        body["counterexamples_checked"])):
                raise ValueError(
                    f"{decision} requires origin, applicability, and counterexample attestations"
                )
        return self._request(
            "POST",
            f"{API_PREFIX}/feedback/{urllib.parse.quote(feedback_id, safe='')}/review",
            payload=body,
        )

    def flush_queue(self, *, max_items: int = 100) -> dict[str, Any]:
        """Replay capture records once; stop and retain records on any failure."""

        if max_items < 1 or max_items > MAX_QUEUE_RECORDS:
            raise ValueError(f"max_items must be between 1 and {MAX_QUEUE_RECORDS}")
        with _queue_lock(self.queue_path):
            records = _read_queue(self.queue_path)
            sent: list[dict[str, Any]] = []
            remaining = list(records)
            blocked: dict[str, Any] | None = None
            for record in records[:max_items]:
                payload = record.get("payload")
                try:
                    if record.get("context_fingerprint") != self._queue_context_fingerprint:
                        raise FeedbackTransportError(
                            "QUEUE_CONTEXT_MISMATCH",
                            "queued feedback belongs to a different service or credential",
                        )
                    normalized = queue_safe_capture(payload if isinstance(payload, Mapping) else {})
                    response = self._request("POST", f"{API_PREFIX}/feedback", payload=normalized)
                    if not isinstance(response, Mapping):
                        raise FeedbackTransportError("INVALID_RESPONSE", "capture response must be an object")
                    feedback_id = _clean_identifier(
                        response.get("feedback_id"),
                        "feedback_id",
                        required=True,
                        limit=80,
                    )
                    if response.get("persisted") is not True:
                        raise FeedbackTransportError(
                            "INVALID_RESPONSE",
                            "capture response did not confirm remote persistence",
                        )
                except (ValueError, FeedbackTransportError) as exc:
                    record["attempts"] = int(record.get("attempts", 0)) + 1
                    record["last_attempt_at"] = _utc_now()
                    record["last_error_code"] = (
                        exc.code if isinstance(exc, FeedbackTransportError) else "LOCAL_VALIDATION_ERROR"
                    )
                    blocked = {
                        "error_code": record["last_error_code"],
                        "retryable": bool(getattr(exc, "retryable", False)),
                    }
                    break
                sent.append({
                    "idempotency_key": normalized["idempotency_key"],
                    "delivery_status": _delivery_result(response)["delivery_status"],
                    "feedback_id": feedback_id,
                })
                remaining.pop(0)
            _write_queue(self.queue_path, remaining)
        return {
            "sent_count": len(sent),
            "sent": sent,
            "remaining_count": len(remaining),
            "blocked": blocked,
            "message": (
                "Queued captures were saved remotely as reported above. Approval was not attempted."
                if sent
                else "No queued capture was saved remotely."
            ),
        }


def _read_json(path: str) -> dict[str, Any]:
    if path == "-":
        raw = __import__("sys").stdin.read()
    else:
        file = Path(path)
        if file.stat().st_size > 500_000:
            raise ValueError("input JSON exceeds 500 KB")
        raw = file.read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("input JSON must be an object")
    return value


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


class _SelfTestHandler(http.server.BaseHTTPRequestHandler):
    calls: list[dict[str, Any]] = []
    fail_capture = False
    invalid_capture = False

    def log_message(self, fmt, *args):  # noqa: ANN001
        return

    def _json(self, status: int, value: object) -> None:
        raw = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        self.__class__.calls.append({"method": "GET", "path": self.path})
        if "/feedback/" in self.path:
            self._json(200, {"feedback_id": "feedback-1", "learning_status": "CANDIDATE"})
        else:
            self._json(200, {"items": []})

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        self.__class__.calls.append({"method": "POST", "path": self.path, "body": body})
        if self.path.endswith("/drafts"):
            self._json(201, {"draft_id": "draft-1", "persisted": True})
        elif self.path.endswith("/feedback") and self.__class__.fail_capture:
            self._json(503, {"detail": "unavailable"})
        elif self.path.endswith("/feedback") and self.__class__.invalid_capture:
            self._json(200, {"feedback_id": "feedback-1", "persisted": False})
        elif self.path.endswith("/review"):
            self._json(200, {"feedback_id": "feedback-1", "learning_status": "APPROVED"})
        elif self.path.endswith("/bind"):
            self._json(200, {"feedback_id": "feedback-1", "binding_status": "BOUND"})
        else:
            self._json(201, {
                "feedback_id": "feedback-1",
                "persisted": True,
                "binding_status": "PENDING_BINDING",
                "learning_status": "PENDING_BINDING",
                "index_status": "SKIPPED",
            })


def run_self_tests() -> None:
    _SelfTestHandler.calls = []
    _SelfTestHandler.fail_capture = False
    _SelfTestHandler.invalid_capture = False
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SelfTestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as temporary:
            queue = Path(temporary) / "queue.jsonl"
            client = FeedbackClient(
                f"http://127.0.0.1:{server.server_port}", "personal-test-token", queue_path=queue
            )
            payload = {
                "jira_key": "TEST-1",
                "idempotency_key": "capture-1",
                "raw_feedback": "Use this Human correction",
                "source_kind": "HUMAN_CORRECTION",
                "proposed_correction": "Use API key=very-secret in the corrected AC",
                "client_context": {"client": "codex", "session_id": "s1"},
                "draft": {"draft_markdown": "full draft must not be queued"},
            }
            saved = client.capture(payload)
            assert saved["delivery_status"] == "SAVED_REMOTE" and not saved["queued"]

            registered = client.register_draft({
                "jira_key": "TEST-1",
                "idempotency_key": "draft-direct-1",
                "draft_markdown": "AC-01: A directly registered criterion.",
                "criteria": {"AC-01": "A directly registered criterion."},
                "client_context": {"client": "claude_desktop"},
            })
            assert registered["draft_id"] == "draft-1"

            _SelfTestHandler.fail_capture = True
            queued = client.capture({**payload, "idempotency_key": "capture-2"})
            assert queued["delivery_status"] == "QUEUED_LOCAL"
            raw_queue = queue.read_text(encoding="utf-8")
            assert "very-secret" not in raw_queue
            assert "full draft" not in raw_queue
            assert "personal-test-token" not in raw_queue
            queued_record = json.loads(raw_queue)["payload"]
            assert "draft" not in queued_record and queued_record["ai_classification"] == {}
            assert queued_record["raw_feedback"] == "Use this Human correction"
            assert queued_record["proposed_correction"].endswith(
                "[REDACTED] in the corrected AC"
            )
            failed_wire = next(
                call["body"] for call in reversed(_SelfTestHandler.calls)
                if call["path"].endswith("/feedback")
            )
            assert failed_wire == queued_record, "queued replay DTO must match the first wire attempt"

            # Duplicate capture idempotency keys do not create duplicate queue records.
            client.capture({**payload, "idempotency_key": "capture-2"})
            assert len(queue.read_text(encoding="utf-8").splitlines()) == 1
            try:
                client.capture({
                    **payload,
                    "idempotency_key": "capture-2",
                    "raw_feedback": "A materially different correction",
                    "proposed_correction": "A materially different correction",
                })
            except FeedbackTransportError as exc:
                assert exc.code == "QUEUE_IDEMPOTENCY_CONFLICT"
            else:
                raise AssertionError("same idempotency key with different content must conflict")

            other_identity = FeedbackClient(
                f"http://127.0.0.1:{server.server_port}",
                "another-personal-token",
                queue_path=queue,
            )
            context_blocked = other_identity.flush_queue()
            assert context_blocked["sent_count"] == 0
            assert context_blocked["remaining_count"] == 1
            assert context_blocked["blocked"]["error_code"] == "QUEUE_CONTEXT_MISMATCH"

            _SelfTestHandler.fail_capture = False
            flushed = client.flush_queue()
            assert flushed["sent_count"] == 1 and flushed["remaining_count"] == 0
            assert not queue.exists()
            replayed_wire = next(
                call["body"] for call in reversed(_SelfTestHandler.calls)
                if call["path"].endswith("/feedback")
            )
            assert replayed_wire == failed_wire, "response-lost replay must preserve source hash"

            _SelfTestHandler.fail_capture = True
            client.capture({**payload, "idempotency_key": "capture-3"})
            _SelfTestHandler.fail_capture = False
            _SelfTestHandler.invalid_capture = True
            invalid = client.flush_queue()
            assert invalid["sent_count"] == 0 and invalid["remaining_count"] == 1
            assert invalid["blocked"]["error_code"] == "INVALID_RESPONSE"
            _SelfTestHandler.invalid_capture = False
            assert client.flush_queue()["remaining_count"] == 0

            client.list_feedback(jira_key="TEST-1", limit=10)
            client.status("feedback-1")
            client.bind(
                "feedback-1", tenant_id="kone", draft_id="draft-1", idempotency_key="bind-1"
            )
            review = client.review("feedback-1", {
                "idempotency_key": "review-1",
                "expected_revision": 1,
                "decision": "APPROVE",
                "note": "Verified against the bound Human correction and counterexamples.",
                "origin_confirmed": True,
                "applicability_confirmed": True,
                "counterexamples_checked": True,
                "lesson": {"guidance": "Investigate the shared behavior."},
            })
            assert review["learning_status"] == "APPROVED"
            assert not queue.exists(), "reviews must never enter the capture retry queue"

            try:
                FeedbackClient("http://127.0.0.1:1", "dev-bypass", queue_path=queue)
            except ValueError as exc:
                assert "personal token" in str(exc)
            else:
                raise AssertionError("dev-bypass must be rejected")

            permanent = FeedbackClient(
                f"http://127.0.0.1:{server.server_port}", "personal-test-token", queue_path=queue
            )
            try:
                permanent.capture({"jira_key": "TEST-1", "raw_feedback": "missing idempotency"})
            except ValueError:
                pass
            else:
                raise AssertionError("invalid captures must fail before network/queue")
            assert not queue.exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    print("feedback_capture self-tests: PASS")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--queue-path", type=Path, default=None)
    parser.add_argument("--self-test", action="store_true")
    sub = parser.add_subparsers(dest="command")

    capture = sub.add_parser("capture", help="capture a Human correction from a JSON file or stdin")
    capture.add_argument("--input", required=True, help="capture DTO JSON path, or - for stdin")
    capture.add_argument("--no-queue", action="store_true")

    draft = sub.add_parser("register-draft", help="register an authored draft before feedback")
    draft.add_argument("--input", required=True, help="draft registration JSON path, or - for stdin")

    listing = sub.add_parser("list", help="list feedback visible to the authenticated user")
    listing.add_argument("--tenant-id", default="kone")
    listing.add_argument("--jira-key", default="")
    listing.add_argument("--plan-fingerprint", default="")
    listing.add_argument("--limit", type=int, default=100)

    status = sub.add_parser("status", help="read one feedback item and its real server status")
    status.add_argument("--feedback-id", required=True)
    status.add_argument("--tenant-id", default="kone")

    bind = sub.add_parser("bind", help="bind pending feedback after a draft is registered")
    bind.add_argument("--feedback-id", required=True)
    bind.add_argument("--tenant-id", default="kone")
    bind.add_argument("--draft-id", required=True)
    bind.add_argument("--idempotency-key", required=True)

    review = sub.add_parser("review", help="submit a named Human review once; never queued")
    review.add_argument("--feedback-id", required=True)
    review.add_argument("--input", required=True, help="review DTO JSON path, or - for stdin")

    flush = sub.add_parser("flush-queue", help="retry queued captures only")
    flush.add_argument("--max-items", type=int, default=100)

    args = parser.parse_args(argv)
    if args.self_test:
        run_self_tests()
        return 0
    if not args.command:
        parser.error("a command or --self-test is required")
    try:
        client = FeedbackClient(
            args.base_url, timeout=args.timeout, queue_path=args.queue_path
        )
        if args.command == "capture":
            result = client.capture(_read_json(args.input), queue_on_failure=not args.no_queue)
        elif args.command == "register-draft":
            result = client.register_draft(_read_json(args.input))
        elif args.command == "list":
            result = client.list_feedback(
                tenant_id=args.tenant_id,
                jira_key=args.jira_key,
                plan_fingerprint=args.plan_fingerprint,
                limit=args.limit,
            )
        elif args.command == "status":
            result = client.status(args.feedback_id, tenant_id=args.tenant_id)
        elif args.command == "bind":
            result = client.bind(
                args.feedback_id,
                tenant_id=args.tenant_id,
                draft_id=args.draft_id,
                idempotency_key=args.idempotency_key,
            )
        elif args.command == "review":
            result = client.review(args.feedback_id, _read_json(args.input))
        else:
            result = client.flush_queue(max_items=args.max_items)
    except (OSError, ValueError, json.JSONDecodeError, FeedbackTransportError) as exc:
        code = exc.code if isinstance(exc, FeedbackTransportError) else "CLIENT_ERROR"
        _print_json({"ok": False, "error_code": code, "message": redact_text(exc, limit=500)})
        return 2
    _print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
