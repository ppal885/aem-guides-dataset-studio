"""Provider-neutral contracts for Human-backed QE reasoning patterns.

The Pattern MCP is discovery-only.  Its records can recommend question families
and relationships to investigate, but they cannot define a current Jira's
acceptance contract or final AC wording.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
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

    source_kind: Literal["TRAIN_MINING_ARTIFACT", "TEST_FIXTURE"]
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

    abstract_change_surface: list[str] = Field(min_length=1, max_length=50)
    applicable_domains: list[str] = Field(default_factory=list, max_length=50)
    applicable_publishing_modes: list[str] = Field(default_factory=list, max_length=50)
    applicable_configuration_states: list[str] = Field(
        default_factory=list,
        max_length=50,
    )
    abstract_signals: list[str] = Field(min_length=1, max_length=100)

    question_families: list[str] = Field(min_length=1, max_length=50)
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
    )
    @classmethod
    def normalize_string_lists(cls, value: list[str]) -> list[str]:
        return _clean_list(value)

    @model_validator(mode="after")
    def validate_support_and_authority(self) -> "QePatternRecord":
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
        return self

    @property
    def production_influence_allowed(self) -> bool:
        return (
            self.validation_status == QePatternValidationStatus.APPROVED
            and self.production_status == QePatternProductionStatus.ACTIVE
            and self.provenance.approval_authority == "HUMAN_QE"
            and not self.customer_specific
            and not self.jira_specific
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

    @field_validator("publishing_mode", "configuration_state")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("change_surfaces", "abstract_signals")
    @classmethod
    def normalize_request_lists(cls, value: list[str]) -> list[str]:
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


class ResolveQePatternsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-qe-pattern-mcp-v1"] = PATTERN_MCP_SCHEMA_VERSION
    provider_name: Literal["TRAIN_V2_PATTERN_ADAPTER"] = "TRAIN_V2_PATTERN_ADAPTER"
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
