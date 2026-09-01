"""Provider-neutral evidence boundary tests for isolated stage-10 providers."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.schemas_canonical_test_plan_runtime import (
    AuthorityClass,
    AuthoritySubject,
    CurrentnessState,
    EvidenceSourceType,
    IssueDomain,
    RuntimePrincipal,
    VerificationState,
    VersionScope,
    VisibilityClass,
)
from app.services.reasoning_evidence_provider import (
    AuthorityRequirement,
    DiscoverySynthesis,
    EvidenceProviderAuthError,
    EvidenceProviderCallResult,
    EvidenceProviderDescriptor,
    EvidenceProviderExecutionContext,
    EvidenceProviderExecutor,
    EvidenceProviderRawResult,
    EvidenceProviderRegistry,
    EvidenceProviderStatus,
    EvidenceQueryV1,
    ExcludedSources,
    FakeEvidenceProvider,
    ProviderCacheState,
    ProviderTransportOutcome,
    QueryMateriality,
    RetrievalProvenance,
    StrictProviderHit,
    TemporalBoundary,
    active_query_filters,
)


_STAMP = "2026-08-28T06:00:00Z"


def _query(
    *,
    correlation_id: str = "corr-neutral-1",
    verified_source_required: bool = False,
    excluded_sources: ExcludedSources | None = None,
) -> EvidenceQueryV1:
    return EvidenceQueryV1(
        question_id="question:neutral-test",
        question="Which official source defines the current title behavior?",
        domain=IssueDomain.AUTHORING,
        requested_evidence_types=[
            EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION
        ],
        materiality=QueryMateriality.P1,
        authority_requirement=AuthorityRequirement(
            subject=AuthoritySubject.PRODUCT_CONTRACT,
            acceptable_classes=[AuthorityClass.OFFICIAL_PRODUCT_CONTRACT],
            direct_source_required=True,
            verified_source_required=verified_source_required,
        ),
        jira_reference="jira:GUIDES-FJ-NEUTRAL",
        temporal_boundary=TemporalBoundary(
            version_scope=VersionScope(),
            allowed_currentness=[CurrentnessState.VERSION_UNKNOWN],
        ),
        excluded_sources=excluded_sources or ExcludedSources(),
        max_results=2,
        correlation_id=correlation_id,
    )


def _context(
    *,
    cancelled=lambda: False,
    correlation_id: str = "corr-neutral-1",
    source_visibility_check=lambda _hit: True,
    source_verification_check=lambda _hit: False,
) -> EvidenceProviderExecutionContext:
    return EvidenceProviderExecutionContext(
        principal=RuntimePrincipal(
            principal_id="neutral-provider-user",
            tenant_id="neutral-provider-tenant",
            roles=["authenticated"],
        ),
        run_id="run-neutral-provider",
        request_id="request-neutral-provider",
        correlation_id=correlation_id,
        timeout_seconds=30.0,
        cancellation_check=cancelled,
        source_visibility_check=source_visibility_check,
        source_verification_check=source_verification_check,
    )


def _descriptor(*, provider: str = "fake-local-rag") -> EvidenceProviderDescriptor:
    return EvidenceProviderDescriptor(
        provider=provider,
        adapter_version="fake-v1",
        provider_contract_version="fake-v1",
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


def _hit(
    *,
    raw_provider_reference: str = "opaque-item-1",
) -> StrictProviderHit:
    return StrictProviderHit(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        source_reference="doc:https://experienceleague.adobe.com/guides/current-title",
        source_locator="https://experienceleague.adobe.com/guides/current-title#behavior",
        source_native_id="doc-1",
        title="Current title behavior",
        text="The current title is displayed after the map is reopened.",
        provider_native_kind="documentation",
        rank=1,
        retrieval_score=0.91,
        raw_provider_reference=raw_provider_reference,
    )


def _raw_factory(
    provider: str,
    *,
    hits: list[StrictProviderHit] | None = None,
    outcome: ProviderTransportOutcome = ProviderTransportOutcome.COMPLETED,
    truncated: bool = False,
    message: str = "",
):
    def build(query: EvidenceQueryV1, context: EvidenceProviderExecutionContext):
        return EvidenceProviderRawResult(
            provider=provider,
            provider_contract_version="fake-v1",
            provider_call_id=f"{provider}-call-1",
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            raw_hits=hits or [],
            transport_outcome=outcome,
            applied_filters=active_query_filters(query),
            attempts=1,
            started_at=_STAMP,
            completed_at=_STAMP,
            truncated=truncated,
            cache_state=ProviderCacheState.MISS,
            retryable=outcome
            in {
                ProviderTransportOutcome.TIMEOUT,
                ProviderTransportOutcome.RATE_LIMITED,
            },
            redacted_message=message,
        )

    return build


def test_generic_fake_provider_success_normalizes_centrally() -> None:
    provider = FakeEvidenceProvider(
        _descriptor(),
        result_factory=_raw_factory("fake-local-rag", hits=[_hit()]),
    )
    result = EvidenceProviderExecutor().execute(provider, _query(), _context())

    assert result.call_result.status == EvidenceProviderStatus.SUCCESS
    assert result.call_result.accepted_evidence_count == 1
    assert len(result.evidence_bundle.records) == 1
    record = result.evidence_bundle.records[0]
    assert record.source_type == EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION
    assert record.requirement_authority == AuthorityClass.OFFICIAL_PRODUCT_CONTRACT
    assert record.verification_status == VerificationState.UNVERIFIED
    assert record.visibility.tenant_id == "neutral-provider-tenant"
    assert record.retrieved_by_query == [_query().query_id]
    assert record.retrieved_at == _STAMP
    assert len(result.provenance) == 1
    provenance = result.provenance[0]
    assert provenance.evidence_id == record.evidence_id
    assert provenance.provider == "fake-local-rag"
    assert provenance.correlation_id == "corr-neutral-1"
    assert provenance.raw_provider_reference == "opaque-item-1"


def test_provider_interchangeability_keeps_underlying_evidence_identity() -> None:
    query = _query()
    context = _context()
    first = EvidenceProviderExecutor().execute(
        FakeEvidenceProvider(
            _descriptor(provider="fake-local-rag"),
            result_factory=_raw_factory("fake-local-rag", hits=[_hit()]),
        ),
        query,
        context,
    )
    second = EvidenceProviderExecutor().execute(
        FakeEvidenceProvider(
            _descriptor(provider="fake-fluffyjaws"),
            result_factory=_raw_factory("fake-fluffyjaws", hits=[_hit()]),
        ),
        query,
        context,
    )
    assert (
        first.evidence_bundle.records[0].evidence_id
        == second.evidence_bundle.records[0].evidence_id
    )
    assert first.evidence_bundle.bundle_id == second.evidence_bundle.bundle_id
    assert first.provenance[0].provider != second.provenance[0].provider


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [
        (ProviderTransportOutcome.COMPLETED, EvidenceProviderStatus.EMPTY),
        (ProviderTransportOutcome.TIMEOUT, EvidenceProviderStatus.TIMEOUT),
        (ProviderTransportOutcome.AUTH_ERROR, EvidenceProviderStatus.AUTH_ERROR),
        (
            ProviderTransportOutcome.RATE_LIMITED,
            EvidenceProviderStatus.RATE_LIMITED,
        ),
        (
            ProviderTransportOutcome.PROVIDER_ERROR,
            EvidenceProviderStatus.PROVIDER_ERROR,
        ),
    ],
)
def test_zero_evidence_statuses_never_create_placeholder_evidence(
    outcome: ProviderTransportOutcome, expected_status: EvidenceProviderStatus
) -> None:
    provider = FakeEvidenceProvider(
        _descriptor(),
        result_factory=_raw_factory("fake-local-rag", outcome=outcome),
    )
    result = EvidenceProviderExecutor().execute(provider, _query(), _context())
    assert result.call_result.status == expected_status
    assert result.call_result.accepted_evidence_count == 0
    assert result.call_result.accepted_evidence_ids == []
    assert result.evidence_bundle.records == []
    assert result.provenance == []


def test_usable_hit_plus_transport_failure_is_partial_with_reason() -> None:
    provider = FakeEvidenceProvider(
        _descriptor(),
        result_factory=_raw_factory(
            "fake-local-rag",
            hits=[_hit()],
            outcome=ProviderTransportOutcome.TIMEOUT,
            message="Provider timed out after one usable item.",
        ),
    )
    result = EvidenceProviderExecutor().execute(provider, _query(), _context())
    assert result.call_result.status == EvidenceProviderStatus.PARTIAL
    assert result.call_result.accepted_evidence_count == 1
    assert result.call_result.partial_reason


def test_typed_auth_failure_is_redacted_and_never_becomes_evidence() -> None:
    provider = FakeEvidenceProvider(
        _descriptor(),
        error=EvidenceProviderAuthError(
            "Bearer abcdef123456 api_key=supersecret",
            error_code="AUTH_ERROR",
        ),
    )
    result = EvidenceProviderExecutor().execute(provider, _query(), _context())
    serialized = result.model_dump_json()
    assert result.call_result.status == EvidenceProviderStatus.AUTH_ERROR
    assert result.evidence_bundle.records == []
    assert "abcdef123456" not in serialized
    assert "supersecret" not in serialized


class _MalformedProvider:
    def descriptor(self) -> EvidenceProviderDescriptor:
        return _descriptor(provider="malformed-provider")

    def retrieve(self, query, context):
        return {
            "provider": "malformed-provider",
            "provider_contract_version": "fake-v1",
            "provider_call_id": "malformed-call",
            "query_id": query.query_id,
            "correlation_id": context.correlation_id,
            "raw_hits": [],
            "authorization": "Bearer must-not-survive",
        }


def test_malformed_provider_response_is_invalid_without_echoing_payload() -> None:
    result = EvidenceProviderExecutor().execute(
        _MalformedProvider(), _query(), _context()
    )
    serialized = result.model_dump_json()
    assert result.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert result.call_result.redacted_error_code == "INVALID_RESPONSE"
    assert result.evidence_bundle.records == []
    assert "must-not-survive" not in serialized


@pytest.mark.parametrize(
    "forbidden",
    [
        {"requirement_authority": "ACCEPTED_PRODUCT_REQUIREMENT"},
        {"authority_class": "ACCEPTED_PRODUCT_REQUIREMENT"},
        {"accepted_human_contract": True},
        {"acceptance_candidate": "must happen"},
        {"promotion_status": "PROMOTED"},
        {"tenant_id": "other-tenant"},
        {"authorization": "Bearer secret"},
    ],
)
def test_strict_hit_rejects_authority_acceptance_tenant_and_secret_injection(
    forbidden: dict[str, object]
) -> None:
    payload = _hit().model_dump(mode="json")
    payload.update(forbidden)
    with pytest.raises(ValidationError):
        StrictProviderHit.model_validate(payload)


def test_discovery_synthesis_cannot_claim_acceptance_authority() -> None:
    payload = {
        "provider": "fake-fluffyjaws",
        "provider_contract_version": "fake-v1",
        "provider_call_id": "call-1",
        "query_id": _query().query_id,
        "correlation_id": "corr-neutral-1",
        "text": "This behavior must become an acceptance criterion.",
        "authority_class": "ACCEPTED_PRODUCT_REQUIREMENT",
    }
    with pytest.raises(ValidationError):
        DiscoverySynthesis.model_validate(payload)


def test_verified_source_requirement_fails_closed_until_independent_verification() -> None:
    provider = FakeEvidenceProvider(
        _descriptor(),
        result_factory=_raw_factory("fake-local-rag", hits=[_hit()]),
    )
    result = EvidenceProviderExecutor().execute(
        provider,
        _query(verified_source_required=True),
        _context(),
    )
    assert result.call_result.status == EvidenceProviderStatus.EMPTY
    assert result.call_result.rejected_hit_count == 1
    assert result.evidence_bundle.records == []


def test_exclusion_is_applied_after_provider_returns_a_hit() -> None:
    provider = FakeEvidenceProvider(
        _descriptor(),
        result_factory=_raw_factory("fake-local-rag", hits=[_hit()]),
    )
    result = EvidenceProviderExecutor().execute(
        provider,
        _query(
            excluded_sources=ExcludedSources(
                source_references=[
                    "doc:https://experienceleague.adobe.com/guides/current-title"
                ]
            )
        ),
        _context(),
    )
    assert result.call_result.status == EvidenceProviderStatus.EMPTY
    assert result.call_result.rejected_hit_count == 1
    assert result.evidence_bundle.records == []


def test_correlation_id_does_not_change_query_identity() -> None:
    first = _query(correlation_id="corr-one")
    second = _query(correlation_id="corr-two")
    assert first.query_id == second.query_id
    assert first.correlation_id != second.correlation_id


def test_disabled_registry_does_not_inspect_provider_or_dispatch() -> None:
    class _ExplodingProvider:
        def descriptor(self):
            raise AssertionError("disabled registry must not inspect providers")

        def retrieve(self, query, context):
            del query, context
            raise AssertionError("disabled registry must not dispatch")

    registry = EvidenceProviderRegistry([_ExplodingProvider()], enabled=False)
    assert registry.enabled is False
    assert registry.eligible(_query()) == []


def test_executor_cancellation_is_bounded_and_skips_provider_call() -> None:
    provider = FakeEvidenceProvider(_descriptor())
    result = EvidenceProviderExecutor().execute(
        provider,
        _query(),
        _context(cancelled=lambda: True),
    )
    assert provider.calls == []
    assert result.call_result.status == EvidenceProviderStatus.PROVIDER_ERROR
    assert result.call_result.redacted_error_code == "CANCELLED"
    assert result.evidence_bundle.records == []


def test_raw_provider_reference_is_redacted_but_correlation_is_preserved() -> None:
    provider = FakeEvidenceProvider(
        _descriptor(),
        result_factory=_raw_factory(
            "fake-local-rag",
            hits=[_hit(raw_provider_reference="Bearer opaque-secret-token")],
        ),
    )
    result = EvidenceProviderExecutor().execute(provider, _query(), _context())
    serialized = result.model_dump_json()
    assert result.provenance[0].correlation_id == "corr-neutral-1"
    assert "opaque-secret-token" not in serialized
    assert "redacted" in result.provenance[0].raw_provider_reference.casefold()


def test_source_and_synthesis_text_are_redacted_at_the_strict_boundary() -> None:
    hit_payload = _hit().model_dump(mode="json")
    hit_payload["text"] = (
        'Bearer source-secret-token api_key=source-key password="alpha beta"'
    )
    hit = StrictProviderHit.model_validate(hit_payload)
    provider = FakeEvidenceProvider(
        _descriptor(),
        result_factory=_raw_factory("fake-local-rag", hits=[hit]),
    )
    result = EvidenceProviderExecutor().execute(provider, _query(), _context())
    synthesis = DiscoverySynthesis(
        provider="fake-fluffyjaws",
        provider_contract_version="fake-v1",
        provider_call_id="call-1",
        query_id=_query().query_id,
        correlation_id="corr-neutral-1",
        text="Bearer synthesis-secret-token api_key=synthesis-key",
    )
    serialized = result.model_dump_json() + synthesis.model_dump_json()
    for secret in (
        "source-secret-token",
        "source-key",
        "alpha beta",
        "synthesis-secret-token",
        "synthesis-key",
    ):
        assert secret not in serialized


def test_authorization_schemes_are_redacted_at_the_strict_boundary() -> None:
    secrets = ("dXNlcjpwYXNz", "digest-user", "negotiate-token")
    hit_payload = _hit().model_dump(mode="json")
    hit_payload["text"] = (
        "Authorization: Basic dXNlcjpwYXNz\n"
        'Authorization: Digest username="digest-user", realm="internal"\n'
        "Proxy-Authorization: Negotiate negotiate-token"
    )
    hit = StrictProviderHit.model_validate(hit_payload)
    synthesis = DiscoverySynthesis(
        provider="fake-fluffyjaws",
        provider_contract_version="fake-v1",
        provider_call_id="call-auth-schemes",
        query_id=_query().query_id,
        correlation_id="corr-neutral-1",
        text=hit_payload["text"],
    )

    serialized = hit.model_dump_json() + synthesis.model_dump_json()
    assert all(secret not in serialized for secret in secrets)
    assert "REDACTED" in serialized


@pytest.mark.parametrize(
    ("query", "context"),
    [
        (
            _query(),
            _context(source_visibility_check=lambda _hit: "true"),
        ),
        (
            _query(verified_source_required=True),
            _context(
                source_visibility_check=lambda _hit: True,
                source_verification_check=lambda _hit: "true",
            ),
        ),
    ],
)
def test_source_policy_callbacks_require_literal_true(query, context) -> None:
    provider = FakeEvidenceProvider(
        _descriptor(),
        result_factory=_raw_factory("fake-local-rag", hits=[_hit()]),
    )

    result = EvidenceProviderExecutor().execute(provider, query, context)

    assert result.evidence_bundle.records == []
    assert result.call_result.accepted_evidence_count == 0


def test_completed_result_cannot_smuggle_an_error_or_failed_synthesis() -> None:
    query = _query()
    context = _context()

    def completed_with_error(_query_value, _context_value):
        return EvidenceProviderRawResult(
            provider="fake-local-rag",
            provider_contract_version="fake-v1",
            provider_call_id="call-with-error",
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            transport_outcome=ProviderTransportOutcome.COMPLETED,
            redacted_error_code="UPSTREAM_ERROR",
        )

    invalid = EvidenceProviderExecutor().execute(
        FakeEvidenceProvider(
            _descriptor(),
            result_factory=completed_with_error,
        ),
        query,
        context,
    )
    assert invalid.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE

    def failed_with_synthesis(_query_value, _context_value):
        return EvidenceProviderRawResult(
            provider="fake-local-rag",
            provider_contract_version="fake-v1",
            provider_call_id="failed-call",
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            transport_outcome=ProviderTransportOutcome.PROVIDER_ERROR,
            discovery_syntheses=[
                DiscoverySynthesis(
                    provider="fake-local-rag",
                    provider_contract_version="fake-v1",
                    provider_call_id="failed-call",
                    query_id=query.query_id,
                    correlation_id=context.correlation_id,
                    text="partial synthesis must be discarded",
                )
            ],
        )

    failed = EvidenceProviderExecutor().execute(
        FakeEvidenceProvider(
            _descriptor(),
            result_factory=failed_with_synthesis,
        ),
        query,
        context,
    )
    assert failed.call_result.status == EvidenceProviderStatus.PROVIDER_ERROR
    assert failed.discovery_syntheses == []


def test_source_visibility_requires_a_trusted_context_attestation() -> None:
    provider = FakeEvidenceProvider(
        _descriptor(),
        result_factory=_raw_factory("fake-local-rag", hits=[_hit()]),
    )
    denied = EvidenceProviderExecutor().execute(
        provider,
        _query(),
        _context(source_visibility_check=lambda _hit: False),
    )
    assert denied.call_result.status == EvidenceProviderStatus.EMPTY
    assert denied.call_result.rejected_hit_count == 1
    assert denied.evidence_bundle.records == []


def test_provider_source_type_outside_descriptor_is_invalid_response() -> None:
    payload = _hit().model_dump(mode="json")
    payload["source_type"] = EvidenceSourceType.CURRENT_CODE
    result = EvidenceProviderExecutor().execute(
        FakeEvidenceProvider(
            _descriptor(),
            result_factory=_raw_factory(
                "fake-local-rag",
                hits=[StrictProviderHit.model_validate(payload)],
            ),
        ),
        _query(),
        _context(),
    )
    assert result.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert result.call_result.redacted_error_code == "UNSUPPORTED_SOURCE_TYPE"


def test_rediscovered_evidence_unions_query_lineage_deterministically() -> None:
    first_query = _query()
    first = EvidenceProviderExecutor().execute(
        FakeEvidenceProvider(
            _descriptor(),
            result_factory=_raw_factory("fake-local-rag", hits=[_hit()]),
        ),
        first_query,
        _context(),
    )
    second_payload = first_query.model_dump(mode="json")
    second_payload.update(
        {
            "query_id": "",
            "question_id": "question:neutral-test-second",
            "question": "Which official source confirms the reopened title?",
            "correlation_id": "corr-neutral-2",
        }
    )
    second_query = EvidenceQueryV1.model_validate(second_payload)
    second = EvidenceProviderExecutor().execute(
        FakeEvidenceProvider(
            _descriptor(),
            result_factory=_raw_factory("fake-local-rag", hits=[_hit()]),
        ),
        second_query,
        _context(correlation_id="corr-neutral-2"),
        base_bundle=first.evidence_bundle,
    )
    assert second.evidence_bundle.records[0].retrieved_by_query == sorted(
        [first_query.query_id, second_query.query_id]
    )


def test_query_and_execution_correlation_mismatch_fails_before_dispatch() -> None:
    provider = FakeEvidenceProvider(_descriptor())
    result = EvidenceProviderExecutor().execute(
        provider,
        _query(correlation_id="corr-query"),
        _context(correlation_id="corr-context"),
    )
    assert provider.calls == []
    assert result.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert result.call_result.redacted_error_code == "CORRELATION_ID_MISMATCH"


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    [
        ("provider_contract_version", "client_secret=version-secret"),
        ("provider_call_id", "Authorization=Bearer call-secret"),
    ],
)
def test_raw_provider_identifiers_reject_secret_shaped_values(
    field: str,
    unsafe_value: str,
) -> None:
    query = _query()
    payload = {
        "provider": "fake-local-rag",
        "provider_contract_version": "fake-v1",
        "provider_call_id": "fake-local-rag-call-1",
        "query_id": query.query_id,
        "correlation_id": query.correlation_id,
    }
    payload[field] = unsafe_value
    with pytest.raises(ValidationError):
        EvidenceProviderRawResult.model_validate(payload)


def test_raw_contract_version_must_match_trusted_descriptor() -> None:
    query = _query()
    context = _context()

    def mismatched(_query_value, _context_value):
        return EvidenceProviderRawResult(
            provider="fake-local-rag",
            provider_contract_version="other-safe-v1",
            provider_call_id="fake-local-rag-call-1",
            query_id=query.query_id,
            correlation_id=context.correlation_id,
        )

    result = EvidenceProviderExecutor().execute(
        FakeEvidenceProvider(_descriptor(), result_factory=mismatched),
        query,
        context,
    )
    assert result.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert (
        result.call_result.redacted_error_code
        == "PROVIDER_CONTRACT_VERSION_MISMATCH"
    )


def test_missing_filter_claims_are_derived_as_unsupported_not_success() -> None:
    query = _query()
    context = _context()

    def omitted_claims(_query_value, _context_value):
        return EvidenceProviderRawResult(
            provider="fake-local-rag",
            provider_contract_version="fake-v1",
            provider_call_id="fake-local-rag-call-1",
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            raw_hits=[_hit()],
        )

    result = EvidenceProviderExecutor().execute(
        FakeEvidenceProvider(_descriptor(), result_factory=omitted_claims),
        query,
        context,
    )
    assert result.call_result.status == EvidenceProviderStatus.PARTIAL
    assert result.call_result.unsupported_filters == active_query_filters(query)


def test_applied_filter_must_be_declared_by_trusted_descriptor() -> None:
    query = _query()
    context = _context()
    descriptor = _descriptor().model_copy(update={"supported_filters": []})

    def overclaimed(_query_value, _context_value):
        return EvidenceProviderRawResult(
            provider="fake-local-rag",
            provider_contract_version="fake-v1",
            provider_call_id="fake-local-rag-call-1",
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            applied_filters=["max_results"],
        )

    result = EvidenceProviderExecutor().execute(
        FakeEvidenceProvider(descriptor, result_factory=overclaimed),
        query,
        context,
    )
    assert result.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert result.call_result.redacted_error_code == "UNSUPPORTED_APPLIED_FILTER"


@pytest.mark.parametrize("incomplete_kind", ["truncated", "unsupported"])
def test_zero_hit_incomplete_result_is_not_reported_as_empty(
    incomplete_kind: str,
) -> None:
    query = _query()
    context = _context()
    active = active_query_filters(query)
    unsupported = ["max_results"] if incomplete_kind == "unsupported" else []
    applied = [name for name in active if name not in unsupported]

    def incomplete(_query_value, _context_value):
        return EvidenceProviderRawResult(
            provider="fake-local-rag",
            provider_contract_version="fake-v1",
            provider_call_id="fake-local-rag-call-1",
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            applied_filters=applied,
            unsupported_filters=unsupported,
            truncated=incomplete_kind == "truncated",
        )

    result = EvidenceProviderExecutor().execute(
        FakeEvidenceProvider(_descriptor(), result_factory=incomplete),
        query,
        context,
    )
    assert result.call_result.status == EvidenceProviderStatus.PROVIDER_ERROR
    assert result.call_result.redacted_error_code == "INCOMPLETE_RESULT"


def test_malicious_raw_synthesis_lineage_is_structured_invalid_response() -> None:
    query = _query()
    context = _context()
    synthesis = DiscoverySynthesis(
        provider="fake-local-rag",
        provider_contract_version="fake-v1",
        provider_call_id="fake-local-rag-call-1",
        query_id=query.query_id,
        correlation_id=context.correlation_id,
        text="Discovery text",
        derived_from=["evidence:not-real"],
    )

    class _MappingProvider:
        def descriptor(self):
            return _descriptor()

        def retrieve(self, _query_value, _context_value):
            return {
                "provider": "fake-local-rag",
                "provider_contract_version": "fake-v1",
                "provider_call_id": "fake-local-rag-call-1",
                "query_id": query.query_id,
                "correlation_id": context.correlation_id,
                "discovery_syntheses": [synthesis.model_dump(mode="json")],
            }

    result = EvidenceProviderExecutor().execute(
        _MappingProvider(),
        query,
        context,
    )
    assert result.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert result.call_result.redacted_error_code == "INVALID_RESPONSE"


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -float("inf")])
def test_provenance_rejects_nonfinite_score(score: float) -> None:
    with pytest.raises(ValidationError, match="retrieval_score must be finite"):
        RetrievalProvenance(
            evidence_id="evidence:safe-id",
            provider="fake-local-rag",
            provider_contract_version="fake-v1",
            provider_call_id="fake-local-rag-call-1",
            query_id=_query().query_id,
            correlation_id="corr-neutral-1",
            retrieved_at=_STAMP,
            raw_provider_reference="opaque-item-1",
            retrieval_score=score,
        )


def test_safe_provider_sidecars_round_trip_deterministically() -> None:
    provenance = RetrievalProvenance(
        evidence_id="evidence:safe-id",
        provider="fake-local-rag",
        provider_contract_version="fake-v1",
        provider_call_id="fake-local-rag-call-1",
        query_id=_query().query_id,
        correlation_id="corr-neutral-1",
        retrieved_at=_STAMP,
        raw_provider_reference="opaque-item-1",
        retrieval_score=0.5,
    )
    assert RetrievalProvenance.model_validate_json(
        provenance.model_dump_json()
    ) == provenance

    with pytest.raises(ValidationError):
        EvidenceProviderCallResult(
            provider="fake-local-rag",
            provider_contract_version="fake-v1",
            provider_call_id="Authorization=Bearer unsafe",
            query_id=_query().query_id,
            correlation_id="corr-neutral-1",
            status=EvidenceProviderStatus.EMPTY,
            accepted_evidence_count=0,
        )


def _query_with_context_ids(*evidence_ids: str) -> EvidenceQueryV1:
    payload = _query().model_dump(mode="json")
    payload.update(
        {
            "query_id": "",
            "context_evidence_ids": list(evidence_ids),
        }
    )
    return EvidenceQueryV1.model_validate(payload)


def _query_with_version_scope(
    scope: VersionScope,
    *,
    allowed_currentness: CurrentnessState = CurrentnessState.VERSION_SPECIFIC,
) -> EvidenceQueryV1:
    payload = _query().model_dump(mode="json")
    payload.update(
        {
            "query_id": "",
            "temporal_boundary": TemporalBoundary(
                version_scope=scope,
                allowed_currentness=[allowed_currentness],
            ).model_dump(mode="json"),
        }
    )
    return EvidenceQueryV1.model_validate(payload)


def _successful_bundle():
    return EvidenceProviderExecutor().execute(
        FakeEvidenceProvider(
            _descriptor(),
            result_factory=_raw_factory("fake-local-rag", hits=[_hit()]),
        ),
        _query(),
        _context(),
    ).evidence_bundle


def test_cross_tenant_bundle_fails_before_provider_dispatch() -> None:
    base_bundle = _successful_bundle().model_copy(
        update={"tenant_id": "another-tenant"}
    )
    provider = FakeEvidenceProvider(_descriptor())
    result = EvidenceProviderExecutor().execute(
        provider,
        _query(),
        _context(),
        base_bundle=base_bundle,
    )

    assert provider.calls == []
    assert result.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert result.call_result.redacted_error_code == "CROSS_TENANT_CONTEXT"
    assert result.evidence_bundle.records == []


def test_missing_context_evidence_fails_before_provider_dispatch() -> None:
    provider = FakeEvidenceProvider(_descriptor())
    result = EvidenceProviderExecutor().execute(
        provider,
        _query_with_context_ids("evidence:not-in-bundle"),
        _context(),
        base_bundle=_successful_bundle(),
    )

    assert provider.calls == []
    assert result.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert result.call_result.redacted_error_code == "CONTEXT_EVIDENCE_UNAVAILABLE"


def test_restricted_context_evidence_fails_before_provider_dispatch() -> None:
    base_bundle = _successful_bundle()
    record = base_bundle.records[0]
    restricted = record.model_copy(
        update={
            "visibility": record.visibility.model_copy(
                update={
                    "classification": VisibilityClass.RESTRICTED,
                    "allowed_roles": ["quality_admin"],
                }
            )
        }
    )
    base_bundle = base_bundle.model_copy(update={"records": [restricted]})
    provider = FakeEvidenceProvider(_descriptor())
    result = EvidenceProviderExecutor().execute(
        provider,
        _query_with_context_ids(restricted.evidence_id),
        _context(),
        base_bundle=base_bundle,
    )

    assert provider.calls == []
    assert result.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert result.call_result.redacted_error_code == "CONTEXT_EVIDENCE_NOT_VISIBLE"


@pytest.mark.parametrize("field", ["tenant_id", "principal_id"])
def test_empty_principal_identity_is_rejected_before_dispatch(field: str) -> None:
    principal_payload = {
        "principal_id": "neutral-provider-user",
        "tenant_id": "neutral-provider-tenant",
        "roles": ["authenticated"],
    }
    principal_payload[field] = ""
    provider = FakeEvidenceProvider(_descriptor())

    with pytest.raises(ValueError, match="non-empty"):
        EvidenceProviderExecutionContext(
            principal=RuntimePrincipal(**principal_payload),
            run_id="run-neutral-provider",
            request_id="request-neutral-provider",
            correlation_id="corr-neutral-1",
        )
    assert provider.calls == []


def test_complete_version_scope_is_enforced_and_preserved() -> None:
    scope = VersionScope(
        product_versions=["5.0"],
        dita_version="1.3",
        deployment_model="on-prem",
        repository="AdobeStarling/starling",
        repository_revision="abc123",
        branch="release/5.0",
        dirty=False,
        environment="customer-production",
        source_updated_at="2026-08-27T04:00:00Z",
        retrieved_at="2026-08-28T05:00:00Z",
    )
    hit_payload = _hit().model_dump(mode="json")
    hit_payload.update(
        {
            "source_version": "5.0",
            "dita_version": "1.3",
            "deployment_model": "on-prem",
            "repository": "AdobeStarling/starling",
            "repository_revision": "abc123",
            "branch": "release/5.0",
            "dirty": False,
            "environment": "customer-production",
            "source_updated_at": "2026-08-27T04:00:00Z",
            "retrieved_at": "2026-08-28T05:00:00Z",
        }
    )
    result = EvidenceProviderExecutor().execute(
        FakeEvidenceProvider(
            _descriptor(),
            result_factory=_raw_factory(
                "fake-local-rag",
                hits=[StrictProviderHit.model_validate(hit_payload)],
            ),
        ),
        _query_with_version_scope(scope),
        _context(),
    )

    assert result.call_result.status == EvidenceProviderStatus.SUCCESS
    assert result.evidence_bundle.records[0].version_scope == scope


@pytest.mark.parametrize(
    ("field", "expected", "actual"),
    [
        ("dita_version", "1.3", "1.2"),
        ("deployment_model", "on-prem", "cloud"),
        ("repository", "AdobeStarling/starling", "AdobeStarling/xmleditor"),
        ("repository_revision", "abc123", "def456"),
        ("branch", "release/5.0", "main"),
        ("environment", "customer-production", "development"),
        ("source_updated_at", "2026-08-27T04:00:00Z", "2026-08-27T05:00:00Z"),
        ("retrieved_at", "2026-08-28T05:00:00Z", "2026-08-28T06:00:00Z"),
    ],
)
def test_version_scope_mismatch_rejects_provider_hit(
    field: str,
    expected: str,
    actual: str,
) -> None:
    scope = VersionScope.model_validate({field: expected})
    hit_payload = _hit().model_dump(mode="json")
    hit_payload[field] = actual
    result = EvidenceProviderExecutor().execute(
        FakeEvidenceProvider(
            _descriptor(),
            result_factory=_raw_factory(
                "fake-local-rag",
                hits=[StrictProviderHit.model_validate(hit_payload)],
            ),
        ),
        _query_with_version_scope(scope),
        _context(),
    )

    assert result.call_result.status == EvidenceProviderStatus.EMPTY
    assert result.call_result.rejected_hit_count == 1


def test_dirty_scope_mismatch_rejects_provider_hit() -> None:
    hit_payload = _hit().model_dump(mode="json")
    hit_payload["dirty"] = True
    result = EvidenceProviderExecutor().execute(
        FakeEvidenceProvider(
            _descriptor(),
            result_factory=_raw_factory(
                "fake-local-rag",
                hits=[StrictProviderHit.model_validate(hit_payload)],
            ),
        ),
        _query_with_version_scope(VersionScope(dirty=False)),
        _context(),
    )

    assert result.call_result.status == EvidenceProviderStatus.EMPTY
    assert result.call_result.rejected_hit_count == 1


@pytest.mark.parametrize("field", ["source_updated_at", "retrieved_at"])
def test_version_scope_rejects_malformed_timestamps(field: str) -> None:
    with pytest.raises(ValidationError, match="timestamp must be ISO-8601"):
        TemporalBoundary(
            version_scope=VersionScope.model_validate({field: "not-a-timestamp"})
        )


def test_combined_correlation_and_tenant_mismatch_fails_without_dispatch() -> None:
    provider = FakeEvidenceProvider(_descriptor())
    base_bundle = _successful_bundle().model_copy(
        update={"tenant_id": "another-tenant"}
    )
    result = EvidenceProviderExecutor().execute(
        provider,
        _query(correlation_id="corr-query"),
        _context(correlation_id="corr-context"),
        base_bundle=base_bundle,
    )

    assert provider.calls == []
    assert result.call_result.status == EvidenceProviderStatus.INVALID_RESPONSE
    assert result.call_result.redacted_error_code == "CORRELATION_ID_MISMATCH"
    assert result.evidence_bundle.records == []


def test_url_userinfo_credentials_are_redacted_before_canonicalization() -> None:
    hit_payload = _hit().model_dump(mode="json")
    hit_payload.update(
        {
            "source_reference": "doc:https://alice:source-password@example.test/doc",
            "source_locator": "https://bob:locator-password@example.test/doc#part",
            "text": "See https://carol:text-password@example.test/private",
        }
    )
    result = EvidenceProviderExecutor().execute(
        FakeEvidenceProvider(
            _descriptor(),
            result_factory=_raw_factory(
                "fake-local-rag",
                hits=[StrictProviderHit.model_validate(hit_payload)],
            ),
        ),
        _query(),
        _context(),
    )
    serialized = result.model_dump_json()

    assert result.call_result.status == EvidenceProviderStatus.SUCCESS
    for secret in (
        "alice",
        "source-password",
        "bob",
        "locator-password",
        "carol",
        "text-password",
    ):
        assert secret not in serialized
    assert "REDACTED-CREDENTIALS" in serialized


def test_url_userinfo_credentials_are_redacted_from_provider_sidecars() -> None:
    hit_payload = _hit().model_dump(mode="json")
    hit_payload["raw_provider_reference"] = (
        "https://provider-user:provider-password@example.test/result"
    )
    hit = StrictProviderHit.model_validate(hit_payload)
    error = EvidenceProviderAuthError(
        "Failed at https://error-user:error-password@example.test/request"
    )

    assert "provider-user" not in hit.raw_provider_reference
    assert "provider-password" not in hit.raw_provider_reference
    assert "error-user" not in error.redacted_message
    assert "error-password" not in error.redacted_message
    assert "REDACTED-CREDENTIALS" in hit.raw_provider_reference
    assert "REDACTED-CREDENTIALS" in error.redacted_message


def test_conflicting_duplicate_evidence_is_rejected_in_any_hit_order() -> None:
    first_payload = _hit(raw_provider_reference="opaque-item-a").model_dump(mode="json")
    second_payload = _hit(raw_provider_reference="opaque-item-b").model_dump(mode="json")
    first_payload["branch"] = "release/a"
    second_payload["branch"] = "release/b"
    hits = [
        StrictProviderHit.model_validate(first_payload),
        StrictProviderHit.model_validate(second_payload),
    ]
    query = _query_with_version_scope(VersionScope())

    results = [
        EvidenceProviderExecutor().execute(
            FakeEvidenceProvider(
                _descriptor(),
                result_factory=_raw_factory("fake-local-rag", hits=ordered),
            ),
            query,
            _context(),
        )
        for ordered in (hits, list(reversed(hits)))
    ]

    assert {
        (result.call_result.status, result.call_result.redacted_error_code)
        for result in results
    } == {(EvidenceProviderStatus.INVALID_RESPONSE, "CONFLICTING_EVIDENCE_ID")}
    assert all(result.evidence_bundle.records == [] for result in results)


def test_deployment_only_hit_is_environment_specific() -> None:
    hit_payload = _hit().model_dump(mode="json")
    hit_payload.update(
        {
            "deployment_model": "on-prem",
            "environment": "customer-production",
        }
    )
    result = EvidenceProviderExecutor().execute(
        FakeEvidenceProvider(
            _descriptor(),
            result_factory=_raw_factory(
                "fake-local-rag",
                hits=[StrictProviderHit.model_validate(hit_payload)],
            ),
        ),
        _query_with_version_scope(
            VersionScope(
                deployment_model="on-prem",
                environment="customer-production",
            ),
            allowed_currentness=CurrentnessState.ENVIRONMENT_SPECIFIC,
        ),
        _context(),
    )

    assert result.call_result.status == EvidenceProviderStatus.SUCCESS
    assert (
        result.evidence_bundle.records[0].currentness
        == CurrentnessState.ENVIRONMENT_SPECIFIC
    )


def test_retrieval_timestamp_alone_does_not_claim_a_source_version() -> None:
    retrieved_at = "2026-08-28T05:00:00Z"
    hit_payload = _hit().model_dump(mode="json")
    hit_payload["retrieved_at"] = retrieved_at
    hit = StrictProviderHit.model_validate(hit_payload)
    def provider() -> FakeEvidenceProvider:
        return FakeEvidenceProvider(
            _descriptor(),
            result_factory=_raw_factory("fake-local-rag", hits=[hit]),
        )

    accepted = EvidenceProviderExecutor().execute(
        provider(),
        _query_with_version_scope(
            VersionScope(retrieved_at=retrieved_at),
            allowed_currentness=CurrentnessState.VERSION_UNKNOWN,
        ),
        _context(),
    )
    misclassified = EvidenceProviderExecutor().execute(
        provider(),
        _query_with_version_scope(VersionScope(retrieved_at=retrieved_at)),
        _context(),
    )

    assert accepted.call_result.status == EvidenceProviderStatus.SUCCESS
    assert (
        accepted.evidence_bundle.records[0].currentness
        == CurrentnessState.VERSION_UNKNOWN
    )
    assert misclassified.call_result.status == EvidenceProviderStatus.EMPTY


def test_executor_discards_result_returned_after_total_deadline() -> None:
    def expire_before_return(
        query: EvidenceQueryV1,
        context: EvidenceProviderExecutionContext,
    ) -> EvidenceProviderRawResult:
        object.__setattr__(context, "started_monotonic", -1_000_000_000.0)
        return _raw_factory("fake-local-rag", hits=[_hit()])(query, context)

    provider = FakeEvidenceProvider(
        _descriptor(),
        result_factory=expire_before_return,
    )
    result = EvidenceProviderExecutor().execute(provider, _query(), _context())

    assert len(provider.calls) == 1
    assert result.call_result.status == EvidenceProviderStatus.TIMEOUT
    assert result.call_result.redacted_error_code == "TIMEOUT"
    assert result.evidence_bundle.records == []
