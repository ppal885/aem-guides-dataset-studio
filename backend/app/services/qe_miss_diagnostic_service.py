"""Post-generation diagnosis for a missed material QE dimension.

The debugger consumes only an already-frozen canonical ``GenerationResult`` and
the existing content-minimal question retrieval trace.  It never invokes a
reasoner, retrieves evidence, changes a plan, or retains Human reference text.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from enum import StrEnum
from hashlib import sha256
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.schemas_canonical_test_plan_runtime import (
    AcceptanceCandidate,
    AcceptancePromotionDecision,
    ApplicabilityState,
    BehaviorHypothesis,
    CanonicalRuntimeStage,
    ClosureDimensionResult,
    ContractFactSet,
    CoverageDisposition,
    CoverageDispositionRecord,
    CurrentPatternApplicability,
    DirectedRetrievalRecord,
    DomainActivation,
    EvidenceSourceType,
    FamilyActivationDecision,
    GateDecision,
    GenerationResult,
    HypothesisState,
    MissingQuestion,
    PatternLookupRuntimeStatus,
    QeInvestigationPreparation,
    ReasoningPatternActivation,
    RetrievalStatus,
    SemanticDimension,
    stable_sha256,
)
from app.services.reasoning_evidence_observability import (
    QuestionRetrievalTraceBundle,
)


QE_MISS_DIAGNOSTIC_SCHEMA = "aem-guides-qe-miss-diagnostic-v1"
_RUN_ID_RE = re.compile(
    r"^run:[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$"
)
_REASON_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,95}$")
_TRACE_RECORD_ID_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_-]{0,31}:[A-Za-z0-9_.:-]{1,180}$"
)
_MAX_TRACE_IDS = 2_000
_MAX_HUMAN_REFERENCE_CHARS = 100_000
HumanReferenceState = Literal["NOT_PROVIDED", "POST_GENERATION_HASH_ONLY"]


class QeMissStage(StrEnum):
    EVIDENCE_INTAKE = "EVIDENCE_INTAKE"
    CONTRACT_FACT = "CONTRACT_FACT"
    DOMAIN = "DOMAIN"
    CHANGE_SURFACE = "CHANGE_SURFACE"
    SIGNAL = "SIGNAL"
    PATTERN_LOOKUP = "PATTERN_LOOKUP"
    PATTERN_APPLICABILITY = "PATTERN_APPLICABILITY"
    FAMILY_ACTIVATION = "FAMILY_ACTIVATION"
    CLAUDE_QUESTION = "CLAUDE_QUESTION"
    QUESTION_VALIDATOR = "QUESTION_VALIDATOR"
    ROUTING = "ROUTING"
    RETRIEVAL = "RETRIEVAL"
    NORMALIZATION = "NORMALIZATION"
    GITHUB_BLAST_RADIUS = "GITHUB_BLAST_RADIUS"
    HYPOTHESIS = "HYPOTHESIS"
    APPLICABILITY = "APPLICABILITY"
    AUTHORITY = "AUTHORITY"
    DISPOSITION = "DISPOSITION"
    SCORING = "SCORING"
    FAMILY_COMPLETENESS = "FAMILY_COMPLETENESS"
    CANDIDATE_COMPLETENESS = "CANDIDATE_COMPLETENESS"
    DEDUP = "DEDUP"
    RENDERER = "RENDERER"


QE_MISS_STAGE_ORDER: tuple[QeMissStage, ...] = tuple(QeMissStage)


class QeMissStageState(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"
    DOWNSTREAM_BLOCKED = "DOWNSTREAM_BLOCKED"


class QeMissCategory(StrEnum):
    EVIDENCE_MISS = "EVIDENCE_MISS"
    DISCOVERY_REASONING_MISS = "DISCOVERY_REASONING_MISS"
    DISPOSITION_MISS = "DISPOSITION_MISS"
    RENDERING_MISS = "RENDERING_MISS"


class DiagnosticFieldState(StrEnum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


def _normalize_reason_codes(values: Iterable[str]) -> tuple[str, ...]:
    result = tuple(sorted({str(value).strip() for value in values if str(value).strip()}))
    if any(_REASON_CODE_RE.fullmatch(value) is None for value in result):
        raise ValueError("diagnostic reason codes must use the static token format")
    return result


def _normalize_record_ids(values: Iterable[str]) -> tuple[str, ...]:
    result = tuple(sorted({str(value).strip() for value in values if str(value).strip()}))
    if len(result) > _MAX_TRACE_IDS:
        raise ValueError("diagnostic record ID limit exceeded")
    if any(_TRACE_RECORD_ID_RE.fullmatch(value) is None for value in result):
        raise ValueError("diagnostic record IDs must be typed opaque identifiers")
    return result


class DiagnosticTraceField(BaseModel):
    """Content-minimal trace projection; no source text or locators are allowed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: DiagnosticFieldState
    reason_codes: tuple[str, ...] = ()
    record_ids: tuple[str, ...] = ()

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _normalize_reason_codes(value)

    @field_validator("record_ids")
    @classmethod
    def validate_record_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _normalize_record_ids(value)


class QeMissStageObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: QeMissStage
    state: QeMissStageState
    reason_codes: tuple[str, ...] = ()
    record_ids: tuple[str, ...] = ()

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _normalize_reason_codes(value)

    @field_validator("record_ids")
    @classmethod
    def validate_record_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _normalize_record_ids(value)


class QeMissFailureClassification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    earliest_failed_stage: QeMissStage
    category: QeMissCategory
    observations: tuple[QeMissStageObservation, ...]

    @model_validator(mode="after")
    def validate_one_earliest_failure(self) -> "QeMissFailureClassification":
        if tuple(row.stage for row in self.observations) != QE_MISS_STAGE_ORDER:
            raise ValueError("QE miss observations must use the full canonical order")
        failures = [row.stage for row in self.observations if row.state == QeMissStageState.FAIL]
        if failures != [self.earliest_failed_stage]:
            raise ValueError("QE miss classification requires exactly one earliest failure")
        return self


class QeMissProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_ids: tuple[str, ...] = ()
    pattern_ids: tuple[str, ...] = ()
    question_ids: tuple[str, ...] = ()
    provider_call_ids: tuple[str, ...] = ()
    code_evidence_ids: tuple[str, ...] = ()
    candidate_ids: tuple[str, ...] = ()
    disposition_ids: tuple[str, ...] = ()
    dedup_merge_ids: tuple[str, ...] = ()
    renderer_source_ids: tuple[str, ...] = ()

    @field_validator("*")
    @classmethod
    def validate_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _normalize_record_ids(value)


class QeMissDiagnosis(BaseModel):
    """PFIX-19 explainability result with the requested field names."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["aem-guides-qe-miss-diagnostic-v1"] = (
        QE_MISS_DIAGNOSTIC_SCHEMA
    )
    PLAN_ID: str
    PLAN_ID_KIND: Literal["CANONICAL_RUN_ID"] = "CANONICAL_RUN_ID"
    PLAN_ID_NOTE: Literal["CANONICAL_PLAN_ID_NOT_DEFINED"] = (
        "CANONICAL_PLAN_ID_NOT_DEFINED"
    )
    RUN_ID: str
    REQUEST_ID: str
    OUTPUT_SHA256: str = Field(pattern=r"^[a-f0-9]{64}$")
    EXPECTED_DIMENSION: SemanticDimension
    WAS_DISCOVERED: Literal["YES", "NO"]
    EARLIEST_FAILED_STAGE: QeMissStage
    MISS_CATEGORY: QeMissCategory
    WHY_IT_FAILED: str = Field(min_length=1, max_length=500)
    EVIDENCE: tuple[str, ...] = ()
    DOWNSTREAM_EFFECT: str = Field(min_length=1, max_length=500)
    GENERIC_FIX_LAYER: str = Field(min_length=1, max_length=300)
    DO_NOT_FIX_HERE: str = Field(min_length=1, max_length=300)
    HUMAN_REFERENCE_STATE: HumanReferenceState
    HUMAN_REFERENCE_SHA256: str = Field(default="", pattern=r"^(?:[a-f0-9]{64})?$")
    AUTO_MUTATION: Literal[False] = False

    EVIDENCE_PRESENT: DiagnosticTraceField
    CONTRACT_FACT_PRESENT: DiagnosticTraceField
    DOMAIN: DiagnosticTraceField
    CHANGE_SURFACES: DiagnosticTraceField
    ABSTRACT_SIGNALS: DiagnosticTraceField
    PATTERN_MCP_MATCHES: DiagnosticTraceField
    PATTERN_APPLICABILITY: DiagnosticTraceField
    MANDATORY_FAMILIES: DiagnosticTraceField
    CLAUDE_QUESTIONS: DiagnosticTraceField
    QUESTION_GATE_RESULTS: DiagnosticTraceField
    PROVIDER_ROUTING: DiagnosticTraceField
    RETRIEVAL_EXECUTED: DiagnosticTraceField
    RAW_EVIDENCE: DiagnosticTraceField
    NORMALIZED_EVIDENCE: DiagnosticTraceField
    GITHUB_BLAST_RADIUS: DiagnosticTraceField
    CANDIDATES_DISCOVERED: DiagnosticTraceField
    HYPOTHESES: DiagnosticTraceField
    APPLICABILITY_RESULTS: DiagnosticTraceField
    AUTHORITIES: DiagnosticTraceField
    DISPOSITIONS: DiagnosticTraceField
    SCORING: DiagnosticTraceField
    FAMILY_COMPLETENESS: DiagnosticTraceField
    CANDIDATE_COMPLETENESS: DiagnosticTraceField
    DEDUP_DECISIONS: DiagnosticTraceField
    RENDERER_DECISIONS: DiagnosticTraceField

    ACTIVE_REASONERS: DiagnosticTraceField
    DITA_SEMANTIC_TRACE: DiagnosticTraceField
    AUTHORING_CAPABILITY_TRACE: DiagnosticTraceField
    CONFIGURATION_BRANCHES: DiagnosticTraceField
    BEHAVIOR_TRACE: DiagnosticTraceField
    ORACLE: DiagnosticTraceField
    SEMANTIC_BLAST_RADIUS: DiagnosticTraceField

    STAGE_OBSERVATIONS: tuple[QeMissStageObservation, ...]
    PROVENANCE: QeMissProvenance

    @field_validator("PLAN_ID", "RUN_ID")
    @classmethod
    def validate_run_ids(cls, value: str) -> str:
        if _RUN_ID_RE.fullmatch(value) is None:
            raise ValueError("plan_id uses the canonical run ID in the current runtime")
        return value

    @field_validator("EVIDENCE")
    @classmethod
    def validate_evidence_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _normalize_record_ids(value)

    @model_validator(mode="after")
    def validate_invariants(self) -> "QeMissDiagnosis":
        if self.PLAN_ID != self.RUN_ID:
            raise ValueError("current plan_id must be the frozen canonical run ID")
        if (self.HUMAN_REFERENCE_STATE == "NOT_PROVIDED") != (
            not self.HUMAN_REFERENCE_SHA256
        ):
            raise ValueError("Human reference state and content hash must agree")
        failures = [
            row.stage
            for row in self.STAGE_OBSERVATIONS
            if row.state == QeMissStageState.FAIL
        ]
        if failures != [self.EARLIEST_FAILED_STAGE]:
            raise ValueError("diagnosis must expose exactly one earliest failure")
        return self


class _FrozenQeRunSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    result: GenerationResult = Field(repr=False)
    question_trace: QuestionRetrievalTraceBundle | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def validate_frozen_linkage(self) -> "_FrozenQeRunSnapshot":
        if not self.result.output_sha256:
            raise ValueError("generation must be frozen before diagnostic capture")
        if self.result.output_sha256 != stable_sha256(self.result.output_payload):
            raise ValueError("frozen generation output hash does not match payload")
        if self.question_trace is not None and (
            self.question_trace.run_id != self.result.run_id
            or self.question_trace.request_id != self.result.request_id
            or self.question_trace.output_sha256 != self.result.output_sha256
        ):
            raise ValueError("question trace does not belong to the frozen generation")
        return self


_LAST_QE_MISS_SNAPSHOT: ContextVar[_FrozenQeRunSnapshot | None] = ContextVar(
    "aem_guides_last_qe_miss_snapshot", default=None
)


def clear_last_qe_miss_debug_snapshot() -> None:
    """Clear only diagnostic state; canonical generation state is untouched."""

    _LAST_QE_MISS_SNAPSHOT.set(None)


def record_qe_miss_debug_snapshot(
    *,
    result: GenerationResult,
    question_trace: QuestionRetrievalTraceBundle | None,
) -> None:
    """Capture a deep, private snapshot only after output hashing is complete."""

    snapshot = _FrozenQeRunSnapshot(
        result=result.model_copy(deep=True),
        question_trace=(
            question_trace.model_copy(deep=True) if question_trace is not None else None
        ),
    )
    _LAST_QE_MISS_SNAPSHOT.set(snapshot)


_CATEGORY_BY_STAGE: dict[QeMissStage, QeMissCategory] = {
    QeMissStage.EVIDENCE_INTAKE: QeMissCategory.EVIDENCE_MISS,
    QeMissStage.ROUTING: QeMissCategory.EVIDENCE_MISS,
    QeMissStage.RETRIEVAL: QeMissCategory.EVIDENCE_MISS,
    QeMissStage.NORMALIZATION: QeMissCategory.EVIDENCE_MISS,
    QeMissStage.AUTHORITY: QeMissCategory.DISPOSITION_MISS,
    QeMissStage.DISPOSITION: QeMissCategory.DISPOSITION_MISS,
    QeMissStage.SCORING: QeMissCategory.DISPOSITION_MISS,
    QeMissStage.FAMILY_COMPLETENESS: QeMissCategory.DISPOSITION_MISS,
    QeMissStage.CANDIDATE_COMPLETENESS: QeMissCategory.DISPOSITION_MISS,
    QeMissStage.DEDUP: QeMissCategory.DISPOSITION_MISS,
    QeMissStage.RENDERER: QeMissCategory.RENDERING_MISS,
}


_FIX_LAYER: dict[QeMissStage, str] = {
    QeMissStage.EVIDENCE_INTAKE: "evidence intake and source visibility",
    QeMissStage.CONTRACT_FACT: "contract fact extraction and preservation",
    QeMissStage.DOMAIN: "domain routing",
    QeMissStage.CHANGE_SURFACE: "generic change-surface extraction",
    QeMissStage.SIGNAL: "abstract signal extraction",
    QeMissStage.PATTERN_LOOKUP: "Pattern MCP lookup/resolver contract",
    QeMissStage.PATTERN_APPLICABILITY: "current-case pattern applicability",
    QeMissStage.FAMILY_ACTIVATION: "family activation and materiality logic",
    QeMissStage.CLAUDE_QUESTION: "Missing Question generation",
    QeMissStage.QUESTION_VALIDATOR: "question validation/gating",
    QeMissStage.ROUTING: "evidence provider routing",
    QeMissStage.RETRIEVAL: "provider retrieval/query formulation",
    QeMissStage.NORMALIZATION: "evidence normalization and fusion",
    QeMissStage.GITHUB_BLAST_RADIUS: "GitHub implementation blast-radius verification",
    QeMissStage.HYPOTHESIS: "hypothesis formation",
    QeMissStage.APPLICABILITY: "current-case applicability verification",
    QeMissStage.AUTHORITY: "authority classification and provenance",
    QeMissStage.DISPOSITION: "coverage disposition classification",
    QeMissStage.SCORING: "AC/plan scoring",
    QeMissStage.FAMILY_COMPLETENESS: "behavioral family completeness gate",
    QeMissStage.CANDIDATE_COMPLETENESS: "candidate completeness/promotion gate",
    QeMissStage.DEDUP: "semantic deduplication/subsumption trace",
    QeMissStage.RENDERER: "strict QE renderer/source-record projection",
}


_WHY_FAILED: dict[QeMissStage, str] = {
    stage: f"The first material trace failure occurred in {_FIX_LAYER[stage]}."
    for stage in QeMissStage
}


def classify_earliest_qe_failure(
    observations: Iterable[QeMissStageObservation],
) -> QeMissFailureClassification:
    """Return one root failure and downgrade every later failure to an effect."""

    rows = tuple(observations)
    if tuple(row.stage for row in rows) != QE_MISS_STAGE_ORDER:
        raise ValueError("QE miss observations must contain every stage in order")
    failure_indexes = [
        index for index, row in enumerate(rows) if row.state == QeMissStageState.FAIL
    ]
    if not failure_indexes:
        raise ValueError("a confirmed miss requires one evidenced failing stage")
    earliest_index = failure_indexes[0]
    earliest = rows[earliest_index].stage
    normalized: list[QeMissStageObservation] = []
    for index, row in enumerate(rows):
        if index > earliest_index and row.state == QeMissStageState.FAIL:
            normalized.append(
                QeMissStageObservation(
                    stage=row.stage,
                    state=QeMissStageState.DOWNSTREAM_BLOCKED,
                    reason_codes=(f"DOWNSTREAM_OF_{earliest.value}",),
                    record_ids=row.record_ids,
                )
            )
        else:
            normalized.append(row)
    return QeMissFailureClassification(
        earliest_failed_stage=earliest,
        category=_CATEGORY_BY_STAGE.get(
            earliest, QeMissCategory.DISCOVERY_REASONING_MISS
        ),
        observations=tuple(normalized),
    )


def _typed(prefix: str, values: Iterable[str]) -> tuple[str, ...]:
    return _normalize_record_ids(f"{prefix}:{value}" for value in values if value)


def _field(
    state: DiagnosticFieldState,
    *reason_codes: str,
    record_ids: Iterable[str] = (),
) -> DiagnosticTraceField:
    return DiagnosticTraceField(
        state=state,
        reason_codes=tuple(reason_codes),
        record_ids=tuple(record_ids),
    )


def _observation(
    stage: QeMissStage,
    state: QeMissStageState,
    reason_code: str,
    record_ids: Iterable[str] = (),
) -> QeMissStageObservation:
    return QeMissStageObservation(
        stage=stage,
        state=state,
        reason_codes=(reason_code,),
        record_ids=tuple(record_ids),
    )


def _parse_list(payload: dict[str, object], key: str, model: type[BaseModel]) -> list[BaseModel]:
    raw = payload.get(key, [])
    if not isinstance(raw, list):
        raise ValueError(f"frozen output field {key} is not a list")
    return [model.model_validate(row) for row in raw]


def _human_reference_hash(value: str | None) -> tuple[HumanReferenceState, str]:
    if value is None:
        return "NOT_PROVIDED", ""
    if not isinstance(value, str):
        raise TypeError("optional_human_reference must be text")
    if not value.strip():
        raise ValueError("optional_human_reference cannot be blank")
    if len(value) > _MAX_HUMAN_REFERENCE_CHARS or "\x00" in value:
        raise ValueError("optional_human_reference is invalid or too large")
    # The text is never retained or returned.  A hash proves which post-freeze
    # reference was used without exposing its contents.
    return "POST_GENERATION_HASH_ONLY", sha256(value.encode("utf-8")).hexdigest()


_IMPLEMENTATION_DIMENSIONS = {
    SemanticDimension.DIRECT_CONSUMERS,
    SemanticDimension.SIBLING_CONSUMERS,
    SemanticDimension.DOWNSTREAM_PROCESSOR,
}


def _diagnose_snapshot(
    snapshot: _FrozenQeRunSnapshot,
    *,
    plan_id: str,
    dimension: SemanticDimension,
    human_reference_state: HumanReferenceState,
    human_reference_sha256: str,
) -> QeMissDiagnosis:
    result = snapshot.result
    payload = result.output_payload
    facts = ContractFactSet.model_validate(payload.get("contract_facts", {}))
    domains = [
        row for row in _parse_list(payload, "domains", DomainActivation)
        if isinstance(row, DomainActivation)
    ]
    surfaces = list(result.trace.qe_investigation.change_surfaces) if result.trace.qe_investigation else []
    signals = list(result.trace.qe_investigation.abstract_signals) if result.trace.qe_investigation else []
    activations = [
        row
        for row in _parse_list(
            payload, "reasoning_pattern_activations", ReasoningPatternActivation
        )
        if isinstance(row, ReasoningPatternActivation)
    ]
    investigation = QeInvestigationPreparation.model_validate(payload["qe_investigation"])
    closures = [
        row for row in _parse_list(payload, "semantic_closure", ClosureDimensionResult)
        if isinstance(row, ClosureDimensionResult)
    ]
    questions = [
        row for row in _parse_list(payload, "missing_questions", MissingQuestion)
        if isinstance(row, MissingQuestion)
    ]
    retrievals = [
        row for row in _parse_list(payload, "directed_retrievals", DirectedRetrievalRecord)
        if isinstance(row, DirectedRetrievalRecord)
    ]
    hypotheses = [
        row for row in _parse_list(payload, "hypotheses", BehaviorHypothesis)
        if isinstance(row, BehaviorHypothesis)
    ]
    dispositions = [
        row
        for row in _parse_list(
            payload, "coverage_dispositions", CoverageDispositionRecord
        )
        if isinstance(row, CoverageDispositionRecord)
    ]
    candidates = [
        row for row in _parse_list(payload, "acceptance_candidates", AcceptanceCandidate)
        if isinstance(row, AcceptanceCandidate)
    ]
    discovered_candidates = [
        row
        for row in _parse_list(
            payload, "discovered_acceptance_candidates", AcceptanceCandidate
        )
        if isinstance(row, AcceptanceCandidate)
    ] or candidates
    promotions = [
        row
        for row in _parse_list(
            payload, "promotion_decisions", AcceptancePromotionDecision
        )
        if isinstance(row, AcceptancePromotionDecision)
    ]
    gates = [
        row for row in _parse_list(payload, "gate_decisions", GateDecision)
        if isinstance(row, GateDecision)
    ]

    dim_activations = [row for row in activations if row.semantic_dimension == dimension]
    dim_families = [
        row for row in investigation.mandatory_families if row.family_id == dimension
    ]
    dim_closures = [row for row in closures if row.dimension == dimension]
    dim_questions = [row for row in questions if row.dimension == dimension]
    question_ids = {row.question_id for row in dim_questions}
    dim_retrievals = [row for row in retrievals if row.question_id in question_ids]
    dim_hypotheses = [
        row for row in hypotheses if row.derived_from_question_id in question_ids
    ]
    hypothesis_ids = {row.hypothesis_id for row in dim_hypotheses}
    closure_ids = {row.closure_id for row in dim_closures}
    dim_dispositions = [
        row
        for row in dispositions
        if set(row.source_question_ids) & question_ids
        or set(row.source_hypothesis_ids) & hypothesis_ids
        or set(row.source_closure_ids) & closure_ids
    ]
    disposition_ids = {row.disposition_id for row in dim_dispositions}
    dim_candidates = [
        row
        for row in candidates
        if set(row.source_disposition_ids) & disposition_ids
    ]
    dim_discovered_candidates = [
        row
        for row in discovered_candidates
        if set(row.source_disposition_ids) & disposition_ids
    ]
    canonical_candidate_ids = {row.candidate_id for row in dim_candidates}
    discovered_candidate_ids = {
        row.candidate_id for row in dim_discovered_candidates
    }
    candidate_ids = canonical_candidate_ids | discovered_candidate_ids
    dim_promotions = [
        row for row in promotions if row.candidate_id in canonical_candidate_ids
    ]
    plan = result.structured_plan
    dim_dedup_decisions = [
        row
        for row in (plan.dedup_decisions if plan else [])
        if set(row.merged_candidate_ids) & discovered_candidate_ids
        or row.surviving_candidate_id in canonical_candidate_ids
    ]
    dim_lifecycle = [
        row
        for row in (plan.candidate_lifecycle if plan else [])
        if row.discovered_candidate_id in discovered_candidate_ids
        or row.canonical_candidate_id in canonical_candidate_ids
    ]
    dim_pattern_rows = [
        row
        for row in investigation.pattern_lookup.applicability_records
        if dimension in row.recommended_question_families
    ]
    pattern_ids = {row.pattern_id for row in dim_pattern_rows}

    question_trace_rows = (
        [row for row in snapshot.question_trace.questions if row.question_id in question_ids]
        if snapshot.question_trace is not None
        else []
    )
    provider_call_ids = {
        call_id for row in question_trace_rows for call_id in row.provider_call_ids
    }
    github_handoff_ids = {
        handoff_id
        for row in question_trace_rows
        for handoff_id in row.implementation_handoff_ids
    }
    github_result_ids = {
        result_id
        for row in question_trace_rows
        for result_id in row.implementation_result_ids
    }

    evidence_ids = {row.evidence_id for row in result.evidence_bundle.records}
    related_evidence_ids = {
        evidence_id
        for row in dim_closures
        for evidence_id in row.evidence_ids
    } | {
        evidence_id
        for row in dim_retrievals
        for evidence_id in row.matched_evidence_ids
    } | {
        evidence_id
        for row in dim_hypotheses
        for evidence_id in (
            row.supporting_evidence_ids
            + row.contradicting_evidence_ids
            + row.verification_evidence_ids
        )
    } | {
        evidence_id
        for row in dim_dispositions
        for evidence_id in row.evidence_ids
    } | {
        evidence_id
        for row in dim_candidates
        for evidence_id in row.evidence_ids
    }
    code_evidence_ids = {
        row.evidence_id
        for row in result.evidence_bundle.records
        if row.source_type == EvidenceSourceType.CURRENT_CODE
    }
    lineage_ids = (
        question_ids
        | closure_ids
        | hypothesis_ids
        | disposition_ids
        | candidate_ids
    )
    renderer_source_ids = {
        source_id
        for section in (result.structured_plan.sections if result.structured_plan else [])
        for source_id in section.source_record_ids
        if source_id in lineage_ids
    }
    was_discovered = bool(
        dim_activations or dim_families or dim_closures or dim_questions
    )
    if renderer_source_ids:
        raise ValueError(
            "expected dimension already has a final-output lineage; no silent miss is proven"
        )

    pattern_status = investigation.pattern_lookup.status
    active_family = any(
        row.activation_decision
        in {
            FamilyActivationDecision.ACTIVATE_BLOCKING,
            FamilyActivationDecision.ACTIVATE_NON_BLOCKING,
        }
        for row in dim_families
    )
    retrieval_used = any(row.status == RetrievalStatus.USED for row in dim_retrievals)
    normalized_ids = {
        evidence_id
        for row in dim_retrievals
        for evidence_id in row.matched_evidence_ids
        if evidence_id in evidence_ids
    }
    implementation_required = dimension in _IMPLEMENTATION_DIMENSIONS or any(
        row.authority_subject.value == "ACTUAL_IMPLEMENTATION" for row in dim_questions
    )
    accepted_or_material_disposition = any(
        row.disposition
        not in {
            CoverageDisposition.OUT_OF_SCOPE,
            CoverageDisposition.INVESTIGATED_AND_REJECTED,
            CoverageDisposition.UNSUPPORTED_INFERENCE,
        }
        for row in dim_dispositions
    )

    behavioral_gate = next(
        (
            row
            for row in gates
            if row.gate == CanonicalRuntimeStage.BEHAVIORAL_COMPLETENESS_GATE
        ),
        None,
    )
    raw_observations = [
        _observation(
            QeMissStage.EVIDENCE_INTAKE,
            QeMissStageState.PASS if evidence_ids else QeMissStageState.FAIL,
            "EVIDENCE_BUNDLE_PRESENT" if evidence_ids else "EVIDENCE_BUNDLE_EMPTY",
            evidence_ids,
        ),
        _observation(
            QeMissStage.CONTRACT_FACT,
            QeMissStageState.PASS if facts.facts else QeMissStageState.FAIL,
            "CONTRACT_FACTS_PRESENT" if facts.facts else "CONTRACT_FACTS_ABSENT",
            (row.fact_id for row in facts.facts),
        ),
        _observation(
            QeMissStage.DOMAIN,
            QeMissStageState.PASS if domains else QeMissStageState.FAIL,
            "DOMAIN_ACTIVATED" if domains else "DOMAIN_NOT_ACTIVATED",
            _typed("domain", (row.domain.value for row in domains)),
        ),
        _observation(
            QeMissStage.CHANGE_SURFACE,
            QeMissStageState.PASS if surfaces else QeMissStageState.FAIL,
            "CHANGE_SURFACE_PRESENT" if surfaces else "CHANGE_SURFACE_ABSENT",
            (row.surface_id for row in surfaces),
        ),
        _observation(
            QeMissStage.SIGNAL,
            QeMissStageState.PASS if signals else QeMissStageState.FAIL,
            "ABSTRACT_SIGNAL_PRESENT" if signals else "ABSTRACT_SIGNAL_ABSENT",
            (row.signal_id for row in signals),
        ),
        _observation(
            QeMissStage.PATTERN_LOOKUP,
            (
                QeMissStageState.FAIL
                if pattern_status
                in {
                    PatternLookupRuntimeStatus.PROVIDER_UNAVAILABLE,
                    PatternLookupRuntimeStatus.PROVIDER_ERROR,
                    PatternLookupRuntimeStatus.INVALID_RESPONSE,
                }
                and not (dim_activations or dim_families or dim_closures)
                else QeMissStageState.PASS
                if dim_pattern_rows
                else QeMissStageState.NOT_APPLICABLE
            ),
            (
                "PATTERN_PROVIDER_FAILED"
                if pattern_status
                in {
                    PatternLookupRuntimeStatus.PROVIDER_UNAVAILABLE,
                    PatternLookupRuntimeStatus.PROVIDER_ERROR,
                    PatternLookupRuntimeStatus.INVALID_RESPONSE,
                }
                and not (dim_activations or dim_families or dim_closures)
                else "DIMENSION_PATTERN_MATCHED"
                if dim_pattern_rows
                else "NO_DIMENSION_PATTERN_REQUIRED"
            ),
            _typed("pattern", pattern_ids),
        ),
        _observation(
            QeMissStage.PATTERN_APPLICABILITY,
            (
                QeMissStageState.PASS
                if any(
                    row.current_applicability
                    == CurrentPatternApplicability.CURRENTLY_VERIFIED
                    for row in dim_pattern_rows
                )
                else QeMissStageState.FAIL
                if dim_pattern_rows and not (dim_families or dim_closures)
                else QeMissStageState.NOT_APPLICABLE
            ),
            (
                "PATTERN_CURRENTLY_VERIFIED"
                if any(
                    row.current_applicability
                    == CurrentPatternApplicability.CURRENTLY_VERIFIED
                    for row in dim_pattern_rows
                )
                else "PATTERN_APPLICABILITY_REJECTED_OR_UNRESOLVED"
                if dim_pattern_rows and not (dim_families or dim_closures)
                else "NO_APPLICABLE_PATTERN_RECORD"
            ),
            _typed("pattern-app", (row.pattern_id for row in dim_pattern_rows)),
        ),
        _observation(
            QeMissStage.FAMILY_ACTIVATION,
            (
                QeMissStageState.PASS
                if active_family or dim_closures or dim_questions
                else QeMissStageState.FAIL
            ),
            (
                "DIMENSION_FAMILY_ACTIVE_OR_TRAVERSED"
                if active_family or dim_closures or dim_questions
                else "MATERIAL_DIMENSION_FAMILY_NOT_ACTIVATED"
            ),
            _typed("family", (row.family_id.value for row in dim_families)),
        ),
        _observation(
            QeMissStage.CLAUDE_QUESTION,
            (
                QeMissStageState.PASS
                if dim_questions
                else QeMissStageState.NOT_APPLICABLE
                if dim_closures
                and all(
                    row.applicability == ApplicabilityState.NOT_APPLICABLE
                    or row.disposition.value == "COVERED"
                    for row in dim_closures
                )
                else QeMissStageState.FAIL
                if active_family
                else QeMissStageState.UNKNOWN
            ),
            (
                "CANONICAL_QUESTION_PRESENT"
                if dim_questions
                else "QUESTION_NOT_REQUIRED_BY_CLOSURE_STATE"
                if dim_closures
                and all(
                    row.applicability == ApplicabilityState.NOT_APPLICABLE
                    or row.disposition.value == "COVERED"
                    for row in dim_closures
                )
                else "MATERIAL_FAMILY_HAS_NO_QUESTION"
                if active_family
                else "QUESTION_STAGE_NOT_REACHED"
            ),
            question_ids,
        ),
        _observation(
            QeMissStage.QUESTION_VALIDATOR,
            QeMissStageState.NOT_IMPLEMENTED,
            "QUESTION_VALIDATOR_TRACE_NOT_IMPLEMENTED",
            question_ids,
        ),
        _observation(
            QeMissStage.ROUTING,
            (
                QeMissStageState.NOT_APPLICABLE
                if not dim_questions
                else QeMissStageState.PASS
                if dim_retrievals or provider_call_ids
                else QeMissStageState.FAIL
            ),
            (
                "NO_DIMENSION_QUESTION"
                if not dim_questions
                else "QUESTION_ROUTED"
                if dim_retrievals or provider_call_ids
                else "QUESTION_NOT_ROUTED"
            ),
            {row.retrieval_id for row in dim_retrievals} | provider_call_ids,
        ),
        _observation(
            QeMissStage.RETRIEVAL,
            (
                QeMissStageState.NOT_APPLICABLE
                if not dim_questions
                else QeMissStageState.PASS
                if retrieval_used
                else QeMissStageState.FAIL
            ),
            (
                "NO_DIMENSION_QUESTION"
                if not dim_questions
                else "RETRIEVAL_USED"
                if retrieval_used
                else "RETRIEVAL_EMPTY_REJECTED_OR_UNAVAILABLE"
            ),
            (row.retrieval_id for row in dim_retrievals),
        ),
        _observation(
            QeMissStage.NORMALIZATION,
            (
                QeMissStageState.NOT_APPLICABLE
                if not dim_retrievals
                else QeMissStageState.PASS
                if normalized_ids
                else QeMissStageState.FAIL
                if retrieval_used
                else QeMissStageState.UNKNOWN
            ),
            (
                "NO_RETRIEVAL_RESULT"
                if not dim_retrievals
                else "MATCHED_EVIDENCE_NORMALIZED"
                if normalized_ids
                else "RETRIEVED_EVIDENCE_MISSING_AFTER_NORMALIZATION"
                if retrieval_used
                else "NORMALIZATION_NOT_REACHED"
            ),
            normalized_ids,
        ),
        _observation(
            QeMissStage.GITHUB_BLAST_RADIUS,
            (
                QeMissStageState.NOT_APPLICABLE
                if not implementation_required
                else QeMissStageState.PASS
                if github_handoff_ids and github_result_ids
                else QeMissStageState.FAIL
            ),
            (
                "IMPLEMENTATION_VERIFICATION_NOT_REQUIRED"
                if not implementation_required
                else "GITHUB_BLAST_RADIUS_RECORDED"
                if github_handoff_ids and github_result_ids
                else "GITHUB_BLAST_RADIUS_MISSING"
            ),
            github_handoff_ids | github_result_ids,
        ),
        _observation(
            QeMissStage.HYPOTHESIS,
            (
                QeMissStageState.NOT_APPLICABLE
                if not dim_questions
                else QeMissStageState.PASS
                if dim_hypotheses
                else QeMissStageState.FAIL
            ),
            (
                "NO_DIMENSION_QUESTION"
                if not dim_questions
                else "HYPOTHESIS_PRESENT"
                if dim_hypotheses
                else "HYPOTHESIS_NOT_FORMED"
            ),
            hypothesis_ids,
        ),
        _observation(
            QeMissStage.APPLICABILITY,
            (
                QeMissStageState.FAIL
                if dim_closures
                and all(row.applicability == ApplicabilityState.NOT_APPLICABLE for row in dim_closures)
                else QeMissStageState.FAIL
                if dim_hypotheses
                and all(row.state == HypothesisState.REJECTED for row in dim_hypotheses)
                else QeMissStageState.PASS
                if dim_closures or dim_hypotheses
                else QeMissStageState.NOT_IMPLEMENTED
            ),
            (
                "DIMENSION_MARKED_NOT_APPLICABLE"
                if dim_closures
                and all(row.applicability == ApplicabilityState.NOT_APPLICABLE for row in dim_closures)
                else "ALL_HYPOTHESES_REJECTED"
                if dim_hypotheses
                and all(row.state == HypothesisState.REJECTED for row in dim_hypotheses)
                else "APPLICABILITY_RETAINED"
                if dim_closures or dim_hypotheses
                else "SEPARATE_APPLICABILITY_TRACE_NOT_IMPLEMENTED"
            ),
            closure_ids | hypothesis_ids,
        ),
        _observation(
            QeMissStage.AUTHORITY,
            (
                QeMissStageState.PASS
                if any(row.authority_supported for row in dim_promotions)
                or accepted_or_material_disposition
                else QeMissStageState.FAIL
                if dim_candidates or dim_hypotheses
                else QeMissStageState.NOT_APPLICABLE
            ),
            (
                "AUTHORITY_OR_MATERIAL_DISPOSITION_PRESENT"
                if any(row.authority_supported for row in dim_promotions)
                or accepted_or_material_disposition
                else "AUTHORITY_NOT_ESTABLISHED"
                if dim_candidates or dim_hypotheses
                else "NO_AUTHORITY_DECISION_REQUIRED"
            ),
            related_evidence_ids | candidate_ids,
        ),
        _observation(
            QeMissStage.DISPOSITION,
            (
                QeMissStageState.PASS
                if accepted_or_material_disposition
                else QeMissStageState.FAIL
                if dim_dispositions or dim_hypotheses or dim_closures
                else QeMissStageState.NOT_APPLICABLE
            ),
            (
                "MATERIAL_DISPOSITION_PRESENT"
                if accepted_or_material_disposition
                else "DIMENSION_REJECTED_DROPPED_OR_UNDISPOSITIONED"
                if dim_dispositions or dim_hypotheses or dim_closures
                else "NO_DIMENSION_CANDIDATE"
            ),
            disposition_ids,
        ),
        _observation(
            QeMissStage.SCORING,
            QeMissStageState.NOT_IMPLEMENTED,
            "AC_PLAN_SCORING_TRACE_NOT_IMPLEMENTED",
        ),
        _observation(
            QeMissStage.FAMILY_COMPLETENESS,
            (
                QeMissStageState.NOT_APPLICABLE
                if not (closure_ids or question_ids)
                else QeMissStageState.PASS
                if behavioral_gate
                and bool(set(behavioral_gate.checked_ids) & (closure_ids | question_ids))
                else QeMissStageState.FAIL
            ),
            (
                "NO_DIMENSION_LINEAGE_FOR_FAMILY_GATE"
                if not (closure_ids or question_ids)
                else "FAMILY_GATE_CHECKED_DIMENSION"
                if behavioral_gate
                and bool(set(behavioral_gate.checked_ids) & (closure_ids | question_ids))
                else "FAMILY_GATE_DID_NOT_CHECK_DIMENSION"
            ),
            _typed("gate", (behavioral_gate.gate.value,)) if behavioral_gate else (),
        ),
        _observation(
            QeMissStage.CANDIDATE_COMPLETENESS,
            (
                QeMissStageState.NOT_APPLICABLE
                if not discovered_candidate_ids
                else QeMissStageState.PASS
                if len(dim_lifecycle) == len(discovered_candidate_ids)
                and all(
                    row.final_disposition is not None for row in dim_lifecycle
                )
                else QeMissStageState.FAIL
            ),
            (
                "NO_ACCEPTANCE_CANDIDATE_FOR_DIMENSION"
                if not discovered_candidate_ids
                else "EVERY_DISCOVERED_CANDIDATE_HAS_TERMINAL_LIFECYCLE"
                if len(dim_lifecycle) == len(discovered_candidate_ids)
                else "DISCOVERED_CANDIDATE_LACKS_TERMINAL_LIFECYCLE"
            ),
            (row.lifecycle_id for row in dim_lifecycle),
        ),
        _observation(
            QeMissStage.DEDUP,
            (
                QeMissStageState.NOT_APPLICABLE
                if not discovered_candidate_ids
                or discovered_candidate_ids <= canonical_candidate_ids
                else QeMissStageState.PASS
                if discovered_candidate_ids
                <= canonical_candidate_ids
                | {
                    candidate_id
                    for row in dim_dedup_decisions
                    for candidate_id in row.merged_candidate_ids
                }
                else QeMissStageState.FAIL
            ),
            (
                "NO_DEDUP_REQUIRED"
                if not discovered_candidate_ids
                or discovered_candidate_ids <= canonical_candidate_ids
                else "DEDUP_MERGE_LINEAGE_COMPLETE"
                if discovered_candidate_ids
                <= canonical_candidate_ids
                | {
                    candidate_id
                    for row in dim_dedup_decisions
                    for candidate_id in row.merged_candidate_ids
                }
                else "DISCOVERED_CANDIDATE_DROPPED_WITHOUT_DEDUP_TRACE"
            ),
            (row.decision_id for row in dim_dedup_decisions),
        ),
        _observation(
            QeMissStage.RENDERER,
            QeMissStageState.FAIL,
            "DIMENSION_LINEAGE_ABSENT_FROM_FINAL_OUTPUT",
            renderer_source_ids,
        ),
    ]
    classification = classify_earliest_qe_failure(raw_observations)
    earliest = classification.earliest_failed_stage
    earliest_observation = next(
        row for row in classification.observations if row.stage == earliest
    )
    why_it_failed = (
        f"{_WHY_FAILED[earliest]} Reason codes: "
        f"{', '.join(earliest_observation.reason_codes)}."
    )
    downstream_effect = (
        "Later missing records are consequences of the earliest failure and are not "
        "reported as additional root causes."
    )
    do_not_fix = (
        "reasoning patterns, retrieval, or disposition"
        if earliest == QeMissStage.RENDERER
        else "renderer or AC wording"
    )

    evidence_field_ids = tuple(sorted(evidence_ids))
    pattern_field_ids = _typed(
        "pattern",
        (row.pattern_id for row in investigation.pattern_lookup.matched_human_patterns),
    )
    question_field_ids = tuple(sorted(row.question_id for row in questions))
    routing_ids = tuple(
        sorted({row.retrieval_id for row in retrievals} | provider_call_ids)
    )
    github_ids = tuple(sorted(github_handoff_ids | github_result_ids))
    hypothesis_field_ids = tuple(sorted(row.hypothesis_id for row in hypotheses))
    disposition_field_ids = tuple(sorted(row.disposition_id for row in dispositions))
    candidate_field_ids = tuple(
        sorted(
            {row.candidate_id for row in candidates}
            | {row.candidate_id for row in discovered_candidates}
        )
    )
    lifecycle_ids = tuple(
        row.lifecycle_id for row in (plan.candidate_lifecycle if plan else [])
    )
    dedup_ids = tuple(
        row.decision_id for row in (plan.dedup_decisions if plan else [])
    )
    renderer_ids = tuple(
        row.projection_id for row in (plan.renderer_decisions if plan else [])
    )
    not_implemented = _field(
        DiagnosticFieldState.NOT_IMPLEMENTED, "STAGE_TRACE_NOT_IMPLEMENTED"
    )

    return QeMissDiagnosis(
        PLAN_ID=plan_id,
        RUN_ID=result.run_id,
        REQUEST_ID=result.request_id,
        OUTPUT_SHA256=result.output_sha256,
        EXPECTED_DIMENSION=dimension,
        WAS_DISCOVERED="YES" if was_discovered else "NO",
        EARLIEST_FAILED_STAGE=earliest,
        MISS_CATEGORY=classification.category,
        WHY_IT_FAILED=why_it_failed,
        EVIDENCE=tuple(sorted(related_evidence_ids or evidence_ids)),
        DOWNSTREAM_EFFECT=downstream_effect,
        GENERIC_FIX_LAYER=_FIX_LAYER[earliest],
        DO_NOT_FIX_HERE=do_not_fix,
        HUMAN_REFERENCE_STATE=human_reference_state,
        HUMAN_REFERENCE_SHA256=human_reference_sha256,
        EVIDENCE_PRESENT=_field(
            DiagnosticFieldState.PRESENT if evidence_ids else DiagnosticFieldState.ABSENT,
            "CANONICAL_EVIDENCE_REFERENCES_ONLY",
            record_ids=evidence_field_ids,
        ),
        CONTRACT_FACT_PRESENT=_field(
            DiagnosticFieldState.PRESENT if facts.facts else DiagnosticFieldState.ABSENT,
            "CONTRACT_FACT_IDS_ONLY",
            record_ids=(row.fact_id for row in facts.facts),
        ),
        DOMAIN=_field(
            DiagnosticFieldState.PRESENT if domains else DiagnosticFieldState.ABSENT,
            "DOMAIN_ACTIVATION_IDS_ONLY",
            record_ids=_typed("domain", (row.domain.value for row in domains)),
        ),
        CHANGE_SURFACES=_field(
            DiagnosticFieldState.PRESENT if surfaces else DiagnosticFieldState.ABSENT,
            "CHANGE_SURFACE_IDS_ONLY",
            record_ids=(row.surface_id for row in surfaces),
        ),
        ABSTRACT_SIGNALS=_field(
            DiagnosticFieldState.PRESENT if signals else DiagnosticFieldState.ABSENT,
            "ABSTRACT_SIGNAL_IDS_ONLY",
            record_ids=(row.signal_id for row in signals),
        ),
        PATTERN_MCP_MATCHES=_field(
            DiagnosticFieldState.PRESENT
            if investigation.pattern_lookup.matched_human_patterns
            else DiagnosticFieldState.ABSENT,
            f"PATTERN_STATUS_{pattern_status.value}",
            record_ids=pattern_field_ids,
        ),
        PATTERN_APPLICABILITY=_field(
            DiagnosticFieldState.PRESENT
            if investigation.pattern_lookup.applicability_records
            else DiagnosticFieldState.ABSENT,
            "CURRENT_CASE_APPLICABILITY_ONLY",
            record_ids=_typed(
                "pattern-app",
                (row.pattern_id for row in investigation.pattern_lookup.applicability_records),
            ),
        ),
        MANDATORY_FAMILIES=_field(
            DiagnosticFieldState.PRESENT
            if investigation.mandatory_families
            else DiagnosticFieldState.ABSENT,
            "FAMILY_DECISION_IDS_ONLY",
            record_ids=_typed(
                "family", (row.family_id.value for row in investigation.mandatory_families)
            ),
        ),
        CLAUDE_QUESTIONS=_field(
            DiagnosticFieldState.NOT_IMPLEMENTED,
            "EXTERNAL_CLAUDE_INVOCATION_NOT_IMPLEMENTED",
            "CANONICAL_BACKEND_QUESTIONS_PROJECTED",
            record_ids=question_field_ids,
        ),
        QUESTION_GATE_RESULTS=_field(
            DiagnosticFieldState.NOT_IMPLEMENTED,
            "QUESTION_VALIDATOR_TRACE_NOT_IMPLEMENTED",
        ),
        PROVIDER_ROUTING=_field(
            DiagnosticFieldState.PRESENT if routing_ids else DiagnosticFieldState.ABSENT,
            "ROUTING_IDS_ONLY",
            record_ids=routing_ids,
        ),
        RETRIEVAL_EXECUTED=_field(
            DiagnosticFieldState.PRESENT if retrievals else DiagnosticFieldState.ABSENT,
            "RETRIEVAL_IDS_ONLY",
            record_ids=(row.retrieval_id for row in retrievals),
        ),
        RAW_EVIDENCE=_field(
            DiagnosticFieldState.PRESENT if evidence_ids else DiagnosticFieldState.ABSENT,
            "RAW_CONTENT_REDACTED",
            record_ids=evidence_field_ids,
        ),
        NORMALIZED_EVIDENCE=_field(
            DiagnosticFieldState.PRESENT if evidence_ids else DiagnosticFieldState.ABSENT,
            "CANONICAL_NORMALIZED_EVIDENCE_IDS_ONLY",
            record_ids=evidence_field_ids,
        ),
        GITHUB_BLAST_RADIUS=_field(
            DiagnosticFieldState.PRESENT
            if github_ids
            else DiagnosticFieldState.NOT_APPLICABLE
            if not implementation_required
            else DiagnosticFieldState.ABSENT,
            "GITHUB_HANDOFF_RESULT_IDS_ONLY",
            record_ids=github_ids,
        ),
        CANDIDATES_DISCOVERED=_field(
            DiagnosticFieldState.PRESENT if candidates else DiagnosticFieldState.ABSENT,
            "CANDIDATE_IDS_ONLY",
            record_ids=candidate_field_ids,
        ),
        HYPOTHESES=_field(
            DiagnosticFieldState.PRESENT if hypotheses else DiagnosticFieldState.ABSENT,
            "HYPOTHESIS_IDS_ONLY",
            record_ids=hypothesis_field_ids,
        ),
        APPLICABILITY_RESULTS=_field(
            DiagnosticFieldState.PRESENT if closures or hypotheses else DiagnosticFieldState.ABSENT,
            "CLOSURE_AND_HYPOTHESIS_STATES_PROJECTED",
            record_ids=tuple(sorted({row.closure_id for row in closures} | set(hypothesis_field_ids))),
        ),
        AUTHORITIES=_field(
            DiagnosticFieldState.PRESENT if evidence_ids or promotions else DiagnosticFieldState.ABSENT,
            "AUTHORITY_METADATA_IDS_ONLY",
            record_ids=tuple(sorted(evidence_ids | {row.candidate_id for row in promotions})),
        ),
        DISPOSITIONS=_field(
            DiagnosticFieldState.PRESENT if dispositions else DiagnosticFieldState.ABSENT,
            "DISPOSITION_IDS_ONLY",
            record_ids=disposition_field_ids,
        ),
        SCORING=_field(
            DiagnosticFieldState.NOT_IMPLEMENTED, "AC_PLAN_SCORING_TRACE_NOT_IMPLEMENTED"
        ),
        FAMILY_COMPLETENESS=_field(
            DiagnosticFieldState.PRESENT if behavioral_gate else DiagnosticFieldState.ABSENT,
            "BEHAVIORAL_COMPLETENESS_GATE_PROJECTED",
            record_ids=_typed("gate", (behavioral_gate.gate.value,)) if behavioral_gate else (),
        ),
        CANDIDATE_COMPLETENESS=_field(
            DiagnosticFieldState.PRESENT
            if lifecycle_ids
            else DiagnosticFieldState.ABSENT,
            "CANDIDATE_LIFECYCLE_PROJECTED",
            record_ids=lifecycle_ids,
        ),
        DEDUP_DECISIONS=_field(
            DiagnosticFieldState.PRESENT
            if dedup_ids
            else DiagnosticFieldState.NOT_APPLICABLE,
            "CANDIDATE_DEDUP_DECISIONS_PROJECTED"
            if dedup_ids
            else "NO_CANDIDATE_DEDUP_MERGE",
            record_ids=dedup_ids,
        ),
        RENDERER_DECISIONS=_field(
            DiagnosticFieldState.PRESENT if renderer_ids else DiagnosticFieldState.ABSENT,
            "CANDIDATE_RENDERER_PROJECTIONS",
            record_ids=renderer_ids,
        ),
        ACTIVE_REASONERS=not_implemented,
        DITA_SEMANTIC_TRACE=not_implemented,
        AUTHORING_CAPABILITY_TRACE=not_implemented,
        CONFIGURATION_BRANCHES=not_implemented,
        BEHAVIOR_TRACE=not_implemented,
        ORACLE=not_implemented,
        SEMANTIC_BLAST_RADIUS=not_implemented,
        STAGE_OBSERVATIONS=classification.observations,
        PROVENANCE=QeMissProvenance(
            evidence_ids=tuple(sorted(related_evidence_ids or evidence_ids)),
            pattern_ids=_typed("pattern", pattern_ids),
            question_ids=tuple(sorted(question_ids)),
            provider_call_ids=tuple(sorted(provider_call_ids)),
            code_evidence_ids=tuple(sorted(code_evidence_ids & (related_evidence_ids or evidence_ids))),
            candidate_ids=tuple(sorted(candidate_ids)),
            disposition_ids=tuple(sorted(disposition_ids)),
            dedup_merge_ids=tuple(row.decision_id for row in dim_dedup_decisions),
            renderer_source_ids=tuple(sorted(renderer_source_ids)),
        ),
    )


def debug_qe_miss(
    plan_id: str,
    expected_dimension: SemanticDimension | str,
    optional_human_reference: str | None = None,
) -> QeMissDiagnosis:
    """Explain one silent miss in the last frozen canonical generation.

    The current canonical runtime does not define a durable ``plan_id``.  Until
    it does, ``plan_id`` is explicitly the opaque canonical ``run_id``.  This
    function is read-only and requires the snapshot captured before any Human
    reference can be supplied.
    """

    if not isinstance(plan_id, str) or _RUN_ID_RE.fullmatch(plan_id) is None:
        raise ValueError("plan_id must be the canonical frozen run ID")
    try:
        dimension = SemanticDimension(str(expected_dimension))
    except ValueError as exc:
        raise ValueError("expected_dimension must use the canonical dimension enum") from exc
    snapshot = _LAST_QE_MISS_SNAPSHOT.get()
    if snapshot is None or snapshot.result.run_id != plan_id:
        raise LookupError("frozen canonical generation is unavailable for this run ID")
    human_state, human_hash = _human_reference_hash(optional_human_reference)
    return _diagnose_snapshot(
        snapshot,
        plan_id=plan_id,
        dimension=dimension,
        human_reference_state=human_state,
        human_reference_sha256=human_hash,
    )


__all__ = [
    "QE_MISS_DIAGNOSTIC_SCHEMA",
    "QE_MISS_STAGE_ORDER",
    "DiagnosticFieldState",
    "DiagnosticTraceField",
    "QeMissCategory",
    "QeMissDiagnosis",
    "QeMissFailureClassification",
    "QeMissProvenance",
    "QeMissStage",
    "QeMissStageObservation",
    "QeMissStageState",
    "classify_earliest_qe_failure",
    "clear_last_qe_miss_debug_snapshot",
    "debug_qe_miss",
    "record_qe_miss_debug_snapshot",
]
