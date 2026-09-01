"""Conservative, feature-neutral routing policy for FluffyJaws second pass.

The policy is deliberately pure: it evaluates canonical question and local
evidence state, and it never performs provider I/O or mutates canonical
reasoning objects.  Runtime dispatch details are added later through a bounded
routing record.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.schemas_canonical_test_plan_runtime import (
    AuthorityClass,
    AuthoritySubject,
    CanonicalEvidenceBundle,
    CurrentnessState,
    DirectedRetrievalRecord,
    EvidenceLifecycleStatus,
    EvidenceRecord,
    EvidenceSourceType,
    MissingQuestion,
    RetrievalStatus,
    VerificationState,
    stable_sha256,
)
from app.services.reasoning_evidence_provider import QueryMateriality


FLUFFYJAWS_ROUTING_RECORD_SCHEMA = "aem-guides-fluffyjaws-routing-record-v1"
STRONG_LOCAL_EVIDENCE_THRESHOLD = 0.8


class FluffyJawsRoutingSignal(StrEnum):
    MATERIAL_QUESTION = "MATERIAL_QUESTION"
    LOCAL_RETRIEVAL_EMPTY = "LOCAL_RETRIEVAL_EMPTY"
    LOCAL_RETRIEVAL_LOW_CONFIDENCE = "LOCAL_RETRIEVAL_LOW_CONFIDENCE"
    AUTHORITATIVE_INTERNAL_PRODUCT_CONTEXT_MISSING = (
        "AUTHORITATIVE_INTERNAL_PRODUCT_CONTEXT_MISSING"
    )
    UNRESOLVED_P0_OR_P1 = "UNRESOLVED_P0_OR_P1"
    MATERIAL_EVIDENCE_CONFLICT = "MATERIAL_EVIDENCE_CONFLICT"


class FluffyJawsNoCallReason(StrEnum):
    NOT_MATERIAL_QUESTION = "NOT_MATERIAL_QUESTION"
    LOCAL_EVIDENCE_SUFFICIENT = "LOCAL_EVIDENCE_SUFFICIENT"
    QUESTION_BUDGET_EXCEEDED = "QUESTION_BUDGET_EXCEEDED"
    TOTAL_TIMEOUT_EXHAUSTED = "TOTAL_TIMEOUT_EXHAUSTED"
    NO_ALLOWED_TARGET_SOURCE = "NO_ALLOWED_TARGET_SOURCE"
    QUERY_EGRESS_POLICY_DENIED = "QUERY_EGRESS_POLICY_DENIED"
    QUERY_OR_REGISTRY_ERROR = "QUERY_OR_REGISTRY_ERROR"
    PROVIDER_EXECUTOR_ERROR = "PROVIDER_EXECUTOR_ERROR"
    NO_ELIGIBLE_PROVIDER = "NO_ELIGIBLE_PROVIDER"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    CIRCUIT_HALF_OPEN = "CIRCUIT_HALF_OPEN"
    BLIND_REPLAY_BLOCKED = "BLIND_REPLAY_BLOCKED"
    CONFIG_UNAVAILABLE = "CONFIG_UNAVAILABLE"


class FluffyJawsLocalResultStatus(StrEnum):
    MISSING = "MISSING"
    USED = RetrievalStatus.USED.value
    REJECTED = RetrievalStatus.REJECTED.value
    UNAVAILABLE = RetrievalStatus.UNAVAILABLE.value


_MATERIALITIES = {QueryMateriality.P0, QueryMateriality.P1}
_HIGH_AUTHORITY_CLASSES = {
    AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT,
    AuthorityClass.CONFIRMED_PRODUCT_DECISION,
    AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
    AuthorityClass.SPECIFICATION_AUTHORITY,
    AuthorityClass.IMPLEMENTATION_CONFIRMED,
}
_EXPECTED_AUTHORITIES: dict[AuthoritySubject, set[AuthorityClass]] = {
    AuthoritySubject.PRODUCT_CONTRACT: {
        AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT,
        AuthorityClass.CONFIRMED_PRODUCT_DECISION,
        AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
    },
    AuthoritySubject.DITA_SEMANTICS: {
        AuthorityClass.SPECIFICATION_AUTHORITY,
        AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
    },
    AuthoritySubject.ACTUAL_IMPLEMENTATION: {
        AuthorityClass.IMPLEMENTATION_CONFIRMED,
    },
    AuthoritySubject.CURRENT_UI: {
        AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
        AuthorityClass.IMPLEMENTATION_CONFIRMED,
    },
}
_UNUSABLE_LIFECYCLES = {
    EvidenceLifecycleStatus.REJECTED,
    EvidenceLifecycleStatus.UNAVAILABLE,
    EvidenceLifecycleStatus.IGNORED_BY_COMPATIBILITY_PATH,
}
_VERIFIED_STATES = {
    VerificationState.CONFIRMED,
    VerificationState.VERIFIED_LIVE,
    VerificationState.VERIFIED_REVISION,
    VerificationState.VERIFIED_SOURCE,
}
_CURRENT_STATES = {
    CurrentnessState.CURRENT,
    CurrentnessState.VERSION_SPECIFIC,
    CurrentnessState.ENVIRONMENT_SPECIFIC,
}


class FluffyJawsExpectedEvidenceClass(BaseModel):
    """Question-scoped evidence class; contains no provider or feature name."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    authority_subject: AuthoritySubject
    source_types: list[EvidenceSourceType] = Field(default_factory=list)
    authority_classes: list[AuthorityClass] = Field(default_factory=list)

    @field_validator("source_types", "authority_classes")
    @classmethod
    def normalize_enums(cls, values: list[StrEnum]) -> list[StrEnum]:
        return sorted(set(values), key=lambda value: value.value)


class FluffyJawsRoutingBudget(BaseModel):
    """Deterministic allocation snapshot, not a live timer or credential."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    eligible_priority: int | None = Field(default=None, ge=1, le=10_000)
    max_questions: int = Field(ge=1, le=50)
    max_results: int = Field(ge=1, le=100)
    call_timeout_seconds: float = Field(gt=0.0, le=300.0)
    total_timeout_seconds: float = Field(gt=0.0, le=900.0)
    within_question_budget: bool = False

    @model_validator(mode="after")
    def validate_allocation(self) -> "FluffyJawsRoutingBudget":
        expected = (
            self.eligible_priority is not None
            and self.eligible_priority <= self.max_questions
        )
        if self.within_question_budget != expected:
            raise ValueError("within_question_budget does not match eligible priority")
        return self


class FluffyJawsRoutingEvaluation(BaseModel):
    """Pure policy result before runtime/provider gates are applied."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str = Field(min_length=1)
    materiality: QueryMateriality
    local_result_status: FluffyJawsLocalResultStatus
    policy_eligible: bool
    eligibility_signals: list[FluffyJawsRoutingSignal] = Field(default_factory=list)
    policy_skip_reason: FluffyJawsNoCallReason | None = None
    expected_evidence_class: FluffyJawsExpectedEvidenceClass
    local_matched_evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("eligibility_signals", "local_matched_evidence_ids")
    @classmethod
    def normalize_sets(cls, values: list[StrEnum] | list[str]) -> list:
        return sorted(set(values), key=str)

    @model_validator(mode="after")
    def validate_decision(self) -> "FluffyJawsRoutingEvaluation":
        material = FluffyJawsRoutingSignal.MATERIAL_QUESTION in self.eligibility_signals
        deficiencies = set(self.eligibility_signals) - {
            FluffyJawsRoutingSignal.MATERIAL_QUESTION
        }
        if self.policy_eligible != (material and bool(deficiencies)):
            raise ValueError("routing eligibility must require materiality and a deficiency")
        if self.policy_eligible and self.policy_skip_reason is not None:
            raise ValueError("eligible routing evaluation cannot have a policy skip")
        if not self.policy_eligible and self.policy_skip_reason is None:
            raise ValueError("ineligible routing evaluation requires a policy skip")
        return self


class FluffyJawsRoutingRecord(BaseModel):
    """Content-minimal, final record of one SECOND_PASS routing decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["aem-guides-fluffyjaws-routing-record-v1"] = (
        FLUFFYJAWS_ROUTING_RECORD_SCHEMA
    )
    question_id: str = Field(min_length=1)
    materiality: QueryMateriality
    local_result_status: FluffyJawsLocalResultStatus
    why_fj_called: list[FluffyJawsRoutingSignal] = Field(default_factory=list)
    why_fj_not_called: list[FluffyJawsNoCallReason] = Field(default_factory=list)
    expected_evidence_class: FluffyJawsExpectedEvidenceClass
    budget: FluffyJawsRoutingBudget
    trace_id: str = Field(pattern=r"^fj-route:[a-f0-9]{32}$")
    policy_eligible: bool
    provider_called: bool
    eligibility_signals: list[FluffyJawsRoutingSignal] = Field(default_factory=list)
    local_matched_evidence_ids: list[str] = Field(default_factory=list)

    @field_validator(
        "why_fj_called",
        "why_fj_not_called",
        "eligibility_signals",
        "local_matched_evidence_ids",
    )
    @classmethod
    def normalize_sets(cls, values: list[StrEnum] | list[str]) -> list:
        return sorted(set(values), key=str)

    @model_validator(mode="after")
    def validate_call_exclusivity(self) -> "FluffyJawsRoutingRecord":
        if self.provider_called:
            if not self.policy_eligible or not self.why_fj_called:
                raise ValueError("a provider call requires an eligible reason")
            if self.why_fj_not_called:
                raise ValueError("a provider call cannot have a no-call reason")
        else:
            if self.why_fj_called:
                raise ValueError("a no-call record cannot claim FluffyJaws was called")
            if len(self.why_fj_not_called) != 1:
                raise ValueError("a no-call record requires exactly one bounded reason")
        if self.policy_eligible and not (
            FluffyJawsRoutingSignal.MATERIAL_QUESTION in self.eligibility_signals
            and len(self.eligibility_signals) > 1
        ):
            raise ValueError("eligible record requires materiality and a deficiency")
        return self


def _usable_matched_records(
    local: DirectedRetrievalRecord | None,
    bundle: CanonicalEvidenceBundle,
) -> list[EvidenceRecord]:
    if local is None or local.status != RetrievalStatus.USED:
        return []
    by_id = {record.evidence_id: record for record in bundle.records}
    return [
        by_id[evidence_id]
        for evidence_id in local.matched_evidence_ids
        if evidence_id in by_id
        and by_id[evidence_id].lifecycle_status not in _UNUSABLE_LIFECYCLES
    ]


def _record_has_expected_authority(
    question: MissingQuestion,
    record: EvidenceRecord,
) -> bool:
    accepted = _EXPECTED_AUTHORITIES.get(
        question.authority_subject, _HIGH_AUTHORITY_CLASSES
    )
    targets = set(question.target_source_types)
    return bool(
        record.authority_subject == question.authority_subject
        and (not targets or record.source_type in targets)
        and record.requirement_authority in accepted
        and record.verification_status in _VERIFIED_STATES
        and record.currentness in _CURRENT_STATES
    )


def _has_expected_authority(
    question: MissingQuestion,
    records: list[EvidenceRecord],
) -> bool:
    return any(_record_has_expected_authority(question, record) for record in records)


def _has_sufficient_local_record(
    question: MissingQuestion,
    records: list[EvidenceRecord],
) -> bool:
    """Require confidence, authority, verification, and currency on one record."""

    return any(
        record.evidence_confidence >= STRONG_LOCAL_EVIDENCE_THRESHOLD
        and _record_has_expected_authority(question, record)
        for record in records
    )


def _has_material_conflict(
    question: MissingQuestion,
    records: list[EvidenceRecord],
    bundle: CanonicalEvidenceBundle,
) -> bool:
    if not records:
        return False
    matched_ids = {record.evidence_id for record in records}
    matched_claims = {claim for record in records for claim in record.claim_keys}
    if any(
        record.currentness == CurrentnessState.CONFLICTING_CURRENTNESS
        for record in records
    ):
        return True
    if matched_claims & set(bundle.currentness_conflicts):
        return True
    return any(
        conflict.subject == question.authority_subject
        and (
            bool(
                matched_ids
                & (
                    set(conflict.selected_evidence_ids)
                    | set(conflict.competing_evidence_ids)
                )
            )
            or conflict.claim_key in matched_claims
        )
        for conflict in bundle.authority_conflicts
    )


class ConservativeFluffyJawsRoutingPolicy:
    """Evaluate only canonical evidence signals; never inspect feature text."""

    def evaluate(
        self,
        *,
        question: MissingQuestion,
        local: DirectedRetrievalRecord | None,
        bundle: CanonicalEvidenceBundle,
        materiality: QueryMateriality,
    ) -> FluffyJawsRoutingEvaluation:
        records = _usable_matched_records(local, bundle)
        material = materiality in _MATERIALITIES
        has_high_confidence = any(
            record.evidence_confidence >= STRONG_LOCAL_EVIDENCE_THRESHOLD
            for record in records
        )
        has_expected_authority = _has_expected_authority(question, records)
        has_sufficient_local_record = _has_sufficient_local_record(
            question, records
        )
        has_conflict = _has_material_conflict(question, records, bundle)
        locally_resolved = (
            bool(records)
            and has_sufficient_local_record
            and not has_conflict
        )

        signals: list[FluffyJawsRoutingSignal] = []
        if material:
            signals.append(FluffyJawsRoutingSignal.MATERIAL_QUESTION)
        if not records:
            signals.append(FluffyJawsRoutingSignal.LOCAL_RETRIEVAL_EMPTY)
        elif not has_high_confidence:
            signals.append(
                FluffyJawsRoutingSignal.LOCAL_RETRIEVAL_LOW_CONFIDENCE
            )
        if not has_expected_authority:
            signals.append(
                FluffyJawsRoutingSignal.AUTHORITATIVE_INTERNAL_PRODUCT_CONTEXT_MISSING
            )
        if material and not locally_resolved:
            signals.append(FluffyJawsRoutingSignal.UNRESOLVED_P0_OR_P1)
        if has_conflict:
            signals.append(FluffyJawsRoutingSignal.MATERIAL_EVIDENCE_CONFLICT)

        deficiencies = set(signals) - {FluffyJawsRoutingSignal.MATERIAL_QUESTION}
        eligible = material and bool(deficiencies)
        if eligible:
            skip_reason = None
        elif not material:
            skip_reason = FluffyJawsNoCallReason.NOT_MATERIAL_QUESTION
        else:
            skip_reason = FluffyJawsNoCallReason.LOCAL_EVIDENCE_SUFFICIENT

        return FluffyJawsRoutingEvaluation(
            question_id=question.question_id,
            materiality=materiality,
            local_result_status=(
                FluffyJawsLocalResultStatus.MISSING
                if local is None
                else FluffyJawsLocalResultStatus(local.status.value)
            ),
            policy_eligible=eligible,
            eligibility_signals=signals,
            policy_skip_reason=skip_reason,
            expected_evidence_class=FluffyJawsExpectedEvidenceClass(
                authority_subject=question.authority_subject,
                source_types=question.target_source_types,
                authority_classes=sorted(
                    _EXPECTED_AUTHORITIES.get(
                        question.authority_subject, _HIGH_AUTHORITY_CLASSES
                    ),
                    key=lambda value: value.value,
                ),
            ),
            local_matched_evidence_ids=(
                list(local.matched_evidence_ids) if local is not None else []
            ),
        )


def build_fluffyjaws_routing_record(
    *,
    evaluation: FluffyJawsRoutingEvaluation,
    budget: FluffyJawsRoutingBudget,
    run_id: str,
    request_id: str,
    mode: str,
    provider_called: bool,
    no_call_reason: FluffyJawsNoCallReason | None = None,
) -> FluffyJawsRoutingRecord:
    """Finalize an evaluation after all runtime gates, using safe trace fields."""

    if provider_called:
        why_called = list(evaluation.eligibility_signals)
        why_not_called: list[FluffyJawsNoCallReason] = []
    else:
        why_called = []
        reason = no_call_reason or evaluation.policy_skip_reason
        if reason is None:
            raise ValueError("eligible no-call routing record requires a runtime reason")
        why_not_called = [reason]
    trace_projection = {
        "schema": FLUFFYJAWS_ROUTING_RECORD_SCHEMA,
        "run_id": run_id,
        "request_id": request_id,
        "mode": mode,
        "question_id": evaluation.question_id,
        "materiality": evaluation.materiality.value,
        "local_result_status": evaluation.local_result_status.value,
        "signals": [value.value for value in evaluation.eligibility_signals],
        "why_not_called": [value.value for value in why_not_called],
        "provider_called": provider_called,
        "budget": budget.model_dump(mode="json"),
    }
    return FluffyJawsRoutingRecord(
        question_id=evaluation.question_id,
        materiality=evaluation.materiality,
        local_result_status=evaluation.local_result_status,
        why_fj_called=why_called,
        why_fj_not_called=why_not_called,
        expected_evidence_class=evaluation.expected_evidence_class,
        budget=budget,
        trace_id=f"fj-route:{stable_sha256(trace_projection)[:32]}",
        policy_eligible=evaluation.policy_eligible,
        provider_called=provider_called,
        eligibility_signals=evaluation.eligibility_signals,
        local_matched_evidence_ids=evaluation.local_matched_evidence_ids,
    )


__all__ = [
    "FLUFFYJAWS_ROUTING_RECORD_SCHEMA",
    "STRONG_LOCAL_EVIDENCE_THRESHOLD",
    "ConservativeFluffyJawsRoutingPolicy",
    "FluffyJawsExpectedEvidenceClass",
    "FluffyJawsLocalResultStatus",
    "FluffyJawsNoCallReason",
    "FluffyJawsRoutingBudget",
    "FluffyJawsRoutingEvaluation",
    "FluffyJawsRoutingRecord",
    "FluffyJawsRoutingSignal",
    "build_fluffyjaws_routing_record",
]
