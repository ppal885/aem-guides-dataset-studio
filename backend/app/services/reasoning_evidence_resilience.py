"""Provider-neutral retry, cache, and circuit-breaker controls.

The resilience layer wraps only the untrusted raw-provider call.  Cached rows
are therefore sent through the normal executor again, including visibility,
temporal, authority, and source-attestation checks.  The cache is in-memory,
bounded, versioned, access-scoped, and disabled unless explicitly enabled.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import re
from threading import RLock
from time import monotonic
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.schemas_canonical_test_plan_runtime import (
    CANONICAL_RUNTIME_ID,
    CANONICAL_RUNTIME_VERSION,
    stable_sha256,
)
from app.services.reasoning_evidence_provider import (
    EvidenceProvider,
    EvidenceProviderAuthError,
    EvidenceProviderCancelled,
    EvidenceProviderDescriptor,
    EvidenceProviderException,
    EvidenceProviderExecutionContext,
    EvidenceProviderInvalidResponse,
    EvidenceProviderRateLimited,
    EvidenceProviderRawResult,
    EvidenceProviderStatus,
    EvidenceProviderTimeout,
    EvidenceQueryV1,
    ProviderCacheState,
    ProviderCircuitState,
    ProviderTransportOutcome,
    active_query_filters,
)


PROVIDER_CACHE_SCHEMA_VERSION = "aem-guides-provider-cache-v1"

_OUTCOME_STATUS = {
    ProviderTransportOutcome.COMPLETED: EvidenceProviderStatus.SUCCESS,
    ProviderTransportOutcome.TIMEOUT: EvidenceProviderStatus.TIMEOUT,
    ProviderTransportOutcome.AUTH_ERROR: EvidenceProviderStatus.AUTH_ERROR,
    ProviderTransportOutcome.RATE_LIMITED: EvidenceProviderStatus.RATE_LIMITED,
    ProviderTransportOutcome.PROVIDER_ERROR: EvidenceProviderStatus.PROVIDER_ERROR,
    ProviderTransportOutcome.INVALID_RESPONSE: EvidenceProviderStatus.INVALID_RESPONSE,
}
_RETRYABLE_STATUSES = {
    EvidenceProviderStatus.TIMEOUT,
    EvidenceProviderStatus.PROVIDER_ERROR,
}
_CIRCUIT_FAILURE_STATUSES = {
    EvidenceProviderStatus.TIMEOUT,
    EvidenceProviderStatus.RATE_LIMITED,
    EvidenceProviderStatus.PROVIDER_ERROR,
}
_CACHE_SECRET_RE = re.compile(
    r"(?i)(?:"
    r"-----BEGIN[^\r\n]{0,40}PRIVATE KEY-----|"
    r"\b(?:AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{12,}\b|"
    r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{12,}\b|"
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b|"
    r"\b(?:authorization|proxy[_-]?authorization)\b[\"']?\s*[:=]\s*"
    r"(?:basic|bearer|digest|negotiate)\s+[^\r\n]{4,}|"
    r"\b(?:authorization|proxy[_-]?authorization|password|passwd|secret|"
    r"api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"private[_-]?key|cookie|set[_-]?cookie)\b\s*[:=]\s*"
    r"(?!\[REDACTED(?:-CREDENTIALS)?\])[^\s,;]{4,}|"
    r"[a-z][a-z0-9+.-]*://[^/@\s:]+:[^/@\s]+@"
    r")"
)


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ProviderResiliencePolicy(BaseModel):
    """Non-secret, bounded controls for one shared provider boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_attempts: int = Field(default=2, ge=1, le=3)
    cache_enabled: bool = False
    cache_ttl_seconds: float = Field(default=60.0, gt=0.0, le=3600.0)
    cache_max_entries: int = Field(default=128, ge=1, le=4096)
    cache_max_bytes: int = Field(
        default=16 * 1024 * 1024,
        ge=1024,
        le=64 * 1024 * 1024,
    )
    circuit_failure_threshold: int = Field(default=3, ge=1, le=20)
    circuit_cooldown_seconds: float = Field(default=30.0, gt=0.0, le=3600.0)
    circuit_max_entries: int = Field(default=512, ge=1, le=4096)


@dataclass(frozen=True, slots=True)
class ProviderCacheLookup:
    state: ProviderCacheState
    raw: EvidenceProviderRawResult | None = None
    age_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class _ProviderCacheEntry:
    schema_version: str
    provider_contract_version: str
    inserted_at: float
    expires_at: float
    size_bytes: int
    raw: EvidenceProviderRawResult


class InMemoryProviderEvidenceCache:
    """Small process-local cache containing only validated raw source hits."""

    def __init__(
        self,
        *,
        max_entries: int = 128,
        max_bytes: int = 16 * 1024 * 1024,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not 1 <= max_entries <= 4096:
            raise ValueError("cache max_entries must be between 1 and 4096")
        if not 1024 <= max_bytes <= 64 * 1024 * 1024:
            raise ValueError("cache max_bytes must be between 1024 and 67108864")
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._current_bytes = 0
        self._clock = clock
        self._entries: OrderedDict[str, _ProviderCacheEntry] = OrderedDict()
        self._lock = RLock()

    def lookup(
        self,
        key: str,
        *,
        provider_contract_version: str,
    ) -> ProviderCacheLookup:
        now = self._clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return ProviderCacheLookup(ProviderCacheState.MISS)
            age = max(0.0, now - entry.inserted_at)
            if (
                entry.schema_version != PROVIDER_CACHE_SCHEMA_VERSION
                or entry.provider_contract_version != provider_contract_version
                or now >= entry.expires_at
            ):
                removed = self._entries.pop(key, None)
                if removed is not None:
                    self._current_bytes -= removed.size_bytes
                return ProviderCacheLookup(
                    ProviderCacheState.STALE,
                    age_seconds=age,
                )
            self._entries.move_to_end(key)
            return ProviderCacheLookup(
                ProviderCacheState.HIT,
                raw=entry.raw.model_copy(deep=True),
                age_seconds=age,
            )

    def store(
        self,
        key: str,
        raw: EvidenceProviderRawResult,
        *,
        ttl_seconds: float,
    ) -> bool:
        candidate = self._cache_candidate(raw)
        if candidate is None:
            return False
        serialized = candidate.model_dump_json().encode("utf-8")
        size_bytes = len(serialized)
        if size_bytes > self._max_bytes:
            return False
        now = self._clock()
        entry = _ProviderCacheEntry(
            schema_version=PROVIDER_CACHE_SCHEMA_VERSION,
            provider_contract_version=candidate.provider_contract_version,
            inserted_at=now,
            expires_at=now + ttl_seconds,
            size_bytes=size_bytes,
            raw=candidate,
        )
        with self._lock:
            prior = self._entries.get(key)
            if (
                prior is not None
                and prior.schema_version == PROVIDER_CACHE_SCHEMA_VERSION
                and prior.provider_contract_version
                == candidate.provider_contract_version
                and now < prior.expires_at
            ):
                # First valid completion wins until expiry. A slower concurrent
                # response cannot refresh the TTL or replace a newer snapshot.
                return False
            prior = self._entries.pop(key, None)
            if prior is not None:
                self._current_bytes -= prior.size_bytes
            self._entries[key] = entry
            self._current_bytes += entry.size_bytes
            self._entries.move_to_end(key)
            while (
                len(self._entries) > self._max_entries
                or self._current_bytes > self._max_bytes
            ):
                _evicted_key, evicted = self._entries.popitem(last=False)
                self._current_bytes -= evicted.size_bytes
        return True

    @staticmethod
    def _cache_candidate(
        raw: EvidenceProviderRawResult,
    ) -> EvidenceProviderRawResult | None:
        # No negative, partial, discovery-only, or error result is admitted.
        if (
            raw.transport_outcome != ProviderTransportOutcome.COMPLETED
            or not raw.raw_hits
            or raw.truncated
            or raw.unsupported_filters
            or raw.redacted_error_code
            or raw.redacted_message
        ):
            return None
        payload = raw.model_dump(mode="json")
        payload.update(
            {
                "provider_call_id": "cache-source-snapshot",
                "raw_provider_reference": "",
                "discovery_syntheses": [],
                "discovery_synthesis_hit_references": {},
                "attempts": 0,
                "attempt_outcomes": [],
                "started_at": "",
                "completed_at": "",
                "cache_served_at": "",
                "duration_ms": 0,
                "cache_state": ProviderCacheState.BYPASS.value,
                "cache_schema_version": PROVIDER_CACHE_SCHEMA_VERSION,
                "cache_entry_age_seconds": None,
                "circuit_state_before": ProviderCircuitState.CLOSED.value,
                "circuit_state_after": ProviderCircuitState.CLOSED.value,
                "retryable": False,
                "redacted_error_code": "",
                "redacted_message": "",
                "redacted_required_action": "",
            }
        )
        try:
            candidate = EvidenceProviderRawResult.model_validate(payload)
        except ValidationError:
            return None
        # StrictProviderHit redaction runs before this check.  Any remaining
        # recognized credential shape causes cache admission to fail closed.
        if _CACHE_SECRET_RE.search(candidate.model_dump_json()):
            return None
        return candidate

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


@dataclass(frozen=True, slots=True)
class ProviderCircuitPermit:
    allowed: bool
    state: ProviderCircuitState
    generation: int


@dataclass(slots=True)
class _ProviderCircuitEntry:
    state: ProviderCircuitState = ProviderCircuitState.CLOSED
    consecutive_failures: int = 0
    opened_at: float = 0.0
    probe_in_flight: bool = False
    generation: int = 0


class ProviderCircuitBreaker:
    """Thread-safe tenant/principal-scoped circuit with one half-open probe."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        max_entries: int = 512,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not 1 <= failure_threshold <= 20:
            raise ValueError("circuit failure_threshold must be between 1 and 20")
        if not 0 < cooldown_seconds <= 3600:
            raise ValueError("circuit cooldown_seconds must be positive and bounded")
        if not 1 <= max_entries <= 4096:
            raise ValueError("circuit max_entries must be between 1 and 4096")
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[str, _ProviderCircuitEntry] = OrderedDict()
        self._lock = RLock()

    def acquire(self, key: str) -> ProviderCircuitPermit:
        now = self._clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                entry = _ProviderCircuitEntry()
                self._entries[key] = entry
                self._entries.move_to_end(key)
                self._evict_to_limit_locked()
                return ProviderCircuitPermit(
                    True,
                    ProviderCircuitState.CLOSED,
                    entry.generation,
                )
            self._entries.move_to_end(key)
            if entry.state == ProviderCircuitState.CLOSED:
                return ProviderCircuitPermit(
                    True,
                    ProviderCircuitState.CLOSED,
                    entry.generation,
                )
            if entry.state == ProviderCircuitState.OPEN:
                if now - entry.opened_at < self._cooldown_seconds:
                    return ProviderCircuitPermit(
                        False,
                        ProviderCircuitState.OPEN,
                        entry.generation,
                    )
                entry.state = ProviderCircuitState.HALF_OPEN
                entry.probe_in_flight = True
                entry.generation += 1
                return ProviderCircuitPermit(
                    True,
                    ProviderCircuitState.HALF_OPEN,
                    entry.generation,
                )
            if entry.probe_in_flight:
                return ProviderCircuitPermit(
                    False,
                    ProviderCircuitState.HALF_OPEN,
                    entry.generation,
                )
            entry.probe_in_flight = True
            entry.generation += 1
            return ProviderCircuitPermit(
                True,
                ProviderCircuitState.HALF_OPEN,
                entry.generation,
            )

    def record_success(
        self,
        key: str,
        *,
        permit: ProviderCircuitPermit,
    ) -> ProviderCircuitState:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return ProviderCircuitState.CLOSED
            if permit.state == ProviderCircuitState.HALF_OPEN:
                owns_probe = bool(
                    entry.state == ProviderCircuitState.HALF_OPEN
                    and entry.probe_in_flight
                    and entry.generation == permit.generation
                )
                if not owns_probe:
                    return entry.state
            elif entry.state != ProviderCircuitState.CLOSED:
                # A late success from an older CLOSED generation must never
                # erase a newer OPEN or HALF_OPEN circuit.
                return entry.state
            self._entries.pop(key, None)
            return ProviderCircuitState.CLOSED

    def record_failure(
        self,
        key: str,
        *,
        permit: ProviderCircuitPermit,
    ) -> ProviderCircuitState:
        now = self._clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                if permit.state != ProviderCircuitState.CLOSED:
                    return ProviderCircuitState.OPEN
                entry = _ProviderCircuitEntry(generation=permit.generation)
            if permit.state == ProviderCircuitState.HALF_OPEN:
                owns_probe = bool(
                    entry.state == ProviderCircuitState.HALF_OPEN
                    and entry.probe_in_flight
                    and entry.generation == permit.generation
                )
                if not owns_probe:
                    return entry.state
                entry.consecutive_failures = self._failure_threshold
            elif entry.state != ProviderCircuitState.CLOSED:
                # Ignore a late failure from a call admitted before a newer
                # circuit generation opened.
                return entry.state
            else:
                entry.consecutive_failures += 1
            entry.probe_in_flight = False
            entry.generation += 1
            if entry.consecutive_failures >= self._failure_threshold:
                entry.state = ProviderCircuitState.OPEN
                entry.opened_at = now
            else:
                entry.state = ProviderCircuitState.CLOSED
            self._entries[key] = entry
            self._entries.move_to_end(key)
            self._evict_to_limit_locked()
            return entry.state

    def release_without_failure(
        self,
        key: str,
        *,
        permit: ProviderCircuitPermit,
    ) -> ProviderCircuitState:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return ProviderCircuitState.CLOSED
            if permit.state == ProviderCircuitState.HALF_OPEN:
                owns_probe = bool(
                    entry.state == ProviderCircuitState.HALF_OPEN
                    and entry.probe_in_flight
                    and entry.generation == permit.generation
                )
                if not owns_probe:
                    return entry.state
                entry.probe_in_flight = False
                entry.state = ProviderCircuitState.OPEN
                entry.opened_at = self._clock()
                entry.generation += 1
            self._evict_to_limit_locked()
            return entry.state

    def _evict_to_limit_locked(self) -> None:
        """Bound state without evicting the only active recovery probe."""

        while len(self._entries) > self._max_entries:
            candidate = next(
                (
                    key
                    for key, entry in self._entries.items()
                    if entry.state == ProviderCircuitState.CLOSED
                    and not entry.probe_in_flight
                ),
                None,
            )
            if candidate is None:
                candidate = next(
                    (
                        key
                        for key, entry in self._entries.items()
                        if not entry.probe_in_flight
                    ),
                    None,
                )
            if candidate is None:
                # A temporary bounded overflow is safer than admitting a
                # second HALF_OPEN probe for an evicted scope.
                break
            self._entries.pop(candidate, None)

    def state(self, key: str) -> ProviderCircuitState:
        with self._lock:
            entry = self._entries.get(key)
            return entry.state if entry is not None else ProviderCircuitState.CLOSED


class ResilientEvidenceProvider:
    """EvidenceProvider facade applying one shared resilience controller."""

    def __init__(
        self,
        provider: EvidenceProvider,
        controller: "EvidenceProviderResilienceController",
    ) -> None:
        self._provider = provider
        self._controller = controller

    def descriptor(self) -> EvidenceProviderDescriptor:
        return self._provider.descriptor()

    def retrieve(
        self,
        query: EvidenceQueryV1,
        context: EvidenceProviderExecutionContext,
    ) -> EvidenceProviderRawResult:
        return self._controller.retrieve(self._provider, query, context)


class EvidenceProviderResilienceController:
    """Own central attempt, cache, and circuit state for raw retrieval."""

    def __init__(
        self,
        *,
        policy: ProviderResiliencePolicy | None = None,
        cache: InMemoryProviderEvidenceCache | None = None,
        circuit_breaker: ProviderCircuitBreaker | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.policy = policy or ProviderResiliencePolicy()
        self._clock = clock
        self._cache = (
            cache
            if cache is not None
            else InMemoryProviderEvidenceCache(
                max_entries=self.policy.cache_max_entries,
                max_bytes=self.policy.cache_max_bytes,
                clock=clock,
            )
        )
        self._circuit = (
            circuit_breaker
            if circuit_breaker is not None
            else ProviderCircuitBreaker(
                failure_threshold=self.policy.circuit_failure_threshold,
                cooldown_seconds=self.policy.circuit_cooldown_seconds,
                max_entries=self.policy.circuit_max_entries,
                clock=clock,
            )
        )

    @property
    def cache(self) -> InMemoryProviderEvidenceCache:
        return self._cache

    @property
    def circuit_breaker(self) -> ProviderCircuitBreaker:
        return self._circuit

    def wrap(self, provider: EvidenceProvider) -> ResilientEvidenceProvider:
        return ResilientEvidenceProvider(provider, self)

    def retrieve(
        self,
        provider: EvidenceProvider,
        query: EvidenceQueryV1,
        context: EvidenceProviderExecutionContext,
    ) -> EvidenceProviderRawResult:
        descriptor = provider.descriptor()
        cache_key = self._cache_key(descriptor, query, context)
        circuit_key = self._circuit_key(descriptor, context)
        lookup = ProviderCacheLookup(ProviderCacheState.BYPASS)
        if self.policy.cache_enabled:
            lookup = self._cache.lookup(
                cache_key,
                provider_contract_version=descriptor.provider_contract_version,
            )
            if lookup.state == ProviderCacheState.HIT and lookup.raw is not None:
                return self._rebind_cached(
                    lookup.raw,
                    query=query,
                    context=context,
                    cache_key=cache_key,
                    age_seconds=lookup.age_seconds or 0.0,
                    circuit_state=self._circuit.state(circuit_key),
                )

        # A cancelled or expired request must not consume the sole HALF_OPEN
        # recovery probe or move the breaker's cooldown window.
        preflight_state = self._circuit.state(circuit_key)
        if context.cancelled():
            return self._failure_raw(
                descriptor=descriptor,
                query=query,
                context=context,
                outcome=ProviderTransportOutcome.PROVIDER_ERROR,
                error_code="CANCELLED",
                message="Provider call was cancelled.",
                retryable=False,
                attempts=0,
                attempt_outcomes=[],
                cache_lookup=lookup,
                circuit_state_before=preflight_state,
                circuit_state_after=preflight_state,
            )
        if context.remaining_seconds() <= 0:
            return self._failure_raw(
                descriptor=descriptor,
                query=query,
                context=context,
                outcome=ProviderTransportOutcome.TIMEOUT,
                error_code="TIMEOUT",
                message="Provider deadline expired before dispatch.",
                retryable=True,
                attempts=0,
                attempt_outcomes=[],
                cache_lookup=lookup,
                circuit_state_before=preflight_state,
                circuit_state_after=preflight_state,
            )

        permit = self._circuit.acquire(circuit_key)
        if not permit.allowed:
            return self._failure_raw(
                descriptor=descriptor,
                query=query,
                context=context,
                outcome=ProviderTransportOutcome.PROVIDER_ERROR,
                error_code=(
                    "CIRCUIT_HALF_OPEN"
                    if permit.state == ProviderCircuitState.HALF_OPEN
                    else "CIRCUIT_OPEN"
                ),
                message="Provider call temporarily suppressed.",
                retryable=True,
                attempts=0,
                attempt_outcomes=[],
                cache_lookup=lookup,
                circuit_state_before=permit.state,
                circuit_state_after=permit.state,
            )

        started_at = _utc_now()
        started_clock = self._clock()
        logical_attempts = 0
        transport_attempts = 0
        reported_duration_ms = 0
        attempt_outcomes: list[ProviderTransportOutcome] = []

        while logical_attempts < self.policy.max_attempts:
            if context.cancelled():
                state_after = self._circuit.release_without_failure(
                    circuit_key,
                    permit=permit,
                )
                return self._failure_raw(
                    descriptor=descriptor,
                    query=query,
                    context=context,
                    outcome=ProviderTransportOutcome.PROVIDER_ERROR,
                    error_code="CANCELLED",
                    message="Provider call was cancelled.",
                    retryable=False,
                    attempts=transport_attempts,
                    attempt_outcomes=attempt_outcomes,
                    cache_lookup=lookup,
                    circuit_state_before=permit.state,
                    circuit_state_after=state_after,
                    started_at=started_at,
                    started_clock=started_clock,
                )
            if context.remaining_seconds() <= 0:
                outcome = ProviderTransportOutcome.TIMEOUT
                state_after = self._circuit.release_without_failure(
                    circuit_key,
                    permit=permit,
                )
                return self._failure_raw(
                    descriptor=descriptor,
                    query=query,
                    context=context,
                    outcome=outcome,
                    error_code="TIMEOUT",
                    message="Provider deadline expired before dispatch.",
                    retryable=True,
                    attempts=transport_attempts,
                    attempt_outcomes=attempt_outcomes,
                    cache_lookup=lookup,
                    circuit_state_before=permit.state,
                    circuit_state_after=state_after,
                    started_at=started_at,
                    started_clock=started_clock,
                )

            logical_attempts += 1
            try:
                raw = EvidenceProviderRawResult.model_validate(
                    provider.retrieve(query, context)
                )
                # One invocation of the adapter is exactly one transport
                # attempt. Adapter-supplied attempt/cache/circuit telemetry is
                # untrusted and cannot inflate or forge controller metrics.
                transport_attempts += 1
                reported_duration_ms += raw.duration_ms
                attempt_outcomes.append(raw.transport_outcome)
                if context.cancelled():
                    state_after = self._circuit.release_without_failure(
                        circuit_key,
                        permit=permit,
                    )
                    return self._failure_raw(
                        descriptor=descriptor,
                        query=query,
                        context=context,
                        outcome=ProviderTransportOutcome.PROVIDER_ERROR,
                        error_code="CANCELLED",
                        message="Provider call was cancelled before completion.",
                        retryable=False,
                        attempts=transport_attempts,
                        attempt_outcomes=attempt_outcomes[:-1]
                        + [ProviderTransportOutcome.PROVIDER_ERROR],
                        cache_lookup=lookup,
                        circuit_state_before=permit.state,
                        circuit_state_after=state_after,
                        started_at=started_at,
                        started_clock=started_clock,
                    )
                if context.remaining_seconds() <= 0:
                    state_after = self._circuit.record_failure(
                        circuit_key,
                        permit=permit,
                    )
                    return self._failure_raw(
                        descriptor=descriptor,
                        query=query,
                        context=context,
                        outcome=ProviderTransportOutcome.TIMEOUT,
                        error_code="TIMEOUT",
                        message="Provider response arrived after the deadline.",
                        retryable=True,
                        attempts=transport_attempts,
                        attempt_outcomes=attempt_outcomes[:-1]
                        + [ProviderTransportOutcome.TIMEOUT],
                        cache_lookup=lookup,
                        circuit_state_before=permit.state,
                        circuit_state_after=state_after,
                        started_at=started_at,
                        started_clock=started_clock,
                    )
                mismatch = self._basic_contract_mismatch(
                    raw=raw,
                    descriptor=descriptor,
                    query=query,
                    context=context,
                )
                if mismatch:
                    outcome = ProviderTransportOutcome.INVALID_RESPONSE
                    state_after = self._circuit.release_without_failure(
                        circuit_key,
                        permit=permit,
                    )
                    return self._failure_raw(
                        descriptor=descriptor,
                        query=query,
                        context=context,
                        outcome=outcome,
                        error_code=mismatch,
                        message="Provider response did not match the execution contract.",
                        retryable=False,
                        attempts=transport_attempts,
                        attempt_outcomes=attempt_outcomes[:-1] + [outcome],
                        cache_lookup=lookup,
                        circuit_state_before=permit.state,
                        circuit_state_after=state_after,
                        started_at=started_at,
                        started_clock=started_clock,
                    )
                status = _OUTCOME_STATUS[raw.transport_outcome]
                if raw.transport_outcome == ProviderTransportOutcome.COMPLETED:
                    state_after = self._circuit.record_success(
                        circuit_key,
                        permit=permit,
                    )
                    result = self._with_resilience_metadata(
                        raw,
                        attempts=transport_attempts,
                        attempt_outcomes=attempt_outcomes,
                        cache_lookup=lookup,
                        circuit_state_before=permit.state,
                        circuit_state_after=state_after,
                        started_at=started_at,
                        started_clock=started_clock,
                        reported_duration_ms=reported_duration_ms,
                    )
                    if self.policy.cache_enabled:
                        self._cache.store(
                            cache_key,
                            result,
                            ttl_seconds=self.policy.cache_ttl_seconds,
                        )
                    return result
                if self._should_retry(
                    status=status,
                    retryable=raw.retryable,
                    has_usable_hits=bool(raw.raw_hits),
                    logical_attempts=logical_attempts,
                    context=context,
                ):
                    continue
                state_after = self._circuit.record_failure(
                    circuit_key,
                    permit=permit,
                ) if (
                    status in _CIRCUIT_FAILURE_STATUSES
                    and (
                        status != EvidenceProviderStatus.PROVIDER_ERROR
                        or raw.retryable
                    )
                ) else self._circuit.release_without_failure(
                    circuit_key,
                    permit=permit,
                )
                return self._with_resilience_metadata(
                    raw,
                    attempts=transport_attempts,
                    attempt_outcomes=attempt_outcomes,
                    cache_lookup=lookup,
                    circuit_state_before=permit.state,
                    circuit_state_after=state_after,
                    started_at=started_at,
                    started_clock=started_clock,
                    reported_duration_ms=reported_duration_ms,
                )
            except ValidationError:
                outcome = ProviderTransportOutcome.INVALID_RESPONSE
                error_code = "INVALID_RESPONSE"
                message = "Provider returned a malformed response."
                retryable = False
                counts_for_circuit = False
            except EvidenceProviderCancelled:
                outcome = ProviderTransportOutcome.PROVIDER_ERROR
                error_code = "CANCELLED"
                message = "Provider call was cancelled."
                retryable = False
                counts_for_circuit = False
            except EvidenceProviderInvalidResponse as exc:
                outcome = ProviderTransportOutcome.INVALID_RESPONSE
                error_code = exc.redacted_error_code
                message = exc.redacted_message
                retryable = False
                counts_for_circuit = False
            except EvidenceProviderAuthError as exc:
                outcome = ProviderTransportOutcome.AUTH_ERROR
                error_code = exc.redacted_error_code
                message = exc.redacted_message
                retryable = False
                counts_for_circuit = False
            except EvidenceProviderRateLimited as exc:
                outcome = ProviderTransportOutcome.RATE_LIMITED
                error_code = exc.redacted_error_code
                message = exc.redacted_message
                retryable = False
                counts_for_circuit = True
            except EvidenceProviderTimeout as exc:
                outcome = ProviderTransportOutcome.TIMEOUT
                error_code = exc.redacted_error_code
                message = exc.redacted_message
                retryable = True
                counts_for_circuit = True
            except TimeoutError:
                outcome = ProviderTransportOutcome.TIMEOUT
                error_code = "TIMEOUT"
                message = "Provider call reached its deadline."
                retryable = True
                counts_for_circuit = True
            except PermissionError:
                outcome = ProviderTransportOutcome.AUTH_ERROR
                error_code = "AUTH_ERROR"
                message = "Provider authorization failed."
                retryable = False
                counts_for_circuit = False
            except EvidenceProviderException as exc:
                outcome = ProviderTransportOutcome.PROVIDER_ERROR
                error_code = exc.redacted_error_code
                message = exc.redacted_message
                retryable = bool(exc.retryable)
                counts_for_circuit = bool(exc.retryable)
            except Exception:
                # Never preserve a raw transport exception: URLs, headers, and
                # response bodies may contain credentials or customer data.
                outcome = ProviderTransportOutcome.PROVIDER_ERROR
                error_code = "PROVIDER_ERROR"
                message = "Provider execution failed."
                retryable = False
                counts_for_circuit = False

            transport_attempts += 1
            attempt_outcomes.append(outcome)
            status = _OUTCOME_STATUS[outcome]
            if self._should_retry(
                status=status,
                retryable=retryable,
                has_usable_hits=False,
                logical_attempts=logical_attempts,
                context=context,
            ):
                continue
            state_after = (
                self._circuit.record_failure(
                    circuit_key,
                    permit=permit,
                )
                if counts_for_circuit and status in _CIRCUIT_FAILURE_STATUSES
                else self._circuit.release_without_failure(
                    circuit_key,
                    permit=permit,
                )
            )
            return self._failure_raw(
                descriptor=descriptor,
                query=query,
                context=context,
                outcome=outcome,
                error_code=error_code,
                message=message,
                retryable=retryable,
                attempts=transport_attempts,
                attempt_outcomes=attempt_outcomes,
                cache_lookup=lookup,
                circuit_state_before=permit.state,
                circuit_state_after=state_after,
                started_at=started_at,
                started_clock=started_clock,
            )

        raise AssertionError("bounded provider loop exited without a result")

    def _should_retry(
        self,
        *,
        status: EvidenceProviderStatus,
        retryable: bool,
        has_usable_hits: bool,
        logical_attempts: int,
        context: EvidenceProviderExecutionContext,
    ) -> bool:
        return bool(
            retryable
            and not has_usable_hits
            and status in _RETRYABLE_STATUSES
            and logical_attempts < self.policy.max_attempts
            and not context.cancelled()
            and context.remaining_seconds() > 0
        )

    @staticmethod
    def _basic_contract_mismatch(
        *,
        raw: EvidenceProviderRawResult,
        descriptor: EvidenceProviderDescriptor,
        query: EvidenceQueryV1,
        context: EvidenceProviderExecutionContext,
    ) -> str:
        if raw.provider != descriptor.provider:
            return "PROVIDER_ID_MISMATCH"
        if raw.provider_contract_version != descriptor.provider_contract_version:
            return "PROVIDER_CONTRACT_VERSION_MISMATCH"
        if raw.query_id != query.query_id:
            return "QUERY_ID_MISMATCH"
        if raw.correlation_id != context.correlation_id:
            return "CORRELATION_ID_MISMATCH"
        active_filters = set(active_query_filters(query))
        applied_filters = set(raw.applied_filters)
        unsupported_filters = set(raw.unsupported_filters)
        if applied_filters & unsupported_filters:
            return "FILTER_CLAIM_CONFLICT"
        if not applied_filters.issubset(set(descriptor.supported_filters)):
            return "UNSUPPORTED_APPLIED_FILTER"
        if not (applied_filters | unsupported_filters).issubset(active_filters):
            return "INACTIVE_FILTER_CLAIM"
        supported_types = set(descriptor.supported_source_types)
        if any(hit.source_type not in supported_types for hit in raw.raw_hits):
            return "UNSUPPORTED_SOURCE_TYPE"
        if (
            raw.transport_outcome == ProviderTransportOutcome.COMPLETED
            and raw.redacted_error_code
        ):
            return "COMPLETED_WITH_ERROR"
        if any(
            synthesis.provider != raw.provider
            or synthesis.provider_contract_version
            != raw.provider_contract_version
            or synthesis.provider_call_id != raw.provider_call_id
            or synthesis.query_id != raw.query_id
            or synthesis.correlation_id != raw.correlation_id
            for synthesis in raw.discovery_syntheses
        ):
            return "DISCOVERY_SYNTHESIS_MISMATCH"
        return ""

    def _with_resilience_metadata(
        self,
        raw: EvidenceProviderRawResult,
        *,
        attempts: int,
        attempt_outcomes: list[ProviderTransportOutcome],
        cache_lookup: ProviderCacheLookup,
        circuit_state_before: ProviderCircuitState,
        circuit_state_after: ProviderCircuitState,
        started_at: str,
        started_clock: float,
        reported_duration_ms: int = 0,
    ) -> EvidenceProviderRawResult:
        payload = raw.model_dump(mode="json")
        completed_at = _utc_now()
        payload.update(
            {
                "attempts": attempts,
                "attempt_outcomes": [row.value for row in attempt_outcomes],
                "started_at": started_at,
                "completed_at": completed_at,
                "source_snapshot_retrieved_at": (
                    raw.source_snapshot_retrieved_at
                    or raw.completed_at
                    or completed_at
                ),
                "cache_served_at": "",
                "duration_ms": max(
                    reported_duration_ms,
                    max(0, round((self._clock() - started_clock) * 1000)),
                ),
                "cache_state": cache_lookup.state.value,
                "cache_schema_version": (
                    PROVIDER_CACHE_SCHEMA_VERSION
                    if self.policy.cache_enabled
                    else ""
                ),
                "cache_entry_age_seconds": cache_lookup.age_seconds,
                "circuit_state_before": circuit_state_before.value,
                "circuit_state_after": circuit_state_after.value,
            }
        )
        return EvidenceProviderRawResult.model_validate(payload)

    def _failure_raw(
        self,
        *,
        descriptor: EvidenceProviderDescriptor,
        query: EvidenceQueryV1,
        context: EvidenceProviderExecutionContext,
        outcome: ProviderTransportOutcome,
        error_code: str,
        message: str,
        retryable: bool,
        attempts: int,
        attempt_outcomes: list[ProviderTransportOutcome],
        cache_lookup: ProviderCacheLookup,
        circuit_state_before: ProviderCircuitState,
        circuit_state_after: ProviderCircuitState,
        started_at: str | None = None,
        started_clock: float | None = None,
    ) -> EvidenceProviderRawResult:
        call_id = "provider-call:" + stable_sha256(
            {
                "provider": descriptor.provider,
                "query_id": query.query_id,
                "correlation_id": context.correlation_id,
            }
        )[:32]
        return EvidenceProviderRawResult(
            provider=descriptor.provider,
            provider_contract_version=descriptor.provider_contract_version,
            provider_call_id=call_id,
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            transport_outcome=outcome,
            attempts=attempts,
            attempt_outcomes=attempt_outcomes,
            started_at=started_at or _utc_now(),
            completed_at=_utc_now(),
            duration_ms=(
                max(0, round((self._clock() - started_clock) * 1000))
                if started_clock is not None
                else 0
            ),
            cache_state=cache_lookup.state,
            cache_schema_version=(
                PROVIDER_CACHE_SCHEMA_VERSION if self.policy.cache_enabled else ""
            ),
            cache_entry_age_seconds=cache_lookup.age_seconds,
            circuit_state_before=circuit_state_before,
            circuit_state_after=circuit_state_after,
            retryable=retryable,
            redacted_error_code=error_code,
            redacted_message=message,
        )

    def _rebind_cached(
        self,
        raw: EvidenceProviderRawResult,
        *,
        query: EvidenceQueryV1,
        context: EvidenceProviderExecutionContext,
        cache_key: str,
        age_seconds: float,
        circuit_state: ProviderCircuitState,
    ) -> EvidenceProviderRawResult:
        call_id = "provider-cache-call:" + stable_sha256(
            {
                "cache_key": cache_key,
                "correlation_id": context.correlation_id,
            }
        )[:32]
        now = _utc_now()
        payload = raw.model_dump(mode="json")
        payload.update(
            {
                "provider_call_id": call_id,
                "query_id": query.query_id,
                "correlation_id": context.correlation_id,
                "attempts": 0,
                "attempt_outcomes": [],
                "started_at": now,
                "completed_at": now,
                "cache_served_at": now,
                "duration_ms": 0,
                "cache_state": ProviderCacheState.HIT.value,
                "cache_schema_version": PROVIDER_CACHE_SCHEMA_VERSION,
                "cache_entry_age_seconds": age_seconds,
                "circuit_state_before": circuit_state.value,
                "circuit_state_after": circuit_state.value,
                "retryable": False,
                "redacted_error_code": "",
                "redacted_message": "",
                "redacted_required_action": "",
            }
        )
        return EvidenceProviderRawResult.model_validate(payload)

    @staticmethod
    def _cache_key(
        descriptor: EvidenceProviderDescriptor,
        query: EvidenceQueryV1,
        context: EvidenceProviderExecutionContext,
    ) -> str:
        return "provider-cache:" + stable_sha256(
            {
                "cache_schema_version": PROVIDER_CACHE_SCHEMA_VERSION,
                "runtime_id": CANONICAL_RUNTIME_ID,
                "runtime_version": CANONICAL_RUNTIME_VERSION,
                "provider": descriptor.provider,
                "provider_contract_version": descriptor.provider_contract_version,
                "provider_configuration": descriptor.configuration_fingerprint,
                "query_id": query.query_id,
                "benchmark_split": context.benchmark_split,
                "principal": context.principal.model_dump(mode="json"),
            }
        )

    @staticmethod
    def _circuit_key(
        descriptor: EvidenceProviderDescriptor,
        context: EvidenceProviderExecutionContext,
    ) -> str:
        return "provider-circuit:" + stable_sha256(
            {
                "runtime_id": CANONICAL_RUNTIME_ID,
                "runtime_version": CANONICAL_RUNTIME_VERSION,
                "provider": descriptor.provider,
                "provider_contract_version": descriptor.provider_contract_version,
                "provider_configuration": descriptor.configuration_fingerprint,
                "benchmark_split": context.benchmark_split,
                "principal": context.principal.model_dump(mode="json"),
            }
        )


__all__ = [
    "PROVIDER_CACHE_SCHEMA_VERSION",
    "EvidenceProviderResilienceController",
    "InMemoryProviderEvidenceCache",
    "ProviderCacheLookup",
    "ProviderCircuitBreaker",
    "ProviderCircuitPermit",
    "ProviderResiliencePolicy",
    "ResilientEvidenceProvider",
]
