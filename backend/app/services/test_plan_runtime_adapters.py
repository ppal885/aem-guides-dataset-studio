"""Normalization and projection adapters for the canonical Test Plan runtime.

Adapters have no reasoning policy.  They cannot choose domains, stages, gates,
or acceptance promotions.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.schemas_canonical_test_plan_runtime import (
    CanonicalEvidenceBundle,
    ContractFactType,
    ContractMode,
    GateStatus,
    GenerationProfile,
    GenerationRequest,
    GenerationResult,
    LegacyCompatibilityProjection,
    PromotionStatus,
    RuntimeEntryPoint,
    WrittenAcceptanceCriterion,
    WriterProjectionStatus,
    stable_sha256,
)
from app.core.schemas_test_plan_pipeline import (
    ConfidenceDimension,
    PipelineScore,
    PipelineScoreBreakdown,
    PipelineStateTransition,
    QeHandoff,
    TestPlanPipelineRequest,
    TestPlanPipelineResult,
    TicketBrief,
)
from app.services.canonical_evidence_service import (
    build_legacy_compatibility_projection,
    normalize_legacy_packet,
)
from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME


def generation_request_from_pipeline_request(
    request: TestPlanPipelineRequest,
    *,
    entry_point: RuntimeEntryPoint | str,
    user: Any | None = None,
    benchmark_version: str = "",
    benchmark_split: str = "",
    benchmark_record_id: str = "",
) -> GenerationRequest:
    """Normalize an entry request; this does not select reasoning behavior."""

    return CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key=request.jira_key,
        tenant_id=request.tenant_id,
        entry_point=entry_point,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
        user=user,
        options=request.model_dump(mode="json"),
        benchmark_version=benchmark_version,
        benchmark_split=benchmark_split,
        benchmark_record_id=benchmark_record_id,
    )


def pipeline_request_from_generation_request(
    request: GenerationRequest,
) -> TestPlanPipelineRequest:
    payload = request.options.model_dump(mode="json")
    payload.update({"jira_key": request.jira_key, "tenant_id": request.tenant_id})
    return TestPlanPipelineRequest.model_validate(payload)


def canonical_bundle_from_packet(
    packet: dict[str, Any], *, tenant_id: str
) -> CanonicalEvidenceBundle:
    return normalize_legacy_packet(packet, tenant_id=tenant_id)


_HUMAN_FACING_WRITER_STATUSES = frozenset(
    {
        WriterProjectionStatus.STANDALONE_AC,
        WriterProjectionStatus.ATTACHED_VARIANT,
        WriterProjectionStatus.ATTACHED_TBD,
    }
)
_INTERNAL_WRITER_METADATA_PREFIX = "Internal scope or closure metadata"


def _normalized_delivery_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _canonical_uac_delivery_failures(result: GenerationResult) -> list[str]:
    """Verify that a compatibility response cannot hide writer-admitted coverage."""

    plan = result.structured_plan
    if plan is None:
        return []
    projections = [
        row
        for row in plan.writer_projection_records
        if row.priority in {"P0", "P1"}
        and not (
            row.status == WriterProjectionStatus.EXPLICITLY_EXCLUDED
            and row.reason.startswith(_INTERNAL_WRITER_METADATA_PREFIX)
        )
    ]
    if not projections:
        return []

    raw_written = result.output_payload.get("written_acceptance_criteria")
    if not isinstance(raw_written, list):
        return [
            "Canonical Writer output is unavailable; compatibility delivery cannot "
            "prove complete P0/P1 UAC coverage."
        ]
    try:
        written = [
            WrittenAcceptanceCriterion.model_validate(row) for row in raw_written
        ]
    except (TypeError, ValueError) as error:
        return [
            "Canonical Writer output is invalid; compatibility delivery cannot "
            f"prove complete P0/P1 UAC coverage ({error})."
        ]

    failures: list[str] = []
    written_by_id = {row.criterion_id: row for row in written}
    rendered = _normalized_delivery_text(result.rendered_output)
    if not rendered:
        failures.append("Canonical rendered UAC is empty.")

    for projection in projections:
        if projection.status not in _HUMAN_FACING_WRITER_STATUSES:
            failures.append(
                f"{projection.priority} coverage "
                f"{projection.coverage_disposition_id} has no human-facing UAC projection."
            )
            continue
        criterion = written_by_id.get(projection.criterion_id)
        if criterion is None:
            failures.append(
                f"{projection.priority} coverage "
                f"{projection.coverage_disposition_id} references a missing Writer criterion."
            )
            continue
        for text in projection.projected_variant_texts:
            normalized = _normalized_delivery_text(text)
            if normalized and normalized not in rendered:
                failures.append(
                    f"{projection.priority} coverage "
                    f"{projection.coverage_disposition_id} is absent from the "
                    "canonical rendered UAC."
                )
    return failures


class LegacyCompatibilityProjector:
    """Named, lossless projections that run only after canonical reasoning."""

    projector_id = "legacy_compatibility_projector_v2"

    def project_packet(
        self, packet: dict[str, Any], evidence: CanonicalEvidenceBundle
    ) -> LegacyCompatibilityProjection:
        return build_legacy_compatibility_projection(packet, evidence)

    @staticmethod
    def is_postable(result: GenerationResult) -> bool:
        """Reflect the canonical result; never run or reinterpret a gate here."""

        return (
            result.status == "completed"
            and result.validation_status == "passed"
            and bool(result.gate_decisions)
            and all(row.status == GateStatus.PASSED for row in result.gate_decisions)
            and not _canonical_uac_delivery_failures(result)
        )

    def project_result(
        self,
        result: GenerationResult,
        *,
        legacy_packet: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a stable compatibility DTO without changing canonical decisions."""

        packet = legacy_packet or {}
        delivery_failures = _canonical_uac_delivery_failures(result)
        return {
            "projection_version": "canonical-result-compatibility-v2",
            "projector_id": self.projector_id,
            "runtime_id": result.runtime_id,
            "runtime_version": result.runtime_version,
            "run_id": result.run_id,
            "request_id": result.request_id,
            "jira_key": result.output_payload.get("jira_key", ""),
            "status": result.status,
            "validation_status": result.validation_status,
            "postable": self.is_postable(result),
            "plan_markdown": result.rendered_output,
            "uac_delivery": {
                "canonical_field": "plan_markdown",
                "complete": not delivery_failures,
                "failures": delivery_failures,
            },
            "output_payload": result.output_payload,
            "structured_plan": (
                result.structured_plan.model_dump(mode="json")
                if result.structured_plan is not None
                else None
            ),
            "gate_decisions": [
                row.model_dump(mode="json") for row in result.gate_decisions
            ],
            "evidence_bundle_id": result.evidence_bundle_id,
            # These raw fields preserve the small compatibility surface needed by
            # legacy transport callers.  They cannot feed back into canonical logic.
            "issue": packet.get("issue") or {},
            "generation_mode": packet.get("generation_mode"),
            "trace": result.trace.model_dump(mode="json"),
        }

    def project_pipeline_result(
        self,
        result: GenerationResult,
        *,
        request: TestPlanPipelineRequest,
        legacy_packet: dict[str, Any],
        correlation_id: str,
        elapsed_ms: int,
    ) -> TestPlanPipelineResult:
        """Mechanically project canonical records into the retained REST/CLI DTO."""

        payload = result.output_payload
        issue = legacy_packet.get("issue") or {}
        facts = list((payload.get("contract_facts") or {}).get("facts") or [])
        scope = payload.get("scope") or {}
        questions = list(payload.get("missing_questions") or [])
        promotions = list(payload.get("promotion_decisions") or [])
        candidates = {
            str(row.get("candidate_id") or ""): row
            for row in payload.get("acceptance_candidates") or []
        }
        delivery_failures = _canonical_uac_delivery_failures(result)
        contract_mode = str(
            (payload.get("contract_facts") or {}).get("contract_mode") or ""
        )

        acceptance_criteria = _project_acceptance_criteria(
            result,
            candidates=candidates,
            delivery_failures=delivery_failures,
        )
        score = _project_pipeline_score(
            result,
            contract_mode=contract_mode,
            promotions=promotions,
            questions=questions,
        )
        ticket_brief = _project_ticket_brief(
            result,
            issue=issue,
            facts=facts,
            scope=scope,
        )
        test_cases = _project_test_cases(result)
        coverage_matrix = _project_coverage_matrix(
            result,
            acceptance_criteria=acceptance_criteria,
            promotions=promotions,
            questions=questions,
        )
        pm_questions = [
            str(row.get("question") or "")
            for row in questions
            if row.get("blocking") or row.get("authority_subject") == "PRODUCT_CONTRACT"
        ]
        qa_questions = [
            str(row.get("question") or "")
            for row in questions
            if str(row.get("question") or "") not in pm_questions
        ]
        blockers = [
            failure for gate in result.gate_decisions for failure in gate.failures
        ]
        blockers.extend(delivery_failures)
        review_status = (
            "Needs human review"
            if score.human_review_required or delivery_failures
            else "Ready for QE review"
        )
        qe_handoff = QeHandoff(
            review_status=review_status,
            must_run_before_release=[
                str(row.get("uac_id") or "") for row in acceptance_criteria
            ],
            pm_questions=pm_questions,
            qa_questions=qa_questions,
            blocking_gaps=blockers,
            next_actions=(
                [
                    (
                        "Restore complete canonical UAC delivery, then run the "
                        "canonical engine again."
                        if delivery_failures
                        else "Resolve the listed product decisions, then run the canonical engine again."
                    )
                ]
                if score.human_review_required or delivery_failures
                else ["QE can review and execute the canonical plan."]
            ),
        )
        state_history = [
            PipelineStateTransition(
                state=row.stage.value,
                status=("completed" if row.status == "completed" else "failed"),
                reason="; ".join(row.warnings),
                elapsed_ms=round(row.duration_ms),
            )
            for row in result.trace.stage_trace
        ]
        canonical_projection = self.project_result(
            result,
            legacy_packet=legacy_packet,
        )
        return TestPlanPipelineResult(
            jira_key=str(payload.get("jira_key") or request.jira_key),
            correlation_id=correlation_id,
            evidence_snapshot_id=result.evidence_bundle_id,
            plan_fingerprint=result.output_sha256,
            stages_completed=[row.stage.value for row in result.trace.stage_trace],
            ticket_brief=ticket_brief,
            ticket_analysis={
                "current_behaviour": ticket_brief.current_behavior,
                "expected_behaviour": ticket_brief.expected_behavior,
                "contract_facts": facts,
                "domains": payload.get("domains") or [],
                "scope": scope,
                "change_surfaces": payload.get("change_surfaces") or [],
                "canonical_run_id": result.run_id,
            },
            acceptance_criteria=acceptance_criteria,
            test_cases=test_cases,
            coverage_matrix=coverage_matrix,
            score=score,
            confidence_dimensions=score.dimensions,
            uac_intelligence={
                "contract_mode": contract_mode,
                "acceptance_candidates": list(candidates.values()),
                "promotion_decisions": promotions,
                "missing_questions": questions,
            },
            rag_packet_summary={
                "canonical_evidence_bundle_id": result.evidence_bundle_id,
                "source_counts": result.evidence_bundle.source_counts,
                "evidence_record_count": len(result.evidence_bundle.records),
                "unavailable_sources": result.evidence_bundle.unavailable_sources,
            },
            # A compatibility field must never become a shorter manual draft.
            # Preserve it only as an exact canonical mirror for existing clients.
            draft_test_plan_markdown=result.rendered_output,
            output_provenance={
                "canonical": "qe_review_package.canonical_result.plan_markdown",
                "draft_test_plan_markdown": (
                    "CANONICAL_MIRROR:IDENTICAL_TO:"
                    "qe_review_package.canonical_result.plan_markdown"
                ),
                "acceptance_criteria": (
                    "CANONICAL_WRITER_MIRROR:COMPLETE_P0_P1_ONLY"
                    if not delivery_failures
                    else "BLOCKED:CANONICAL_UAC_DELIVERY_INCOMPLETE"
                ),
            },
            validation=result.validation_result,
            qe_handoff=qe_handoff,
            qe_review_package={
                "review_id": f"QE-{request.jira_key}-{correlation_id[:8]}",
                "review_status": review_status,
                "canonical_result": canonical_projection,
                "trace": result.trace.model_dump(mode="json"),
            },
            qe_investigation=dict(payload.get("qe_investigation") or {}),
            missing_question_quality=dict(
                payload.get("missing_question_quality") or {}
            ),
            missing_question_resolutions=list(
                payload.get("missing_question_resolutions") or []
            ),
            state_history=state_history,
            elapsed_ms=max(0, elapsed_ms),
        )


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            value = next((item for item in value if str(item).strip()), "")
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _fact_literals(
    facts: list[dict[str, Any]], fact_type: ContractFactType
) -> list[str]:
    return [
        str(row.get("literal") or "").strip()
        for row in facts
        if row.get("fact_type") == fact_type.value
        and str(row.get("literal") or "").strip()
    ]


def _project_ticket_brief(
    result: GenerationResult,
    *,
    issue: dict[str, Any],
    facts: list[dict[str, Any]],
    scope: dict[str, Any],
) -> TicketBrief:
    fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
    components = issue.get("components") or fields.get("components") or []
    component = _first_text(
        issue.get("component"),
        [row.get("name") if isinstance(row, dict) else row for row in components],
    )
    direct_expected = _fact_literals(facts, ContractFactType.DIRECT_EXPECTED_BEHAVIOR)
    scope_values = [
        *[str(value) for value in scope.get("in_scope") or []],
        *[f"Out of scope: {value}" for value in scope.get("out_of_scope") or []],
    ]
    return TicketBrief(
        jira_key=str(result.output_payload.get("jira_key") or ""),
        summary=_first_text(issue.get("summary"), fields.get("summary")),
        component=component,
        issue_type=_first_text(
            issue.get("issue_type"),
            (fields.get("issuetype") or {}).get("name")
            if isinstance(fields.get("issuetype"), dict)
            else fields.get("issuetype"),
        ),
        priority=_first_text(
            issue.get("priority"),
            (fields.get("priority") or {}).get("name")
            if isinstance(fields.get("priority"), dict)
            else fields.get("priority"),
        ),
        customer=_first_text(
            issue.get("customer"), issue.get("customer_name"), issue.get("account")
        )
        or None,
        labels=[
            str(value) for value in issue.get("labels") or fields.get("labels") or []
        ],
        current_behavior=_first_text(
            issue.get("actual_behavior"),
            issue.get("actual_result"),
            issue.get("current_behavior"),
        ),
        expected_behavior=_first_text(
            issue.get("expected_behavior"),
            issue.get("expected_result"),
            direct_expected,
        ),
        scope_hint="; ".join(scope_values),
    )


def _project_acceptance_criteria(
    result: GenerationResult,
    *,
    candidates: dict[str, dict[str, Any]],
    delivery_failures: list[str],
) -> list[dict[str, Any]]:
    """Mirror Writer output; never rebuild a UAC from promotion rows."""

    if delivery_failures:
        return []
    raw_written = result.output_payload.get("written_acceptance_criteria")
    if not isinstance(raw_written, list):
        return []
    written = [
        WrittenAcceptanceCriterion.model_validate(row) for row in raw_written
    ]
    dispositions = {
        str(row.get("disposition_id") or ""): row
        for row in result.output_payload.get("coverage_dispositions") or []
    }
    rows: list[dict[str, Any]] = []
    for criterion in written:
        sequence = len(rows) + 1
        uac_id = f"UAC-{sequence:02d}"
        statement = " ".join(
            part
            for part in [
                criterion.outcome,
                *[sub_point.text for sub_point in criterion.sub_points],
            ]
            if part.strip()
        )
        evidence_refs = list(dict.fromkeys(criterion.evidence_ids))
        candidate_rows = [
            candidates[candidate_id]
            for candidate_id in criterion.source_candidate_ids
            if candidate_id in candidates
        ]
        for candidate in candidate_rows:
            evidence_refs.extend(
                str(value) for value in candidate.get("evidence_ids") or []
            )
        evidence_refs = list(dict.fromkeys(evidence_refs))
        if not evidence_refs:
            evidence_refs = [result.evidence_bundle_id]
        accepted_snapshot = _accepted_uac_snapshot(result, evidence_refs)
        confirmed = bool(
            candidate_rows
            and len(candidate_rows) == len(criterion.source_candidate_ids)
            and all(
                candidate.get("accepted_human_contract")
                for candidate in candidate_rows
            )
            and accepted_snapshot
        )
        tbd_questions = [
            sub_point.text
            for sub_point in criterion.sub_points
            if sub_point.kind.value == "TBD_QUESTION"
        ]
        applicable_dispositions = [
            dispositions[disposition_id]
            for disposition_id in criterion.source_disposition_ids
            if disposition_id in dispositions
        ]
        priority = next(
            (
                value
                for value in ("P0", "P1", "P2")
                if any(
                    row.get("priority") == value
                    for row in applicable_dispositions
                )
            ),
            "P1",
        )
        sphere = (
            "Negative"
            if any(
                str(row.get("contract_type") or "") == "NEGATIVE"
                for row in applicable_dispositions
            )
            else "Basic"
        )
        requirement_category = next(
            (
                str(row.get("disposition") or "")
                for row in applicable_dispositions
                if str(row.get("disposition") or "")
            ),
            "ACCEPTANCE_CONTRACT",
        )
        classification = next(
            (
                str(candidate.get("contract_mode") or "")
                for candidate in candidate_rows
                if str(candidate.get("contract_mode") or "")
            ),
            str(
                (result.output_payload.get("contract_facts") or {}).get(
                    "contract_mode"
                )
                or ""
            ),
        )
        derivation = (
            "HUMAN_CLARIFICATION_REQUIRED"
            if criterion.unresolved or tbd_questions
            else "TICKET_CONFIRMED"
            if confirmed
            else "REASONABLE_ASSUMPTION"
        )
        fingerprint = stable_sha256(
            {
                "uac_id": uac_id,
                "statement": statement,
                "writer_criterion_id": criterion.criterion_id,
                "evidence_refs": evidence_refs,
            }
        )
        rows.append(
            {
                "schema_version": "aem-guides-ac-v1",
                "uac_id": uac_id,
                "status": "Confirmed" if confirmed else "Proposed",
                "sphere": sphere,
                "behaviour_statement": statement,
                "given": "The Jira scope and required test data are available.",
                "when": "The behavior described in this criterion is exercised.",
                "then": statement,
                "priority": priority,
                "requirement_category": requirement_category,
                "classification": classification,
                "evidence_refs": evidence_refs,
                "source_snapshot_ids": (
                    [accepted_snapshot] if confirmed else evidence_refs
                ),
                "source_clause_id": uac_id if confirmed else "",
                "derivation_classification": derivation,
                "confidence": 100 if confirmed else 80,
                "assumptions": [],
                "open_question": "; ".join(tbd_questions),
                "automation_consumption": "blocked",
                "automation_block_reason": (
                    "Canonical UAC projection requires explicit human approval "
                    "before automation consumption."
                ),
                "fingerprint": fingerprint,
            }
        )
    return rows


def _accepted_uac_snapshot(result: GenerationResult, evidence_refs: list[str]) -> str:
    """Return only a real current-UAC snapshot carried by source evidence."""

    for record in result.evidence_bundle.records:
        if record.evidence_id not in evidence_refs or not isinstance(
            record.content, dict
        ):
            continue
        snapshot = str(record.content.get("source_snapshot_id") or "").strip()
        if snapshot.startswith("jira:") and ":current-uac:" in snapshot:
            return snapshot
    return ""


def _project_pipeline_score(
    result: GenerationResult,
    *,
    contract_mode: str,
    promotions: list[dict[str, Any]],
    questions: list[dict[str, Any]],
) -> PipelineScore:
    gates = result.gate_decisions
    passed_count = sum(row.status == GateStatus.PASSED for row in gates)
    overall = round(100 * passed_count / len(gates)) if gates else 0
    blockers = [failure for row in gates for failure in row.failures]
    fatal = not LEGACY_COMPATIBILITY_PROJECTOR.is_postable(result)
    review_reasons: list[str] = []
    if contract_mode != ContractMode.HUMAN_ACCEPTED_CONTRACT.value:
        review_reasons.append("The acceptance contract is proposed or partial.")
    if any(row.get("blocking") for row in questions):
        review_reasons.append("A blocking product decision remains unresolved.")
    if any(row.get("status") != PromotionStatus.PROMOTED.value for row in promotions):
        review_reasons.append("At least one acceptance candidate was not promoted.")
    review_reasons = list(dict.fromkeys(review_reasons))
    human_review = fatal or bool(review_reasons)
    dimensions: list[ConfidenceDimension] = []
    for index, gate in enumerate(gates):
        base_weight = 100 // len(gates)
        weight = base_weight + (1 if index < 100 % len(gates) else 0)
        dimensions.append(
            ConfidenceDimension(
                name=gate.gate.value,
                weight=weight,
                score=100 if gate.status == GateStatus.PASSED else 0,
                signals=gate.checked_ids,
                deductions=gate.failures,
                recommended_action=(
                    "No gate action required."
                    if gate.status == GateStatus.PASSED
                    else "Resolve the canonical gate failures and run again."
                ),
            )
        )
    return PipelineScore(
        overall=overall,
        tier=("blocked" if fatal else "high" if overall == 100 else "medium"),
        human_review_required=human_review,
        human_review_reasons=review_reasons,
        blockers=blockers,
        warnings=list(result.runtime_warnings),
        breakdown=PipelineScoreBreakdown(uac_quality=overall),
        dimensions=dimensions,
        reason_codes=[
            "CANONICAL_GATE_PROJECTION",
            *(["CANONICAL_RESULT_NOT_POSTABLE"] if fatal else []),
            *(["HUMAN_REVIEW_REQUIRED"] if human_review else []),
        ],
        routing_status=(
            "BLOCKED"
            if fatal
            else "QE_REVIEW_WITH_FLAGS"
            if human_review
            else "QE_REVIEW_READY"
        ),
    )


def _project_test_cases(result: GenerationResult) -> list[dict[str, Any]]:
    if result.structured_plan is None:
        return []
    rows: list[dict[str, Any]] = []
    for section in result.structured_plan.sections:
        if section.section_key in {
            "issue_understanding",
            "product_scope",
            "acceptance_contract",
            "proposed_acceptance_contract",
            "product_decisions",
            "coverage_gate_result",
        }:
            continue
        for item in section.items:
            rows.append(
                {
                    "test_case_id": f"S-{len(rows) + 1:02d}",
                    "title": item,
                    "coverage_section": section.section_key,
                    "steps": [item],
                    "expected_result": item,
                    "source_record_ids": section.source_record_ids,
                }
            )
    return rows


def _project_coverage_matrix(
    result: GenerationResult,
    *,
    acceptance_criteria: list[dict[str, Any]],
    promotions: list[dict[str, Any]],
    questions: list[dict[str, Any]],
) -> dict[str, Any]:
    promotion_count = len(promotions)
    promoted_count = sum(
        row.get("status") == PromotionStatus.PROMOTED.value for row in promotions
    )
    cited = sum(bool(row.get("evidence_refs")) for row in acceptance_criteria)
    disposition_rows = list(result.output_payload.get("coverage_dispositions") or [])
    return {
        "uac_coverage_percentage": (
            round(100 * promoted_count / promotion_count) if promotion_count else 0
        ),
        "evidence_citation_coverage": (
            round(100 * cited / len(acceptance_criteria)) if acceptance_criteria else 0
        ),
        "unsupported_claim_count": sum(
            row.get("disposition") == "UNSUPPORTED_INFERENCE"
            for row in disposition_rows
        ),
        "remaining_risks": [
            str(row.get("question") or "") for row in questions if row.get("question")
        ],
        "canonical_dispositions": disposition_rows,
        "semantic_closure": result.output_payload.get("semantic_closure") or [],
        "gate_decisions": [
            row.model_dump(mode="json") for row in result.gate_decisions
        ],
    }


LEGACY_COMPATIBILITY_PROJECTOR = LegacyCompatibilityProjector()


__all__ = [
    "LEGACY_COMPATIBILITY_PROJECTOR",
    "LegacyCompatibilityProjector",
    "canonical_bundle_from_packet",
    "generation_request_from_pipeline_request",
    "pipeline_request_from_generation_request",
]
