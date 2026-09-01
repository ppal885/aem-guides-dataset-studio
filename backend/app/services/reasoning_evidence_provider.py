"""Provider-neutral boundary for reasoning-directed evidence retrieval.

This module is intentionally isolated from the canonical runtime.  It defines
the versioned query, provider, normalization, and operational result contracts
needed by a future stage-10 integration, but it does not register a provider or
route production traffic.  Provider identity is kept in provenance sidecars;
it never participates in canonical evidence identity or authority selection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import math
import re
from time import monotonic
from typing import Any, Callable, Iterable, Literal, Protocol, runtime_checkable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.core.schemas_canonical_test_plan_runtime import (
    CANONICAL_RUNTIME_ID,
    CANONICAL_RUNTIME_VERSION,
    ApplicabilityState,
    AuthorityClass,
    AuthoritySubject,
    CanonicalEvidenceBundle,
    CurrentnessState,
    EvidenceDirectness,
    EvidenceRecord,
    EvidenceSourceType,
    IssueDomain,
    ProductContractOwnership,
    ProductOwnership,
    RuntimePrincipal,
    SemanticDimension,
    SourceVisibility,
    VerificationState,
    VersionScope,
    VisibilityClass,
    stable_sha256,
)
from app.services.canonical_evidence_service import (
    build_bundle,
    record_visible_to,
    redact_sensitive,
)


EVIDENCE_QUERY_SCHEMA = "aem-guides-evidence-query-v1"
PROVIDER_RESULT_SCHEMA = "aem-guides-provider-result-v1"
DISCOVERY_SYNTHESIS_SCHEMA = "aem-guides-discovery-synthesis-v1"
PROVIDER_HIT_DISPOSITION_SCHEMA = "aem-guides-provider-hit-disposition-v1"
PROVIDER_TRACE_SIDECAR_SCHEMA = "aem-guides-provider-trace-sidecar-v1"
SOURCE_ATTESTATION_SCHEMA = "aem-guides-source-attestation-v2"
QUESTION_EVIDENCE_ASSESSMENT_SCHEMA = (
    "aem-guides-question-evidence-assessment-v1"
)
SEMANTIC_EVIDENCE_AUTHORIZATION_SCHEMA = (
    "aem-guides-semantic-evidence-authorization-v1"
)
QUESTION_EVIDENCE_ASSESSMENTS_METADATA_KEY = "question_evidence_assessments"

_MAX_DIAGNOSTIC_CHARS = 500
_MAX_PROVIDER_REFERENCE_CHARS = 512
_OPAQUE_ID_PATTERN = r"^[A-Za-z0-9._:-]+$"
_OPAQUE_ID_RE = re.compile(_OPAQUE_ID_PATTERN)
_VERSION_TOKEN_PATTERN = r"^[A-Za-z0-9._:+-]+$"
_INLINE_SECRET_RE = re.compile(
    r"(?i)\b(authorization|proxy[_-]?authorization|password|passwd|secret|"
    r"api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"private[_-]?key|cookie|set[_-]?cookie|token)\b\s*[:=]\s*"
    r"(?:bearer\s+)?(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_AUTHORIZATION_FIELD_RE = re.compile(
    r"(?im)\b(authorization|proxy[_-]?authorization)\b[\"']?\s*[:=]\s*[^\r\n]+"
)
_URL_CREDENTIAL_RE = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/@\s:]+:[^/@\s]+@")
_BEARER_SECRET_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{4,}")
_KNOWN_SECRET_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{12,}\b|"
    r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{12,}\b|"
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
    r")"
)
_PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN[^\r\n]{0,40}PRIVATE KEY-----.*?"
    r"-----END[^\r\n]{0,40}PRIVATE KEY-----",
    re.IGNORECASE | re.DOTALL,
)
_HTTP_URL_RE = re.compile(r"(?i)https?://[^\s<>\"']+")
_SENSITIVE_URL_PARAMETER_NAMES = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "code",
    "credential",
    "expires",
    "googaccessid",
    "id_token",
    "key",
    "policy",
    "se",
    "sig",
    "signature",
    "ske",
    "skoid",
    "sks",
    "skt",
    "sktid",
    "skv",
    "sp",
    "spr",
    "sr",
    "srt",
    "ss",
    "st",
    "sv",
    "token",
    "x-amz-credential",
    "x-amz-security-token",
    "x-amz-signature",
    "x-goog-credential",
    "x-goog-date",
    "x-goog-expires",
    "x-goog-signature",
    "x-goog-signedheaders",
}


class QueryMateriality(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class EvidenceProviderStatus(StrEnum):
    """Final post-normalization status for one logical provider call."""

    SUCCESS = "SUCCESS"
    EMPTY = "EMPTY"
    PARTIAL = "PARTIAL"
    TIMEOUT = "TIMEOUT"
    AUTH_ERROR = "AUTH_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"


class ProviderTransportOutcome(StrEnum):
    """Transport outcome reported by an adapter before central normalization."""

    COMPLETED = "completed"
    TIMEOUT = "timeout"
    AUTH_ERROR = "auth_error"
    RATE_LIMITED = "rate_limited"
    PROVIDER_ERROR = "provider_error"
    INVALID_RESPONSE = "invalid_response"


class ProviderCacheState(StrEnum):
    MISS = "MISS"
    HIT = "HIT"
    STALE = "STALE"
    BYPASS = "BYPASS"
    UNKNOWN = "UNKNOWN"


class ProviderCircuitState(StrEnum):
    """Circuit state observed before and after one logical provider call."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


# FJ-03 uses the shorter logical name in prose.  Keep one enum implementation
# while allowing adapters to use either import spelling.
CacheState = ProviderCacheState


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _never_cancelled() -> bool:
    return False


def _deny_unverified_source(_hit: "StrictProviderHit") -> bool:
    return False


def _clean_string_set(values: Iterable[Any]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _sanitize_url_credentials(value: str) -> str:
    """Remove credential-bearing URL components from trace/cache strings."""

    def sanitize(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        trailing = ""
        while raw_url and raw_url[-1] in ".,);]}":
            trailing = raw_url[-1] + trailing
            raw_url = raw_url[:-1]
        try:
            parsed = urlsplit(raw_url)
            host = parsed.hostname or ""
            if not host:
                return "[REDACTED-URL]" + trailing
            display_host = f"[{host}]" if ":" in host else host
            userinfo_marker = (
                "[REDACTED-CREDENTIALS]@"
                if parsed.username is not None or parsed.password is not None
                else ""
            )
            netloc = userinfo_marker + display_host
            if parsed.port is not None:
                netloc += f":{parsed.port}"
            safe_query = urlencode(
                [
                    (key, item)
                    for key, item in parse_qsl(
                        parsed.query,
                        keep_blank_values=True,
                    )
                    if key.casefold() not in _SENSITIVE_URL_PARAMETER_NAMES
                ],
                doseq=True,
            )
            fragment = parsed.fragment
            fragment_keys = {
                key.casefold()
                for key, _item in parse_qsl(fragment, keep_blank_values=True)
            }
            if fragment_keys & _SENSITIVE_URL_PARAMETER_NAMES:
                fragment = ""
            return urlunsplit(
                (parsed.scheme, netloc, parsed.path, safe_query, fragment)
            ) + trailing
        except (TypeError, ValueError):
            return "[REDACTED-URL]" + trailing

    return _HTTP_URL_RE.sub(sanitize, value)


def _safe_diagnostic(value: Any) -> str:
    """Return a bounded diagnostic with known credential shapes redacted."""

    safe = redact_sensitive(str(value or "").strip())
    sanitized = _sanitize_url_credentials(str(safe or ""))
    text = _URL_CREDENTIAL_RE.sub(r"\1[REDACTED-CREDENTIALS]@", sanitized)
    text = _PRIVATE_KEY_BLOCK_RE.sub("[REDACTED-PRIVATE-KEY]", text)
    text = _BEARER_SECRET_RE.sub("Bearer [REDACTED]", text)
    text = _KNOWN_SECRET_RE.sub("[REDACTED-SECRET]", text)
    text = _AUTHORIZATION_FIELD_RE.sub(
        lambda match: f"{match.group(1)}=[REDACTED]", text
    )
    text = _INLINE_SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    if len(text) > _MAX_DIAGNOSTIC_CHARS:
        return text[: _MAX_DIAGNOSTIC_CHARS - 1] + "…"
    return text


def _safe_provider_reference(value: Any) -> str:
    safe = redact_sensitive(str(value or "").strip())
    sanitized = _sanitize_url_credentials(str(safe or ""))
    text = _URL_CREDENTIAL_RE.sub(r"\1[REDACTED-CREDENTIALS]@", sanitized)
    text = _PRIVATE_KEY_BLOCK_RE.sub("[REDACTED-PRIVATE-KEY]", text)
    text = _BEARER_SECRET_RE.sub("Bearer [REDACTED]", text)
    text = _KNOWN_SECRET_RE.sub("[REDACTED-SECRET]", text)
    text = _AUTHORIZATION_FIELD_RE.sub(
        lambda match: f"{match.group(1)}=[REDACTED]", text
    )
    text = _INLINE_SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    return text[:_MAX_PROVIDER_REFERENCE_CHARS]


def _safe_source_text(value: Any) -> str:
    """Redact credential-shaped values without truncating source content."""

    safe = redact_sensitive(str(value or ""))
    safe = _sanitize_url_credentials(str(safe or ""))
    safe = _URL_CREDENTIAL_RE.sub(r"\1[REDACTED-CREDENTIALS]@", safe)
    safe = _PRIVATE_KEY_BLOCK_RE.sub("[REDACTED-PRIVATE-KEY]", safe)
    safe = _BEARER_SECRET_RE.sub("Bearer [REDACTED]", safe)
    safe = _KNOWN_SECRET_RE.sub("[REDACTED-SECRET]", safe)
    safe = _AUTHORIZATION_FIELD_RE.sub(
        lambda match: f"{match.group(1)}=[REDACTED]", safe
    )
    return _INLINE_SECRET_RE.sub(
        lambda match: f"{match.group(1)}=[REDACTED]", str(safe or "")
    )


def _parse_timestamp(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class AuthorityRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: AuthoritySubject
    acceptable_classes: list[AuthorityClass] = Field(default_factory=list)
    direct_source_required: bool = False
    verified_source_required: bool = False

    @field_validator("acceptable_classes")
    @classmethod
    def normalize_classes(cls, values: list[AuthorityClass]) -> list[AuthorityClass]:
        return sorted(set(values), key=lambda value: value.value)


class TemporalBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str = ""
    source_not_before: str = ""
    source_not_after: str = ""
    version_scope: VersionScope = Field(default_factory=VersionScope)
    allowed_currentness: list[CurrentnessState] = Field(default_factory=list)

    @field_validator("as_of", "source_not_before", "source_not_after")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        text = str(value or "").strip()
        if text:
            _parse_timestamp(text)
        return text

    @field_validator("allowed_currentness")
    @classmethod
    def normalize_currentness(
        cls, values: list[CurrentnessState]
    ) -> list[CurrentnessState]:
        return sorted(set(values), key=lambda value: value.value)

    @model_validator(mode="after")
    def validate_order(self) -> "TemporalBoundary":
        lower = _parse_timestamp(self.source_not_before)
        upper = _parse_timestamp(self.source_not_after)
        if lower and upper and lower > upper:
            raise ValueError("source_not_before must not be after source_not_after")
        for value in (
            self.version_scope.source_updated_at,
            self.version_scope.retrieved_at,
        ):
            if str(value or "").strip():
                _parse_timestamp(value)
        return self


class ExcludedSources(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_types: list[EvidenceSourceType] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)
    content_sha256: list[str] = Field(default_factory=list)

    @field_validator("source_types")
    @classmethod
    def normalize_types(
        cls, values: list[EvidenceSourceType]
    ) -> list[EvidenceSourceType]:
        return sorted(set(values), key=lambda value: value.value)

    @field_validator("source_references")
    @classmethod
    def normalize_references(cls, values: list[str]) -> list[str]:
        return _clean_string_set(values)

    @field_validator("content_sha256")
    @classmethod
    def normalize_content_sha256(cls, values: list[str]) -> list[str]:
        normalized = sorted(
            {str(value).strip().casefold() for value in values if str(value).strip()}
        )
        if any(re.fullmatch(r"[a-f0-9]{64}", value) is None for value in normalized):
            raise ValueError("excluded content_sha256 values must be SHA-256 hex")
        return normalized


class EvidenceQueryV1(BaseModel):
    """Provider-neutral query derived from one canonical missing question."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-evidence-query-v1"] = EVIDENCE_QUERY_SCHEMA
    query_id: str = ""
    question_id: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=4000)
    dimension: SemanticDimension | None = None
    domain: IssueDomain
    requested_evidence_types: list[EvidenceSourceType] = Field(default_factory=list)
    materiality: QueryMateriality = QueryMateriality.P2
    authority_requirement: AuthorityRequirement
    jira_reference: str = ""
    context_evidence_ids: list[str] = Field(default_factory=list)
    temporal_boundary: TemporalBoundary = Field(default_factory=TemporalBoundary)
    excluded_sources: ExcludedSources = Field(default_factory=ExcludedSources)
    max_results: int = Field(default=5, ge=1, le=100)
    correlation_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=_OPAQUE_ID_PATTERN,
    )
    blocking: bool = False

    @field_validator("requested_evidence_types")
    @classmethod
    def normalize_source_types(
        cls, values: list[EvidenceSourceType]
    ) -> list[EvidenceSourceType]:
        return sorted(set(values), key=lambda value: value.value)

    @field_validator("context_evidence_ids")
    @classmethod
    def normalize_context_ids(cls, values: list[str]) -> list[str]:
        return _clean_string_set(values)

    @model_validator(mode="after")
    def identify(self) -> "EvidenceQueryV1":
        if self.blocking and self.materiality != QueryMateriality.P0:
            raise ValueError("blocking provider queries require P0 materiality")
        identity = self.model_dump(
            mode="json", exclude={"query_id", "correlation_id"}, exclude_none=True
        )
        expected = f"query:{stable_sha256(identity)[:32]}"
        if self.query_id and self.query_id != expected:
            raise ValueError("query_id does not match deterministic query identity")
        self.query_id = expected
        return self


def active_query_filters(query: EvidenceQueryV1) -> list[str]:
    """Return the canonical names of result-affecting active constraints."""

    active = {"max_results"}
    if query.requested_evidence_types:
        active.add("requested_evidence_types")
    authority = query.authority_requirement
    if (
        authority.acceptable_classes
        or authority.direct_source_required
        or authority.verified_source_required
    ):
        active.add("authority_requirement")
    if query.jira_reference or query.context_evidence_ids:
        active.add("jira_or_context_reference")
    if (
        query.temporal_boundary.as_of
        or query.temporal_boundary.source_not_before
        or query.temporal_boundary.source_not_after
        or query.temporal_boundary.allowed_currentness
        or query.temporal_boundary.version_scope.model_dump(exclude_defaults=True)
    ):
        active.add("temporal_boundary")
    if (
        query.excluded_sources.source_types
        or query.excluded_sources.source_references
        or query.excluded_sources.content_sha256
    ):
        active.add("excluded_sources")
    return sorted(active)


class EvidenceProviderDescriptor(BaseModel):
    """Trusted local provider capabilities; it contains no credentials."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    adapter_version: str = Field(
        min_length=1,
        max_length=80,
        pattern=_VERSION_TOKEN_PATTERN,
    )
    provider_contract_version: str = Field(
        min_length=1,
        max_length=80,
        pattern=_VERSION_TOKEN_PATTERN,
    )
    supported_domains: list[IssueDomain] = Field(default_factory=list)
    supported_source_types: list[EvidenceSourceType] = Field(default_factory=list)
    supports_discovery_synthesis: bool = False
    supported_filters: list[str] = Field(default_factory=list)
    maximum_results: int = Field(default=20, ge=1, le=100)
    configuration_digest: str = Field(
        default="",
        max_length=64,
        pattern=r"^(?:[a-f0-9]{64})?$",
    )

    @field_validator("supported_domains", "supported_source_types")
    @classmethod
    def normalize_enums(cls, values: list[Any]) -> list[Any]:
        return sorted(set(values), key=lambda value: value.value)

    @field_validator("supported_filters")
    @classmethod
    def normalize_filters(cls, values: list[str]) -> list[str]:
        return _clean_string_set(values)

    @property
    def configuration_fingerprint(self) -> str:
        return stable_sha256(self.model_dump(mode="json", exclude_none=True))


class StrictProviderHit(BaseModel):
    """One source-native hit accepted at the untrusted provider boundary.

    Canonical authority, verification, visibility, lifecycle, tenancy, contract
    state, and output fields are deliberately absent.  ``extra='forbid'`` makes
    attempts to smuggle any such field fail closed.
    """

    model_config = ConfigDict(extra="forbid")

    source_type: EvidenceSourceType
    source_reference: str = Field(min_length=1, max_length=2000)
    source_locator: str = Field(min_length=1, max_length=4000)
    text: str = Field(min_length=1, max_length=500_000)
    source_native_id: str = Field(default="", max_length=1000)
    title: str = Field(default="", max_length=2000)
    source_timestamp: str = ""
    source_version: str = Field(default="", max_length=300)
    dita_version: str = Field(default="", max_length=300)
    deployment_model: str = Field(default="", max_length=300)
    repository: str = Field(default="", max_length=1000)
    repository_revision: str = Field(default="", max_length=300)
    branch: str = Field(default="", max_length=1000)
    dirty: bool | None = None
    environment: str = Field(default="", max_length=300)
    source_updated_at: str = ""
    retrieved_at: str = ""
    provider_native_kind: str = Field(default="", max_length=200)
    rank: int | None = Field(default=None, ge=1)
    retrieval_score: float | None = None
    raw_provider_reference: str = Field(min_length=1, max_length=2000)

    @field_validator("source_timestamp", "source_updated_at", "retrieved_at")
    @classmethod
    def validate_source_timestamp(cls, value: str) -> str:
        text = str(value or "").strip()
        if text:
            _parse_timestamp(text)
        return text

    @field_validator(
        "source_reference",
        "source_locator",
        "source_native_id",
        "title",
        "text",
        "source_version",
        "dita_version",
        "deployment_model",
        "repository",
        "repository_revision",
        "branch",
        "environment",
        "provider_native_kind",
    )
    @classmethod
    def redact_source_text(cls, value: str) -> str:
        return _safe_source_text(value)

    @field_validator("retrieval_score")
    @classmethod
    def require_finite_retrieval_score(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("retrieval_score must be finite")
        return value

    @field_validator("raw_provider_reference")
    @classmethod
    def redact_provider_reference(cls, value: str) -> str:
        safe = _safe_provider_reference(value)
        if not safe:
            raise ValueError("raw_provider_reference cannot be empty after redaction")
        return safe

    @model_validator(mode="after")
    def reject_conflicting_source_timestamps(self) -> "StrictProviderHit":
        if (
            self.source_timestamp
            and self.source_updated_at
            and _parse_timestamp(self.source_timestamp)
            != _parse_timestamp(self.source_updated_at)
        ):
            raise ValueError(
                "source_timestamp and source_updated_at must identify the same instant"
            )
        return self


def provider_hit_content_sha256(hit: StrictProviderHit) -> str:
    """Hash source text for title-insensitive sealed-content exclusion."""

    return stable_sha256({"text": hit.text})


class RetrievalProvenance(BaseModel):
    """Operational retrieval provenance kept outside canonical evidence v2."""

    model_config = ConfigDict(extra="forbid")

    provenance_id: str = ""
    evidence_id: str = Field(min_length=1)
    provider: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    provider_contract_version: str = Field(
        min_length=1,
        max_length=80,
        pattern=_VERSION_TOKEN_PATTERN,
    )
    provider_call_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=_OPAQUE_ID_PATTERN,
    )
    query_id: str = Field(min_length=1, pattern=_OPAQUE_ID_PATTERN)
    correlation_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=_OPAQUE_ID_PATTERN,
    )
    retrieved_at: str
    raw_provider_reference: str = Field(max_length=_MAX_PROVIDER_REFERENCE_CHARS)
    applicability: ApplicabilityState = ApplicabilityState.APPLICABLE
    rank: int | None = Field(default=None, ge=1)
    retrieval_score: float | None = None
    retrieval_method: str = Field(default="provider", max_length=100)
    cache_state: ProviderCacheState = ProviderCacheState.UNKNOWN
    cache_served_at: str = ""

    @field_validator("retrieved_at")
    @classmethod
    def validate_retrieved_at(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("retrieved_at is required")
        _parse_timestamp(text)
        return text

    @field_validator("cache_served_at")
    @classmethod
    def validate_cache_served_at(cls, value: str) -> str:
        text = str(value or "").strip()
        if text:
            _parse_timestamp(text)
        return text

    @field_validator("raw_provider_reference")
    @classmethod
    def redact_provider_reference(cls, value: str) -> str:
        return _safe_provider_reference(value)

    @field_validator("retrieval_score")
    @classmethod
    def require_finite_retrieval_score(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("retrieval_score must be finite")
        return value

    @model_validator(mode="after")
    def identify(self) -> "RetrievalProvenance":
        identity = self.model_dump(mode="json", exclude={"provenance_id"})
        expected = f"provenance:{stable_sha256(identity)[:32]}"
        if self.provenance_id and self.provenance_id != expected:
            raise ValueError("provenance_id does not match deterministic identity")
        self.provenance_id = expected
        return self


class QuestionEvidenceStance(StrEnum):
    """Question-bound meaning assigned by a trusted semantic assessor."""

    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    IRRELEVANT = "IRRELEVANT"
    AMBIGUOUS = "AMBIGUOUS"


class SemanticEvidenceBinding(BaseModel):
    """Tamper-evident binding shared by source and semantic attestations.

    The binding contains only opaque identifiers and hashes. It prevents an
    assessment made for one source, question, principal, version, or provider
    call from being replayed in another canonical runtime request.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    binding_id: str = ""
    runtime_id: Literal["aem-guides-test-plan-runtime"] = CANONICAL_RUNTIME_ID
    runtime_version: Literal["2.0.0"] = CANONICAL_RUNTIME_VERSION
    request_id: str = Field(min_length=1, max_length=200, pattern=_OPAQUE_ID_PATTERN)
    question_id: str = Field(min_length=1, max_length=200, pattern=_OPAQUE_ID_PATTERN)
    question_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    query_id: str = Field(min_length=1, max_length=200, pattern=_OPAQUE_ID_PATTERN)
    evidence_id: str = Field(min_length=1, max_length=300)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    tenant_id: str = Field(min_length=1, max_length=300)
    source_type: EvidenceSourceType
    authority_subject: AuthoritySubject
    currentness: CurrentnessState
    source_reference_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider_hit_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provenance_id: str = Field(min_length=1, max_length=300, pattern=_OPAQUE_ID_PATTERN)
    disposition_id: str = Field(
        min_length=1,
        max_length=300,
        pattern=_OPAQUE_ID_PATTERN,
    )
    requirement_authority: AuthorityClass
    provider: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    provider_contract_version: str = Field(
        min_length=1,
        max_length=80,
        pattern=_VERSION_TOKEN_PATTERN,
    )
    provider_call_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=_OPAQUE_ID_PATTERN,
    )
    correlation_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=_OPAQUE_ID_PATTERN,
    )
    version_scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    visibility_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    principal_scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    temporal_policy_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    authority_requirement_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def identify(self) -> "SemanticEvidenceBinding":
        identity = self.model_dump(mode="json", exclude={"binding_id"})
        expected = f"semantic-binding:{stable_sha256(identity)[:32]}"
        if self.binding_id and self.binding_id != expected:
            raise ValueError("binding_id does not match deterministic identity")
        object.__setattr__(self, "binding_id", expected)
        return self


class SourceNativeEvidenceAttestation(BaseModel):
    """Independent authentication of one source under one access scope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["aem-guides-source-attestation-v2"] = (
        SOURCE_ATTESTATION_SCHEMA
    )
    attestation_id: str = ""
    binding: SemanticEvidenceBinding
    verification_status: Literal[
        VerificationState.VERIFIED_LIVE,
        VerificationState.VERIFIED_REVISION,
        VerificationState.VERIFIED_SOURCE,
    ]
    source_revision: str = Field(default="", max_length=500)
    verification_method: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Z0-9_]+$",
    )
    verifier_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )
    verifier_version: str = Field(
        min_length=1,
        max_length=100,
        pattern=_VERSION_TOKEN_PATTERN,
    )
    verified_at: str
    expires_at: str = ""
    reason_code: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Z0-9_]+$",
    )

    @field_validator("verified_at", "expires_at")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        text = str(value or "").strip()
        if text:
            _parse_timestamp(text)
        return text

    @model_validator(mode="after")
    def validate_and_identify(self) -> "SourceNativeEvidenceAttestation":
        verified_at = _parse_timestamp(self.verified_at)
        expires_at = _parse_timestamp(self.expires_at)
        if verified_at is None:
            raise ValueError("verified_at is required")
        if expires_at is not None and expires_at <= verified_at:
            raise ValueError("expires_at must be later than verified_at")
        if self.verification_status == VerificationState.VERIFIED_REVISION:
            if not self.source_revision.strip():
                raise ValueError("verified revision requires a pinned source revision")
        elif expires_at is None:
            raise ValueError("live/source verification requires a bounded expiry")
        identity = self.model_dump(mode="json", exclude={"attestation_id"})
        expected = f"source-attestation:{stable_sha256(identity)[:32]}"
        if self.attestation_id and self.attestation_id != expected:
            raise ValueError("attestation_id does not match deterministic identity")
        object.__setattr__(self, "attestation_id", expected)
        return self


class QuestionEvidenceAssessment(BaseModel):
    """Independent relevance/stance decision for one exact question and source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["aem-guides-question-evidence-assessment-v1"] = (
        QUESTION_EVIDENCE_ASSESSMENT_SCHEMA
    )
    assessment_id: str = ""
    binding: SemanticEvidenceBinding
    source_attestation_id: str = Field(min_length=1, max_length=300)
    stance: QuestionEvidenceStance
    assessed_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    assessment_confidence: float = Field(ge=0.0, le=1.0)
    claim_keys: list[str] = Field(default_factory=list, max_length=50)
    assessment_method: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Z0-9_]+$",
    )
    assessor_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )
    assessor_version: str = Field(
        min_length=1,
        max_length=100,
        pattern=_VERSION_TOKEN_PATTERN,
    )
    assessed_at: str
    expires_at: str
    reason_code: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Z0-9_]+$",
    )

    @field_validator("claim_keys")
    @classmethod
    def normalize_claim_keys(cls, values: list[str]) -> list[str]:
        normalized = _clean_string_set(values)
        if any(len(value) > 300 for value in normalized):
            raise ValueError("assessment claim keys must be at most 300 characters")
        return normalized

    @field_validator("assessed_at", "expires_at")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("assessment timestamps are required")
        _parse_timestamp(text)
        return text

    @model_validator(mode="after")
    def validate_and_identify(self) -> "QuestionEvidenceAssessment":
        if self.assessed_content_sha256 != self.binding.content_sha256:
            raise ValueError("assessment content hash must match its binding")
        if self.stance in {
            QuestionEvidenceStance.SUPPORTS,
            QuestionEvidenceStance.CONTRADICTS,
        }:
            if self.assessment_confidence < 0.8:
                raise ValueError("decisive stance requires at least 0.8 confidence")
            if not self.claim_keys:
                raise ValueError("decisive stance requires an explicit claim key")
        assessed_at = _parse_timestamp(self.assessed_at)
        expires_at = _parse_timestamp(self.expires_at)
        if assessed_at is None or expires_at is None or expires_at <= assessed_at:
            raise ValueError("assessment expiry must be later than assessment time")
        identity = self.model_dump(mode="json", exclude={"assessment_id"})
        expected = f"question-assessment:{stable_sha256(identity)[:32]}"
        if self.assessment_id and self.assessment_id != expected:
            raise ValueError("assessment_id does not match deterministic identity")
        object.__setattr__(self, "assessment_id", expected)
        return self


class SemanticEvidenceAuthorization(BaseModel):
    """Atomic source-authentication plus question-entailment decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["aem-guides-semantic-evidence-authorization-v1"] = (
        SEMANTIC_EVIDENCE_AUTHORIZATION_SCHEMA
    )
    authorization_id: str = ""
    source_attestation: SourceNativeEvidenceAttestation
    question_assessment: QuestionEvidenceAssessment

    @model_validator(mode="after")
    def validate_and_identify(self) -> "SemanticEvidenceAuthorization":
        if (
            self.source_attestation.binding
            != self.question_assessment.binding
            or self.question_assessment.source_attestation_id
            != self.source_attestation.attestation_id
        ):
            raise ValueError("semantic authorization bindings do not match")
        currentness = self.source_attestation.binding.currentness
        verification = self.source_attestation.verification_status
        if currentness == CurrentnessState.VERSION_SPECIFIC:
            if verification != VerificationState.VERIFIED_REVISION:
                raise ValueError("version-specific evidence requires revision verification")
        elif currentness == CurrentnessState.ENVIRONMENT_SPECIFIC:
            if verification not in {
                VerificationState.VERIFIED_LIVE,
                VerificationState.VERIFIED_SOURCE,
            }:
                raise ValueError("environment evidence requires live/source verification")
        elif currentness == CurrentnessState.CURRENT:
            if verification not in {
                VerificationState.VERIFIED_LIVE,
                VerificationState.VERIFIED_SOURCE,
            }:
                raise ValueError("current evidence requires live/source verification")
        else:
            raise ValueError("unknown, stale, or conflicting currentness is not semantic")
        identity = self.model_dump(mode="json", exclude={"authorization_id"})
        expected = f"semantic-authorization:{stable_sha256(identity)[:32]}"
        if self.authorization_id and self.authorization_id != expected:
            raise ValueError("authorization_id does not match deterministic identity")
        object.__setattr__(self, "authorization_id", expected)
        return self


class ProviderHitDisposition(BaseModel):
    """Redacted post-policy outcome for each traceable strict provider hit.

    Rejected blinded-evaluation hits are intentionally omitted from the
    serialized result so their count, type, hashes, and reason cannot leak a
    target supervisory signal.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-provider-hit-disposition-v1"] = (
        PROVIDER_HIT_DISPOSITION_SCHEMA
    )
    disposition_id: str = ""
    provider: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    provider_contract_version: str = Field(
        min_length=1,
        max_length=80,
        pattern=_VERSION_TOKEN_PATTERN,
    )
    provider_call_id: str = Field(
        min_length=1, max_length=200, pattern=_OPAQUE_ID_PATTERN
    )
    query_id: str = Field(min_length=1, pattern=_OPAQUE_ID_PATTERN)
    correlation_id: str = Field(
        min_length=1, max_length=200, pattern=_OPAQUE_ID_PATTERN
    )
    source_type: EvidenceSourceType
    source_reference_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider_hit_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    raw_provider_reference: str = Field(
        default="", max_length=_MAX_PROVIDER_REFERENCE_CHARS
    )
    evidence_id: str = ""
    accepted: bool
    applicability: ApplicabilityState
    reason_code: str = Field(min_length=1, max_length=100, pattern=r"^[A-Z0-9_]+$")

    @field_validator("raw_provider_reference")
    @classmethod
    def redact_provider_reference(cls, value: str) -> str:
        return _safe_provider_reference(value)

    @model_validator(mode="after")
    def validate_and_identify(self) -> "ProviderHitDisposition":
        if self.accepted:
            if (
                not self.evidence_id
                or self.applicability != ApplicabilityState.APPLICABLE
            ):
                raise ValueError("accepted disposition requires applicable evidence")
            if self.reason_code != "ACCEPTED":
                raise ValueError("accepted disposition requires ACCEPTED reason")
        elif self.evidence_id:
            raise ValueError("rejected disposition cannot reference canonical evidence")
        identity = self.model_dump(mode="json", exclude={"disposition_id"})
        expected = f"provider-hit:{stable_sha256(identity)[:32]}"
        if self.disposition_id and self.disposition_id != expected:
            raise ValueError("disposition_id does not match deterministic identity")
        self.disposition_id = expected
        return self


class AuthorizedSemanticEvidence(BaseModel):
    """Sealed stage handoff for one independently authorized source/question pair.

    The consumer receives the exact query, provenance, and accepted disposition
    that produced the semantic authorization. This lets the final verifier
    re-check request, principal, temporal, source, and provider-call lineage
    instead of trusting an authorization object in isolation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    handoff_id: str = ""
    authorization: SemanticEvidenceAuthorization
    query: EvidenceQueryV1
    provenance: RetrievalProvenance
    disposition: ProviderHitDisposition

    @model_validator(mode="after")
    def validate_and_identify(self) -> "AuthorizedSemanticEvidence":
        binding = self.authorization.source_attestation.binding
        if (
            self.authorization.question_assessment.binding != binding
            or self.query.query_id != binding.query_id
            or self.query.question_id != binding.question_id
            or self.query.correlation_id != binding.correlation_id
            or self.provenance.provenance_id != binding.provenance_id
            or self.provenance.evidence_id != binding.evidence_id
            or self.provenance.provider != binding.provider
            or self.provenance.provider_contract_version
            != binding.provider_contract_version
            or self.provenance.provider_call_id != binding.provider_call_id
            or self.provenance.query_id != binding.query_id
            or self.provenance.correlation_id != binding.correlation_id
            or self.disposition.disposition_id != binding.disposition_id
            or not self.disposition.accepted
            or self.disposition.reason_code != "ACCEPTED"
            or self.disposition.evidence_id != binding.evidence_id
            or self.disposition.provider != binding.provider
            or self.disposition.provider_contract_version
            != binding.provider_contract_version
            or self.disposition.provider_call_id != binding.provider_call_id
            or self.disposition.query_id != binding.query_id
            or self.disposition.correlation_id != binding.correlation_id
            or self.disposition.source_type != binding.source_type
            or self.disposition.source_reference_sha256
            != binding.source_reference_sha256
            or self.disposition.provider_hit_sha256 != binding.provider_hit_sha256
        ):
            raise ValueError("semantic evidence handoff lineage does not match")
        identity = self.model_dump(mode="json", exclude={"handoff_id"})
        expected = f"semantic-handoff:{stable_sha256(identity)[:32]}"
        if self.handoff_id and self.handoff_id != expected:
            raise ValueError("handoff_id does not match deterministic identity")
        object.__setattr__(self, "handoff_id", expected)
        return self


class DiscoverySynthesis(BaseModel):
    """Provider-generated discovery text that cannot enter evidence v2."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-discovery-synthesis-v1"] = (
        DISCOVERY_SYNTHESIS_SCHEMA
    )
    synthesis_id: str = ""
    provider: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    provider_contract_version: str = Field(
        min_length=1,
        max_length=80,
        pattern=_VERSION_TOKEN_PATTERN,
    )
    provider_call_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=_OPAQUE_ID_PATTERN,
    )
    query_id: str = Field(min_length=1, pattern=_OPAQUE_ID_PATTERN)
    correlation_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=_OPAQUE_ID_PATTERN,
    )
    text: str = Field(min_length=1, max_length=100_000)
    derived_from: list[str] = Field(default_factory=list)
    raw_provider_reference: str = Field(default="", max_length=2000)
    authority_class: Literal["SUPPORTING_DISCOVERY"] = "SUPPORTING_DISCOVERY"
    source_type: Literal["MODEL_INFERENCE"] = "MODEL_INFERENCE"
    directness: Literal["DERIVED"] = "DERIVED"
    verification_status: VerificationState = VerificationState.ANALYZED
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("derived_from")
    @classmethod
    def normalize_lineage(cls, values: list[str]) -> list[str]:
        return _clean_string_set(values)

    @field_validator("text")
    @classmethod
    def redact_synthesis_text(cls, value: str) -> str:
        return _safe_source_text(value)

    @field_validator("raw_provider_reference")
    @classmethod
    def redact_provider_reference(cls, value: str) -> str:
        return _safe_provider_reference(value)

    @field_validator("verification_status")
    @classmethod
    def restrict_verification(cls, value: VerificationState) -> VerificationState:
        if value not in {VerificationState.ANALYZED, VerificationState.UNVERIFIED}:
            raise ValueError("discovery synthesis may only be analyzed or unverified")
        return value

    @model_validator(mode="after")
    def identify(self) -> "DiscoverySynthesis":
        identity = self.model_dump(
            mode="json",
            exclude={
                "synthesis_id",
                "correlation_id",
                "provider_call_id",
                "raw_provider_reference",
            },
        )
        expected = f"discovery:{stable_sha256(identity)[:32]}"
        if self.synthesis_id and self.synthesis_id != expected:
            raise ValueError("synthesis_id does not match deterministic identity")
        self.synthesis_id = expected
        return self


class EvidenceProviderRawResult(BaseModel):
    """Transient adapter output; final status is assigned by the executor."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    provider_contract_version: str = Field(
        min_length=1,
        max_length=80,
        pattern=_VERSION_TOKEN_PATTERN,
    )
    provider_call_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=_OPAQUE_ID_PATTERN,
    )
    raw_provider_reference: str = Field(
        default="", max_length=_MAX_PROVIDER_REFERENCE_CHARS
    )
    query_id: str = Field(min_length=1, pattern=_OPAQUE_ID_PATTERN)
    correlation_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=_OPAQUE_ID_PATTERN,
    )
    raw_hits: list[StrictProviderHit] = Field(default_factory=list, max_length=100)
    discovery_syntheses: list[DiscoverySynthesis] = Field(
        default_factory=list, max_length=20
    )
    discovery_synthesis_hit_references: dict[str, list[str]] = Field(
        default_factory=dict
    )
    transport_outcome: ProviderTransportOutcome = ProviderTransportOutcome.COMPLETED
    applied_filters: list[str] = Field(default_factory=list)
    unsupported_filters: list[str] = Field(default_factory=list)
    attempts: int = Field(default=1, ge=0, le=10)
    attempt_outcomes: list[ProviderTransportOutcome] = Field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    source_snapshot_retrieved_at: str = ""
    cache_served_at: str = ""
    duration_ms: int = Field(default=0, ge=0)
    truncated: bool = False
    cache_state: ProviderCacheState = ProviderCacheState.UNKNOWN
    cache_schema_version: str = Field(default="", max_length=80)
    cache_entry_age_seconds: float | None = Field(default=None, ge=0.0)
    circuit_state_before: ProviderCircuitState = ProviderCircuitState.CLOSED
    circuit_state_after: ProviderCircuitState = ProviderCircuitState.CLOSED
    retryable: bool = False
    redacted_error_code: str = Field(default="", max_length=100)
    redacted_message: str = Field(default="", max_length=_MAX_DIAGNOSTIC_CHARS)
    redacted_required_action: str = Field(default="", max_length=100)

    @field_validator("applied_filters", "unsupported_filters")
    @classmethod
    def normalize_filters(cls, values: list[str]) -> list[str]:
        return _clean_string_set(values)

    @field_validator(
        "started_at",
        "completed_at",
        "source_snapshot_retrieved_at",
        "cache_served_at",
    )
    @classmethod
    def validate_timestamps(cls, value: str) -> str:
        text = str(value or "").strip()
        if text:
            _parse_timestamp(text)
        return text

    @field_validator("cache_entry_age_seconds")
    @classmethod
    def require_finite_cache_age(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("cache_entry_age_seconds must be finite")
        return value

    @field_validator(
        "redacted_error_code",
        "redacted_message",
        "redacted_required_action",
    )
    @classmethod
    def redact_diagnostics(cls, value: str) -> str:
        return _safe_diagnostic(value)

    @field_validator("raw_provider_reference")
    @classmethod
    def redact_call_reference(cls, value: str) -> str:
        return _safe_provider_reference(value)

    @field_validator("discovery_synthesis_hit_references")
    @classmethod
    def normalize_synthesis_hit_references(
        cls, value: dict[str, list[str]]
    ) -> dict[str, list[str]]:
        return {
            str(synthesis_id).strip(): _clean_string_set(references)
            for synthesis_id, references in sorted(value.items())
            if str(synthesis_id).strip()
        }

    @model_validator(mode="after")
    def validate_raw_synthesis_lineage(self) -> "EvidenceProviderRawResult":
        if any(synthesis.derived_from for synthesis in self.discovery_syntheses):
            raise ValueError(
                "raw discovery synthesis cannot assert canonical evidence lineage"
            )
        synthesis_ids = {
            synthesis.synthesis_id for synthesis in self.discovery_syntheses
        }
        if not set(self.discovery_synthesis_hit_references).issubset(synthesis_ids):
            raise ValueError(
                "discovery synthesis linkage references an unknown synthesis"
            )
        hit_references = {hit.raw_provider_reference for hit in self.raw_hits}
        linked_references = {
            reference
            for references in self.discovery_synthesis_hit_references.values()
            for reference in references
        }
        if not linked_references.issubset(hit_references):
            raise ValueError("discovery synthesis linkage references an unknown hit")
        return self


class EvidenceProviderCallResult(BaseModel):
    """Redacted, post-policy result of one logical provider call."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-provider-result-v1"] = PROVIDER_RESULT_SCHEMA
    provider_result_id: str = ""
    provider: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    provider_contract_version: str = Field(
        min_length=1,
        max_length=80,
        pattern=_VERSION_TOKEN_PATTERN,
    )
    provider_call_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=_OPAQUE_ID_PATTERN,
    )
    raw_provider_reference: str = Field(
        default="", max_length=_MAX_PROVIDER_REFERENCE_CHARS
    )
    query_id: str = Field(min_length=1, pattern=_OPAQUE_ID_PATTERN)
    correlation_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=_OPAQUE_ID_PATTERN,
    )
    status: EvidenceProviderStatus
    transport_outcome: ProviderTransportOutcome = ProviderTransportOutcome.COMPLETED
    accepted_evidence_ids: list[str] = Field(default_factory=list)
    accepted_evidence_count: int = Field(ge=0)
    rejected_hit_count: int = Field(default=0, ge=0)
    applied_filters: list[str] = Field(default_factory=list)
    unsupported_filters: list[str] = Field(default_factory=list)
    attempts: int = Field(default=1, ge=0, le=10)
    attempt_outcomes: list[ProviderTransportOutcome] = Field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    source_snapshot_retrieved_at: str = ""
    cache_served_at: str = ""
    duration_ms: int = Field(default=0, ge=0)
    truncated: bool = False
    cache_state: ProviderCacheState = ProviderCacheState.UNKNOWN
    cache_schema_version: str = Field(default="", max_length=80)
    cache_entry_age_seconds: float | None = Field(default=None, ge=0.0)
    circuit_state_before: ProviderCircuitState = ProviderCircuitState.CLOSED
    circuit_state_after: ProviderCircuitState = ProviderCircuitState.CLOSED
    retryable: bool = False
    redacted_error_code: str = Field(default="", max_length=100)
    redacted_message: str = Field(default="", max_length=_MAX_DIAGNOSTIC_CHARS)
    redacted_required_action: str = Field(default="", max_length=100)
    partial_reason: str = Field(default="", max_length=_MAX_DIAGNOSTIC_CHARS)

    @field_validator("accepted_evidence_ids", "applied_filters", "unsupported_filters")
    @classmethod
    def normalize_sets(cls, values: list[str]) -> list[str]:
        return _clean_string_set(values)

    @field_validator(
        "started_at",
        "completed_at",
        "source_snapshot_retrieved_at",
        "cache_served_at",
    )
    @classmethod
    def validate_timestamps(cls, value: str) -> str:
        text = str(value or "").strip()
        if text:
            _parse_timestamp(text)
        return text

    @field_validator("cache_entry_age_seconds")
    @classmethod
    def require_finite_cache_age(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("cache_entry_age_seconds must be finite")
        return value

    @field_validator(
        "redacted_error_code",
        "redacted_message",
        "redacted_required_action",
        "partial_reason",
    )
    @classmethod
    def redact_diagnostics(cls, value: str) -> str:
        return _safe_diagnostic(value)

    @field_validator("raw_provider_reference")
    @classmethod
    def redact_call_reference(cls, value: str) -> str:
        return _safe_provider_reference(value)

    @model_validator(mode="after")
    def validate_cardinality_and_identify(self) -> "EvidenceProviderCallResult":
        if self.accepted_evidence_count != len(self.accepted_evidence_ids):
            raise ValueError(
                "accepted_evidence_count must equal accepted_evidence_ids length"
            )
        positive = self.status in {
            EvidenceProviderStatus.SUCCESS,
            EvidenceProviderStatus.PARTIAL,
        }
        if positive and not self.accepted_evidence_ids:
            raise ValueError(f"{self.status.value} requires accepted evidence")
        if not positive and self.accepted_evidence_ids:
            raise ValueError(f"{self.status.value} cannot contain accepted evidence")
        if self.status == EvidenceProviderStatus.PARTIAL and not self.partial_reason:
            raise ValueError("PARTIAL requires a redacted partial_reason")
        if self.status in {
            EvidenceProviderStatus.SUCCESS,
            EvidenceProviderStatus.EMPTY,
        } and self.transport_outcome != ProviderTransportOutcome.COMPLETED:
            raise ValueError(
                f"{self.status.value} requires a completed transport outcome"
            )
        expected_transport = _STATUS_TRANSPORT.get(self.status)
        if (
            expected_transport is not None
            and self.transport_outcome != expected_transport
            and not (
                self.status == EvidenceProviderStatus.PROVIDER_ERROR
                and self.transport_outcome == ProviderTransportOutcome.COMPLETED
                and self.redacted_error_code == "INCOMPLETE_RESULT"
            )
        ):
            raise ValueError("provider status does not match transport outcome")
        if self.cache_state == ProviderCacheState.HIT and self.attempts != 0:
            raise ValueError("cache hits cannot claim provider attempts")
        if self.attempts == 0 and self.attempt_outcomes:
            raise ValueError("zero-attempt calls cannot contain attempt outcomes")
        if len(self.attempt_outcomes) != self.attempts:
            raise ValueError(
                "attempt_outcomes must contain one outcome per provider attempt"
            )
        identity = self.model_dump(mode="json", exclude={"provider_result_id"})
        expected = f"provider-result:{stable_sha256(identity)[:32]}"
        if self.provider_result_id and self.provider_result_id != expected:
            raise ValueError(
                "provider_result_id does not match deterministic result identity"
            )
        self.provider_result_id = expected
        return self


@dataclass(frozen=True, slots=True)
class EvidenceProviderExecutionContext:
    """Non-serializable execution context.  Credentials are intentionally absent."""

    principal: RuntimePrincipal
    run_id: str
    request_id: str
    correlation_id: str
    benchmark_split: Literal["", "train", "validation", "blind"] = ""
    timeout_seconds: float = 300.0
    cancellation_check: Callable[[], bool] = _never_cancelled
    source_visibility_check: Callable[[StrictProviderHit], bool] = (
        _deny_unverified_source
    )
    source_verification_check: Callable[[StrictProviderHit], bool] = (
        _deny_unverified_source
    )
    started_monotonic: float = field(default_factory=monotonic, repr=False)

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if not str(self.principal.tenant_id or "").strip():
            raise ValueError(
                "provider execution requires a non-empty tenant identifier"
            )
        if not str(self.principal.principal_id or "").strip():
            raise ValueError(
                "provider execution requires a non-empty principal identifier"
            )
        if not self.run_id or not self.request_id or not self.correlation_id:
            raise ValueError("run, request, and correlation identifiers are required")
        if any(
            _OPAQUE_ID_RE.fullmatch(value) is None
            for value in (self.run_id, self.request_id, self.correlation_id)
        ):
            raise ValueError("execution identifiers must be opaque safe identifiers")
        if self.benchmark_split not in {"", "train", "validation", "blind"}:
            raise ValueError("benchmark_split is invalid")

    @property
    def deadline_monotonic(self) -> float:
        return self.started_monotonic + self.timeout_seconds

    def cancelled(self) -> bool:
        try:
            return bool(self.cancellation_check())
        except Exception:
            return True

    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline_monotonic - monotonic())

    def source_is_visible(self, hit: StrictProviderHit) -> bool:
        try:
            return self.source_visibility_check(hit) is True
        except Exception:
            return False

    def source_is_verified(self, hit: StrictProviderHit) -> bool:
        try:
            return self.source_verification_check(hit) is True
        except Exception:
            return False


@runtime_checkable
class EvidenceProvider(Protocol):
    def descriptor(self) -> EvidenceProviderDescriptor: ...

    def retrieve(
        self, query: EvidenceQueryV1, context: EvidenceProviderExecutionContext
    ) -> EvidenceProviderRawResult: ...


class EvidenceProviderException(Exception):
    """Typed provider failure whose public message is redacted and bounded."""

    status = EvidenceProviderStatus.PROVIDER_ERROR
    error_code = "PROVIDER_ERROR"
    retryable = False

    def __init__(
        self,
        message: str = "Provider execution failed.",
        *,
        error_code: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        self.redacted_message = (
            _safe_diagnostic(message) or "Provider execution failed."
        )
        self.redacted_error_code = _safe_diagnostic(error_code or self.error_code)
        if retryable is not None:
            self.retryable = bool(retryable)
        super().__init__(self.redacted_message)


class EvidenceProviderTimeout(EvidenceProviderException):
    status = EvidenceProviderStatus.TIMEOUT
    error_code = "TIMEOUT"
    retryable = True


class EvidenceProviderAuthError(EvidenceProviderException):
    status = EvidenceProviderStatus.AUTH_ERROR
    error_code = "AUTH_ERROR"


class EvidenceProviderRateLimited(EvidenceProviderException):
    status = EvidenceProviderStatus.RATE_LIMITED
    error_code = "RATE_LIMITED"
    retryable = True


class EvidenceProviderInvalidResponse(EvidenceProviderException):
    status = EvidenceProviderStatus.INVALID_RESPONSE
    error_code = "INVALID_RESPONSE"


class EvidenceProviderCancelled(EvidenceProviderException):
    status = EvidenceProviderStatus.PROVIDER_ERROR
    error_code = "CANCELLED"


class ProviderHitRejected(ValueError):
    """Internal policy rejection; the message is a stable code, not source text."""


_SOURCE_AUTHORITY: dict[EvidenceSourceType, AuthorityClass] = {
    EvidenceSourceType.DITA_SPECIFICATION: AuthorityClass.SPECIFICATION_AUTHORITY,
    EvidenceSourceType.DITA_OT_DOCUMENTATION: AuthorityClass.SPECIFICATION_AUTHORITY,
    EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION: AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
    EvidenceSourceType.AEM_ASSETS_PLATFORM_DOCUMENTATION: AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
    EvidenceSourceType.CURRENT_CODE: AuthorityClass.IMPLEMENTATION_CONFIRMED,
    EvidenceSourceType.CURRENT_PR: AuthorityClass.IMPLEMENTATION_CONFIRMED,
    EvidenceSourceType.IMPLEMENTATION_DIFF: AuthorityClass.IMPLEMENTATION_CONFIRMED,
    EvidenceSourceType.CODE_DIFF: AuthorityClass.IMPLEMENTATION_CONFIRMED,
    EvidenceSourceType.EXISTING_AUTOMATION: AuthorityClass.IMPLEMENTATION_CONFIRMED,
    EvidenceSourceType.HISTORICAL_JIRA: AuthorityClass.HISTORICAL_EXPECTATION,
    EvidenceSourceType.CUSTOMER_REQUEST: AuthorityClass.CUSTOMER_REQUEST,
    EvidenceSourceType.CUSTOMER_WORKFLOW: AuthorityClass.CUSTOMER_REQUEST,
    EvidenceSourceType.BUSINESS_IMPACT: AuthorityClass.CUSTOMER_REQUEST,
    EvidenceSourceType.SCALE_SIGNAL: AuthorityClass.CUSTOMER_REQUEST,
    EvidenceSourceType.USER_FEEDBACK: AuthorityClass.PENDING_HUMAN_REVIEW,
    # A provider hit cannot assert that a human accepted a contract.  Those
    # source classes stay pending until a separate source verifier confirms it.
    EvidenceSourceType.ACCEPTED_UAC: AuthorityClass.PENDING_HUMAN_REVIEW,
    EvidenceSourceType.PRODUCT_DECISION: AuthorityClass.PENDING_HUMAN_REVIEW,
    EvidenceSourceType.ENGINEERING_DECISION: AuthorityClass.PENDING_HUMAN_REVIEW,
}

# These source labels carry human acceptance or current-ticket semantics in
# the canonical runtime.  A discovery provider cannot attest those semantics;
# they require separate source-native ingestion/verification.
_PROVIDER_HUMAN_TRUTH_SOURCE_TYPES = {
    EvidenceSourceType.ACCEPTED_UAC,
    EvidenceSourceType.ENGINEERING_DECISION,
    EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA,
    EvidenceSourceType.JIRA_DESCRIPTION,
    EvidenceSourceType.PRODUCT_DECISION,
    EvidenceSourceType.CURRENT_JIRA,
    EvidenceSourceType.USER_FEEDBACK,
}

# Blind evaluation accepts only independently inspectable product, spec, code,
# and automation source families.  Human labels, historical Jira/UAC material,
# screenshots, observations, and unknown sources stay outside the blind bundle.
_BLIND_PROVIDER_SOURCE_TYPES = {
    EvidenceSourceType.AEM_ASSETS_PLATFORM_DOCUMENTATION,
    EvidenceSourceType.CODE_DIFF,
    EvidenceSourceType.CURRENT_CODE,
    EvidenceSourceType.CURRENT_PR,
    EvidenceSourceType.DITA_OT_DOCUMENTATION,
    EvidenceSourceType.DITA_SPECIFICATION,
    EvidenceSourceType.EXISTING_AUTOMATION,
    EvidenceSourceType.IMPLEMENTATION_DIFF,
    EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
}
_BLINDED_BENCHMARK_SPLITS = {"validation", "blind"}
_JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b", re.IGNORECASE)


def _authority_for(source_type: EvidenceSourceType) -> AuthorityClass:
    return _SOURCE_AUTHORITY.get(source_type, AuthorityClass.UNKNOWN)


def _authority_subject_for(source_type: EvidenceSourceType) -> AuthoritySubject:
    if source_type in {
        EvidenceSourceType.DITA_SPECIFICATION,
        EvidenceSourceType.DITA_OT_DOCUMENTATION,
    }:
        return AuthoritySubject.DITA_SEMANTICS
    if source_type in {
        EvidenceSourceType.CURRENT_CODE,
        EvidenceSourceType.CURRENT_PR,
        EvidenceSourceType.IMPLEMENTATION_DIFF,
        EvidenceSourceType.CODE_DIFF,
        EvidenceSourceType.EXISTING_AUTOMATION,
    }:
        return AuthoritySubject.ACTUAL_IMPLEMENTATION
    if source_type in {
        EvidenceSourceType.UI_OBSERVATION,
        EvidenceSourceType.OBSERVED_UI_FLOW,
        EvidenceSourceType.SCREENSHOT_REPRODUCTION,
    }:
        return AuthoritySubject.CURRENT_UI
    return AuthoritySubject.PRODUCT_CONTRACT


def _references_target_jira(hit: StrictProviderHit, jira_reference: str) -> bool:
    target_keys = {
        match.group(0).casefold()
        for match in _JIRA_KEY_RE.finditer(str(jira_reference or ""))
    }
    if not target_keys:
        return False
    source_identity = "\n".join(
        (hit.source_reference, hit.source_locator, hit.source_native_id)
    ).casefold()
    return any(key in source_identity for key in target_keys)


def _ownership_for(source_type: EvidenceSourceType) -> ProductOwnership:
    contract = ProductContractOwnership.AEM_GUIDES_PRODUCT_CONTRACT
    if source_type == EvidenceSourceType.DITA_SPECIFICATION:
        contract = ProductContractOwnership.DITA_SPECIFICATION_CONTRACT
    elif source_type == EvidenceSourceType.DITA_OT_DOCUMENTATION:
        contract = ProductContractOwnership.DITA_OT_PROCESSING_BEHAVIOR
    elif source_type in {
        EvidenceSourceType.CURRENT_CODE,
        EvidenceSourceType.CURRENT_PR,
        EvidenceSourceType.IMPLEMENTATION_DIFF,
        EvidenceSourceType.CODE_DIFF,
        EvidenceSourceType.EXISTING_AUTOMATION,
    }:
        contract = ProductContractOwnership.CURRENT_IMPLEMENTATION_EVIDENCE
    elif source_type in {
        EvidenceSourceType.UI_OBSERVATION,
        EvidenceSourceType.OBSERVED_UI_FLOW,
        EvidenceSourceType.SCREENSHOT_REPRODUCTION,
    }:
        contract = ProductContractOwnership.OBSERVED_UI_STATE
    elif source_type in {
        EvidenceSourceType.CUSTOMER_REQUEST,
        EvidenceSourceType.CUSTOMER_WORKFLOW,
        EvidenceSourceType.USER_FEEDBACK,
        EvidenceSourceType.BUSINESS_IMPACT,
        EvidenceSourceType.SCALE_SIGNAL,
    }:
        contract = ProductContractOwnership.USER_REPORTED_BEHAVIOR
    return ProductOwnership(contract_ownership=contract, owner_status="inferred")


def _currentness_for(hit: StrictProviderHit) -> CurrentnessState:
    if (
        any(
            (
                hit.source_version,
                hit.dita_version,
                hit.repository_revision,
                hit.branch,
            )
        )
        or hit.dirty is not None
    ):
        return CurrentnessState.VERSION_SPECIFIC
    if hit.deployment_model or hit.environment:
        return CurrentnessState.ENVIRONMENT_SPECIFIC
    return CurrentnessState.VERSION_UNKNOWN


def _evidence_source_projection(record: EvidenceRecord) -> dict[str, Any]:
    """Fields that must agree whenever canonical evidence identity agrees."""

    # Retrieval time is operational provenance, not a source fact.  Excluding
    # it permits the same source/content to be rediscovered by another provider
    # without producing a false source conflict.
    version_scope = record.version_scope.model_dump(mode="json")
    version_scope.pop("retrieved_at", None)

    return {
        "source_type": record.source_type,
        "source_reference": record.source_reference,
        "source_location": record.source_location,
        "source_native_id": record.source_native_id,
        "tenant_id": record.tenant_id,
        "content": record.content,
        "source_timestamp": record.source_timestamp,
        "product_version": record.product_version,
        "dita_version": record.dita_version,
        "deployment_model": record.deployment_model,
        "environment": record.environment,
        "version_scope": version_scope,
    }


def _hit_allowed_by_temporal_policy(
    hit: StrictProviderHit, boundary: TemporalBoundary
) -> bool:
    timestamp = _parse_timestamp(hit.source_updated_at or hit.source_timestamp)
    constraints = (
        _parse_timestamp(boundary.as_of),
        _parse_timestamp(boundary.source_not_before),
        _parse_timestamp(boundary.source_not_after),
    )
    if any(constraints) and timestamp is None:
        return False
    as_of, lower, upper = constraints
    if as_of and timestamp and timestamp > as_of:
        return False
    if lower and timestamp and timestamp < lower:
        return False
    if upper and timestamp and timestamp > upper:
        return False
    scope = boundary.version_scope
    versions = set(scope.product_versions)
    if versions and hit.source_version not in versions:
        return False
    expected_revision = scope.repository_revision
    if expected_revision and hit.repository_revision != expected_revision:
        return False
    exact_fields = (
        (scope.dita_version, hit.dita_version),
        (scope.deployment_model, hit.deployment_model),
        (scope.repository, hit.repository),
        (scope.branch, hit.branch),
        (scope.environment, hit.environment),
    )
    if any(expected and actual != expected for expected, actual in exact_fields):
        return False
    if scope.dirty is not None and hit.dirty is not scope.dirty:
        return False
    timestamp_fields = (
        (scope.source_updated_at, hit.source_updated_at or hit.source_timestamp),
        (scope.retrieved_at, hit.retrieved_at),
    )
    for expected, actual in timestamp_fields:
        if not expected:
            continue
        if not actual or _parse_timestamp(actual) != _parse_timestamp(expected):
            return False
    return True


def normalize_provider_hit(
    hit: StrictProviderHit,
    query: EvidenceQueryV1,
    context: EvidenceProviderExecutionContext,
) -> EvidenceRecord:
    """Normalize one strict hit without trusting provider authority or tenancy."""

    if not context.source_is_visible(hit):
        raise ProviderHitRejected("SOURCE_VISIBILITY_NOT_ATTESTED")

    if (
        context.benchmark_split in _BLINDED_BENCHMARK_SPLITS
        and not context.source_is_verified(hit)
    ):
        raise ProviderHitRejected("BLIND_SOURCE_NOT_VERIFIED")

    if hit.source_type == EvidenceSourceType.USER_FEEDBACK:
        raise ProviderHitRejected("PROVIDER_CANNOT_CREATE_HUMAN_FEEDBACK")
    if hit.source_type in _PROVIDER_HUMAN_TRUTH_SOURCE_TYPES:
        raise ProviderHitRejected("PROVIDER_CANNOT_ATTEST_HUMAN_CONTRACT")
    if (
        context.benchmark_split in _BLINDED_BENCHMARK_SPLITS
        and hit.source_type not in _BLIND_PROVIDER_SOURCE_TYPES
    ):
        raise ProviderHitRejected("BLIND_SOURCE_TYPE_NOT_ALLOWED")
    if context.benchmark_split in _BLINDED_BENCHMARK_SPLITS and _references_target_jira(
        hit, query.jira_reference
    ):
        raise ProviderHitRejected("BLIND_TARGET_JIRA_EXCLUDED")

    if (
        query.requested_evidence_types
        and hit.source_type not in query.requested_evidence_types
    ):
        raise ProviderHitRejected("SOURCE_TYPE_NOT_REQUESTED")
    if hit.source_type in query.excluded_sources.source_types:
        raise ProviderHitRejected("SOURCE_TYPE_EXCLUDED")
    excluded_references = set(query.excluded_sources.source_references)
    if (
        hit.source_reference in excluded_references
        or hit.source_locator in excluded_references
    ):
        raise ProviderHitRejected("SOURCE_REFERENCE_EXCLUDED")
    if provider_hit_content_sha256(hit) in set(query.excluded_sources.content_sha256):
        raise ProviderHitRejected("SOURCE_CONTENT_EXCLUDED")
    if not _hit_allowed_by_temporal_policy(hit, query.temporal_boundary):
        raise ProviderHitRejected("TEMPORAL_OR_VERSION_MISMATCH")

    authority = _authority_for(hit.source_type)
    authority_subject = _authority_subject_for(hit.source_type)
    requirement = query.authority_requirement
    if authority_subject != requirement.subject:
        raise ProviderHitRejected("AUTHORITY_SUBJECT_MISMATCH")
    if (
        requirement.acceptable_classes
        and authority not in requirement.acceptable_classes
    ):
        raise ProviderHitRejected("AUTHORITY_CLASS_NOT_ACCEPTABLE")
    # A strict source hit is direct, but remains unverified until a source-native
    # verifier confirms it independently of provider synthesis.
    if requirement.verified_source_required:
        raise ProviderHitRejected("VERIFIED_SOURCE_REQUIRED")

    currentness = _currentness_for(hit)
    if (
        query.temporal_boundary.allowed_currentness
        and currentness not in query.temporal_boundary.allowed_currentness
    ):
        raise ProviderHitRejected("CURRENTNESS_NOT_ALLOWED")

    tenant_id = context.principal.tenant_id
    source_updated_at = hit.source_updated_at or hit.source_timestamp
    return EvidenceRecord(
        source_type=hit.source_type,
        authority_subject=authority_subject,
        source_reference=hit.source_reference,
        source_location=hit.source_locator,
        source_native_id=hit.source_native_id,
        tenant_id=tenant_id,
        content={"text": hit.text, "title": hit.title},
        source_timestamp=source_updated_at,
        retrieved_at="",
        product_version=hit.source_version,
        dita_version=hit.dita_version,
        deployment_model=hit.deployment_model,
        environment=hit.environment,
        currentness=currentness,
        # Provider score/model confidence is not source confidence.  A source
        # remains UNKNOWN/0 until a source-native verifier attests it.
        evidence_confidence=0.0,
        requirement_authority=authority,
        verification_status=VerificationState.UNVERIFIED,
        evidence_role="SUPPORTING",
        retrieval_query=query.question,
        retrieval_pass="reasoning-directed-provider",
        retrieved_by_query=[query.query_id],
        directness=EvidenceDirectness.DIRECT,
        version_scope=VersionScope(
            product_versions=[hit.source_version] if hit.source_version else [],
            dita_version=hit.dita_version,
            deployment_model=hit.deployment_model,
            repository=hit.repository,
            repository_revision=hit.repository_revision,
            branch=hit.branch,
            dirty=hit.dirty,
            environment=hit.environment,
            source_updated_at=source_updated_at,
            retrieved_at=hit.retrieved_at,
        ),
        ownership=_ownership_for(hit.source_type),
        visibility=SourceVisibility(
            classification=VisibilityClass.TENANT,
            tenant_id=tenant_id,
            contains_customer_data=hit.source_type
            in {
                EvidenceSourceType.CUSTOMER_REQUEST,
                EvidenceSourceType.CUSTOMER_WORKFLOW,
                EvidenceSourceType.USER_FEEDBACK,
                EvidenceSourceType.HISTORICAL_JIRA,
            },
            redacted=True,
        ),
        metadata={"title": hit.title, "provider_native_kind": hit.provider_native_kind},
    )


class StrictProviderHitNormalizer:
    def normalize(
        self,
        hit: StrictProviderHit,
        query: EvidenceQueryV1,
        context: EvidenceProviderExecutionContext,
    ) -> EvidenceRecord:
        return normalize_provider_hit(hit, query, context)


class EvidenceProviderTraceSidecar(BaseModel):
    """Redacted operational linkage kept outside semantic evidence identity."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-provider-trace-sidecar-v1"] = (
        PROVIDER_TRACE_SIDECAR_SCHEMA
    )
    trace_id: str = ""
    provider: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    run_id: str = Field(min_length=1, max_length=200, pattern=_OPAQUE_ID_PATTERN)
    request_id: str = Field(min_length=1, max_length=200, pattern=_OPAQUE_ID_PATTERN)
    question_id: str = Field(min_length=1)
    query_id: str = Field(min_length=1, pattern=_OPAQUE_ID_PATTERN)
    correlation_id: str = Field(
        min_length=1, max_length=200, pattern=_OPAQUE_ID_PATTERN
    )
    provider_call_id: str = Field(
        min_length=1, max_length=200, pattern=_OPAQUE_ID_PATTERN
    )
    provider_result_id: str = Field(min_length=1, pattern=_OPAQUE_ID_PATTERN)
    evidence_ids: list[str] = Field(default_factory=list)
    provenance_ids: list[str] = Field(default_factory=list)
    disposition_ids: list[str] = Field(default_factory=list)
    synthesis_ids: list[str] = Field(default_factory=list)

    @field_validator(
        "evidence_ids",
        "provenance_ids",
        "disposition_ids",
        "synthesis_ids",
    )
    @classmethod
    def normalize_ids(cls, values: list[str]) -> list[str]:
        return _clean_string_set(values)

    @model_validator(mode="after")
    def identify(self) -> "EvidenceProviderTraceSidecar":
        identity = self.model_dump(mode="json", exclude={"trace_id"})
        expected = f"provider-trace:{stable_sha256(identity)[:32]}"
        if self.trace_id and self.trace_id != expected:
            raise ValueError("trace_id does not match deterministic identity")
        self.trace_id = expected
        return self


class ProviderExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_result: EvidenceProviderCallResult
    evidence_bundle: CanonicalEvidenceBundle
    provenance: list[RetrievalProvenance] = Field(default_factory=list)
    hit_dispositions: list[ProviderHitDisposition] = Field(default_factory=list)
    discovery_syntheses: list[DiscoverySynthesis] = Field(default_factory=list)
    trace_sidecar: EvidenceProviderTraceSidecar

    @model_validator(mode="after")
    def validate_references(self) -> "ProviderExecutionResult":
        evidence_ids = {record.evidence_id for record in self.evidence_bundle.records}
        if not set(self.call_result.accepted_evidence_ids).issubset(evidence_ids):
            raise ValueError("accepted evidence IDs must exist in the evidence bundle")
        if any(row.evidence_id not in evidence_ids for row in self.provenance):
            raise ValueError("retrieval provenance must reference bundled evidence")
        if any(
            not set(synthesis.derived_from).issubset(evidence_ids)
            for synthesis in self.discovery_syntheses
        ):
            raise ValueError(
                "discovery synthesis lineage must reference bundled evidence"
            )
        trace = self.trace_sidecar
        if (
            trace.provider != self.call_result.provider
            or trace.query_id != self.call_result.query_id
            or trace.correlation_id != self.call_result.correlation_id
            or trace.provider_call_id != self.call_result.provider_call_id
            or trace.provider_result_id != self.call_result.provider_result_id
            or trace.evidence_ids != self.call_result.accepted_evidence_ids
            or trace.provenance_ids
            != sorted(row.provenance_id for row in self.provenance)
            or trace.disposition_ids
            != sorted(row.disposition_id for row in self.hit_dispositions)
            or trace.synthesis_ids
            != sorted(row.synthesis_id for row in self.discovery_syntheses)
        ):
            raise ValueError("provider trace sidecar does not match execution result")
        return self


_TRANSPORT_STATUS: dict[ProviderTransportOutcome, EvidenceProviderStatus] = {
    ProviderTransportOutcome.TIMEOUT: EvidenceProviderStatus.TIMEOUT,
    ProviderTransportOutcome.AUTH_ERROR: EvidenceProviderStatus.AUTH_ERROR,
    ProviderTransportOutcome.RATE_LIMITED: EvidenceProviderStatus.RATE_LIMITED,
    ProviderTransportOutcome.PROVIDER_ERROR: EvidenceProviderStatus.PROVIDER_ERROR,
    ProviderTransportOutcome.INVALID_RESPONSE: EvidenceProviderStatus.INVALID_RESPONSE,
}

_STATUS_TRANSPORT: dict[EvidenceProviderStatus, ProviderTransportOutcome] = {
    EvidenceProviderStatus.TIMEOUT: ProviderTransportOutcome.TIMEOUT,
    EvidenceProviderStatus.AUTH_ERROR: ProviderTransportOutcome.AUTH_ERROR,
    EvidenceProviderStatus.RATE_LIMITED: ProviderTransportOutcome.RATE_LIMITED,
    EvidenceProviderStatus.PROVIDER_ERROR: ProviderTransportOutcome.PROVIDER_ERROR,
    EvidenceProviderStatus.INVALID_RESPONSE: ProviderTransportOutcome.INVALID_RESPONSE,
}


class EvidenceProviderExecutor:
    """Validate, normalize, filter, and finalize one bounded provider call."""

    def __init__(self, normalizer: StrictProviderHitNormalizer | None = None) -> None:
        self._normalizer = normalizer or StrictProviderHitNormalizer()

    def execute(
        self,
        provider: EvidenceProvider,
        query: EvidenceQueryV1,
        context: EvidenceProviderExecutionContext,
        *,
        base_bundle: CanonicalEvidenceBundle | None = None,
        resilience_metadata_trusted: bool = False,
    ) -> ProviderExecutionResult:
        descriptor = provider.descriptor()
        started_at = _utc_now()
        started_clock = monotonic()
        fallback_call_id = self._call_id(
            descriptor.provider, query.query_id, context.correlation_id
        )

        if query.correlation_id != context.correlation_id:
            return self._failure(
                descriptor=descriptor,
                query=query,
                context=context,
                base_bundle=None,
                provider_call_id=fallback_call_id,
                status=EvidenceProviderStatus.INVALID_RESPONSE,
                error_code="CORRELATION_ID_MISMATCH",
                message="Query and execution correlation identifiers differ.",
                started_at=started_at,
                started_clock=started_clock,
            )
        preflight_error = self._context_preflight_error(
            query=query,
            context=context,
            base_bundle=base_bundle,
        )
        if preflight_error:
            error_code, message = preflight_error
            return self._failure(
                descriptor=descriptor,
                query=query,
                context=context,
                base_bundle=None,
                provider_call_id=fallback_call_id,
                status=EvidenceProviderStatus.INVALID_RESPONSE,
                error_code=error_code,
                message=message,
                started_at=started_at,
                started_clock=started_clock,
            )
        if context.cancelled():
            return self._failure(
                descriptor=descriptor,
                query=query,
                context=context,
                base_bundle=base_bundle,
                provider_call_id=fallback_call_id,
                status=EvidenceProviderStatus.PROVIDER_ERROR,
                error_code="CANCELLED",
                message="Provider call was cancelled.",
                started_at=started_at,
                started_clock=started_clock,
            )
        if context.remaining_seconds() <= 0:
            return self._failure(
                descriptor=descriptor,
                query=query,
                context=context,
                base_bundle=base_bundle,
                provider_call_id=fallback_call_id,
                status=EvidenceProviderStatus.TIMEOUT,
                error_code="TIMEOUT",
                message="Provider deadline expired before dispatch.",
                started_at=started_at,
                started_clock=started_clock,
                retryable=True,
            )

        try:
            raw_value = provider.retrieve(query, context)
            if context.cancelled():
                raise EvidenceProviderCancelled(
                    "Provider call was cancelled before its result could be accepted."
                )
            if context.remaining_seconds() <= 0:
                raise EvidenceProviderTimeout(
                    "Provider deadline expired before its result could be accepted."
                )
            raw = EvidenceProviderRawResult.model_validate(raw_value)
            if not resilience_metadata_trusted:
                # Cache/circuit/attempt telemetry is owned by the local
                # resilience boundary, never by an untrusted adapter payload.
                raw = raw.model_copy(
                    update={
                        "attempts": 1,
                        "attempt_outcomes": [raw.transport_outcome],
                        "cache_state": ProviderCacheState.BYPASS,
                        "cache_schema_version": "",
                        "cache_entry_age_seconds": None,
                        "circuit_state_before": ProviderCircuitState.CLOSED,
                        "circuit_state_after": ProviderCircuitState.CLOSED,
                        "source_snapshot_retrieved_at": (
                            raw.source_snapshot_retrieved_at
                            or raw.completed_at
                            or _utc_now()
                        ),
                        "cache_served_at": "",
                    }
                )
        except ValidationError:
            return self._failure(
                descriptor=descriptor,
                query=query,
                context=context,
                base_bundle=base_bundle,
                provider_call_id=fallback_call_id,
                status=EvidenceProviderStatus.INVALID_RESPONSE,
                error_code="INVALID_RESPONSE",
                message="Provider returned a malformed response.",
                started_at=started_at,
                started_clock=started_clock,
                attempts=1,
            )
        except EvidenceProviderException as exc:
            return self._failure(
                descriptor=descriptor,
                query=query,
                context=context,
                base_bundle=base_bundle,
                provider_call_id=fallback_call_id,
                status=exc.status,
                error_code=exc.redacted_error_code,
                message=exc.redacted_message,
                started_at=started_at,
                started_clock=started_clock,
                retryable=exc.retryable,
                attempts=1,
            )
        except TimeoutError:
            return self._failure(
                descriptor=descriptor,
                query=query,
                context=context,
                base_bundle=base_bundle,
                provider_call_id=fallback_call_id,
                status=EvidenceProviderStatus.TIMEOUT,
                error_code="TIMEOUT",
                message="Provider call reached its deadline.",
                started_at=started_at,
                started_clock=started_clock,
                retryable=True,
                attempts=1,
            )
        except PermissionError:
            return self._failure(
                descriptor=descriptor,
                query=query,
                context=context,
                base_bundle=base_bundle,
                provider_call_id=fallback_call_id,
                status=EvidenceProviderStatus.AUTH_ERROR,
                error_code="AUTH_ERROR",
                message="Provider authorization failed.",
                started_at=started_at,
                started_clock=started_clock,
                attempts=1,
            )
        except Exception:
            # Never serialize or log the raw exception: transport exceptions can
            # contain request headers, URLs, or upstream response bodies.
            return self._failure(
                descriptor=descriptor,
                query=query,
                context=context,
                base_bundle=base_bundle,
                provider_call_id=fallback_call_id,
                status=EvidenceProviderStatus.PROVIDER_ERROR,
                error_code="PROVIDER_ERROR",
                message="Provider execution failed.",
                started_at=started_at,
                started_clock=started_clock,
                attempts=1,
            )

        mismatch = self._contract_mismatch(raw, descriptor, query, context)
        if mismatch:
            return self._failure(
                descriptor=descriptor,
                query=query,
                context=context,
                base_bundle=base_bundle,
                provider_call_id=raw.provider_call_id,
                status=EvidenceProviderStatus.INVALID_RESPONSE,
                error_code=mismatch,
                message="Provider response did not match the execution contract.",
                started_at=raw.started_at or started_at,
                started_clock=started_clock,
                attempts=raw.attempts,
                attempt_outcomes=raw.attempt_outcomes,
            )

        active_filters = set(active_query_filters(query))
        unreported_filters = (
            active_filters - set(raw.applied_filters) - set(raw.unsupported_filters)
        )
        if unreported_filters:
            raw = raw.model_copy(
                update={
                    "unsupported_filters": sorted(
                        set(raw.unsupported_filters) | unreported_filters
                    )
                }
            )

        records: dict[str, EvidenceRecord] = {}
        provenance: list[RetrievalProvenance] = []
        dispositions: list[ProviderHitDisposition] = []
        evidence_by_hit_reference: dict[str, set[str]] = {}
        rejected = 0
        limit = min(query.max_results, descriptor.maximum_results)
        retrieved_at = (
            raw.source_snapshot_retrieved_at or raw.completed_at or _utc_now()
        )

        def record_rejection(hit: StrictProviderHit, reason_code: str) -> None:
            nonlocal rejected
            # Target-derived hit counts, types, hashes, and reason codes are
            # supervisory signals.  Do not persist them for blinded evaluation.
            if context.benchmark_split in _BLINDED_BENCHMARK_SPLITS:
                return
            rejected += 1
            dispositions.append(
                self._hit_disposition(
                    raw=raw,
                    query=query,
                    context=context,
                    hit=hit,
                    accepted=False,
                    reason_code=reason_code,
                )
            )

        for hit in raw.raw_hits:
            if len(records) >= limit:
                record_rejection(hit, "RESULT_LIMIT_EXCEEDED")
                continue
            if hit.source_type not in descriptor.supported_source_types:
                record_rejection(hit, "UNSUPPORTED_SOURCE_TYPE")
                continue
            try:
                record = self._normalizer.normalize(hit, query, context)
            except ProviderHitRejected as exc:
                record_rejection(hit, str(exc))
                continue
            except (ValidationError, ValueError):
                record_rejection(hit, "NORMALIZATION_VALIDATION_FAILED")
                continue
            record = record.model_copy(update={"retrieved_at": retrieved_at})
            prior = records.get(record.evidence_id)
            if prior is not None and _evidence_source_projection(
                prior
            ) != _evidence_source_projection(record):
                return self._failure(
                    descriptor=descriptor,
                    query=query,
                    context=context,
                    base_bundle=base_bundle,
                    provider_call_id=raw.provider_call_id,
                    status=EvidenceProviderStatus.INVALID_RESPONSE,
                    error_code="CONFLICTING_EVIDENCE_ID",
                    message=(
                        "Provider returned conflicting records for one evidence identity."
                    ),
                    started_at=raw.started_at or started_at,
                    started_clock=started_clock,
                    attempts=raw.attempts,
                    attempt_outcomes=raw.attempt_outcomes,
                )
            records.setdefault(record.evidence_id, record)
            evidence_by_hit_reference.setdefault(hit.raw_provider_reference, set()).add(
                record.evidence_id
            )
            dispositions.append(
                self._hit_disposition(
                    raw=raw,
                    query=query,
                    context=context,
                    hit=hit,
                    accepted=True,
                    reason_code="ACCEPTED",
                    evidence_id=record.evidence_id,
                )
            )
            provenance.append(
                RetrievalProvenance(
                    evidence_id=record.evidence_id,
                    provider=raw.provider,
                    provider_contract_version=raw.provider_contract_version,
                    provider_call_id=raw.provider_call_id,
                    query_id=query.query_id,
                    correlation_id=context.correlation_id,
                    retrieved_at=retrieved_at,
                    raw_provider_reference=hit.raw_provider_reference,
                    applicability=ApplicabilityState.APPLICABLE,
                    rank=hit.rank,
                    retrieval_score=hit.retrieval_score,
                    retrieval_method="provider",
                    cache_state=raw.cache_state,
                    cache_served_at=raw.cache_served_at,
                )
            )

        unique_provenance = {row.provenance_id: row for row in provenance}
        provenance = sorted(
            unique_provenance.values(), key=lambda row: row.provenance_id
        )
        accepted_ids = sorted(records)
        status, partial_reason = self._status(raw, accepted_ids)
        incomplete_without_hits = bool(
            status == EvidenceProviderStatus.PROVIDER_ERROR
            and raw.transport_outcome == ProviderTransportOutcome.COMPLETED
            and not accepted_ids
            and (raw.truncated or raw.unsupported_filters)
        )
        redacted_error_code = raw.redacted_error_code
        redacted_message = raw.redacted_message
        if incomplete_without_hits:
            redacted_error_code = redacted_error_code or "INCOMPLETE_RESULT"
            redacted_message = redacted_message or (
                "Provider returned no usable evidence and the result was incomplete."
            )
        completed_at = raw.completed_at or _utc_now()
        duration_ms = raw.duration_ms or max(
            0, round((monotonic() - started_clock) * 1000)
        )
        existing_records = (
            {record.evidence_id: record for record in base_bundle.records}
            if base_bundle is not None
            else {}
        )
        if any(
            record.evidence_id in existing_records
            and _evidence_source_projection(existing_records[record.evidence_id])
            != _evidence_source_projection(record)
            for record in records.values()
        ):
            return self._failure(
                descriptor=descriptor,
                query=query,
                context=context,
                base_bundle=base_bundle,
                provider_call_id=raw.provider_call_id,
                status=EvidenceProviderStatus.INVALID_RESPONSE,
                error_code="CONFLICTING_EVIDENCE_ID",
                message="Provider evidence conflicts with an existing evidence identity.",
                started_at=raw.started_at or started_at,
                started_clock=started_clock,
                attempts=raw.attempts,
                attempt_outcomes=raw.attempt_outcomes,
            )
        call_result = EvidenceProviderCallResult(
            provider=raw.provider,
            provider_contract_version=raw.provider_contract_version,
            provider_call_id=raw.provider_call_id,
            raw_provider_reference=raw.raw_provider_reference,
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            status=status,
            transport_outcome=raw.transport_outcome,
            accepted_evidence_ids=accepted_ids,
            accepted_evidence_count=len(accepted_ids),
            rejected_hit_count=rejected,
            applied_filters=raw.applied_filters,
            unsupported_filters=raw.unsupported_filters,
            attempts=raw.attempts,
            attempt_outcomes=raw.attempt_outcomes,
            started_at=raw.started_at or started_at,
            completed_at=completed_at,
            source_snapshot_retrieved_at=retrieved_at,
            cache_served_at=raw.cache_served_at,
            duration_ms=duration_ms,
            truncated=raw.truncated,
            cache_state=raw.cache_state,
            cache_schema_version=raw.cache_schema_version,
            cache_entry_age_seconds=raw.cache_entry_age_seconds,
            circuit_state_before=raw.circuit_state_before,
            circuit_state_after=raw.circuit_state_after,
            retryable=raw.retryable,
            redacted_error_code=redacted_error_code,
            redacted_message=redacted_message,
            redacted_required_action=raw.redacted_required_action,
            partial_reason=partial_reason,
        )
        bundle = self._bundle(
            context=context,
            new_records=records.values(),
            base_bundle=base_bundle,
        )
        syntheses: list[DiscoverySynthesis] = []
        if (
            raw.transport_outcome == ProviderTransportOutcome.COMPLETED
            and context.benchmark_split not in _BLINDED_BENCHMARK_SPLITS
        ):
            for synthesis in raw.discovery_syntheses:
                # Canonical IDs do not exist at the adapter boundary. Link a
                # same-call synthesis only after strict hits survive central
                # visibility, source-type, temporal, and authority policy.
                payload = synthesis.model_dump(
                    mode="json",
                    exclude={"synthesis_id"},
                )
                linked_references = raw.discovery_synthesis_hit_references.get(
                    synthesis.synthesis_id,
                    [],
                )
                payload["derived_from"] = sorted(
                    {
                        evidence_id
                        for reference in linked_references
                        for evidence_id in evidence_by_hit_reference.get(
                            reference, set()
                        )
                    }
                )
                syntheses.append(DiscoverySynthesis.model_validate(payload))
            syntheses = sorted(
                {row.synthesis_id: row for row in syntheses}.values(),
                key=lambda row: row.synthesis_id,
            )
        return ProviderExecutionResult(
            call_result=call_result,
            evidence_bundle=bundle,
            provenance=provenance,
            hit_dispositions=dispositions,
            discovery_syntheses=syntheses,
            trace_sidecar=self._trace_sidecar(
                query=query,
                context=context,
                call_result=call_result,
                provenance=provenance,
                dispositions=dispositions,
                syntheses=syntheses,
            ),
        )

    @staticmethod
    def _hit_disposition(
        *,
        raw: EvidenceProviderRawResult,
        query: EvidenceQueryV1,
        context: EvidenceProviderExecutionContext,
        hit: StrictProviderHit,
        accepted: bool,
        reason_code: str,
        evidence_id: str = "",
    ) -> ProviderHitDisposition:
        safe_reason = re.sub(
            r"[^A-Z0-9_]+",
            "_",
            str(reason_code or "NORMALIZATION_REJECTED").strip().upper(),
        ).strip("_")[:100]
        if not safe_reason:
            safe_reason = "NORMALIZATION_REJECTED"
        blind_rejection = (
            context.benchmark_split in _BLINDED_BENCHMARK_SPLITS and not accepted
        )
        return ProviderHitDisposition(
            provider=raw.provider,
            provider_contract_version=raw.provider_contract_version,
            provider_call_id=raw.provider_call_id,
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            source_type=hit.source_type,
            source_reference_sha256=stable_sha256(
                {
                    "source_reference": hit.source_reference,
                    "source_locator": hit.source_locator,
                    "source_native_id": hit.source_native_id,
                }
            ),
            content_sha256=provider_hit_content_sha256(hit),
            provider_hit_sha256=stable_sha256(
                hit.model_dump(mode="json", exclude_none=True)
            ),
            raw_provider_reference=(
                "" if blind_rejection else hit.raw_provider_reference
            ),
            evidence_id=evidence_id,
            accepted=accepted,
            applicability=(
                ApplicabilityState.APPLICABLE
                if accepted
                else ApplicabilityState.NOT_APPLICABLE
            ),
            reason_code=safe_reason,
        )

    @staticmethod
    def _trace_sidecar(
        *,
        query: EvidenceQueryV1,
        context: EvidenceProviderExecutionContext,
        call_result: EvidenceProviderCallResult,
        provenance: Iterable[RetrievalProvenance] = (),
        dispositions: Iterable[ProviderHitDisposition] = (),
        syntheses: Iterable[DiscoverySynthesis] = (),
    ) -> EvidenceProviderTraceSidecar:
        provenance_rows = list(provenance)
        disposition_rows = list(dispositions)
        synthesis_rows = list(syntheses)
        return EvidenceProviderTraceSidecar(
            provider=call_result.provider,
            run_id=context.run_id,
            request_id=context.request_id,
            question_id=query.question_id,
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            provider_call_id=call_result.provider_call_id,
            provider_result_id=call_result.provider_result_id,
            evidence_ids=call_result.accepted_evidence_ids,
            provenance_ids=[row.provenance_id for row in provenance_rows],
            disposition_ids=[row.disposition_id for row in disposition_rows],
            synthesis_ids=[row.synthesis_id for row in synthesis_rows],
        )

    @staticmethod
    def _context_preflight_error(
        *,
        query: EvidenceQueryV1,
        context: EvidenceProviderExecutionContext,
        base_bundle: CanonicalEvidenceBundle | None,
    ) -> tuple[str, str] | None:
        tenant_id = context.principal.tenant_id
        if base_bundle is not None and base_bundle.tenant_id != tenant_id:
            return (
                "CROSS_TENANT_CONTEXT",
                "Provider context cannot use an evidence bundle from another tenant.",
            )
        if context.benchmark_split in _BLINDED_BENCHMARK_SPLITS:
            has_target_jira = _JIRA_KEY_RE.search(query.jira_reference) is not None
            has_sealed_content = bool(query.excluded_sources.content_sha256)
            if not has_target_jira or not has_sealed_content:
                return (
                    "BLIND_EXCLUSION_CONTEXT_REQUIRED",
                    "Blinded provider execution requires sealed target exclusions.",
                )
        if not query.context_evidence_ids:
            return None
        if base_bundle is None:
            return (
                "CONTEXT_EVIDENCE_UNAVAILABLE",
                "Provider context evidence is unavailable to this execution.",
            )
        records = {record.evidence_id: record for record in base_bundle.records}
        context_records = [records.get(item) for item in query.context_evidence_ids]
        if any(record is None for record in context_records):
            return (
                "CONTEXT_EVIDENCE_UNAVAILABLE",
                "Provider context evidence is unavailable to this execution.",
            )
        if any(
            record is None
            or record.tenant_id != tenant_id
            or not record_visible_to(record, context.principal)
            for record in context_records
        ):
            return (
                "CONTEXT_EVIDENCE_NOT_VISIBLE",
                "Provider context evidence is not visible to this execution.",
            )
        return None

    @staticmethod
    def _call_id(provider: str, query_id: str, correlation_id: str) -> str:
        return f"provider-call:{stable_sha256({'provider': provider, 'query_id': query_id, 'correlation_id': correlation_id})[:32]}"

    @staticmethod
    def _contract_mismatch(
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
            or synthesis.provider_contract_version != raw.provider_contract_version
            or synthesis.provider_call_id != raw.provider_call_id
            or synthesis.query_id != raw.query_id
            or synthesis.correlation_id != raw.correlation_id
            for synthesis in raw.discovery_syntheses
        ):
            return "DISCOVERY_SYNTHESIS_MISMATCH"
        return ""

    @staticmethod
    def _status(
        raw: EvidenceProviderRawResult, accepted_ids: list[str]
    ) -> tuple[EvidenceProviderStatus, str]:
        if raw.transport_outcome != ProviderTransportOutcome.COMPLETED:
            if accepted_ids:
                reason = raw.redacted_message or (
                    f"Provider completed only partially ({raw.transport_outcome.value})."
                )
                return EvidenceProviderStatus.PARTIAL, _safe_diagnostic(reason)
            return _TRANSPORT_STATUS[raw.transport_outcome], ""
        if not accepted_ids and (raw.truncated or raw.unsupported_filters):
            return EvidenceProviderStatus.PROVIDER_ERROR, ""
        if not accepted_ids:
            return EvidenceProviderStatus.EMPTY, ""
        if raw.truncated or raw.unsupported_filters:
            reason = raw.redacted_message or (
                "Provider result was truncated or could not apply every requested filter."
            )
            return EvidenceProviderStatus.PARTIAL, _safe_diagnostic(reason)
        return EvidenceProviderStatus.SUCCESS, ""

    @staticmethod
    def _bundle(
        *,
        context: EvidenceProviderExecutionContext,
        new_records: Iterable[EvidenceRecord],
        base_bundle: CanonicalEvidenceBundle | None,
    ) -> CanonicalEvidenceBundle:
        tenant_id = context.principal.tenant_id
        if base_bundle is not None and base_bundle.tenant_id != tenant_id:
            raise ValueError("cannot augment a canonical bundle across tenants")
        existing = {
            record.evidence_id: record
            for record in (base_bundle.records if base_bundle is not None else [])
        }
        for record in new_records:
            prior = existing.get(record.evidence_id)
            if prior is None:
                existing[record.evidence_id] = record
                continue
            if _evidence_source_projection(prior) != _evidence_source_projection(
                record
            ):
                raise ValueError("one evidence identity has conflicting source facts")
            existing[record.evidence_id] = prior.model_copy(
                update={
                    "retrieved_by_query": sorted(
                        set(prior.retrieved_by_query) | set(record.retrieved_by_query)
                    )
                }
            )
        return build_bundle(
            existing.values(),
            tenant_id=tenant_id,
            issue_facts=base_bundle.issue_facts if base_bundle is not None else {},
            unavailable_sources=(
                base_bundle.unavailable_sources if base_bundle is not None else []
            ),
        )

    def _failure(
        self,
        *,
        descriptor: EvidenceProviderDescriptor,
        query: EvidenceQueryV1,
        context: EvidenceProviderExecutionContext,
        base_bundle: CanonicalEvidenceBundle | None,
        provider_call_id: str,
        status: EvidenceProviderStatus,
        error_code: str,
        message: str,
        started_at: str,
        started_clock: float,
        retryable: bool = False,
        attempts: int = 0,
        attempt_outcomes: list[ProviderTransportOutcome] | None = None,
    ) -> ProviderExecutionResult:
        completed_at = _utc_now()
        resolved_attempt_outcomes = list(attempt_outcomes or [])
        if len(resolved_attempt_outcomes) != attempts:
            fallback_outcome = _STATUS_TRANSPORT.get(status)
            resolved_attempt_outcomes = (
                [fallback_outcome] * attempts if fallback_outcome is not None else []
            )
        result = EvidenceProviderCallResult(
            provider=descriptor.provider,
            provider_contract_version=descriptor.provider_contract_version,
            provider_call_id=provider_call_id,
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            status=status,
            transport_outcome=_STATUS_TRANSPORT.get(
                status,
                ProviderTransportOutcome.COMPLETED,
            ),
            accepted_evidence_count=0,
            attempts=attempts,
            attempt_outcomes=resolved_attempt_outcomes,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=max(0, round((monotonic() - started_clock) * 1000)),
            retryable=retryable,
            redacted_error_code=error_code,
            redacted_message=message,
        )
        return ProviderExecutionResult(
            call_result=result,
            evidence_bundle=self._bundle(
                context=context, new_records=[], base_bundle=base_bundle
            ),
            trace_sidecar=self._trace_sidecar(
                query=query,
                context=context,
                call_result=result,
            ),
        )


class EvidenceProviderRegistry:
    """Deterministic, centrally disable-able provider registry.

    The default is disabled.  When disabled, selection does not inspect provider
    descriptors and therefore cannot trigger discovery, authentication, or I/O.
    """

    def __init__(
        self,
        providers: Iterable[EvidenceProvider] = (),
        *,
        enabled: bool = False,
    ) -> None:
        self._enabled = bool(enabled)
        self._providers: dict[str, EvidenceProvider] = {}
        if self._enabled:
            for provider in providers:
                self.register(provider)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def register(self, provider: EvidenceProvider) -> None:
        descriptor = provider.descriptor()
        if descriptor.provider in self._providers:
            raise ValueError(f"provider already registered: {descriptor.provider}")
        self._providers[descriptor.provider] = provider

    def eligible(
        self,
        query: EvidenceQueryV1,
        *,
        allow_discovery_only: bool = False,
    ) -> list[EvidenceProvider]:
        if not self._enabled:
            return []
        eligible: list[tuple[str, EvidenceProvider]] = []
        requested = set(query.requested_evidence_types)
        for name, provider in self._providers.items():
            descriptor = provider.descriptor()
            if (
                descriptor.supported_domains
                and query.domain not in descriptor.supported_domains
            ):
                continue
            supported = set(descriptor.supported_source_types)
            if (
                requested
                and not requested.intersection(supported)
                and not (
                    allow_discovery_only
                    and descriptor.supports_discovery_synthesis
                )
            ):
                continue
            eligible.append((name, provider))
        return [provider for _name, provider in sorted(eligible)]


class FakeEvidenceProvider:
    """Deterministic fake used by contract tests; it performs no external I/O."""

    def __init__(
        self,
        descriptor: EvidenceProviderDescriptor,
        *,
        result: EvidenceProviderRawResult | None = None,
        result_factory: Callable[
            [EvidenceQueryV1, EvidenceProviderExecutionContext],
            EvidenceProviderRawResult,
        ]
        | None = None,
        error: Exception | None = None,
        provider_contract_version: str = "fake-v1",
    ) -> None:
        if result is not None and result_factory is not None:
            raise ValueError("provide result or result_factory, not both")
        self._descriptor = descriptor
        self._result = result
        self._result_factory = result_factory
        self._error = error
        self._provider_contract_version = provider_contract_version
        self.calls: list[tuple[str, str]] = []

    def descriptor(self) -> EvidenceProviderDescriptor:
        return self._descriptor

    def retrieve(
        self, query: EvidenceQueryV1, context: EvidenceProviderExecutionContext
    ) -> EvidenceProviderRawResult:
        self.calls.append((query.query_id, context.correlation_id))
        if self._error is not None:
            raise self._error
        if self._result_factory is not None:
            return self._result_factory(query, context)
        if self._result is not None:
            return self._result.model_copy(deep=True)
        call_id = EvidenceProviderExecutor._call_id(
            self._descriptor.provider, query.query_id, context.correlation_id
        )
        return EvidenceProviderRawResult(
            provider=self._descriptor.provider,
            provider_contract_version=self._provider_contract_version,
            provider_call_id=call_id,
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            transport_outcome=ProviderTransportOutcome.COMPLETED,
        )


__all__ = [
    "AuthorizedSemanticEvidence",
    "AuthorityRequirement",
    "CacheState",
    "DiscoverySynthesis",
    "EvidenceProvider",
    "EvidenceProviderAuthError",
    "EvidenceProviderCallResult",
    "EvidenceProviderCancelled",
    "EvidenceProviderDescriptor",
    "EvidenceProviderException",
    "EvidenceProviderExecutionContext",
    "EvidenceProviderExecutor",
    "EvidenceProviderInvalidResponse",
    "EvidenceProviderRateLimited",
    "EvidenceProviderRawResult",
    "EvidenceProviderRegistry",
    "EvidenceProviderStatus",
    "EvidenceProviderTraceSidecar",
    "EvidenceProviderTimeout",
    "EvidenceQueryV1",
    "ExcludedSources",
    "FakeEvidenceProvider",
    "ProviderCacheState",
    "ProviderCircuitState",
    "ProviderExecutionResult",
    "ProviderHitDisposition",
    "ProviderHitRejected",
    "ProviderTransportOutcome",
    "QueryMateriality",
    "QUESTION_EVIDENCE_ASSESSMENTS_METADATA_KEY",
    "QUESTION_EVIDENCE_ASSESSMENT_SCHEMA",
    "QuestionEvidenceAssessment",
    "QuestionEvidenceStance",
    "RetrievalProvenance",
    "SEMANTIC_EVIDENCE_AUTHORIZATION_SCHEMA",
    "SOURCE_ATTESTATION_SCHEMA",
    "SemanticEvidenceAuthorization",
    "SemanticEvidenceBinding",
    "SourceNativeEvidenceAttestation",
    "StrictProviderHit",
    "StrictProviderHitNormalizer",
    "TemporalBoundary",
    "active_query_filters",
    "normalize_provider_hit",
    "provider_hit_content_sha256",
]
