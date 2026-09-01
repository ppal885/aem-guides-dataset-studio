"""Allowlisted, question-scoped observability for canonical evidence retrieval.

This module projects canonical stage objects and the private FluffyJaws sidecar
into a content-minimal diagnostic view.  It deliberately does not retain Jira
text, evidence content, source locators, tenant/principal data, provider bodies,
or arbitrary error messages.
"""

from __future__ import annotations

import re
from collections import Counter
from contextvars import ContextVar
from enum import StrEnum
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.schemas_canonical_test_plan_runtime import (
    CANONICAL_RUNTIME_ID,
    CANONICAL_RUNTIME_VERSION,
    AcceptanceCandidate,
    AcceptancePromotionDecision,
    AuthorityClass,
    AuthoritySubject,
    BehaviorHypothesis,
    CanonicalRuntimeStage,
    CoverageDisposition,
    CoverageDispositionRecord,
    CurrentnessState,
    DirectedRetrievalRecord,
    EvidenceRecord,
    EvidenceSourceType,
    GenerationRequest,
    GitHubImplementationVerificationHandoff,
    GitHubImplementationVerificationResult,
    GitHubImplementationVerificationStatus,
    HypothesisState,
    MissingQuestion,
    PromotionStatus,
    RetrievalStatus,
    SemanticDimension,
    StructuredQEPlan,
    VerificationState,
    stable_sha256,
)
from app.services.canonical_evidence_service import record_visible_to
from app.services.fluffyjaws_routing_policy import (
    FluffyJawsNoCallReason,
    FluffyJawsRoutingRecord,
    FluffyJawsRoutingSignal,
)
from app.services.reasoning_evidence_provider import (
    EvidenceProviderStatus,
    ProviderCacheState,
    ProviderCircuitState,
    ProviderTransportOutcome,
    QuestionEvidenceStance,
    QueryMateriality,
)
from app.services.reasoning_evidence_shadow_service import (
    FluffyJawsRuntimeMode,
    FluffyJawsShadowCallTrace,
    FluffyJawsShadowRunTrace,
)


QUESTION_RETRIEVAL_TRACE_SCHEMA = "aem-guides-question-retrieval-trace-v1"
_QUESTION_ID_PATTERN = r"^question:[a-f0-9]{32}$"
_RUN_ID_PATTERN = (
    r"^run:[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$"
)
_REQUEST_ID_PATTERN = r"^req:[a-f0-9]{64}$"
_EVIDENCE_ID_PATTERN = r"^ev:[A-Z0-9_]+:[a-f0-9]{32}$"
_RETRIEVAL_ID_PATTERN = r"^retrieval:[a-f0-9]{32}$"
_QUERY_ID_PATTERN = r"^query:[a-f0-9]{32}$"
_PROVIDER_CALL_ID_PATTERN = r"^provider-call:[a-f0-9]{32}$"
_PROVIDER_RESULT_ID_PATTERN = r"^provider-result:[a-f0-9]{32}$"
_PROVENANCE_ID_PATTERN = r"^provenance:[a-f0-9]{32}$"
_HYPOTHESIS_ID_PATTERN = r"^hypothesis:[a-f0-9]{32}$"
_CANDIDATE_ID_PATTERN = r"^candidate:[a-f0-9]{32}$"
_DISPOSITION_ID_PATTERN = r"^disposition:[a-f0-9]{32}$"
_FACT_ID_PATTERN = r"^fact:[a-f0-9]{32}$"
_CLOSURE_ID_PATTERN = r"^closure:[a-f0-9]{32}$"
_DISCOVERY_ID_PATTERN = r"^discovery:[a-f0-9]{32}$"
_GITHUB_HANDOFF_ID_PATTERN = r"^github-handoff:[a-f0-9]{32}$"
_GITHUB_RESULT_ID_PATTERN = r"^github-result:[a-f0-9]{32}$"
_IMPLEMENTATION_TRACE_ID_PATTERN = r"^implementation-trace:[a-f0-9]{32}$"
_SAFE_RECORD_ID_RE = re.compile(
    "(?:"
    + "|".join(
        pattern.removeprefix("^").removesuffix("$")
        for pattern in (
            _QUESTION_ID_PATTERN,
            _EVIDENCE_ID_PATTERN,
            _RETRIEVAL_ID_PATTERN,
            _QUERY_ID_PATTERN,
            _PROVIDER_CALL_ID_PATTERN,
            _PROVIDER_RESULT_ID_PATTERN,
            _PROVENANCE_ID_PATTERN,
            _HYPOTHESIS_ID_PATTERN,
            _CANDIDATE_ID_PATTERN,
            _DISPOSITION_ID_PATTERN,
            _FACT_ID_PATTERN,
            _CLOSURE_ID_PATTERN,
            _DISCOVERY_ID_PATTERN,
            _GITHUB_HANDOFF_ID_PATTERN,
            _GITHUB_RESULT_ID_PATTERN,
            _IMPLEMENTATION_TRACE_ID_PATTERN,
        )
    )
    + ")"
)
_MAX_IDS_PER_FIELD = 2_000
_SAFE_PROVIDER_ERROR_CODES = frozenset(
    {
        "AUTH_ERROR",
        "BLIND_EXCLUSION_CONTEXT_REQUIRED",
        "CANCELLED",
        "CIRCUIT_OPEN",
        "CONFLICTING_EVIDENCE_ID",
        "CONTEXT_EVIDENCE_NOT_VISIBLE",
        "CONTEXT_EVIDENCE_UNAVAILABLE",
        "CONTINUATION_UNAVAILABLE",
        "CORRELATION_ID_MISMATCH",
        "CROSS_TENANT_CONTEXT",
        "FILTER_CLAIM_CONFLICT",
        "INCOMPLETE_RESULT",
        "INVALID_RESPONSE",
        "ITERATION_LIMIT_REACHED",
        "PROVIDER_ERROR",
        "RATE_LIMITED",
        "RESPONSE_TOO_LARGE",
        "STREAM_INTERRUPTED",
        "TEMPORARY_PROVIDER_FAILURE",
        "TIMEOUT",
        "UNSUPPORTED_APPLIED_FILTER",
        "UNSUPPORTED_SOURCE_TYPE",
        "UPSTREAM_ERROR",
    }
)
_TRACE_REASON_CODES = frozenset(
    {
        "BLOCKING_PRODUCT_DECISION_GAP",
        "CANDIDATE_PROMOTION_RESULT_NOT_RETAINED",
        "CANDIDATE_PROMOTION_RESULT_RECORDED",
        "DISCOVERY_SYNTHESIS_HAS_NO_UNDERLYING_SOURCE",
        "DISCOVERY_SYNTHESIS_NOT_CANONICAL_EVIDENCE",
        "FINAL_PLAN_NOT_AVAILABLE",
        "FLUFFYJAWS_MODE_DISABLED",
        "FLUFFYJAWS_NOT_CALLED",
        "FLUFFYJAWS_RETURNED_NO_SOURCE",
        "FLUFFYJAWS_TRACE_UNAVAILABLE",
        "HYPOTHESIS_DERIVED_FROM_QUESTION_ID",
        "HYPOTHESIS_COVERAGE_DISPOSITION_RECORDED",
        "HYPOTHESIS_STATE_IS_NOT_COVERAGE_DISPOSITION",
        "HYPOTHESIS_TO_COVERAGE_DISPOSITION_ID_RETAINED",
        "HYPOTHESIS_TO_COVERAGE_DISPOSITION_ID_NOT_RETAINED",
        "IMPLEMENTATION_HANDOFF_NOT_CREATED",
        "IMPLEMENTATION_VERIFICATION_NOT_APPLICABLE",
        "IMPLEMENTATION_VERIFICATION_PENDING_OR_UNRESOLVED",
        "IMPLEMENTATION_VERIFICATION_TERMINAL",
        "LOCAL_EVIDENCE_CANONICALIZED",
        "LOCAL_RESULTS_EMPTY",
        "LOCAL_RESULTS_MATCHED",
        "LOCAL_RESULTS_REJECTED",
        "LOCAL_RESULTS_UNAVAILABLE",
        "LOCAL_RETRIEVAL_RECORD_RETAINED",
        "LOCAL_RETRIEVAL_RECORD_UNAVAILABLE",
        "LOGICAL_PROVIDER_CALL_RECORDED",
        "MISSING_QUESTION_GENERATOR_OUTPUT",
        "NO_ACCEPTED_UNDERLYING_SOURCE",
        "NO_HYPOTHESIS_CREATED",
        "NO_HYPOTHESIS_OR_CANDIDATE_DISPOSITION",
        "NO_HYPOTHESIS_RECORDED",
        "NO_PROVIDER_EVIDENCE_NORMALIZED",
        "PROVIDER_CALL_RESULT_NOT_RECORDED",
        "PROVIDER_EVIDENCE_NORMALIZED",
        "PROVIDER_RESULT_WITHOUT_TRANSPORT_ATTEMPT",
        "PROVIDER_RESULTS_RECORDED",
        "PROVIDER_RETURNED_NO_ACCEPTED_RESULTS",
        "PROVIDER_STATUS_RECORDED",
        "PROVIDER_TRANSPORT_ATTEMPTED",
        "QUESTION_GENERATION_REASON_NOT_RETAINED",
        "QUESTION_SOURCE_RECORD_IDS_RETAINED",
        "QUESTION_LINKED_CANDIDATE_SECTION_LOCATION_RECORDED",
        "QUESTION_LINKED_DISPOSITION_SECTION_LOCATION_RECORDED",
        "QUESTION_NOT_LINKED_TO_FINAL_PLAN_SECTION",
        "QUESTION_SECTION_LOCATION_RECORDED",
        "QUESTION_SOURCE_RECORD_IDS_NOT_RETAINED",
        "ROUTING_RECORD_UNAVAILABLE",
        "SECOND_PASS_NOT_CALLED",
        "SHADOW_CALL_NOT_RECORDED",
        "SHADOW_LOGICAL_CALL_RECORDED",
        "SHADOW_OBSERVATION_MODE",
        "UNDERLYING_SOURCE_IDENTITIES_PARTIAL",
        "UNDERLYING_SOURCE_IDENTITIES_REDACTED",
        "UNDERLYING_SOURCE_IDENTITY_ABSENT",
        "UNRECOGNIZED_PROVIDER_SKIP_REASON",
        "UNRESOLVED_SEMANTIC_DIMENSION",
        "UNSAFE_PROVIDER_ERROR_CODE_REDACTED",
        "VERIFIER_CITED_EVIDENCE",
        "VERIFIER_CITED_NO_EVIDENCE",
        "VERIFIER_EVIDENCE_LINKAGE_INCOMPLETE",
        "QUESTION_UNRESOLVED_DECISION_TO_CANDIDATE",
    }
    | {value.value for value in FluffyJawsRoutingSignal}
    | {value.value for value in FluffyJawsNoCallReason}
    | _SAFE_PROVIDER_ERROR_CODES
)
_TRACE_WARNING_CODES = frozenset({"FLUFFYJAWS_TRACE_IDENTITY_MISMATCH"})
_PLAN_SECTION_KEYS = frozenset(
    {
        "acceptance_contract",
        "configuration_state_coverage",
        "coverage_gate_result",
        "cross_mode_regression",
        "evidence_gaps",
        "explicit_out_of_scope",
        "failure_recovery_coverage",
        "generated_output_validation",
        "investigated_and_rejected",
        "issue_understanding",
        "lifecycle_coverage",
        "negative_boundary_coverage",
        "nfr_coverage",
        "product_decisions",
        "product_scope",
        "reference_link_integrity",
        "referenced_content_coverage",
        "semantic_coverage",
        "structural_hierarchy_coverage",
        "transformation_processing_coverage",
        "technical_notes",
        "known_limitations",
    }
)
_SEMANTIC_REJECTION_CODES = frozenset(
    {
        "ACCEPTED_DISPOSITION_REQUIRED",
        "ASSESSED_RECORD_INVALID",
        "CURRENT_SOURCE_ATTESTATION_REQUIRED",
        "DISPOSITION_LINKAGE_MISMATCH",
        "DISPOSITION_SOURCE_BINDING_MISMATCH",
        "ENVIRONMENT_SCOPE_REQUIRED",
        "FRESH_CACHE_SOURCE_ATTESTATION_REQUIRED",
        "LIVE_ENVIRONMENT_ATTESTATION_REQUIRED",
        "PINNED_REVISION_ATTESTATION_REQUIRED",
        "PROVENANCE_NOT_APPLICABLE",
        "PROVENANCE_REQUIRED",
        "PROVIDER_RESULT_NOT_USABLE",
        "QUERY_LINEAGE_MISMATCH",
        "QUESTION_ASSESSMENT_AMBIGUOUS",
        "QUESTION_ASSESSMENT_EXPIRED",
        "QUESTION_ASSESSMENT_IRRELEVANT",
        "QUESTION_ASSESSMENT_NOT_YET_VALID",
        "QUESTION_LINKAGE_MISMATCH",
        "ROUTING_NOT_PERMITTED",
        "SEMANTIC_AUTHORIZATION_BINDING_MISMATCH",
        "SEMANTIC_AUTHORIZATION_INVALID",
        "SEMANTIC_AUTHORIZATION_REQUIRED",
        "SEMANTIC_SOURCE_POLICY_REJECTED",
        "SOURCE_ATTESTATION_EXPIRED",
        "SOURCE_ATTESTATION_NOT_YET_VALID",
        "SOURCE_NOT_VISIBLE_TO_PRINCIPAL",
    }
)
_HIT_DISPOSITION_CODES = frozenset(
    {
        "ACCEPTED",
        "AUTHORITY_CLASS_NOT_ACCEPTABLE",
        "AUTHORITY_SUBJECT_MISMATCH",
        "BLIND_SOURCE_NOT_VERIFIED",
        "BLIND_SOURCE_TYPE_NOT_ALLOWED",
        "BLIND_TARGET_JIRA_EXCLUDED",
        "CURRENTNESS_NOT_ALLOWED",
        "NORMALIZATION_REJECTED",
        "NORMALIZATION_VALIDATION_FAILED",
        "PROVIDER_CANNOT_ATTEST_HUMAN_CONTRACT",
        "PROVIDER_CANNOT_CREATE_HUMAN_FEEDBACK",
        "RESULT_LIMIT_EXCEEDED",
        "SOURCE_CONTENT_EXCLUDED",
        "SOURCE_REFERENCE_EXCLUDED",
        "SOURCE_TYPE_EXCLUDED",
        "SOURCE_TYPE_NOT_REQUESTED",
        "SOURCE_VISIBILITY_NOT_ATTESTED",
        "TEMPORAL_OR_VERSION_MISMATCH",
        "UNSUPPORTED_SOURCE_TYPE",
        "VERIFIED_SOURCE_REQUIRED",
    }
)


class TraceAnswerState(StrEnum):
    YES = "YES"
    NO = "NO"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class TraceCompletionState(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"


class TraceEvidenceOrigin(StrEnum):
    LOCAL = "LOCAL"
    FLUFFYJAWS = "FLUFFYJAWS"


class TraceSemanticFusionState(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_EVALUATED = "NOT_EVALUATED"
    FUSED = "FUSED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class CitationDisclosureState(StrEnum):
    REDACTED = "REDACTED"
    ABSENT = "ABSENT"


class TraceCheckpoint(BaseModel):
    """A tri-state answer plus bounded, machine-readable justification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: TraceAnswerState
    reason_codes: tuple[str, ...] = Field(default=(), max_length=50)
    record_ids: tuple[str, ...] = Field(default=(), max_length=_MAX_IDS_PER_FIELD)

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(set(values)))
        if any(value not in _TRACE_REASON_CODES for value in normalized):
            raise ValueError("trace reason codes must use the static allowlist")
        return normalized

    @field_validator("record_ids")
    @classmethod
    def validate_record_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(set(values)))
        if any(
            _SAFE_RECORD_ID_RE.fullmatch(value) is None
            for value in normalized
        ):
            raise ValueError("trace record IDs must use a canonical typed ID")
        return normalized


class TraceEvidenceReference(BaseModel):
    """Content-free source identity sufficient to join to protected evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(pattern=_EVIDENCE_ID_PATTERN)
    origin: TraceEvidenceOrigin
    provider: Literal["", "fluffyjaws"] = ""
    provider_call_id: str = Field(
        default="", pattern=r"^(?:provider-call:[a-f0-9]{32})?$"
    )
    provenance_ids: tuple[str, ...] = Field(default=(), max_length=_MAX_IDS_PER_FIELD)
    source_type: EvidenceSourceType
    authority_class: AuthorityClass
    currentness: CurrentnessState
    verification_status: VerificationState
    source_identity_available: bool
    citation_disclosure: CitationDisclosureState
    normalized: bool
    used_by_verifier: bool
    semantic_fusion_state: TraceSemanticFusionState = (
        TraceSemanticFusionState.NOT_APPLICABLE
    )
    semantic_stance: QuestionEvidenceStance | None = None
    semantic_rejection_code: str = Field(default="", max_length=100)

    @field_validator("provenance_ids")
    @classmethod
    def normalize_provenance_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(set(values)))
        if any(
            re.fullmatch(_PROVENANCE_ID_PATTERN, value) is None
            for value in normalized
        ):
            raise ValueError("provenance IDs must use canonical provenance IDs")
        return normalized

    @model_validator(mode="after")
    def validate_citation_disclosure(self) -> "TraceEvidenceReference":
        expected = (
            CitationDisclosureState.REDACTED
            if self.source_identity_available
            else CitationDisclosureState.ABSENT
        )
        if self.citation_disclosure != expected:
            raise ValueError("citation disclosure must reflect source identity availability")
        if self.origin == TraceEvidenceOrigin.FLUFFYJAWS and not self.provider:
            raise ValueError("FluffyJaws evidence requires a provider name")
        if self.origin == TraceEvidenceOrigin.LOCAL and (
            self.semantic_fusion_state != TraceSemanticFusionState.NOT_APPLICABLE
            or self.semantic_stance is not None
            or self.semantic_rejection_code
        ):
            raise ValueError("local evidence cannot claim provider semantic fusion")
        if self.semantic_rejection_code and (
            self.semantic_rejection_code not in _SEMANTIC_REJECTION_CODES
            and self.semantic_rejection_code
            != "UNRECOGNIZED_SEMANTIC_REJECTION"
        ):
            raise ValueError("semantic rejection code must use the static allowlist")
        if (
            self.semantic_fusion_state == TraceSemanticFusionState.REJECTED
        ) != bool(self.semantic_rejection_code):
            raise ValueError("semantic rejection state and code must agree")
        return self


class ProviderCallTraceSummary(BaseModel):
    """Allowlisted operational fields for one provider call result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["fluffyjaws"]
    provider_call_id: str = Field(pattern=_PROVIDER_CALL_ID_PATTERN)
    provider_result_id: str = Field(pattern=_PROVIDER_RESULT_ID_PATTERN)
    query_id: str = Field(pattern=_QUERY_ID_PATTERN)
    status: EvidenceProviderStatus
    transport_outcome: ProviderTransportOutcome
    attempts: int = Field(ge=0, le=10)
    attempt_outcomes: tuple[ProviderTransportOutcome, ...] = Field(
        default=(), max_length=10
    )
    duration_ms: int = Field(ge=0)
    cache_state: ProviderCacheState
    circuit_state_before: ProviderCircuitState
    circuit_state_after: ProviderCircuitState
    accepted_evidence_ids: tuple[str, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )
    synthesis_ids: tuple[str, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )
    rejected_hit_count: int = Field(default=0, ge=0, le=_MAX_IDS_PER_FIELD)
    hit_disposition_reason_counts: dict[str, int] = Field(default_factory=dict)
    semantic_fusion_evaluated: bool = False
    fused_evidence_ids: tuple[str, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )
    consumed_evidence_ids: tuple[str, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )
    semantic_rejection_counts: dict[str, int] = Field(default_factory=dict)
    semantic_stance_counts: dict[str, int] = Field(default_factory=dict)
    source_attestation_count: int = Field(default=0, ge=0, le=_MAX_IDS_PER_FIELD)
    question_assessment_count: int = Field(default=0, ge=0, le=_MAX_IDS_PER_FIELD)
    semantic_authorization_count: int = Field(default=0, ge=0, le=_MAX_IDS_PER_FIELD)
    safe_error_code: str = Field(default="", max_length=100, pattern=r"^(?:[A-Z0-9_]+)?$")

    @field_validator(
        "accepted_evidence_ids", "fused_evidence_ids", "consumed_evidence_ids"
    )
    @classmethod
    def normalize_evidence_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(set(values)))
        if any(re.fullmatch(_EVIDENCE_ID_PATTERN, value) is None for value in normalized):
            raise ValueError("provider evidence IDs must use canonical evidence IDs")
        return normalized

    @field_validator("synthesis_ids")
    @classmethod
    def normalize_synthesis_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(set(values)))
        if any(re.fullmatch(_DISCOVERY_ID_PATTERN, value) is None for value in normalized):
            raise ValueError("provider synthesis IDs must use canonical discovery IDs")
        return normalized

    @field_validator("hit_disposition_reason_counts")
    @classmethod
    def validate_hit_reason_counts(cls, value: dict[str, int]) -> dict[str, int]:
        normalized = dict(sorted(value.items()))
        if len(normalized) > 100 or any(
            key not in _HIT_DISPOSITION_CODES
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
            or count > _MAX_IDS_PER_FIELD
            for key, count in normalized.items()
        ):
            raise ValueError("hit reason counts must use the static allowlist")
        return normalized

    @field_validator("semantic_rejection_counts")
    @classmethod
    def validate_semantic_rejection_counts(
        cls, value: dict[str, int]
    ) -> dict[str, int]:
        normalized = dict(sorted(value.items()))
        if len(normalized) > 100 or any(
            key not in _SEMANTIC_REJECTION_CODES
            and key != "UNRECOGNIZED_SEMANTIC_REJECTION"
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
            or count > _MAX_IDS_PER_FIELD
            for key, count in normalized.items()
        ):
            raise ValueError("semantic rejection counts must use the static allowlist")
        return normalized

    @field_validator("semantic_stance_counts")
    @classmethod
    def validate_semantic_stance_counts(cls, value: dict[str, int]) -> dict[str, int]:
        normalized = dict(sorted(value.items()))
        allowed = {row.value for row in QuestionEvidenceStance}
        if len(normalized) > len(allowed) or any(
            key not in allowed
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
            or count > _MAX_IDS_PER_FIELD
            for key, count in normalized.items()
        ):
            raise ValueError("semantic stance counts must use the enum allowlist")
        return normalized

    @field_validator("safe_error_code")
    @classmethod
    def validate_safe_error_code(cls, value: str) -> str:
        if value and value not in _SAFE_PROVIDER_ERROR_CODES | {
            "UNSAFE_PROVIDER_ERROR_CODE_REDACTED"
        }:
            raise ValueError("provider error code must use the static allowlist")
        return value

    @model_validator(mode="after")
    def validate_operational_counts(self) -> "ProviderCallTraceSummary":
        if self.attempts != len(self.attempt_outcomes):
            raise ValueError("provider attempts must equal attempt outcomes")
        accepted = set(self.accepted_evidence_ids)
        if not set(self.fused_evidence_ids).issubset(accepted):
            raise ValueError("fused evidence must be accepted provider evidence")
        if not set(self.consumed_evidence_ids).issubset(self.fused_evidence_ids):
            raise ValueError("consumed provider evidence must be fused evidence")
        if not self.semantic_fusion_evaluated and (
            self.fused_evidence_ids
            or self.consumed_evidence_ids
            or self.semantic_rejection_counts
            or self.semantic_stance_counts
            or self.source_attestation_count
            or self.question_assessment_count
            or self.semantic_authorization_count
        ):
            raise ValueError("unevaluated provider call cannot claim semantic fusion")
        return self


class HypothesisTraceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hypothesis_id: str = Field(pattern=_HYPOTHESIS_ID_PATTERN)
    state: HypothesisState
    supporting_evidence_ids: tuple[str, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )
    contradicting_evidence_ids: tuple[str, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )
    verification_evidence_ids: tuple[str, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )

    @field_validator(
        "supporting_evidence_ids",
        "contradicting_evidence_ids",
        "verification_evidence_ids",
    )
    @classmethod
    def validate_evidence_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(set(values)))
        if any(re.fullmatch(_EVIDENCE_ID_PATTERN, value) is None for value in normalized):
            raise ValueError("hypothesis evidence must use canonical evidence IDs")
        return normalized

    @model_validator(mode="after")
    def reject_conflicting_evidence(self) -> "HypothesisTraceSummary":
        if set(self.supporting_evidence_ids) & set(self.contradicting_evidence_ids):
            raise ValueError("hypothesis evidence cannot both support and contradict")
        return self


class ImplementationVerificationTraceSummary(BaseModel):
    """Opaque GitHub MCP lineage; no Jira/code/provider content is retained."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    handoff_id: str = Field(pattern=_GITHUB_HANDOFF_ID_PATTERN)
    result_id: str = Field(default="", pattern=r"^(?:github-result:[a-f0-9]{32})?$")
    trace_id: str = Field(pattern=_IMPLEMENTATION_TRACE_ID_PATTERN)
    status: GitHubImplementationVerificationStatus | None = None
    unresolved: bool = True

    @model_validator(mode="after")
    def validate_terminal_state(self) -> "ImplementationVerificationTraceSummary":
        terminal = self.status in {
            GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED,
            GitHubImplementationVerificationStatus.UNRELATED_PATH,
        }
        if self.unresolved == terminal:
            raise ValueError(
                "implementation verification unresolved state conflicts with status"
            )
        if self.status is not None and not self.result_id:
            raise ValueError("implementation verification status requires a result ID")
        if self.result_id and self.status is None:
            raise ValueError("implementation verification result ID requires a status")
        return self


class CandidateTraceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(pattern=_CANDIDATE_ID_PATTERN)
    promotion_status: PromotionStatus | None = None
    resulting_disposition: CoverageDisposition | None = None
    linkage_basis: Literal["UNRESOLVED_DECISION_ID"] = "UNRESOLVED_DECISION_ID"


class CoverageDispositionTraceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    disposition_id: str = Field(pattern=_DISPOSITION_ID_PATTERN)
    disposition: CoverageDisposition
    source_question_ids: tuple[str, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )
    source_hypothesis_ids: tuple[str, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )

    @field_validator("source_question_ids", "source_hypothesis_ids")
    @classmethod
    def normalize_source_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(values)))


class FinalOutputLocation(BaseModel):
    """Exact section membership; the current plan schema does not retain item offsets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_record_id: str = Field(
        pattern=r"^(?:question|candidate|disposition):[a-f0-9]{32}$"
    )
    record_type: Literal["QUESTION", "CANDIDATE", "DISPOSITION"]
    section_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")
    structured_path: str = Field(min_length=1, max_length=300)
    granularity: Literal["SECTION_ONLY"] = "SECTION_ONLY"

    @field_validator("structured_path")
    @classmethod
    def validate_structured_path(cls, value: str) -> str:
        if re.fullmatch(r"output_payload\.structured_plan\.sections\[[a-z0-9_]+\]", value) is None:
            raise ValueError("structured output path must use the fixed section notation")
        return value

    @field_validator("section_key")
    @classmethod
    def validate_section_key(cls, value: str) -> str:
        if value not in _PLAN_SECTION_KEYS:
            raise ValueError("output section key must use the canonical allowlist")
        return value


class QuestionEndToEndTrace(BaseModel):
    """One material question from generation through final output."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str = Field(pattern=_QUESTION_ID_PATTERN)
    dimension: SemanticDimension | None = None
    authority_subject: AuthoritySubject
    materiality: QueryMateriality
    blocking: bool
    local_result_status: RetrievalStatus | None = None

    question_generated: TraceCheckpoint
    why_generated: TraceCheckpoint
    generation_lineage: TraceCheckpoint
    local_retrieval_executed: TraceCheckpoint
    local_results: TraceCheckpoint
    fluffyjaws_called: TraceCheckpoint
    fluffyjaws_transport_executed: TraceCheckpoint
    why_fluffyjaws: TraceCheckpoint
    fluffyjaws_status: TraceCheckpoint
    fluffyjaws_results: TraceCheckpoint
    underlying_sources: TraceCheckpoint
    evidence_normalized: TraceCheckpoint
    evidence_used_by_verifier: TraceCheckpoint
    hypothesis_created: TraceCheckpoint
    disposition: TraceCheckpoint
    coverage_disposition_linkage: TraceCheckpoint
    final_output_location: TraceCheckpoint
    implementation_verification: TraceCheckpoint = Field(
        default_factory=lambda: TraceCheckpoint(
            state=TraceAnswerState.NOT_APPLICABLE,
            reason_codes=("IMPLEMENTATION_VERIFICATION_NOT_APPLICABLE",),
        )
    )

    local_retrieval_ids: tuple[str, ...] = Field(default=(), max_length=1)
    query_ids: tuple[str, ...] = Field(default=(), max_length=_MAX_IDS_PER_FIELD)
    provider_call_ids: tuple[str, ...] = Field(default=(), max_length=_MAX_IDS_PER_FIELD)
    evidence_ids: tuple[str, ...] = Field(default=(), max_length=_MAX_IDS_PER_FIELD)
    hypothesis_ids: tuple[str, ...] = Field(default=(), max_length=_MAX_IDS_PER_FIELD)
    disposition_ids: tuple[str, ...] = Field(default=(), max_length=_MAX_IDS_PER_FIELD)
    candidate_ids: tuple[str, ...] = Field(default=(), max_length=_MAX_IDS_PER_FIELD)
    implementation_handoff_ids: tuple[str, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )
    implementation_result_ids: tuple[str, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )
    implementation_trace_ids: tuple[str, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )
    local_evidence: tuple[TraceEvidenceReference, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )
    fluffyjaws_evidence: tuple[TraceEvidenceReference, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )
    provider_calls: tuple[ProviderCallTraceSummary, ...] = Field(
        default=(), max_length=50
    )
    hypotheses: tuple[HypothesisTraceSummary, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )
    candidates: tuple[CandidateTraceSummary, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )
    coverage_dispositions: tuple[CoverageDispositionTraceSummary, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )
    output_locations: tuple[FinalOutputLocation, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )
    implementation_verifications: tuple[
        ImplementationVerificationTraceSummary, ...
    ] = Field(default=(), max_length=_MAX_IDS_PER_FIELD)

    @field_validator(
        "local_retrieval_ids",
        "query_ids",
        "provider_call_ids",
        "evidence_ids",
        "hypothesis_ids",
        "disposition_ids",
        "candidate_ids",
        "implementation_handoff_ids",
        "implementation_result_ids",
        "implementation_trace_ids",
    )
    @classmethod
    def normalize_identifier_sets(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(set(values)))
        if any(_SAFE_RECORD_ID_RE.fullmatch(value) is None for value in normalized):
            raise ValueError("trace IDs must use canonical typed IDs")
        return normalized

    @model_validator(mode="after")
    def validate_identifier_projections(self) -> "QuestionEndToEndTrace":
        typed_sets = (
            (self.local_retrieval_ids, _RETRIEVAL_ID_PATTERN, "local retrieval"),
            (self.query_ids, _QUERY_ID_PATTERN, "query"),
            (self.provider_call_ids, _PROVIDER_CALL_ID_PATTERN, "provider call"),
            (self.evidence_ids, _EVIDENCE_ID_PATTERN, "evidence"),
            (self.hypothesis_ids, _HYPOTHESIS_ID_PATTERN, "hypothesis"),
            (self.disposition_ids, _DISPOSITION_ID_PATTERN, "disposition"),
            (self.candidate_ids, _CANDIDATE_ID_PATTERN, "candidate"),
            (
                self.implementation_handoff_ids,
                _GITHUB_HANDOFF_ID_PATTERN,
                "GitHub implementation handoff",
            ),
            (
                self.implementation_result_ids,
                _GITHUB_RESULT_ID_PATTERN,
                "GitHub implementation result",
            ),
            (
                self.implementation_trace_ids,
                _IMPLEMENTATION_TRACE_ID_PATTERN,
                "implementation trace",
            ),
        )
        for values, pattern, label in typed_sets:
            if any(re.fullmatch(pattern, value) is None for value in values):
                raise ValueError(f"{label} projection contains a wrong ID type")
        if self.provider_call_ids != tuple(
            sorted({row.provider_call_id for row in self.provider_calls})
        ):
            raise ValueError("provider_call_ids must project provider calls")
        if self.query_ids != tuple(sorted({row.query_id for row in self.provider_calls})):
            raise ValueError("query_ids must project provider calls")
        if self.hypothesis_ids != tuple(
            sorted({row.hypothesis_id for row in self.hypotheses})
        ):
            raise ValueError("hypothesis_ids must project hypotheses")
        if self.candidate_ids != tuple(sorted({row.candidate_id for row in self.candidates})):
            raise ValueError("candidate_ids must project linked candidates")
        if self.disposition_ids != tuple(
            sorted({row.disposition_id for row in self.coverage_dispositions})
        ):
            raise ValueError("disposition_ids must project coverage dispositions")
        if self.implementation_handoff_ids != tuple(
            sorted({row.handoff_id for row in self.implementation_verifications})
        ):
            raise ValueError("implementation handoff IDs must project summaries")
        if self.implementation_result_ids != tuple(
            sorted(
                {
                    row.result_id
                    for row in self.implementation_verifications
                    if row.result_id
                }
            )
        ):
            raise ValueError("implementation result IDs must project summaries")
        if self.implementation_trace_ids != tuple(
            sorted({row.trace_id for row in self.implementation_verifications})
        ):
            raise ValueError("implementation trace IDs must project summaries")
        evidence_ids = {
            row.evidence_id for row in self.local_evidence + self.fluffyjaws_evidence
        }
        if self.evidence_ids != tuple(sorted(evidence_ids)):
            raise ValueError("evidence_ids must project evidence references")
        for hypothesis in self.hypotheses:
            if not (
                set(hypothesis.supporting_evidence_ids)
                | set(hypothesis.contradicting_evidence_ids)
                | set(hypothesis.verification_evidence_ids)
            ).issubset(evidence_ids):
                raise ValueError("hypothesis evidence must exist in trace references")
        for call in self.provider_calls:
            call_evidence_ids = {
                row.evidence_id
                for row in self.fluffyjaws_evidence
                if row.provider_call_id == call.provider_call_id
            }
            if set(call.accepted_evidence_ids) != call_evidence_ids:
                raise ValueError("provider accepted evidence must match call references")
        for location in self.output_locations:
            expected_type = (
                "QUESTION"
                if location.source_record_id == self.question_id
                else "CANDIDATE"
                if location.source_record_id in self.candidate_ids
                else "DISPOSITION"
                if location.source_record_id in self.disposition_ids
                else ""
            )
            if not expected_type or location.record_type != expected_type:
                raise ValueError(
                    "output location must reference this question/candidate/disposition"
                )
        return self


class QuestionRetrievalTraceBundle(BaseModel):
    """Content-minimal run sidecar; safe to persist in a private debug store."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["aem-guides-question-retrieval-trace-v1"] = (
        QUESTION_RETRIEVAL_TRACE_SCHEMA
    )
    trace_id: str = Field(
        default="", pattern=r"^(?:question-trace:[a-f0-9]{32})?$"
    )
    runtime_id: Literal["aem-guides-test-plan-runtime"] = CANONICAL_RUNTIME_ID
    runtime_version: Literal["2.0.0"] = CANONICAL_RUNTIME_VERSION
    run_id: str = Field(pattern=_RUN_ID_PATTERN)
    request_id: str = Field(pattern=_REQUEST_ID_PATTERN)
    plan_id: None = None
    plan_id_state: Literal["UNKNOWN"] = "UNKNOWN"
    plan_id_reason_code: Literal["CANONICAL_PLAN_ID_NOT_DEFINED"] = (
        "CANONICAL_PLAN_ID_NOT_DEFINED"
    )
    output_sha256: str = Field(default="", pattern=r"^(?:[a-f0-9]{64})?$")
    completion_state: TraceCompletionState
    failed_stage: CanonicalRuntimeStage | None = None
    fluffyjaws_mode: FluffyJawsRuntimeMode
    warning_codes: tuple[str, ...] = Field(default=(), max_length=50)
    generated_question_count: int = Field(default=0, ge=0, le=_MAX_IDS_PER_FIELD)
    generated_question_ids: tuple[str, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )
    questions: tuple[QuestionEndToEndTrace, ...] = Field(
        default=(), max_length=_MAX_IDS_PER_FIELD
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_pre_fj17_v1_trace(cls, value: object) -> object:
        """Verify and migrate trace-v1 rows written before FJ-17 fields existed."""

        if not isinstance(value, dict):
            return value
        questions = value.get("questions")
        if not isinstance(questions, (list, tuple)) or not any(
            isinstance(question, dict)
            and "implementation_verification" not in question
            for question in questions
        ):
            return value
        supplied_trace_id = str(value.get("trace_id") or "")
        legacy_identity = {
            key: child for key, child in value.items() if key != "trace_id"
        }
        expected_legacy_id = (
            f"question-trace:{stable_sha256(legacy_identity)[:32]}"
        )
        if supplied_trace_id and supplied_trace_id != expected_legacy_id:
            raise ValueError("legacy trace_id does not match deterministic identity")
        migrated = dict(value)
        migrated_questions: list[object] = []
        for question in questions:
            if not isinstance(question, dict):
                migrated_questions.append(question)
                continue
            migrated_question = dict(question)
            migrated_question.setdefault(
                "implementation_verification",
                {
                    "state": TraceAnswerState.NOT_APPLICABLE.value,
                    "reason_codes": [
                        "IMPLEMENTATION_VERIFICATION_NOT_APPLICABLE"
                    ],
                    "record_ids": [],
                },
            )
            migrated_questions.append(migrated_question)
        migrated["questions"] = migrated_questions
        # The verified legacy identity did not include FJ-17 projections.  The
        # normal validator assigns the deterministic migrated identity.
        migrated["trace_id"] = ""
        return migrated

    @field_validator("warning_codes")
    @classmethod
    def normalize_warning_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(set(values)))
        if any(value not in _TRACE_WARNING_CODES for value in normalized):
            raise ValueError("trace warnings must use the static allowlist")
        return normalized

    @field_validator("generated_question_ids")
    @classmethod
    def validate_generated_question_ids(
        cls, values: tuple[str, ...]
    ) -> tuple[str, ...]:
        normalized = tuple(sorted(set(values)))
        if any(re.fullmatch(_QUESTION_ID_PATTERN, value) is None for value in normalized):
            raise ValueError("generated question IDs must use canonical question IDs")
        return normalized

    @model_validator(mode="after")
    def identify_and_validate(self) -> "QuestionRetrievalTraceBundle":
        if (
            self.completion_state == TraceCompletionState.COMPLETE
            and self.failed_stage is not None
        ):
            raise ValueError("complete trace cannot contain a failed stage")
        if (
            self.completion_state == TraceCompletionState.PARTIAL
            and self.failed_stage is None
        ):
            raise ValueError("partial trace requires a failed stage")
        sorted_questions = tuple(sorted(self.questions, key=lambda row: row.question_id))
        if len({row.question_id for row in sorted_questions}) != len(sorted_questions):
            raise ValueError("question trace contains duplicate question IDs")
        projected_question_ids = tuple(row.question_id for row in sorted_questions)
        if self.generated_question_ids != projected_question_ids:
            raise ValueError("generated question manifest must equal question rows")
        if self.generated_question_count != len(projected_question_ids):
            raise ValueError("generated question count must equal question rows")
        object.__setattr__(self, "questions", sorted_questions)
        identity = self.model_dump(mode="json", exclude={"trace_id"})
        expected = f"question-trace:{stable_sha256(identity)[:32]}"
        if self.trace_id and self.trace_id != expected:
            raise ValueError("trace_id does not match deterministic identity")
        object.__setattr__(self, "trace_id", expected)
        return self


_LAST_QUESTION_RETRIEVAL_TRACE: ContextVar[QuestionRetrievalTraceBundle | None] = (
    ContextVar("aem_guides_last_question_retrieval_trace", default=None)
)


def clear_last_question_retrieval_trace() -> None:
    _LAST_QUESTION_RETRIEVAL_TRACE.set(None)


def get_last_question_retrieval_trace() -> QuestionRetrievalTraceBundle | None:
    trace = _LAST_QUESTION_RETRIEVAL_TRACE.get()
    return trace.model_copy(deep=True) if trace is not None else None


def _checkpoint(
    state: TraceAnswerState,
    *reason_codes: str,
    record_ids: Iterable[str] = (),
) -> TraceCheckpoint:
    return TraceCheckpoint(
        state=state,
        reason_codes=tuple(reason_codes),
        record_ids=tuple(record_ids),
    )


def _safe_error_code(value: str) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if text not in _SAFE_PROVIDER_ERROR_CODES:
        return "UNSAFE_PROVIDER_ERROR_CODE_REDACTED"
    return text


def _validate_shadow_call(call: FluffyJawsShadowCallTrace) -> None:
    result = call.call_result
    sidecar = call.trace_sidecar
    if (
        call.question_id != call.query.question_id
        or call.question_id != sidecar.question_id
        or call.query.query_id != result.query_id
        or call.query.query_id != sidecar.query_id
        or result.provider != sidecar.provider
        or result.provider_call_id != sidecar.provider_call_id
        or result.provider_result_id != sidecar.provider_result_id
    ):
        raise ValueError("FluffyJaws trace contains inconsistent call linkage")


def _evidence_reference(
    record: EvidenceRecord,
    *,
    origin: TraceEvidenceOrigin,
    used_ids: set[str],
    provider: str = "",
    provider_call_id: str = "",
    provenance_ids: Iterable[str] = (),
    semantic_fusion_state: TraceSemanticFusionState = (
        TraceSemanticFusionState.NOT_APPLICABLE
    ),
    semantic_stance: QuestionEvidenceStance | None = None,
    semantic_rejection_code: str = "",
) -> TraceEvidenceReference:
    source_identity_available = bool(
        record.source_reference or record.source_location or record.source_native_id
    )
    return TraceEvidenceReference(
        evidence_id=record.evidence_id,
        origin=origin,
        provider=provider,
        provider_call_id=provider_call_id,
        provenance_ids=tuple(provenance_ids),
        source_type=record.source_type,
        authority_class=record.requirement_authority,
        currentness=record.currentness,
        verification_status=record.verification_status,
        source_identity_available=source_identity_available,
        citation_disclosure=(
            CitationDisclosureState.REDACTED
            if source_identity_available
            else CitationDisclosureState.ABSENT
        ),
        normalized=True,
        used_by_verifier=record.evidence_id in used_ids,
        semantic_fusion_state=semantic_fusion_state,
        semantic_stance=semantic_stance,
        semantic_rejection_code=semantic_rejection_code,
    )


def _generation_reason(
    question: MissingQuestion,
) -> tuple[TraceAnswerState, str, SemanticDimension | None]:
    if question.dimension is not None:
        return (
            TraceAnswerState.YES,
            "UNRESOLVED_SEMANTIC_DIMENSION",
            question.dimension,
        )
    return (
        TraceAnswerState.UNKNOWN,
        "QUESTION_GENERATION_REASON_NOT_RETAINED",
        None,
    )


def _safe_skip_reason(value: str) -> str:
    try:
        return FluffyJawsNoCallReason(value).value
    except ValueError:
        return "UNRECOGNIZED_PROVIDER_SKIP_REASON"


def _safe_semantic_rejection(value: str) -> str:
    return (
        value
        if value in _SEMANTIC_REJECTION_CODES
        else "UNRECOGNIZED_SEMANTIC_REJECTION"
    )


def _safe_hit_reason(value: str) -> str:
    return value if value in _HIT_DISPOSITION_CODES else "NORMALIZATION_REJECTED"


def _provider_call_summary(
    call: FluffyJawsShadowCallTrace,
    *,
    consumed_evidence_ids: set[str],
) -> ProviderCallTraceSummary:
    result = call.call_result
    hit_reason_counts = Counter(
        _safe_hit_reason(row.reason_code) for row in call.hit_dispositions
    )
    rejection_counts = Counter(
        _safe_semantic_rejection(value)
        for value in call.semantic_fusion_rejections.values()
    )
    stance_counts = Counter(value.value for value in call.semantic_stances.values())
    return ProviderCallTraceSummary(
        provider=result.provider,
        provider_call_id=result.provider_call_id,
        provider_result_id=result.provider_result_id,
        query_id=result.query_id,
        status=result.status,
        transport_outcome=result.transport_outcome,
        attempts=result.attempts,
        attempt_outcomes=tuple(result.attempt_outcomes),
        duration_ms=result.duration_ms,
        cache_state=result.cache_state,
        circuit_state_before=result.circuit_state_before,
        circuit_state_after=result.circuit_state_after,
        accepted_evidence_ids=tuple(result.accepted_evidence_ids),
        synthesis_ids=tuple(row.synthesis_id for row in call.discovery_syntheses),
        rejected_hit_count=result.rejected_hit_count,
        hit_disposition_reason_counts=dict(hit_reason_counts),
        semantic_fusion_evaluated=call.semantic_fusion_evaluated,
        fused_evidence_ids=tuple(call.semantic_fusion_evidence_ids),
        consumed_evidence_ids=tuple(
            sorted(set(call.semantic_fusion_evidence_ids) & consumed_evidence_ids)
        ),
        semantic_rejection_counts=dict(rejection_counts),
        semantic_stance_counts=dict(stance_counts),
        source_attestation_count=len(call.source_attestation_ids),
        question_assessment_count=len(call.question_assessment_ids),
        semantic_authorization_count=len(call.semantic_authorization_ids),
        safe_error_code=_safe_error_code(result.redacted_error_code),
    )


def _output_locations(
    plan: StructuredQEPlan | None,
    *,
    question_id: str,
    candidate_ids: set[str],
    disposition_ids: set[str],
) -> tuple[FinalOutputLocation, ...]:
    if plan is None:
        return ()
    locations: list[FinalOutputLocation] = []
    target_types = {
        question_id: "QUESTION",
        **{value: "CANDIDATE" for value in candidate_ids},
        **{value: "DISPOSITION" for value in disposition_ids},
    }
    for section in plan.sections:
        for record_id in sorted(set(section.source_record_ids) & set(target_types)):
            locations.append(
                FinalOutputLocation(
                    source_record_id=record_id,
                    record_type=target_types[record_id],  # type: ignore[arg-type]
                    section_key=section.section_key,
                    structured_path=(
                        "output_payload.structured_plan.sections["
                        f"{section.section_key}]"
                    ),
                )
            )
    return tuple(
        sorted(locations, key=lambda row: (row.section_key, row.source_record_id))
    )


def build_question_retrieval_trace(
    *,
    run_id: str,
    request: GenerationRequest,
    output_sha256: str,
    completion_state: TraceCompletionState,
    failed_stage: CanonicalRuntimeStage | str | None = None,
    questions: Iterable[MissingQuestion] = (),
    local_retrievals: Iterable[DirectedRetrievalRecord] = (),
    hypotheses: Iterable[BehaviorHypothesis] = (),
    implementation_handoffs: Iterable[
        GitHubImplementationVerificationHandoff
    ] = (),
    implementation_results: Iterable[GitHubImplementationVerificationResult] = (),
    unresolved_implementation_handoff_ids: Iterable[str] = (),
    dispositions: Iterable[CoverageDispositionRecord] = (),
    candidates: Iterable[AcceptanceCandidate] = (),
    promotions: Iterable[AcceptancePromotionDecision] = (),
    structured_plan: StructuredQEPlan | None = None,
    evidence_records: Iterable[EvidenceRecord] = (),
    fluffyjaws_mode: FluffyJawsRuntimeMode,
    fluffyjaws_trace: FluffyJawsShadowRunTrace | None = None,
) -> QuestionRetrievalTraceBundle:
    """Build a strict projection without accepting a raw generation DTO."""

    question_rows = list(questions)
    local_rows = list(local_retrievals)
    hypothesis_rows = list(hypotheses)
    implementation_handoff_rows = list(implementation_handoffs)
    implementation_result_rows = list(implementation_results)
    unresolved_implementation_ids = set(unresolved_implementation_handoff_ids)
    disposition_rows = list(dispositions)
    candidate_rows = list(candidates)
    promotion_rows = list(promotions)
    evidence_rows = list(evidence_records)
    question_ids = {row.question_id for row in question_rows}
    if len(question_ids) != len(question_rows):
        raise ValueError("question trace contains duplicate question IDs")
    if len({row.evidence_id for row in evidence_rows}) != len(evidence_rows):
        raise ValueError("question trace contains duplicate evidence IDs")
    if len({row.hypothesis_id for row in hypothesis_rows}) != len(hypothesis_rows):
        raise ValueError("question trace contains duplicate hypothesis IDs")
    if len({row.handoff_id for row in implementation_handoff_rows}) != len(
        implementation_handoff_rows
    ):
        raise ValueError("question trace contains duplicate implementation handoffs")
    if len({row.result_id for row in implementation_result_rows}) != len(
        implementation_result_rows
    ):
        raise ValueError("question trace contains duplicate implementation results")
    if len({row.handoff_id for row in implementation_result_rows}) != len(
        implementation_result_rows
    ):
        raise ValueError(
            "question trace contains duplicate results for one implementation handoff"
        )
    if len({row.disposition_id for row in disposition_rows}) != len(
        disposition_rows
    ):
        raise ValueError("question trace contains duplicate disposition IDs")
    if len({row.candidate_id for row in candidate_rows}) != len(candidate_rows):
        raise ValueError("question trace contains duplicate candidate IDs")
    if len({row.candidate_id for row in promotion_rows}) != len(promotion_rows):
        raise ValueError("question trace contains duplicate promotion decisions")
    for record in evidence_rows:
        if (
            record.tenant_id != request.tenant_id
            or not record_visible_to(record, request.principal)
            or (
                request.allowed_sources
                and record.source_type not in set(request.allowed_sources)
            )
        ):
            raise ValueError("question trace evidence is outside request visibility")
    evidence_by_id = {row.evidence_id: row for row in evidence_rows}
    for retrieval in local_rows:
        matched_ids = set(retrieval.matched_evidence_ids)
        if not matched_ids.issubset(evidence_by_id):
            raise ValueError("local retrieval references unavailable evidence")
        if retrieval.status == RetrievalStatus.USED and not matched_ids:
            raise ValueError("USED local retrieval requires matched evidence")
        if retrieval.status == RetrievalStatus.UNAVAILABLE and matched_ids:
            raise ValueError("UNAVAILABLE local retrieval cannot contain matches")
    local_by_question = {row.question_id: row for row in local_rows}
    if len(local_by_question) != len(local_rows):
        raise ValueError("local retrieval trace contains duplicate question IDs")
    if not set(local_by_question).issubset(question_ids):
        raise ValueError("local retrieval trace references an unknown question ID")
    if any(
        row.derived_from_question_id
        and row.derived_from_question_id not in question_ids
        for row in hypothesis_rows
    ):
        raise ValueError("hypothesis trace references an unknown question ID")
    hypothesis_ids = {row.hypothesis_id for row in hypothesis_rows}
    hypothesis_lineage_ids = hypothesis_ids | {
        row.verification_origin_hypothesis_id
        for row in hypothesis_rows
        if row.verification_origin_hypothesis_id
    }
    handoff_ids = {row.handoff_id for row in implementation_handoff_rows}
    if not unresolved_implementation_ids.issubset(handoff_ids):
        raise ValueError("unresolved implementation handoff is absent from trace")
    if any(
        row.question_id not in question_ids
        or row.hypothesis_id not in hypothesis_lineage_ids
        for row in implementation_handoff_rows
    ):
        raise ValueError("implementation handoff has unknown question/hypothesis lineage")
    handoffs_by_id = {row.handoff_id: row for row in implementation_handoff_rows}
    if any(
        row.handoff_id not in handoffs_by_id
        or row.question_id != handoffs_by_id[row.handoff_id].question_id
        or row.hypothesis_id != handoffs_by_id[row.handoff_id].hypothesis_id
        or row.trace_id != handoffs_by_id[row.handoff_id].trace_id
        for row in implementation_result_rows
    ):
        raise ValueError("implementation result breaks sealed handoff lineage")
    disposition_ids = {row.disposition_id for row in disposition_rows}
    if any(
        not set(row.source_question_ids).issubset(question_ids)
        or not set(row.source_hypothesis_ids).issubset(hypothesis_ids)
        for row in disposition_rows
    ):
        raise ValueError("coverage disposition trace has unknown question/hypothesis lineage")
    if any(
        not set(row.source_disposition_ids).issubset(disposition_ids)
        for row in candidate_rows
    ):
        raise ValueError("candidate trace references an unknown coverage disposition")
    if any(
        unresolved_id not in question_ids
        for row in candidate_rows
        for unresolved_id in row.unresolved_decision_ids
    ):
        raise ValueError("candidate trace references an unknown question ID")
    if not {row.candidate_id for row in promotion_rows}.issubset(
        {row.candidate_id for row in candidate_rows}
    ):
        raise ValueError("promotion trace references an unknown candidate ID")

    warning_codes: list[str] = []
    trace = fluffyjaws_trace
    if trace is not None and (trace.run_id != run_id or trace.request_id != request.request_id):
        warning_codes.append("FLUFFYJAWS_TRACE_IDENTITY_MISMATCH")
        trace = None
    if trace is not None and trace.mode != fluffyjaws_mode:
        raise ValueError("FluffyJaws trace mode does not match runtime mode")
    if trace is not None:
        trace_question_ids = (
            set(trace.eligible_question_ids)
            | set(trace.dispatched_question_ids)
            | set(trace.skipped_question_ids)
            | set(trace.skip_reasons)
            | set(trace.fused_evidence_ids_by_question)
            | set(trace.fused_question_stances)
        )
        if not trace_question_ids.issubset(question_ids):
            raise ValueError("FluffyJaws run trace references an unknown question ID")
        if fluffyjaws_mode == FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW and (
            trace.fused_evidence_ids
            or trace.fused_evidence_ids_by_question
            or trace.consumed_evidence_ids
            or any(call.semantic_fusion_evaluated for call in trace.calls)
        ):
            raise ValueError("SHADOW trace cannot claim semantic fusion or consumption")

    routes_by_question: dict[str, FluffyJawsRoutingRecord] = {}
    calls_by_question: dict[str, list[FluffyJawsShadowCallTrace]] = {}
    provider_evidence_questions: dict[str, set[str]] = {}
    if trace is not None:
        traced_question_ids = {
            row.question_id for row in trace.routing_records
        } | {row.question_id for row in trace.calls}
        if not traced_question_ids.issubset(question_ids):
            raise ValueError("FluffyJaws trace references an unknown question ID")
        for route in trace.routing_records:
            if route.question_id in routes_by_question:
                raise ValueError("FluffyJaws trace contains duplicate routing records")
            routes_by_question[route.question_id] = route
        seen_provider_call_ids: set[str] = set()
        seen_query_ids: set[str] = set()
        for call in trace.calls:
            _validate_shadow_call(call)
            call_id = call.call_result.provider_call_id
            query_id = call.query.query_id
            if call_id in seen_provider_call_ids or query_id in seen_query_ids:
                raise ValueError("FluffyJaws trace contains duplicate call/query IDs")
            seen_provider_call_ids.add(call_id)
            seen_query_ids.add(query_id)
            for record in call.evidence_records:
                if (
                    record.tenant_id != request.tenant_id
                    or not record_visible_to(record, request.principal)
                    or (
                        request.allowed_sources
                        and record.source_type not in set(request.allowed_sources)
                    )
                ):
                    raise ValueError(
                        "FluffyJaws trace evidence is outside request visibility"
                    )
                provider_evidence_questions.setdefault(record.evidence_id, set()).add(
                    call.question_id
                )
            calls_by_question.setdefault(call.question_id, []).append(call)
        if fluffyjaws_mode == FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS:
            for question_id, question_calls in calls_by_question.items():
                route = routes_by_question.get(question_id)
                if route is None or not route.provider_called:
                    raise ValueError(
                        "SECOND_PASS provider call requires a positive routing record"
                    )

    hypotheses_by_question: dict[str, list[BehaviorHypothesis]] = {}
    for hypothesis in hypothesis_rows:
        if hypothesis.derived_from_question_id:
            hypotheses_by_question.setdefault(
                hypothesis.derived_from_question_id, []
            ).append(hypothesis)
    hypothesis_by_id = {row.hypothesis_id: row for row in hypothesis_rows}
    dispositions_by_question: dict[str, list[CoverageDispositionRecord]] = {}
    for disposition in disposition_rows:
        linked_question_ids = set(disposition.source_question_ids)
        linked_question_ids.update(
            hypothesis_by_id[hypothesis_id].derived_from_question_id
            for hypothesis_id in disposition.source_hypothesis_ids
            if hypothesis_id in hypothesis_by_id
            and hypothesis_by_id[hypothesis_id].derived_from_question_id
        )
        for question_id in linked_question_ids:
            dispositions_by_question.setdefault(question_id, []).append(disposition)
    promotions_by_candidate = {row.candidate_id: row for row in promotion_rows}
    implementation_handoffs_by_question: dict[
        str, list[GitHubImplementationVerificationHandoff]
    ] = {}
    for handoff in implementation_handoff_rows:
        implementation_handoffs_by_question.setdefault(
            handoff.question_id, []
        ).append(handoff)
    implementation_results_by_handoff = {
        row.handoff_id: row for row in implementation_result_rows
    }

    output: list[QuestionEndToEndTrace] = []
    for question in question_rows:
        generation_state, generation_reason, dimension = _generation_reason(question)
        local = local_by_question.get(question.question_id)
        local_ids = tuple(local.matched_evidence_ids) if local is not None else ()
        question_hypotheses = sorted(
            hypotheses_by_question.get(question.question_id, []),
            key=lambda row: row.hypothesis_id,
        )
        verifier_cited_ids = {
            evidence_id
            for hypothesis in question_hypotheses
            for evidence_id in (
                list(hypothesis.supporting_evidence_ids)
                + list(hypothesis.contradicting_evidence_ids)
                + list(hypothesis.verification_evidence_ids)
            )
        }
        question_implementation_handoffs = sorted(
            implementation_handoffs_by_question.get(question.question_id, []),
            key=lambda row: row.handoff_id,
        )
        implementation_summaries = tuple(
            ImplementationVerificationTraceSummary(
                handoff_id=handoff.handoff_id,
                result_id=(
                    implementation_results_by_handoff[handoff.handoff_id].result_id
                    if handoff.handoff_id in implementation_results_by_handoff
                    else ""
                ),
                trace_id=handoff.trace_id,
                status=(
                    implementation_results_by_handoff[handoff.handoff_id].status
                    if handoff.handoff_id in implementation_results_by_handoff
                    else None
                ),
                unresolved=handoff.handoff_id in unresolved_implementation_ids,
            )
            for handoff in question_implementation_handoffs
        )
        if not implementation_summaries:
            implementation_checkpoint = _checkpoint(
                TraceAnswerState.NOT_APPLICABLE
                if question.authority_subject != AuthoritySubject.ACTUAL_IMPLEMENTATION
                else TraceAnswerState.NO,
                "IMPLEMENTATION_VERIFICATION_NOT_APPLICABLE"
                if question.authority_subject != AuthoritySubject.ACTUAL_IMPLEMENTATION
                else "IMPLEMENTATION_HANDOFF_NOT_CREATED",
            )
        elif any(row.unresolved for row in implementation_summaries):
            implementation_checkpoint = _checkpoint(
                TraceAnswerState.PARTIAL,
                "IMPLEMENTATION_VERIFICATION_PENDING_OR_UNRESOLVED",
                record_ids=(
                    identifier
                    for row in implementation_summaries
                    for identifier in (
                        row.handoff_id,
                        row.result_id,
                        row.trace_id,
                    )
                    if identifier
                ),
            )
        else:
            implementation_checkpoint = _checkpoint(
                TraceAnswerState.YES,
                "IMPLEMENTATION_VERIFICATION_TERMINAL",
                record_ids=(
                    identifier
                    for row in implementation_summaries
                    for identifier in (
                        row.handoff_id,
                        row.result_id,
                        row.trace_id,
                    )
                    if identifier
                ),
            )
        linked_candidates = sorted(
            (
                row
                for row in candidate_rows
                if question.question_id in row.unresolved_decision_ids
            ),
            key=lambda row: row.candidate_id,
        )
        linked_dispositions = sorted(
            dispositions_by_question.get(question.question_id, []),
            key=lambda row: row.disposition_id,
        )
        disposition_summaries = tuple(
            CoverageDispositionTraceSummary(
                disposition_id=row.disposition_id,
                disposition=row.disposition,
                source_question_ids=tuple(row.source_question_ids),
                source_hypothesis_ids=tuple(row.source_hypothesis_ids),
            )
            for row in linked_dispositions
        )
        candidate_summaries = tuple(
            CandidateTraceSummary(
                candidate_id=row.candidate_id,
                promotion_status=(
                    promotions_by_candidate[row.candidate_id].status
                    if row.candidate_id in promotions_by_candidate
                    else None
                ),
                resulting_disposition=(
                    promotions_by_candidate[row.candidate_id].resulting_disposition
                    if row.candidate_id in promotions_by_candidate
                    else None
                ),
            )
            for row in linked_candidates
        )

        calls = sorted(
            calls_by_question.get(question.question_id, []),
            key=lambda row: (row.call_result.provider, row.call_result.provider_call_id),
        )
        route = routes_by_question.get(question.question_id)
        skip_reason = trace.skip_reasons.get(question.question_id, "") if trace else ""
        if route is not None and not route.provider_called and calls:
            raise ValueError("no-call routing record cannot contain provider calls")
        consumed_for_run = (
            set(trace.consumed_evidence_ids)
            if trace is not None
            and fluffyjaws_mode == FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS
            else set()
        )
        provider_summaries = tuple(
            _provider_call_summary(
                call,
                consumed_evidence_ids=consumed_for_run,
            )
            for call in calls
        )
        fj_accepted_ids = {
            evidence_id
            for call in calls
            for evidence_id in call.call_result.accepted_evidence_ids
        }
        synthesis_ids = {
            row.synthesis_id for call in calls for row in call.discovery_syntheses
        }
        query_ids = tuple(call.query.query_id for call in calls)

        local_id_set = set(local_ids)
        global_provider_ids = set(provider_evidence_questions)
        foreign_provider_citations = verifier_cited_ids & (
            global_provider_ids - fj_accepted_ids - local_id_set
        )
        if foreign_provider_citations:
            raise ValueError(
                "provider evidence belongs to a different question/call"
            )
        provider_only_citations = verifier_cited_ids & (
            fj_accepted_ids - local_id_set
        )
        if (
            fluffyjaws_mode == FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW
            and provider_only_citations
        ):
            raise ValueError("SHADOW provider evidence cannot be verifier input")
        provider_used_ids: set[str] = set()
        if trace is not None and fluffyjaws_mode == FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS:
            fused_for_question = set(
                trace.fused_evidence_ids_by_question.get(question.question_id, [])
            )
            provider_used_ids = (
                verifier_cited_ids
                & fj_accepted_ids
                & set(trace.consumed_evidence_ids)
                & set(trace.fused_evidence_ids)
                & fused_for_question
            )
            if provider_only_citations - provider_used_ids:
                raise ValueError(
                    "SECOND_PASS provider evidence lacks fused/consumed linkage"
                )
        # GitHub verification results are canonical evidence cited directly by
        # the verifier rather than local-retrieval matches.  Count all cited,
        # non-provider canonical IDs so their usage is not silently lost.
        local_used_ids = (
            verifier_cited_ids & set(evidence_by_id)
        ) - global_provider_ids
        permitted_verifier_used_ids = local_used_ids | provider_used_ids

        unknown_verifier_ids = verifier_cited_ids - set(evidence_by_id) - fj_accepted_ids
        if unknown_verifier_ids:
            raise ValueError("verifier cites evidence absent from canonical/provider records")
        local_reference_ids = local_id_set | (
            (verifier_cited_ids & set(evidence_by_id)) - global_provider_ids
        )

        local_evidence = tuple(
            _evidence_reference(
                evidence_by_id[evidence_id],
                origin=TraceEvidenceOrigin.LOCAL,
                used_ids=local_used_ids,
            )
            for evidence_id in sorted(local_reference_ids)
            if evidence_id in evidence_by_id
        )
        fj_evidence_rows: list[TraceEvidenceReference] = []
        for call in calls:
            provenance_by_evidence: dict[str, list[str]] = {}
            for provenance in call.provenance:
                provenance_by_evidence.setdefault(provenance.evidence_id, []).append(
                    provenance.provenance_id
                )
            for record in call.evidence_records:
                if not call.semantic_fusion_evaluated:
                    fusion_state = TraceSemanticFusionState.NOT_EVALUATED
                    rejection_code = ""
                elif record.evidence_id in call.semantic_fusion_evidence_ids:
                    fusion_state = TraceSemanticFusionState.FUSED
                    rejection_code = ""
                elif record.evidence_id in call.semantic_fusion_rejections:
                    fusion_state = TraceSemanticFusionState.REJECTED
                    rejection_code = _safe_semantic_rejection(
                        call.semantic_fusion_rejections[record.evidence_id]
                    )
                else:
                    fusion_state = TraceSemanticFusionState.UNKNOWN
                    rejection_code = ""
                fj_evidence_rows.append(
                    _evidence_reference(
                        record,
                        origin=TraceEvidenceOrigin.FLUFFYJAWS,
                        used_ids=provider_used_ids,
                        provider=call.call_result.provider,
                        provider_call_id=call.call_result.provider_call_id,
                        provenance_ids=provenance_by_evidence.get(record.evidence_id, []),
                        semantic_fusion_state=fusion_state,
                        semantic_stance=call.semantic_stances.get(record.evidence_id),
                        semantic_rejection_code=rejection_code,
                    )
                )
        fj_evidence = tuple(
            sorted(
                {row.evidence_id: row for row in fj_evidence_rows}.values(),
                key=lambda row: row.evidence_id,
            )
        )

        if fluffyjaws_mode == FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED:
            fj_called = _checkpoint(
                TraceAnswerState.NO, "FLUFFYJAWS_MODE_DISABLED"
            )
            why_fj = _checkpoint(
                TraceAnswerState.NOT_APPLICABLE, "FLUFFYJAWS_MODE_DISABLED"
            )
        elif trace is None:
            fj_called = _checkpoint(
                TraceAnswerState.UNKNOWN, "FLUFFYJAWS_TRACE_UNAVAILABLE"
            )
            why_fj = _checkpoint(
                TraceAnswerState.UNKNOWN, "FLUFFYJAWS_TRACE_UNAVAILABLE"
            )
        elif fluffyjaws_mode == FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW:
            if calls:
                fj_called = _checkpoint(
                    TraceAnswerState.YES,
                    "SHADOW_LOGICAL_CALL_RECORDED",
                    record_ids=(row.call_result.provider_call_id for row in calls),
                )
                why_fj = _checkpoint(
                    TraceAnswerState.YES, "SHADOW_OBSERVATION_MODE"
                )
            else:
                reason = (
                    _safe_skip_reason(skip_reason)
                    if skip_reason
                    else "SHADOW_CALL_NOT_RECORDED"
                )
                fj_called = _checkpoint(TraceAnswerState.NO, reason)
                why_fj = _checkpoint(TraceAnswerState.NO, reason)
        elif route is not None:
            if route.provider_called:
                reasons = tuple(
                    value.value for value in route.why_fj_called
                )
                fj_called = _checkpoint(
                    TraceAnswerState.YES,
                    "LOGICAL_PROVIDER_CALL_RECORDED",
                    record_ids=(row.call_result.provider_call_id for row in calls),
                )
                why_fj = _checkpoint(TraceAnswerState.YES, *reasons)
            else:
                reasons = tuple(
                    value.value for value in route.why_fj_not_called
                ) or (
                    _safe_skip_reason(skip_reason)
                    if skip_reason
                    else "SECOND_PASS_NOT_CALLED",
                )
                fj_called = _checkpoint(TraceAnswerState.NO, *reasons)
                why_fj = _checkpoint(TraceAnswerState.NO, *reasons)
        else:
            reason = (
                _safe_skip_reason(skip_reason)
                if skip_reason
                else "ROUTING_RECORD_UNAVAILABLE"
            )
            fj_called = _checkpoint(TraceAnswerState.NO, reason)
            why_fj = _checkpoint(
                TraceAnswerState.YES if skip_reason else TraceAnswerState.UNKNOWN,
                reason,
            )

        transport_attempts = sum(row.call_result.attempts for row in calls)
        if transport_attempts:
            fj_transport = _checkpoint(
                TraceAnswerState.YES,
                "PROVIDER_TRANSPORT_ATTEMPTED",
                record_ids=(row.call_result.provider_call_id for row in calls),
            )
        elif calls:
            fj_transport = _checkpoint(
                TraceAnswerState.NO,
                "PROVIDER_RESULT_WITHOUT_TRANSPORT_ATTEMPT",
                record_ids=(row.call_result.provider_call_id for row in calls),
            )
        elif fj_called.state == TraceAnswerState.NO:
            fj_transport = _checkpoint(
                TraceAnswerState.NOT_APPLICABLE, "FLUFFYJAWS_NOT_CALLED"
            )
        else:
            fj_transport = _checkpoint(
                TraceAnswerState.UNKNOWN, "PROVIDER_CALL_RESULT_NOT_RECORDED"
            )

        if calls:
            fj_status = _checkpoint(
                TraceAnswerState.YES,
                "PROVIDER_STATUS_RECORDED",
                record_ids=(row.call_result.provider_result_id for row in calls),
            )
        elif fj_called.state == TraceAnswerState.NO:
            fj_status = _checkpoint(
                TraceAnswerState.NOT_APPLICABLE, "FLUFFYJAWS_NOT_CALLED"
            )
        else:
            fj_status = _checkpoint(
                TraceAnswerState.UNKNOWN, "PROVIDER_CALL_RESULT_NOT_RECORDED"
            )

        if fj_accepted_ids or synthesis_ids:
            fj_results = _checkpoint(
                TraceAnswerState.YES,
                "PROVIDER_RESULTS_RECORDED",
                record_ids=tuple(sorted(fj_accepted_ids | synthesis_ids)),
            )
        elif calls:
            fj_results = _checkpoint(
                TraceAnswerState.NO, "PROVIDER_RETURNED_NO_ACCEPTED_RESULTS"
            )
        elif fj_called.state == TraceAnswerState.NO:
            fj_results = _checkpoint(
                TraceAnswerState.NOT_APPLICABLE, "FLUFFYJAWS_NOT_CALLED"
            )
        else:
            fj_results = _checkpoint(
                TraceAnswerState.UNKNOWN, "PROVIDER_CALL_RESULT_NOT_RECORDED"
            )

        if fj_evidence:
            source_identity_ids = {
                row.evidence_id for row in fj_evidence if row.source_identity_available
            }
            if len(source_identity_ids) == len(fj_evidence):
                underlying_sources = _checkpoint(
                    TraceAnswerState.YES,
                    "UNDERLYING_SOURCE_IDENTITIES_REDACTED",
                    record_ids=source_identity_ids,
                )
            elif source_identity_ids:
                underlying_sources = _checkpoint(
                    TraceAnswerState.PARTIAL,
                    "UNDERLYING_SOURCE_IDENTITIES_PARTIAL",
                    record_ids=source_identity_ids,
                )
            else:
                underlying_sources = _checkpoint(
                    TraceAnswerState.NO,
                    "UNDERLYING_SOURCE_IDENTITY_ABSENT",
                )
            normalized = _checkpoint(
                TraceAnswerState.YES,
                "PROVIDER_EVIDENCE_NORMALIZED",
                *(
                    ("LOCAL_EVIDENCE_CANONICALIZED",)
                    if local_evidence
                    else ()
                ),
                record_ids=(
                    row.evidence_id for row in local_evidence + fj_evidence
                ),
            )
        elif local_evidence:
            underlying_sources = _checkpoint(
                TraceAnswerState.NOT_APPLICABLE, "FLUFFYJAWS_RETURNED_NO_SOURCE"
            )
            normalized = _checkpoint(
                TraceAnswerState.YES,
                "LOCAL_EVIDENCE_CANONICALIZED",
                record_ids=(row.evidence_id for row in local_evidence),
            )
        elif synthesis_ids:
            underlying_sources = _checkpoint(
                TraceAnswerState.NO, "DISCOVERY_SYNTHESIS_HAS_NO_UNDERLYING_SOURCE"
            )
            normalized = _checkpoint(
                TraceAnswerState.NO, "DISCOVERY_SYNTHESIS_NOT_CANONICAL_EVIDENCE"
            )
        elif fj_results.state == TraceAnswerState.NOT_APPLICABLE:
            underlying_sources = _checkpoint(
                TraceAnswerState.NOT_APPLICABLE, "FLUFFYJAWS_NOT_CALLED"
            )
            normalized = _checkpoint(
                TraceAnswerState.NOT_APPLICABLE, "FLUFFYJAWS_NOT_CALLED"
            )
        elif calls:
            underlying_sources = _checkpoint(
                TraceAnswerState.NO, "NO_ACCEPTED_UNDERLYING_SOURCE"
            )
            normalized = _checkpoint(
                TraceAnswerState.NO, "NO_PROVIDER_EVIDENCE_NORMALIZED"
            )
        else:
            underlying_sources = _checkpoint(
                TraceAnswerState.UNKNOWN, "PROVIDER_CALL_RESULT_NOT_RECORDED"
            )
            normalized = _checkpoint(
                TraceAnswerState.UNKNOWN, "PROVIDER_CALL_RESULT_NOT_RECORDED"
            )

        if local is None:
            local_executed = _checkpoint(
                TraceAnswerState.UNKNOWN, "LOCAL_RETRIEVAL_RECORD_UNAVAILABLE"
            )
            local_results = _checkpoint(
                TraceAnswerState.UNKNOWN, "LOCAL_RETRIEVAL_RECORD_UNAVAILABLE"
            )
        else:
            local_executed = _checkpoint(
                TraceAnswerState.YES,
                "LOCAL_RETRIEVAL_RECORD_RETAINED",
                record_ids=(local.retrieval_id,),
            )
            if local.status == RetrievalStatus.USED:
                local_results = _checkpoint(
                    TraceAnswerState.YES if local_ids else TraceAnswerState.NO,
                    "LOCAL_RESULTS_MATCHED" if local_ids else "LOCAL_RESULTS_EMPTY",
                    record_ids=local_ids,
                )
            elif local.status == RetrievalStatus.REJECTED:
                local_results = _checkpoint(
                    TraceAnswerState.NO,
                    "LOCAL_RESULTS_REJECTED",
                    record_ids=local_ids,
                )
            else:
                local_results = _checkpoint(
                    TraceAnswerState.NO,
                    "LOCAL_RESULTS_UNAVAILABLE",
                    record_ids=local_ids,
                )

        if not question_hypotheses:
            verifier_usage = _checkpoint(
                TraceAnswerState.NOT_APPLICABLE, "NO_HYPOTHESIS_CREATED"
            )
            hypothesis_created = _checkpoint(
                TraceAnswerState.NO, "NO_HYPOTHESIS_RECORDED"
            )
            disposition = _checkpoint(
                TraceAnswerState.NO, "NO_HYPOTHESIS_OR_CANDIDATE_DISPOSITION"
            )
            coverage_linkage = _checkpoint(
                TraceAnswerState.NOT_APPLICABLE, "NO_HYPOTHESIS_CREATED"
            )
        else:
            missing_verifier_links = verifier_cited_ids - {
                row.evidence_id for row in local_evidence + fj_evidence
            }
            if missing_verifier_links:
                verifier_usage = _checkpoint(
                    TraceAnswerState.UNKNOWN,
                    "VERIFIER_EVIDENCE_LINKAGE_INCOMPLETE",
                    record_ids=verifier_cited_ids,
                )
            else:
                verifier_usage = _checkpoint(
                    TraceAnswerState.YES
                    if permitted_verifier_used_ids
                    else TraceAnswerState.NO,
                    "VERIFIER_CITED_EVIDENCE"
                    if permitted_verifier_used_ids
                    else "VERIFIER_CITED_NO_EVIDENCE",
                    record_ids=permitted_verifier_used_ids,
                )
            hypothesis_created = _checkpoint(
                TraceAnswerState.YES,
                "HYPOTHESIS_DERIVED_FROM_QUESTION_ID",
                record_ids=(row.hypothesis_id for row in question_hypotheses),
            )
            disposition = _checkpoint(
                TraceAnswerState.UNKNOWN,
                "HYPOTHESIS_STATE_IS_NOT_COVERAGE_DISPOSITION",
                record_ids=(row.hypothesis_id for row in question_hypotheses),
            )
            coverage_linkage = _checkpoint(
                TraceAnswerState.UNKNOWN,
                "HYPOTHESIS_TO_COVERAGE_DISPOSITION_ID_NOT_RETAINED",
            )

        promoted_candidate_ids = {
            row.candidate_id
            for row in candidate_summaries
            if row.promotion_status is not None and row.resulting_disposition is not None
        }
        linked_disposition_ids = {
            row.disposition_id for row in linked_dispositions
        }
        if linked_disposition_ids:
            disposition = _checkpoint(
                TraceAnswerState.YES,
                "HYPOTHESIS_COVERAGE_DISPOSITION_RECORDED",
                record_ids=linked_disposition_ids,
            )
            coverage_linkage = _checkpoint(
                TraceAnswerState.YES,
                "HYPOTHESIS_TO_COVERAGE_DISPOSITION_ID_RETAINED",
                record_ids=linked_disposition_ids,
            )
        elif promoted_candidate_ids:
            disposition = _checkpoint(
                TraceAnswerState.YES,
                "CANDIDATE_PROMOTION_RESULT_RECORDED",
                record_ids=promoted_candidate_ids,
            )
            coverage_linkage = _checkpoint(
                TraceAnswerState.YES,
                "QUESTION_UNRESOLVED_DECISION_TO_CANDIDATE",
                record_ids=promoted_candidate_ids,
            )
        elif candidate_summaries:
            disposition = _checkpoint(
                TraceAnswerState.UNKNOWN,
                "CANDIDATE_PROMOTION_RESULT_NOT_RETAINED",
                record_ids=(row.candidate_id for row in candidate_summaries),
            )
            coverage_linkage = _checkpoint(
                TraceAnswerState.YES,
                "QUESTION_UNRESOLVED_DECISION_TO_CANDIDATE",
                record_ids=(row.candidate_id for row in candidate_summaries),
            )

        candidate_ids = {row.candidate_id for row in linked_candidates}
        locations = _output_locations(
            structured_plan,
            question_id=question.question_id,
            candidate_ids=candidate_ids,
            disposition_ids=linked_disposition_ids,
        )
        question_locations = [
            row for row in locations if row.source_record_id == question.question_id
        ]
        disposition_locations = [
            row for row in locations if row.record_type == "DISPOSITION"
        ]
        if question_locations:
            output_location = _checkpoint(
                TraceAnswerState.YES,
                "QUESTION_SECTION_LOCATION_RECORDED",
                record_ids=(row.source_record_id for row in question_locations),
            )
        elif disposition_locations:
            output_location = _checkpoint(
                TraceAnswerState.YES,
                "QUESTION_LINKED_DISPOSITION_SECTION_LOCATION_RECORDED",
                record_ids=(row.source_record_id for row in disposition_locations),
            )
        elif locations:
            output_location = _checkpoint(
                TraceAnswerState.YES,
                "QUESTION_LINKED_CANDIDATE_SECTION_LOCATION_RECORDED",
                record_ids=(row.source_record_id for row in locations),
            )
        elif structured_plan is None:
            output_location = _checkpoint(
                TraceAnswerState.UNKNOWN, "FINAL_PLAN_NOT_AVAILABLE"
            )
        else:
            output_location = _checkpoint(
                TraceAnswerState.NO, "QUESTION_NOT_LINKED_TO_FINAL_PLAN_SECTION"
            )

        all_evidence = tuple(
            sorted(
                {row.evidence_id: row for row in local_evidence + fj_evidence}.values(),
                key=lambda row: row.evidence_id,
            )
        )
        question_source_ids = tuple(
            sorted(set(question.source_closure_ids + question.source_fact_ids))
        )
        generation_lineage = (
            _checkpoint(
                TraceAnswerState.YES,
                "QUESTION_SOURCE_RECORD_IDS_RETAINED",
                record_ids=question_source_ids,
            )
            if question_source_ids
            else _checkpoint(
                TraceAnswerState.UNKNOWN,
                "QUESTION_SOURCE_RECORD_IDS_NOT_RETAINED",
            )
        )
        output.append(
            QuestionEndToEndTrace(
                question_id=question.question_id,
                dimension=dimension,
                authority_subject=question.authority_subject.value,
                materiality=(
                    calls[0].materiality
                    if calls
                    else QueryMateriality.P0
                    if question.blocking
                    else QueryMateriality.P1
                ),
                blocking=question.blocking,
                local_result_status=local.status if local is not None else None,
                question_generated=_checkpoint(
                    TraceAnswerState.YES,
                    "MISSING_QUESTION_GENERATOR_OUTPUT",
                    record_ids=(question.question_id,),
                ),
                why_generated=_checkpoint(
                    generation_state, generation_reason
                ),
                generation_lineage=generation_lineage,
                local_retrieval_executed=local_executed,
                local_results=local_results,
                fluffyjaws_called=fj_called,
                fluffyjaws_transport_executed=fj_transport,
                why_fluffyjaws=why_fj,
                fluffyjaws_status=fj_status,
                fluffyjaws_results=fj_results,
                underlying_sources=underlying_sources,
                evidence_normalized=normalized,
                evidence_used_by_verifier=verifier_usage,
                hypothesis_created=hypothesis_created,
                disposition=disposition,
                coverage_disposition_linkage=coverage_linkage,
                final_output_location=output_location,
                implementation_verification=implementation_checkpoint,
                local_retrieval_ids=(local.retrieval_id,) if local else (),
                query_ids=query_ids,
                provider_call_ids=tuple(
                    row.provider_call_id for row in provider_summaries
                ),
                evidence_ids=tuple(row.evidence_id for row in all_evidence),
                hypothesis_ids=tuple(
                    row.hypothesis_id for row in question_hypotheses
                ),
                disposition_ids=tuple(sorted(linked_disposition_ids)),
                candidate_ids=tuple(sorted(candidate_ids)),
                implementation_handoff_ids=tuple(
                    row.handoff_id for row in implementation_summaries
                ),
                implementation_result_ids=tuple(
                    row.result_id for row in implementation_summaries if row.result_id
                ),
                implementation_trace_ids=tuple(
                    row.trace_id for row in implementation_summaries
                ),
                local_evidence=local_evidence,
                fluffyjaws_evidence=fj_evidence,
                provider_calls=provider_summaries,
                hypotheses=tuple(
                    HypothesisTraceSummary(
                        hypothesis_id=row.hypothesis_id,
                        state=row.state,
                        supporting_evidence_ids=tuple(row.supporting_evidence_ids),
                        contradicting_evidence_ids=tuple(
                            row.contradicting_evidence_ids
                        ),
                        verification_evidence_ids=tuple(
                            row.verification_evidence_ids
                        ),
                    )
                    for row in question_hypotheses
                ),
                candidates=candidate_summaries,
                coverage_dispositions=disposition_summaries,
                output_locations=locations,
                implementation_verifications=implementation_summaries,
            )
        )

    return QuestionRetrievalTraceBundle(
        run_id=run_id,
        request_id=request.request_id,
        output_sha256=output_sha256,
        completion_state=completion_state,
        failed_stage=failed_stage,
        fluffyjaws_mode=fluffyjaws_mode,
        warning_codes=tuple(warning_codes),
        generated_question_count=len(output),
        generated_question_ids=tuple(row.question_id for row in output),
        questions=tuple(output),
    )


def record_question_retrieval_trace(
    *,
    run_id: str,
    request: GenerationRequest,
    output_sha256: str,
    completion_state: TraceCompletionState,
    failed_stage: CanonicalRuntimeStage | str | None = None,
    questions: Iterable[MissingQuestion] = (),
    local_retrievals: Iterable[DirectedRetrievalRecord] = (),
    hypotheses: Iterable[BehaviorHypothesis] = (),
    implementation_handoffs: Iterable[
        GitHubImplementationVerificationHandoff
    ] = (),
    implementation_results: Iterable[GitHubImplementationVerificationResult] = (),
    unresolved_implementation_handoff_ids: Iterable[str] = (),
    dispositions: Iterable[CoverageDispositionRecord] = (),
    candidates: Iterable[AcceptanceCandidate] = (),
    promotions: Iterable[AcceptancePromotionDecision] = (),
    structured_plan: StructuredQEPlan | None = None,
    evidence_records: Iterable[EvidenceRecord] = (),
    fluffyjaws_mode: FluffyJawsRuntimeMode,
    fluffyjaws_trace: FluffyJawsShadowRunTrace | None = None,
) -> QuestionRetrievalTraceBundle:
    """Build and retain an isolated deep snapshot for the current context."""

    trace = build_question_retrieval_trace(
        run_id=run_id,
        request=request,
        output_sha256=output_sha256,
        completion_state=completion_state,
        failed_stage=failed_stage,
        questions=questions,
        local_retrievals=local_retrievals,
        hypotheses=hypotheses,
        implementation_handoffs=implementation_handoffs,
        implementation_results=implementation_results,
        unresolved_implementation_handoff_ids=(
            unresolved_implementation_handoff_ids
        ),
        dispositions=dispositions,
        candidates=candidates,
        promotions=promotions,
        structured_plan=structured_plan,
        evidence_records=evidence_records,
        fluffyjaws_mode=fluffyjaws_mode,
        fluffyjaws_trace=fluffyjaws_trace,
    )
    _LAST_QUESTION_RETRIEVAL_TRACE.set(trace.model_copy(deep=True))
    return trace.model_copy(deep=True)


def render_question_debug_report(
    trace: QuestionRetrievalTraceBundle,
    question_id: str,
) -> str:
    """Render one content-free question journey as deterministic Markdown."""

    if re.fullmatch(_QUESTION_ID_PATTERN, question_id) is None:
        raise ValueError("question_id must be a canonical opaque question ID")
    question = next((row for row in trace.questions if row.question_id == question_id), None)
    if question is None:
        raise LookupError("question ID is not present in this trace")

    def checkpoint(label: str, value: TraceCheckpoint) -> str:
        reasons = ", ".join(value.reason_codes) or "none"
        records = ", ".join(value.record_ids) or "none"
        return f"- {label}: {value.state.value} | reasons={reasons} | records={records}"

    lines = [
        "# FluffyJaws question retrieval trace",
        "",
        "- Artifact authenticity: UNVERIFIED_CONTENT_HASH_ONLY",
        f"- Trace ID: {trace.trace_id}",
        f"- Run ID: {trace.run_id}",
        f"- Request ID: {trace.request_id}",
        "- Plan ID: unavailable (CANONICAL_PLAN_ID_NOT_DEFINED)",
        f"- Output SHA-256: {trace.output_sha256 or 'unavailable'}",
        f"- Completion: {trace.completion_state.value}",
        f"- Failed stage: {trace.failed_stage.value if trace.failed_stage else 'none'}",
        f"- Warning codes: {', '.join(trace.warning_codes) or 'none'}",
        f"- Generated question count: {trace.generated_question_count}",
        f"- FluffyJaws mode: {trace.fluffyjaws_mode.value}",
        f"- Question ID: {question.question_id}",
        f"- Materiality: {question.materiality.value}",
        f"- Dimension: {question.dimension.value if question.dimension else 'unclassified'}",
        f"- Authority subject: {question.authority_subject.value}",
        f"- Local result status: {question.local_result_status.value if question.local_result_status else 'unavailable'}",
        "",
        "## End-to-end checkpoints",
        "",
        checkpoint("QUESTION_GENERATED", question.question_generated),
        checkpoint("WHY_GENERATED", question.why_generated),
        checkpoint("GENERATION_LINEAGE", question.generation_lineage),
        checkpoint("LOCAL_RETRIEVAL_EXECUTED", question.local_retrieval_executed),
        checkpoint("LOCAL_RESULTS", question.local_results),
        checkpoint("FLUFFYJAWS_CALLED", question.fluffyjaws_called),
        checkpoint("FLUFFYJAWS_TRANSPORT_EXECUTED", question.fluffyjaws_transport_executed),
        checkpoint("WHY_FLUFFYJAWS", question.why_fluffyjaws),
        checkpoint("FLUFFYJAWS_STATUS", question.fluffyjaws_status),
        checkpoint("FLUFFYJAWS_RESULTS", question.fluffyjaws_results),
        checkpoint("UNDERLYING_SOURCES", question.underlying_sources),
        checkpoint("EVIDENCE_NORMALIZED", question.evidence_normalized),
        checkpoint("EVIDENCE_USED_BY_VERIFIER", question.evidence_used_by_verifier),
        checkpoint("HYPOTHESIS_CREATED", question.hypothesis_created),
        checkpoint("DISPOSITION", question.disposition),
        checkpoint("COVERAGE_DISPOSITION_LINKAGE", question.coverage_disposition_linkage),
        checkpoint("FINAL_OUTPUT_LOCATION", question.final_output_location),
        checkpoint(
            "GITHUB_IMPLEMENTATION_VERIFICATION",
            question.implementation_verification,
        ),
        "",
        "## Identifiers",
        "",
        f"- Local retrieval IDs: {', '.join(question.local_retrieval_ids) or 'none'}",
        f"- Query IDs: {', '.join(question.query_ids) or 'none'}",
        f"- Provider call IDs: {', '.join(question.provider_call_ids) or 'none'}",
        f"- Evidence IDs: {', '.join(question.evidence_ids) or 'none'}",
        f"- Hypothesis IDs: {', '.join(question.hypothesis_ids) or 'none'}",
        f"- Disposition IDs: {', '.join(question.disposition_ids) or 'unavailable'}",
        f"- Candidate IDs: {', '.join(question.candidate_ids) or 'none'}",
        f"- GitHub handoff IDs: {', '.join(question.implementation_handoff_ids) or 'none'}",
        f"- GitHub result IDs: {', '.join(question.implementation_result_ids) or 'none'}",
        f"- Implementation trace IDs: {', '.join(question.implementation_trace_ids) or 'none'}",
        "",
        "## Evidence and source state",
        "",
    ]
    evidence_rows = question.local_evidence + question.fluffyjaws_evidence
    if evidence_rows:
        for evidence in evidence_rows:
            lines.append(
                "- "
                f"{evidence.evidence_id}: origin={evidence.origin.value}, "
                f"source_type={evidence.source_type.value}, "
                f"authority={evidence.authority_class.value}, "
                f"currentness={evidence.currentness.value}, "
                f"verification={evidence.verification_status.value}, "
                f"source_identity={str(evidence.source_identity_available).lower()}, "
                f"citation={evidence.citation_disclosure.value}, "
                f"normalized={str(evidence.normalized).lower()}, "
                f"verifier_used={str(evidence.used_by_verifier).lower()}, "
                f"fusion={evidence.semantic_fusion_state.value}, "
                f"stance={evidence.semantic_stance.value if evidence.semantic_stance else 'none'}, "
                f"rejection={evidence.semantic_rejection_code or 'none'}, "
                f"provenance_count={len(evidence.provenance_ids)}"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Hypotheses", ""])
    if question.hypotheses:
        for hypothesis in question.hypotheses:
            lines.append(
                "- "
                f"{hypothesis.hypothesis_id}: state={hypothesis.state.value}, "
                f"supporting={','.join(hypothesis.supporting_evidence_ids) or 'none'}, "
                f"contradicting={','.join(hypothesis.contradicting_evidence_ids) or 'none'}"
                f", verification={','.join(hypothesis.verification_evidence_ids) or 'none'}"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## GitHub implementation verification", ""])
    if question.implementation_verifications:
        for verification in question.implementation_verifications:
            lines.append(
                "- "
                f"{verification.handoff_id}: result={verification.result_id or 'none'}, "
                f"trace={verification.trace_id}, "
                f"status={verification.status.value if verification.status else 'pending'}, "
                f"unresolved={str(verification.unresolved).lower()}"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Candidate and disposition", ""])
    if question.coverage_dispositions:
        for disposition in question.coverage_dispositions:
            lines.append(
                "- "
                f"{disposition.disposition_id}: "
                f"disposition={disposition.disposition.value}, "
                "linkage=QUESTION_OR_HYPOTHESIS_ID"
            )
    if question.candidates:
        for candidate in question.candidates:
            lines.append(
                "- "
                f"{candidate.candidate_id}: "
                f"promotion={candidate.promotion_status.value if candidate.promotion_status else 'unavailable'}, "
                f"disposition={candidate.resulting_disposition.value if candidate.resulting_disposition else 'unavailable'}, "
                f"linkage={candidate.linkage_basis}"
            )
    elif not question.coverage_dispositions:
        lines.append("- none")
    lines.extend(
        [
            "",
        "## Provider calls",
        "",
        ]
    )
    if question.provider_calls:
        for call in question.provider_calls:
            lines.append(
                "- "
                f"{call.provider_call_id}: provider={call.provider}, "
                f"status={call.status.value}, transport={call.transport_outcome.value}, "
                f"attempts={call.attempts}, duration_ms={call.duration_ms}, "
                f"attempt_outcomes={','.join(row.value for row in call.attempt_outcomes) or 'none'}, "
                f"cache={call.cache_state.value}, circuit="
                f"{call.circuit_state_before.value}->{call.circuit_state_after.value}, "
                f"accepted={len(call.accepted_evidence_ids)}, "
                f"rejected_hits={call.rejected_hit_count}, "
                f"normalization={','.join(f'{key}:{value}' for key, value in call.hit_disposition_reason_counts.items()) or 'none'}, "
                f"syntheses={len(call.synthesis_ids)}, "
                f"fusion_evaluated={str(call.semantic_fusion_evaluated).lower()}, "
                f"fused={len(call.fused_evidence_ids)}, "
                f"consumed={len(call.consumed_evidence_ids)}, "
                f"semantic_rejections={','.join(f'{key}:{value}' for key, value in call.semantic_rejection_counts.items()) or 'none'}, "
                f"stances={','.join(f'{key}:{value}' for key, value in call.semantic_stance_counts.items()) or 'none'}, "
                f"attestations={call.source_attestation_count}, "
                f"assessments={call.question_assessment_count}, "
                f"authorizations={call.semantic_authorization_count}, "
                f"error_code={call.safe_error_code or 'none'}"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Final output locations", ""])
    if question.output_locations:
        for location in question.output_locations:
            lines.append(
                f"- {location.source_record_id}: {location.structured_path} "
                f"({location.granularity})"
            )
    else:
        lines.append("- none")
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "QUESTION_RETRIEVAL_TRACE_SCHEMA",
    "CandidateTraceSummary",
    "CitationDisclosureState",
    "CoverageDispositionTraceSummary",
    "FinalOutputLocation",
    "HypothesisTraceSummary",
    "ImplementationVerificationTraceSummary",
    "ProviderCallTraceSummary",
    "QuestionEndToEndTrace",
    "QuestionRetrievalTraceBundle",
    "TraceAnswerState",
    "TraceCheckpoint",
    "TraceCompletionState",
    "TraceEvidenceOrigin",
    "TraceEvidenceReference",
    "TraceSemanticFusionState",
    "build_question_retrieval_trace",
    "clear_last_question_retrieval_trace",
    "get_last_question_retrieval_trace",
    "record_question_retrieval_trace",
    "render_question_debug_report",
]
