"""Strict, provider-neutral contracts for shared Human UAC feedback."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class LearningDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UacClientContext(LearningDTO):
    client: Literal["claude_desktop", "codex", "api", "unknown"] = "unknown"
    session_id: str = Field(default="", max_length=160)
    message_id: str = Field(default="", max_length=160)


class UacDraftContent(LearningDTO):
    draft_markdown: str = Field(min_length=1, max_length=100_000)
    criteria: dict[str, str] = Field(default_factory=dict, max_length=200)
    evidence_bundle_id: str = Field(default="", max_length=180)
    run_id: str = Field(default="", max_length=160)
    client_context: UacClientContext = Field(default_factory=UacClientContext)

    @field_validator("criteria")
    @classmethod
    def bounded_criteria(cls, value):
        if any(not key.strip() or len(key) > 120 or not text.strip() or len(text) > 12_000
               for key, text in value.items()):
            raise ValueError("Criteria require nonempty bounded IDs and text.")
        return value


class UacDraftRegistration(UacDraftContent):
    tenant_id: str = Field(default="kone", max_length=120)
    jira_key: str = Field(min_length=3, max_length=64)
    plan_fingerprint: str = Field(default="", pattern=r"^$|^[a-f0-9]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=240)


DeltaType = Literal[
    "UNCLASSIFIED", "COVERAGE_ADDED", "COVERAGE_REMOVED", "SCOPE_NARROWED",
    "SCOPE_EXPANDED", "DISPOSITION_CHANGED", "OPEN_QUESTION_ADDED",
    "OPEN_QUESTION_REMOVED", "LANGUAGE_SIMPLIFIED", "AC_MERGED", "AC_SPLIT",
    "ORACLE_CHANGED", "PRIORITY_CHANGED", "IMPLEMENTATION_DETAIL_REMOVED",
]


class UacFeedbackCapture(LearningDTO):
    contract_version: Literal["shared-uac-feedback-v1"] = "shared-uac-feedback-v1"
    tenant_id: str = Field(default="kone", max_length=120)
    jira_key: str = Field(min_length=3, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=240)
    raw_feedback: str = Field(min_length=1, max_length=12_000)
    source_kind: Literal["HUMAN_CORRECTION", "AI_PROPOSAL", "UNCONFIRMED"] = "UNCONFIRMED"
    proposed_correction: str = Field(default="", max_length=12_000)
    delta_type: DeltaType = "UNCLASSIFIED"
    ai_classification: dict[str, Any] = Field(default_factory=dict, max_length=20)
    draft_id: str = Field(default="", max_length=36)
    plan_fingerprint: str = Field(default="", pattern=r"^$|^[a-f0-9]{64}$")
    evidence_bundle_id: str = Field(default="", max_length=180)
    run_id: str = Field(default="", max_length=160)
    ac_id: str = Field(default="", max_length=120)
    draft: UacDraftContent | None = None
    client_context: UacClientContext = Field(default_factory=UacClientContext)


class UacFeedbackBind(LearningDTO):
    tenant_id: str = Field(default="kone", max_length=120)
    draft_id: str = Field(min_length=1, max_length=36)
    idempotency_key: str = Field(min_length=1, max_length=240)


class UacLessonScope(LearningDTO):
    publishing_modes: list[str] = Field(default_factory=list, max_length=30)
    configuration_states: list[str] = Field(default_factory=list, max_length=30)
    subject_terms: list[str] = Field(default_factory=list, max_length=30)
    jira_keys: list[str] = Field(default_factory=list, max_length=30)
    deployment_models: list[str] = Field(default_factory=list, max_length=30)
    product_versions: list[str] = Field(default_factory=list, max_length=30)


class UacSupportGroup(LearningDTO):
    group_id: str = Field(min_length=1, max_length=200)
    case_ids: list[str] = Field(min_length=1, max_length=1000)


class UacExceptionAttestation(LearningDTO):
    kind: Literal["NORMATIVE_INVARIANT", "SEVERE_P0_P1"]
    rationale: str = Field(min_length=1, max_length=2000)
    evidence_refs: list[str] = Field(min_length=1, max_length=30)


class UacLessonDefinition(LearningDTO):
    kind: Literal["SCOPED_CASE", "GENERIC_PATTERN"] = "SCOPED_CASE"
    guidance: str = Field(min_length=1, max_length=2000)
    delta_type: DeltaType = "UNCLASSIFIED"
    domains: list[str] = Field(default_factory=list, max_length=30)
    surfaces: list[str] = Field(default_factory=list, max_length=30)
    signals: list[str] = Field(default_factory=list, max_length=30)
    families: list[str] = Field(default_factory=list, max_length=30)
    scope: UacLessonScope = Field(default_factory=UacLessonScope)
    preferred_evidence: list[str] = Field(default_factory=list, max_length=30)
    confidence: float = Field(default=0.7, ge=0, le=1)
    materiality: Literal["P0", "P1", "P2", "P3"] = "P2"
    supporting_delta_ids: list[str] = Field(default_factory=list, max_length=100)
    independent_support_groups: list[UacSupportGroup] = Field(default_factory=list, max_length=100)
    counterexamples: list[str] = Field(default_factory=list, max_length=30)
    hard_negatives: list[str] = Field(default_factory=list, max_length=30)
    exception_attestation: UacExceptionAttestation | None = None
    first_failed_stage: str = Field(default="", max_length=80)


class UacLessonReview(LearningDTO):
    tenant_id: str = Field(default="kone", max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=240)
    expected_revision: int = Field(ge=1)
    decision: Literal["APPROVE", "REJECT", "REVOKE", "SUPERSEDE"]
    note: str = Field(min_length=1, max_length=2000)
    lesson: UacLessonDefinition | None = None
    origin_confirmed: StrictBool = False
    applicability_confirmed: StrictBool = False
    counterexamples_checked: StrictBool = False
