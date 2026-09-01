"""Isolated FluffyJaws API/SSE knowledge provider.

This module deliberately has no runtime registration or environment-variable
loading.  A caller must explicitly enable the provider and inject an HTTP
transport whose client owns authentication and token lifecycle.  The public
FluffyJaws API does not currently define a stable per-answer citation schema,
so streamed answer text is retained only as supporting discovery synthesis;
it is never converted into a canonical evidence hit here.
"""

from __future__ import annotations

import json
import logging
import math
import re
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Protocol
from uuid import uuid4

import httpx
from pydantic import ValidationError

from app.core.schemas_canonical_test_plan_runtime import (
    EvidenceSourceType,
    stable_sha256,
)

from app.services.reasoning_evidence_provider import (
    DiscoverySynthesis,
    EvidenceProviderCancelled,
    EvidenceProviderDescriptor,
    EvidenceProviderExecutionContext,
    EvidenceProviderInvalidResponse,
    EvidenceProviderRawResult,
    EvidenceProviderTimeout,
    EvidenceQueryV1,
    ProviderCacheState,
    ProviderTransportOutcome,
    StrictProviderHit,
    active_query_filters,
)


_PROVIDER_NAME = "fluffyjaws"
_PROVIDER_CONTRACT_VERSION = "api-v1-sse"
_DEFAULT_BASE_URL = "https://api.fluffyjaws.adobe.com"
_STREAM_PATH = "/api/v1/stream"
_DEFAULT_STREAM_URL = f"{_DEFAULT_BASE_URL}{_STREAM_PATH}"
_DEFAULT_TIMEOUT_SECONDS = 300.0
_DEFAULT_MAX_RESPONSE_CHARS = 100_000
_DEFAULT_MAX_EVENT_CHARS = 256_000
_DEFAULT_MAX_SSE_EVENTS = 10_000
_DEFAULT_MAX_STREAM_CHARS = 2_000_000
_STREAM_CHUNK_BYTES = 64 * 1024
_MAX_DIAGNOSTIC_CHARS = 500
_MAX_DECODED_EVIDENCE_HITS = 100
_SOURCE_SHAPED_KEYS = frozenset(
    {
        "annotation",
        "annotations",
        "citation",
        "citations",
        "document",
        "documents",
        "source",
        "sources",
        "source_uri",
        "source_url",
        "uri",
        "url",
    }
)

_SENSITIVE_FIELD_RE = re.compile(
    r"(?i)(authorization|cookie|set-cookie|client[_-]?secret|access[_-]?token|"
    r"refresh[_-]?token|id[_-]?token|api[_-]?key|password|session)\s*[:=]\s*"
    r"(?:bearer\s+)?(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_AUTHORIZATION_FIELD_RE = re.compile(
    r"(?im)\b(authorization|proxy[_-]?authorization)\b[\"']?\s*[:=]\s*[^\r\n]+"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{4,}")
_URL_CREDENTIAL_RE = re.compile(r"(?i)(https?://)[^/@\s:]+:[^/@\s]+@")

logger = logging.getLogger(__name__)


class FluffyJawsFailureCode(str, Enum):
    """Allowlisted, non-secret provider diagnostic codes."""

    INVALID_RESPONSE = "invalid_response"
    AUTH_ERROR = "auth_error"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"
    STREAM_INTERRUPTED = "stream_interrupted"
    RESPONSE_TOO_LARGE = "response_too_large"


@dataclass(frozen=True)
class FluffyJawsProviderError:
    """Structured and redacted error safe for provider traces."""

    code: FluffyJawsFailureCode
    message: str
    retryable: bool = False
    required_action: str = ""
    upstream_code: str = ""
    http_status: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "message", _redact_text(self.message))
        object.__setattr__(
            self,
            "required_action",
            _redact_text(self.required_action),
        )
        object.__setattr__(
            self,
            "upstream_code",
            _safe_upstream_code(self.upstream_code),
        )


class FluffyJawsProviderDisabledError(RuntimeError):
    """Raised when a disabled adapter is called outside provider selection."""


class FluffyJawsProviderCancelled(EvidenceProviderCancelled):
    """Cooperative cancellation signal; never normalized as provider failure."""


@dataclass(frozen=True)
class FluffyJawsProviderConfig:
    """Non-secret configuration; default-off is the mandatory kill switch."""

    enabled: bool = False
    base_url: str = _DEFAULT_BASE_URL
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
    max_response_chars: int = _DEFAULT_MAX_RESPONSE_CHARS
    max_event_chars: int = _DEFAULT_MAX_EVENT_CHARS
    max_sse_events: int = _DEFAULT_MAX_SSE_EVENTS
    max_stream_chars: int = _DEFAULT_MAX_STREAM_CHARS
    fluffy_pack_slug: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None

    def __post_init__(self) -> None:
        base_url = self.base_url.strip().rstrip("/")
        if base_url != _DEFAULT_BASE_URL:
            raise ValueError("FluffyJaws base_url must use the approved API origin")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("FluffyJaws timeout_seconds must be finite and positive")
        if not 1 <= self.max_response_chars <= 500_000:
            raise ValueError(
                "FluffyJaws max_response_chars must be between 1 and 500000"
            )
        if not 1 <= self.max_event_chars <= 1_000_000:
            raise ValueError(
                "FluffyJaws max_event_chars must be between 1 and 1000000"
            )
        if not 1 <= self.max_sse_events <= 100_000:
            raise ValueError(
                "FluffyJaws max_sse_events must be between 1 and 100000"
            )
        if not 1 <= self.max_stream_chars <= 10_000_000:
            raise ValueError(
                "FluffyJaws max_stream_chars must be between 1 and 10000000"
            )
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(
            self,
            "fluffy_pack_slug",
            _bounded_optional_text(
                self.fluffy_pack_slug,
                field_name="fluffy_pack_slug",
            ),
        )
        object.__setattr__(
            self,
            "model",
            _bounded_optional_text(self.model, field_name="model"),
        )
        object.__setattr__(
            self,
            "reasoning_effort",
            _bounded_optional_text(
                self.reasoning_effort,
                field_name="reasoning_effort",
            ),
        )

    @property
    def stream_url(self) -> str:
        return f"{self.base_url}{_STREAM_PATH}"


@dataclass(frozen=True)
class FluffyJawsStreamRequest:
    """Bounded transport request; correlation remains local, not an API field."""

    url: str
    json_body: Mapping[str, Any]
    timeout_seconds: float
    correlation_id: str


class FluffyJawsStreamResponse(Protocol):
    """Small response surface used by the deterministic SSE parser."""

    status_code: int

    def iter_bytes(self, chunk_size: int) -> Iterable[bytes]: ...


class FluffyJawsTransport(Protocol):
    """Injected transport. Its client owns authorization and token lifecycle."""

    def stream(
        self,
        request: FluffyJawsStreamRequest,
    ) -> AbstractContextManager[FluffyJawsStreamResponse]: ...


@dataclass(frozen=True)
class FluffyJawsDecodedEvidence:
    """Contract-decoder output independent of any FluffyJaws wire shape."""

    hits: tuple[StrictProviderHit | Mapping[str, Any], ...] = ()
    synthesis_hit_references: tuple[str, ...] = ()


class FluffyJawsCitationDecoder(Protocol):
    """Future citation-contract hook; no wire fields are assumed here."""

    contract_version: str
    supported_source_types: tuple[EvidenceSourceType, ...]

    def decode(
        self,
        events: tuple[Mapping[str, Any], ...],
        *,
        final_response_id: str,
    ) -> FluffyJawsDecodedEvidence: ...


class HttpxFluffyJawsTransport:
    """Documented HTTPS transport using an explicitly injected HTTP client.

    The injected client must already be configured with approved authentication.
    This class never reads credentials, environment variables, cookies, or CLI
    sessions and never logs request headers.
    """

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def stream(
        self,
        request: FluffyJawsStreamRequest,
    ) -> AbstractContextManager[httpx.Response]:
        if request.url != _DEFAULT_STREAM_URL:
            raise ValueError("FluffyJaws transport requires the approved stream URL")
        if (
            not math.isfinite(request.timeout_seconds)
            or request.timeout_seconds <= 0
        ):
            raise ValueError("FluffyJaws transport timeout must be finite and positive")
        return self._client.stream(
            "POST",
            request.url,
            headers={
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
            },
            json=dict(request.json_body),
            timeout=httpx.Timeout(request.timeout_seconds),
            follow_redirects=False,
        )


@dataclass(frozen=True)
class _ParsedStream:
    text: str
    final_response_id: str
    completed: bool
    done: bool
    restarted_count: int
    iteration_limited: bool
    source_metadata_quarantined: bool
    events: tuple[Mapping[str, Any], ...]
    error: FluffyJawsProviderError | None = None


class FluffyJawsKnowledgeProvider:
    """Default-disabled discovery-only implementation of the public API contract."""

    def __init__(
        self,
        *,
        config: FluffyJawsProviderConfig | None = None,
        transport: FluffyJawsTransport,
        citation_decoder: FluffyJawsCitationDecoder | None = None,
        now: Callable[[], datetime] | None = None,
        call_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.config = config or FluffyJawsProviderConfig()
        self._transport = transport
        self._citation_decoder = citation_decoder
        self._provider_contract_version_value = _PROVIDER_CONTRACT_VERSION
        if citation_decoder is not None:
            decoder_version = _safe_upstream_code(citation_decoder.contract_version)
            if not decoder_version:
                raise ValueError(
                    "FluffyJaws citation decoder contract version is invalid"
                )
            provider_contract_version = (
                f"{_PROVIDER_CONTRACT_VERSION}+{decoder_version}"
            )
            if len(provider_contract_version) > 80:
                raise ValueError(
                    "FluffyJaws provider contract version exceeds 80 characters"
                )
            self._provider_contract_version_value = provider_contract_version
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._call_id_factory = call_id_factory or (lambda: str(uuid4()))

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def descriptor(self) -> EvidenceProviderDescriptor:
        # No source type is advertised unless a separately supplied,
        # contract-versioned decoder owns that mapping.
        configuration_digest = stable_sha256(
            {
                "provider_contract_version": self._provider_contract_version(),
                "base_url": self.config.base_url,
                "timeout_seconds": self.config.timeout_seconds,
                "max_response_chars": self.config.max_response_chars,
                "max_event_chars": self.config.max_event_chars,
                "max_sse_events": self.config.max_sse_events,
                "max_stream_chars": self.config.max_stream_chars,
                "fluffy_pack_slug": self.config.fluffy_pack_slug,
                "model": self.config.model,
                "reasoning_effort": self.config.reasoning_effort,
            }
        )
        return EvidenceProviderDescriptor(
            provider=_PROVIDER_NAME,
            adapter_version="1.0.0",
            provider_contract_version=self._provider_contract_version(),
            supported_domains=(),
            supported_source_types=(
                list(self._citation_decoder.supported_source_types)
                if self._citation_decoder is not None
                else []
            ),
            supports_discovery_synthesis=True,
            supported_filters=(
                ["max_results"] if self._citation_decoder is not None else []
            ),
            maximum_results=100 if self._citation_decoder is not None else 1,
            configuration_digest=configuration_digest,
        )

    def retrieve(
        self,
        query: EvidenceQueryV1,
        context: EvidenceProviderExecutionContext,
    ) -> EvidenceProviderRawResult:
        if not self.enabled:
            raise FluffyJawsProviderDisabledError(
                "FluffyJaws provider is disabled by configuration"
            )

        _raise_if_stopped(context)
        started_at = self._now()
        provider_call_id = self._call_id_factory()
        request = FluffyJawsStreamRequest(
            url=self.config.stream_url,
            json_body=self._request_body(query),
            timeout_seconds=max(
                0.001,
                min(self.config.timeout_seconds, context.remaining_seconds()),
            ),
            correlation_id=context.correlation_id,
        )

        outcome = ProviderTransportOutcome.COMPLETED
        error: FluffyJawsProviderError | None = None
        parsed: _ParsedStream | None = None
        try:
            with self._transport.stream(request) as response:
                _raise_if_stopped(context)
                error = _http_error(response.status_code)
                if error is None:
                    bounded_lines = _iter_bounded_sse_lines(
                        response.iter_bytes(
                            chunk_size=min(
                                _STREAM_CHUNK_BYTES,
                                self.config.max_event_chars,
                                self.config.max_stream_chars,
                            )
                        ),
                        max_line_bytes=self.config.max_event_chars,
                        max_stream_bytes=self.config.max_stream_chars,
                        cancellation_check=lambda: _raise_if_stopped(context),
                    )
                    parsed = _parse_stream(
                        bounded_lines,
                        max_response_chars=self.config.max_response_chars,
                        max_event_chars=self.config.max_event_chars,
                        max_sse_events=self.config.max_sse_events,
                        max_stream_chars=self.config.max_stream_chars,
                        capture_events=self._citation_decoder is not None,
                        cancellation_check=lambda: _raise_if_stopped(context),
                    )
                    error = parsed.error
            _raise_if_stopped(context)
        except FluffyJawsProviderCancelled:
            raise
        except EvidenceProviderTimeout:
            raise
        except EvidenceProviderInvalidResponse:
            raise
        except UnicodeDecodeError:
            raise EvidenceProviderInvalidResponse(
                "FluffyJaws stream was not valid UTF-8",
                error_code=FluffyJawsFailureCode.INVALID_RESPONSE.value,
            ) from None
        except httpx.TimeoutException:
            outcome = ProviderTransportOutcome.TIMEOUT
            error = FluffyJawsProviderError(
                code=FluffyJawsFailureCode.TIMEOUT,
                message="FluffyJaws request timed out",
                retryable=True,
            )
        except (httpx.TransportError, OSError):
            outcome = ProviderTransportOutcome.PROVIDER_ERROR
            error = FluffyJawsProviderError(
                code=FluffyJawsFailureCode.STREAM_INTERRUPTED,
                message="FluffyJaws stream was interrupted",
                retryable=True,
            )
        except Exception:
            outcome = ProviderTransportOutcome.PROVIDER_ERROR
            error = FluffyJawsProviderError(
                code=FluffyJawsFailureCode.PROVIDER_ERROR,
                message="FluffyJaws provider failed",
                retryable=False,
            )

        if error is not None:
            outcome = _transport_outcome_for(error, fallback=outcome)
        iteration_limited = bool(parsed and parsed.iteration_limited)
        if iteration_limited and error is None:
            outcome = ProviderTransportOutcome.PROVIDER_ERROR
        if error is not None and error.code in {
            FluffyJawsFailureCode.INVALID_RESPONSE,
            FluffyJawsFailureCode.RESPONSE_TOO_LARGE,
        }:
            raise EvidenceProviderInvalidResponse(
                error.message,
                error_code=error.code.value,
                retryable=error.retryable,
            )
        completed_at = self._now()
        duration_ms = max(
            0,
            int((completed_at - started_at).total_seconds() * 1000),
        )

        raw_hits: list[StrictProviderHit] = []
        synthesis_hit_references: list[str] = []
        decoded_truncated = False
        if parsed is not None and error is None and self._citation_decoder is not None:
            try:
                decoded = self._citation_decoder.decode(
                    parsed.events,
                    final_response_id=parsed.final_response_id,
                )
                _raise_if_stopped(context)
                if not isinstance(decoded, FluffyJawsDecodedEvidence):
                    raise TypeError("decoder result must use FluffyJawsDecodedEvidence")
                for index, item in enumerate(decoded.hits):
                    _raise_if_stopped(context)
                    # Keep the adapter's hard safety bound here, but leave the
                    # query result budget to EvidenceProviderExecutor.  It can
                    # apply that budget after normalization and deterministic
                    # dedupe; applying it here can discard a later unique hit
                    # when earlier decoder rows describe the same evidence.
                    if index >= _MAX_DECODED_EVIDENCE_HITS:
                        decoded_truncated = True
                        break
                    raw_hits.append(StrictProviderHit.model_validate(item))
                decoded_references = {
                    reference.strip()
                    for reference in decoded.synthesis_hit_references
                    if isinstance(reference, str) and reference.strip()
                }
                if len(decoded_references) != len(
                    set(decoded.synthesis_hit_references)
                ):
                    raise ValueError("decoder synthesis references are invalid")
                accepted_references = {
                    hit.raw_provider_reference for hit in raw_hits
                }
                if (
                    not decoded_truncated
                    and not decoded_references.issubset(accepted_references)
                ):
                    raise ValueError("decoder synthesis references an unknown hit")
                synthesis_hit_references = sorted(
                    decoded_references & accepted_references
                )
            except (FluffyJawsProviderCancelled, EvidenceProviderTimeout):
                raise
            except (ValidationError, ValueError, TypeError):
                raise EvidenceProviderInvalidResponse(
                    "FluffyJaws citation decoder returned an invalid source",
                    error_code=FluffyJawsFailureCode.INVALID_RESPONSE.value,
                ) from None
            except Exception:
                raise EvidenceProviderInvalidResponse(
                    "FluffyJaws citation decoder failed",
                    error_code=FluffyJawsFailureCode.INVALID_RESPONSE.value,
                ) from None

        provider_contract_version = self._provider_contract_version()
        syntheses: tuple[DiscoverySynthesis, ...] = ()
        synthesis_truncated = False
        if parsed is not None and error is None and parsed.text:
            synthesis_truncated = len(parsed.text) > 100_000
            syntheses = (
                DiscoverySynthesis(
                    provider=_PROVIDER_NAME,
                    provider_contract_version=provider_contract_version,
                    provider_call_id=provider_call_id,
                    query_id=query.query_id,
                    correlation_id=context.correlation_id,
                    text=_redact_text(
                        parsed.text,
                        limit=min(self.config.max_response_chars, 100_000),
                    ),
                    derived_from=[],
                    raw_provider_reference=parsed.final_response_id,
                ),
            )
        synthesis_links = (
            {syntheses[0].synthesis_id: synthesis_hit_references}
            if syntheses and synthesis_hit_references
            else {}
        )

        safe_code = (
            (error.upstream_code or error.code.value)
            if error is not None
            else "iteration_limit_reached"
            if iteration_limited
            else ""
        )
        safe_message = (
            error.message
            if error is not None
            else "FluffyJaws iteration limit reached"
            if iteration_limited
            else ""
        )
        retryable = error.retryable if error is not None else False
        result = EvidenceProviderRawResult(
            provider=_PROVIDER_NAME,
            provider_contract_version=provider_contract_version,
            provider_call_id=provider_call_id,
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            raw_hits=raw_hits,
            discovery_syntheses=list(syntheses),
            discovery_synthesis_hit_references=synthesis_links,
            transport_outcome=outcome,
            applied_filters=(
                ["max_results"] if self._citation_decoder is not None else []
            ),
            unsupported_filters=_unsupported_provider_filters(
                query,
                supports_max_results=self._citation_decoder is not None,
            ),
            attempts=1,
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            duration_ms=duration_ms,
            truncated=bool(
                synthesis_truncated or (parsed and parsed.iteration_limited)
                or decoded_truncated
            ),
            cache_state=ProviderCacheState.BYPASS,
            retryable=retryable,
            redacted_error_code=safe_code,
            redacted_message=safe_message,
            redacted_required_action=(
                error.required_action if error is not None else ""
            ),
            raw_provider_reference=(
                parsed.final_response_id
                if parsed is not None and error is None
                else ""
            ),
        )
        _log_result(result, source_metadata_quarantined=bool(
            parsed and parsed.source_metadata_quarantined
        ))
        return result

    def _provider_contract_version(self) -> str:
        return self._provider_contract_version_value

    def _request_body(self, query: EvidenceQueryV1) -> dict[str, Any]:
        body: dict[str, Any] = {
            "messages": [
                {
                    "role": "user",
                    "content": _redact_text(
                        query.question,
                        limit=max(1, len(query.question)),
                    ),
                }
            ],
        }
        if self.config.fluffy_pack_slug:
            body["fluffyPackSlug"] = self.config.fluffy_pack_slug
        if self.config.model:
            body["model"] = self.config.model
        if self.config.reasoning_effort:
            body["reasoningEffort"] = self.config.reasoning_effort
        return body


def _parse_stream(
    lines: Iterable[str],
    *,
    max_response_chars: int,
    max_event_chars: int,
    max_sse_events: int,
    max_stream_chars: int = _DEFAULT_MAX_STREAM_CHARS,
    capture_events: bool = False,
    cancellation_check: Callable[[], None],
) -> _ParsedStream:
    fragments: list[str] = []
    total_chars = 0
    final_response_id = ""
    completed = False
    done = False
    restarted_count = 0
    iteration_limited = False
    source_metadata_quarantined = False
    event_count = 0
    events: list[Mapping[str, Any]] = []

    for data in _iter_sse_data(
        lines,
        max_event_chars=max_event_chars,
        max_stream_chars=max_stream_chars,
        cancellation_check=cancellation_check,
    ):
        cancellation_check()
        if data is None:
            return _invalid_stream(
                "FluffyJaws SSE event limit was exceeded",
                code=FluffyJawsFailureCode.RESPONSE_TOO_LARGE,
                source_metadata_quarantined=source_metadata_quarantined,
            )
        event_count += 1
        if (
            event_count > max_sse_events
            or len(data) > max_event_chars
        ):
            return _invalid_stream(
                "FluffyJaws SSE event limit was exceeded",
                code=FluffyJawsFailureCode.RESPONSE_TOO_LARGE,
                source_metadata_quarantined=source_metadata_quarantined,
            )
        if data == "[DONE]":
            if done:
                return _invalid_stream(
                    "FluffyJaws stream repeated its terminal marker",
                    source_metadata_quarantined=source_metadata_quarantined,
                )
            done = True
            continue
        if done:
            return _invalid_stream(
                "FluffyJaws stream emitted data after its terminal marker",
                source_metadata_quarantined=source_metadata_quarantined,
            )
        try:
            event = json.loads(data)
        except (TypeError, json.JSONDecodeError):
            return _invalid_stream(
                "Malformed JSON in FluffyJaws SSE event",
                source_metadata_quarantined=source_metadata_quarantined,
            )
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            return _invalid_stream(
                "Malformed FluffyJaws SSE event envelope",
                source_metadata_quarantined=source_metadata_quarantined,
            )

        event_type = event["type"]
        if completed:
            return _invalid_stream(
                "FluffyJaws stream emitted an event after completion",
                source_metadata_quarantined=source_metadata_quarantined,
            )
        source_metadata_quarantined = (
            source_metadata_quarantined or _contains_source_shaped_metadata(event)
        )
        if event_type == "stream_restarted":
            events.clear()
        elif capture_events:
            events.append(event)

        if event_type == "response.output_text.delta":
            delta = event.get("delta")
            if not isinstance(delta, str):
                return _invalid_stream(
                    "Malformed FluffyJaws text delta",
                    source_metadata_quarantined=source_metadata_quarantined,
                )
            total_chars += len(delta)
            if total_chars > max_response_chars:
                return _invalid_stream(
                    "FluffyJaws response exceeded the configured size limit",
                    code=FluffyJawsFailureCode.RESPONSE_TOO_LARGE,
                    source_metadata_quarantined=source_metadata_quarantined,
                )
            fragments.append(delta)
        elif event_type == "stream_restarted":
            fragments.clear()
            total_chars = 0
            final_response_id = ""
            completed = False
            restarted_count += 1
            iteration_limited = False
        elif event_type == "response.completed":
            response_id = event.get("response_id")
            if not isinstance(response_id, str) or not response_id.strip():
                return _invalid_stream(
                    "FluffyJaws completion did not include a final response ID",
                    source_metadata_quarantined=source_metadata_quarantined,
                )
            final_response_id = _opaque_reference(response_id)
            if not final_response_id:
                return _invalid_stream(
                    "FluffyJaws completion response ID was not safe to retain",
                    source_metadata_quarantined=source_metadata_quarantined,
                )
            completed = True
        elif event_type == "error":
            message = event.get("message")
            upstream_code = event.get("code", "")
            retryable_value = event.get("retryable", False)
            required_action = event.get("required_action", "")
            if (
                not isinstance(message, str)
                or not isinstance(upstream_code, str)
                or not isinstance(retryable_value, bool)
                or not isinstance(required_action, str)
            ):
                return _invalid_stream(
                    "Malformed FluffyJaws error event",
                    source_metadata_quarantined=source_metadata_quarantined,
                )
            return _ParsedStream(
                text="",
                final_response_id="",
                completed=False,
                done=False,
                restarted_count=restarted_count,
                iteration_limited=iteration_limited,
                source_metadata_quarantined=source_metadata_quarantined,
                events=tuple(events),
                error=FluffyJawsProviderError(
                    code=FluffyJawsFailureCode.PROVIDER_ERROR,
                    message="FluffyJaws stream reported an error",
                    upstream_code=upstream_code,
                    retryable=retryable_value,
                    required_action=(
                        "resend_full_history"
                        if required_action == "resend_full_history"
                        else ""
                    ),
                ),
            )
        elif event_type == "iteration_limit_reached":
            iteration_limited = True
        # response.created is provisional. Other documented tool/progress events
        # and unspecified response.* progress events are intentionally ignored.

    if not completed or not done:
        return _invalid_stream(
            "FluffyJaws stream ended before its completion contract",
            source_metadata_quarantined=source_metadata_quarantined,
        )
    return _ParsedStream(
        text="".join(fragments),
        final_response_id=final_response_id,
        completed=True,
        done=True,
        restarted_count=restarted_count,
        iteration_limited=iteration_limited,
        source_metadata_quarantined=source_metadata_quarantined,
        events=tuple(events),
    )


def _iter_bounded_sse_lines(
    chunks: Iterable[bytes],
    *,
    max_line_bytes: int,
    max_stream_bytes: int,
    cancellation_check: Callable[[], None],
) -> Iterable[bytes]:
    """Frame SSE lines from bounded raw chunks before text decoding."""

    buffer = bytearray()
    total_bytes = 0
    for raw_chunk in chunks:
        cancellation_check()
        if not isinstance(raw_chunk, bytes):
            raise EvidenceProviderInvalidResponse(
                "FluffyJaws transport returned a non-byte stream chunk",
                error_code=FluffyJawsFailureCode.INVALID_RESPONSE.value,
            )
        total_bytes += len(raw_chunk)
        if total_bytes > max_stream_bytes:
            raise EvidenceProviderInvalidResponse(
                "FluffyJaws stream exceeded the configured total size limit",
                error_code=FluffyJawsFailureCode.RESPONSE_TOO_LARGE.value,
            )

        start = 0
        while True:
            newline = raw_chunk.find(b"\n", start)
            if newline < 0:
                tail = raw_chunk[start:]
                if len(buffer) + len(tail) > max_line_bytes:
                    raise EvidenceProviderInvalidResponse(
                        "FluffyJaws stream line exceeded the configured size limit",
                        error_code=FluffyJawsFailureCode.RESPONSE_TOO_LARGE.value,
                    )
                buffer.extend(tail)
                break

            piece = raw_chunk[start:newline]
            if len(buffer) + len(piece) > max_line_bytes:
                raise EvidenceProviderInvalidResponse(
                    "FluffyJaws stream line exceeded the configured size limit",
                    error_code=FluffyJawsFailureCode.RESPONSE_TOO_LARGE.value,
                )
            buffer.extend(piece)
            if buffer.endswith(b"\r"):
                del buffer[-1:]
            yield bytes(buffer)
            buffer.clear()
            start = newline + 1

    if buffer:
        if buffer.endswith(b"\r"):
            del buffer[-1:]
        yield bytes(buffer)


def _iter_sse_data(
    lines: Iterable[str],
    *,
    max_event_chars: int,
    max_stream_chars: int,
    cancellation_check: Callable[[], None],
) -> Iterable[str | None]:
    data_lines: list[str] = []
    event_chars = 0
    stream_chars = 0
    for raw_line in lines:
        cancellation_check()
        if isinstance(raw_line, bytes):
            line_size = len(raw_line)
            if line_size > max_event_chars:
                yield None
                return
            line = raw_line.decode("utf-8")
        else:
            line = str(raw_line)
            if len(line) > max_event_chars:
                yield None
                return
            line_size = len(line.encode("utf-8"))
        if line_size > max_event_chars:
            yield None
            return
        stream_chars += line_size + 1
        if stream_chars > max_stream_chars:
            yield None
            return
        if not line:
            if data_lines:
                yield "\n".join(data_lines)
                data_lines.clear()
                event_chars = 0
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            value = line[5:]
            if value.startswith(" "):
                value = value[1:]
            event_chars += len(value) + (1 if data_lines else 0)
            if event_chars > max_event_chars:
                yield None
                return
            data_lines.append(value)
    if data_lines:
        yield "\n".join(data_lines)


def _invalid_stream(
    message: str,
    *,
    code: FluffyJawsFailureCode = FluffyJawsFailureCode.INVALID_RESPONSE,
    source_metadata_quarantined: bool,
) -> _ParsedStream:
    return _ParsedStream(
        text="",
        final_response_id="",
        completed=False,
        done=False,
        restarted_count=0,
        iteration_limited=False,
        source_metadata_quarantined=source_metadata_quarantined,
        events=(),
        error=FluffyJawsProviderError(code=code, message=message),
    )


def _http_error(status_code: int) -> FluffyJawsProviderError | None:
    if 200 <= status_code < 300:
        return None
    if status_code in {401, 403}:
        return FluffyJawsProviderError(
            code=FluffyJawsFailureCode.AUTH_ERROR,
            message="FluffyJaws authentication or authorization failed",
            http_status=status_code,
        )
    if status_code == 429:
        return FluffyJawsProviderError(
            code=FluffyJawsFailureCode.RATE_LIMITED,
            message="FluffyJaws rate limit was reached",
            retryable=True,
            http_status=status_code,
        )
    if status_code == 400:
        return FluffyJawsProviderError(
            code=FluffyJawsFailureCode.INVALID_RESPONSE,
            message="FluffyJaws rejected the documented request",
            http_status=status_code,
        )
    return FluffyJawsProviderError(
        code=FluffyJawsFailureCode.PROVIDER_ERROR,
        message="FluffyJaws provider returned an error",
        retryable=status_code >= 500,
        http_status=status_code,
    )


def _transport_outcome_for(
    error: FluffyJawsProviderError,
    *,
    fallback: ProviderTransportOutcome,
) -> ProviderTransportOutcome:
    if error.code == FluffyJawsFailureCode.TIMEOUT:
        return ProviderTransportOutcome.TIMEOUT
    if error.code == FluffyJawsFailureCode.AUTH_ERROR:
        return ProviderTransportOutcome.AUTH_ERROR
    if error.code == FluffyJawsFailureCode.RATE_LIMITED:
        return ProviderTransportOutcome.RATE_LIMITED
    if error.code in {
        FluffyJawsFailureCode.PROVIDER_ERROR,
        FluffyJawsFailureCode.STREAM_INTERRUPTED,
    }:
        return ProviderTransportOutcome.PROVIDER_ERROR
    # Invalid protocol/schema is a completed transport whose payload fails the
    # strict normalization boundary; the central executor finalizes it as
    # INVALID_RESPONSE rather than a transport failure.
    return fallback


def _raise_if_stopped(context: EvidenceProviderExecutionContext) -> None:
    if context.cancelled():
        raise FluffyJawsProviderCancelled("FluffyJaws provider call was cancelled")
    if context.remaining_seconds() <= 0:
        raise EvidenceProviderTimeout(
            "FluffyJaws provider deadline expired",
            error_code=FluffyJawsFailureCode.TIMEOUT.value,
        )


def _contains_source_shaped_metadata(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().casefold()
            if normalized in _SOURCE_SHAPED_KEYS:
                return True
            if _contains_source_shaped_metadata(child):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_source_shaped_metadata(child) for child in value)
    return False


def _unsupported_provider_filters(
    query: EvidenceQueryV1,
    *,
    supports_max_results: bool,
) -> list[str]:
    """Report constraints not represented by the documented stream request."""

    unsupported = set(active_query_filters(query))
    if supports_max_results:
        unsupported.discard("max_results")
    return sorted(unsupported)


def _opaque_reference(value: str) -> str:
    candidate = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,200}", candidate):
        return ""
    safe = _redact_text(candidate, limit=200).strip()
    return safe if safe == candidate else ""


def _bounded_optional_text(
    value: str | None,
    *,
    field_name: str,
    max_chars: int = 200,
) -> str | None:
    normalized = str(value or "").strip()
    if len(normalized) > max_chars:
        raise ValueError(f"FluffyJaws {field_name} exceeds {max_chars} characters")
    return normalized or None


def _safe_upstream_code(value: Any) -> str:
    code = str(value or "").strip()
    return code if re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", code) else ""


def _redact_text(value: Any, *, limit: int = _MAX_DIAGNOSTIC_CHARS) -> str:
    text = str(value or "")
    text = _URL_CREDENTIAL_RE.sub(r"\1[redacted-credentials]@", text)
    text = _BEARER_RE.sub("Bearer [redacted-token]", text)
    text = _AUTHORIZATION_FIELD_RE.sub(
        lambda match: f"{match.group(1)}=[redacted]",
        text,
    )
    text = _SENSITIVE_FIELD_RE.sub(
        lambda match: f"{match.group(1)}=[redacted]",
        text,
    )
    return text[:limit]


def _safe_log_identifier(value: Any) -> str:
    redacted = _redact_text(value, limit=200)
    return re.sub(r"[^A-Za-z0-9._:-]", "_", redacted)


def _log_result(
    result: EvidenceProviderRawResult,
    *,
    source_metadata_quarantined: bool,
) -> None:
    logger.info(
        "fluffyjaws_provider_call_completed",
        extra={
            "provider": _PROVIDER_NAME,
            "provider_call_id": _safe_log_identifier(result.provider_call_id),
            "query_id": _safe_log_identifier(result.query_id),
            "correlation_id": _safe_log_identifier(result.correlation_id),
            "transport_outcome": result.transport_outcome.value,
            "redacted_error_code": result.redacted_error_code,
            "source_metadata_quarantined": source_metadata_quarantined,
        },
    )


def build_fluffyjaws_provider(
    *,
    config: FluffyJawsProviderConfig | None = None,
    transport_factory: Callable[[], FluffyJawsTransport],
    citation_decoder: FluffyJawsCitationDecoder | None = None,
    now: Callable[[], datetime] | None = None,
    call_id_factory: Callable[[], str] | None = None,
) -> FluffyJawsKnowledgeProvider | None:
    """Build only when enabled, without touching auth/transport on the off path."""

    resolved = config or FluffyJawsProviderConfig()
    if not resolved.enabled:
        return None
    return FluffyJawsKnowledgeProvider(
        config=resolved,
        transport=transport_factory(),
        citation_decoder=citation_decoder,
        now=now,
        call_id_factory=call_id_factory,
    )


__all__ = [
    "FluffyJawsDecodedEvidence",
    "FluffyJawsFailureCode",
    "FluffyJawsCitationDecoder",
    "FluffyJawsKnowledgeProvider",
    "FluffyJawsProviderCancelled",
    "FluffyJawsProviderConfig",
    "FluffyJawsProviderDisabledError",
    "FluffyJawsProviderError",
    "FluffyJawsStreamRequest",
    "FluffyJawsStreamResponse",
    "FluffyJawsTransport",
    "HttpxFluffyJawsTransport",
    "build_fluffyjaws_provider",
]
