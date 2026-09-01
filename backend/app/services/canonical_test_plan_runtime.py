"""The one stage-owned runtime for AEM Guides Test Plan generation.

Entry points may normalize inputs and project outputs, but they cannot inject a
composer, reorder stages, select a gate, or bypass typed intermediate records.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable, Literal, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.schemas_canonical_test_plan_runtime import (
    CANONICAL_RUNTIME_ID,
    CANONICAL_RUNTIME_VERSION,
    CANONICAL_STAGE_ORDER,
    AcceptanceCandidate,
    AcceptanceResolutionBatch,
    AcceptancePromotionDecision,
    BehaviorHypothesis,
    CanonicalBehaviorModel,
    CanonicalEvidenceBundle,
    CanonicalRuntimeStage,
    CandidateLifecycleRecord,
    ClaudeMissingQuestionSubmission,
    CompatibilityProjectionLink,
    CoverageDisposition,
    CoverageDispositionRecord,
    DirectedRetrievalRecord,
    EvidenceLifecycleStatus,
    EvidenceSourceType,
    EvidenceUsageTrace,
    GateDecision,
    GateStatus,
    GenerationProfile,
    GenerationRequest,
    GenerationResult,
    GitHubImplementationVerificationHandoff,
    GitHubImplementationVerificationResult,
    HypothesisState,
    InvestigationFamilySatisfactionStatus,
    MissingQuestion,
    MissingQuestionQualityReport,
    MissingQuestionResolutionRecord,
    PipelineCompatibilityOptions,
    PromotionStatus,
    QeInvestigationPreparation,
    QuestionGenerationDiagnosticTrace,
    RuntimeEntryPoint,
    RuntimePrincipal,
    RuntimeStageTrace,
    RuntimeTrace,
    StructuredQEPlan,
    stable_sha256,
)
from app.services.canonical_evidence_service import (
    apply_usage_lifecycle,
    assert_generation_safe,
    build_legacy_compatibility_projection,
    merge_bundles,
    mark_evidence_used,
    normalize_benchmark_public_input,
    normalize_codex_manifest,
    normalize_legacy_packet,
    redacted_trace_payload,
    visible_bundle,
)
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE,
    CanonicalTestPlanReasoningService,
)
from app.services.canonical_qe_investigation_service import (
    CanonicalQeInvestigationService,
    PatternResolver,
)
from app.services.canonical_missing_question_service import (
    CANONICAL_MISSING_QUESTION_SERVICE,
    CanonicalMissingQuestionService,
)
from app.services.github_implementation_verification import (
    GITHUB_IMPLEMENTATION_VERIFICATION_SERVICE,
    GitHubImplementationVerificationService,
)
from app.services.fluffyjaws_second_pass_influence import (
    SecondPassInfluenceDecision,
    select_controlled_second_pass_result,
)
from app.services.reasoning_evidence_shadow_service import (
    FluffyJawsRuntimeMode,
    FluffyJawsShadowConfig,
    ReasoningEvidenceSemanticBatch,
    ReasoningEvidenceShadowService,
    clear_last_fluffyjaws_shadow_trace,
    get_last_fluffyjaws_shadow_trace,
    record_semantic_usage_trace,
)
from app.services.reasoning_evidence_observability import (
    QuestionRetrievalTraceBundle,
    TraceCompletionState,
    clear_last_question_retrieval_trace,
    get_last_question_retrieval_trace,
    record_question_retrieval_trace,
)
from app.services.qe_miss_diagnostic_service import (
    clear_last_qe_miss_debug_snapshot,
    record_qe_miss_debug_snapshot,
)


logger = logging.getLogger(__name__)
_LAST_RUNTIME_TRACE: ContextVar[RuntimeTrace | None] = ContextVar(
    "aem_guides_last_test_plan_runtime_trace", default=None
)
T = TypeVar("T")


class HypothesisVerificationSemanticBatch(BaseModel):
    """Provider-neutral semantic output owned and hashed by runtime stage 11."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["aem-guides-hypothesis-verification-semantic-batch-v1"] = (
        "aem-guides-hypothesis-verification-semantic-batch-v1"
    )
    hypotheses: list[BehaviorHypothesis]
    behavior_model: CanonicalBehaviorModel
    evidence_bundle: CanonicalEvidenceBundle
    consumed_evidence_ids: list[str]
    implementation_handoffs: list[GitHubImplementationVerificationHandoff] = Field(
        default_factory=list
    )
    implementation_results: list[GitHubImplementationVerificationResult] = Field(
        default_factory=list
    )
    implementation_result_evidence_ids: list[str] = Field(default_factory=list)
    unresolved_implementation_handoff_ids: list[str] = Field(default_factory=list)
    rejected_implementation_result_evidence_ids: list[str] = Field(default_factory=list)

    @field_validator(
        "consumed_evidence_ids",
        "implementation_result_evidence_ids",
        "unresolved_implementation_handoff_ids",
        "rejected_implementation_result_evidence_ids",
    )
    @classmethod
    def normalize_consumed_ids(cls, values: list[str]) -> list[str]:
        return sorted({str(value).strip() for value in values if str(value).strip()})

    @model_validator(mode="after")
    def validate_consumption(self) -> "HypothesisVerificationSemanticBatch":
        records = {row.evidence_id: row for row in self.evidence_bundle.records}
        cited = {
            evidence_id
            for hypothesis in self.hypotheses
            for evidence_id in (
                list(hypothesis.supporting_evidence_ids)
                + list(hypothesis.contradicting_evidence_ids)
                + list(hypothesis.verification_evidence_ids)
            )
        }
        if any(
            evidence_id not in records
            or not records[evidence_id].used
            or evidence_id not in cited
            for evidence_id in self.consumed_evidence_ids
        ):
            raise ValueError("consumed evidence must be cited and marked used")
        if not set(self.implementation_result_evidence_ids).issubset(cited):
            raise ValueError("implementation result evidence must be cited")
        handoff_ids = {row.handoff_id for row in self.implementation_handoffs}
        if not set(self.unresolved_implementation_handoff_ids).issubset(handoff_ids):
            raise ValueError("unresolved implementation handoff must exist in batch")
        result_ids = {row.result_id for row in self.implementation_results}
        if len(result_ids) != len(self.implementation_results):
            raise ValueError("implementation results must be unique")
        return self

    def semantic_projection(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "hypotheses": [row.model_dump(mode="json") for row in self.hypotheses],
            "behavior_model": self.behavior_model.model_dump(mode="json"),
            "evidence_bundle_id": self.evidence_bundle.bundle_id,
            "consumed_evidence_ids": self.consumed_evidence_ids,
            "implementation_handoffs": [
                row.model_dump(mode="json", by_alias=True)
                for row in self.implementation_handoffs
            ],
            "implementation_results": [
                row.model_dump(mode="json", by_alias=True)
                for row in self.implementation_results
            ],
            "implementation_result_evidence_ids": (
                self.implementation_result_evidence_ids
            ),
            "unresolved_implementation_handoff_ids": (
                self.unresolved_implementation_handoff_ids
            ),
            "rejected_implementation_result_evidence_ids": (
                self.rejected_implementation_result_evidence_ids
            ),
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hashable(value: Any) -> Any:
    if isinstance(value, ReasoningEvidenceSemanticBatch):
        return value.semantic_projection()
    if isinstance(value, HypothesisVerificationSemanticBatch):
        return value.semantic_projection()
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, dict):
        return {str(key): _hashable(child) for key, child in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_hashable(child) for child in value]
    return value


def _item_count(value: Any) -> int:
    if isinstance(value, ReasoningEvidenceSemanticBatch):
        return len(value.retrievals)
    if isinstance(value, HypothesisVerificationSemanticBatch):
        return len(value.hypotheses)
    if isinstance(value, BaseModel):
        for field in ("facts", "nodes", "edges", "sections", "accepted_questions"):
            child = getattr(value, field, None)
            if isinstance(child, list):
                return len(child)
        return 1
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    return 1 if value is not None else 0


def _roles_from_user(user: Any | None) -> list[str]:
    if user is None:
        return ["system"]
    roles = [str(role) for role in getattr(user, "roles", []) if str(role).strip()]
    if getattr(user, "is_admin", False):
        roles.append("admin")
    return roles or ["authenticated"]


class CanonicalTestPlanRuntime:
    """Own and execute the fixed canonical reasoning sequence."""

    runtime_id = CANONICAL_RUNTIME_ID
    runtime_version = CANONICAL_RUNTIME_VERSION
    stage_order = CANONICAL_STAGE_ORDER

    def __init__(
        self,
        *,
        shadow_service: ReasoningEvidenceShadowService | None = None,
        github_verification_service: (
            GitHubImplementationVerificationService | None
        ) = None,
        pattern_resolver: PatternResolver | None = None,
    ) -> None:
        self._reasoning: CanonicalTestPlanReasoningService = CANONICAL_REASONING_SERVICE
        self._shadow_service = shadow_service or ReasoningEvidenceShadowService()
        self._github_verification = (
            github_verification_service or GITHUB_IMPLEMENTATION_VERIFICATION_SERVICE
        )
        self._qe_investigation = CanonicalQeInvestigationService(pattern_resolver)
        self._missing_questions: CanonicalMissingQuestionService = (
            CANONICAL_MISSING_QUESTION_SERVICE
        )

    def build_request(
        self,
        *,
        jira_key: str,
        tenant_id: str,
        entry_point: RuntimeEntryPoint | str,
        generation_profile: GenerationProfile | str,
        user: Any | None = None,
        lifecycle_stage: str = "unknown",
        options: dict[str, Any] | None = None,
        benchmark_version: str = "",
        benchmark_split: str = "",
        benchmark_record_id: str = "",
    ) -> GenerationRequest:
        safe_options = redacted_trace_payload(options or {})
        assert_generation_safe(safe_options)
        option_fields = set(PipelineCompatibilityOptions.model_fields)
        safe_options = {
            key: value for key, value in safe_options.items() if key in option_fields
        }
        tenant = str(tenant_id).strip()
        principal = RuntimePrincipal(
            principal_id=str(getattr(user, "id", None) or "system"),
            tenant_id=tenant,
            roles=_roles_from_user(user),
        )
        return GenerationRequest(
            jira_key=jira_key,
            tenant_id=tenant,
            entry_point=entry_point,
            generation_profile=generation_profile,
            lifecycle_stage=lifecycle_stage,  # type: ignore[arg-type]
            principal=principal,
            benchmark_version=benchmark_version,
            benchmark_split=benchmark_split,  # type: ignore[arg-type]
            benchmark_record_id=benchmark_record_id,
            allowed_sources=list(EvidenceSourceType),
            retrieval_budget={
                "evidence_k": int(safe_options.get("evidence_k", 8)),
                "max_repo_matches": int(safe_options.get("max_repo_matches", 30)),
                "graph_max_paths": int(safe_options.get("graph_max_paths", 20)),
            },
            feature_flags={
                key: bool(safe_options.get(key, default))
                for key, default in {
                    "include_repository_evidence": True,
                    "include_evidence_graph": True,
                    "include_uac_intelligence": True,
                    "compose_draft_plan": True,
                }.items()
            },
            runtime_context={"contract_owner": CANONICAL_RUNTIME_ID},
            options=safe_options,
        )

    def normalize_packet(
        self, packet: dict[str, Any], *, request: GenerationRequest
    ) -> CanonicalEvidenceBundle:
        return visible_bundle(
            normalize_legacy_packet(packet, tenant_id=request.tenant_id),
            request.principal,
        )

    def normalize_benchmark_input(
        self,
        row: dict[str, Any],
        *,
        request: GenerationRequest,
        source_path: str = "",
    ) -> CanonicalEvidenceBundle:
        if request.entry_point != RuntimeEntryPoint.BENCHMARK_V2:
            raise ValueError("benchmark inputs require the Benchmark V2 entry point")
        return visible_bundle(
            normalize_benchmark_public_input(
                row,
                tenant_id=request.tenant_id,
                split=request.benchmark_split,
                source_path=source_path,
            ),
            request.principal,
        )

    def _trace(
        self,
        *,
        run_id: str,
        request: GenerationRequest,
        evidence: CanonicalEvidenceBundle,
        started_at: str,
        stage_trace: list[RuntimeStageTrace],
        compatibility_adapter: str,
        deprecated_path: bool,
        warnings: list[str],
        compatibility_projection: list[CompatibilityProjectionLink],
        facts: Any = None,
        model: Any = None,
        closure: list[Any] | None = None,
        retrievals: list[Any] | None = None,
        hypotheses: list[Any] | None = None,
        implementation_handoffs: list[GitHubImplementationVerificationHandoff]
        | None = None,
        implementation_results: list[GitHubImplementationVerificationResult]
        | None = None,
        unresolved_implementation_handoff_ids: list[str] | None = None,
        candidates: list[Any] | None = None,
        candidate_resolution: AcceptanceResolutionBatch | None = None,
        candidate_lifecycle: list[CandidateLifecycleRecord] | None = None,
        structured_plan: StructuredQEPlan | None = None,
        dispositions: list[Any] | None = None,
        promotions: list[AcceptancePromotionDecision] | None = None,
        gates: list[GateDecision] | None = None,
        question_generation_trace: QuestionGenerationDiagnosticTrace | None = None,
        qe_investigation: QeInvestigationPreparation | None = None,
        missing_question_quality: MissingQuestionQualityReport | None = None,
        missing_question_resolutions: list[MissingQuestionResolutionRecord]
        | None = None,
    ) -> RuntimeTrace:
        closure = closure or []
        retrievals = retrievals or []
        hypotheses = hypotheses or []
        implementation_handoffs = implementation_handoffs or []
        implementation_results = implementation_results or []
        unresolved_implementation_handoff_ids = (
            unresolved_implementation_handoff_ids or []
        )
        candidates = candidates or []
        candidate_lifecycle = candidate_lifecycle or []
        dispositions = dispositions or []
        promotions = promotions or []
        gates = gates or []
        return RuntimeTrace(
            run_id=run_id,
            request_id=request.request_id,
            entry_point=request.entry_point,
            generation_profile=request.generation_profile,
            evidence_bundle_id=evidence.bundle_id,
            started_at=started_at,
            completed_at=_utc_now(),
            stage_trace=stage_trace,
            consumed_evidence_ids=[
                row.evidence_id
                for row in evidence.records
                if row.lifecycle_status == EvidenceLifecycleStatus.USED
            ],
            evidence_usage_trace=[
                EvidenceUsageTrace(
                    evidence_id=row.evidence_id,
                    lifecycle_status=row.lifecycle_status,
                    inspected=row.inspected,
                    used=row.used,
                    rejected_reason=row.rejected_reason,
                )
                for row in evidence.records
            ],
            question_generation_trace=question_generation_trace,
            qe_investigation=qe_investigation,
            missing_question_quality=missing_question_quality,
            missing_question_resolutions=missing_question_resolutions or [],
            source_counts=evidence.source_counts,
            compatibility_projection=compatibility_projection,
            compatibility_adapter=compatibility_adapter,
            deprecated_path=deprecated_path,
            quality_gate=", ".join(
                f"{gate.gate.value}:{gate.status.value}" for gate in gates
            ),
            warnings=warnings,
            authoritative_facts_extracted=(
                list(getattr(facts, "authoritative_fact_ids", [])) if facts else []
            ),
            authoritative_facts_preserved=(
                [
                    fact.fact_id
                    for fact in getattr(facts, "facts", [])
                    if fact.authoritative and fact.preservation_state.value != "LOST"
                ]
                if facts
                else []
            ),
            primary_entities=list(getattr(model, "primary_entities", []))
            if model
            else [],
            graph_nodes_visited=[row.node_id for row in model.graph.nodes]
            if model
            else [],
            edges_visited=[row.edge_id for row in model.graph.edges] if model else [],
            edges_rejected=(
                [
                    row.edge_id
                    for row in model.graph.edges
                    if row.verification_state == HypothesisState.REJECTED
                ]
                if model
                else []
            ),
            semantic_dimensions_considered=sorted(
                {row.dimension.value for row in closure}
            ),
            second_pass_retrievals=[row.retrieval_id for row in retrievals],
            implementation_verification_handoff_ids=[
                row.handoff_id for row in implementation_handoffs
            ],
            implementation_verification_result_ids=[
                row.result_id for row in implementation_results
            ],
            unresolved_implementation_handoff_ids=(
                unresolved_implementation_handoff_ids
            ),
            hypotheses_confirmed=[
                row.hypothesis_id
                for row in hypotheses
                if row.state == HypothesisState.CONFIRMED
            ],
            hypotheses_rejected=[
                row.hypothesis_id
                for row in hypotheses
                if row.state == HypothesisState.REJECTED
            ],
            hypotheses_unresolved=[
                row.hypothesis_id
                for row in hypotheses
                if row.state == HypothesisState.UNRESOLVED
            ],
            ac_candidates=[row.candidate_id for row in candidates],
            candidate_lifecycle_ids=[
                row.lifecycle_id for row in candidate_lifecycle
            ],
            candidate_dedup_decision_ids=(
                [row.decision_id for row in candidate_resolution.dedup_decisions]
                if candidate_resolution is not None
                else []
            ),
            renderer_projection_ids=(
                [row.projection_id for row in structured_plan.renderer_decisions]
                if structured_plan is not None
                else []
            ),
            regression_candidates=[
                row.disposition_id
                for row in dispositions
                if row.disposition
                not in {
                    CoverageDisposition.ACCEPTANCE_CONTRACT,
                    CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
                    CoverageDisposition.OPEN_QUESTION,
                }
            ],
            promotion_rejections=[
                row.candidate_id
                for row in promotions
                if row.status in {PromotionStatus.REJECTED, PromotionStatus.BLOCKED}
            ],
            gate_failures=[failure for gate in gates for failure in gate.failures],
        )

    def run(
        self,
        request: GenerationRequest,
        evidence: CanonicalEvidenceBundle,
        *,
        claude_question_submission: ClaudeMissingQuestionSubmission | None = None,
        compatibility_adapter: str = "",
        deprecated_path: bool = False,
        warnings: list[str] | None = None,
        compatibility_projection: list[CompatibilityProjectionLink] | None = None,
    ) -> GenerationResult:
        """Execute once, or pair and qualify an enabled SECOND_PASS run."""

        clear_last_qe_miss_debug_snapshot()
        if self._shadow_service.mode != (FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS):
            result = self._run_once(
                request,
                evidence,
                claude_question_submission=claude_question_submission,
                compatibility_adapter=compatibility_adapter,
                deprecated_path=deprecated_path,
                warnings=warnings,
                compatibility_projection=compatibility_projection,
            )
            self._record_qe_miss_snapshot_safely(
                result,
                get_last_question_retrieval_trace(),
            )
            return result
        selected, _decision = self.run_controlled_second_pass(
            request,
            evidence,
            claude_question_submission=claude_question_submission,
            compatibility_adapter=compatibility_adapter,
            deprecated_path=deprecated_path,
            warnings=warnings,
            compatibility_projection=compatibility_projection,
        )
        return selected

    @staticmethod
    def _record_qe_miss_snapshot_safely(
        result: GenerationResult,
        question_trace: QuestionRetrievalTraceBundle | None,
    ) -> None:
        """Keep diagnostic infrastructure from affecting generation output."""

        try:
            record_qe_miss_debug_snapshot(
                result=result,
                question_trace=question_trace,
            )
        except Exception:
            # Do not expose source content or exception text in logs.  The
            # canonical plan remains available when diagnostics are not.
            logger.warning(
                "QE miss diagnostic snapshot unavailable",
                extra={"run_id": result.run_id},
            )

    def run_controlled_second_pass(
        self,
        request: GenerationRequest,
        evidence: CanonicalEvidenceBundle,
        *,
        claude_question_submission: ClaudeMissingQuestionSubmission | None = None,
        compatibility_adapter: str = "",
        deprecated_path: bool = False,
        warnings: list[str] | None = None,
        compatibility_projection: list[CompatibilityProjectionLink] | None = None,
    ) -> tuple[GenerationResult, SecondPassInfluenceDecision]:
        """Pair DISABLED and SECOND_PASS, selecting DISABLED on any audit gap."""

        if self._shadow_service.mode != (FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS):
            raise ValueError(
                "controlled second pass requires FLUFFYJAWS_SECOND_PASS mode"
            )
        clear_last_qe_miss_debug_snapshot()
        disabled_runtime = CanonicalTestPlanRuntime(
            shadow_service=ReasoningEvidenceShadowService(
                config=FluffyJawsShadowConfig(
                    mode=FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED
                )
            ),
            github_verification_service=self._github_verification,
            pattern_resolver=self._qe_investigation.resolver,
        )
        run_kwargs = {
            "claude_question_submission": claude_question_submission,
            "compatibility_adapter": compatibility_adapter,
            "deprecated_path": deprecated_path,
            "warnings": warnings,
            "compatibility_projection": compatibility_projection,
        }
        disabled_result = disabled_runtime._run_once(
            request,
            evidence,
            **run_kwargs,
        )
        disabled_question_trace = get_last_question_retrieval_trace()
        second_pass_result = self._run_once(
            request,
            evidence,
            **run_kwargs,
        )
        second_pass_question_trace = get_last_question_retrieval_trace()
        fluffyjaws_trace = get_last_fluffyjaws_shadow_trace()
        selected, decision = select_controlled_second_pass_result(
            disabled_result=disabled_result,
            second_pass_result=second_pass_result,
            disabled_question_trace=disabled_question_trace,
            second_pass_question_trace=second_pass_question_trace,
            fluffyjaws_trace=fluffyjaws_trace,
        )
        selected_question_trace = (
            disabled_question_trace
            if selected.run_id == disabled_result.run_id
            else second_pass_question_trace
        )
        self._record_qe_miss_snapshot_safely(selected, selected_question_trace)
        return selected, decision

    def _run_once(
        self,
        request: GenerationRequest,
        evidence: CanonicalEvidenceBundle,
        *,
        claude_question_submission: ClaudeMissingQuestionSubmission | None = None,
        compatibility_adapter: str = "",
        deprecated_path: bool = False,
        warnings: list[str] | None = None,
        compatibility_projection: list[CompatibilityProjectionLink] | None = None,
    ) -> GenerationResult:
        """Execute one canonical pass.  Callers use :meth:`run`."""

        clear_last_fluffyjaws_shadow_trace()
        clear_last_question_retrieval_trace()
        if evidence.tenant_id != request.tenant_id:
            raise ValueError("generation request and evidence bundle tenant differ")
        if not evidence.records:
            raise ValueError(
                "canonical generation requires at least one evidence record"
            )
        visible = visible_bundle(evidence, request.principal)
        allowed = set(request.allowed_sources)
        disallowed = sorted(
            {
                row.source_type.value
                for row in visible.records
                if allowed and row.source_type not in allowed
            }
        )
        if disallowed:
            raise ValueError(
                f"evidence bundle contains disallowed sources: {disallowed}"
            )
        visible = apply_usage_lifecycle(
            visible,
            used_source_types=set(EvidenceSourceType),
            entered_evidence_ids=[row.evidence_id for row in visible.records],
            rejection_reason="The canonical runtime did not consume this evidence record.",
        )
        runtime_evidence = visible
        run_id = f"run:{uuid4()}"
        run_started = _utc_now()
        stage_trace: list[RuntimeStageTrace] = []
        runtime_warnings = list(warnings or [])
        questions_for_trace: list[MissingQuestion] = []
        local_retrievals_for_trace: list[DirectedRetrievalRecord] = []
        hypotheses_for_trace: list[BehaviorHypothesis] = []
        implementation_handoffs_for_trace: list[
            GitHubImplementationVerificationHandoff
        ] = []
        implementation_results_for_trace: list[
            GitHubImplementationVerificationResult
        ] = []
        unresolved_implementation_handoff_ids_for_trace: list[str] = []
        dispositions_for_trace: list[CoverageDispositionRecord] = []
        candidates_for_trace: list[AcceptanceCandidate] = []
        promotions_for_trace: list[AcceptancePromotionDecision] = []
        structured_plan_for_trace: StructuredQEPlan | None = None

        def capture_question_trace(
            *,
            output_sha256: str = "",
            completion_state: TraceCompletionState,
            failed_stage: CanonicalRuntimeStage | str | None = None,
        ) -> bool:
            """Record diagnostics without making generation depend on observability."""

            try:
                record_question_retrieval_trace(
                    run_id=run_id,
                    request=request,
                    output_sha256=output_sha256,
                    completion_state=completion_state,
                    failed_stage=failed_stage,
                    questions=questions_for_trace,
                    local_retrievals=local_retrievals_for_trace,
                    hypotheses=hypotheses_for_trace,
                    implementation_handoffs=implementation_handoffs_for_trace,
                    implementation_results=implementation_results_for_trace,
                    unresolved_implementation_handoff_ids=(
                        unresolved_implementation_handoff_ids_for_trace
                    ),
                    dispositions=dispositions_for_trace,
                    candidates=candidates_for_trace,
                    promotions=promotions_for_trace,
                    structured_plan=structured_plan_for_trace,
                    evidence_records=runtime_evidence.records,
                    fluffyjaws_mode=self._shadow_service.mode,
                    fluffyjaws_trace=get_last_fluffyjaws_shadow_trace(),
                )
                return True
            except Exception:
                warning = "QUESTION_RETRIEVAL_TRACE_RECORD_FAILED"
                if warning not in runtime_warnings:
                    runtime_warnings.append(warning)
                return False

        def stage(
            stage_name: CanonicalRuntimeStage,
            input_value: Any,
            operation: Callable[[], T],
        ) -> T:
            expected = CANONICAL_STAGE_ORDER[len(stage_trace)]
            if stage_name != expected:
                raise RuntimeError(
                    f"canonical stage order violation: expected {expected.value}, got {stage_name.value}"
                )
            started_at = _utc_now()
            start = perf_counter()
            input_hash = stable_sha256(_hashable(input_value))
            try:
                output = operation()
            except Exception as exc:
                stage_trace.append(
                    RuntimeStageTrace(
                        stage=stage_name,
                        sequence=len(stage_trace) + 1,
                        started_at=started_at,
                        completed_at=_utc_now(),
                        duration_ms=(perf_counter() - start) * 1000,
                        input_sha256=input_hash,
                        output_sha256=stable_sha256({"error": type(exc).__name__}),
                        status="failed",
                        warnings=[type(exc).__name__],
                    )
                )
                partial = self._trace(
                    run_id=run_id,
                    request=request,
                    evidence=runtime_evidence,
                    started_at=run_started,
                    stage_trace=stage_trace,
                    compatibility_adapter=compatibility_adapter,
                    deprecated_path=deprecated_path,
                    warnings=runtime_warnings
                    + [f"{stage_name.value} failed: {type(exc).__name__}"],
                    compatibility_projection=list(compatibility_projection or []),
                )
                _LAST_RUNTIME_TRACE.set(partial)
                capture_question_trace(
                    completion_state=TraceCompletionState.PARTIAL,
                    failed_stage=stage_name.value,
                )
                raise
            stage_trace.append(
                RuntimeStageTrace(
                    stage=stage_name,
                    sequence=len(stage_trace) + 1,
                    started_at=started_at,
                    completed_at=_utc_now(),
                    duration_ms=(perf_counter() - start) * 1000,
                    input_sha256=input_hash,
                    output_sha256=stable_sha256(_hashable(output)),
                    status="completed",
                    item_count=_item_count(output),
                )
            )
            return output

        facts = stage(
            CanonicalRuntimeStage.CONTRACT_FACT_EXTRACTOR,
            visible,
            lambda: self._reasoning.extract_contract_facts(visible),
        )
        contract_gate = stage(
            CanonicalRuntimeStage.CONTRACT_INTEGRITY_GATE,
            facts,
            lambda: self._reasoning.contract_integrity_gate(facts),
        )
        if contract_gate.status == GateStatus.FAILED:
            trace = self._trace(
                run_id=run_id,
                request=request,
                evidence=visible,
                started_at=run_started,
                stage_trace=stage_trace,
                compatibility_adapter=compatibility_adapter,
                deprecated_path=deprecated_path,
                warnings=runtime_warnings,
                compatibility_projection=list(compatibility_projection or []),
                facts=facts,
                gates=[contract_gate],
            )
            _LAST_RUNTIME_TRACE.set(trace)
            payload = {
                "jira_key": request.jira_key,
                "contract_facts": facts.model_dump(mode="json"),
                "gate_decisions": [contract_gate.model_dump(mode="json")],
            }
            result = GenerationResult(
                run_id=run_id,
                request_id=request.request_id,
                evidence_bundle_id=visible.bundle_id,
                evidence_bundle=visible,
                status="blocked",
                output_contract=request.output_contract,
                output_kind="test_plan",
                output_payload=payload,
                structured_output=payload,
                gate_decisions=[contract_gate],
                validation_status="failed",
                validation_result={
                    "status": "failed",
                    "gate": contract_gate.gate.value,
                },
                runtime_warnings=runtime_warnings,
                metrics={"evidence_record_count": len(visible.records)},
                trace=trace,
            )
            capture_question_trace(
                output_sha256=result.output_sha256,
                completion_state=TraceCompletionState.COMPLETE,
            )
            if runtime_warnings != result.runtime_warnings:
                result.runtime_warnings = list(runtime_warnings)
            return result
        domains = stage(
            CanonicalRuntimeStage.ISSUE_DOMAIN_ROUTER,
            [visible, facts],
            lambda: self._reasoning.route_domains(visible, facts),
        )
        scope = stage(
            CanonicalRuntimeStage.SCOPE_RESOLVER,
            [facts, domains],
            lambda: self._reasoning.resolve_scope(facts, domains),
        )
        surfaces = stage(
            CanonicalRuntimeStage.CHANGE_SURFACE_EXTRACTOR,
            [visible, facts],
            lambda: self._reasoning.extract_change_surfaces(visible, facts),
        )
        abstract_signals = self._reasoning.extract_abstract_signals(surfaces)
        reasoning_pattern_activations = self._reasoning.route_reasoning_patterns(
            abstract_signals
        )
        pattern_lookup = self._qe_investigation.lookup_patterns(
            facts=facts,
            scope=scope,
            domains=domains,
            surfaces=surfaces,
            signals=abstract_signals,
        )
        for warning_code in pattern_lookup.warning_codes:
            if warning_code not in runtime_warnings:
                runtime_warnings.append(warning_code)
        graph = stage(
            CanonicalRuntimeStage.EVIDENCE_BACKED_BEHAVIOR_GRAPH_BUILDER,
            [visible, facts, surfaces],
            lambda: self._reasoning.build_behavior_graph(visible, facts, surfaces),
        )
        model = stage(
            CanonicalRuntimeStage.BEHAVIOR_MODEL_BUILDER,
            [domains, scope, surfaces, graph, facts],
            lambda: self._reasoning.build_behavior_model(
                domains, scope, surfaces, graph, facts
            ),
        )
        investigation = self._qe_investigation.prepare_qe_investigation(
            request=request,
            facts=facts,
            scope=scope,
            domains=domains,
            surfaces=surfaces,
            signals=abstract_signals,
            activations=reasoning_pattern_activations,
            deterministic_dimensions=self._reasoning.applicable_semantic_dimensions(
                visible, model
            ),
            pattern_lookup=pattern_lookup,
        )
        closure = stage(
            CanonicalRuntimeStage.SEMANTIC_BEHAVIORAL_CLOSURE_EXPLORER,
            [
                visible,
                model,
                abstract_signals,
                reasoning_pattern_activations,
                investigation.mandatory_families,
            ],
            lambda: self._reasoning.explore_semantic_closure(
                visible,
                model,
                abstract_signals,
                reasoning_pattern_activations,
                investigation.mandatory_families,
            ),
        )
        investigation_payload = investigation.model_dump(
            mode="json", exclude={"preparation_id"}
        )
        investigation_payload["already_investigated_dimensions"] = sorted(
            {
                row.dimension.value
                for row in closure
                if row.disposition.value in {"COVERED", "INVESTIGATED_AND_REJECTED"}
            }
        )
        investigation = QeInvestigationPreparation.model_validate(investigation_payload)

        def select_missing_questions() -> MissingQuestionQualityReport:
            compatibility_questions = (
                self._reasoning.generate_missing_questions(
                    closure,
                    scope,
                    facts,
                    investigation,
                )
                if claude_question_submission is None
                else []
            )
            return self._missing_questions.select_questions(
                preparation=investigation,
                closure=closure,
                compatibility_questions=compatibility_questions,
                claude_submission=claude_question_submission,
                expected_request_id=request.request_id,
            )

        missing_question_quality = stage(
            CanonicalRuntimeStage.MISSING_QUESTION_GENERATOR,
            [
                closure,
                scope,
                facts,
                investigation,
                claude_question_submission,
            ],
            select_missing_questions,
        )
        questions = list(missing_question_quality.accepted_questions)
        question_generation_trace = self._reasoning.build_question_generation_trace(
            bundle=visible,
            facts=facts,
            surfaces=surfaces,
            signals=abstract_signals,
            activations=reasoning_pattern_activations,
            closure=closure,
            questions=questions,
            investigation=investigation,
        )
        questions_for_trace = list(questions)

        def retrieve_with_optional_second_pass() -> (
            list[DirectedRetrievalRecord] | ReasoningEvidenceSemanticBatch
        ):
            nonlocal local_retrievals_for_trace
            local_retrievals = self._reasoning.retrieve_for_questions(
                visible, questions
            )
            local_retrievals_for_trace = list(local_retrievals)
            try:
                second_pass = self._shadow_service.retrieve(
                    run_id=run_id,
                    request=request,
                    evidence=visible,
                    domains=domains,
                    scope=scope,
                    questions=questions,
                    local_retrievals=local_retrievals,
                )
                if second_pass.semantic_evidence:
                    return second_pass.to_semantic_batch(
                        local_evidence_bundle_id=visible.bundle_id,
                        local_retrievals=local_retrievals,
                    )
                return second_pass.retrievals
            except Exception:
                # Optional provider retrieval fails open for plan availability
                # and closed for semantic influence.
                # Any already-recorded redacted provider trace is retained for
                # diagnosis; it is never a semantic input.
                return local_retrievals

        retrieval_stage_output = stage(
            CanonicalRuntimeStage.REASONING_DIRECTED_RETRIEVER,
            [visible, questions],
            retrieve_with_optional_second_pass,
        )
        semantic_batch = (
            retrieval_stage_output
            if isinstance(retrieval_stage_output, ReasoningEvidenceSemanticBatch)
            else None
        )
        if semantic_batch is None:
            retrievals = retrieval_stage_output
        else:
            runtime_evidence = semantic_batch.evidence_bundle
            retrievals = semantic_batch.retrievals
        pre_verifier_model = model

        def verify_with_optional_second_pass():
            provisional_hypotheses, enriched_model = self._reasoning.verify_hypotheses(
                runtime_evidence,
                questions,
                retrievals,
                model,
                scope=scope,
                request=request if semantic_batch is not None else None,
                semantic_evidence=(
                    semantic_batch.semantic_evidence
                    if semantic_batch is not None
                    else None
                ),
                local_evidence_ids=(
                    {
                        evidence_id
                        for retrieval in semantic_batch.local_retrievals
                        for evidence_id in retrieval.matched_evidence_ids
                    }
                    if semantic_batch is not None
                    else None
                ),
            )
            implementation_handoffs = self._github_verification.create_handoffs(
                request=request,
                scope=scope,
                surfaces=surfaces,
                evidence=runtime_evidence,
                questions=questions,
                hypotheses=provisional_hypotheses,
            )
            implementation_batch = self._github_verification.apply_results(
                scope=scope,
                evidence=runtime_evidence,
                handoffs=implementation_handoffs,
                hypotheses=provisional_hypotheses,
            )
            provider_ids = (
                {
                    row.authorization.source_attestation.binding.evidence_id
                    for row in semantic_batch.semantic_evidence
                }
                if semantic_batch is not None
                else set()
            )
            cited_ids = {
                evidence_id
                for hypothesis in implementation_batch.hypotheses
                for evidence_id in (
                    list(hypothesis.supporting_evidence_ids)
                    + list(hypothesis.contradicting_evidence_ids)
                )
                if evidence_id in provider_ids
            }
            finalized_evidence = mark_evidence_used(runtime_evidence, cited_ids)
            return HypothesisVerificationSemanticBatch(
                hypotheses=implementation_batch.hypotheses,
                behavior_model=enriched_model,
                evidence_bundle=finalized_evidence,
                consumed_evidence_ids=sorted(cited_ids),
                implementation_handoffs=implementation_handoffs,
                implementation_results=implementation_batch.applied_results,
                implementation_result_evidence_ids=(
                    implementation_batch.applied_result_evidence_ids
                ),
                unresolved_implementation_handoff_ids=(
                    implementation_batch.unresolved_handoff_ids
                ),
                rejected_implementation_result_evidence_ids=(
                    implementation_batch.rejected_result_evidence_ids
                ),
            )

        verifier_inputs = [runtime_evidence, questions, retrievals, model, scope]
        if semantic_batch is not None:
            verifier_inputs = [semantic_batch, questions, model, scope]
        verifier_stage_output = stage(
            CanonicalRuntimeStage.HYPOTHESIS_VERIFIER,
            verifier_inputs,
            verify_with_optional_second_pass,
        )
        hypotheses = verifier_stage_output.hypotheses
        model = verifier_stage_output.behavior_model
        runtime_evidence = verifier_stage_output.evidence_bundle
        implementation_handoffs_for_trace = list(
            verifier_stage_output.implementation_handoffs
        )
        implementation_results_for_trace = list(
            verifier_stage_output.implementation_results
        )
        unresolved_implementation_handoff_ids_for_trace = list(
            verifier_stage_output.unresolved_implementation_handoff_ids
        )
        if verifier_stage_output.consumed_evidence_ids:
            try:
                record_semantic_usage_trace(
                    runtime_evidence,
                    verifier_stage_output.consumed_evidence_ids,
                )
            except Exception:
                runtime_warnings.append("SEMANTIC_USAGE_TRACE_UPDATE_FAILED")
        hypotheses_for_trace = list(hypotheses)
        impact_model = pre_verifier_model if semantic_batch is not None else model
        impacts = stage(
            CanonicalRuntimeStage.DOMAIN_SPECIFIC_IMPACT_MODEL,
            [visible, domains, impact_model],
            lambda: self._reasoning.model_domain_impact(visible, domains, impact_model),
        )
        dispositions = stage(
            CanonicalRuntimeStage.COVERAGE_DISPOSITION_CLASSIFIER,
            [facts, closure, impacts, hypotheses, scope, questions],
            lambda: self._reasoning.classify_coverage(
                facts, closure, impacts, hypotheses, scope, questions
            ),
        )
        dispositions_for_trace = list(dispositions)
        missing_question_resolutions = self._missing_questions.resolve_after_evidence(
            report=missing_question_quality,
            retrievals=retrievals,
            dispositions=dispositions,
            closure=closure,
        )
        # Keep the reasoning questions immutable across provider modes.  The
        # terminal state is carried by the separate, evidence-linked resolution
        # records so second-pass evidence cannot rewrite question identity.
        questions_for_trace = list(questions)
        candidate_resolution = stage(
            CanonicalRuntimeStage.ACCEPTANCE_CONTRACT_RESOLVER,
            [facts, dispositions, questions],
            lambda: self._reasoning.resolve_acceptance_contract_with_trace(
                facts, dispositions, questions
            ),
        )
        candidates = candidate_resolution.candidates
        candidates_for_trace = list(candidates)
        completeness_gate = stage(
            CanonicalRuntimeStage.BEHAVIORAL_COMPLETENESS_GATE,
            [
                closure,
                questions,
                scope,
                hypotheses,
                dispositions,
                missing_question_quality,
            ],
            lambda: self._reasoning.behavioral_completeness_gate(
                closure,
                questions,
                scope,
                hypotheses,
                dispositions,
                missing_question_quality,
            ),
        )
        def promote_with_lifecycle() -> tuple[
            GateDecision,
            list[AcceptancePromotionDecision],
            list[CandidateLifecycleRecord],
        ]:
            gate, decisions = self._reasoning.acceptance_promotion_gate(
                candidates, facts, scope, dispositions
            )
            lifecycle = self._reasoning.build_candidate_lifecycle(
                candidate_resolution, decisions
            )
            return gate, decisions, lifecycle

        promotion_gate, promotions, candidate_lifecycle = stage(
            CanonicalRuntimeStage.ACCEPTANCE_PROMOTION_GATE,
            [candidate_resolution, facts, scope, dispositions],
            promote_with_lifecycle,
        )
        promotions_for_trace = list(promotions)
        gates = [contract_gate, completeness_gate, promotion_gate]
        structured_plan, rendered_output = stage(
            CanonicalRuntimeStage.FINAL_QE_PLAN_RENDERER,
            [
                request,
                facts,
                scope,
                model,
                closure,
                questions,
                impacts,
                dispositions,
                candidates,
                promotions,
                gates,
                candidate_resolution,
                candidate_lifecycle,
            ],
            lambda: self._reasoning.render_final_plan(
                request,
                facts,
                scope,
                model,
                closure,
                questions,
                impacts,
                dispositions,
                candidates,
                promotions,
                gates,
                candidate_resolution,
                candidate_lifecycle,
            ),
        )
        structured_plan_for_trace = structured_plan
        trace = self._trace(
            run_id=run_id,
            request=request,
            evidence=runtime_evidence,
            started_at=run_started,
            stage_trace=stage_trace,
            compatibility_adapter=compatibility_adapter,
            deprecated_path=deprecated_path,
            warnings=runtime_warnings,
            compatibility_projection=list(compatibility_projection or []),
            facts=facts,
            model=model,
            closure=closure,
            retrievals=retrievals,
            hypotheses=hypotheses,
            implementation_handoffs=implementation_handoffs_for_trace,
            implementation_results=implementation_results_for_trace,
            unresolved_implementation_handoff_ids=(
                unresolved_implementation_handoff_ids_for_trace
            ),
            candidates=candidates,
            candidate_resolution=candidate_resolution,
            candidate_lifecycle=candidate_lifecycle,
            structured_plan=structured_plan,
            dispositions=dispositions,
            promotions=promotions,
            gates=gates,
            question_generation_trace=question_generation_trace,
            qe_investigation=investigation,
            missing_question_quality=missing_question_quality,
            missing_question_resolutions=missing_question_resolutions,
        )
        _LAST_RUNTIME_TRACE.set(trace)
        blocked = any(
            gate.status in {GateStatus.FAILED, GateStatus.BLOCKED} for gate in gates
        )
        needs_human_review = not blocked and (
            facts.contract_mode.value != "HUMAN_ACCEPTED_CONTRACT"
            or bool(unresolved_implementation_handoff_ids_for_trace)
            or any(
                row.status == InvestigationFamilySatisfactionStatus.UNSATISFIED
                for row in missing_question_quality.family_satisfaction
            )
        )
        payload = {
            "jira_key": request.jira_key,
            "contract_facts": facts.model_dump(mode="json"),
            "domains": [row.model_dump(mode="json") for row in domains],
            "scope": scope.model_dump(mode="json"),
            "change_surfaces": [row.model_dump(mode="json") for row in surfaces],
            "abstract_signals": [
                row.model_dump(mode="json") for row in abstract_signals
            ],
            "reasoning_pattern_activations": [
                row.model_dump(mode="json") for row in reasoning_pattern_activations
            ],
            "qe_investigation": investigation.model_dump(mode="json"),
            "missing_question_quality": missing_question_quality.model_dump(
                mode="json"
            ),
            "missing_question_resolutions": [
                row.model_dump(mode="json") for row in missing_question_resolutions
            ],
            "behavior_model": model.model_dump(mode="json"),
            "semantic_closure": [row.model_dump(mode="json") for row in closure],
            "missing_questions": [row.model_dump(mode="json") for row in questions],
            "directed_retrievals": [row.model_dump(mode="json") for row in retrievals],
            "hypotheses": [row.model_dump(mode="json") for row in hypotheses],
            "domain_impacts": [row.model_dump(mode="json") for row in impacts],
            "coverage_dispositions": [
                row.model_dump(mode="json") for row in dispositions
            ],
            "acceptance_candidates": [
                row.model_dump(mode="json") for row in candidates
            ],
            "discovered_acceptance_candidates": [
                row.model_dump(mode="json")
                for row in candidate_resolution.discovered_candidates
            ],
            "candidate_dedup_decisions": [
                row.model_dump(mode="json")
                for row in candidate_resolution.dedup_decisions
            ],
            "candidate_lifecycle": [
                row.model_dump(mode="json") for row in candidate_lifecycle
            ],
            "promotion_decisions": [row.model_dump(mode="json") for row in promotions],
            "gate_decisions": [row.model_dump(mode="json") for row in gates],
            "structured_plan": structured_plan.model_dump(mode="json"),
            "plan_markdown": rendered_output,
        }
        if (
            implementation_handoffs_for_trace
            or implementation_results_for_trace
            or verifier_stage_output.rejected_implementation_result_evidence_ids
        ):
            payload.update(
                {
                    "github_implementation_verification_handoffs": [
                        row.model_dump(mode="json", by_alias=True)
                        for row in implementation_handoffs_for_trace
                    ],
                    "github_implementation_verification_results": [
                        row.model_dump(mode="json", by_alias=True)
                        for row in implementation_results_for_trace
                    ],
                    "unresolved_github_implementation_handoff_ids": (
                        unresolved_implementation_handoff_ids_for_trace
                    ),
                    "rejected_github_implementation_result_evidence_ids": (
                        verifier_stage_output.rejected_implementation_result_evidence_ids
                    ),
                }
            )
        result = GenerationResult(
            run_id=run_id,
            request_id=request.request_id,
            evidence_bundle_id=runtime_evidence.bundle_id,
            evidence_bundle=runtime_evidence,
            status=(
                "blocked"
                if blocked
                else "needs_human_review"
                if needs_human_review
                else "completed"
            ),
            output_contract=request.output_contract,
            output_kind="test_plan",
            output_payload=payload,
            rendered_output=rendered_output,
            structured_output=payload,
            structured_plan=structured_plan,
            gate_decisions=gates,
            validation_status="failed" if blocked else "passed",
            validation_result={
                "status": (
                    "failed"
                    if blocked
                    else "needs_human_review"
                    if needs_human_review
                    else "passed"
                ),
                "gates": [row.model_dump(mode="json") for row in gates],
            },
            runtime_warnings=runtime_warnings,
            metrics={
                "evidence_record_count": len(runtime_evidence.records),
                "used_evidence_count": len(trace.consumed_evidence_ids),
                "stage_count": len(stage_trace),
                "contract_fact_count": len(facts.facts),
                "closure_dimension_count": len(closure),
                "missing_question_submitted_count": len(
                    missing_question_quality.submitted_questions
                ),
                "missing_question_accepted_count": len(questions),
                "missing_question_rejected_count": (
                    len(missing_question_quality.submitted_questions) - len(questions)
                ),
                "missing_question_resolved_by_evidence_count": sum(
                    row.status.value == "RESOLVED_BY_EVIDENCE"
                    for row in missing_question_resolutions
                ),
                "second_pass_retrieval_count": len(retrievals),
                "github_implementation_handoff_count": len(
                    implementation_handoffs_for_trace
                ),
                "github_implementation_result_count": len(
                    implementation_results_for_trace
                ),
            },
            trace=trace,
        )
        capture_question_trace(
            output_sha256=result.output_sha256,
            completion_state=TraceCompletionState.COMPLETE,
        )
        if runtime_warnings != result.runtime_warnings:
            result.runtime_warnings = list(runtime_warnings)
        return result

    def generate_backend_compatibility(
        self,
        *,
        request: GenerationRequest,
        packet: dict[str, Any],
        benchmark_input: dict[str, Any] | None = None,
        benchmark_source_path: str = "",
        claude_question_submission: ClaudeMissingQuestionSubmission | None = None,
    ) -> GenerationResult:
        """Normalize a backend packet and delegate without a composer hook."""

        bundle = self.normalize_packet(packet, request=request)
        if benchmark_input is not None:
            benchmark_bundle = self.normalize_benchmark_input(
                benchmark_input,
                request=request,
                source_path=benchmark_source_path,
            )
            bundle = visible_bundle(
                merge_bundles([bundle, benchmark_bundle], tenant_id=request.tenant_id),
                request.principal,
            )
        projection = build_legacy_compatibility_projection(packet, bundle)
        return self.run(
            request,
            bundle,
            claude_question_submission=claude_question_submission,
            compatibility_adapter="backend_packet_normalizer_v2",
            compatibility_projection=projection.evidence_links,
        )

    def adapt_legacy_packet(
        self, *, request: GenerationRequest, packet: dict[str, Any]
    ) -> GenerationResult:
        """Deprecated input adapter; reasoning still delegates to ``run``."""

        bundle = self.normalize_packet(packet, request=request)
        projection = build_legacy_compatibility_projection(packet, bundle)
        return self.run(
            request,
            bundle,
            compatibility_adapter="legacy_packet_normalizer_v2",
            deprecated_path=True,
            warnings=[
                "Legacy packet input delegated to the canonical stage-owned runtime."
            ],
            compatibility_projection=projection.evidence_links,
        )

    def adapt_codex_artifacts(
        self,
        *,
        request: GenerationRequest,
        manifest: dict[str, Any],
        plan_markdown: str = "",
        gate_status: str = "",
        claude_question_submission: ClaudeMissingQuestionSubmission | None = None,
    ) -> GenerationResult:
        """Normalize Codex evidence; external prose/gates cannot control the run."""

        if request.generation_profile != GenerationProfile.CODEX_CANONICAL:
            raise ValueError(
                "Codex artifact adapter requires the canonical Codex profile"
            )
        bundle = visible_bundle(
            normalize_codex_manifest(
                manifest,
                tenant_id=request.tenant_id,
                jira_key=request.jira_key,
            ),
            request.principal,
        )
        runtime_warnings: list[str] = []
        if plan_markdown or gate_status:
            runtime_warnings.append(
                "Caller-supplied prose and gate status did not select canonical stages or gates."
            )
        return self.run(
            request,
            bundle,
            claude_question_submission=claude_question_submission,
            compatibility_adapter="codex_manifest_normalizer_v2",
            warnings=runtime_warnings,
        )


CANONICAL_TEST_PLAN_RUNTIME = CanonicalTestPlanRuntime()


def get_last_runtime_trace() -> RuntimeTrace | None:
    return _LAST_RUNTIME_TRACE.get()


__all__ = [
    "CANONICAL_TEST_PLAN_RUNTIME",
    "CanonicalTestPlanRuntime",
    "get_last_fluffyjaws_shadow_trace",
    "get_last_runtime_trace",
]
