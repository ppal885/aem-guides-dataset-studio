"""Focused FJ-09 retry, cache, and circuit-breaker contract tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from time import sleep

from app.core.schemas_canonical_test_plan_runtime import (
    AuthoritySubject,
    CurrentnessState,
    EvidenceSourceType,
    IssueDomain,
    RuntimePrincipal,
    VersionScope,
)
from app.services.reasoning_evidence_provider import (
    AuthorityRequirement,
    EvidenceProviderAuthError,
    EvidenceProviderDescriptor,
    EvidenceProviderException,
    EvidenceProviderExecutionContext,
    EvidenceProviderExecutor,
    EvidenceProviderRateLimited,
    EvidenceProviderRawResult,
    EvidenceProviderStatus,
    EvidenceQueryV1,
    ExcludedSources,
    ProviderCacheState,
    ProviderCircuitState,
    ProviderTransportOutcome,
    QueryMateriality,
    StrictProviderHit,
    TemporalBoundary,
    active_query_filters,
)
from app.services.reasoning_evidence_resilience import (
    PROVIDER_CACHE_SCHEMA_VERSION,
    EvidenceProviderResilienceController,
    InMemoryProviderEvidenceCache,
    ProviderCircuitBreaker,
    ProviderResiliencePolicy,
)


_STAMP = "2026-08-30T06:00:00Z"
_PROVIDER = "fluffyjaws"
_CONTRACT = "fake-fj09-v1"


@dataclass
class _ManualClock:
    value: float = 1_000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


ProviderAction = (
    Callable[
        [EvidenceQueryV1, EvidenceProviderExecutionContext],
        EvidenceProviderRawResult,
    ]
    | Exception
)


class _SequenceProvider:
    """Deterministic provider whose actions are consumed only on real dispatch."""

    def __init__(
        self,
        actions: list[ProviderAction],
        *,
        descriptor: EvidenceProviderDescriptor | None = None,
    ) -> None:
        self._descriptor = descriptor or _descriptor()
        self._actions = list(actions)
        self.calls: list[tuple[str, str]] = []

    def descriptor(self) -> EvidenceProviderDescriptor:
        return self._descriptor

    def retrieve(
        self,
        query: EvidenceQueryV1,
        context: EvidenceProviderExecutionContext,
    ) -> EvidenceProviderRawResult:
        self.calls.append((query.query_id, context.correlation_id))
        if not self._actions:
            raise AssertionError("provider received an unexpected extra call")
        action = self._actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action(query, context)


def _descriptor(*, contract: str = _CONTRACT) -> EvidenceProviderDescriptor:
    return EvidenceProviderDescriptor(
        provider=_PROVIDER,
        adapter_version="fake-fj09-v1",
        provider_contract_version=contract,
        supported_domains=[IssueDomain.AUTHORING],
        supported_source_types=[
            EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION
        ],
        supported_filters=[
            "authority_requirement",
            "excluded_sources",
            "jira_or_context_reference",
            "max_results",
            "requested_evidence_types",
            "temporal_boundary",
        ],
        maximum_results=5,
    )


def _query(*, correlation_id: str = "corr-fj09") -> EvidenceQueryV1:
    return EvidenceQueryV1(
        question_id="question:fj09-resilience",
        question="Which official source defines the current behavior?",
        domain=IssueDomain.AUTHORING,
        requested_evidence_types=[
            EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION
        ],
        materiality=QueryMateriality.P1,
        authority_requirement=AuthorityRequirement(
            subject=AuthoritySubject.PRODUCT_CONTRACT,
            direct_source_required=True,
        ),
        jira_reference="jira:GUIDES-FJ09",
        temporal_boundary=TemporalBoundary(
            version_scope=VersionScope(),
            allowed_currentness=[CurrentnessState.VERSION_UNKNOWN],
        ),
        excluded_sources=ExcludedSources(),
        max_results=2,
        correlation_id=correlation_id,
    )


def _context(
    *,
    correlation_id: str = "corr-fj09",
    tenant_id: str = "fj09-tenant",
    principal_id: str = "fj09-user",
) -> EvidenceProviderExecutionContext:
    return EvidenceProviderExecutionContext(
        principal=RuntimePrincipal(
            principal_id=principal_id,
            tenant_id=tenant_id,
            roles=["authenticated"],
        ),
        run_id="run-fj09",
        request_id="request-fj09",
        correlation_id=correlation_id,
        timeout_seconds=30.0,
        source_visibility_check=lambda _hit: True,
        source_verification_check=lambda _hit: True,
    )


def _hit(
    *,
    text: str = "The current behavior is defined by the official product guide.",
    raw_provider_reference: str = "fj09-source-item",
) -> StrictProviderHit:
    return StrictProviderHit(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        source_reference="doc:https://experienceleague.adobe.com/fj09",
        source_locator="https://experienceleague.adobe.com/fj09#behavior",
        source_native_id="fj09-doc-1",
        title="Official behavior",
        text=text,
        rank=1,
        retrieval_score=0.95,
        raw_provider_reference=raw_provider_reference,
    )


def _raw_factory(
    *,
    outcome: ProviderTransportOutcome = ProviderTransportOutcome.COMPLETED,
    hits: list[StrictProviderHit] | None = None,
    retryable: bool = False,
    message: str = "",
) -> Callable[
    [EvidenceQueryV1, EvidenceProviderExecutionContext],
    EvidenceProviderRawResult,
]:
    def build(
        query: EvidenceQueryV1,
        context: EvidenceProviderExecutionContext,
    ) -> EvidenceProviderRawResult:
        return EvidenceProviderRawResult(
            provider=_PROVIDER,
            provider_contract_version=_CONTRACT,
            provider_call_id=EvidenceProviderExecutor._call_id(
                _PROVIDER,
                query.query_id,
                context.correlation_id,
            ),
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            raw_hits=list(hits or []),
            transport_outcome=outcome,
            applied_filters=active_query_filters(query),
            attempts=1,
            started_at=_STAMP,
            completed_at=_STAMP,
            duration_ms=4,
            retryable=retryable,
            redacted_message=message,
        )

    return build


def _controller(
    *,
    clock: _ManualClock | None = None,
    max_attempts: int = 2,
    cache_enabled: bool = False,
    cache_ttl_seconds: float = 60.0,
    circuit_failure_threshold: int = 20,
    circuit_cooldown_seconds: float = 30.0,
) -> EvidenceProviderResilienceController:
    active_clock = clock or _ManualClock()
    return EvidenceProviderResilienceController(
        policy=ProviderResiliencePolicy(
            max_attempts=max_attempts,
            cache_enabled=cache_enabled,
            cache_ttl_seconds=cache_ttl_seconds,
            circuit_failure_threshold=circuit_failure_threshold,
            circuit_cooldown_seconds=circuit_cooldown_seconds,
        ),
        clock=active_clock,
    )


def _execute(
    controller: EvidenceProviderResilienceController,
    provider: _SequenceProvider,
    *,
    query: EvidenceQueryV1 | None = None,
    context: EvidenceProviderExecutionContext | None = None,
):
    active_query = query or _query()
    active_context = context or _context(
        correlation_id=active_query.correlation_id
    )
    return EvidenceProviderExecutor().execute(
        controller.wrap(provider),
        active_query,
        active_context,
        resilience_metadata_trusted=True,
    )


def test_timeout_retry_recovers_within_the_configured_bound() -> None:
    provider = _SequenceProvider(
        [
            TimeoutError("Authorization=Bearer timeout-secret"),
            _raw_factory(hits=[_hit()]),
        ]
    )

    result = _execute(_controller(max_attempts=2), provider)

    assert len(provider.calls) == 2
    assert result.call_result.status == EvidenceProviderStatus.SUCCESS
    assert result.call_result.attempts == 2
    assert result.call_result.attempt_outcomes == [
        ProviderTransportOutcome.TIMEOUT,
        ProviderTransportOutcome.COMPLETED,
    ]
    assert result.call_result.accepted_evidence_count == 1
    assert "timeout-secret" not in result.model_dump_json()


def test_repeated_timeout_stops_at_the_configured_attempt_limit() -> None:
    provider = _SequenceProvider(
        [TimeoutError("first timeout"), TimeoutError("second timeout")]
    )

    result = _execute(_controller(max_attempts=2), provider)

    assert len(provider.calls) == 2
    assert result.call_result.status == EvidenceProviderStatus.TIMEOUT
    assert result.call_result.attempts == 2
    assert result.call_result.attempt_outcomes == [
        ProviderTransportOutcome.TIMEOUT,
        ProviderTransportOutcome.TIMEOUT,
    ]
    assert result.call_result.accepted_evidence_ids == []
    assert result.evidence_bundle.records == []
    assert result.provenance == []
    assert result.discovery_syntheses == []


def test_late_completion_is_not_cached_or_recorded_as_success() -> None:
    def complete_after_deadline(query, context):
        sleep(0.03)
        return _raw_factory(hits=[_hit()])(query, context)

    provider = _SequenceProvider(
        [complete_after_deadline, _raw_factory(hits=[_hit()])]
    )
    controller = _controller(max_attempts=1, cache_enabled=True)

    timed_out = _execute(
        controller,
        provider,
        context=replace(_context(), timeout_seconds=0.01),
    )
    assert timed_out.call_result.status == EvidenceProviderStatus.TIMEOUT
    assert timed_out.call_result.cache_state != ProviderCacheState.HIT
    assert len(controller.cache) == 0

    recovered = _execute(controller, provider)

    assert recovered.call_result.status == EvidenceProviderStatus.SUCCESS
    assert recovered.call_result.cache_state == ProviderCacheState.MISS
    assert len(controller.cache) == 1
    assert len(provider.calls) == 2


def test_auth_failure_is_not_retried_or_cached() -> None:
    secret = "auth-secret-value"
    provider = _SequenceProvider(
        [
            EvidenceProviderAuthError(
                f"Authorization=Bearer {secret}",
                retryable=True,
            ),
            _raw_factory(hits=[_hit()]),
        ]
    )
    controller = _controller(max_attempts=3, cache_enabled=True)

    result = _execute(controller, provider)

    assert len(provider.calls) == 1
    assert result.call_result.status == EvidenceProviderStatus.AUTH_ERROR
    assert result.call_result.attempts == 1
    assert result.call_result.retryable is False
    assert result.evidence_bundle.records == []
    assert len(controller.cache) == 0
    assert secret not in result.model_dump_json()


def test_rate_limit_is_structured_without_an_unsafe_immediate_retry() -> None:
    provider = _SequenceProvider(
        [
            EvidenceProviderRateLimited(
                "rate limited; retry later",
                retryable=True,
            ),
            _raw_factory(hits=[_hit()]),
        ]
    )

    result = _execute(_controller(max_attempts=3), provider)

    assert len(provider.calls) == 1
    assert result.call_result.status == EvidenceProviderStatus.RATE_LIMITED
    assert result.call_result.attempts == 1
    assert result.call_result.attempt_outcomes == [
        ProviderTransportOutcome.RATE_LIMITED
    ]
    assert result.call_result.retryable is False
    assert result.evidence_bundle.records == []


def test_explicitly_retryable_provider_error_can_recover() -> None:
    provider = _SequenceProvider(
        [
            EvidenceProviderException(
                "temporary provider failure",
                error_code="TEMPORARY_PROVIDER_FAILURE",
                retryable=True,
            ),
            _raw_factory(hits=[_hit()]),
        ]
    )

    result = _execute(_controller(max_attempts=2), provider)

    assert len(provider.calls) == 2
    assert result.call_result.status == EvidenceProviderStatus.SUCCESS
    assert result.call_result.attempts == 2
    assert result.call_result.attempt_outcomes == [
        ProviderTransportOutcome.PROVIDER_ERROR,
        ProviderTransportOutcome.COMPLETED,
    ]
    assert result.call_result.accepted_evidence_count == 1


def test_adapter_cannot_spoof_attempt_counts_across_retries() -> None:
    def claimed_timeout(query, context):
        return _raw_factory(
            outcome=ProviderTransportOutcome.TIMEOUT,
            retryable=True,
        )(query, context).model_copy(
            update={
                "attempts": 10,
                "attempt_outcomes": [ProviderTransportOutcome.TIMEOUT] * 10,
            }
        )

    def claimed_success(query, context):
        return _raw_factory(hits=[_hit()])(query, context).model_copy(
            update={
                "attempts": 10,
                "attempt_outcomes": [ProviderTransportOutcome.COMPLETED] * 10,
            }
        )

    provider = _SequenceProvider([claimed_timeout, claimed_success])

    result = _execute(_controller(max_attempts=2), provider)

    assert len(provider.calls) == 2
    assert result.call_result.attempts == 2
    assert result.call_result.attempt_outcomes == [
        ProviderTransportOutcome.TIMEOUT,
        ProviderTransportOutcome.COMPLETED,
    ]


def test_post_retry_contract_failure_is_structured_not_raised() -> None:
    def conflicting_filter_claims(query, context):
        raw = _raw_factory(hits=[_hit()])(query, context)
        active_filter = active_query_filters(query)[0]
        return raw.model_copy(
            update={
                "applied_filters": [active_filter],
                "unsupported_filters": [active_filter],
            }
        )

    provider = _SequenceProvider(
        [TimeoutError("first timeout"), conflicting_filter_claims]
    )

    result = _execute(_controller(max_attempts=2), provider)

    assert len(provider.calls) == 2
    assert result.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert result.call_result.redacted_error_code == "FILTER_CLAIM_CONFLICT"
    assert result.call_result.attempts == 2
    assert result.call_result.attempt_outcomes == [
        ProviderTransportOutcome.TIMEOUT,
        ProviderTransportOutcome.INVALID_RESPONSE,
    ]
    assert result.evidence_bundle.records == []


def test_invalid_completed_response_is_never_cached() -> None:
    def invalid_filter_claim(query, context):
        raw = _raw_factory(hits=[_hit()])(query, context)
        return raw.model_copy(update={"applied_filters": ["unknown-filter"]})

    provider = _SequenceProvider(
        [invalid_filter_claim, _raw_factory(hits=[_hit()])]
    )
    controller = _controller(cache_enabled=True, max_attempts=1)

    invalid = _execute(controller, provider)
    assert len(controller.cache) == 0
    recovered = _execute(controller, provider)

    assert invalid.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert invalid.call_result.redacted_error_code == "UNSUPPORTED_APPLIED_FILTER"
    assert len(controller.cache) == 1
    assert recovered.call_result.status == EvidenceProviderStatus.SUCCESS
    assert recovered.call_result.cache_state == ProviderCacheState.MISS
    assert len(provider.calls) == 2


def test_empty_injected_cache_is_preserved_by_identity() -> None:
    clock = _ManualClock()
    cache = InMemoryProviderEvidenceCache(clock=clock)
    controller = EvidenceProviderResilienceController(
        policy=ProviderResiliencePolicy(cache_enabled=True),
        cache=cache,
        clock=clock,
    )

    assert controller.cache is cache


def test_successful_cache_hit_avoids_transport_and_rebinds_the_call() -> None:
    provider = _SequenceProvider([_raw_factory(hits=[_hit()])])
    controller = _controller(cache_enabled=True, max_attempts=1)
    query = _query()
    context = _context(correlation_id=query.correlation_id)

    first = _execute(controller, provider, query=query, context=context)
    second = _execute(controller, provider, query=query, context=context)

    assert len(provider.calls) == 1
    assert first.call_result.cache_state == ProviderCacheState.MISS
    assert first.call_result.attempts == 1
    assert second.call_result.status == EvidenceProviderStatus.SUCCESS
    assert second.call_result.cache_state == ProviderCacheState.HIT
    assert second.call_result.cache_schema_version == PROVIDER_CACHE_SCHEMA_VERSION
    assert second.call_result.attempts == 0
    assert second.call_result.attempt_outcomes == []
    assert second.call_result.cache_served_at
    assert second.call_result.provider_call_id != first.call_result.provider_call_id
    assert (
        second.call_result.accepted_evidence_ids
        == first.call_result.accepted_evidence_ids
    )
    assert all(
        row.cache_state == ProviderCacheState.HIT for row in second.provenance
    )


def test_stale_cache_is_not_used_as_fallback_when_refresh_times_out() -> None:
    clock = _ManualClock()
    provider = _SequenceProvider(
        [
            _raw_factory(hits=[_hit()]),
            TimeoutError("refresh timeout"),
        ]
    )
    controller = _controller(
        clock=clock,
        cache_enabled=True,
        cache_ttl_seconds=5.0,
        max_attempts=1,
    )

    first = _execute(controller, provider)
    clock.advance(6.0)
    stale_refresh = _execute(controller, provider)

    assert first.call_result.status == EvidenceProviderStatus.SUCCESS
    assert len(provider.calls) == 2
    assert stale_refresh.call_result.status == EvidenceProviderStatus.TIMEOUT
    assert stale_refresh.call_result.cache_state == ProviderCacheState.STALE
    assert stale_refresh.call_result.cache_entry_age_seconds == 6.0
    assert stale_refresh.call_result.accepted_evidence_ids == []
    assert stale_refresh.evidence_bundle.records == []
    assert stale_refresh.provenance == []
    assert len(controller.cache) == 0


def test_live_cache_entry_cannot_be_replaced_by_a_late_completion() -> None:
    clock = _ManualClock()
    cache = InMemoryProviderEvidenceCache(clock=clock)
    query = _query()
    context = _context()
    first = _raw_factory(
        hits=[_hit(text="First completed source snapshot.")]
    )(query, context)
    late = _raw_factory(
        hits=[_hit(text="Late stale source snapshot.")]
    )(query, context)

    assert cache.store("provider-cache:race", first, ttl_seconds=60.0) is True
    assert cache.store("provider-cache:race", late, ttl_seconds=60.0) is False
    lookup = cache.lookup(
        "provider-cache:race",
        provider_contract_version=_CONTRACT,
    )

    assert lookup.raw is not None
    serialized = lookup.raw.model_dump_json()
    assert "First completed source snapshot." in serialized
    assert "Late stale source snapshot." not in serialized


def test_cache_enforces_entry_and_byte_bounds() -> None:
    clock = _ManualClock()
    oversized = _raw_factory(hits=[_hit(text="x" * 5_000)])(
        _query(),
        _context(),
    )
    byte_bounded = InMemoryProviderEvidenceCache(
        max_entries=2,
        max_bytes=1_024,
        clock=clock,
    )

    assert byte_bounded.store("provider-cache:large", oversized, ttl_seconds=60.0) is False
    assert len(byte_bounded) == 0

    entry_bounded = InMemoryProviderEvidenceCache(
        max_entries=1,
        max_bytes=16 * 1024,
        clock=clock,
    )
    first = _raw_factory(hits=[_hit(text="first")])(_query(), _context())
    second = _raw_factory(hits=[_hit(text="second")])(_query(), _context())
    assert entry_bounded.store("provider-cache:first", first, ttl_seconds=60.0)
    assert entry_bounded.store("provider-cache:second", second, ttl_seconds=60.0)
    assert len(entry_bounded) == 1
    assert entry_bounded.lookup(
        "provider-cache:first",
        provider_contract_version=_CONTRACT,
    ).state == ProviderCacheState.MISS
    assert entry_bounded.lookup(
        "provider-cache:second",
        provider_contract_version=_CONTRACT,
    ).state == ProviderCacheState.HIT


def test_cache_is_isolated_by_tenant_and_principal_scope() -> None:
    provider = _SequenceProvider(
        [
            _raw_factory(hits=[_hit()]),
            _raw_factory(hits=[_hit()]),
            _raw_factory(hits=[_hit()]),
        ]
    )
    controller = _controller(cache_enabled=True, max_attempts=1)
    query = _query()

    tenant_a_user_a = _context(
        correlation_id=query.correlation_id,
        tenant_id="tenant-a",
        principal_id="user-a",
    )
    tenant_b_user_b = _context(
        correlation_id=query.correlation_id,
        tenant_id="tenant-b",
        principal_id="user-b",
    )
    tenant_a_user_b = _context(
        correlation_id=query.correlation_id,
        tenant_id="tenant-a",
        principal_id="user-b",
    )

    first = _execute(
        controller,
        provider,
        query=query,
        context=tenant_a_user_a,
    )
    cross_tenant = _execute(
        controller,
        provider,
        query=query,
        context=tenant_b_user_b,
    )
    cross_principal = _execute(
        controller,
        provider,
        query=query,
        context=tenant_a_user_b,
    )
    original_scope = _execute(
        controller,
        provider,
        query=query,
        context=tenant_a_user_a,
    )

    assert first.call_result.cache_state == ProviderCacheState.MISS
    assert cross_tenant.call_result.cache_state == ProviderCacheState.MISS
    assert cross_principal.call_result.cache_state == ProviderCacheState.MISS
    assert original_scope.call_result.cache_state == ProviderCacheState.HIT
    assert len(provider.calls) == 3


def test_circuit_opens_suppresses_calls_and_recovers_after_half_open_probe() -> None:
    clock = _ManualClock()
    provider = _SequenceProvider(
        [
            TimeoutError("first outage"),
            TimeoutError("second outage"),
            _raw_factory(hits=[_hit()]),
            _raw_factory(hits=[_hit()]),
        ]
    )
    controller = _controller(
        clock=clock,
        max_attempts=1,
        circuit_failure_threshold=2,
        circuit_cooldown_seconds=5.0,
    )

    first = _execute(controller, provider)
    second = _execute(controller, provider)
    suppressed = _execute(controller, provider)

    assert first.call_result.circuit_state_after == ProviderCircuitState.CLOSED
    assert second.call_result.circuit_state_after == ProviderCircuitState.OPEN
    assert suppressed.call_result.status == EvidenceProviderStatus.PROVIDER_ERROR
    assert suppressed.call_result.redacted_error_code == "CIRCUIT_OPEN"
    assert suppressed.call_result.attempts == 0
    assert suppressed.call_result.circuit_state_before == ProviderCircuitState.OPEN
    assert suppressed.call_result.circuit_state_after == ProviderCircuitState.OPEN
    assert suppressed.evidence_bundle.records == []
    assert len(provider.calls) == 2

    clock.advance(6.0)
    recovered = _execute(controller, provider)
    after_recovery = _execute(controller, provider)

    assert len(provider.calls) == 4
    assert recovered.call_result.status == EvidenceProviderStatus.SUCCESS
    assert recovered.call_result.circuit_state_before == ProviderCircuitState.HALF_OPEN
    assert recovered.call_result.circuit_state_after == ProviderCircuitState.CLOSED
    assert after_recovery.call_result.status == EvidenceProviderStatus.SUCCESS
    assert after_recovery.call_result.circuit_state_before == ProviderCircuitState.CLOSED
    assert after_recovery.call_result.circuit_state_after == ProviderCircuitState.CLOSED


def test_cancelled_request_does_not_consume_half_open_recovery_probe() -> None:
    clock = _ManualClock()
    provider = _SequenceProvider(
        [TimeoutError("outage"), _raw_factory(hits=[_hit()])]
    )
    controller = _controller(
        clock=clock,
        max_attempts=1,
        circuit_failure_threshold=1,
        circuit_cooldown_seconds=5.0,
    )

    outage = _execute(controller, provider)
    assert outage.call_result.circuit_state_after == ProviderCircuitState.OPEN
    clock.advance(6.0)

    cancelled = _execute(
        controller,
        provider,
        context=replace(_context(), cancellation_check=lambda: True),
    )
    recovered = _execute(controller, provider)

    assert cancelled.call_result.redacted_error_code == "CANCELLED"
    assert cancelled.call_result.attempts == 0
    assert recovered.call_result.status == EvidenceProviderStatus.SUCCESS
    assert recovered.call_result.circuit_state_before == ProviderCircuitState.HALF_OPEN
    assert len(provider.calls) == 2


def test_half_open_probe_is_not_evicted_or_overwritten_by_late_completion() -> None:
    clock = _ManualClock()
    breaker = ProviderCircuitBreaker(
        failure_threshold=1,
        cooldown_seconds=5.0,
        max_entries=1,
        clock=clock,
    )
    original = breaker.acquire("protected-scope")
    assert breaker.record_failure(
        "protected-scope",
        permit=original,
    ) == ProviderCircuitState.OPEN

    clock.advance(6.0)
    probe = breaker.acquire("protected-scope")
    assert probe.allowed is True
    assert probe.state == ProviderCircuitState.HALF_OPEN

    # Key churn cannot evict the single active recovery probe.
    breaker.acquire("unrelated-scope")
    concurrent = breaker.acquire("protected-scope")
    assert concurrent.allowed is False
    assert concurrent.state == ProviderCircuitState.HALF_OPEN

    # A success from the old CLOSED generation cannot close the newer probe.
    assert breaker.record_success(
        "protected-scope",
        permit=original,
    ) == ProviderCircuitState.HALF_OPEN
    assert breaker.acquire("protected-scope").allowed is False

    assert breaker.record_success(
        "protected-scope",
        permit=probe,
    ) == ProviderCircuitState.CLOSED
    assert breaker.acquire("protected-scope").allowed is True


def test_cache_retains_only_validated_redacted_source_data() -> None:
    secret_text = "plain-cache-secret"
    secret_user = "cache-user"
    secret_password = "cache-password"
    hit = _hit(
        text=f"authorization={secret_text}",
        raw_provider_reference=(
            f"https://{secret_user}:{secret_password}@example.test/result"
        ),
    )
    raw = _raw_factory(hits=[hit])(_query(), _context())
    clock = _ManualClock()
    cache = InMemoryProviderEvidenceCache(clock=clock)

    assert cache.store("provider-cache:opaque", raw, ttl_seconds=60.0) is True
    lookup = cache.lookup(
        "provider-cache:opaque",
        provider_contract_version=_CONTRACT,
    )

    assert lookup.state == ProviderCacheState.HIT
    assert lookup.raw is not None
    serialized = lookup.raw.model_dump_json()
    for secret in (secret_text, secret_user, secret_password):
        assert secret not in serialized
    assert "REDACTED" in serialized
    assert lookup.raw.discovery_syntheses == []
    assert lookup.raw.raw_provider_reference == ""


def test_authorization_schemes_are_redacted_before_cache_admission() -> None:
    secrets = ("dXNlcjpwYXNz", "digest-user", "negotiate-token")
    hit = _hit(
        text=(
            "Authorization: Basic dXNlcjpwYXNz\n"
            'Authorization: Digest username="digest-user", realm="internal"\n'
            "Proxy-Authorization: Negotiate negotiate-token"
        )
    )
    raw = _raw_factory(hits=[hit])(_query(), _context())
    cache = InMemoryProviderEvidenceCache(clock=_ManualClock())

    assert cache.store("provider-cache:auth-schemes", raw, ttl_seconds=60.0)
    lookup = cache.lookup(
        "provider-cache:auth-schemes",
        provider_contract_version=_CONTRACT,
    )

    assert lookup.raw is not None
    serialized = lookup.raw.model_dump_json()
    assert all(secret not in serialized for secret in secrets)
    assert "REDACTED" in serialized


def test_signed_url_credentials_are_removed_before_trace_or_cache_admission() -> None:
    secrets = ("aws-secret", "azure-secret", "gcs-secret", "oauth-secret")
    hit = StrictProviderHit(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        source_reference=(
            "https://bucket.example.test/object?"
            "X-Amz-Signature=aws-secret&safe=kept"
        ),
        source_locator=(
            "https://storage.example.test/blob?sv=2026-01-01&sig=azure-secret"
            "#section-one"
        ),
        text=(
            "See https://storage.googleapis.test/object?"
            "X-Goog-Signature=gcs-secret&alt=media"
        ),
        raw_provider_reference=(
            "https://provider.example.test/result?access_token=oauth-secret"
        ),
    )
    raw = _raw_factory(hits=[hit])(_query(), _context())
    cache = InMemoryProviderEvidenceCache(clock=_ManualClock())

    assert cache.store("provider-cache:signed-url", raw, ttl_seconds=60.0) is True
    lookup = cache.lookup(
        "provider-cache:signed-url",
        provider_contract_version=_CONTRACT,
    )

    assert lookup.raw is not None
    serialized = lookup.raw.model_dump_json()
    assert all(secret not in serialized for secret in secrets)
    assert "X-Amz-Signature" not in serialized
    assert "sig=" not in serialized
    assert "X-Goog-Signature" not in serialized
    assert "access_token" not in serialized
    assert "safe=kept" in serialized
    assert "alt=media" in serialized
