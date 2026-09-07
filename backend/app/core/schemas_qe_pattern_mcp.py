"""Provider-neutral contracts for Human-backed QE reasoning patterns.

The Pattern MCP is discovery-only.  Its records can recommend question families
and relationships to investigate, but they cannot define a current Jira's
acceptance contract or final AC wording.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
import hashlib
import json
import re
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)


PATTERN_MCP_SCHEMA_VERSION = "aem-guides-qe-pattern-mcp-v1"


def _clean_list(values: list[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _clean_reviewer(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("reviewer must not be blank")
    return cleaned


def _clean_review_timestamp(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("review timestamp must not be blank")
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("review timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("review timestamp must include a timezone")
    return cleaned


class QePatternProviderStatus(StrEnum):
    SUCCESS = "SUCCESS"
    EMPTY = "EMPTY"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID_LIBRARY = "INVALID_LIBRARY"
    INVALID_REQUEST = "INVALID_REQUEST"


class QePatternValidationStatus(StrEnum):
    HUMAN_BACKED_CANDIDATE = "HUMAN_BACKED_CANDIDATE"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class QePatternProductionStatus(StrEnum):
    ANALYSIS_ONLY = "ANALYSIS_ONLY"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class QePatternMateriality(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class SharedLearningMode(StrEnum):
    DISABLED = "DISABLED"
    SHADOW = "SHADOW"
    ENABLED = "ENABLED"


class SharedLearningContext(BaseModel):
    """Server-owned access context; never accepted from a client manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    tenant_id: str = Field(min_length=1, max_length=120)
    principal_id: str = Field(min_length=1, max_length=200)
    authenticated: StrictBool = False
    mode: SharedLearningMode = SharedLearningMode.SHADOW
    cutoff_at: datetime | None = None
    excluded_source_case_ids: set[str] = Field(default_factory=set, max_length=1000)
    benchmark_isolation: StrictBool = False

    @field_validator("tenant_id")
    @classmethod
    def normalize_tenant(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("shared learning tenant must not be blank")
        return value.strip().casefold()

    @field_validator("principal_id")
    @classmethod
    def nonblank_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("shared learning identity must not be blank")
        return value.strip()

    @field_validator("cutoff_at")
    @classmethod
    def aware_cutoff(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("shared learning cutoff must include a timezone")
        return value

    @field_validator("excluded_source_case_ids")
    @classmethod
    def normalize_exclusions(cls, values: set[str]) -> set[str]:
        if any(not value.strip() or len(value) > 200 for value in values):
            raise ValueError("source exclusions must be bounded identifiers")
        return {value.strip().upper() for value in values}


class SharedPromotionException(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["NORMATIVE_INVARIANT", "SEVERE_P0_P1"]
    rationale: str = Field(min_length=1, max_length=2000)
    evidence_refs: list[str] = Field(min_length=1, max_length=30)
    reviewer_id: str = Field(min_length=1, max_length=200)
    reviewed_at: str = Field(min_length=1, max_length=100)

    @field_validator("reviewed_at")
    @classmethod
    def review_time(cls, value: str) -> str:
        return _clean_review_timestamp(value) or ""

    @model_validator(mode="after")
    def concrete_attestation(self) -> "SharedPromotionException":
        if not self.rationale.strip() or not self.reviewer_id.strip() or any(not value.strip() or len(value) > 500 for value in self.evidence_refs):
            raise ValueError("promotion exception requires concrete reviewed evidence")
        return self


class QePatternSupportGroup(BaseModel):
    """One independently reviewed incident/case family.

    Multiple Jira variants or copied requirements may share one group.  The
    resolver counts groups, never raw case IDs, as independent support.
    """

    model_config = ConfigDict(extra="forbid")

    group_id: str = Field(min_length=1, max_length=200)
    case_ids: list[str] = Field(min_length=1, max_length=500)

    @field_validator("case_ids")
    @classmethod
    def normalize_case_ids(cls, value: list[str]) -> list[str]:
        cleaned = _clean_list(value)
        if not cleaned:
            raise ValueError("support group requires at least one case ID")
        return cleaned


class QePatternProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_kind: Literal["TRAIN_MINING_ARTIFACT", "TEST_FIXTURE", "SHARED_UAC_LEARNING"]
    source_locator: str = Field(min_length=1, max_length=500)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_schema_version: str = Field(min_length=1, max_length=200)
    derivation_partition: str = Field(min_length=1, max_length=100)
    human_backed: bool
    raw_human_uac_included: bool
    candidate_source_case_ids: list[str] = Field(default_factory=list, max_length=1000)
    approval_overlay_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    approval_authority: Literal["NONE", "HUMAN_QE"] = "NONE"
    validated_by: str | None = Field(default=None, max_length=200)
    validated_at: str | None = Field(default=None, max_length=100)
    origin_confirmed: StrictBool = False
    applicability_confirmed: StrictBool = False
    counterexamples_checked: StrictBool = False

    @field_validator("candidate_source_case_ids")
    @classmethod
    def normalize_candidate_sources(cls, value: list[str]) -> list[str]:
        return _clean_list(value)

    @field_validator("validated_by")
    @classmethod
    def normalize_reviewer(cls, value: str | None) -> str | None:
        return _clean_reviewer(value)

    @field_validator("validated_at")
    @classmethod
    def normalize_review_time(cls, value: str | None) -> str | None:
        return _clean_review_timestamp(value)


class QePatternRecord(BaseModel):
    """Normalized pattern contract exposed by the resolver."""

    model_config = ConfigDict(extra="forbid")

    pattern_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")
    pattern_version: str = Field(min_length=1, max_length=100)
    validation_status: QePatternValidationStatus
    production_status: QePatternProductionStatus
    lesson_id: str = Field(default="", max_length=200)
    lesson_kind: Literal["GENERIC_PATTERN", "SCOPED_CASE"] = "GENERIC_PATTERN"
    lesson_influence_kind: Literal["INVESTIGATION_CANDIDATE", "AUTHORING_GUIDANCE"] = "INVESTIGATION_CANDIDATE"
    promotion_exception: SharedPromotionException | None = None

    abstract_change_surface: list[str] = Field(min_length=1, max_length=50)
    applicable_domains: list[str] = Field(default_factory=list, max_length=50)
    applicable_publishing_modes: list[str] = Field(default_factory=list, max_length=50)
    applicable_configuration_states: list[str] = Field(
        default_factory=list,
        max_length=50,
    )
    abstract_signals: list[str] = Field(min_length=1, max_length=100)
    applicable_subject_terms: list[str] = Field(default_factory=list, max_length=30)
    applicable_deployment_models: list[str] = Field(default_factory=list, max_length=30)
    applicable_product_versions: list[str] = Field(default_factory=list, max_length=30)

    question_families: list[str] = Field(default_factory=list, max_length=50)
    relationship_to_explore: list[str] = Field(min_length=1, max_length=50)
    preferred_evidence_sources: list[str] = Field(default_factory=list, max_length=50)

    materiality: QePatternMateriality
    blocking_default: bool = False

    human_support_count: int = Field(ge=0)
    independent_case_count: int = Field(ge=0)
    supporting_case_ids: list[str] = Field(default_factory=list, max_length=1000)
    qualifying_human_support_case_ids: list[str] = Field(
        default_factory=list,
        max_length=1000,
    )
    independent_support_groups: list[QePatternSupportGroup] = Field(
        default_factory=list,
        max_length=500,
    )

    counterexamples: list[str] = Field(default_factory=list, max_length=100)
    hard_negatives: list[str] = Field(default_factory=list, max_length=100)
    activation_guardrails: list[str] = Field(default_factory=list, max_length=100)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    customer_specific: bool = False
    jira_specific: bool = False
    provenance: QePatternProvenance

    @field_validator(
        "abstract_change_surface",
        "applicable_domains",
        "applicable_publishing_modes",
        "applicable_configuration_states",
        "abstract_signals",
        "question_families",
        "relationship_to_explore",
        "preferred_evidence_sources",
        "supporting_case_ids",
        "qualifying_human_support_case_ids",
        "counterexamples",
        "hard_negatives",
        "activation_guardrails",
        "applicable_subject_terms",
        "applicable_deployment_models",
        "applicable_product_versions",
    )
    @classmethod
    def normalize_string_lists(cls, value: list[str]) -> list[str]:
        return _clean_list(value)

    @model_validator(mode="after")
    def validate_support_and_authority(self) -> "QePatternRecord":
        shared = self.provenance.source_kind == "SHARED_UAC_LEARNING"
        editorial = self.lesson_influence_kind == "AUTHORING_GUIDANCE"
        if editorial and (not shared or self.question_families):
            raise ValueError("authoring guidance cannot define investigation families")
        if not editorial and not self.question_families:
            raise ValueError("investigation patterns require question families")
        if self.human_support_count != len(self.qualifying_human_support_case_ids):
            raise ValueError(
                "human_support_count must equal qualifying Human support case IDs"
            )
        if not set(self.qualifying_human_support_case_ids).issubset(
            set(self.supporting_case_ids)
        ):
            raise ValueError(
                "qualifying Human support case IDs must exist in supporting_case_ids"
            )
        group_ids = [group.group_id for group in self.independent_support_groups]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("independent support group IDs must be unique")
        if self.independent_case_count != len(self.independent_support_groups):
            raise ValueError(
                "independent_case_count must equal independent support groups"
            )
        grouped_case_sequence = [
            case_id
            for group in self.independent_support_groups
            for case_id in group.case_ids
        ]
        if len(grouped_case_sequence) != len(set(grouped_case_sequence)):
            raise ValueError(
                "a qualifying case ID may belong to only one independent support group"
            )
        grouped_cases = set(grouped_case_sequence)
        if not grouped_cases.issubset(set(self.qualifying_human_support_case_ids)):
            raise ValueError(
                "support-group case IDs must be qualifying Human support cases"
            )
        if grouped_cases != set(self.qualifying_human_support_case_ids):
            raise ValueError(
                "every qualifying Human support case must belong to exactly one support group"
            )
        if self.production_status == QePatternProductionStatus.ACTIVE:
            if self.validation_status != QePatternValidationStatus.APPROVED:
                raise ValueError("only approved patterns may be ACTIVE")
            if not self.provenance.human_backed:
                raise ValueError("ACTIVE patterns require Human-backed provenance")
            if self.provenance.approval_authority != "HUMAN_QE":
                raise ValueError("ACTIVE patterns require Human QE approval provenance")
            if not self.provenance.validated_by or not self.provenance.validated_at:
                raise ValueError("ACTIVE patterns require reviewer and review time")
            if not self.provenance.approval_overlay_sha256:
                raise ValueError("ACTIVE patterns require a versioned approval overlay")
            if self.independent_case_count < 1:
                raise ValueError("ACTIVE patterns require independent Human support")
            if not self.applicable_domains:
                raise ValueError(
                    "ACTIVE patterns require at least one applicable domain"
                )
            if self.confidence is None:
                raise ValueError("ACTIVE patterns require reviewed confidence")
        if shared:
            expected_pattern_id = "SHARED_" + hashlib.sha256(
                # The provider uses the canonical JSON string representation.
                json.dumps(self.lesson_id, sort_keys=True,
                    separators=(",", ":")).encode()
            ).hexdigest()[:32].upper()
            if self.pattern_id != expected_pattern_id:
                raise ValueError("shared pattern identity must be bound to its lesson")
            if not self.lesson_id or not all((self.provenance.origin_confirmed,
                    self.provenance.applicability_confirmed, self.provenance.counterexamples_checked)):
                raise ValueError("shared lessons require complete Human approval")
            if self.provenance.raw_human_uac_included or self.customer_specific or self.jira_specific:
                raise ValueError("shared lessons cannot expose raw UAC or activate from identities")
            semantics = [*self.abstract_change_surface, *self.abstract_signals,
                *self.relationship_to_explore, *self.applicable_subject_terms,
                *self.applicable_publishing_modes, *self.applicable_configuration_states,
                *self.applicable_deployment_models, *self.applicable_product_versions]
            if any(len(value) > 2000 or re.search(r"\b[A-Z][A-Z0-9]+-\d+\b", value, re.I) for value in semantics):
                raise ValueError("shared lesson semantics must be bounded and cannot contain Jira identities")
            if self.blocking_default:
                raise ValueError("shared lessons cannot independently block acceptance")
            if self.lesson_kind == "SCOPED_CASE" and not any((self.applicable_subject_terms,
                    self.applicable_publishing_modes, self.applicable_configuration_states,
                    self.applicable_deployment_models, self.applicable_product_versions)):
                raise ValueError("single-case lessons require concrete scope qualifiers")
            if self.lesson_kind == "GENERIC_PATTERN" and self.independent_case_count < 2 and not self.promotion_exception:
                raise ValueError("generic shared patterns require independent support or a reviewed exception")
            if self.promotion_exception:
                if self.promotion_exception.reviewer_id != self.provenance.validated_by:
                    raise ValueError("exception must be bound to the approving reviewer")
                if datetime.fromisoformat(self.promotion_exception.reviewed_at.replace("Z", "+00:00")) > datetime.fromisoformat((self.provenance.validated_at or "").replace("Z", "+00:00")):
                    raise ValueError("exception must be reviewed before lesson approval")
                if self.promotion_exception.kind == "SEVERE_P0_P1" and self.materiality not in {QePatternMateriality.P0, QePatternMateriality.P1}:
                    raise ValueError("severe exception requires P0 or P1 materiality")
        return self

    @property
    def production_influence_allowed(self) -> bool:
        return (
            self.validation_status == QePatternValidationStatus.APPROVED
            and self.production_status == QePatternProductionStatus.ACTIVE
            and self.provenance.approval_authority == "HUMAN_QE"
            and not self.customer_specific
            and not self.jira_specific
            and self.lesson_influence_kind == "INVESTIGATION_CANDIDATE"
        )


class QePatternScopeConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explicit_out_of_scope: list[str] = Field(default_factory=list, max_length=100)
    excluded_relationships: list[str] = Field(default_factory=list, max_length=100)
    current_product_decisions: list[str] = Field(default_factory=list, max_length=100)

    @field_validator(
        "explicit_out_of_scope",
        "excluded_relationships",
        "current_product_decisions",
    )
    @classmethod
    def normalize_constraints(cls, value: list[str]) -> list[str]:
        return _clean_list(value)


class ResolveQePatternsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str = Field(min_length=1, max_length=100)
    change_surfaces: list[str] = Field(default_factory=list, max_length=100)
    abstract_signals: list[str] = Field(default_factory=list, max_length=100)
    publishing_mode: str | None = Field(default=None, max_length=100)
    configuration_state: str | None = Field(default=None, max_length=200)
    current_jira_key: str = Field(default="", max_length=64)
    subject_terms: list[str] = Field(default_factory=list, max_length=30)
    deployment_model: str | None = Field(default=None, max_length=100)
    product_version: str | None = Field(default=None, max_length=100)
    scope_constraints: QePatternScopeConstraints = Field(
        default_factory=QePatternScopeConstraints
    )
    include_analysis_candidates: StrictBool = False
    max_results: int = Field(default=10, ge=1, le=50)

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("domain must not be blank")
        return cleaned

    @field_validator("publishing_mode", "configuration_state", "deployment_model", "product_version")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("change_surfaces", "abstract_signals", "subject_terms")
    @classmethod
    def normalize_request_lists(cls, value: list[str]) -> list[str]:
        if any(len(item) > 500 for item in value):
            raise ValueError("pattern relevance terms must be bounded")
        return _clean_list(value)

    @model_validator(mode="after")
    def require_abstract_input(self) -> "ResolveQePatternsRequest":
        if not self.change_surfaces and not self.abstract_signals:
            raise ValueError(
                "at least one change surface or abstract signal is required"
            )
        return self


class QePatternMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern: QePatternRecord
    match_reason: list[str] = Field(default_factory=list)
    applicability_score: float = Field(ge=0.0, le=1.0)
    counterexample_conflicts: list[str] = Field(default_factory=list)
    recommended_families: list[str] = Field(default_factory=list)
    blocking_recommendations: list[str] = Field(default_factory=list)
    influence_allowed: bool


class QePatternSuppressedMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")
    reason_codes: list[str] = Field(min_length=1, max_length=100)
    counterexample_conflicts: list[str] = Field(default_factory=list, max_length=100)
    recommended_families: list[str] = Field(default_factory=list, max_length=50)
    relationship_to_explore: list[str] = Field(default_factory=list, max_length=50)
    preferred_evidence_sources: list[str] = Field(default_factory=list, max_length=50)
    materiality: QePatternMateriality | None = None
    blocking_default: bool = False
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    applicability_score: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator(
        "reason_codes",
        "counterexample_conflicts",
        "recommended_families",
        "relationship_to_explore",
        "preferred_evidence_sources",
    )
    @classmethod
    def normalize_suppressed_values(cls, value: list[str]) -> list[str]:
        return _clean_list(value)


class SharedAuthoringGuidance(BaseModel):
    """Editorial context, explicitly not proof that a writer applied it."""

    model_config = ConfigDict(extra="forbid")
    lesson_id: str = Field(min_length=1, max_length=200)
    lesson_version: str = Field(min_length=1, max_length=100)
    lesson_kind: Literal["GENERIC_PATTERN", "SCOPED_CASE"]
    guidance: str = Field(min_length=1, max_length=2000)
    publication_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    consumption_state: Literal["RETRIEVED_NOT_APPLIED"] = "RETRIEVED_NOT_APPLIED"


class SharedLearningEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: SharedLearningMode = SharedLearningMode.SHADOW
    status: Literal["DISABLED", "SUCCESS", "EMPTY", "UNAVAILABLE", "INVALID_LIBRARY", "INVALID_REQUEST"]
    publication_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    pattern_count: int = Field(default=0, ge=0, le=500)
    matched_patterns: list[QePatternMatch] = Field(default_factory=list, max_length=50)
    suppressed_patterns: list[QePatternSuppressedMatch] = Field(default_factory=list, max_length=500)
    shadow_pattern_ids: list[str] = Field(default_factory=list, max_length=50)
    shadow_suppressed_pattern_ids: list[str] = Field(default_factory=list, max_length=500)
    authoring_guidance: list[SharedAuthoringGuidance] = Field(default_factory=list, max_length=50)
    shadow_authoring_guidance_ids: list[str] = Field(default_factory=list, max_length=50)
    excluded_pattern_counts: dict[str, int] = Field(default_factory=dict, max_length=50)
    warnings: list[str] = Field(default_factory=list, max_length=100)
    error_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{2,127}$")

    @model_validator(mode="after")
    def validate_influence(self) -> "SharedLearningEnvelope":
        influence = bool(self.matched_patterns or self.suppressed_patterns or self.authoring_guidance)
        if self.mode != SharedLearningMode.ENABLED and influence:
            raise ValueError("disabled or shadow shared learning cannot influence generation")
        if self.status not in {"SUCCESS", "EMPTY"} and influence:
            raise ValueError("failed shared lookup cannot carry influence")
        if influence and not self.publication_id:
            raise ValueError("shared influence requires a publication identity")
        for match in self.matched_patterns:
            if match.pattern.provenance.source_kind != "SHARED_UAC_LEARNING" or match.pattern.provenance.source_sha256 != self.publication_id:
                raise ValueError("shared pattern must be bound to its publication")
        shared_ids = [row.pattern_id for row in self.suppressed_patterns]
        shared_ids.extend(self.shadow_pattern_ids)
        shared_ids.extend(self.shadow_suppressed_pattern_ids)
        if any(re.fullmatch(r"SHARED_[A-F0-9]{32}", value) is None for value in shared_ids):
            raise ValueError("shared result identities cannot target baseline patterns")
        if any(row.publication_id != self.publication_id for row in self.authoring_guidance):
            raise ValueError("editorial guidance must be bound to its publication")
        return self


class ResolveQePatternsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-qe-pattern-mcp-v1"] = PATTERN_MCP_SCHEMA_VERSION
    provider_name: Literal["TRAIN_V2_PATTERN_ADAPTER", "SHARED_UAC_LEARNING"] = "TRAIN_V2_PATTERN_ADAPTER"
    provider_status: QePatternProviderStatus
    pattern_library_version: str
    pattern_library_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    pattern_count: int = Field(ge=0)
    validated_production_pattern_count: int = Field(ge=0)
    matched_patterns: list[QePatternMatch] = Field(default_factory=list)
    suppressed_patterns: list[QePatternSuppressedMatch] = Field(default_factory=list)
    excluded_pattern_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{2,127}$",
    )
    shared_learning: SharedLearningEnvelope | None = None
