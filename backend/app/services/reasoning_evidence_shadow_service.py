"""Bounded FluffyJaws retrieval for the canonical test-plan runtime.

SHADOW remains trace-only.  SECOND_PASS uses the conservative FJ-07 routing
policy and may return independently attested underlying-source evidence to the
canonical retriever.  Provider synthesis never enters the semantic bundle.
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from datetime import datetime, timezone
from enum import StrEnum
from time import monotonic
from typing import Any, Callable, Iterable, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.schemas_canonical_test_plan_runtime import (
    CANONICAL_RUNTIME_ID,
    CANONICAL_RUNTIME_VERSION,
    ApplicabilityState,
    AuthorityClass,
    AuthorityResolution,
    CanonicalEvidenceBundle,
    CurrentnessState,
    DirectedRetrievalRecord,
    DomainActivation,
    EvidenceLifecycleStatus,
    EvidenceRecord,
    EvidenceSourceType,
    GenerationRequest,
    IssueDomain,
    MissingQuestion,
    RetrievalStatus,
    RuntimePrincipal,
    ScopeResolution,
    VerificationState,
    VersionScope,
    stable_sha256,
)
from app.services.canonical_evidence_service import (
    build_bundle,
    record_visible_to,
    redacted_trace_payload,
)
from app.services.fluffyjaws_routing_policy import (
    ConservativeFluffyJawsRoutingPolicy,
    FluffyJawsNoCallReason,
    FluffyJawsRoutingBudget,
    FluffyJawsRoutingEvaluation,
    FluffyJawsRoutingRecord,
    build_fluffyjaws_routing_record,
)
from app.services.reasoning_evidence_provider import (
    AuthorizedSemanticEvidence,
    AuthorityRequirement,
    DiscoverySynthesis,
    EvidenceProvider,
    EvidenceProviderCallResult,
    EvidenceProviderExecutionContext,
    EvidenceProviderExecutor,
    EvidenceProviderRegistry,
    EvidenceProviderStatus,
    EvidenceProviderTraceSidecar,
    EvidenceQueryV1,
    ExcludedSources,
    ProviderCacheState,
    ProviderCircuitState,
    ProviderHitDisposition,
    ProviderExecutionResult,
    ProviderTransportOutcome,
    QuestionEvidenceStance,
    QueryMateriality,
    RetrievalProvenance,
    SOURCE_ATTESTATION_SCHEMA,
    SemanticEvidenceAuthorization,
    SemanticEvidenceBinding,
    SourceNativeEvidenceAttestation,
    TemporalBoundary,
)
from app.services.reasoning_evidence_resilience import (
    EvidenceProviderResilienceController,
    ProviderResiliencePolicy,
)


FLUFFYJAWS_MODE_ENV = "FLUFFYJAWS_MODE"
FLUFFYJAWS_SHADOW_MAX_QUESTIONS_ENV = "FLUFFYJAWS_SHADOW_MAX_QUESTIONS"
FLUFFYJAWS_SHADOW_MAX_RESULTS_ENV = "FLUFFYJAWS_SHADOW_MAX_RESULTS"
FLUFFYJAWS_SHADOW_CALL_TIMEOUT_ENV = "FLUFFYJAWS_SHADOW_CALL_TIMEOUT_SECONDS"
FLUFFYJAWS_SHADOW_TOTAL_TIMEOUT_ENV = "FLUFFYJAWS_SHADOW_TOTAL_TIMEOUT_SECONDS"
FLUFFYJAWS_RETRY_MAX_ATTEMPTS_ENV = "FLUFFYJAWS_RETRY_MAX_ATTEMPTS"
FLUFFYJAWS_CACHE_ENABLED_ENV = "FLUFFYJAWS_CACHE_ENABLED"
FLUFFYJAWS_CACHE_TTL_ENV = "FLUFFYJAWS_CACHE_TTL_SECONDS"
FLUFFYJAWS_CACHE_MAX_ENTRIES_ENV = "FLUFFYJAWS_CACHE_MAX_ENTRIES"
FLUFFYJAWS_CACHE_MAX_BYTES_ENV = "FLUFFYJAWS_CACHE_MAX_BYTES"
FLUFFYJAWS_CIRCUIT_FAILURE_THRESHOLD_ENV = (
    "FLUFFYJAWS_CIRCUIT_FAILURE_THRESHOLD"
)
FLUFFYJAWS_CIRCUIT_COOLDOWN_ENV = "FLUFFYJAWS_CIRCUIT_COOLDOWN_SECONDS"
FLUFFYJAWS_CIRCUIT_MAX_ENTRIES_ENV = "FLUFFYJAWS_CIRCUIT_MAX_ENTRIES"
FLUFFYJAWS_SHADOW_TRACE_SCHEMA = "aem-guides-fluffyjaws-shadow-run-v4"
REASONING_EVIDENCE_SEMANTIC_BATCH_SCHEMA = (
    "aem-guides-reasoning-evidence-semantic-batch-v1"
)

_ERROR_STATUSES = {
    EvidenceProviderStatus.TIMEOUT,
    EvidenceProviderStatus.AUTH_ERROR,
    EvidenceProviderStatus.RATE_LIMITED,
    EvidenceProviderStatus.PROVIDER_ERROR,
    EvidenceProviderStatus.INVALID_RESPONSE,
}
_TARGET_HUMAN_SOURCE_TYPES = {
    EvidenceSourceType.JIRA_DESCRIPTION,
    EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA,
    EvidenceSourceType.ACCEPTED_UAC,
    EvidenceSourceType.PRODUCT_DECISION,
    EvidenceSourceType.ENGINEERING_DECISION,
    EvidenceSourceType.USER_FEEDBACK,
    EvidenceSourceType.CURRENT_JIRA,
    EvidenceSourceType.DRAFT_UAC,
}
_SEMANTIC_AUTHORITY_CLASSES = {
    AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
    AuthorityClass.SPECIFICATION_AUTHORITY,
    AuthorityClass.IMPLEMENTATION_CONFIRMED,
}
_SEMANTIC_CURRENTNESS_ALLOWED = {
    CurrentnessState.CURRENT,
    CurrentnessState.VERSION_SPECIFIC,
    CurrentnessState.ENVIRONMENT_SPECIFIC,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("attestation timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _never_cancelled() -> bool:
    return False


def _deny_unverified_source(_value: Any) -> bool:
    return False


def _deny_query_egress(
    _query: EvidenceQueryV1,
    _request: GenerationRequest,
) -> bool:
    return False


def _deny_semantic_evidence_authorization(
    _record: EvidenceRecord,
    _provenance: RetrievalProvenance,
    _disposition: ProviderHitDisposition,
    _query: EvidenceQueryV1,
    _binding: SemanticEvidenceBinding,
) -> None:
    return None


class FluffyJawsRuntimeMode(StrEnum):
    FLUFFYJAWS_DISABLED = "FLUFFYJAWS_DISABLED"
    FLUFFYJAWS_SHADOW = "FLUFFYJAWS_SHADOW"
    FLUFFYJAWS_SECOND_PASS = "FLUFFYJAWS_SECOND_PASS"


class FluffyJawsShadowConfig(BaseModel):
    """Non-secret, centrally resolved provider-capture configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: FluffyJawsRuntimeMode = FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED
    max_questions: int = Field(default=20, ge=1, le=50)
    max_results: int = Field(default=5, ge=1, le=100)
    call_timeout_seconds: float = Field(default=300.0, gt=0.0, le=300.0)
    total_timeout_seconds: float = Field(default=300.0, gt=0.0, le=900.0)
    retry_max_attempts: int = Field(default=2, ge=1, le=3)
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

    @property
    def shadow_enabled(self) -> bool:
        return self.mode == FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW

    @property
    def provider_capture_enabled(self) -> bool:
        return self.mode in {
            FluffyJawsRuntimeMode.FLUFFYJAWS_SHADOW,
            FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS,
        }

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "FluffyJawsShadowConfig":
        source = os.environ if environment is None else environment
        payload: dict[str, Any] = {}
        if FLUFFYJAWS_MODE_ENV in source:
            raw_mode = str(source[FLUFFYJAWS_MODE_ENV]).strip()
            if not raw_mode:
                raise ValueError(f"{FLUFFYJAWS_MODE_ENV} cannot be blank")
            try:
                payload["mode"] = FluffyJawsRuntimeMode(raw_mode)
            except ValueError as exc:
                allowed = ", ".join(mode.value for mode in FluffyJawsRuntimeMode)
                raise ValueError(
                    f"{FLUFFYJAWS_MODE_ENV} must be one of: {allowed}"
                ) from exc
        numeric_fields: tuple[tuple[str, str, type[int] | type[float]], ...] = (
            (FLUFFYJAWS_SHADOW_MAX_QUESTIONS_ENV, "max_questions", int),
            (FLUFFYJAWS_SHADOW_MAX_RESULTS_ENV, "max_results", int),
            (FLUFFYJAWS_SHADOW_CALL_TIMEOUT_ENV, "call_timeout_seconds", float),
            (FLUFFYJAWS_SHADOW_TOTAL_TIMEOUT_ENV, "total_timeout_seconds", float),
            (FLUFFYJAWS_RETRY_MAX_ATTEMPTS_ENV, "retry_max_attempts", int),
            (FLUFFYJAWS_CACHE_TTL_ENV, "cache_ttl_seconds", float),
            (FLUFFYJAWS_CACHE_MAX_ENTRIES_ENV, "cache_max_entries", int),
            (FLUFFYJAWS_CACHE_MAX_BYTES_ENV, "cache_max_bytes", int),
            (
                FLUFFYJAWS_CIRCUIT_FAILURE_THRESHOLD_ENV,
                "circuit_failure_threshold",
                int,
            ),
            (
                FLUFFYJAWS_CIRCUIT_COOLDOWN_ENV,
                "circuit_cooldown_seconds",
                float,
            ),
            (FLUFFYJAWS_CIRCUIT_MAX_ENTRIES_ENV, "circuit_max_entries", int),
        )
        for environment_key, field_name, parser in numeric_fields:
            if environment_key not in source:
                continue
            raw_value = str(source[environment_key]).strip()
            if not raw_value:
                raise ValueError(f"{environment_key} cannot be blank")
            try:
                payload[field_name] = parser(raw_value)
            except ValueError as exc:
                raise ValueError(f"{environment_key} has an invalid numeric value") from exc
        if FLUFFYJAWS_CACHE_ENABLED_ENV in source:
            raw_cache_enabled = str(source[FLUFFYJAWS_CACHE_ENABLED_ENV]).strip().casefold()
            if raw_cache_enabled not in {"true", "false"}:
                raise ValueError(
                    f"{FLUFFYJAWS_CACHE_ENABLED_ENV} must be true or false"
                )
            payload["cache_enabled"] = raw_cache_enabled == "true"
        return cls.model_validate(payload)


class FluffyJawsShadowMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_call_count: int = Field(default=0, ge=0)
    logical_call_count: int = Field(default=0, ge=0)
    recorded_call_count: int = Field(default=0, ge=0)
    internal_error_count: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    cache_hit_count: int = Field(default=0, ge=0)
    cache_stale_count: int = Field(default=0, ge=0)
    circuit_open_count: int = Field(default=0, ge=0)
    suppressed_call_count: int = Field(default=0, ge=0)
    success_count: int = Field(default=0, ge=0)
    empty_count: int = Field(default=0, ge=0)
    partial_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
    status_counts: dict[str, int] = Field(default_factory=dict)
    total_latency_ms: int = Field(default=0, ge=0)
    minimum_latency_ms: int = Field(default=0, ge=0)
    maximum_latency_ms: int = Field(default=0, ge=0)
    mean_latency_ms: float = Field(default=0.0, ge=0.0)
    source_count: int = Field(default=0, ge=0)
    citation_count: int = Field(default=0, ge=0)
    overlap_with_local_retrieval_count: int = Field(default=0, ge=0)
    unique_evidence_count: int = Field(default=0, ge=0)
    accepted_evidence_count: int = Field(default=0, ge=0)
    synthesis_count: int = Field(default=0, ge=0)
    discovery_success_count: int = Field(default=0, ge=0)
    synthesis_only_call_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> "FluffyJawsShadowMetrics":
        if self.logical_call_count != (
            self.recorded_call_count + self.internal_error_count
        ):
            raise ValueError(
                "logical calls must equal recorded calls plus internal errors"
            )
        if self.status_counts and sum(self.status_counts.values()) != (
            self.logical_call_count
        ):
            raise ValueError("provider status counts must equal logical calls")
        if self.suppressed_call_count > self.recorded_call_count:
            raise ValueError("suppressed calls cannot exceed recorded calls")
        if self.cache_hit_count > self.recorded_call_count:
            raise ValueError("cache hits cannot exceed recorded calls")
        expected_error_count = sum(
            self.status_counts.get(status.value, 0) for status in _ERROR_STATUSES
        )
        if self.error_count != expected_error_count:
            raise ValueError("provider error count does not match status counts")
        for status, count in (
            (EvidenceProviderStatus.SUCCESS, self.success_count),
            (EvidenceProviderStatus.EMPTY, self.empty_count),
            (EvidenceProviderStatus.PARTIAL, self.partial_count),
        ):
            if count != self.status_counts.get(status.value, 0):
                raise ValueError(f"{status.value} count does not match status counts")
        if self.discovery_success_count > self.recorded_call_count:
            raise ValueError("discovery successes cannot exceed recorded calls")
        if self.synthesis_only_call_count > self.discovery_success_count:
            raise ValueError(
                "synthesis-only calls cannot exceed discovery successes"
            )
        return self


class FluffyJawsShadowCallTrace(BaseModel):
    """Sanitized result slice for one shadow provider call."""

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1)
    materiality: QueryMateriality
    query: EvidenceQueryV1
    local_matched_evidence_ids: list[str] = Field(default_factory=list)
    overlap_evidence_ids: list[str] = Field(default_factory=list)
    unique_evidence_ids: list[str] = Field(default_factory=list)
    call_result: EvidenceProviderCallResult
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)
    provenance: list[RetrievalProvenance] = Field(default_factory=list)
    hit_dispositions: list[ProviderHitDisposition] = Field(default_factory=list)
    discovery_syntheses: list[DiscoverySynthesis] = Field(default_factory=list)
    trace_sidecar: EvidenceProviderTraceSidecar
    semantic_fusion_evaluated: bool = False
    semantic_fusion_evidence_ids: list[str] = Field(default_factory=list)
    semantic_fusion_rejections: dict[str, str] = Field(default_factory=dict)
    source_attestation_ids: list[str] = Field(default_factory=list)
    question_assessment_ids: list[str] = Field(default_factory=list)
    semantic_authorization_ids: list[str] = Field(default_factory=list)
    semantic_stances: dict[str, QuestionEvidenceStance] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def validate_linkage(self) -> "FluffyJawsShadowCallTrace":
        self.local_matched_evidence_ids = sorted(
            set(self.local_matched_evidence_ids)
        )
        self.overlap_evidence_ids = sorted(set(self.overlap_evidence_ids))
        self.unique_evidence_ids = sorted(set(self.unique_evidence_ids))
        evidence_ids = {record.evidence_id for record in self.evidence_records}
        accepted_ids = set(self.call_result.accepted_evidence_ids)
        if evidence_ids != accepted_ids:
            raise ValueError("shadow evidence must equal accepted provider evidence")
        if not set(self.overlap_evidence_ids).issubset(accepted_ids):
            raise ValueError("shadow overlap must reference accepted evidence")
        if not set(self.unique_evidence_ids).issubset(accepted_ids):
            raise ValueError("shadow unique evidence must reference accepted evidence")
        if set(self.overlap_evidence_ids) & set(self.unique_evidence_ids):
            raise ValueError("shadow overlap and unique evidence cannot intersect")
        if set(self.overlap_evidence_ids) | set(self.unique_evidence_ids) != accepted_ids:
            raise ValueError("shadow overlap and unique evidence must partition accepted evidence")
        self.semantic_fusion_evidence_ids = sorted(
            set(self.semantic_fusion_evidence_ids)
        )
        self.source_attestation_ids = sorted(set(self.source_attestation_ids))
        self.question_assessment_ids = sorted(set(self.question_assessment_ids))
        self.semantic_authorization_ids = sorted(
            set(self.semantic_authorization_ids)
        )
        self.semantic_stances = {
            key: self.semantic_stances[key] for key in sorted(self.semantic_stances)
        }
        self.semantic_fusion_rejections = {
            key: self.semantic_fusion_rejections[key]
            for key in sorted(self.semantic_fusion_rejections)
        }
        semantic_ids = set(self.semantic_fusion_evidence_ids)
        rejected_ids = set(self.semantic_fusion_rejections)
        if not semantic_ids.issubset(accepted_ids) or not rejected_ids.issubset(
            accepted_ids
        ):
            raise ValueError("semantic fusion decisions must reference accepted evidence")
        if semantic_ids & rejected_ids:
            raise ValueError("semantic fusion and rejection IDs cannot intersect")
        if self.semantic_fusion_evaluated:
            if semantic_ids | rejected_ids != accepted_ids:
                raise ValueError(
                    "semantic fusion decisions must partition accepted evidence"
                )
        if not set(self.semantic_stances).issubset(accepted_ids):
            raise ValueError("semantic stances must reference accepted evidence")
        if not self.semantic_fusion_evaluated and (
            semantic_ids
            or rejected_ids
            or self.source_attestation_ids
            or self.question_assessment_ids
            or self.semantic_authorization_ids
            or self.semantic_stances
        ):
            raise ValueError("unevaluated calls cannot contain semantic fusion decisions")
        return self


class FluffyJawsShadowRunTrace(BaseModel):
    """Separate operational sidecar; never part of public runtime v2 output."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-fluffyjaws-shadow-run-v4"] = (
        FLUFFYJAWS_SHADOW_TRACE_SCHEMA
    )
    mode: FluffyJawsRuntimeMode
    runtime_id: Literal["aem-guides-test-plan-runtime"] = CANONICAL_RUNTIME_ID
    runtime_version: Literal["2.0.0"] = CANONICAL_RUNTIME_VERSION
    run_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    evidence_bundle_id: str = Field(min_length=1)
    started_at: str
    completed_at: str
    state: Literal[
        "SHADOW_COMPLETED",
        "SHADOW_PARTIAL",
        "SECOND_PASS_COMPLETED",
        "SECOND_PASS_PARTIAL",
        "CONFIG_UNAVAILABLE",
        "BLIND_REPLAY_BLOCKED",
    ]
    eligible_question_ids: list[str] = Field(default_factory=list)
    dispatched_question_ids: list[str] = Field(default_factory=list)
    skipped_question_ids: list[str] = Field(default_factory=list)
    skip_reasons: dict[str, str] = Field(default_factory=dict)
    warning_codes: list[str] = Field(default_factory=list)
    routing_records: list[FluffyJawsRoutingRecord] = Field(default_factory=list)
    calls: list[FluffyJawsShadowCallTrace] = Field(default_factory=list)
    fused_bundle_id: str = ""
    fused_evidence_ids: list[str] = Field(default_factory=list)
    fused_evidence_ids_by_question: dict[str, list[str]] = Field(default_factory=dict)
    fused_question_stances: dict[str, dict[str, QuestionEvidenceStance]] = Field(
        default_factory=dict
    )
    fused_authority_conflicts: list[AuthorityResolution] = Field(default_factory=list)
    fused_currentness_conflicts: list[str] = Field(default_factory=list)
    consumed_evidence_ids: list[str] = Field(default_factory=list)
    metrics: FluffyJawsShadowMetrics = Field(default_factory=FluffyJawsShadowMetrics)

    @model_validator(mode="after")
    def normalize_sets(self) -> "FluffyJawsShadowRunTrace":
        self.eligible_question_ids = sorted(set(self.eligible_question_ids))
        self.dispatched_question_ids = sorted(set(self.dispatched_question_ids))
        self.skipped_question_ids = sorted(set(self.skipped_question_ids))
        self.warning_codes = sorted(set(self.warning_codes))
        self.routing_records = sorted(
            self.routing_records, key=lambda row: row.question_id
        )
        self.fused_evidence_ids = sorted(set(self.fused_evidence_ids))
        self.fused_evidence_ids_by_question = {
            key: sorted(set(self.fused_evidence_ids_by_question[key]))
            for key in sorted(self.fused_evidence_ids_by_question)
        }
        self.fused_question_stances = {
            question_id: {
                evidence_id: self.fused_question_stances[question_id][evidence_id]
                for evidence_id in sorted(self.fused_question_stances[question_id])
            }
            for question_id in sorted(self.fused_question_stances)
        }
        self.fused_authority_conflicts = sorted(
            self.fused_authority_conflicts,
            key=lambda row: (row.claim_key, row.subject.value),
        )
        self.fused_currentness_conflicts = sorted(
            set(self.fused_currentness_conflicts)
        )
        self.consumed_evidence_ids = sorted(set(self.consumed_evidence_ids))
        self.skip_reasons = {
            key: self.skip_reasons[key] for key in sorted(self.skip_reasons)
        }
        return self


class ReasoningEvidenceSemanticBatch(BaseModel):
    """Provider-neutral semantic output owned and hashed by runtime stage 10."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[
        "aem-guides-reasoning-evidence-semantic-batch-v1"
    ] = REASONING_EVIDENCE_SEMANTIC_BATCH_SCHEMA
    local_evidence_bundle_id: str = Field(min_length=1)
    evidence_bundle: CanonicalEvidenceBundle
    local_retrievals: list[DirectedRetrievalRecord] = Field(default_factory=list)
    retrievals: list[DirectedRetrievalRecord] = Field(default_factory=list)
    semantic_evidence: list[AuthorizedSemanticEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_semantic_links(self) -> "ReasoningEvidenceSemanticBatch":
        if not self.semantic_evidence:
            raise ValueError("semantic stage batch requires authorized evidence")
        local_question_ids = [row.question_id for row in self.local_retrievals]
        fused_question_ids = [row.question_id for row in self.retrievals]
        if (
            len(local_question_ids) != len(set(local_question_ids))
            or len(fused_question_ids) != len(set(fused_question_ids))
        ):
            raise ValueError("semantic stage batch contains duplicate question IDs")
        if local_question_ids != fused_question_ids:
            raise ValueError("local and fused retrieval question sets differ")
        evidence_ids = {record.evidence_id for record in self.evidence_bundle.records}
        retrieval_by_question = {row.question_id: row for row in self.retrievals}
        if any(
            not set(row.matched_evidence_ids).issubset(evidence_ids)
            for row in self.local_retrievals + self.retrievals
        ):
            raise ValueError("semantic stage retrieval references missing evidence")
        handoff_ids: set[str] = set()
        handoff_pairs: set[tuple[str, str]] = set()
        for handoff in self.semantic_evidence:
            binding = handoff.authorization.source_attestation.binding
            pair = (binding.question_id, binding.evidence_id)
            if (
                binding.evidence_id not in evidence_ids
                or binding.question_id not in fused_question_ids
                or binding.evidence_id
                not in retrieval_by_question[binding.question_id].matched_evidence_ids
                or handoff.handoff_id in handoff_ids
                or pair in handoff_pairs
            ):
                raise ValueError("semantic handoff references missing stage evidence")
            handoff_ids.add(handoff.handoff_id)
            handoff_pairs.add(pair)
        return self

    def semantic_projection(self) -> dict[str, Any]:
        """Deterministic stage hash projection without operational timestamps."""

        handoffs: list[dict[str, Any]] = []
        for handoff in sorted(
            self.semantic_evidence,
            key=lambda row: (
                row.authorization.source_attestation.binding.question_id,
                row.authorization.source_attestation.binding.evidence_id,
            ),
        ):
            authorization = handoff.authorization
            binding = authorization.source_attestation.binding
            attestation = authorization.source_attestation
            assessment = authorization.question_assessment
            handoffs.append(
                {
                    "request_id": binding.request_id,
                    "question_id": binding.question_id,
                    "question_sha256": binding.question_sha256,
                    "query_id": binding.query_id,
                    "evidence_id": binding.evidence_id,
                    "content_sha256": binding.content_sha256,
                    "tenant_id": binding.tenant_id,
                    "source_type": binding.source_type.value,
                    "authority_subject": binding.authority_subject.value,
                    "requirement_authority": binding.requirement_authority.value,
                    "currentness": binding.currentness.value,
                    "source_reference_sha256": binding.source_reference_sha256,
                    "version_scope_sha256": binding.version_scope_sha256,
                    "visibility_sha256": binding.visibility_sha256,
                    "principal_scope_sha256": binding.principal_scope_sha256,
                    "temporal_policy_sha256": binding.temporal_policy_sha256,
                    "authority_requirement_sha256": (
                        binding.authority_requirement_sha256
                    ),
                    "verification_status": attestation.verification_status.value,
                    "source_revision": attestation.source_revision,
                    "verification_method": attestation.verification_method,
                    "verifier_id": attestation.verifier_id,
                    "verifier_version": attestation.verifier_version,
                    "attestation_reason_code": attestation.reason_code,
                    "stance": assessment.stance.value,
                    "assessment_confidence": assessment.assessment_confidence,
                    "claim_keys": assessment.claim_keys,
                    "assessment_method": assessment.assessment_method,
                    "assessor_id": assessment.assessor_id,
                    "assessor_version": assessment.assessor_version,
                    "assessment_reason_code": assessment.reason_code,
                }
            )
        return {
            "schema_version": self.schema_version,
            "local_evidence_bundle_id": self.local_evidence_bundle_id,
            "evidence_bundle_id": self.evidence_bundle.bundle_id,
            "local_retrievals": [
                row.model_dump(mode="json") for row in self.local_retrievals
            ],
            "retrievals": [row.model_dump(mode="json") for row in self.retrievals],
            "semantic_evidence": handoffs,
        }


class ReasoningEvidenceSecondPassResult(BaseModel):
    """Private semantic result returned to the canonical stage-10 owner."""

    model_config = ConfigDict(extra="forbid")

    evidence_bundle: CanonicalEvidenceBundle
    retrievals: list[DirectedRetrievalRecord] = Field(default_factory=list)
    semantic_evidence: list[AuthorizedSemanticEvidence] = Field(default_factory=list)
    trace: FluffyJawsShadowRunTrace | None = None

    @property
    def semantic_authorizations(self) -> list[SemanticEvidenceAuthorization]:
        """Compatibility projection; runtime consumers use sealed handoffs."""

        return [row.authorization for row in self.semantic_evidence]

    def to_semantic_batch(
        self,
        *,
        local_evidence_bundle_id: str,
        local_retrievals: list[DirectedRetrievalRecord],
    ) -> ReasoningEvidenceSemanticBatch:
        return ReasoningEvidenceSemanticBatch(
            local_evidence_bundle_id=local_evidence_bundle_id,
            evidence_bundle=self.evidence_bundle,
            local_retrievals=local_retrievals,
            retrievals=self.retrievals,
            semantic_evidence=self.semantic_evidence,
        )

    @model_validator(mode="after")
    def validate_retrieval_links(self) -> "ReasoningEvidenceSecondPassResult":
        evidence_ids = {record.evidence_id for record in self.evidence_bundle.records}
        question_ids: set[str] = set()
        for retrieval in self.retrievals:
            if retrieval.question_id in question_ids:
                raise ValueError("second-pass result contains duplicate question IDs")
            question_ids.add(retrieval.question_id)
            if not set(retrieval.matched_evidence_ids).issubset(evidence_ids):
                raise ValueError("second-pass retrieval references missing evidence")
        authorization_ids: set[str] = set()
        for handoff in self.semantic_evidence:
            authorization = handoff.authorization
            if authorization.authorization_id in authorization_ids:
                raise ValueError("second-pass result contains duplicate authorization IDs")
            authorization_ids.add(authorization.authorization_id)
            binding = authorization.source_attestation.binding
            if binding.evidence_id not in evidence_ids:
                raise ValueError("semantic authorization references missing evidence")
            if binding.question_id not in question_ids:
                raise ValueError("semantic authorization references missing question")
        return self


_LAST_FLUFFYJAWS_SHADOW_TRACE: ContextVar[FluffyJawsShadowRunTrace | None] = (
    ContextVar("aem_guides_last_fluffyjaws_shadow_trace", default=None)
)


def clear_last_fluffyjaws_shadow_trace() -> None:
    _LAST_FLUFFYJAWS_SHADOW_TRACE.set(None)


def get_last_fluffyjaws_shadow_trace() -> FluffyJawsShadowRunTrace | None:
    trace = _LAST_FLUFFYJAWS_SHADOW_TRACE.get()
    return trace.model_copy(deep=True) if trace is not None else None


def record_semantic_usage_trace(
    bundle: CanonicalEvidenceBundle,
    consumed_evidence_ids: Iterable[str],
) -> None:
    """Update only the operational sidecar after canonical stage 11 completes."""

    trace = get_last_fluffyjaws_shadow_trace()
    if trace is None:
        return
    consumed = sorted(
        set(consumed_evidence_ids).intersection(trace.fused_evidence_ids)
    )
    _LAST_FLUFFYJAWS_SHADOW_TRACE.set(
        FluffyJawsShadowRunTrace.model_validate(
            {
                **trace.model_dump(mode="json"),
                "fused_bundle_id": bundle.bundle_id,
                "consumed_evidence_ids": consumed,
            }
        )
    )


class ReasoningEvidenceShadowService:
    """Execute bounded provider calls without influencing canonical reasoning."""

    def __init__(
        self,
        *,
        config: FluffyJawsShadowConfig | None = None,
        providers: Iterable[EvidenceProvider] = (),
        executor: EvidenceProviderExecutor | None = None,
        resilience_controller: EvidenceProviderResilienceController | None = None,
        routing_policy: ConservativeFluffyJawsRoutingPolicy | None = None,
        source_visibility_check: Callable[[Any], bool] = _deny_unverified_source,
        source_verification_check: Callable[[Any], bool] = _deny_unverified_source,
        semantic_evidence_authorization_check: Callable[
            [
                EvidenceRecord,
                RetrievalProvenance,
                ProviderHitDisposition,
                EvidenceQueryV1,
                SemanticEvidenceBinding,
            ],
            SemanticEvidenceAuthorization | Mapping[str, Any] | None,
        ] = _deny_semantic_evidence_authorization,
        query_egress_check: Callable[
            [EvidenceQueryV1, GenerationRequest], bool
        ] = _deny_query_egress,
        cancellation_check: Callable[[], bool] = _never_cancelled,
    ) -> None:
        self._configuration_error_code = ""
        if config is not None:
            self.config = config
        else:
            try:
                self.config = FluffyJawsShadowConfig.from_environment()
            except ValueError:
                # An optional trace-only integration can never prevent the
                # canonical runtime from starting.  Keep the strict parser
                # public for deployment validation, but fail disabled here.
                self.config = FluffyJawsShadowConfig()
                self._configuration_error_code = "INVALID_SHADOW_CONFIGURATION"
        registry_enabled = self.config.provider_capture_enabled
        registered_providers: list[EvidenceProvider] = []
        if registry_enabled:
            for provider in providers:
                if provider.descriptor().provider != "fluffyjaws":
                    raise ValueError(
                        "FluffyJaws capture accepts only the fluffyjaws provider"
                    )
                registered_providers.append(provider)
        self._registry = EvidenceProviderRegistry(
            registered_providers, enabled=registry_enabled
        )
        self._executor = executor or EvidenceProviderExecutor()
        self._resilience = resilience_controller or (
            EvidenceProviderResilienceController(
                policy=ProviderResiliencePolicy(
                    max_attempts=self.config.retry_max_attempts,
                    cache_enabled=self.config.cache_enabled,
                    cache_ttl_seconds=self.config.cache_ttl_seconds,
                    cache_max_entries=self.config.cache_max_entries,
                    cache_max_bytes=self.config.cache_max_bytes,
                    circuit_failure_threshold=self.config.circuit_failure_threshold,
                    circuit_cooldown_seconds=self.config.circuit_cooldown_seconds,
                    circuit_max_entries=self.config.circuit_max_entries,
                )
            )
        )
        self._routing_policy = routing_policy or ConservativeFluffyJawsRoutingPolicy()
        self._source_visibility_check = source_visibility_check
        self._source_verification_check = source_verification_check
        self._semantic_evidence_authorization_check = (
            semantic_evidence_authorization_check
        )
        self._query_egress_check = query_egress_check
        self._cancellation_check = cancellation_check

    @property
    def mode(self) -> FluffyJawsRuntimeMode:
        return self.config.mode

    def retrieve(
        self,
        *,
        run_id: str,
        request: GenerationRequest,
        evidence: CanonicalEvidenceBundle,
        domains: list[DomainActivation],
        scope: ScopeResolution,
        questions: list[MissingQuestion],
        local_retrievals: list[DirectedRetrievalRecord],
    ) -> ReasoningEvidenceSecondPassResult:
        """Run optional retrieval and return the semantic stage-10 projection.

        DISABLED and SHADOW return the exact local bundle and retrieval models.
        SECOND_PASS can add only independently attested underlying sources.
        Operational timestamps, latency, provider status, and synthesis remain in
        the sidecar and are never part of the semantic stage output.
        """

        trace = self.capture(
            run_id=run_id,
            request=request,
            evidence=evidence,
            domains=domains,
            scope=scope,
            questions=questions,
            local_retrievals=local_retrievals,
        )
        if (
            self.mode != FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS
            or trace is None
            or trace.state
            in {"CONFIG_UNAVAILABLE", "BLIND_REPLAY_BLOCKED"}
        ):
            return ReasoningEvidenceSecondPassResult(
                evidence_bundle=evidence,
                retrievals=local_retrievals,
                trace=trace,
            )
        return self._fuse_second_pass(
            request=request,
            evidence=evidence,
            questions=questions,
            local_retrievals=local_retrievals,
            trace=trace,
        )

    def capture(
        self,
        *,
        run_id: str,
        request: GenerationRequest,
        evidence: CanonicalEvidenceBundle,
        domains: list[DomainActivation],
        scope: ScopeResolution,
        questions: list[MissingQuestion],
        local_retrievals: list[DirectedRetrievalRecord],
    ) -> FluffyJawsShadowRunTrace | None:
        """Capture provider results without changing canonical semantic objects."""

        clear_last_fluffyjaws_shadow_trace()
        if self._configuration_error_code:
            started_at = _utc_now()
            trace = self._empty_trace(
                run_id=run_id,
                request=request,
                evidence=evidence,
                started_at=started_at,
                state="CONFIG_UNAVAILABLE",
                warning_codes=[self._configuration_error_code],
                skipped_question_ids=[row.question_id for row in questions],
            )
            _LAST_FLUFFYJAWS_SHADOW_TRACE.set(trace)
            return trace
        if self.mode == FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED:
            return None
        started_at = _utc_now()
        if request.benchmark_split in {"validation", "blind"}:
            trace = self._empty_trace(
                run_id=run_id,
                request=request,
                evidence=evidence,
                started_at=started_at,
                state="BLIND_REPLAY_BLOCKED",
                warning_codes=["BLIND_COLLECTOR_NOT_CERTIFIED"],
                skipped_question_ids=[row.question_id for row in questions],
            )
            _LAST_FLUFFYJAWS_SHADOW_TRACE.set(trace)
            return trace

        local_by_question = {row.question_id: row for row in local_retrievals}
        material_questions = [
            (question, self._materiality(question)) for question in questions
        ]
        second_pass = self.mode == FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS
        skipped_question_ids: list[str] = []
        skip_reasons: dict[str, str] = {}
        warning_codes: list[str] = []
        calls: list[FluffyJawsShadowCallTrace] = []
        dispatched_question_ids: list[str] = []
        routing_evaluations: dict[str, FluffyJawsRoutingEvaluation] = {}
        routing_budgets: dict[str, FluffyJawsRoutingBudget] = {}
        routing_no_call_reasons: dict[str, FluffyJawsNoCallReason] = {}
        routing_called_question_ids: set[str] = set()
        dispatch_attempt_count = 0
        internal_error_count = 0
        internal_error_latencies: list[int] = []
        budget_started = monotonic()

        def skip_question(
            question_id: str,
            reason: FluffyJawsNoCallReason | str,
            *,
            warning: bool = True,
        ) -> None:
            code = reason.value if isinstance(reason, FluffyJawsNoCallReason) else reason
            skipped_question_ids.append(question_id)
            skip_reasons[question_id] = code
            if warning:
                warning_codes.append(code)
            if (
                second_pass
                and isinstance(reason, FluffyJawsNoCallReason)
                and question_id not in routing_called_question_ids
            ):
                routing_no_call_reasons[question_id] = reason

        if second_pass:
            for question, materiality in material_questions:
                routing_evaluations[question.question_id] = (
                    self._routing_policy.evaluate(
                        question=question,
                        local=local_by_question.get(question.question_id),
                        bundle=evidence,
                        materiality=materiality,
                    )
                )
            eligible_questions = sorted(
                (
                    (question, materiality)
                    for question, materiality in material_questions
                    if routing_evaluations[question.question_id].policy_eligible
                ),
                key=lambda row: (
                    0 if row[1] == QueryMateriality.P0 else 1,
                    row[0].question_id,
                ),
            )
            priority_by_question = {
                question.question_id: priority
                for priority, (question, _materiality) in enumerate(
                    eligible_questions, start=1
                )
            }
            max_results = self._effective_max_results(request)
            for question, _materiality in material_questions:
                evaluation = routing_evaluations[question.question_id]
                priority = priority_by_question.get(question.question_id)
                routing_budgets[question.question_id] = FluffyJawsRoutingBudget(
                    eligible_priority=priority,
                    max_questions=self.config.max_questions,
                    max_results=max_results,
                    call_timeout_seconds=self.config.call_timeout_seconds,
                    total_timeout_seconds=self.config.total_timeout_seconds,
                    within_question_budget=(
                        priority is not None and priority <= self.config.max_questions
                    ),
                )
                if not evaluation.policy_eligible:
                    if evaluation.policy_skip_reason is None:
                        raise ValueError("ineligible routing evaluation has no reason")
                    skip_question(
                        question.question_id,
                        evaluation.policy_skip_reason,
                        warning=False,
                    )
            selected_questions = eligible_questions[: self.config.max_questions]
            for question, _materiality in eligible_questions[
                self.config.max_questions :
            ]:
                skip_question(
                    question.question_id,
                    FluffyJawsNoCallReason.QUESTION_BUDGET_EXCEEDED,
                )
        else:
            # FJ-06 SHADOW remains an observation mode: it samples material
            # questions without applying the SECOND_PASS policy.
            selected_questions = material_questions[: self.config.max_questions]
            for question, _materiality in material_questions[
                self.config.max_questions :
            ]:
                skip_question(
                    question.question_id,
                    FluffyJawsNoCallReason.QUESTION_BUDGET_EXCEEDED,
                )

        for question, materiality in selected_questions:
            elapsed = monotonic() - budget_started
            remaining = self.config.total_timeout_seconds - elapsed
            if remaining <= 0:
                skip_question(
                    question.question_id,
                    FluffyJawsNoCallReason.TOTAL_TIMEOUT_EXHAUSTED,
                )
                continue
            local = local_by_question.get(question.question_id)
            allowed_sources = set(request.allowed_sources)
            if allowed_sources and not (
                allowed_sources & set(question.target_source_types)
            ):
                skip_question(
                    question.question_id,
                    FluffyJawsNoCallReason.NO_ALLOWED_TARGET_SOURCE,
                )
                continue
            try:
                query = self._build_query(
                    request=request,
                    evidence=evidence,
                    scope=scope,
                    domains=domains,
                    question=question,
                    local=local,
                    materiality=materiality,
                    max_results=(
                        routing_budgets[question.question_id].max_results
                        if second_pass
                        else self.config.max_results
                    ),
                )
                if self._query_egress_check(query, request) is not True:
                    skip_question(
                        question.question_id,
                        FluffyJawsNoCallReason.QUERY_EGRESS_POLICY_DENIED,
                    )
                    continue
                providers = self._registry.eligible(
                    query, allow_discovery_only=True
                )
            except Exception:
                skip_question(
                    question.question_id,
                    FluffyJawsNoCallReason.QUERY_OR_REGISTRY_ERROR,
                )
                continue
            if not providers:
                skip_question(
                    question.question_id,
                    FluffyJawsNoCallReason.NO_ELIGIBLE_PROVIDER,
                )
                continue
            for provider in providers:
                elapsed = monotonic() - budget_started
                remaining = self.config.total_timeout_seconds - elapsed
                if remaining <= 0:
                    skip_question(
                        question.question_id,
                        FluffyJawsNoCallReason.TOTAL_TIMEOUT_EXHAUSTED,
                    )
                    break
                context = EvidenceProviderExecutionContext(
                    principal=RuntimePrincipal.model_validate(request.principal),
                    run_id=run_id,
                    request_id=request.request_id,
                    correlation_id=query.correlation_id,
                    benchmark_split=request.benchmark_split,
                    timeout_seconds=min(
                        self.config.call_timeout_seconds, max(0.001, remaining)
                    ),
                    cancellation_check=self._cancellation_check,
                    source_visibility_check=self._source_visibility_check,
                    source_verification_check=self._source_verification_check,
                )
                dispatch_started = monotonic()
                try:
                    execution = self._executor.execute(
                        self._resilience.wrap(provider),
                        query,
                        context,
                        base_bundle=evidence,
                        resilience_metadata_trusted=True,
                    )
                    call_trace = self._call_trace(
                        query=query,
                        materiality=materiality,
                        local=local,
                        execution=execution,
                    )
                except Exception:
                    internal_error_count += 1
                    internal_error_latencies.append(
                        max(0, round((monotonic() - dispatch_started) * 1000))
                    )
                    skip_question(
                        question.question_id,
                        FluffyJawsNoCallReason.PROVIDER_EXECUTOR_ERROR,
                    )
                    continue
                actual_attempts = execution.call_result.attempts
                dispatch_attempt_count += actual_attempts
                if actual_attempts > 0:
                    dispatched_question_ids.append(question.question_id)
                logical_provider_call = bool(
                    actual_attempts > 0
                    or execution.call_result.cache_state == ProviderCacheState.HIT
                )
                if second_pass and logical_provider_call:
                    routing_called_question_ids.add(question.question_id)
                    routing_no_call_reasons.pop(question.question_id, None)
                elif second_pass:
                    error_code = execution.call_result.redacted_error_code
                    if error_code == "CIRCUIT_OPEN":
                        skip_question(
                            question.question_id,
                            FluffyJawsNoCallReason.CIRCUIT_OPEN,
                        )
                    elif error_code == "CIRCUIT_HALF_OPEN":
                        skip_question(
                            question.question_id,
                            FluffyJawsNoCallReason.CIRCUIT_HALF_OPEN,
                        )
                calls.append(call_trace)

        routing_records: list[FluffyJawsRoutingRecord] = []
        if second_pass:
            for question, _materiality in material_questions:
                evaluation = routing_evaluations[question.question_id]
                called = question.question_id in routing_called_question_ids
                routing_records.append(
                    build_fluffyjaws_routing_record(
                        evaluation=evaluation,
                        budget=routing_budgets[question.question_id],
                        run_id=run_id,
                        request_id=request.request_id,
                        mode=self.mode.value,
                        provider_called=called,
                        no_call_reason=(
                            None
                            if called
                            else routing_no_call_reasons.get(question.question_id)
                        ),
                    )
                )

        eligible_question_ids = (
            sorted(
                evaluation.question_id
                for evaluation in routing_evaluations.values()
                if evaluation.policy_eligible
            )
            if second_pass
            else [row.question_id for row, _ in material_questions]
        )
        eligible_no_call_reasons = {
            question_id: reason
            for question_id, reason in routing_no_call_reasons.items()
            if routing_evaluations.get(question_id) is not None
            and routing_evaluations[question_id].policy_eligible
            and question_id not in routing_called_question_ids
        }
        missing_provider_only = bool(
            second_pass
            and eligible_question_ids
            and dispatch_attempt_count == 0
            and eligible_no_call_reasons
            and set(eligible_no_call_reasons.values())
            == {FluffyJawsNoCallReason.NO_ELIGIBLE_PROVIDER}
        ) or bool(
            not second_pass
            and questions
            and dispatch_attempt_count == 0
            and skip_reasons
            and set(skip_reasons.values()) == {"NO_ELIGIBLE_PROVIDER"}
        )
        if missing_provider_only:
            state = "CONFIG_UNAVAILABLE"
        elif second_pass:
            state = (
                "SECOND_PASS_PARTIAL"
                if internal_error_count
                or eligible_no_call_reasons
                or any(call.call_result.status in _ERROR_STATUSES for call in calls)
                else "SECOND_PASS_COMPLETED"
            )
        else:
            state = (
                "SHADOW_PARTIAL"
                if internal_error_count
                or skipped_question_ids
                or any(call.call_result.status in _ERROR_STATUSES for call in calls)
                else "SHADOW_COMPLETED"
            )
        trace = FluffyJawsShadowRunTrace(
            mode=self.mode,
            run_id=run_id,
            request_id=request.request_id,
            evidence_bundle_id=evidence.bundle_id,
            started_at=started_at,
            completed_at=_utc_now(),
            state=state,
            eligible_question_ids=eligible_question_ids,
            dispatched_question_ids=dispatched_question_ids,
            skipped_question_ids=skipped_question_ids,
            skip_reasons=skip_reasons,
            warning_codes=warning_codes,
            routing_records=routing_records,
            calls=calls,
            metrics=self._metrics(
                calls,
                dispatch_attempt_count=dispatch_attempt_count,
                internal_error_count=internal_error_count,
                internal_error_latencies=internal_error_latencies,
            ),
        )
        _LAST_FLUFFYJAWS_SHADOW_TRACE.set(trace)
        return trace

    def _fuse_second_pass(
        self,
        *,
        request: GenerationRequest,
        evidence: CanonicalEvidenceBundle,
        questions: list[MissingQuestion],
        local_retrievals: list[DirectedRetrievalRecord],
        trace: FluffyJawsShadowRunTrace,
    ) -> ReasoningEvidenceSecondPassResult:
        """Fuse only independently authenticated and question-assessed evidence."""

        questions_by_id = {row.question_id: row for row in questions}
        called_routes = {
            row.question_id
            for row in trace.routing_records
            if row.provider_called
        }
        assessed_records: dict[str, EvidenceRecord] = {}
        semantic_handoffs: dict[str, AuthorizedSemanticEvidence] = {}
        fused_by_question: dict[str, set[str]] = {}
        stances_by_question: dict[str, dict[str, QuestionEvidenceStance]] = {}
        updated_calls: list[FluffyJawsShadowCallTrace] = []

        for call in trace.calls:
            fused_ids: list[str] = []
            rejections: dict[str, str] = {}
            attestation_ids: list[str] = []
            assessment_ids: list[str] = []
            authorization_ids: list[str] = []
            semantic_stances: dict[str, QuestionEvidenceStance] = {}
            route_permitted = call.question_id in called_routes
            status_usable = bool(
                call.call_result.transport_outcome
                == ProviderTransportOutcome.COMPLETED
                and call.call_result.status
                in {
                    EvidenceProviderStatus.SUCCESS,
                    EvidenceProviderStatus.PARTIAL,
                }
            )
            for record in call.evidence_records:
                if not route_permitted:
                    rejections[record.evidence_id] = "ROUTING_NOT_PERMITTED"
                    continue
                if not status_usable:
                    rejections[record.evidence_id] = "PROVIDER_RESULT_NOT_USABLE"
                    continue
                provenance = next(
                    (
                        row
                        for row in call.provenance
                        if row.evidence_id == record.evidence_id
                        and row.query_id == call.query.query_id
                    ),
                    None,
                )
                if provenance is None:
                    rejections[record.evidence_id] = "PROVENANCE_REQUIRED"
                    continue
                disposition = next(
                    (
                        row
                        for row in call.hit_dispositions
                        if row.accepted
                        and row.evidence_id == record.evidence_id
                        and row.query_id == call.query.query_id
                    ),
                    None,
                )
                if disposition is None:
                    rejections[record.evidence_id] = "ACCEPTED_DISPOSITION_REQUIRED"
                    continue
                assessed, authorization, rejection = self._authorize_source_record(
                    request=request,
                    record=record,
                    provenance=provenance,
                    disposition=disposition,
                    query=call.query,
                    question=questions_by_id.get(call.question_id),
                )
                if assessed is None or authorization is None:
                    rejections[record.evidence_id] = rejection
                    continue
                source_attestation = authorization.source_attestation
                question_assessment = authorization.question_assessment
                attestation_ids.append(source_attestation.attestation_id)
                assessment_ids.append(question_assessment.assessment_id)
                authorization_ids.append(authorization.authorization_id)
                semantic_handoffs[authorization.authorization_id] = (
                    AuthorizedSemanticEvidence(
                        authorization=authorization,
                        query=call.query,
                        provenance=provenance,
                        disposition=disposition,
                    )
                )
                semantic_stances[record.evidence_id] = question_assessment.stance
                if question_assessment.stance in {
                    QuestionEvidenceStance.IRRELEVANT,
                    QuestionEvidenceStance.AMBIGUOUS,
                }:
                    rejections[record.evidence_id] = (
                        f"QUESTION_ASSESSMENT_{question_assessment.stance.value}"
                    )
                    continue
                prior = assessed_records.get(assessed.evidence_id)
                assessed_records[assessed.evidence_id] = (
                    self._merge_assessed_records(prior, assessed)
                    if prior is not None
                    else assessed
                )
                fused_ids.append(assessed.evidence_id)
                fused_by_question.setdefault(call.question_id, set()).add(
                    assessed.evidence_id
                )
                stances_by_question.setdefault(call.question_id, {})[
                    assessed.evidence_id
                ] = question_assessment.stance
            updated_calls.append(
                FluffyJawsShadowCallTrace.model_validate(
                    {
                        **call.model_dump(mode="json"),
                        "semantic_fusion_evaluated": True,
                        "semantic_fusion_evidence_ids": fused_ids,
                        "semantic_fusion_rejections": rejections,
                        "source_attestation_ids": attestation_ids,
                        "question_assessment_ids": assessment_ids,
                        "semantic_authorization_ids": authorization_ids,
                        "semantic_stances": semantic_stances,
                    }
                )
            )

        if not assessed_records:
            updated_trace = FluffyJawsShadowRunTrace.model_validate(
                {
                    **trace.model_dump(mode="json"),
                    "calls": [
                        row.model_dump(mode="json") for row in updated_calls
                    ],
                    "fused_bundle_id": evidence.bundle_id,
                }
            )
            _LAST_FLUFFYJAWS_SHADOW_TRACE.set(updated_trace)
            return ReasoningEvidenceSecondPassResult(
                evidence_bundle=evidence,
                retrievals=local_retrievals,
                semantic_evidence=[],
                trace=updated_trace,
            )

        combined = {record.evidence_id: record for record in evidence.records}
        for record in assessed_records.values():
            prior = combined.get(record.evidence_id)
            combined[record.evidence_id] = (
                self._merge_assessed_records(prior, record)
                if prior is not None
                else record
            )
        fused_bundle = build_bundle(
            combined.values(),
            tenant_id=evidence.tenant_id,
            issue_facts=evidence.issue_facts,
            unavailable_sources=evidence.unavailable_sources,
        )

        all_fused_ids = set(assessed_records)
        relevant_authority_conflicts = [
            row
            for row in fused_bundle.authority_conflicts
            if (
                set(row.selected_evidence_ids)
                | set(row.competing_evidence_ids)
            )
            & all_fused_ids
        ]
        relevant_conflict_ids = {
            evidence_id
            for row in relevant_authority_conflicts
            for evidence_id in (
                list(row.selected_evidence_ids) + list(row.competing_evidence_ids)
            )
        }
        fused_claim_keys = {
            claim_key
            for evidence_id in all_fused_ids
            for record in fused_bundle.records
            if record.evidence_id == evidence_id
            for claim_key in record.claim_keys
        }
        relevant_currentness_conflicts = sorted(
            set(fused_bundle.currentness_conflicts) & fused_claim_keys
        )
        currentness_conflict_ids = {
            record.evidence_id
            for record in fused_bundle.records
            if set(record.claim_keys) & set(relevant_currentness_conflicts)
        }
        relevant_conflict_ids |= currentness_conflict_ids

        augmented_retrievals: list[DirectedRetrievalRecord] = []
        for local in local_retrievals:
            semantic_ids = fused_by_question.get(local.question_id, set())
            if not semantic_ids:
                augmented_retrievals.append(local)
                continue
            matched_ids = sorted(
                set(local.matched_evidence_ids) | set(semantic_ids)
            )
            has_unresolved_conflict = bool(
                set(matched_ids) & relevant_conflict_ids
            )
            augmented_retrievals.append(
                DirectedRetrievalRecord(
                    question_id=local.question_id,
                    query=local.query,
                    authority_subject=local.authority_subject,
                    target_source_types=local.target_source_types,
                    matched_evidence_ids=matched_ids,
                    status=RetrievalStatus.USED,
                    reason=(
                        "Local and independently verified second-pass evidence "
                        "were retained with an unresolved canonical conflict."
                        if has_unresolved_conflict
                        else "Local and independently verified second-pass source "
                        "evidence matched the question."
                        if local.matched_evidence_ids
                        else "Independently verified second-pass source evidence "
                        "matched the question."
                    ),
                )
            )

        updated_trace = FluffyJawsShadowRunTrace.model_validate(
            {
                **trace.model_dump(mode="json"),
                "calls": [row.model_dump(mode="json") for row in updated_calls],
                "fused_bundle_id": fused_bundle.bundle_id,
                "fused_evidence_ids": sorted(all_fused_ids),
                "fused_evidence_ids_by_question": {
                    key: sorted(value) for key, value in fused_by_question.items()
                },
                "fused_question_stances": {
                    question_id: {
                        evidence_id: stance.value
                        for evidence_id, stance in evidence_stances.items()
                    }
                    for question_id, evidence_stances in stances_by_question.items()
                },
                "fused_authority_conflicts": [
                    row.model_dump(mode="json")
                    for row in relevant_authority_conflicts
                ],
                "fused_currentness_conflicts": relevant_currentness_conflicts,
            }
        )
        _LAST_FLUFFYJAWS_SHADOW_TRACE.set(updated_trace)
        return ReasoningEvidenceSecondPassResult(
            evidence_bundle=fused_bundle,
            retrievals=augmented_retrievals,
            semantic_evidence=[
                semantic_handoffs[key]
                for key in sorted(semantic_handoffs)
                if semantic_handoffs[key]
                .authorization.question_assessment.stance
                in {
                    QuestionEvidenceStance.SUPPORTS,
                    QuestionEvidenceStance.CONTRADICTS,
                }
            ],
            trace=updated_trace,
        )

    def _authorize_source_record(
        self,
        *,
        request: GenerationRequest,
        record: EvidenceRecord,
        provenance: RetrievalProvenance,
        disposition: ProviderHitDisposition,
        query: EvidenceQueryV1,
        question: MissingQuestion | None,
    ) -> tuple[
        EvidenceRecord | None,
        SemanticEvidenceAuthorization | None,
        str,
    ]:
        if question is None or question.question_id != query.question_id:
            return None, None, "QUESTION_LINKAGE_MISMATCH"
        if record.evidence_id not in query.context_evidence_ids and (
            query.query_id not in record.retrieved_by_query
        ):
            return None, None, "QUERY_LINEAGE_MISMATCH"
        if (
            provenance.provider != "fluffyjaws"
            or provenance.query_id != query.query_id
            or provenance.provider_call_id != disposition.provider_call_id
            or provenance.correlation_id != query.correlation_id
            or provenance.applicability != ApplicabilityState.APPLICABLE
        ):
            return None, None, "PROVENANCE_NOT_APPLICABLE"
        if (
            not disposition.accepted
            or disposition.reason_code != "ACCEPTED"
            or disposition.applicability != ApplicabilityState.APPLICABLE
            or disposition.evidence_id != record.evidence_id
            or disposition.provider != provenance.provider
            or disposition.provider_contract_version
            != provenance.provider_contract_version
            or disposition.query_id != query.query_id
            or disposition.correlation_id != query.correlation_id
            or disposition.source_type != record.source_type
        ):
            return None, None, "DISPOSITION_LINKAGE_MISMATCH"
        if (
            record.source_type not in question.target_source_types
            or record.authority_subject != question.authority_subject
            or record.requirement_authority not in _SEMANTIC_AUTHORITY_CLASSES
            or record.currentness not in _SEMANTIC_CURRENTNESS_ALLOWED
        ):
            return None, None, "SEMANTIC_SOURCE_POLICY_REJECTED"
        principal = RuntimePrincipal.model_validate(request.principal)
        if not record_visible_to(record, principal):
            return None, None, "SOURCE_NOT_VISIBLE_TO_PRINCIPAL"
        expected_source_reference_sha256 = stable_sha256(
            {
                "source_reference": record.source_reference,
                "source_locator": record.source_location,
                "source_native_id": record.source_native_id,
            }
        )
        content = record.content if isinstance(record.content, Mapping) else {}
        expected_hit_content_sha256 = stable_sha256(
            {"text": str(content.get("text") or "")}
        )
        if (
            disposition.source_reference_sha256
            != expected_source_reference_sha256
            or disposition.content_sha256 != expected_hit_content_sha256
        ):
            return None, None, "DISPOSITION_SOURCE_BINDING_MISMATCH"
        binding = SemanticEvidenceBinding(
            request_id=request.request_id,
            question_id=question.question_id,
            question_sha256=stable_sha256(question.question),
            query_id=query.query_id,
            evidence_id=record.evidence_id,
            content_sha256=record.content_sha256,
            tenant_id=record.tenant_id,
            source_type=record.source_type,
            authority_subject=record.authority_subject,
            currentness=record.currentness,
            source_reference_sha256=disposition.source_reference_sha256,
            provider_hit_sha256=disposition.provider_hit_sha256,
            provenance_id=provenance.provenance_id,
            disposition_id=disposition.disposition_id,
            requirement_authority=record.requirement_authority,
            provider=provenance.provider,
            provider_contract_version=provenance.provider_contract_version,
            provider_call_id=provenance.provider_call_id,
            correlation_id=provenance.correlation_id,
            version_scope_sha256=stable_sha256(
                record.version_scope.model_dump(mode="json")
            ),
            visibility_sha256=stable_sha256(
                record.visibility.model_dump(mode="json")
            ),
            principal_scope_sha256=stable_sha256(
                principal.model_dump(mode="json")
            ),
            temporal_policy_sha256=stable_sha256(
                query.temporal_boundary.model_dump(mode="json")
            ),
            authority_requirement_sha256=stable_sha256(
                query.authority_requirement.model_dump(mode="json")
            ),
        )
        try:
            raw_authorization = self._semantic_evidence_authorization_check(
                record,
                provenance,
                disposition,
                query,
                binding,
            )
            if raw_authorization is None:
                return None, None, "SEMANTIC_AUTHORIZATION_REQUIRED"
            authorization = SemanticEvidenceAuthorization.model_validate(
                raw_authorization
            )
        except Exception:
            return None, None, "SEMANTIC_AUTHORIZATION_INVALID"
        if authorization.source_attestation.binding != binding:
            return None, None, "SEMANTIC_AUTHORIZATION_BINDING_MISMATCH"
        attestation = authorization.source_attestation
        assessment = authorization.question_assessment
        now = datetime.now(timezone.utc)
        if _parse_utc_timestamp(attestation.verified_at) > now:
            return None, None, "SOURCE_ATTESTATION_NOT_YET_VALID"
        if attestation.expires_at and _parse_utc_timestamp(
            attestation.expires_at
        ) <= now:
            return None, None, "SOURCE_ATTESTATION_EXPIRED"
        if _parse_utc_timestamp(assessment.assessed_at) > now:
            return None, None, "QUESTION_ASSESSMENT_NOT_YET_VALID"
        if _parse_utc_timestamp(assessment.expires_at) <= now:
            return None, None, "QUESTION_ASSESSMENT_EXPIRED"
        expected_revision = self._expected_source_revision(record)
        if record.currentness == CurrentnessState.VERSION_SPECIFIC:
            if (
                attestation.verification_status
                != VerificationState.VERIFIED_REVISION
                or not expected_revision
                or attestation.source_revision != expected_revision
            ):
                return None, None, "PINNED_REVISION_ATTESTATION_REQUIRED"
        elif record.currentness == CurrentnessState.ENVIRONMENT_SPECIFIC:
            if (
                not record.deployment_model
                and not record.environment
                and not record.version_scope.deployment_model
                and not record.version_scope.environment
            ):
                return None, None, "ENVIRONMENT_SCOPE_REQUIRED"
            if attestation.verification_status not in {
                VerificationState.VERIFIED_LIVE,
                VerificationState.VERIFIED_SOURCE,
            }:
                return None, None, "LIVE_ENVIRONMENT_ATTESTATION_REQUIRED"
        elif attestation.verification_status not in {
            VerificationState.VERIFIED_LIVE,
            VerificationState.VERIFIED_SOURCE,
        }:
            return None, None, "CURRENT_SOURCE_ATTESTATION_REQUIRED"
        if (
            provenance.cache_state == ProviderCacheState.HIT
            and record.currentness
            in {
                CurrentnessState.CURRENT,
                CurrentnessState.ENVIRONMENT_SPECIFIC,
            }
            and (
                not provenance.cache_served_at
                or _parse_utc_timestamp(attestation.verified_at)
                < _parse_utc_timestamp(provenance.cache_served_at)
            )
        ):
            return None, None, "FRESH_CACHE_SOURCE_ATTESTATION_REQUIRED"
        payload = record.model_dump(mode="json")
        payload.update(
            {
                "verification_status": attestation.verification_status,
                "claim_keys": sorted(
                    set(record.claim_keys) | set(assessment.claim_keys)
                ),
                "lifecycle_status": EvidenceLifecycleStatus.INSPECTED,
                "inspected": True,
                "used": False,
                "rejected_reason": "",
            }
        )
        try:
            return (
                EvidenceRecord.model_validate(payload),
                authorization,
                "",
            )
        except Exception:
            return None, None, "ASSESSED_RECORD_INVALID"

    @staticmethod
    def _merge_assessed_records(
        prior: EvidenceRecord,
        candidate: EvidenceRecord,
    ) -> EvidenceRecord:
        if prior.evidence_id != candidate.evidence_id:
            raise ValueError("only identical source evidence can be merged")
        if prior.content_sha256 != candidate.content_sha256:
            raise ValueError("identical evidence IDs cannot carry different content")
        protected_fields = (
            "source_type",
            "authority_subject",
            "source_reference",
            "source_location",
            "source_native_id",
            "tenant_id",
            "currentness",
            "requirement_authority",
            "visibility",
            "ownership",
        )
        prior_version = prior.version_scope.model_dump(mode="json")
        candidate_version = candidate.version_scope.model_dump(mode="json")
        prior_version.pop("retrieved_at", None)
        candidate_version.pop("retrieved_at", None)
        if (
            any(
                getattr(prior, field) != getattr(candidate, field)
                for field in protected_fields
            )
            or prior_version != candidate_version
        ):
            raise ValueError("duplicate evidence has conflicting source security fields")
        if prior.lifecycle_status in {
            EvidenceLifecycleStatus.REJECTED,
            EvidenceLifecycleStatus.UNAVAILABLE,
            EvidenceLifecycleStatus.IGNORED_BY_COMPATIBILITY_PATH,
        }:
            raise ValueError("rejected or unavailable local evidence cannot be fused")
        payload = prior.model_dump(mode="json")
        provider_duplicate = prior.retrieval_pass == "reasoning-directed-provider"
        payload["retrieved_by_query"] = sorted(
            set(prior.retrieved_by_query) | set(candidate.retrieved_by_query)
        )
        if provider_duplicate:
            verification_rank = {
                VerificationState.UNVERIFIED: 0,
                VerificationState.VERIFIED_SOURCE: 1,
                VerificationState.VERIFIED_LIVE: 2,
                VerificationState.VERIFIED_REVISION: 3,
            }
            payload.update(
                {
                    "verification_status": max(
                        (prior.verification_status, candidate.verification_status),
                        key=lambda value: verification_rank.get(value, -1),
                    ),
                    "claim_keys": sorted(
                        set(prior.claim_keys) | set(candidate.claim_keys)
                    ),
                    "lifecycle_status": (
                        EvidenceLifecycleStatus.USED
                        if prior.lifecycle_status == EvidenceLifecycleStatus.USED
                        else EvidenceLifecycleStatus.INSPECTED
                    ),
                    "inspected": True,
                    "used": prior.lifecycle_status == EvidenceLifecycleStatus.USED,
                    "rejected_reason": "",
                }
            )
        return EvidenceRecord.model_validate(payload)

    @staticmethod
    def _expected_source_revision(record: EvidenceRecord) -> str:
        return next(
            (
                value
                for value in (
                    record.version_scope.repository_revision,
                    record.product_version,
                    record.dita_version,
                    record.version_scope.dita_version,
                )
                if str(value or "").strip()
            ),
            "",
        )

    @staticmethod
    def _materiality(question: MissingQuestion) -> QueryMateriality:
        # MissingQuestion has no explicit P0-P3 field yet.  Every generated row
        # represents a reasoning gap; blocking rows are P0 and all others are P1.
        return QueryMateriality.P0 if question.blocking else QueryMateriality.P1

    def _effective_max_results(self, request: GenerationRequest) -> int:
        requested = request.retrieval_budget.get("evidence_k")
        if (
            isinstance(requested, int)
            and not isinstance(requested, bool)
            and requested > 0
        ):
            return min(self.config.max_results, requested)
        return self.config.max_results

    def _build_query(
        self,
        *,
        request: GenerationRequest,
        evidence: CanonicalEvidenceBundle,
        scope: ScopeResolution,
        domains: list[DomainActivation],
        question: MissingQuestion,
        local: DirectedRetrievalRecord | None,
        materiality: QueryMateriality,
        max_results: int | None = None,
    ) -> EvidenceQueryV1:
        allowed = set(request.allowed_sources)
        requested_types = [
            source_type
            for source_type in question.target_source_types
            if not allowed or source_type in allowed
        ]
        target_records = [
            record
            for record in evidence.records
            if record.source_type in _TARGET_HUMAN_SOURCE_TYPES
        ]
        exclusions = ExcludedSources(
            source_types=[],
            source_references=sorted(
                {request.jira_key}
                | {
                    record.source_reference
                    for record in target_records
                    if record.source_reference
                }
            ),
            content_sha256=sorted(
                {stable_sha256({"text": record.content}) for record in target_records}
            ),
        )
        primary_domain = (
            sorted(domains, key=lambda row: (-row.confidence, row.domain.value))[0].domain
            if domains
            else IssueDomain.OTHER
        )
        correlation_id = (
            "fj-shadow:"
            + stable_sha256(
                {
                    "request_id": request.request_id,
                    "question_id": question.question_id,
                }
            )[:32]
        )
        safe_question = str(redacted_trace_payload(question.question))
        return EvidenceQueryV1(
            question_id=question.question_id,
            question=safe_question,
            dimension=question.dimension,
            domain=primary_domain,
            requested_evidence_types=requested_types,
            materiality=materiality,
            authority_requirement=AuthorityRequirement(
                subject=question.authority_subject
            ),
            jira_reference=request.jira_key,
            context_evidence_ids=(
                list(local.matched_evidence_ids) if local is not None else []
            ),
            temporal_boundary=TemporalBoundary(
                version_scope=VersionScope(product_versions=scope.product_versions)
            ),
            excluded_sources=exclusions,
            max_results=max_results or self.config.max_results,
            correlation_id=correlation_id,
            blocking=question.blocking,
        )

    @staticmethod
    def _call_trace(
        *,
        query: EvidenceQueryV1,
        materiality: QueryMateriality,
        local: DirectedRetrievalRecord | None,
        execution: ProviderExecutionResult,
    ) -> FluffyJawsShadowCallTrace:
        accepted_ids = set(execution.call_result.accepted_evidence_ids)
        local_ids = set(local.matched_evidence_ids if local is not None else [])
        evidence_records = [
            record
            for record in execution.evidence_bundle.records
            if record.evidence_id in accepted_ids
        ]
        return FluffyJawsShadowCallTrace(
            question_id=query.question_id,
            materiality=materiality,
            query=query,
            local_matched_evidence_ids=sorted(local_ids),
            overlap_evidence_ids=sorted(accepted_ids & local_ids),
            unique_evidence_ids=sorted(accepted_ids - local_ids),
            call_result=execution.call_result,
            evidence_records=evidence_records,
            provenance=execution.provenance,
            hit_dispositions=execution.hit_dispositions,
            discovery_syntheses=execution.discovery_syntheses,
            trace_sidecar=execution.trace_sidecar,
        )

    @staticmethod
    def _metrics(
        calls: list[FluffyJawsShadowCallTrace],
        *,
        dispatch_attempt_count: int | None = None,
        internal_error_count: int = 0,
        internal_error_latencies: list[int] | None = None,
    ) -> FluffyJawsShadowMetrics:
        statuses = [call.call_result.status for call in calls]
        status_counts = {
            status.value: statuses.count(status) for status in EvidenceProviderStatus
        }
        status_counts[EvidenceProviderStatus.PROVIDER_ERROR.value] += (
            internal_error_count
        )
        latencies = [call.call_result.duration_ms for call in calls] + list(
            internal_error_latencies or []
        )
        accepted_records = {
            record.evidence_id: record
            for call in calls
            for record in call.evidence_records
        }
        sources = {
            (
                record.source_type.value,
                record.source_reference,
                record.source_location,
            )
            for record in accepted_records.values()
        }
        citations = {
            (record.source_reference, record.source_location)
            for record in accepted_records.values()
            if record.source_location
        }
        overlap_ids = {
            evidence_id for call in calls for evidence_id in call.overlap_evidence_ids
        }
        unique_ids = {
            evidence_id for call in calls for evidence_id in call.unique_evidence_ids
        }
        discovery_success_count = sum(
            bool(call.discovery_syntheses) for call in calls
        )
        total_latency = sum(latencies)
        return FluffyJawsShadowMetrics(
            provider_call_count=(
                sum(call.call_result.attempts for call in calls)
                if dispatch_attempt_count is None
                else dispatch_attempt_count
            ),
            logical_call_count=len(calls) + internal_error_count,
            recorded_call_count=len(calls),
            internal_error_count=internal_error_count,
            retry_count=sum(
                max(0, call.call_result.attempts - 1) for call in calls
            ),
            cache_hit_count=sum(
                call.call_result.cache_state == ProviderCacheState.HIT
                for call in calls
            ),
            cache_stale_count=sum(
                call.call_result.cache_state == ProviderCacheState.STALE
                for call in calls
            ),
            circuit_open_count=sum(
                call.call_result.circuit_state_after == ProviderCircuitState.OPEN
                for call in calls
            ),
            suppressed_call_count=sum(
                call.call_result.attempts == 0
                and call.call_result.redacted_error_code
                in {"CIRCUIT_OPEN", "CIRCUIT_HALF_OPEN"}
                for call in calls
            ),
            success_count=status_counts[EvidenceProviderStatus.SUCCESS.value],
            empty_count=status_counts[EvidenceProviderStatus.EMPTY.value],
            partial_count=status_counts[EvidenceProviderStatus.PARTIAL.value],
            error_count=sum(status_counts[status.value] for status in _ERROR_STATUSES),
            status_counts=status_counts,
            total_latency_ms=total_latency,
            minimum_latency_ms=min(latencies, default=0),
            maximum_latency_ms=max(latencies, default=0),
            mean_latency_ms=(total_latency / len(latencies) if latencies else 0.0),
            source_count=len(sources),
            citation_count=len(citations),
            overlap_with_local_retrieval_count=len(overlap_ids),
            unique_evidence_count=len(unique_ids),
            accepted_evidence_count=len(accepted_records),
            synthesis_count=sum(len(call.discovery_syntheses) for call in calls),
            discovery_success_count=discovery_success_count,
            synthesis_only_call_count=sum(
                bool(call.discovery_syntheses)
                and not call.call_result.accepted_evidence_ids
                for call in calls
            ),
        )

    def _empty_trace(
        self,
        *,
        run_id: str,
        request: GenerationRequest,
        evidence: CanonicalEvidenceBundle,
        started_at: str,
        state: Literal[
            "CONFIG_UNAVAILABLE", "BLIND_REPLAY_BLOCKED"
        ],
        warning_codes: list[str] | None = None,
        skipped_question_ids: list[str] | None = None,
    ) -> FluffyJawsShadowRunTrace:
        skipped = list(skipped_question_ids or [])
        return FluffyJawsShadowRunTrace(
            mode=self.mode,
            run_id=run_id,
            request_id=request.request_id,
            evidence_bundle_id=evidence.bundle_id,
            started_at=started_at,
            completed_at=_utc_now(),
            state=state,
            skipped_question_ids=skipped,
            skip_reasons={question_id: state for question_id in skipped},
            warning_codes=list(warning_codes or []),
        )


__all__ = [
    "FLUFFYJAWS_CACHE_ENABLED_ENV",
    "FLUFFYJAWS_CACHE_MAX_BYTES_ENV",
    "FLUFFYJAWS_CACHE_MAX_ENTRIES_ENV",
    "FLUFFYJAWS_CACHE_TTL_ENV",
    "FLUFFYJAWS_CIRCUIT_COOLDOWN_ENV",
    "FLUFFYJAWS_CIRCUIT_FAILURE_THRESHOLD_ENV",
    "FLUFFYJAWS_CIRCUIT_MAX_ENTRIES_ENV",
    "FLUFFYJAWS_MODE_ENV",
    "FLUFFYJAWS_RETRY_MAX_ATTEMPTS_ENV",
    "FLUFFYJAWS_SHADOW_CALL_TIMEOUT_ENV",
    "FLUFFYJAWS_SHADOW_MAX_QUESTIONS_ENV",
    "FLUFFYJAWS_SHADOW_MAX_RESULTS_ENV",
    "FLUFFYJAWS_SHADOW_TOTAL_TIMEOUT_ENV",
    "FLUFFYJAWS_SHADOW_TRACE_SCHEMA",
    "SOURCE_ATTESTATION_SCHEMA",
    "FluffyJawsRuntimeMode",
    "FluffyJawsShadowCallTrace",
    "FluffyJawsShadowConfig",
    "FluffyJawsShadowMetrics",
    "FluffyJawsShadowRunTrace",
    "FluffyJawsRoutingRecord",
    "ReasoningEvidenceSemanticBatch",
    "ReasoningEvidenceSecondPassResult",
    "ReasoningEvidenceShadowService",
    "SourceNativeEvidenceAttestation",
    "clear_last_fluffyjaws_shadow_trace",
    "get_last_fluffyjaws_shadow_trace",
    "record_semantic_usage_trace",
]
