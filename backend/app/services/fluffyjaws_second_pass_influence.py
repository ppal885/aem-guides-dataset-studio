"""Fail-closed qualification for controlled FluffyJaws second-pass influence.

The canonical runtime executes a visible paired qualification: one
provider-disabled control and one controlled SECOND_PASS result.  This module
proves that every provider-caused output change has the canonical lineage:

    material question -> routed provider evidence -> verified hypothesis
    -> terminal coverage disposition -> rendered plan location

The decision is content-minimal.  It retains canonical IDs and hashes rather
than provider text, Jira content, citations, or credentials.  A blocked audit
selects the provider-disabled result, which is the deterministic rollout
rollback required by FJ-18.
"""

from __future__ import annotations

from collections import Counter
from contextvars import ContextVar
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.schemas_canonical_test_plan_runtime import (
    AcceptanceCandidate,
    AcceptancePromotionDecision,
    BehaviorHypothesis,
    CanonicalBehaviorModel,
    CoverageDisposition,
    CoverageDispositionRecord,
    DirectedRetrievalRecord,
    GenerationResult,
    GitHubImplementationVerificationHandoff,
    GitHubImplementationVerificationResult,
    PlanSection,
    PromotionStatus,
    StructuredQEPlan,
    stable_sha256,
)
from app.services.reasoning_evidence_observability import (
    QuestionRetrievalTraceBundle,
    TraceAnswerState,
)
from app.services.reasoning_evidence_provider import QueryMateriality
from app.services.reasoning_evidence_shadow_service import (
    FluffyJawsRuntimeMode,
    FluffyJawsShadowRunTrace,
)


SECOND_PASS_INFLUENCE_SCHEMA = "aem-guides-fluffyjaws-second-pass-influence-v1"

_PRE_RETRIEVAL_PROJECTIONS = (
    "contract_facts",
    "domains",
    "scope",
    "change_surfaces",
    "abstract_signals",
    "reasoning_pattern_activations",
    "qe_investigation",
    "semantic_closure",
    "missing_questions",
    "domain_impacts",
)
_CANONICAL_SECTION_TITLES = {
    "issue_understanding": "Issue understanding",
    "product_scope": "Publishing / product scope",
    "product_decisions": "Product decisions required",
    "semantic_coverage": "Semantic coverage",
    "structural_hierarchy_coverage": "Structural / hierarchy coverage",
    "referenced_content_coverage": "Referenced content coverage",
    "configuration_state_coverage": "Configuration / state coverage",
    "transformation_processing_coverage": "Transformation / processing coverage",
    "generated_output_validation": "Generated output validation",
    "reference_link_integrity": "Reference / link integrity",
    "negative_boundary_coverage": "Negative / boundary coverage",
    "failure_recovery_coverage": "Failure / recovery coverage",
    "lifecycle_coverage": "Lifecycle coverage",
    "cross_mode_regression": "Cross-mode regression",
    "nfr_coverage": "NFR coverage",
    "explicit_out_of_scope": "Explicit out of scope",
    "investigated_and_rejected": "Investigated and rejected",
    "technical_notes": "Technical notes",
    "known_limitations": "Known limitations",
    "evidence_gaps": "Evidence gaps",
    "coverage_gate_result": "Coverage gate result",
}
_CANONICAL_SECTION_ORDER = (
    "issue_understanding",
    "product_scope",
    "acceptance_contract",
    *tuple(_CANONICAL_SECTION_TITLES)[2:],
)


class SecondPassInfluenceStatus(StrEnum):
    PASSED = "PASSED"
    BLOCKED = "BLOCKED"


class SecondPassInfluenceReason(StrEnum):
    AUDIT_INPUT_INVALID = "AUDIT_INPUT_INVALID"
    REQUEST_MISMATCH = "REQUEST_MISMATCH"
    DISABLED_TRACE_MISSING = "DISABLED_TRACE_MISSING"
    SECOND_PASS_TRACE_MISSING = "SECOND_PASS_TRACE_MISSING"
    DISABLED_MODE_NOT_PROVED = "DISABLED_MODE_NOT_PROVED"
    SECOND_PASS_MODE_NOT_PROVED = "SECOND_PASS_MODE_NOT_PROVED"
    TRACE_RESULT_MISMATCH = "TRACE_RESULT_MISMATCH"
    REASONING_INPUT_CHANGED = "REASONING_INPUT_CHANGED"
    QUESTIONS_CHANGED = "QUESTIONS_CHANGED"
    ACCEPTANCE_CANDIDATES_CHANGED = "ACCEPTANCE_CANDIDATES_CHANGED"
    ACCEPTANCE_PROMOTIONS_CHANGED = "ACCEPTANCE_PROMOTIONS_CHANGED"
    ACCEPTANCE_OUTPUT_CHANGED = "ACCEPTANCE_OUTPUT_CHANGED"
    ACCEPTANCE_LINEAGE_CHANGED = "ACCEPTANCE_LINEAGE_CHANGED"
    RESULT_CONTRACT_CHANGED = "RESULT_CONTRACT_CHANGED"
    RESULT_STATUS_CHANGED = "RESULT_STATUS_CHANGED"
    OUTPUT_PROJECTION_MISMATCH = "OUTPUT_PROJECTION_MISMATCH"
    PLAN_CONTRACT_CHANGED = "PLAN_CONTRACT_CHANGED"
    GATE_RESULT_CHANGED = "GATE_RESULT_CHANGED"
    LOCAL_EVIDENCE_CHANGED = "LOCAL_EVIDENCE_CHANGED"
    PROVIDER_TRACE_BUNDLE_MISMATCH = "PROVIDER_TRACE_BUNDLE_MISMATCH"
    PROVIDER_EVIDENCE_QUESTION_MISMATCH = "PROVIDER_EVIDENCE_QUESTION_MISMATCH"
    PROVIDER_EVIDENCE_NOT_FUSED = "PROVIDER_EVIDENCE_NOT_FUSED"
    PROVIDER_EVIDENCE_NOT_CONSUMED_BY_VERIFIER = (
        "PROVIDER_EVIDENCE_NOT_CONSUMED_BY_VERIFIER"
    )
    PROVIDER_INFLUENCE_NOT_ROUTED = "PROVIDER_INFLUENCE_NOT_ROUTED"
    PROVIDER_INFLUENCE_NOT_MATERIAL = "PROVIDER_INFLUENCE_NOT_MATERIAL"
    PROVIDER_INFLUENCE_NOT_NORMALIZED = "PROVIDER_INFLUENCE_NOT_NORMALIZED"
    PROVIDER_INFLUENCE_NOT_VERIFIED = "PROVIDER_INFLUENCE_NOT_VERIFIED"
    PROVIDER_INFLUENCE_HAS_NO_DISPOSITION = "PROVIDER_INFLUENCE_HAS_NO_DISPOSITION"
    PROVIDER_INFLUENCE_NOT_RENDERED = "PROVIDER_INFLUENCE_NOT_RENDERED"
    PROVIDER_INFLUENCE_CARDINALITY = "PROVIDER_INFLUENCE_CARDINALITY"
    UNEXPLAINED_HYPOTHESIS_CHANGE = "UNEXPLAINED_HYPOTHESIS_CHANGE"
    UNEXPLAINED_DISPOSITION_CHANGE = "UNEXPLAINED_DISPOSITION_CHANGE"
    UNEXPLAINED_OPEN_QUESTION_CHANGE = "UNEXPLAINED_OPEN_QUESTION_CHANGE"
    UNEXPLAINED_OUTPUT_GROWTH = "UNEXPLAINED_OUTPUT_GROWTH"
    UNEXPLAINED_OUTPUT_REMOVAL = "UNEXPLAINED_OUTPUT_REMOVAL"
    UNEXPLAINED_OUTPUT_ORDER_CHANGE = "UNEXPLAINED_OUTPUT_ORDER_CHANGE"
    UNEXPLAINED_PUBLIC_OUTPUT_CHANGE = "UNEXPLAINED_PUBLIC_OUTPUT_CHANGE"
    IMPLEMENTATION_HANDOFF_LINEAGE_MISMATCH = "IMPLEMENTATION_HANDOFF_LINEAGE_MISMATCH"
    STRUCTURED_PLAN_MISSING = "STRUCTURED_PLAN_MISSING"


class SecondPassSectionDelta(BaseModel):
    """Content-free plan delta for one canonical section."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    section_key: str = Field(min_length=1, max_length=100)
    disabled_item_count: int = Field(ge=0)
    second_pass_item_count: int = Field(ge=0)
    added_item_sha256s: tuple[str, ...] = ()
    removed_item_sha256s: tuple[str, ...] = ()


class SecondPassInfluenceLineage(BaseModel):
    """Exact canonical IDs for one provider-influenced material question."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str = Field(pattern=r"^question:[a-f0-9]{32}$")
    materiality: QueryMateriality
    provider_evidence_ids: tuple[str, ...]
    hypothesis_ids: tuple[str, ...]
    disposition_ids: tuple[str, ...]
    output_section_keys: tuple[str, ...]
    output_item_sha256s: tuple[str, ...]

    @model_validator(mode="after")
    def validate_complete_lineage(self) -> "SecondPassInfluenceLineage":
        if self.materiality not in {QueryMateriality.P0, QueryMateriality.P1}:
            raise ValueError("second-pass influence requires a material question")
        if not self.provider_evidence_ids:
            raise ValueError("second-pass influence requires provider evidence")
        if not self.hypothesis_ids:
            raise ValueError("second-pass influence requires a hypothesis")
        if not self.disposition_ids:
            raise ValueError("second-pass influence requires a disposition")
        if not self.output_section_keys or not self.output_item_sha256s:
            raise ValueError("second-pass influence requires a rendered location")
        return self


class SecondPassInfluenceDecision(BaseModel):
    """Release/rollout decision for one disabled-versus-SECOND_PASS pair."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["aem-guides-fluffyjaws-second-pass-influence-v1"] = (
        SECOND_PASS_INFLUENCE_SCHEMA
    )
    decision_id: str = Field(default="", pattern=r"^(?:fj-influence:[a-f0-9]{32})?$")
    status: SecondPassInfluenceStatus
    request_id: str
    disabled_run_id: str
    second_pass_run_id: str
    disabled_output_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    second_pass_output_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    selected_output_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rollback_applied: bool
    questions_unchanged: bool
    acceptance_output_unchanged: bool
    provider_fused_evidence_ids: tuple[str, ...] = ()
    provider_consumed_evidence_ids: tuple[str, ...] = ()
    changed_hypothesis_ids: tuple[str, ...] = ()
    changed_disposition_ids: tuple[str, ...] = ()
    added_open_question_ids: tuple[str, ...] = ()
    removed_open_question_ids: tuple[str, ...] = ()
    section_deltas: tuple[SecondPassSectionDelta, ...] = ()
    influence_lineages: tuple[SecondPassInfluenceLineage, ...] = ()
    blocking_reason_codes: tuple[SecondPassInfluenceReason, ...] = ()

    @model_validator(mode="after")
    def identify_and_validate(self) -> "SecondPassInfluenceDecision":
        reasons = tuple(sorted(set(self.blocking_reason_codes), key=str))
        object.__setattr__(self, "blocking_reason_codes", reasons)
        blocked = bool(reasons)
        if (self.status == SecondPassInfluenceStatus.BLOCKED) != blocked:
            raise ValueError("influence status must reflect blocking reasons")
        if self.rollback_applied != blocked:
            raise ValueError("blocked influence must select deterministic rollback")
        expected_selected = (
            self.disabled_output_sha256 if blocked else self.second_pass_output_sha256
        )
        if self.selected_output_sha256 != expected_selected:
            raise ValueError("selected output does not match influence decision")
        identity = self.model_dump(mode="json", exclude={"decision_id"})
        expected_id = f"fj-influence:{stable_sha256(identity)[:32]}"
        if self.decision_id and self.decision_id != expected_id:
            raise ValueError("decision_id does not match deterministic influence audit")
        object.__setattr__(self, "decision_id", expected_id)
        return self


_LAST_SECOND_PASS_INFLUENCE_DECISION = ContextVar(
    "aem_guides_last_second_pass_influence_decision",
    default=None,
)


def get_last_second_pass_influence_decision() -> SecondPassInfluenceDecision | None:
    """Return the latest content-minimal paired rollout decision."""

    decision = _LAST_SECOND_PASS_INFLUENCE_DECISION.get()
    return decision.model_copy(deep=True) if decision is not None else None


def _payload_rows(result: GenerationResult, key: str) -> list[dict[str, Any]]:
    value = result.output_payload.get(key, [])
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        return []
    return value


def _payload_value(result: GenerationResult, key: str) -> Any:
    return result.output_payload.get(key)


def _plan(result: GenerationResult) -> StructuredQEPlan | None:
    if result.structured_plan is None:
        return None
    payload_plan = result.output_payload.get("structured_plan")
    if payload_plan != result.structured_plan.model_dump(mode="json"):
        return None
    return result.structured_plan


def _sections(plan: StructuredQEPlan | None) -> dict[str, PlanSection]:
    if plan is None:
        return {}
    return {row.section_key: row for row in plan.sections}


def _section_item_hash(section_key: str, item: str) -> str:
    return stable_sha256({"section_key": section_key, "item": item})


def _plain_candidate(value: str) -> str:
    """Mirror the canonical renderer's ontology-label projection."""

    prefix, separator, remainder = value.partition(": ")
    if (
        separator
        and prefix
        and all(character.isupper() or character == "_" for character in prefix)
    ):
        return f"{prefix.replace('_', ' ').capitalize()}: {remainder}"
    return value


def _record_set(rows: list[dict[str, Any]]) -> set[str]:
    return {stable_sha256(row) for row in rows}


def _hypotheses(result: GenerationResult) -> list[BehaviorHypothesis]:
    return [
        BehaviorHypothesis.model_validate(row)
        for row in _payload_rows(result, "hypotheses")
    ]


def _dispositions(result: GenerationResult) -> list[CoverageDispositionRecord]:
    return [
        CoverageDispositionRecord.model_validate(row)
        for row in _payload_rows(result, "coverage_dispositions")
    ]


def _candidates(result: GenerationResult) -> list[AcceptanceCandidate]:
    return [
        AcceptanceCandidate.model_validate(row)
        for row in _payload_rows(result, "acceptance_candidates")
    ]


def _promotions(result: GenerationResult) -> list[AcceptancePromotionDecision]:
    return [
        AcceptancePromotionDecision.model_validate(row)
        for row in _payload_rows(result, "promotion_decisions")
    ]


def _retrievals(result: GenerationResult) -> list[DirectedRetrievalRecord]:
    return [
        DirectedRetrievalRecord.model_validate(row)
        for row in _payload_rows(result, "directed_retrievals")
    ]


def _implementation_handoffs(
    result: GenerationResult,
) -> list[GitHubImplementationVerificationHandoff]:
    return [
        GitHubImplementationVerificationHandoff.model_validate(row)
        for row in _payload_rows(result, "github_implementation_verification_handoffs")
    ]


def _implementation_results(
    result: GenerationResult,
) -> list[GitHubImplementationVerificationResult]:
    return [
        GitHubImplementationVerificationResult.model_validate(row)
        for row in _payload_rows(result, "github_implementation_verification_results")
    ]


def _behavior_model(result: GenerationResult) -> CanonicalBehaviorModel:
    return CanonicalBehaviorModel.model_validate(
        result.output_payload.get("behavior_model", {})
    )


def _metrics_are_coherent(result: GenerationResult) -> bool:
    contract_facts = result.output_payload.get("contract_facts", {})
    contract_fact_rows = (
        contract_facts.get("facts", []) if isinstance(contract_facts, dict) else []
    )
    expected = {
        "closure_dimension_count": len(_payload_rows(result, "semantic_closure")),
        "contract_fact_count": len(contract_fact_rows),
        "evidence_record_count": len(result.evidence_bundle.records),
        "github_implementation_handoff_count": len(
            _payload_rows(result, "github_implementation_verification_handoffs")
        ),
        "github_implementation_result_count": len(
            _payload_rows(result, "github_implementation_verification_results")
        ),
        "second_pass_retrieval_count": len(
            _payload_rows(result, "directed_retrievals")
        ),
        "missing_question_submitted_count": len(
            (result.output_payload.get("missing_question_quality") or {}).get(
                "submitted_questions", []
            )
        ),
        "missing_question_accepted_count": len(
            _payload_rows(result, "missing_questions")
        ),
        "missing_question_rejected_count": (
            len(
                (result.output_payload.get("missing_question_quality") or {}).get(
                    "submitted_questions", []
                )
            )
            - len(_payload_rows(result, "missing_questions"))
        ),
        "missing_question_resolved_by_evidence_count": sum(
            row.get("status") == "RESOLVED_BY_EVIDENCE"
            for row in _payload_rows(result, "missing_question_resolutions")
        ),
        "stage_count": len(result.trace.stage_trace),
        "used_evidence_count": sum(
            1 for row in result.evidence_bundle.records if row.used
        ),
    }
    return result.metrics == expected


def _runtime_trace_is_coherent(result: GenerationResult) -> bool:
    trace = result.trace
    if (
        trace.run_id != result.run_id
        or trace.request_id != result.request_id
        or trace.evidence_bundle_id != result.evidence_bundle_id
        or trace.warnings != result.runtime_warnings
    ):
        return False
    retrieval_ids = [row.retrieval_id for row in _retrievals(result)]
    if trace.second_pass_retrievals != retrieval_ids:
        return False
    used_evidence_ids = sorted(
        row.evidence_id for row in result.evidence_bundle.records if row.used
    )
    if sorted(trace.consumed_evidence_ids) != used_evidence_ids:
        return False
    expected_source_counts = dict(
        sorted(
            Counter(
                row.source_type.value for row in result.evidence_bundle.records
            ).items()
        )
    )
    if trace.source_counts != expected_source_counts:
        return False
    handoffs = _implementation_handoffs(result)
    implementation_results = _implementation_results(result)
    handoff_ids = sorted(row.handoff_id for row in handoffs)
    result_ids = sorted(row.result_id for row in implementation_results)
    unresolved_handoff_ids = sorted(
        str(value)
        for value in result.output_payload.get(
            "unresolved_github_implementation_handoff_ids", []
        )
    )
    if len(unresolved_handoff_ids) != len(set(unresolved_handoff_ids)) or not set(
        unresolved_handoff_ids
    ).issubset(handoff_ids):
        return False
    rejected_result_evidence_ids = [
        str(value)
        for value in result.output_payload.get(
            "rejected_github_implementation_result_evidence_ids", []
        )
    ]
    if len(rejected_result_evidence_ids) != len(
        set(rejected_result_evidence_ids)
    ) or not set(rejected_result_evidence_ids).issubset(
        {row.evidence_id for row in result.evidence_bundle.records}
    ):
        return False
    if (
        sorted(trace.implementation_verification_handoff_ids) != handoff_ids
        or sorted(trace.implementation_verification_result_ids) != result_ids
        or sorted(trace.unresolved_implementation_handoff_ids) != unresolved_handoff_ids
    ):
        return False
    hypotheses = _hypotheses(result)
    expected_confirmed = sorted(
        row.hypothesis_id for row in hypotheses if row.state.value == "CONFIRMED"
    )
    expected_rejected = sorted(
        row.hypothesis_id for row in hypotheses if row.state.value == "REJECTED"
    )
    expected_unresolved = sorted(
        row.hypothesis_id for row in hypotheses if row.state.value == "UNRESOLVED"
    )
    if (
        sorted(trace.hypotheses_confirmed) != expected_confirmed
        or sorted(trace.hypotheses_rejected) != expected_rejected
        or sorted(trace.hypotheses_unresolved) != expected_unresolved
    ):
        return False
    candidates = _candidates(result)
    dispositions = _dispositions(result)
    promotions = _promotions(result)
    if sorted(trace.ac_candidates) != sorted(row.candidate_id for row in candidates):
        return False
    expected_regressions = sorted(
        row.disposition_id
        for row in dispositions
        if row.disposition
        not in {
            CoverageDisposition.ACCEPTANCE_CONTRACT,
            CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
            CoverageDisposition.OPEN_QUESTION,
        }
    )
    if sorted(trace.regression_candidates) != expected_regressions:
        return False
    expected_rejections = sorted(
        row.candidate_id
        for row in promotions
        if row.status in {PromotionStatus.REJECTED, PromotionStatus.BLOCKED}
    )
    if sorted(trace.promotion_rejections) != expected_rejections:
        return False
    if trace.gate_failures != [
        failure for gate in result.gate_decisions for failure in gate.failures
    ]:
        return False
    return True


def _canonical_plan_markdown(plan: StructuredQEPlan) -> str:
    lines = [f"# {plan.jira_key} — QE plan", ""]
    for section in plan.sections:
        lines.extend([f"## {section.title}", ""])
        lines.extend(f"- {item}" for item in section.items)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _projection_is_coherent(result: GenerationResult) -> bool:
    plan = _plan(result)
    if plan is None:
        return False
    plan_payload = plan.model_dump(mode="json")
    if result.structured_output != result.output_payload:
        return False
    if result.structured_output.get("structured_plan") != plan_payload:
        return False
    markdown = _canonical_plan_markdown(plan)
    if result.output_payload.get("plan_markdown") != markdown:
        return False
    if result.rendered_output != markdown:
        return False
    dumped_gates = [row.model_dump(mode="json") for row in result.gate_decisions]
    if result.output_payload.get("gate_decisions") != dumped_gates:
        return False
    if plan.gate_decisions != result.gate_decisions:
        return False
    if len({row.section_key for row in plan.sections}) != len(plan.sections):
        return False
    section_keys = tuple(row.section_key for row in plan.sections)
    if any(key not in _CANONICAL_SECTION_ORDER for key in section_keys):
        return False
    expected_section_keys = tuple(
        key for key in _CANONICAL_SECTION_ORDER if key in set(section_keys)
    )
    if section_keys != expected_section_keys:
        return False
    for section in plan.sections:
        if section.section_key == "acceptance_contract":
            if section.title not in {
                "Acceptance contract",
                "Proposed acceptance contract",
            }:
                return False
        elif _CANONICAL_SECTION_TITLES.get(section.section_key) != section.title:
            return False
    return all(
        bool(section.items)
        and len(section.items) == len(set(section.items))
        and section.source_record_ids == sorted(set(section.source_record_ids))
        for section in plan.sections
    )


def _rows_by_id(
    rows: list[dict[str, Any]],
    *,
    id_key: str,
) -> dict[str, dict[str, Any]]:
    return {
        str(row[id_key]): row
        for row in rows
        if isinstance(row.get(id_key), str) and row[id_key]
    }


def _question_text_by_id(result: GenerationResult) -> dict[str, str]:
    return {
        str(row["question_id"]): str(row["question"])
        for row in _payload_rows(result, "missing_questions")
        if row.get("question_id") and row.get("question")
    }


def _source_linked_pairs(
    *,
    sections: dict[str, PlanSection],
    record_ids: set[str],
    rendered_texts: set[str],
) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for section in sections.values():
        if not record_ids.intersection(section.source_record_ids):
            continue
        for item in section.items:
            if item in rendered_texts:
                pairs.add((section.section_key, item))
    return pairs


def audit_second_pass_influence(
    *,
    disabled_result: GenerationResult,
    second_pass_result: GenerationResult,
    disabled_question_trace: QuestionRetrievalTraceBundle | None,
    second_pass_question_trace: QuestionRetrievalTraceBundle | None,
    fluffyjaws_trace: FluffyJawsShadowRunTrace | None,
) -> SecondPassInfluenceDecision:
    """Compare paired runs and fail closed on unexplained semantic/output change."""

    reasons: set[SecondPassInfluenceReason] = set()
    if disabled_result.request_id != second_pass_result.request_id:
        reasons.add(SecondPassInfluenceReason.REQUEST_MISMATCH)

    stable_result_fields = (
        "runtime_id",
        "runtime_version",
        "request_id",
        "output_contract",
        "output_kind",
        "validation_status",
        "validation_result",
        "runtime_warnings",
    )
    if any(
        getattr(disabled_result, field) != getattr(second_pass_result, field)
        for field in stable_result_fields
    ):
        reasons.add(SecondPassInfluenceReason.RESULT_CONTRACT_CHANGED)
    if disabled_result.status != second_pass_result.status:
        reasons.add(SecondPassInfluenceReason.RESULT_STATUS_CHANGED)
    if not _projection_is_coherent(disabled_result) or not _projection_is_coherent(
        second_pass_result
    ):
        reasons.add(SecondPassInfluenceReason.OUTPUT_PROJECTION_MISMATCH)

    disabled_record_by_id = {
        row.evidence_id: row for row in disabled_result.evidence_bundle.records
    }
    second_pass_record_by_id = {
        row.evidence_id: row for row in second_pass_result.evidence_bundle.records
    }
    if any(
        evidence_id not in second_pass_record_by_id
        or second_pass_record_by_id[evidence_id] != record
        for evidence_id, record in disabled_record_by_id.items()
    ):
        reasons.add(SecondPassInfluenceReason.LOCAL_EVIDENCE_CHANGED)
    if not _metrics_are_coherent(disabled_result) or not _metrics_are_coherent(
        second_pass_result
    ):
        reasons.add(SecondPassInfluenceReason.OUTPUT_PROJECTION_MISMATCH)
    if not _runtime_trace_is_coherent(
        disabled_result
    ) or not _runtime_trace_is_coherent(second_pass_result):
        reasons.add(SecondPassInfluenceReason.TRACE_RESULT_MISMATCH)

    if disabled_question_trace is None:
        reasons.add(SecondPassInfluenceReason.DISABLED_TRACE_MISSING)
    elif disabled_question_trace.fluffyjaws_mode != (
        FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED
    ):
        reasons.add(SecondPassInfluenceReason.DISABLED_MODE_NOT_PROVED)
    if second_pass_question_trace is None or fluffyjaws_trace is None:
        reasons.add(SecondPassInfluenceReason.SECOND_PASS_TRACE_MISSING)
    else:
        if (
            second_pass_question_trace.fluffyjaws_mode
            != (FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS)
            or fluffyjaws_trace.mode != FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS
        ):
            reasons.add(SecondPassInfluenceReason.SECOND_PASS_MODE_NOT_PROVED)

    for result, trace in (
        (disabled_result, disabled_question_trace),
        (second_pass_result, second_pass_question_trace),
    ):
        if trace is not None and (
            trace.run_id != result.run_id
            or trace.request_id != result.request_id
            or trace.output_sha256 != result.output_sha256
        ):
            reasons.add(SecondPassInfluenceReason.TRACE_RESULT_MISMATCH)

    for key in _PRE_RETRIEVAL_PROJECTIONS:
        if _payload_value(disabled_result, key) != _payload_value(
            second_pass_result, key
        ):
            reasons.add(
                SecondPassInfluenceReason.QUESTIONS_CHANGED
                if key == "missing_questions"
                else SecondPassInfluenceReason.REASONING_INPUT_CHANGED
            )

    questions_unchanged = _payload_value(
        disabled_result, "missing_questions"
    ) == _payload_value(second_pass_result, "missing_questions")
    if disabled_question_trace is not None and second_pass_question_trace is not None:
        if (
            disabled_question_trace.generated_question_ids
            != second_pass_question_trace.generated_question_ids
        ):
            questions_unchanged = False
            reasons.add(SecondPassInfluenceReason.QUESTIONS_CHANGED)

    disabled_candidates = _candidates(disabled_result)
    second_pass_candidates = _candidates(second_pass_result)
    if disabled_candidates != second_pass_candidates:
        reasons.add(SecondPassInfluenceReason.ACCEPTANCE_CANDIDATES_CHANGED)
    disabled_promotions = _promotions(disabled_result)
    second_pass_promotions = _promotions(second_pass_result)
    if disabled_promotions != second_pass_promotions:
        reasons.add(SecondPassInfluenceReason.ACCEPTANCE_PROMOTIONS_CHANGED)

    disabled_plan = _plan(disabled_result)
    second_pass_plan = _plan(second_pass_result)
    if disabled_plan is None or second_pass_plan is None:
        reasons.add(SecondPassInfluenceReason.STRUCTURED_PLAN_MISSING)
    disabled_sections = _sections(disabled_plan)
    second_pass_sections = _sections(second_pass_plan)
    disabled_acceptance = tuple(
        disabled_sections.get(
            "acceptance_contract",
            PlanSection(section_key="acceptance_contract", title="Acceptance contract"),
        ).items
    )
    second_pass_acceptance = tuple(
        second_pass_sections.get(
            "acceptance_contract",
            PlanSection(section_key="acceptance_contract", title="Acceptance contract"),
        ).items
    )
    acceptance_output_unchanged = disabled_acceptance == second_pass_acceptance
    if not acceptance_output_unchanged:
        reasons.add(SecondPassInfluenceReason.ACCEPTANCE_OUTPUT_CHANGED)
    disabled_acceptance_section = disabled_sections.get("acceptance_contract")
    second_pass_acceptance_section = second_pass_sections.get("acceptance_contract")
    if disabled_acceptance_section != second_pass_acceptance_section:
        reasons.add(SecondPassInfluenceReason.ACCEPTANCE_LINEAGE_CHANGED)
    if disabled_plan is not None and second_pass_plan is not None:
        if any(
            getattr(disabled_plan, field) != getattr(second_pass_plan, field)
            for field in (
                "jira_key",
                "contract_mode",
                "contract_fact_ids",
                "closure_ids",
                "promoted_candidate_ids",
            )
        ):
            reasons.add(SecondPassInfluenceReason.PLAN_CONTRACT_CHANGED)
        if disabled_plan.gate_decisions != second_pass_plan.gate_decisions:
            reasons.add(SecondPassInfluenceReason.GATE_RESULT_CHANGED)
    if disabled_result.gate_decisions != second_pass_result.gate_decisions:
        reasons.add(SecondPassInfluenceReason.GATE_RESULT_CHANGED)

    disabled_evidence_ids = {
        row.evidence_id for row in disabled_result.evidence_bundle.records
    }
    second_pass_evidence_ids = {
        row.evidence_id for row in second_pass_result.evidence_bundle.records
    }
    fused_ids = set(fluffyjaws_trace.fused_evidence_ids) if fluffyjaws_trace else set()
    consumed_ids = (
        set(fluffyjaws_trace.consumed_evidence_ids) if fluffyjaws_trace else set()
    )
    added_evidence_ids = second_pass_evidence_ids - disabled_evidence_ids
    if not added_evidence_ids.issubset(fused_ids) or not fused_ids.issubset(
        second_pass_evidence_ids
    ):
        reasons.add(SecondPassInfluenceReason.PROVIDER_EVIDENCE_NOT_FUSED)
    if not consumed_ids.issubset(fused_ids):
        reasons.add(
            SecondPassInfluenceReason.PROVIDER_EVIDENCE_NOT_CONSUMED_BY_VERIFIER
        )
    if fluffyjaws_trace is not None and (
        fluffyjaws_trace.request_id != second_pass_result.request_id
        or fluffyjaws_trace.run_id != second_pass_result.run_id
        or fluffyjaws_trace.evidence_bundle_id != disabled_result.evidence_bundle_id
        or (
            fluffyjaws_trace.fused_bundle_id
            and fluffyjaws_trace.fused_bundle_id
            != second_pass_result.evidence_bundle_id
        )
    ):
        reasons.add(SecondPassInfluenceReason.PROVIDER_TRACE_BUNDLE_MISMATCH)
    fused_by_question = (
        {
            question_id: tuple(sorted(evidence_ids))
            for question_id, evidence_ids in (
                fluffyjaws_trace.fused_evidence_ids_by_question.items()
            )
        }
        if fluffyjaws_trace is not None
        else {}
    )
    expected_fused_by_question: dict[str, set[str]] = {}
    if fluffyjaws_trace is not None:
        for call in fluffyjaws_trace.calls:
            expected_fused_by_question.setdefault(call.question_id, set()).update(
                call.semantic_fusion_evidence_ids
            )
    normalized_expected_fused = {
        question_id: tuple(sorted(evidence_ids))
        for question_id, evidence_ids in expected_fused_by_question.items()
        if evidence_ids
    }
    if fused_by_question != normalized_expected_fused:
        reasons.add(SecondPassInfluenceReason.PROVIDER_EVIDENCE_QUESTION_MISMATCH)

    disabled_hypotheses = _hypotheses(disabled_result)
    second_pass_hypotheses = _hypotheses(second_pass_result)
    disabled_hypothesis_hashes = _record_set(
        [row.model_dump(mode="json") for row in disabled_hypotheses]
    )
    changed_hypotheses = [
        row
        for row in second_pass_hypotheses
        if stable_sha256(row.model_dump(mode="json")) not in disabled_hypothesis_hashes
    ]
    second_pass_hypothesis_hashes = _record_set(
        [row.model_dump(mode="json") for row in second_pass_hypotheses]
    )
    removed_hypotheses = [
        row
        for row in disabled_hypotheses
        if stable_sha256(row.model_dump(mode="json"))
        not in second_pass_hypothesis_hashes
    ]
    provider_hypotheses = [
        row
        for row in second_pass_hypotheses
        if consumed_ids
        & (
            set(row.supporting_evidence_ids)
            | set(row.contradicting_evidence_ids)
            | set(row.verification_evidence_ids)
        )
    ]
    provider_hypothesis_ids = {row.hypothesis_id for row in provider_hypotheses}
    provider_question_ids = {
        row.derived_from_question_id for row in provider_hypotheses
    }
    disabled_behavior_model = _behavior_model(disabled_result)
    second_pass_behavior_model = _behavior_model(second_pass_result)
    for field in (
        "primary_entities",
        "domains",
        "publishing_transformation_stages",
        "generated_artifact_delivery",
        "generated_output_oracles",
        "lifecycle_operations",
    ):
        if getattr(disabled_behavior_model, field) != getattr(
            second_pass_behavior_model, field
        ):
            reasons.add(SecondPassInfluenceReason.UNEXPLAINED_PUBLIC_OUTPUT_CHANGE)
    disabled_node_by_id = {
        row.node_id: row for row in disabled_behavior_model.graph.nodes
    }
    second_pass_node_by_id = {
        row.node_id: row for row in second_pass_behavior_model.graph.nodes
    }
    added_nodes = [
        row
        for node_id, row in second_pass_node_by_id.items()
        if node_id not in disabled_node_by_id
    ]
    removed_nodes = [
        row
        for node_id, row in disabled_node_by_id.items()
        if node_id not in second_pass_node_by_id
    ]
    provider_statements = {
        row.statement
        for row in disabled_hypotheses + second_pass_hypotheses
        if row.derived_from_question_id in set(fused_by_question)
    }
    if any(
        not set(row.source_evidence_ids).intersection(fused_ids)
        or row.node_type not in {"VERIFIED_HYPOTHESIS", "EVIDENCE_SOURCE"}
        for row in added_nodes
    ) or any(row.label not in provider_statements for row in removed_nodes):
        reasons.add(SecondPassInfluenceReason.UNEXPLAINED_PUBLIC_OUTPUT_CHANGE)
    provider_changed_node_ids = {row.node_id for row in added_nodes + removed_nodes}
    disabled_edge_by_id = {
        row.edge_id: row for row in disabled_behavior_model.graph.edges
    }
    second_pass_edge_by_id = {
        row.edge_id: row for row in second_pass_behavior_model.graph.edges
    }
    changed_edges = [
        row
        for edge_id, row in second_pass_edge_by_id.items()
        if edge_id not in disabled_edge_by_id
    ] + [
        row
        for edge_id, row in disabled_edge_by_id.items()
        if edge_id not in second_pass_edge_by_id
    ]
    if any(
        not set(row.provenance_evidence_ids).intersection(fused_ids)
        and row.source_node_id not in provider_changed_node_ids
        and row.target_node_id not in provider_changed_node_ids
        for row in changed_edges
    ):
        reasons.add(SecondPassInfluenceReason.UNEXPLAINED_PUBLIC_OUTPUT_CHANGE)
    if any(
        row.hypothesis_id not in provider_hypothesis_ids for row in changed_hypotheses
    ):
        reasons.add(SecondPassInfluenceReason.UNEXPLAINED_HYPOTHESIS_CHANGE)
    if any(
        row.derived_from_question_id not in provider_question_ids
        for row in removed_hypotheses
    ):
        reasons.add(SecondPassInfluenceReason.UNEXPLAINED_HYPOTHESIS_CHANGE)
    cited_provider_ids = {
        evidence_id
        for row in provider_hypotheses
        for evidence_id in (
            list(row.supporting_evidence_ids)
            + list(row.contradicting_evidence_ids)
            + list(row.verification_evidence_ids)
        )
        if evidence_id in fused_ids
    }
    if cited_provider_ids != consumed_ids:
        reasons.add(
            SecondPassInfluenceReason.PROVIDER_EVIDENCE_NOT_CONSUMED_BY_VERIFIER
        )
    if any(
        evidence_id not in set(fused_by_question.get(row.derived_from_question_id, ()))
        for row in provider_hypotheses
        for evidence_id in (
            list(row.supporting_evidence_ids)
            + list(row.contradicting_evidence_ids)
            + list(row.verification_evidence_ids)
        )
        if evidence_id in consumed_ids
    ):
        reasons.add(SecondPassInfluenceReason.PROVIDER_EVIDENCE_QUESTION_MISMATCH)
    if any(
        sum(
            item.derived_from_question_id == question_id for item in provider_hypotheses
        )
        != 1
        for question_id in provider_question_ids
    ):
        reasons.add(SecondPassInfluenceReason.PROVIDER_INFLUENCE_CARDINALITY)
    disabled_dispositions = _dispositions(disabled_result)
    second_pass_dispositions = _dispositions(second_pass_result)
    disabled_disposition_hashes = _record_set(
        [row.model_dump(mode="json") for row in disabled_dispositions]
    )
    changed_dispositions = [
        row
        for row in second_pass_dispositions
        if stable_sha256(row.model_dump(mode="json")) not in disabled_disposition_hashes
    ]
    second_pass_disposition_hashes = _record_set(
        [row.model_dump(mode="json") for row in second_pass_dispositions]
    )
    removed_dispositions = [
        row
        for row in disabled_dispositions
        if stable_sha256(row.model_dump(mode="json"))
        not in second_pass_disposition_hashes
    ]
    provider_dispositions = [
        row
        for row in second_pass_dispositions
        if set(row.source_hypothesis_ids) & provider_hypothesis_ids
        and set(row.source_question_ids) & provider_question_ids
    ]
    changed_provider_dispositions = [
        row
        for row in changed_dispositions
        if set(row.source_hypothesis_ids) & provider_hypothesis_ids
        and set(row.source_question_ids) & provider_question_ids
    ]
    if len(changed_provider_dispositions) != len(changed_dispositions):
        reasons.add(SecondPassInfluenceReason.UNEXPLAINED_DISPOSITION_CHANGE)
    removed_provider_dispositions = [
        row
        for row in removed_dispositions
        if set(row.source_question_ids) & provider_question_ids
    ]
    if len(removed_provider_dispositions) != len(removed_dispositions):
        reasons.add(SecondPassInfluenceReason.UNEXPLAINED_DISPOSITION_CHANGE)
    if any(
        sum(
            question_id in item.source_question_ids
            and bool(set(item.source_hypothesis_ids) & provider_hypothesis_ids)
            for item in provider_dispositions
        )
        != 1
        for question_id in provider_question_ids
    ):
        reasons.add(SecondPassInfluenceReason.PROVIDER_INFLUENCE_CARDINALITY)
    if (
        disabled_plan is not None
        and disabled_plan.coverage_disposition_ids
        != [row.disposition_id for row in disabled_dispositions]
    ) or (
        second_pass_plan is not None
        and second_pass_plan.coverage_disposition_ids
        != [row.disposition_id for row in second_pass_dispositions]
    ):
        reasons.add(SecondPassInfluenceReason.OUTPUT_PROJECTION_MISMATCH)

    question_trace_by_id = (
        {row.question_id: row for row in second_pass_question_trace.questions}
        if second_pass_question_trace is not None
        else {}
    )
    routes_by_question = (
        {row.question_id: row for row in fluffyjaws_trace.routing_records}
        if fluffyjaws_trace is not None
        else {}
    )
    dispositions_by_question: dict[str, list[CoverageDispositionRecord]] = {}
    for disposition in provider_dispositions:
        for question_id in disposition.source_question_ids:
            dispositions_by_question.setdefault(question_id, []).append(disposition)

    explained_output_pairs: set[tuple[str, str]] = set()
    lineages: list[SecondPassInfluenceLineage] = []
    for question_id in sorted(provider_question_ids):
        row = question_trace_by_id.get(question_id)
        route = routes_by_question.get(question_id)
        question_hypotheses = [
            hypothesis
            for hypothesis in provider_hypotheses
            if hypothesis.derived_from_question_id == question_id
        ]
        question_evidence_ids = {
            evidence_id
            for hypothesis in question_hypotheses
            for evidence_id in (
                list(hypothesis.supporting_evidence_ids)
                + list(hypothesis.contradicting_evidence_ids)
                + list(hypothesis.verification_evidence_ids)
            )
            if evidence_id in consumed_ids
        }
        question_dispositions = dispositions_by_question.get(question_id, [])
        if route is None or not route.provider_called:
            reasons.add(SecondPassInfluenceReason.PROVIDER_INFLUENCE_NOT_ROUTED)
        if row is None or row.materiality not in {
            QueryMateriality.P0,
            QueryMateriality.P1,
        }:
            reasons.add(SecondPassInfluenceReason.PROVIDER_INFLUENCE_NOT_MATERIAL)
        if row is None or row.evidence_normalized.state != TraceAnswerState.YES:
            reasons.add(SecondPassInfluenceReason.PROVIDER_INFLUENCE_NOT_NORMALIZED)
        if row is None or row.evidence_used_by_verifier.state != TraceAnswerState.YES:
            reasons.add(SecondPassInfluenceReason.PROVIDER_INFLUENCE_NOT_VERIFIED)
        if not question_dispositions:
            reasons.add(SecondPassInfluenceReason.PROVIDER_INFLUENCE_HAS_NO_DISPOSITION)

        output_pairs: set[tuple[str, str]] = set()
        output_item_hashes: set[str] = set()
        for disposition in question_dispositions:
            rendered_text = _plain_candidate(disposition.candidate)
            for section in second_pass_sections.values():
                if (
                    disposition.disposition_id in section.source_record_ids
                    and rendered_text in section.items
                ):
                    output_pairs.add((section.section_key, rendered_text))
                    output_item_hashes.add(
                        _section_item_hash(section.section_key, rendered_text)
                    )
        explained_output_pairs.update(output_pairs)
        trace_locations = (
            {
                (location.section_key, location.source_record_id)
                for location in row.output_locations
            }
            if row is not None
            else set()
        )
        expected_locations = {
            (section_key, disposition.disposition_id)
            for disposition in question_dispositions
            for section_key, text in output_pairs
            if text == _plain_candidate(disposition.candidate)
        }
        if not output_pairs or not expected_locations.issubset(trace_locations):
            reasons.add(SecondPassInfluenceReason.PROVIDER_INFLUENCE_NOT_RENDERED)
        if (
            row is not None
            and question_evidence_ids
            and question_hypotheses
            and question_dispositions
            and output_pairs
            and expected_locations.issubset(trace_locations)
        ):
            lineages.append(
                SecondPassInfluenceLineage(
                    question_id=question_id,
                    materiality=row.materiality,
                    provider_evidence_ids=tuple(sorted(question_evidence_ids)),
                    hypothesis_ids=tuple(
                        sorted(item.hypothesis_id for item in question_hypotheses)
                    ),
                    disposition_ids=tuple(
                        sorted(item.disposition_id for item in question_dispositions)
                    ),
                    output_section_keys=tuple(
                        sorted({section_key for section_key, _ in output_pairs})
                    ),
                    output_item_sha256s=tuple(sorted(output_item_hashes)),
                )
            )

    disabled_related_record_ids = {
        row.disposition_id for row in removed_provider_dispositions
    } | provider_question_ids
    disabled_related_texts = {
        _plain_candidate(row.candidate) for row in removed_provider_dispositions
    } | {
        text
        for question_id, text in _question_text_by_id(disabled_result).items()
        if question_id in provider_question_ids
    }
    explained_removed_pairs = _source_linked_pairs(
        sections=disabled_sections,
        record_ids=disabled_related_record_ids,
        rendered_texts=disabled_related_texts,
    )
    provider_related_pairs = explained_output_pairs | explained_removed_pairs
    allowed_changed_source_ids = (
        provider_question_ids
        | {row.disposition_id for row in provider_dispositions}
        | {row.disposition_id for row in removed_provider_dispositions}
    )

    all_section_keys = sorted(set(disabled_sections) | set(second_pass_sections))
    section_deltas: list[SecondPassSectionDelta] = []
    unexplained_added_pairs: set[tuple[str, str]] = set()
    unexplained_removed_pairs: set[tuple[str, str]] = set()
    for section_key in all_section_keys:
        disabled_section = disabled_sections.get(
            section_key,
            PlanSection(section_key=section_key, title=section_key),
        )
        second_pass_section = second_pass_sections.get(
            section_key,
            PlanSection(section_key=section_key, title=section_key),
        )
        disabled_counter = Counter(disabled_section.items)
        second_pass_counter = Counter(second_pass_section.items)
        added_counter = second_pass_counter - disabled_counter
        removed_counter = disabled_counter - second_pass_counter
        added = [
            (section_key, item)
            for item, count in added_counter.items()
            for _ in range(count)
        ]
        removed = [
            (section_key, item)
            for item, count in removed_counter.items()
            for _ in range(count)
        ]
        if added or removed:
            section_deltas.append(
                SecondPassSectionDelta(
                    section_key=section_key,
                    disabled_item_count=len(disabled_section.items),
                    second_pass_item_count=len(second_pass_section.items),
                    added_item_sha256s=tuple(
                        sorted(_section_item_hash(*pair) for pair in added)
                    ),
                    removed_item_sha256s=tuple(
                        sorted(_section_item_hash(*pair) for pair in removed)
                    ),
                )
            )
        unexplained_added_pairs.update(set(added) - explained_output_pairs)
        unexplained_removed_pairs.update(set(removed) - explained_removed_pairs)
        disabled_unaffected = [
            item
            for item in disabled_section.items
            if (section_key, item) not in provider_related_pairs
        ]
        second_pass_unaffected = [
            item
            for item in second_pass_section.items
            if (section_key, item) not in provider_related_pairs
        ]
        if disabled_unaffected != second_pass_unaffected:
            reasons.add(SecondPassInfluenceReason.UNEXPLAINED_OUTPUT_ORDER_CHANGE)
        if (
            section_key in disabled_sections
            and section_key in second_pass_sections
            and disabled_section.title != second_pass_section.title
        ):
            reasons.add(SecondPassInfluenceReason.UNEXPLAINED_PUBLIC_OUTPUT_CHANGE)
        changed_source_ids = set(disabled_section.source_record_ids) ^ set(
            second_pass_section.source_record_ids
        )
        if changed_source_ids - allowed_changed_source_ids:
            reasons.add(SecondPassInfluenceReason.UNEXPLAINED_PUBLIC_OUTPUT_CHANGE)
    if unexplained_added_pairs:
        reasons.add(SecondPassInfluenceReason.UNEXPLAINED_OUTPUT_GROWTH)
    if unexplained_removed_pairs:
        reasons.add(SecondPassInfluenceReason.UNEXPLAINED_OUTPUT_REMOVAL)

    disabled_open_ids = set(disabled_plan.open_question_ids) if disabled_plan else set()
    second_pass_open_ids = (
        set(second_pass_plan.open_question_ids) if second_pass_plan else set()
    )
    added_open_ids = second_pass_open_ids - disabled_open_ids
    removed_open_ids = disabled_open_ids - second_pass_open_ids
    if (added_open_ids | removed_open_ids) - provider_question_ids:
        reasons.add(SecondPassInfluenceReason.UNEXPLAINED_OPEN_QUESTION_CHANGE)

    disabled_retrievals = {row.question_id: row for row in _retrievals(disabled_result)}
    second_pass_retrievals = {
        row.question_id: row for row in _retrievals(second_pass_result)
    }
    if set(disabled_retrievals) != set(second_pass_retrievals):
        reasons.add(SecondPassInfluenceReason.UNEXPLAINED_PUBLIC_OUTPUT_CHANGE)
    for question_id in sorted(set(disabled_retrievals) & set(second_pass_retrievals)):
        disabled_retrieval = disabled_retrievals[question_id]
        second_pass_retrieval = second_pass_retrievals[question_id]
        if disabled_retrieval == second_pass_retrieval:
            continue
        expected_provider_ids = set(fused_by_question.get(question_id, ()))
        stable_fields = ("query", "authority_subject", "target_source_types")
        disabled_matched = set(disabled_retrieval.matched_evidence_ids)
        second_pass_matched = set(second_pass_retrieval.matched_evidence_ids)
        if (
            not expected_provider_ids
            or any(
                getattr(disabled_retrieval, field)
                != getattr(second_pass_retrieval, field)
                for field in stable_fields
            )
            or not disabled_matched.issubset(second_pass_matched)
            or second_pass_matched - disabled_matched != expected_provider_ids
        ):
            reasons.add(SecondPassInfluenceReason.PROVIDER_EVIDENCE_QUESTION_MISMATCH)

    handoff_keys = (
        "github_implementation_verification_handoffs",
        "github_implementation_verification_results",
    )
    implementation_lineage_question_ids = set(fused_by_question)
    implementation_lineage_hypothesis_ids = {
        row.hypothesis_id
        for row in disabled_hypotheses + second_pass_hypotheses
        if row.derived_from_question_id in implementation_lineage_question_ids
    }
    for key in handoff_keys:
        disabled_rows = _payload_rows(disabled_result, key)
        disabled_hashes = _record_set(disabled_rows)
        second_pass_rows = _payload_rows(second_pass_result, key)
        second_pass_hashes = _record_set(second_pass_rows)
        changed_rows = [
            row for row in second_pass_rows if stable_sha256(row) not in disabled_hashes
        ]
        removed_rows = [
            row for row in disabled_rows if stable_sha256(row) not in second_pass_hashes
        ]
        if any(
            row.get("QUESTION_ID") not in implementation_lineage_question_ids
            or row.get("HYPOTHESIS_ID") not in implementation_lineage_hypothesis_ids
            for row in changed_rows + removed_rows
        ):
            reasons.add(
                SecondPassInfluenceReason.IMPLEMENTATION_HANDOFF_LINEAGE_MISMATCH
            )

    allowed_payload_changes = {
        "behavior_model",
        "coverage_dispositions",
        "directed_retrievals",
        "github_implementation_verification_handoffs",
        "github_implementation_verification_results",
        "hypotheses",
        "missing_question_resolutions",
        "plan_markdown",
        "rejected_github_implementation_result_evidence_ids",
        "structured_plan",
        "unresolved_github_implementation_handoff_ids",
    }
    changed_payload_keys = {
        key
        for key in set(disabled_result.output_payload)
        | set(second_pass_result.output_payload)
        if disabled_result.output_payload.get(key)
        != second_pass_result.output_payload.get(key)
    }
    if changed_payload_keys - allowed_payload_changes:
        reasons.add(SecondPassInfluenceReason.UNEXPLAINED_PUBLIC_OUTPUT_CHANGE)

    blocking_reasons = tuple(sorted(reasons, key=str))
    blocked = bool(blocking_reasons)
    return SecondPassInfluenceDecision(
        status=(
            SecondPassInfluenceStatus.BLOCKED
            if blocked
            else SecondPassInfluenceStatus.PASSED
        ),
        request_id=second_pass_result.request_id,
        disabled_run_id=disabled_result.run_id,
        second_pass_run_id=second_pass_result.run_id,
        disabled_output_sha256=disabled_result.output_sha256,
        second_pass_output_sha256=second_pass_result.output_sha256,
        selected_output_sha256=(
            disabled_result.output_sha256
            if blocked
            else second_pass_result.output_sha256
        ),
        rollback_applied=blocked,
        questions_unchanged=questions_unchanged,
        acceptance_output_unchanged=acceptance_output_unchanged,
        provider_fused_evidence_ids=tuple(sorted(fused_ids)),
        provider_consumed_evidence_ids=tuple(sorted(consumed_ids)),
        changed_hypothesis_ids=tuple(
            sorted(row.hypothesis_id for row in changed_hypotheses)
        ),
        changed_disposition_ids=tuple(
            sorted(row.disposition_id for row in changed_dispositions)
        ),
        added_open_question_ids=tuple(sorted(added_open_ids)),
        removed_open_question_ids=tuple(sorted(removed_open_ids)),
        section_deltas=tuple(section_deltas),
        influence_lineages=tuple(lineages),
        blocking_reason_codes=blocking_reasons,
    )


def select_controlled_second_pass_result(
    *,
    disabled_result: GenerationResult,
    second_pass_result: GenerationResult,
    disabled_question_trace: QuestionRetrievalTraceBundle | None,
    second_pass_question_trace: QuestionRetrievalTraceBundle | None,
    fluffyjaws_trace: FluffyJawsShadowRunTrace | None,
) -> tuple[GenerationResult, SecondPassInfluenceDecision]:
    """Return SECOND_PASS only after the paired audit passes; otherwise rollback."""

    try:
        decision = audit_second_pass_influence(
            disabled_result=disabled_result,
            second_pass_result=second_pass_result,
            disabled_question_trace=disabled_question_trace,
            second_pass_question_trace=second_pass_question_trace,
            fluffyjaws_trace=fluffyjaws_trace,
        )
    except Exception:
        # The influence audit consumes attacker/provider-adjacent structured
        # projections.  A malformed projection is a rollout rejection, not a
        # reason to make the canonical disabled result unavailable.  Do not
        # retain exception text because it may contain provider content.
        decision = SecondPassInfluenceDecision(
            status=SecondPassInfluenceStatus.BLOCKED,
            request_id=second_pass_result.request_id,
            disabled_run_id=disabled_result.run_id,
            second_pass_run_id=second_pass_result.run_id,
            disabled_output_sha256=disabled_result.output_sha256,
            second_pass_output_sha256=second_pass_result.output_sha256,
            selected_output_sha256=disabled_result.output_sha256,
            rollback_applied=True,
            questions_unchanged=False,
            acceptance_output_unchanged=False,
            blocking_reason_codes=(SecondPassInfluenceReason.AUDIT_INPUT_INVALID,),
        )
    selected = (
        disabled_result
        if decision.status == SecondPassInfluenceStatus.BLOCKED
        else second_pass_result
    )
    _LAST_SECOND_PASS_INFLUENCE_DECISION.set(decision.model_copy(deep=True))
    return selected, decision


__all__ = [
    "SECOND_PASS_INFLUENCE_SCHEMA",
    "SecondPassInfluenceDecision",
    "SecondPassInfluenceLineage",
    "SecondPassInfluenceReason",
    "SecondPassInfluenceStatus",
    "SecondPassSectionDelta",
    "audit_second_pass_influence",
    "get_last_second_pass_influence_decision",
    "select_controlled_second_pass_result",
]
