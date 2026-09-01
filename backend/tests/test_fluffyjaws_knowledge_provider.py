"""Isolated contract tests for the default-off FluffyJaws provider.

These tests intentionally exercise only the documented API/SSE transport
contract.  FluffyJaws answer text is discovery synthesis, not canonical
evidence, because the public contract does not define stable source fields.
"""

from __future__ import annotations

import json
import logging
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from typing import Iterable

import httpx
import pytest
from pydantic import ValidationError

import app.services.fluffyjaws_knowledge_provider as fluffyjaws_module

from app.core.schemas_canonical_test_plan_runtime import (
    ApplicabilityState,
    AuthorityClass,
    AuthoritySubject,
    CurrentnessState,
    EvidenceSourceType,
    IssueDomain,
    RuntimePrincipal,
    VerificationState,
    VersionScope,
)
from app.services.fluffyjaws_knowledge_provider import (
    FluffyJawsDecodedEvidence,
    FluffyJawsFailureCode,
    FluffyJawsKnowledgeProvider,
    FluffyJawsProviderCancelled,
    FluffyJawsProviderConfig,
    FluffyJawsProviderDisabledError,
    FluffyJawsStreamRequest,
    HttpxFluffyJawsTransport,
    build_fluffyjaws_provider,
)
from app.services.reasoning_evidence_provider import (
    AuthorityRequirement,
    EvidenceProviderExecutionContext,
    EvidenceProviderInvalidResponse,
    EvidenceProviderStatus,
    EvidenceProviderTimeout,
    EvidenceQueryV1,
    EvidenceProviderExecutor,
    ExcludedSources,
    ProviderTransportOutcome,
    QueryMateriality,
    StrictProviderHit,
    TemporalBoundary,
    provider_hit_content_sha256,
)


_FIXED_NOW = datetime(2026, 8, 28, 6, 0, tzinfo=timezone.utc)


def _sse_event(payload: dict[str, object]) -> list[str]:
    return [f"data: {json.dumps(payload, separators=(',', ':'))}", ""]


def _successful_lines(
    *,
    text: str = "Supporting answer",
    final_response_id: str = "resp-final-1",
    delta_extra: dict[str, object] | None = None,
) -> list[str]:
    delta: dict[str, object] = {
        "type": "response.output_text.delta",
        "delta": text,
    }
    delta.update(delta_extra or {})
    return [
        ": keep-alive",
        "",
        *_sse_event({"type": "response.created", "response_id": "provisional"}),
        *_sse_event(delta),
        *_sse_event({"type": "response.completed", "response_id": final_response_id}),
        "data: [DONE]",
        "",
    ]


class _Response:
    def __init__(
        self,
        *,
        status_code: int = 200,
        lines: Iterable[str | bytes] = (),
        iteration_error: BaseException | None = None,
    ) -> None:
        self.status_code = status_code
        self._lines = list(lines)
        self._iteration_error = iteration_error

    def iter_lines(self) -> Iterable[str]:
        yield from self._lines
        if self._iteration_error is not None:
            raise self._iteration_error

    def iter_bytes(self, chunk_size: int) -> Iterable[bytes]:
        payload = b"\n".join(
            line if isinstance(line, bytes) else str(line).encode("utf-8")
            for line in self._lines
        )
        for offset in range(0, len(payload), chunk_size):
            yield payload[offset : offset + chunk_size]
        if self._iteration_error is not None:
            raise self._iteration_error


class _ResponseContext(AbstractContextManager[_Response]):
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.exited = False

    def __enter__(self) -> _Response:
        return self.response

    def __exit__(self, exc_type, exc, traceback) -> bool:
        del exc_type, exc, traceback
        self.exited = True
        return False


class _Transport:
    def __init__(
        self,
        response: _Response | None = None,
        *,
        call_error: BaseException | None = None,
    ) -> None:
        self.response = response or _Response(lines=_successful_lines())
        self.call_error = call_error
        self.requests: list[FluffyJawsStreamRequest] = []

    def stream(
        self, request: FluffyJawsStreamRequest
    ) -> AbstractContextManager[_Response]:
        self.requests.append(request)
        if self.call_error is not None:
            raise self.call_error
        return _ResponseContext(self.response)


class _FailIfCalledTransport:
    def stream(self, request: FluffyJawsStreamRequest):
        del request
        raise AssertionError("disabled provider must not construct a transport call")


def _query(
    *,
    correlation_id: str = "corr-fj-1",
    verified_source_required: bool = True,
) -> EvidenceQueryV1:
    return EvidenceQueryV1(
        question_id="question:fj-test",
        question="What current product evidence defines this behavior?",
        dimension=None,
        domain=IssueDomain.AUTHORING,
        requested_evidence_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
        materiality=QueryMateriality.P1,
        authority_requirement=AuthorityRequirement(
            subject=AuthoritySubject.PRODUCT_CONTRACT,
            acceptable_classes=[AuthorityClass.OFFICIAL_PRODUCT_CONTRACT],
            direct_source_required=True,
            verified_source_required=verified_source_required,
        ),
        jira_reference="jira:GUIDES-FJ-1",
        context_evidence_ids=[],
        temporal_boundary=TemporalBoundary(
            version_scope=VersionScope(),
            allowed_currentness=[
                CurrentnessState.CURRENT,
                CurrentnessState.VERSION_UNKNOWN,
            ],
        ),
        excluded_sources=ExcludedSources(),
        max_results=3,
        correlation_id=correlation_id,
        blocking=False,
    )


def _minimal_query() -> EvidenceQueryV1:
    return EvidenceQueryV1(
        question_id="question:fj-minimal",
        question="Find directly usable source evidence.",
        domain=IssueDomain.AUTHORING,
        authority_requirement=AuthorityRequirement(
            subject=AuthoritySubject.PRODUCT_CONTRACT,
        ),
        materiality=QueryMateriality.P2,
        max_results=1,
        correlation_id="corr-fj-1",
    )


def _context(
    *,
    cancelled=lambda: False,
    source_visible: bool = False,
    source_verified=False,
    benchmark_split: str = "",
) -> EvidenceProviderExecutionContext:
    verification_check = (
        source_verified
        if callable(source_verified)
        else lambda _hit: bool(source_verified)
    )
    return EvidenceProviderExecutionContext(
        principal=RuntimePrincipal(
            principal_id="provider-test-user",
            tenant_id="provider-test-tenant",
            roles=["authenticated"],
        ),
        run_id="run-fj-test",
        request_id="request-fj-test",
        correlation_id="corr-fj-1",
        benchmark_split=benchmark_split,
        timeout_seconds=30.0,
        cancellation_check=cancelled,
        source_visibility_check=lambda _hit: source_visible,
        source_verification_check=verification_check,
    )


def _provider(
    transport,
    *,
    enabled: bool = True,
    max_response_chars: int = 100_000,
    max_stream_chars: int = 2_000_000,
    citation_decoder=None,
) -> FluffyJawsKnowledgeProvider:
    return FluffyJawsKnowledgeProvider(
        config=FluffyJawsProviderConfig(
            enabled=enabled,
            timeout_seconds=30.0,
            max_response_chars=max_response_chars,
            max_stream_chars=max_stream_chars,
        ),
        transport=transport,
        citation_decoder=citation_decoder,
        now=lambda: _FIXED_NOW,
        call_id_factory=lambda: "fj-call-1",
    )


def test_documented_discovery_is_not_evidence_or_a_false_empty_result() -> None:
    transport = _Transport(_Response(lines=_successful_lines()))
    query = _query()
    context = _context()

    raw = _provider(transport).retrieve(query, context)

    assert raw.transport_outcome == ProviderTransportOutcome.COMPLETED
    assert raw.raw_hits == []
    assert len(raw.discovery_syntheses) == 1
    synthesis = raw.discovery_syntheses[0]
    assert synthesis.text == "Supporting answer"
    assert synthesis.authority_class == "SUPPORTING_DISCOVERY"
    assert synthesis.raw_provider_reference == "resp-final-1"
    assert synthesis.query_id == query.query_id
    assert synthesis.correlation_id == query.correlation_id
    assert transport.requests[0].timeout_seconds == pytest.approx(30.0, abs=0.01)
    assert "authorization" not in json.dumps(transport.requests[0].json_body).casefold()

    executed = EvidenceProviderExecutor().execute(
        _provider(_Transport(_Response(lines=_successful_lines()))),
        query,
        context,
    )
    assert executed.call_result.status == EvidenceProviderStatus.PROVIDER_ERROR
    assert executed.call_result.redacted_error_code == "INCOMPLETE_RESULT"
    assert executed.call_result.accepted_evidence_count == 0
    assert executed.call_result.raw_provider_reference == "resp-final-1"
    assert not executed.evidence_bundle.records
    assert len(executed.discovery_syntheses) == 1


def test_authorization_schemes_are_removed_from_outbound_question_and_synthesis() -> None:
    secrets = ("dXNlcjpwYXNz", "digest-user", "negotiate-token")
    question = (
        "Authorization: Basic dXNlcjpwYXNz\n"
        'Authorization: Digest username="digest-user", realm="internal"\n'
        "Proxy-Authorization: Negotiate negotiate-token"
    )
    query = _query().model_copy(update={"question": question})
    transport = _Transport(
        _Response(lines=_successful_lines(text=question))
    )

    raw = _provider(transport).retrieve(query, _context())

    request_payload = json.dumps(transport.requests[0].json_body)
    serialized = request_payload + raw.model_dump_json()
    assert all(secret not in serialized for secret in secrets)
    assert "redacted" in serialized.casefold()


def test_completed_empty_answer_is_empty_without_a_synthesis() -> None:
    raw = _provider(_Transport(_Response(lines=_successful_lines(text="")))).retrieve(
        _query(), _context()
    )
    assert raw.transport_outcome == ProviderTransportOutcome.COMPLETED
    assert raw.raw_hits == []
    assert raw.discovery_syntheses == []


@pytest.mark.parametrize(
    ("lines", "expected_code"),
    [
        (["data: not-json", ""], FluffyJawsFailureCode.INVALID_RESPONSE),
        (
            _sse_event({"delta": "missing type"}),
            FluffyJawsFailureCode.INVALID_RESPONSE,
        ),
        (
            _sse_event({"type": "response.output_text.delta", "delta": 42}),
            FluffyJawsFailureCode.INVALID_RESPONSE,
        ),
        (
            [*_sse_event({"type": "response.output_text.delta", "delta": "x"})],
            FluffyJawsFailureCode.INVALID_RESPONSE,
        ),
    ],
)
def test_malformed_or_incomplete_stream_fails_closed(
    lines: list[str], expected_code: FluffyJawsFailureCode
) -> None:
    with pytest.raises(EvidenceProviderInvalidResponse) as raised:
        _provider(_Transport(_Response(lines=lines))).retrieve(_query(), _context())
    assert raised.value.redacted_error_code == expected_code.value

    result = EvidenceProviderExecutor().execute(
        _provider(_Transport(_Response(lines=lines))),
        _query(),
        _context(),
    )
    assert result.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert result.call_result.redacted_error_code == expected_code.value
    assert result.evidence_bundle.records == []
    assert result.discovery_syntheses == []


def test_non_utf8_stream_is_invalid_response_without_exposing_raw_bytes() -> None:
    result = EvidenceProviderExecutor().execute(
        _provider(_Transport(_Response(lines=[b"\xff\xfe"]))),
        _query(),
        _context(),
    )
    assert result.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert result.call_result.redacted_error_code == "invalid_response"
    assert result.evidence_bundle.records == []


@pytest.mark.parametrize(
    ("status_code", "outcome", "error_code", "retryable"),
    [
        (401, ProviderTransportOutcome.AUTH_ERROR, "auth_error", False),
        (403, ProviderTransportOutcome.AUTH_ERROR, "auth_error", False),
        (429, ProviderTransportOutcome.RATE_LIMITED, "rate_limited", True),
        (500, ProviderTransportOutcome.PROVIDER_ERROR, "provider_error", True),
    ],
)
def test_http_failures_map_to_structured_provider_outcomes(
    status_code: int,
    outcome: ProviderTransportOutcome,
    error_code: str,
    retryable: bool,
) -> None:
    raw = _provider(_Transport(_Response(status_code=status_code))).retrieve(
        _query(), _context()
    )
    assert raw.transport_outcome == outcome
    assert raw.redacted_error_code == error_code
    assert raw.retryable is retryable
    assert raw.raw_hits == []
    assert raw.discovery_syntheses == []


def test_timeout_and_transport_failure_are_structured_and_bounded() -> None:
    request = httpx.Request("POST", "https://api.fluffyjaws.adobe.com/api/v1/stream")
    timeout_raw = _provider(
        _Transport(call_error=httpx.ReadTimeout("secret timeout", request=request))
    ).retrieve(_query(), _context())
    assert timeout_raw.transport_outcome == ProviderTransportOutcome.TIMEOUT
    assert timeout_raw.redacted_error_code == "timeout"
    assert timeout_raw.attempts == 1
    assert timeout_raw.raw_hits == []

    failure_raw = _provider(
        _Transport(call_error=httpx.ConnectError("connection failed", request=request))
    ).retrieve(_query(), _context())
    assert failure_raw.transport_outcome == ProviderTransportOutcome.PROVIDER_ERROR
    assert failure_raw.redacted_error_code == "stream_interrupted"
    assert failure_raw.attempts == 1
    assert failure_raw.raw_hits == []


def test_http_200_sse_error_is_authoritative_and_redacted() -> None:
    lines = _sse_event(
        {
            "type": "error",
            "message": "Bearer abcdef123456 api_key=supersecret",
            "retryable": True,
            "required_action": "session=private-session-value",
        }
    )
    raw = _provider(_Transport(_Response(lines=lines))).retrieve(_query(), _context())
    serialized = raw.model_dump_json()
    assert raw.transport_outcome == ProviderTransportOutcome.PROVIDER_ERROR
    assert raw.redacted_error_code == "provider_error"
    assert raw.retryable is True
    assert raw.raw_hits == []
    assert raw.discovery_syntheses == []
    for secret in ("abcdef123456", "supersecret", "private-session-value"):
        assert secret not in serialized


def test_stream_interruption_discards_partial_text() -> None:
    request = httpx.Request("POST", "https://api.fluffyjaws.adobe.com/api/v1/stream")
    response = _Response(
        lines=_sse_event(
            {"type": "response.output_text.delta", "delta": "partial secret text"}
        ),
        iteration_error=httpx.ReadError("connection reset", request=request),
    )
    raw = _provider(_Transport(response)).retrieve(_query(), _context())
    assert raw.transport_outcome == ProviderTransportOutcome.PROVIDER_ERROR
    assert raw.redacted_error_code == "stream_interrupted"
    assert raw.raw_hits == []
    assert raw.discovery_syntheses == []


def test_stream_restart_discards_pre_restart_content_and_provisional_id() -> None:
    lines = [
        *_sse_event({"type": "response.output_text.delta", "delta": "discard this"}),
        *_sse_event({"type": "stream_restarted"}),
        *_sse_event({"type": "response.created", "response_id": "provisional"}),
        *_sse_event({"type": "response.output_text.delta", "delta": "keep this"}),
        *_sse_event({"type": "response.completed", "response_id": "final-id"}),
        "data: [DONE]",
        "",
    ]
    raw = _provider(_Transport(_Response(lines=lines))).retrieve(_query(), _context())
    assert raw.redacted_error_code == ""
    assert len(raw.discovery_syntheses) == 1
    assert raw.discovery_syntheses[0].text == "keep this"
    assert raw.discovery_syntheses[0].raw_provider_reference == "final-id"


def test_cancellation_prevents_transport_and_is_not_coerced_to_provider_error() -> None:
    transport = _Transport()
    with pytest.raises(FluffyJawsProviderCancelled):
        _provider(transport).retrieve(_query(), _context(cancelled=lambda: True))
    assert transport.requests == []


def test_cancellation_during_stream_closes_response_and_discards_partial_text() -> None:
    state = {"cancelled": False}

    class _StreamingResponse:
        status_code = 200

        def iter_lines(self) -> Iterable[str]:
            yield 'data: {"type":"response.output_text.delta","delta":"partial"}'
            state["cancelled"] = True
            yield ""

        def iter_bytes(self, chunk_size: int) -> Iterable[bytes]:
            del chunk_size
            for line in self.iter_lines():
                yield f"{line}\n".encode("utf-8")

    response = _StreamingResponse()
    response_context = _ResponseContext(response)

    class _StreamingTransport:
        def stream(self, request: FluffyJawsStreamRequest):
            del request
            return response_context

    with pytest.raises(FluffyJawsProviderCancelled):
        _provider(_StreamingTransport()).retrieve(
            _query(),
            _context(cancelled=lambda: state["cancelled"]),
        )
    assert response_context.exited is True


def test_source_metadata_absent_or_uncontracted_never_becomes_evidence() -> None:
    absent = _provider(
        _Transport(_Response(lines=_successful_lines(text="No citation fields")))
    ).retrieve(_query(), _context())
    undocumented = _provider(
        _Transport(
            _Response(
                lines=_successful_lines(
                    text="Text with an undocumented citation",
                    delta_extra={
                        "citations": [
                            {
                                "url": "https://uncontracted.example/source",
                                "title": "Uncontracted source",
                            }
                        ]
                    },
                )
            )
        )
    ).retrieve(_query(), _context())

    assert absent.raw_hits == []
    assert undocumented.raw_hits == []
    assert absent.discovery_syntheses[0].authority_class == "SUPPORTING_DISCOVERY"
    assert undocumented.discovery_syntheses[0].authority_class == "SUPPORTING_DISCOVERY"
    serialized = undocumented.model_dump_json()
    assert "uncontracted.example" not in serialized
    assert "Uncontracted source" not in serialized


def test_disabled_provider_does_not_authenticate_or_touch_transport() -> None:
    provider = _provider(_FailIfCalledTransport(), enabled=False)
    assert provider.enabled is False
    with pytest.raises(FluffyJawsProviderDisabledError):
        provider.retrieve(_query(), _context())


def test_default_off_builder_does_not_construct_auth_or_transport() -> None:
    touched = False

    def forbidden_factory():
        nonlocal touched
        touched = True
        raise AssertionError("disabled builder must not initialize transport or auth")

    assert (
        build_fluffyjaws_provider(
            config=FluffyJawsProviderConfig(enabled=False),
            transport_factory=forbidden_factory,
        )
        is None
    )
    assert touched is False


def test_httpx_transport_uses_only_the_documented_request_contract() -> None:
    class _RecordingClient:
        def __init__(self) -> None:
            self.call: tuple[tuple[object, ...], dict[str, object]] | None = None

        def stream(self, *args, **kwargs):
            self.call = (args, kwargs)
            return _ResponseContext(_Response(lines=_successful_lines()))

    client = _RecordingClient()
    request = FluffyJawsStreamRequest(
        url="https://api.fluffyjaws.adobe.com/api/v1/stream",
        json_body={"messages": [{"role": "user", "content": "question"}]},
        timeout_seconds=17.0,
        correlation_id="local-only-correlation",
    )
    HttpxFluffyJawsTransport(client).stream(request)

    assert client.call is not None
    args, kwargs = client.call
    assert args == ("POST", request.url)
    assert kwargs["headers"] == {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
    }
    assert kwargs["json"] == request.json_body
    assert isinstance(kwargs["timeout"], httpx.Timeout)
    assert kwargs["follow_redirects"] is False
    serialized = json.dumps(kwargs["json"])
    assert "local-only-correlation" not in serialized


def test_unknown_reasoning_effort_is_passed_through_without_inventing_a_whitelist() -> (
    None
):
    transport = _Transport(_Response(lines=_successful_lines()))
    provider = FluffyJawsKnowledgeProvider(
        config=FluffyJawsProviderConfig(
            enabled=True,
            reasoning_effort="provider-defined-effort",
        ),
        transport=transport,
        now=lambda: _FIXED_NOW,
        call_id_factory=lambda: "fj-call-1",
    )
    provider.retrieve(_query(), _context())
    assert transport.requests[0].json_body["reasoningEffort"] == (
        "provider-defined-effort"
    )


def test_logs_use_allowlisted_fields_and_never_include_provider_error_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = "must-not-enter-provider-logs"
    caplog.set_level(
        logging.INFO,
        logger="app.services.fluffyjaws_knowledge_provider",
    )
    lines = _sse_event({"type": "error", "message": marker})
    _provider(_Transport(_Response(lines=lines))).retrieve(_query(), _context())

    rendered_records = "\n".join(
        f"{record.getMessage()} {record.__dict__}" for record in caplog.records
    )
    assert marker not in rendered_records


def test_parser_is_deterministic_for_the_same_documented_event_sequence() -> None:
    query = _query(correlation_id="corr-deterministic")
    first = _provider(
        _Transport(_Response(lines=_successful_lines(text="A deterministic answer")))
    ).retrieve(query, _context())
    differently_chunked = [
        ": another keep-alive",
        "",
        *_sse_event(
            {"type": "response.output_text.delta", "delta": "A deterministic "}
        ),
        *_sse_event({"type": "tool_progress", "message": "ignored progress"}),
        *_sse_event({"type": "response.output_text.delta", "delta": "answer"}),
        *_sse_event({"type": "response.completed", "response_id": "resp-final-1"}),
        "data: [DONE]",
        "",
    ]
    second = _provider(_Transport(_Response(lines=differently_chunked))).retrieve(
        query, _context()
    )
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_response_size_limit_fails_closed_without_partial_synthesis() -> None:
    with pytest.raises(EvidenceProviderInvalidResponse) as raised:
        _provider(
            _Transport(_Response(lines=_successful_lines(text="too long"))),
            max_response_chars=3,
        ).retrieve(_query(), _context())
    assert raised.value.redacted_error_code == "response_too_large"

    result = EvidenceProviderExecutor().execute(
        _provider(
            _Transport(_Response(lines=_successful_lines(text="too long"))),
            max_response_chars=3,
        ),
        _query(),
        _context(),
    )
    assert result.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert result.call_result.redacted_error_code == "response_too_large"
    assert result.evidence_bundle.records == []
    assert result.discovery_syntheses == []


def test_total_sse_payload_budget_fails_closed_across_multiple_events() -> None:
    first = {"type": "tool_progress", "message": "first bounded event"}
    second = {"type": "tool_progress", "message": "second bounded event"}
    first_size = len(json.dumps(first, separators=(",", ":")))
    second_size = len(json.dumps(second, separators=(",", ":")))
    total_budget = first_size + second_size - 1
    assert first_size <= total_budget
    assert second_size <= total_budget
    assert first_size + second_size > total_budget

    lines = [
        *_sse_event(first),
        *_sse_event(second),
        *_sse_event({"type": "response.completed", "response_id": "too-late"}),
        "data: [DONE]",
        "",
    ]
    with pytest.raises(EvidenceProviderInvalidResponse) as raised:
        _provider(
            _Transport(_Response(lines=lines)),
            max_stream_chars=total_budget,
        ).retrieve(_query(), _context())
    assert raised.value.redacted_error_code == "response_too_large"


def test_without_decoder_source_events_are_not_captured_or_retained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}
    original_parse_stream = fluffyjaws_module._parse_stream

    def _parse_stream_spy(lines, **kwargs):
        observed["capture_events"] = kwargs["capture_events"]
        parsed = original_parse_stream(lines, **kwargs)
        observed["events"] = parsed.events
        return parsed

    monkeypatch.setattr(fluffyjaws_module, "_parse_stream", _parse_stream_spy)
    source_marker = "https://must-not-be-retained.example/private-source"
    lines = [
        *_sse_event({"type": "response.output_text.delta", "delta": "Safe discovery"}),
        *_sse_event(
            {
                "type": "future.source.event",
                "source": {"url": source_marker, "title": "Uncontracted"},
            }
        ),
        *_sse_event({"type": "response.completed", "response_id": "safe-final"}),
        "data: [DONE]",
        "",
    ]

    raw = _provider(_Transport(_Response(lines=lines))).retrieve(_query(), _context())

    assert observed == {"capture_events": False, "events": ()}
    assert raw.raw_hits == []
    assert source_marker not in raw.model_dump_json()


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.fluffyjaws.adobe.com",
        "https://api.fluffyjaws.adobe.com.evil.example",
        "https://api.fluffyjaws.adobe.com:443",
        "https://api.fluffyjaws.adobe.com/api/v1",
        "https://fluffyjaws.adobe.com",
    ],
)
def test_config_rejects_every_non_approved_exact_origin(base_url: str) -> None:
    with pytest.raises(ValueError, match="approved API origin"):
        FluffyJawsProviderConfig(enabled=True, base_url=base_url)


def test_stream_rejects_data_after_done_marker() -> None:
    lines = [
        *_successful_lines(text="complete"),
        *_sse_event({"type": "tool_progress", "message": "too late"}),
    ]
    with pytest.raises(EvidenceProviderInvalidResponse) as raised:
        _provider(_Transport(_Response(lines=lines))).retrieve(_query(), _context())
    assert raised.value.redacted_error_code == "invalid_response"


def test_stream_rejects_event_after_response_completed() -> None:
    lines = [
        *_sse_event({"type": "response.output_text.delta", "delta": "complete"}),
        *_sse_event({"type": "response.completed", "response_id": "final-id"}),
        *_sse_event({"type": "tool_progress", "message": "too late"}),
        "data: [DONE]",
        "",
    ]
    with pytest.raises(EvidenceProviderInvalidResponse) as raised:
        _provider(_Transport(_Response(lines=lines))).retrieve(_query(), _context())
    assert raised.value.redacted_error_code == "invalid_response"


def test_completion_response_id_that_redacts_to_empty_is_invalid() -> None:
    lines = _successful_lines(final_response_id="Bearer response-secret-token")
    with pytest.raises(EvidenceProviderInvalidResponse) as raised:
        _provider(_Transport(_Response(lines=lines))).retrieve(_query(), _context())
    assert raised.value.redacted_error_code == "invalid_response"
    assert "response-secret-token" not in str(raised.value)


def test_iteration_limit_is_provider_error_and_discards_executor_sidecars() -> None:
    lines = [
        *_sse_event(
            {"type": "response.output_text.delta", "delta": "bounded discovery"}
        ),
        *_sse_event(
            {
                "type": "iteration_limit_reached",
                "iteration": 7,
                "pending_calls": 2,
            }
        ),
        *_sse_event({"type": "response.completed", "response_id": "final-limit"}),
        "data: [DONE]",
        "",
    ]
    raw = _provider(_Transport(_Response(lines=lines))).retrieve(_query(), _context())
    assert raw.transport_outcome == ProviderTransportOutcome.PROVIDER_ERROR
    assert raw.truncated is True
    assert raw.redacted_error_code == "iteration_limit_reached"
    assert raw.redacted_message == "FluffyJaws iteration limit reached"
    assert raw.raw_provider_reference == "final-limit"
    assert raw.raw_hits == []
    assert len(raw.discovery_syntheses) == 1
    assert raw.discovery_syntheses[0].text == "bounded discovery"

    executed = EvidenceProviderExecutor().execute(
        _provider(_Transport(_Response(lines=lines))),
        _query(),
        _context(),
    )
    assert executed.call_result.status == EvidenceProviderStatus.PROVIDER_ERROR
    assert executed.call_result.accepted_evidence_count == 0
    assert executed.evidence_bundle.records == []
    assert executed.provenance == []
    assert executed.discovery_syntheses == []


def test_discovery_redacts_quoted_multiword_secrets() -> None:
    secret_text = (
        'client_secret="alpha beta gamma"; '
        "api_key='delta epsilon zeta'; password=plain-secret"
    )
    raw = _provider(
        _Transport(_Response(lines=_successful_lines(text=secret_text)))
    ).retrieve(_query(), _context())
    serialized = raw.model_dump_json()
    for secret in (
        "alpha beta gamma",
        "delta epsilon zeta",
        "plain-secret",
    ):
        assert secret not in serialized
    assert "[redacted]" in raw.discovery_syntheses[0].text.casefold()


def test_sse_error_preserves_only_safe_code_and_resend_action() -> None:
    lines = _sse_event(
        {
            "type": "error",
            "message": 'client_secret="do not retain this value"',
            "code": "continuation_unavailable",
            "retryable": False,
            "required_action": "resend_full_history",
        }
    )
    raw = _provider(_Transport(_Response(lines=lines))).retrieve(_query(), _context())
    assert raw.transport_outcome == ProviderTransportOutcome.PROVIDER_ERROR
    assert raw.redacted_error_code == "continuation_unavailable"
    assert raw.redacted_required_action == "resend_full_history"
    assert raw.redacted_message == "FluffyJaws stream reported an error"
    assert "do not retain this value" not in raw.model_dump_json()

    result = EvidenceProviderExecutor().execute(
        _provider(_Transport(_Response(lines=lines))),
        _query(),
        _context(),
    )
    assert result.call_result.status == EvidenceProviderStatus.PROVIDER_ERROR
    assert result.call_result.redacted_error_code == "continuation_unavailable"
    assert result.call_result.redacted_required_action == "resend_full_history"


def test_unsafe_sse_error_code_falls_back_to_allowlisted_provider_code() -> None:
    lines = _sse_event(
        {
            "type": "error",
            "message": "upstream failed",
            "code": "unsafe code Bearer secret-token",
            "required_action": "copy_private_session",
        }
    )
    raw = _provider(_Transport(_Response(lines=lines))).retrieve(_query(), _context())
    assert raw.redacted_error_code == "provider_error"
    assert raw.redacted_required_action == ""
    assert "secret-token" not in raw.model_dump_json()


def test_deadline_expiring_between_sse_events_stops_without_partial_result() -> None:
    class _ExpiringContext:
        correlation_id = "corr-fj-1"

        def __init__(self) -> None:
            self.remaining_checks = 0

        def cancelled(self) -> bool:
            return False

        def remaining_seconds(self) -> float:
            self.remaining_checks += 1
            return 30.0 if self.remaining_checks <= 8 else 0.0

    lines = [
        *_sse_event({"type": "response.output_text.delta", "delta": "partial"}),
        *_sse_event({"type": "response.output_text.delta", "delta": "late"}),
        *_sse_event({"type": "response.completed", "response_id": "never-used"}),
        "data: [DONE]",
        "",
    ]
    context = _ExpiringContext()
    with pytest.raises(EvidenceProviderTimeout) as raised:
        _provider(_Transport(_Response(lines=lines))).retrieve(_query(), context)
    assert raised.value.redacted_error_code == "timeout"
    assert context.remaining_checks > 8


class _SyntheticCitationDecoder:
    """Test-only decoder seam; it assumes no FluffyJaws wire citation fields."""

    contract_version = "synthetic_decoder_v1"
    supported_source_types = (EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,)

    def __init__(self, *, include_source: bool) -> None:
        self.include_source = include_source
        self.events: tuple[dict[str, object], ...] = ()
        self.final_response_id = ""

    def decode(self, events, *, final_response_id: str):
        self.events = tuple(dict(event) for event in events)
        self.final_response_id = final_response_id
        if not self.include_source:
            return FluffyJawsDecodedEvidence()
        hit = StrictProviderHit(
            source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
            source_reference="doc:https://experienceleague.adobe.com/current",
            source_locator="https://experienceleague.adobe.com/current#title",
            source_native_id="synthetic-doc-1",
            title="Current title behavior",
            text="The current title appears after the map is reopened.",
            provider_native_kind="synthetic-decoder-test",
            rank=1,
            raw_provider_reference=f"{final_response_id}:synthetic-source:1",
        )
        return FluffyJawsDecodedEvidence(
            hits=(hit,),
            synthesis_hit_references=(hit.raw_provider_reference,),
        )


def _decoder_lines() -> list[str]:
    return [
        *_sse_event(
            {"type": "response.output_text.delta", "delta": "Discovery answer"}
        ),
        *_sse_event({"type": "response.completed", "response_id": "citation-final"}),
        "data: [DONE]",
        "",
    ]


def test_contract_versioned_citation_decoder_accepts_visible_source_evidence() -> None:
    decoder = _SyntheticCitationDecoder(include_source=True)
    provider = _provider(
        _Transport(_Response(lines=_decoder_lines())),
        citation_decoder=decoder,
    )
    result = EvidenceProviderExecutor().execute(
        provider,
        _query(verified_source_required=False),
        _context(source_visible=True),
    )

    assert result.call_result.accepted_evidence_count == 1
    assert result.call_result.status == EvidenceProviderStatus.PARTIAL
    assert len(result.evidence_bundle.records) == 1
    record = result.evidence_bundle.records[0]
    assert record.source_type == EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION
    assert record.visibility.tenant_id == "provider-test-tenant"
    assert record.source_reference == ("doc:https://experienceleague.adobe.com/current")
    assert result.provenance[0].raw_provider_reference == (
        "citation-final:synthetic-source:1"
    )
    assert result.call_result.provider_contract_version.endswith(
        "+synthetic_decoder_v1"
    )
    assert decoder.final_response_id == "citation-final"


def test_contract_versioned_citation_decoder_without_source_is_empty() -> None:
    decoder = _SyntheticCitationDecoder(include_source=False)
    provider = _provider(
        _Transport(_Response(lines=_decoder_lines())),
        citation_decoder=decoder,
    )
    result = EvidenceProviderExecutor().execute(
        provider,
        _minimal_query(),
        _context(),
    )

    assert result.call_result.status == EvidenceProviderStatus.EMPTY
    assert result.call_result.accepted_evidence_count == 0
    assert result.evidence_bundle.records == []
    assert result.provenance == []
    assert len(result.discovery_syntheses) == 1
    assert decoder.final_response_id == "citation-final"


def _strict_source_hit(
    *,
    source_type: EvidenceSourceType = EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
    source_reference: str = "doc:https://experienceleague.adobe.com/decoded",
) -> StrictProviderHit:
    return StrictProviderHit(
        source_type=source_type,
        source_reference=source_reference,
        source_locator="https://experienceleague.adobe.com/decoded#behavior",
        source_native_id="decoded-doc-1",
        title="Decoded product behavior",
        text="The decoded product source defines the behavior.",
        provider_native_kind="contracted-citation",
        rank=1,
        retrieval_score=0.75,
        raw_provider_reference="citation-final:citation:decoded-1",
    )


class _MalformedCitationDecoder:
    contract_version = "malformed_v1"
    supported_source_types = (EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,)

    def decode(self, events, *, final_response_id: str):
        del events, final_response_id
        return FluffyJawsDecodedEvidence(
            hits=(
                {
                    "source_type": (EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION),
                    "source_reference": "doc:missing-required-fields",
                },
            )
        )


class _ExplodingCitationDecoder:
    contract_version = "exploding_v1"
    supported_source_types = (EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,)

    def decode(self, events, *, final_response_id: str):
        del events, final_response_id
        raise RuntimeError('client_secret="decoder private value"')


class _MismatchedTypeCitationDecoder:
    contract_version = "mismatch_v1"
    supported_source_types = (EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,)

    def decode(self, events, *, final_response_id: str):
        del events, final_response_id
        return FluffyJawsDecodedEvidence(
            hits=(
                _strict_source_hit(
                    source_type=EvidenceSourceType.DITA_SPECIFICATION,
                    source_reference="spec:dita-2.0",
                ),
            )
        )


class _EmptyVersionedCitationDecoder:
    supported_source_types = (EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,)

    def __init__(self, contract_version: str) -> None:
        self.contract_version = contract_version

    def decode(self, events, *, final_response_id: str):
        del events, final_response_id
        return FluffyJawsDecodedEvidence()


def test_decoder_malformed_hit_is_invalid_response_without_discovery_sidecar() -> None:
    result = EvidenceProviderExecutor().execute(
        _provider(
            _Transport(_Response(lines=_successful_lines())),
            citation_decoder=_MalformedCitationDecoder(),
        ),
        _query(verified_source_required=False),
        _context(source_visible=True),
    )
    assert result.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert result.call_result.redacted_error_code == "invalid_response"
    assert result.call_result.accepted_evidence_count == 0
    assert result.evidence_bundle.records == []
    assert result.discovery_syntheses == []


def test_decoder_exception_is_generic_invalid_response_and_redacts_exception() -> None:
    result = EvidenceProviderExecutor().execute(
        _provider(
            _Transport(_Response(lines=_successful_lines())),
            citation_decoder=_ExplodingCitationDecoder(),
        ),
        _query(verified_source_required=False),
        _context(source_visible=True),
    )
    serialized = result.model_dump_json()
    assert result.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert result.call_result.redacted_error_code == "invalid_response"
    assert result.call_result.redacted_message == ("FluffyJaws citation decoder failed")
    assert "decoder private value" not in serialized
    assert result.discovery_syntheses == []


def test_stream_restart_removes_pre_restart_events_before_citation_decode() -> None:
    decoder = _SyntheticCitationDecoder(include_source=True)
    lines = [
        *_sse_event(
            {
                "type": "tool_progress",
                "message": "pre-restart-must-disappear",
            }
        ),
        *_sse_event({"type": "stream_restarted"}),
        *_sse_event(
            {"type": "response.output_text.delta", "delta": "Restarted answer"}
        ),
        *_sse_event(
            {
                "type": "tool_progress",
                "message": "post-restart-kept",
            }
        ),
        *_sse_event({"type": "response.completed", "response_id": "restart-final"}),
        "data: [DONE]",
        "",
    ]

    raw = _provider(
        _Transport(_Response(lines=lines)),
        citation_decoder=decoder,
    ).retrieve(_query(verified_source_required=False), _context())

    decoder_payload = json.dumps(decoder.events, sort_keys=True)
    assert "pre-restart-must-disappear" not in decoder_payload
    assert "post-restart-kept" in decoder_payload
    assert len(raw.raw_hits) == 1


def test_decoder_supported_type_mismatch_is_invalid_response() -> None:
    result = EvidenceProviderExecutor().execute(
        _provider(
            _Transport(_Response(lines=_successful_lines())),
            citation_decoder=_MismatchedTypeCitationDecoder(),
        ),
        _query(verified_source_required=False),
        _context(source_visible=True),
    )
    assert result.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert result.call_result.redacted_error_code == "UNSUPPORTED_SOURCE_TYPE"
    assert result.call_result.accepted_evidence_count == 0
    assert result.evidence_bundle.records == []
    assert result.discovery_syntheses == []


def test_combined_citation_contract_version_accepts_80_and_rejects_81_chars() -> None:
    base_raw = _provider(_Transport(_Response(lines=_successful_lines()))).retrieve(
        _query(), _context()
    )
    decoder_chars_at_boundary = 80 - len(base_raw.provider_contract_version) - 1
    boundary_version = "v" * decoder_chars_at_boundary
    boundary_raw = _provider(
        _Transport(_Response(lines=_successful_lines())),
        citation_decoder=_EmptyVersionedCitationDecoder(boundary_version),
    ).retrieve(_query(), _context())
    assert len(boundary_raw.provider_contract_version) == 80
    assert boundary_raw.provider_contract_version == (
        f"{base_raw.provider_contract_version}+{boundary_version}"
    )

    with pytest.raises(ValueError, match="exceeds 80 characters"):
        _provider(
            _Transport(_Response(lines=_successful_lines())),
            citation_decoder=_EmptyVersionedCitationDecoder(
                "v" * (decoder_chars_at_boundary + 1)
            ),
        )


def test_descriptor_fingerprint_changes_with_decoder_and_nonsecret_config() -> None:
    base_descriptor = _provider(_Transport()).descriptor()
    decoder_descriptor = _provider(
        _Transport(),
        citation_decoder=_EmptyVersionedCitationDecoder("fingerprint_v1"),
    ).descriptor()
    configured_descriptor = FluffyJawsKnowledgeProvider(
        config=FluffyJawsProviderConfig(
            enabled=True,
            model="configured-model",
            fluffy_pack_slug="configured-pack",
        ),
        transport=_Transport(),
        now=lambda: _FIXED_NOW,
        call_id_factory=lambda: "fj-call-1",
    ).descriptor()

    fingerprints = {
        base_descriptor.configuration_fingerprint,
        decoder_descriptor.configuration_fingerprint,
        configured_descriptor.configuration_fingerprint,
    }
    assert len(fingerprints) == 3
    assert (
        len(
            {
                base_descriptor.configuration_digest,
                decoder_descriptor.configuration_digest,
                configured_descriptor.configuration_digest,
            }
        )
        == 3
    )


def test_decoder_backed_minimal_query_can_complete_with_success() -> None:
    decoder = _SyntheticCitationDecoder(include_source=True)
    result = EvidenceProviderExecutor().execute(
        _provider(
            _Transport(_Response(lines=_decoder_lines())),
            citation_decoder=decoder,
        ),
        _minimal_query(),
        _context(source_visible=True),
    )

    assert result.call_result.status == EvidenceProviderStatus.SUCCESS
    assert result.call_result.unsupported_filters == []
    assert result.call_result.accepted_evidence_count == 1
    assert len(result.evidence_bundle.records) == 1
    assert len(result.discovery_syntheses) == 1
    assert result.discovery_syntheses[0].derived_from == (
        result.call_result.accepted_evidence_ids
    )


def test_strict_provider_hit_redacts_version_and_repository_revision() -> None:
    hit = StrictProviderHit(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        source_reference="doc:safe-reference",
        source_locator="https://experienceleague.adobe.com/safe",
        text="Safe source text",
        source_version='api_key="version private value"',
        repository_revision='client_secret="revision private value"',
        raw_provider_reference="provider:safe-reference",
    )
    serialized = hit.model_dump_json()
    assert "version private value" not in serialized
    assert "revision private value" not in serialized
    assert "REDACTED" in serialized


@pytest.mark.parametrize("retrieval_score", [float("nan"), float("inf"), -float("inf")])
def test_strict_provider_hit_rejects_nonfinite_retrieval_score(
    retrieval_score: float,
) -> None:
    with pytest.raises(ValidationError, match="retrieval_score must be finite"):
        StrictProviderHit(
            source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
            source_reference="doc:safe-reference",
            source_locator="https://experienceleague.adobe.com/safe",
            text="Safe source text",
            retrieval_score=retrieval_score,
            raw_provider_reference="provider:safe-reference",
        )


def test_httpx_transport_rejects_unapproved_url_before_client_call() -> None:
    class _FailIfCalledClient:
        def stream(self, *args, **kwargs):
            del args, kwargs
            raise AssertionError(
                "unapproved origin must not reach authenticated client"
            )

    request = FluffyJawsStreamRequest(
        url="https://attacker.invalid/api/v1/stream",
        json_body={"messages": [{"role": "user", "content": "question"}]},
        timeout_seconds=10.0,
        correlation_id="local-correlation",
    )
    with pytest.raises(ValueError, match="approved stream URL"):
        HttpxFluffyJawsTransport(_FailIfCalledClient()).stream(request)


def test_no_newline_raw_byte_stream_is_bounded_before_sse_parsing() -> None:
    with pytest.raises(EvidenceProviderInvalidResponse) as raised:
        _provider(
            _Transport(_Response(lines=[b"x" * 51])),
            max_stream_chars=50,
        ).retrieve(_minimal_query(), _context())
    assert raised.value.redacted_error_code == "response_too_large"


@pytest.mark.parametrize("retryable", ["false", 0, 1, None])
def test_error_event_requires_json_boolean_retryable(retryable: object) -> None:
    event = {
        "type": "error",
        "message": "safe upstream failure",
        "retryable": retryable,
    }
    with pytest.raises(EvidenceProviderInvalidResponse) as raised:
        _provider(_Transport(_Response(lines=_sse_event(event)))).retrieve(
            _minimal_query(), _context()
        )
    assert raised.value.redacted_error_code == "invalid_response"


def test_decoder_result_is_discarded_when_total_deadline_expires() -> None:
    class _ExpiringContext:
        correlation_id = "corr-fj-1"

        def __init__(self) -> None:
            self.expired = False

        def cancelled(self) -> bool:
            return False

        def remaining_seconds(self) -> float:
            return 0.0 if self.expired else 30.0

    class _ExpiringDecoder(_SyntheticCitationDecoder):
        def __init__(self, context: _ExpiringContext) -> None:
            super().__init__(include_source=False)
            self.context = context

        def decode(self, events, *, final_response_id: str):
            decoded = super().decode(events, final_response_id=final_response_id)
            self.context.expired = True
            return decoded

    context = _ExpiringContext()
    provider = _provider(
        _Transport(_Response(lines=_decoder_lines())),
        citation_decoder=_ExpiringDecoder(context),
    )

    with pytest.raises(EvidenceProviderTimeout) as raised:
        provider.retrieve(_minimal_query(), context)
    assert raised.value.redacted_error_code == "timeout"


@pytest.mark.parametrize(
    "response_id",
    [
        "contains whitespace",
        "https://api.fluffyjaws.adobe.com/response/1",
        "line\nbreak",
        "control\x00character",
    ],
)
def test_completion_requires_bounded_opaque_response_id(response_id: str) -> None:
    with pytest.raises(EvidenceProviderInvalidResponse) as raised:
        _provider(
            _Transport(
                _Response(lines=_successful_lines(final_response_id=response_id))
            )
        ).retrieve(_minimal_query(), _context())
    assert raised.value.redacted_error_code == "invalid_response"


class _Fj05StaticCitationDecoder:
    contract_version = "fj05_normalization_v1"

    def __init__(self, *hits: StrictProviderHit) -> None:
        self.hits = tuple(hits)
        self.supported_source_types = tuple(
            sorted({hit.source_type for hit in hits}, key=lambda item: item.value)
        )

    def decode(self, events, *, final_response_id: str):
        del events, final_response_id
        return FluffyJawsDecodedEvidence(
            hits=self.hits,
            synthesis_hit_references=tuple(
                hit.raw_provider_reference for hit in self.hits
            ),
        )


def _fj05_query(
    *,
    max_results: int = 5,
    requested_evidence_types: list[EvidenceSourceType] | None = None,
    acceptable_classes: list[AuthorityClass] | None = None,
    authority_subject: AuthoritySubject = AuthoritySubject.PRODUCT_CONTRACT,
    jira_reference: str = "",
    excluded_sources: ExcludedSources | None = None,
) -> EvidenceQueryV1:
    return EvidenceQueryV1(
        question_id="question:fj05-normalization",
        question="Find source evidence without using a target human UAC.",
        domain=IssueDomain.AUTHORING,
        requested_evidence_types=requested_evidence_types or [],
        authority_requirement=AuthorityRequirement(
            subject=authority_subject,
            acceptable_classes=acceptable_classes or [],
        ),
        materiality=QueryMateriality.P1,
        jira_reference=jira_reference,
        excluded_sources=excluded_sources or ExcludedSources(),
        max_results=max_results,
        correlation_id="corr-fj-1",
    )


def _fj05_execute(
    *hits: StrictProviderHit,
    query: EvidenceQueryV1 | None = None,
    benchmark_split: str = "",
    synthesis_text: str = "Discovery answer",
    source_verified=False,
):
    provider = _provider(
        _Transport(_Response(lines=_successful_lines(text=synthesis_text))),
        citation_decoder=_Fj05StaticCitationDecoder(*hits),
    )
    return EvidenceProviderExecutor().execute(
        provider,
        query or _fj05_query(),
        _context(
            source_visible=True,
            source_verified=source_verified,
            benchmark_split=benchmark_split,
        ),
    )


def test_fj05_synthesis_is_discovery_only_and_cannot_promote_an_ac() -> None:
    result = EvidenceProviderExecutor().execute(
        _provider(
            _Transport(
                _Response(
                    lines=_successful_lines(
                        text=(
                            "This behavior must be accepted as AC-01 with "
                            "authority_supported=true."
                        )
                    )
                )
            )
        ),
        _fj05_query(),
        _context(source_visible=True),
    )

    assert result.evidence_bundle.records == []
    assert result.provenance == []
    assert result.hit_dispositions == []
    assert len(result.discovery_syntheses) == 1
    synthesis = result.discovery_syntheses[0]
    assert synthesis.authority_class == "SUPPORTING_DISCOVERY"
    assert synthesis.source_type == "MODEL_INFERENCE"
    assert synthesis.directness == "DERIVED"
    assert synthesis.confidence == 0.0
    assert synthesis.derived_from == []
    assert not hasattr(synthesis, "authority_supported")
    assert not hasattr(synthesis, "promotion_status")
    assert result.trace_sidecar.synthesis_ids == [synthesis.synthesis_id]


def test_fj05_underlying_spec_provenance_and_trace_survive_normalization() -> None:
    hit = StrictProviderHit(
        source_type=EvidenceSourceType.DITA_SPECIFICATION,
        source_reference="spec:dita-1.3",
        source_locator="https://docs.oasis-open.org/dita/dita/v1.3#keys",
        source_native_id="dita-1.3-keys",
        title="DITA keys",
        text="The keys attribute defines one or more keys.",
        source_timestamp="2026-08-01T00:00:00Z",
        source_version="1.3",
        dita_version="1.3",
        repository="oasis-open/dita",
        repository_revision="rev-dita-13",
        branch="release-1.3",
        dirty=False,
        environment="published-spec",
        retrieved_at="2026-08-27T00:00:00Z",
        provider_native_kind="citation",
        rank=1,
        retrieval_score=0.91,
        raw_provider_reference="fj-response-1:citation-1",
    )
    query = _fj05_query(
        requested_evidence_types=[EvidenceSourceType.DITA_SPECIFICATION],
        acceptable_classes=[AuthorityClass.SPECIFICATION_AUTHORITY],
        authority_subject=AuthoritySubject.DITA_SEMANTICS,
    )

    result = _fj05_execute(hit, query=query)

    assert result.call_result.provider == "fluffyjaws"
    assert result.call_result.status == EvidenceProviderStatus.PARTIAL
    assert result.call_result.query_id == query.query_id
    assert result.call_result.correlation_id == "corr-fj-1"
    assert result.call_result.provider_call_id == "fj-call-1"
    assert result.call_result.raw_provider_reference == "resp-final-1"
    assert len(result.evidence_bundle.records) == 1
    record = result.evidence_bundle.records[0]
    assert record.source_type == EvidenceSourceType.DITA_SPECIFICATION
    assert record.source_reference == "spec:dita-1.3"
    assert record.source_location.endswith("#keys")
    assert record.source_native_id == "dita-1.3-keys"
    assert record.content == {
        "text": "The keys attribute defines one or more keys.",
        "title": "DITA keys",
    }
    assert record.source_timestamp == "2026-08-01T00:00:00Z"
    assert record.authority_subject == AuthoritySubject.DITA_SEMANTICS
    assert record.requirement_authority == AuthorityClass.SPECIFICATION_AUTHORITY
    assert record.verification_status == VerificationState.UNVERIFIED
    assert record.evidence_confidence == 0.0
    assert record.currentness == CurrentnessState.VERSION_SPECIFIC
    assert record.product_version == "1.3"
    assert record.dita_version == "1.3"
    assert record.version_scope.repository_revision == "rev-dita-13"
    assert record.version_scope.repository == "oasis-open/dita"
    assert record.version_scope.branch == "release-1.3"
    assert record.version_scope.dirty is False
    assert record.version_scope.environment == "published-spec"
    assert record.version_scope.retrieved_at == "2026-08-27T00:00:00Z"
    provenance = result.provenance[0]
    assert provenance.evidence_id == record.evidence_id
    assert provenance.provider == "fluffyjaws"
    assert provenance.provider_contract_version.endswith("+fj05_normalization_v1")
    assert provenance.provider_call_id == "fj-call-1"
    assert provenance.query_id == query.query_id
    assert provenance.correlation_id == "corr-fj-1"
    assert provenance.raw_provider_reference == "fj-response-1:citation-1"
    assert provenance.applicability == ApplicabilityState.APPLICABLE
    assert provenance.rank == 1
    assert provenance.retrieval_score == 0.91
    assert result.hit_dispositions[0].accepted is True
    assert result.hit_dispositions[0].reason_code == "ACCEPTED"
    trace = result.trace_sidecar
    assert trace.run_id == "run-fj-test"
    assert trace.request_id == "request-fj-test"
    assert trace.provider == "fluffyjaws"
    assert trace.question_id == query.question_id
    assert trace.query_id == query.query_id
    assert trace.evidence_ids == [record.evidence_id]
    assert trace.provenance_ids == [provenance.provenance_id]
    assert trace.provider_result_id == result.call_result.provider_result_id
    assert trace.disposition_ids == [result.hit_dispositions[0].disposition_id]
    assert trace.synthesis_ids == [result.discovery_syntheses[0].synthesis_id]
    assert result.discovery_syntheses[0].derived_from == [record.evidence_id]


def test_fj05_authority_subject_must_match_the_underlying_source() -> None:
    hit = StrictProviderHit(
        source_type=EvidenceSourceType.DITA_SPECIFICATION,
        source_reference="spec:dita-subject-mismatch",
        source_locator="https://docs.oasis-open.org/dita/dita/v1.3#subject",
        text="A DITA-semantic fact cannot satisfy a product-contract query.",
        raw_provider_reference="fj-subject:item-1",
    )

    result = _fj05_execute(hit, query=_fj05_query())

    assert result.evidence_bundle.records == []
    assert result.provenance == []
    assert result.hit_dispositions[0].reason_code == "AUTHORITY_SUBJECT_MISMATCH"


def test_fj05_unknown_source_never_becomes_authoritative() -> None:
    hit = StrictProviderHit(
        source_type=EvidenceSourceType.UNKNOWN,
        source_reference="unknown:source-1",
        source_locator="unknown:source-1#line-1",
        text="An unattributed result claims this behavior is required.",
        raw_provider_reference="fj-response-unknown:item-1",
    )

    result = _fj05_execute(hit)

    record = result.evidence_bundle.records[0]
    assert record.requirement_authority == AuthorityClass.UNKNOWN
    assert record.verification_status == VerificationState.UNVERIFIED
    assert record.evidence_confidence == 0.0


def test_fj05_conflicting_source_claims_remain_separate_records() -> None:
    common = {
        "source_type": EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        "source_reference": "doc:output-behavior",
        "source_locator": "https://experienceleague.adobe.com/output#behavior",
        "source_native_id": "output-behavior",
        "title": "Output behavior",
    }
    first = StrictProviderHit(
        **common,
        text="The output keeps the previous page.",
        raw_provider_reference="fj-conflict:item-1",
    )
    second = StrictProviderHit(
        **common,
        text="The output removes the previous page.",
        raw_provider_reference="fj-conflict:item-2",
    )

    result = _fj05_execute(first, second)

    assert result.call_result.status == EvidenceProviderStatus.SUCCESS
    assert result.call_result.accepted_evidence_count == 2
    assert len({record.evidence_id for record in result.evidence_bundle.records}) == 2
    assert {record.content["text"] for record in result.evidence_bundle.records} == {
        "The output keeps the previous page.",
        "The output removes the previous page.",
    }
    assert len(result.provenance) == 2
    assert all(row.accepted for row in result.hit_dispositions)
    assert all(
        record.requirement_authority == AuthorityClass.OFFICIAL_PRODUCT_CONTRACT
        for record in result.evidence_bundle.records
    )


def test_fj14_unique_evidence_survives_duplicate_hits_before_result_limit() -> None:
    duplicate = StrictProviderHit(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        source_reference="doc:dedupe-a",
        source_locator="https://experienceleague.adobe.com/dedupe#a",
        source_native_id="dedupe-a",
        title="Repeated source fact",
        text="The first source defines behavior A.",
        rank=1,
        raw_provider_reference="fj-dedupe:item-1",
    )
    repeated = duplicate.model_copy(
        update={
            "rank": 2,
            "raw_provider_reference": "fj-dedupe:item-2",
        }
    )
    unique = StrictProviderHit(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        source_reference="doc:dedupe-b",
        source_locator="https://experienceleague.adobe.com/dedupe#b",
        source_native_id="dedupe-b",
        title="Unique source fact",
        text="The second source defines behavior B.",
        rank=3,
        raw_provider_reference="fj-dedupe:item-3",
    )

    result = _fj05_execute(
        duplicate,
        repeated,
        unique,
        query=_fj05_query(max_results=2),
    )

    assert result.call_result.truncated is False
    assert result.call_result.accepted_evidence_count == 2
    assert {record.source_reference for record in result.evidence_bundle.records} == {
        "doc:dedupe-a",
        "doc:dedupe-b",
    }
    assert {row.raw_provider_reference for row in result.provenance} == {
        "fj-dedupe:item-1",
        "fj-dedupe:item-2",
        "fj-dedupe:item-3",
    }


def test_fj14_decoder_hard_capacity_remains_bounded() -> None:
    hits = tuple(
        StrictProviderHit(
            source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
            source_reference=f"doc:capacity-{index}",
            source_locator=f"https://experienceleague.adobe.com/capacity#{index}",
            source_native_id=f"capacity-{index}",
            text=f"Bounded source fact {index}.",
            rank=index,
            raw_provider_reference=f"fj-capacity:item-{index}",
        )
        for index in range(1, 102)
    )
    provider = _provider(
        _Transport(_Response(lines=_successful_lines())),
        citation_decoder=_Fj05StaticCitationDecoder(*hits),
    )

    raw = provider.retrieve(_fj05_query(max_results=100), _context())

    assert len(raw.raw_hits) == 100
    assert raw.truncated is True
    assert raw.raw_hits[-1].raw_provider_reference == "fj-capacity:item-100"
    assert all(
        hit.raw_provider_reference != "fj-capacity:item-101" for hit in raw.raw_hits
    )


def test_fj05_rediscovery_time_does_not_create_a_false_source_conflict() -> None:
    first_hit = StrictProviderHit(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        source_reference="doc:stable-source",
        source_locator="https://experienceleague.adobe.com/stable#source",
        source_native_id="stable-source",
        text="The same independently inspectable source fact.",
        retrieved_at="2026-08-26T00:00:00Z",
        raw_provider_reference="fj-rediscovery:item-1",
    )
    second_hit = first_hit.model_copy(
        update={
            "retrieved_at": "2026-08-27T00:00:00Z",
            "raw_provider_reference": "fj-rediscovery:item-2",
        }
    )
    query = _fj05_query()
    executor = EvidenceProviderExecutor()
    first = executor.execute(
        _provider(
            _Transport(_Response(lines=_successful_lines())),
            citation_decoder=_Fj05StaticCitationDecoder(first_hit),
        ),
        query,
        _context(source_visible=True),
    )

    second = executor.execute(
        _provider(
            _Transport(_Response(lines=_successful_lines())),
            citation_decoder=_Fj05StaticCitationDecoder(second_hit),
        ),
        query,
        _context(source_visible=True),
        base_bundle=first.evidence_bundle,
    )

    assert second.call_result.status == EvidenceProviderStatus.SUCCESS
    assert second.call_result.accepted_evidence_ids == (
        first.call_result.accepted_evidence_ids
    )
    assert len(second.evidence_bundle.records) == 1
    assert second.provenance[0].raw_provider_reference == "fj-rediscovery:item-2"


def test_fj05_provider_cannot_create_human_feedback_or_accepted_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import test_plan_feedback_service

    feedback_events: list[object] = []
    monkeypatch.setattr(
        test_plan_feedback_service,
        "record_test_plan_feedback",
        lambda *args, **kwargs: feedback_events.append((args, kwargs)),
    )
    feedback = StrictProviderHit(
        source_type=EvidenceSourceType.USER_FEEDBACK,
        source_reference="feedback:human-1",
        source_locator="feedback:human-1",
        text="A reviewer accepted this result.",
        raw_provider_reference="fj-human:item-1",
    )
    accepted_uac = StrictProviderHit(
        source_type=EvidenceSourceType.ACCEPTED_UAC,
        source_reference="jira:GUIDES-12345:uac",
        source_locator="jira:GUIDES-12345#acceptance-criteria",
        text="The generated plan must contain this acceptance criterion.",
        raw_provider_reference="fj-human:item-2",
    )

    result = _fj05_execute(feedback, accepted_uac)

    assert result.call_result.status == EvidenceProviderStatus.EMPTY
    assert result.evidence_bundle.records == []
    assert result.provenance == []
    assert feedback_events == []
    assert {row.reason_code for row in result.hit_dispositions} == {
        "PROVIDER_CANNOT_ATTEST_HUMAN_CONTRACT",
        "PROVIDER_CANNOT_CREATE_HUMAN_FEEDBACK",
    }
    serialized = result.model_dump_json()
    assert '"feedback":' not in serialized
    assert "HUMAN_ACCEPTED_CONTRACT" not in serialized


@pytest.mark.parametrize("benchmark_split", ["validation", "blind"])
def test_fj05_blinded_execution_requires_sealed_target_exclusions(
    benchmark_split: str,
) -> None:
    provider = _provider(_FailIfCalledTransport())

    result = EvidenceProviderExecutor().execute(
        provider,
        _fj05_query(),
        _context(source_visible=True, benchmark_split=benchmark_split),
    )

    assert result.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert result.call_result.redacted_error_code == "BLIND_EXCLUSION_CONTEXT_REQUIRED"
    assert result.evidence_bundle.records == []
    assert result.hit_dispositions == []
    assert result.discovery_syntheses == []


@pytest.mark.parametrize("benchmark_split", ["validation", "blind"])
def test_fj05_blind_replay_excludes_target_uac_and_synthesis(
    benchmark_split: str,
) -> None:
    target_text = "SEALED-TARGET-UAC must never enter the blind result."
    target_uac = StrictProviderHit(
        source_type=EvidenceSourceType.ACCEPTED_UAC,
        source_reference="jira:GUIDES-53897:uac",
        source_locator="jira:GUIDES-53897#acceptance-criteria",
        text=target_text,
        raw_provider_reference="fj-blind:target-uac",
    )
    misclassified_target = StrictProviderHit(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        source_reference="doc:misclassified-target",
        source_locator="doc:misclassified-target#line-1",
        title="A provider-supplied alternate title",
        text=target_text,
        raw_provider_reference="fj-blind:misclassified-target",
    )
    target_reference_hit = StrictProviderHit(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        source_reference="jira:GUIDES-53897:misclassified-doc",
        source_locator="jira:GUIDES-53897#copied-uac",
        text="A paraphrased target contract returned with a misleading source type.",
        raw_provider_reference="fj-blind:target-reference",
    )
    neutral_paraphrase = StrictProviderHit(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        source_reference="doc:neutral-reference",
        source_locator="doc:neutral-reference#line-1",
        text="A rewritten target contract with no target Jira identifier.",
        raw_provider_reference="fj-blind:neutral-paraphrase",
    )
    safe_spec = StrictProviderHit(
        source_type=EvidenceSourceType.DITA_SPECIFICATION,
        source_reference="spec:dita-1.3-safe",
        source_locator="https://docs.oasis-open.org/dita/dita/v1.3#safe",
        text="A source-native DITA specification fact.",
        dita_version="1.3",
        raw_provider_reference="fj-blind:safe-spec",
    )
    query = _fj05_query(
        authority_subject=AuthoritySubject.DITA_SEMANTICS,
        jira_reference="jira:GUIDES-53897",
        excluded_sources=ExcludedSources(
            content_sha256=[provider_hit_content_sha256(target_uac)]
        ),
    )

    result = _fj05_execute(
        target_uac,
        misclassified_target,
        target_reference_hit,
        neutral_paraphrase,
        safe_spec,
        query=query,
        benchmark_split=benchmark_split,
        synthesis_text=target_text,
        source_verified=lambda hit: (
            hit.source_reference
            in {
                "doc:misclassified-target",
                "jira:GUIDES-53897:misclassified-doc",
                "spec:dita-1.3-safe",
            }
        ),
    )

    assert [record.source_reference for record in result.evidence_bundle.records] == [
        "spec:dita-1.3-safe"
    ]
    assert [row.raw_provider_reference for row in result.provenance] == [
        "fj-blind:safe-spec"
    ]
    assert result.discovery_syntheses == []
    assert result.call_result.rejected_hit_count == 0
    rejected = [row for row in result.hit_dispositions if not row.accepted]
    assert rejected == []
    assert len(result.hit_dispositions) == 1
    assert result.hit_dispositions[0].accepted is True
    serialized = result.model_dump_json()
    assert target_text not in serialized
    assert "GUIDES-53897" not in serialized
    assert "fj-blind:target-uac" not in serialized
    assert "fj-blind:target-reference" not in serialized
    assert "fj-blind:neutral-paraphrase" not in serialized
    assert provider_hit_content_sha256(target_uac) not in serialized
    assert result.trace_sidecar.synthesis_ids == []
