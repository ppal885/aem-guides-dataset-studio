"""Unified test-plan pipeline: ticket → RAG → score → UAC → draft plan → QE handoff."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.core.schemas_test_plan_pipeline import (
    ConfidenceDimension,
    PipelineScore,
    PipelineScoreBreakdown,
    PipelineStateTransition,
    PreUacProductBrief,
    QeHandoff,
    TestPlanPipelineRequest,
    TestPlanPipelineResult,
    TicketBrief,
    TicketWorkflowProfileSummary,
)
from app.core.structured_logging import get_structured_logger
from app.services.guides_test_plan_generator_service import (
    build_guides_test_plan_packet,
    normalize_jira_key,
    render_guides_test_plan_packet_markdown,
)

logger = get_structured_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_JIRA_KEY_RE = re.compile(r"[A-Z][A-Z0-9]+-\d+")
_VALIDATOR = (
    _PROJECT_ROOT
    / "claude-skills"
    / "aem-guides-test-scenario-generator"
    / "scripts"
    / "validate_test_plan.py"
)


def run_test_plan_pipeline(
    request: TestPlanPipelineRequest,
    user: Any | None = None,
) -> TestPlanPipelineResult:
    """Run all pipeline stages synchronously and return a structured result."""
    started = time.perf_counter()
    cid = str(uuid.uuid4())
    key = normalize_jira_key(request.jira_key)
    stages: list[str] = []
    state_history: list[PipelineStateTransition] = []

    def mark(state: str, status: str = "completed", reason: str = "") -> None:
        state_history.append(
            PipelineStateTransition(
                state=state,
                status=status,  # type: ignore[arg-type]
                reason=reason,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
        )

    logger.info_structured(
        "test_plan_pipeline_start",
        extra_fields={"jira_key": key, "correlation_id": cid},
    )

    roles = {str(role).strip().casefold() for role in getattr(user, "roles", [])}
    allow_cross_customer_graph_details = bool(
        getattr(user, "is_admin", False) or "knowledge_reader" in roles
    )
    packet = build_guides_test_plan_packet(
        key,
        tenant_id=request.tenant_id,
        evidence_k=request.evidence_k,
        include_repository_evidence=request.include_repository_evidence,
        max_repo_matches=request.max_repo_matches,
        skip_uac_label_gate=request.skip_uac_label_gate,
        full_rag=request.full_rag,
        include_evidence_graph=request.include_evidence_graph,
        graph_max_paths=request.graph_max_paths,
        allow_cross_customer_graph_details=allow_cross_customer_graph_details,
    )
    stages.append("rag")
    mark("RETRIEVING_EVIDENCE")

    ticket_brief = build_ticket_brief(packet)
    stages.append("ticket_intake")
    mark("ANALYZING_TICKET")
    ticket_analysis = build_enhanced_ticket_analysis(packet, ticket_brief)

    from app.services.pre_uac_product_brief_service import build_pre_uac_product_brief
    from app.services.ticket_workflow_profile_service import classify_ticket_workflow

    workflow = classify_ticket_workflow(packet, ticket_brief)
    stages.append("ticket_workflow")
    mark("CLASSIFYING_TICKET_WORKFLOW")

    pre_uac_brief: PreUacProductBrief | None = None
    if packet.get("generation_mode") != "blocked":
        pre_uac_brief = build_pre_uac_product_brief(packet, ticket_brief, workflow)
        stages.append("pre_uac_product_brief")
        mark("BUILDING_PRE_UAC_CONTEXT")

    uac_intel: dict[str, Any] | None = None
    if request.include_uac_intelligence and packet.get("generation_mode") != "blocked":
        try:
            from services.uac.uac_orchestrator import run_requirement_intelligence

            uac_intel = run_requirement_intelligence(
                key,
                include_docs=True,
                max_similar_jiras=8,
                correlation_id=cid,
            )
            stages.append("uac_intelligence")
            mark("GENERATING_UAC")
            ticket_brief = merge_uac_into_brief(ticket_brief, uac_intel)
            ticket_analysis = build_enhanced_ticket_analysis(packet, ticket_brief)
            workflow = classify_ticket_workflow(packet, ticket_brief, uac_intel)
            pre_uac_brief = build_pre_uac_product_brief(packet, ticket_brief, workflow)
        except Exception as exc:
            uac_intel = _fallback_uac_from_packet(packet)
            stages.append("uac_intelligence_fallback")
            mark("GENERATING_UAC", "completed", "Used deterministic fallback because UAC orchestrator was unavailable.")
            ticket_brief = merge_uac_into_brief(ticket_brief, uac_intel)
            ticket_analysis = build_enhanced_ticket_analysis(packet, ticket_brief)
            workflow = classify_ticket_workflow(packet, ticket_brief, uac_intel)
            pre_uac_brief = build_pre_uac_product_brief(packet, ticket_brief, workflow)
            logger.warning_structured(
                "test_plan_pipeline_uac_fallback",
                extra_fields={"jira_key": key, "error": str(exc)},
            )

    acceptance_criteria = build_evidence_grounded_acceptance_criteria(
        packet,
        uac_intel,
        ticket_brief,
        pre_uac_brief,
    )
    stages.append("acceptance_criteria")
    mark("NORMALIZING_UAC")

    test_cases = build_grounded_test_cases(packet, acceptance_criteria, ticket_brief, workflow)
    coverage_matrix = build_requirement_test_coverage(acceptance_criteria, test_cases)
    stages.append("test_case_traceability")
    mark("VALIDATING_COVERAGE")

    score = score_pipeline_readiness(
        packet,
        uac_intel,
        workflow=workflow,
        human_review_threshold=request.human_review_threshold,
        ticket_brief=ticket_brief,
        acceptance_criteria=acceptance_criteria,
        coverage_matrix=coverage_matrix,
    )
    stages.append("score")
    mark("SCORING_CONFIDENCE")

    draft_md: str | None = None
    validation: dict[str, Any] | None = None
    if request.compose_draft_plan and packet.get("generation_mode") != "blocked":
        draft_md = compose_draft_test_plan(
            packet, uac_intel, score, ticket_brief, pre_uac_brief, workflow
        )
        stages.append("draft_test_plan")
        mark("GENERATING_TEST_PLAN")
        if draft_md:
            validation = validate_test_plan_markdown(draft_md)

    qe_handoff = build_qe_handoff(
        key,
        packet,
        uac_intel,
        score,
        ticket_brief,
        draft_md,
        validation,
        workflow,
        pre_uac_brief,
    )
    stages.append("qe_handoff")
    mark("QE_REVIEW_READY" if qe_handoff.review_status == "Ready for QE review" else "QE_REVIEW_WITH_FLAGS")
    qe_review_package = build_qe_review_package(
        key,
        cid,
        packet,
        ticket_analysis,
        acceptance_criteria,
        test_cases,
        coverage_matrix,
        score,
        qe_handoff,
        validation,
    )

    artifacts_written: list[str] = []
    if request.write_starling_artifacts:
        starling_root = _resolve_starling_path(request.starling_repo_path)
        artifacts_written = write_starling_artifacts(
            starling_root,
            key,
            packet,
            uac_intel,
            draft_md,
            qe_handoff,
            pre_uac_brief,
            workflow,
        )
        if artifacts_written:
            stages.append("write_starling_artifacts")

    if request.publish_to_team_ui and draft_md:
        from app.services import test_plan_artifact_service as artifacts

        saved = artifacts.save_test_plan(key, draft_md)
        artifacts_written.append(str(saved.get("filename") or f"{key}-test-plan.md"))
        stages.append("publish_team_ui")

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    result = TestPlanPipelineResult(
        jira_key=key,
        correlation_id=cid,
        stages_completed=stages,
        ticket_brief=ticket_brief,
        ticket_workflow=_workflow_summary(workflow),
        pre_uac_product_brief=pre_uac_brief,
        ticket_analysis=ticket_analysis,
        acceptance_criteria=acceptance_criteria,
        test_cases=test_cases,
        coverage_matrix=coverage_matrix,
        score=score,
        confidence_dimensions=score.dimensions,
        uac_intelligence=uac_intel,
        rag_packet_summary=summarize_rag_packet(packet),
        draft_test_plan_markdown=draft_md,
        validation=validation,
        qe_handoff=qe_handoff,
        qe_review_package=qe_review_package,
        state_history=state_history,
        artifacts_written=artifacts_written,
        elapsed_ms=elapsed_ms,
    )

    try:
        from app.services import test_plan_artifact_service as artifacts

        memory_entry = artifacts.record_pipeline_memory(result)
        result.artifacts_written.append(str(memory_entry.get("memory_path") or "pipeline-memory"))
        result.stages_completed.append("pipeline_memory")
    except Exception as exc:
        logger.warning_structured(
            "test_plan_pipeline_memory_failed",
            extra_fields={"jira_key": key, "correlation_id": cid, "error": str(exc)},
        )

    logger.info_structured(
        "test_plan_pipeline_done",
        extra_fields={
            "jira_key": key,
            "correlation_id": cid,
            "score": score.overall,
            "human_review_required": score.human_review_required,
            "elapsed_ms": elapsed_ms,
        },
    )
    return result


def build_ticket_brief(packet: dict[str, Any]) -> TicketBrief:
    issue = packet.get("issue") or {}
    labels = [str(x) for x in (issue.get("labels") or [])]
    summary = str(issue.get("summary") or issue.get("title") or "")
    description = str(issue.get("description") or issue.get("snippet") or "")
    component = _first_non_empty(
        issue.get("component"),
        issue.get("components"),
        _extract_component_from_text(summary, description),
    )
    return TicketBrief(
        jira_key=str(packet.get("jira_key") or issue.get("issue_key") or ""),
        summary=summary,
        component=str(component or ""),
        issue_type=str(issue.get("issue_type") or issue.get("type") or ""),
        priority=str(issue.get("priority") or ""),
        customer=_extract_customer(issue),
        labels=labels,
        current_behavior=_first_non_empty(
            issue.get("actual_behavior"),
            issue.get("actual_result"),
            _extract_field(description, ("actual", "current behavior", "steps to reproduce")),
        ),
        expected_behavior=_first_non_empty(
            issue.get("expected_behavior"),
            issue.get("expected_result"),
            _extract_field(
                description,
                (
                    "expected",
                    "expected result",
                    "expected behavior",
                    "requested enhancement",
                    "requested behaviour",
                    "requested behavior",
                    "next steps requested from engineering",
                ),
            ),
        ),
        scope_hint=_infer_scope(summary, description),
    )


def merge_uac_into_brief(brief: TicketBrief, uac_intel: dict[str, Any]) -> TicketBrief:
    req = uac_intel.get("requirement_understanding") or {}
    cls = uac_intel.get("classification") if isinstance(uac_intel.get("classification"), dict) else {}
    if cls.get("issue_type") and not brief.issue_type:
        brief.issue_type = str(cls["issue_type"])
    if req.get("stated_expected") and not brief.expected_behavior:
        brief.expected_behavior = str(req["stated_expected"])[:2000]
    if req.get("stated_actual") and not brief.current_behavior:
        brief.current_behavior = str(req["stated_actual"])[:2000]
    if req.get("domain_hypothesis") and req["domain_hypothesis"] != "unknown":
        brief.component = brief.component or str(req["domain_hypothesis"])
    return brief


def build_enhanced_ticket_analysis(packet: dict[str, Any], brief: TicketBrief) -> dict[str, Any]:
    """Normalize ticket facts into explicit current/expected behavior and missing info."""
    issue = packet.get("issue") or {}
    description = str(issue.get("description") or issue.get("snippet") or "")
    text = f"{brief.summary}\n{description}"
    api_paths = sorted(set(re.findall(r"/bin/[^\s\"'<>]+", text, re.I)))
    error_messages = _extract_error_messages(text)
    linked = sorted(set(re.findall(r"\b[A-Z][A-Z0-9]+-\d+\b", text)) - {brief.jira_key})
    missing: list[str] = []
    if not brief.expected_behavior:
        missing.append("Expected behaviour")
    if not brief.current_behavior:
        missing.append("Current behaviour / Actual result")
    if not brief.component and not brief.scope_hint:
        missing.append("Component or feature area")
    if not issue.get("priority"):
        missing.append("Priority")

    return {
        "jira_key": brief.jira_key,
        "title": brief.summary,
        "concise_ticket_summary": _summarize_text(brief.summary, description, max_chars=600),
        "issue_type": brief.issue_type,
        "product": brief.product,
        "component": brief.component,
        "subcomponent_or_feature": brief.scope_hint,
        "labels": brief.labels,
        "customer_context": brief.customer or _extract_customer(issue) or "",
        "priority": brief.priority,
        "severity": str(issue.get("severity") or ""),
        "business_impact": _extract_field(description, ("business impact", "impact")),
        "affected_environment": _extract_field(description, ("environment", "server", "tenant", "program")),
        "affected_version_build": _extract_field(description, ("affected version", "build", "fixed version")),
        "preconditions": _extract_field(description, ("precondition", "setup")),
        "reproduction_steps": _extract_steps(description),
        "current_behaviour": brief.current_behavior,
        "expected_behaviour": brief.expected_behavior,
        "existing_acceptance_criteria": list((packet.get("uac_label_gate") or {}).get("instructions") or []),
        "error_messages": error_messages,
        "technical_identifiers": api_paths,
        "linked_jiras": linked,
        "fix_version": str(issue.get("fix_version") or issue.get("fixVersion") or ""),
        "attachments_or_log_metadata": issue.get("attachments") or issue.get("attachment_metadata") or [],
        "missing_information": missing,
        "contradictions": _detect_ticket_contradictions(brief, packet),
        "open_questions": _build_open_questions(brief, packet, missing),
        "statement_classification": {
            "current_behaviour": "TICKET_CONFIRMED" if brief.current_behavior else "HUMAN_CLARIFICATION_REQUIRED",
            "expected_behaviour": "TICKET_CONFIRMED" if brief.expected_behavior else "HUMAN_CLARIFICATION_REQUIRED",
            "repository_evidence": "IMPLEMENTATION_DERIVED",
            "experience_league_evidence": "PRODUCT_DOCUMENTATION_CONFIRMED",
            "dita_spec_evidence": "SPECIFICATION_CONFIRMED",
            "previous_jiras": "PREVIOUS_JIRA_DERIVED",
        },
        "source_references": _collect_evidence_refs(packet),
    }


def build_evidence_grounded_acceptance_criteria(
    packet: dict[str, Any],
    uac_intel: dict[str, Any] | None,
    brief: TicketBrief,
    pre_uac: PreUacProductBrief | None,
) -> list[dict[str, Any]]:
    """Produce deterministic UAC rows; never rely on commit-only evidence."""
    uac = uac_intel or {}
    raw_items = [str(item).strip() for item in (uac.get("acceptance_criteria") or []) if str(item).strip()]
    if not raw_items and brief.expected_behavior:
        raw_items = _split_requirement_statements(brief.expected_behavior)
    if not raw_items:
        raw_items = ["Clarify expected behaviour before final QE sign-off."]

    refs = _collect_evidence_refs(packet)
    authoritative_refs = [
        ref for ref in refs if ref.startswith(("JIRA:", "DOC:", "SPEC:", "PRE-UAC:"))
    ] or refs[:3]
    criteria: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_items[:8], 1):
        needs_clarification = "clarify" in item.lower() or not brief.expected_behavior
        category = _classify_requirement_category(item, brief)
        criteria.append(
            {
                "uac_id": f"UAC-{idx:02d}",
                "behaviour_statement": item,
                "given": _given_for_brief(brief),
                "when": _when_for_brief(brief),
                "then": _then_from_text(item),
                "priority": "P0" if idx == 1 else "P1",
                "requirement_category": category,
                "classification": _case_classification(item),
                "evidence_refs": authoritative_refs[:4],
                "derivation_classification": (
                    "HUMAN_CLARIFICATION_REQUIRED"
                    if needs_clarification
                    else "TICKET_CONFIRMED"
                    if brief.expected_behavior
                    else "REASONABLE_ASSUMPTION"
                ),
                "confidence": 35 if needs_clarification else 82 if authoritative_refs else 60,
                "assumptions": [] if brief.expected_behavior else ["Expected behaviour not explicit in Jira."],
                "open_question": (
                    _first_open_question(brief, packet)
                    if needs_clarification
                    else ""
                ),
            }
        )
    if pre_uac and pre_uac.known_product_behavior:
        criteria[0]["evidence_refs"] = list(dict.fromkeys(criteria[0]["evidence_refs"] + ["PRE-UAC:known_product_behavior"]))
    return criteria


def build_grounded_test_cases(
    packet: dict[str, Any],
    acceptance_criteria: list[dict[str, Any]],
    brief: TicketBrief,
    workflow: Any | None,
) -> list[dict[str, Any]]:
    """Generate compact traceable cases from grounded UACs only."""
    seeds = packet.get("planning_seeds") or {}
    test_areas = [str(x) for x in (seeds.get("test_area_seed") or []) if str(x).strip()]
    if not test_areas:
        test_areas = [brief.scope_hint or brief.component or "Primary AEM Guides flow"]
    cases: list[dict[str, Any]] = []
    for idx, criterion in enumerate(acceptance_criteria, 1):
        if criterion.get("derivation_classification") == "HUMAN_CLARIFICATION_REQUIRED":
            continue
        area = test_areas[(idx - 1) % len(test_areas)]
        cases.append(
            {
                "test_case_id": f"TC-{idx:02d}",
                "title": _case_title(area, criterion),
                "objective": criterion.get("behaviour_statement", ""),
                "uac_refs": [criterion.get("uac_id")],
                "evidence_refs": criterion.get("evidence_refs") or [],
                "priority": criterion.get("priority", "P1"),
                "test_level": _test_level_for_scope(brief.scope_hint or brief.component),
                "test_category": criterion.get("classification") or "functional",
                "preconditions": [criterion.get("given") or _given_for_brief(brief)],
                "controlled_test_data": _controlled_data_for_brief(brief),
                "steps": _steps_for_case(brief, criterion, area),
                "expected_result": criterion.get("then") or criterion.get("behaviour_statement"),
                "cleanup": "Remove generated test data/assets and restore Workspace Settings changed during the test.",
                "automation_suitability": _automation_suitability(packet),
                "recommended_automation_repository": _recommended_automation_repo(brief),
                "existing_automation_match": _automation_match_summary(packet),
                "assumptions": criterion.get("assumptions") or [],
                "risks": _case_risks(packet, criterion),
            }
        )
    return cases


def build_requirement_test_coverage(
    acceptance_criteria: list[dict[str, Any]],
    test_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    by_uac = {str(item.get("uac_id")): [] for item in acceptance_criteria}
    for case in test_cases:
        for ref in case.get("uac_refs") or []:
            by_uac.setdefault(str(ref), []).append(case.get("test_case_id"))
    unmapped = [uac_id for uac_id, case_ids in by_uac.items() if not case_ids]
    evidence_missing = [
        case.get("test_case_id")
        for case in test_cases
        if not case.get("evidence_refs")
    ]
    unsupported = [
        item.get("uac_id")
        for item in acceptance_criteria
        if item.get("derivation_classification") == "HUMAN_CLARIFICATION_REQUIRED"
    ]
    total = max(1, len(acceptance_criteria))
    return {
        "uac_to_tests": by_uac,
        "test_to_uacs": {
            str(case.get("test_case_id")): list(case.get("uac_refs") or []) for case in test_cases
        },
        "uac_coverage_percentage": round(((total - len(unmapped)) / total) * 100, 1),
        "critical_uac_coverage": all(
            by_uac.get(str(item.get("uac_id"))) for item in acceptance_criteria if item.get("priority") == "P0"
        ),
        "evidence_citation_coverage": round(
            (
                sum(1 for case in test_cases if case.get("evidence_refs"))
                / max(1, len(test_cases))
            )
            * 100,
            1,
        ),
        "unsupported_claim_count": len(unsupported),
        "ambiguity_count": len(unsupported),
        "duplicate_test_count": _duplicate_test_count(test_cases),
        "automation_mapping_coverage": round(
            (
                sum(1 for case in test_cases if case.get("recommended_automation_repository"))
                / max(1, len(test_cases))
            )
            * 100,
            1,
        ),
        "unmapped_uacs": unmapped,
        "tests_missing_evidence": [x for x in evidence_missing if x],
        "remaining_risks": [
            "Clarify UACs before final plan." if unsupported else "",
            "Add automation only after repository evidence confirms matching framework patterns."
            if test_cases
            else "No executable test cases generated because all UACs need clarification.",
        ],
    }


def score_pipeline_readiness(
    packet: dict[str, Any],
    uac_intel: dict[str, Any] | None,
    *,
    workflow: Any | None = None,
    human_review_threshold: int = 50,
    ticket_brief: TicketBrief | None = None,
    acceptance_criteria: list[dict[str, Any]] | None = None,
    coverage_matrix: dict[str, Any] | None = None,
) -> PipelineScore:
    blockers: list[str] = []
    warnings: list[str] = []
    human_reasons: list[str] = []
    breakdown = PipelineScoreBreakdown()
    if ticket_brief is None and packet.get("generation_mode") != "blocked":
        ticket_brief = build_ticket_brief(packet)

    gate = packet.get("uac_label_gate") or {}
    if packet.get("generation_mode") == "blocked":
        blockers.append(gate.get("blocked_reason") or "UAC_Check label missing — full RAG blocked.")
        return PipelineScore(
            overall=0,
            tier="blocked",
            human_review_required=True,
            human_review_reasons=blockers,
            blockers=blockers,
            warnings=warnings,
            breakdown=breakdown,
        )

    issue = packet.get("issue") or {}
    if str(issue.get("source") or "").lower() in {"jira_api", "live_jira"}:
        breakdown.jira_live = 20
    elif issue.get("issue_key"):
        breakdown.jira_live = 12
        warnings.append("Jira issue may be stub/cached — verify live fields before sign-off.")
    else:
        warnings.append("Jira issue payload is thin.")

    el_count = len(packet.get("experience_league_evidence") or [])
    breakdown.experience_league = min(15, el_count * 5)
    if el_count == 0:
        warnings.append("No Experience League documentation hits.")

    graph = packet.get("evidence_graph") or {}
    graph_status_value = str(graph.get("status") or "").lower()
    if packet.get("include_evidence_graph") and not graph.get("available"):
        warnings.append(
            "Evidence graph unavailable; continuing in degraded mode with direct Jira, documentation, DITA, and repository evidence."
        )
    elif graph_status_value == "degraded":
        warnings.append("Evidence graph is degraded; validate leaf sources directly before using connected findings.")

    uac = uac_intel or {}
    similar_count = len(_combined_historical_jira_evidence(packet, uac))
    breakdown.similar_jiras = min(15, similar_count * 5)
    if similar_count == 0:
        warnings.append("No similar historical Jira evidence.")

    repo_status = str(
        packet.get("repo_evidence_status")
        or (packet.get("repository_evidence") or {}).get("status")
        or ""
    ).lower()
    if repo_status == "complete":
        breakdown.repository_evidence = 15
    elif repo_status == "partial":
        breakdown.repository_evidence = 10
    else:
        warnings.append("Repository evidence missing or unavailable.")

    qs = uac.get("quality_score") or {}
    breakdown.uac_quality = int(float(qs.get("evidence_coverage") or 0) * 10) + int(
        float(qs.get("clarity_of_expectations") or 0) * 10
    )
    if float(qs.get("clarity_of_expectations") or 0) < 0.5:
        human_reasons.append("Expected behavior is unclear in Jira — PM alignment needed.")

    if gate.get("uac_done_present"):
        breakdown.uac_labels = 10
    elif gate.get("uac_check_present"):
        breakdown.uac_labels = 5
    elif gate.get("gate_skipped"):
        breakdown.uac_labels = 5
        warnings.append("UAC_Check label gate skipped for testing — add UAC_Check in production runs.")
    else:
        blockers.append("UAC_Check label missing on Jira ticket.")

    high_amb = sum(
        1 for a in (uac.get("ambiguities") or []) if str(a.get("severity") or "").lower() == "high"
    )
    breakdown.ambiguity_penalty = high_amb * 10
    if high_amb >= 2:
        human_reasons.append(f"{high_amb} high-severity ambiguities require PM/dev alignment.")

    if packet.get("mcp_fast_mode"):
        breakdown.mcp_fast_penalty = 15
        warnings.append("MCP fast mode skipped semantic RAG — run full_rag via HTTP pipeline.")

    if workflow is not None:
        overall_adjust = int(getattr(workflow, "score_bonus", 0) or 0) - int(
            getattr(workflow, "score_penalty", 0) or 0
        )
        if overall_adjust:
            warnings.append(
                f"Workflow ({getattr(workflow, 'ticket_category', 'other')}) score adjust: {overall_adjust:+d}."
            )
        for reason in getattr(workflow, "human_review_reasons", []) or []:
            if reason not in human_reasons:
                human_reasons.append(reason)

    legacy_overall = (
        breakdown.jira_live
        + breakdown.experience_league
        + breakdown.similar_jiras
        + breakdown.repository_evidence
        + breakdown.uac_quality
        + breakdown.uac_labels
        - breakdown.ambiguity_penalty
        - breakdown.mcp_fast_penalty
        + (int(getattr(workflow, "score_bonus", 0) or 0) if workflow else 0)
        - (int(getattr(workflow, "score_penalty", 0) or 0) if workflow else 0)
    )
    legacy_overall = max(0, min(100, legacy_overall))

    dimensions = build_confidence_dimensions(
        packet,
        uac_intel,
        ticket_brief=ticket_brief,
        acceptance_criteria=acceptance_criteria or [],
        coverage_matrix=coverage_matrix or {},
    )
    weighted_overall = sum(round((dim.score * dim.weight) / 100) for dim in dimensions)
    overall = max(0, min(100, weighted_overall if dimensions else legacy_overall))
    reason_codes = _score_reason_codes(packet, ticket_brief, acceptance_criteria or [], coverage_matrix or {})
    warnings.extend(_dimension_warnings(dimensions))

    mandatory_human = _mandatory_human_reasons(packet, ticket_brief, acceptance_criteria or [], coverage_matrix or {})
    for reason in mandatory_human:
        if reason not in human_reasons:
            human_reasons.append(reason)

    if blockers:
        tier = "blocked"
        human_review_required = True
        routing_status = "BLOCKED"
    elif overall < 70 or mandatory_human:
        tier = "low"
        human_review_required = True
        routing_status = "HUMAN_INPUT_REQUIRED"
        if overall < 70:
            human_reasons.append(f"Pipeline score {overall} below 70; focused clarification required.")
    elif overall < 85:
        tier = "medium"
        human_review_required = bool(human_reasons)
        routing_status = "QE_REVIEW_WITH_FLAGS"
    else:
        tier = "high"
        human_review_required = bool(human_reasons or blockers)
        routing_status = "QE_REVIEW_READY"

    return PipelineScore(
        overall=overall,
        tier=tier,  # type: ignore[arg-type]
        human_review_required=human_review_required,
        human_review_reasons=human_reasons,
        blockers=blockers,
        warnings=warnings,
        breakdown=breakdown,
        dimensions=dimensions,
        reason_codes=reason_codes,
        routing_status=routing_status,  # type: ignore[arg-type]
    )


def compose_draft_test_plan(
    packet: dict[str, Any],
    uac_intel: dict[str, Any] | None,
    score: PipelineScore,
    brief: TicketBrief,
    pre_uac: PreUacProductBrief | None = None,
    workflow: Any | None = None,
) -> str:
    from app.services.draft_test_plan_content_service import (
        build_ac_lines,
        build_blast_rows,
        build_eb_lines,
        build_historical_rows,
        build_hypothesis_rows,
        build_must_run_rows,
        build_regression_bullets,
        build_risk_rows,
        build_scenario_rows,
        build_setup_lines,
        build_step_lines,
        _scenario_table_lines,
    )
    from app.services.pre_uac_product_brief_service import render_pre_uac_markdown
    from app.services.ticket_workflow_profile_service import category_display_label

    key = str(packet.get("jira_key") or brief.jira_key)
    seeds = packet.get("planning_seeds") or {}
    uac = uac_intel or {}
    acceptance = list(uac.get("acceptance_criteria") or [])
    similar = _combined_historical_jira_evidence(packet, uac)[:5]
    test_areas = list(seeds.get("test_area_seed") or [])[:8]
    blast = list(seeds.get("blast_radius_seed") or [])[:6]
    risks = list(seeds.get("regression_risk_seed") or [])[:6]
    hypotheses = list(seeds.get("bug_hypothesis_seed") or [])[:3]

    jira_url = f"https://jira.corp.adobe.com/browse/{key}"
    customer_line = f" · {brief.customer}" if brief.customer else ""
    scope = brief.scope_hint or brief.component or "See Jira summary"
    review_note = (
        "Needs human review — pipeline score low or ambiguities open."
        if score.human_review_required
        else "Draft — refine scenarios before QE sign-off."
    )
    ticket_type = (
        category_display_label(getattr(workflow, "ticket_category", "other"))
        if workflow
        else "Unclassified"
    )
    gate_text = (
        getattr(workflow, "must_run_gate_text", None)
        or "All P0 scenarios and sign-off checks must pass on Author."
    )

    scenarios = build_scenario_rows(test_areas, workflow, pre_uac, brief)
    scenario_rows = _scenario_table_lines(scenarios)
    must_run_rows = build_must_run_rows(scenarios)
    if not must_run_rows:
        primary = getattr(workflow, "primary_scenario_title", "Primary scenario") if workflow else "Primary scenario"
        must_run_rows = [
            f"| **1** | **S-01** {primary} | Matches expected behavior from Jira |"
        ]

    setup_lines = [f"{idx}. {line}" for idx, line in enumerate(build_setup_lines(key, brief, pre_uac, workflow), 1)]
    step_lines = build_step_lines(scenarios, brief)
    ac_lines = build_ac_lines(acceptance, brief, workflow, scenarios)
    eb_lines = build_eb_lines(brief, uac, workflow, pre_uac)
    if _graph_can_influence(packet):
        for item in (packet.get("evidence_graph") or {}).get("documented_behaviors") or []:
            behavior = str(item.get("behavior") or "").strip()
            if not behavior or item.get("trust_tier") == "candidate":
                continue
            citations = [
                str(citation.get("source_ref") or citation.get("source_record_id") or "")
                for citation in (item.get("leaf_citations") or [])
                if citation.get("source_ref") or citation.get("source_record_id")
            ]
            eb_lines.append(
                f"- Documented reference: {behavior[:500]}"
                + (f" (source: {citations[0]})" if citations else "")
            )
    impact_rows = build_blast_rows(blast, scenarios, workflow, pre_uac, brief)
    risk_rows = build_risk_rows(risks, scenarios, workflow, pre_uac)
    hypothesis_rows = build_hypothesis_rows(hypotheses, scenarios, workflow, pre_uac)
    historical_rows = build_historical_rows(similar, key)
    regression_bullets = build_regression_bullets(workflow, pre_uac, brief)
    if _graph_can_influence(packet):
        for item in (packet.get("evidence_graph") or {}).get("regression_signals") or []:
            signal = str(item.get("signal") or "").strip()
            if signal and signal not in regression_bullets:
                regression_bullets.append(signal[:500])

    repo_status = str(packet.get("repo_evidence_status") or "unknown")
    diff_summary = str((packet.get("implementation_diff_evidence") or {}).get("summary_line") or "unknown")
    release_conf = "Low" if score.overall < 50 else "Medium" if score.overall < 75 else "Medium-High"

    pre_uac_block = ""
    if pre_uac:
        pre_uac_block = render_pre_uac_markdown(pre_uac, workflow) + "\n---\n\n"

    expected_summary = brief.expected_behavior[:500] if brief.expected_behavior else (
        "See Jira Expected Result — PM alignment pending."
        if workflow and getattr(workflow, "ticket_category", "") == "feature_request"
        else "See Jira Expected Result."
    )

    lines = [
        f"# Test Plan: {key} — {brief.summary or 'AEM Guides ticket'}",
        "",
        f"**Jira:** [{key}]({jira_url}){customer_line}",
        f"**Type:** {ticket_type}",
        f"**Scope:** {scope}",
        f"**Plan status:** {review_note}",
        "",
        "---",
        "",
        pre_uac_block,
        "## 1. Action items (QA — start here)",
        "",
        "### Setup (one time)",
        "",
        *setup_lines,
        "",
        "### Must run before release",
        "",
        f"**Gate:** {gate_text}",
        "",
        "| Run first | Scenario | Pass if |",
        "| --- | --- | --- |",
        *must_run_rows,
        "",
        "### Test list (priority order)",
        "",
        "| Scenario ID | Priority | Title | Links to | How to verify |",
        "| --- | --- | --- | --- | --- |",
        *scenario_rows,
        "",
        "### Steps for P0 / P1 tests",
        "",
        *step_lines,
        "",
        "### Sign-off checks (acceptance from Jira / UAC)",
        "",
        *ac_lines,
        "",
        f"**Pipeline score:** {score.overall}/100 ({score.tier}) — "
        + ("human review required before QE sign-off." if score.human_review_required else "proceed with QE review."),
        "",
        "---",
        "",
        "## 2. Supplementary — context, risks & traceability",
        "",
        "### Summary & expected behaviour",
        "",
        f"- **Issue ({ticket_type}):** {brief.summary or 'See Jira.'}",
        f"- **Current behavior:** {brief.current_behavior[:500] or 'See Jira Actual Result.'}",
        f"- **Expected behavior:** {expected_summary}",
        "",
        "**Expected behaviour (reference):**",
        "",
        *eb_lines,
        "",
        "### What can break & risks",
        "",
        "**Code path:** See repository evidence and diff summary in full RAG packet.",
        "",
        "| Area | Impact | Why | Test / skip |",
        "| --- | --- | --- | --- |",
        *impact_rows,
        "",
        "| Risk ID | Priority | What goes wrong | Test / skip |",
        "| --- | --- | --- | --- |",
        *risk_rows,
        "",
        "**Likely bugs to watch:**",
        "",
        "| ID | What we suspect | How you'd notice | Test |",
        "| --- | --- | --- | --- |",
        *hypothesis_rows,
        "",
        "### Must not break (regression checks)",
        "",
        *[f"- {item}" for item in regression_bullets],
        "",
        "### Related past Jiras",
        "",
        "| Jira | What happened | Why it matters here | Test |",
        "| --- | --- | --- | --- |",
        *historical_rows,
        "",
        "### Automation coverage",
        "",
        "| Check | Where | Coverage | Gap |",
        "| --- | --- | --- | --- |",
        f"| Repo scan | starling / dxml-it-tests | {repo_status} | See full RAG packet |",
        "",
        "### Where we got the facts (evidence)",
        "",
        f"- **Jira:** [{key}]({jira_url})",
        f"- **Full RAG packet:** `docs/qa/test-plans/{key}-full-rag-packet.md`",
        f"- **Repo evidence status:** {repo_status}",
        f"- **Diff summary:** {diff_summary}",
        "",
        "### Evidence & release status",
        "",
        f"- **Release confidence:** {release_conf} until P0 scenarios pass on Author.",
        f"- **Review status:** Draft",
        "",
    ]
    return "\n".join(lines) + "\n"


def build_confidence_dimensions(
    packet: dict[str, Any],
    uac_intel: dict[str, Any] | None,
    *,
    ticket_brief: TicketBrief | None,
    acceptance_criteria: list[dict[str, Any]],
    coverage_matrix: dict[str, Any],
) -> list[ConfidenceDimension]:
    issue = packet.get("issue") or {}
    docs = packet.get("experience_league_evidence") or []
    learned = packet.get("learned_behavior_evidence") or {}
    repo = packet.get("repository_evidence") or {}
    repo_status = str(packet.get("repo_evidence_status") or repo.get("status") or "").lower()
    uac = uac_intel or {}
    similar = uac.get("similar_jira_evidence") or []
    contradictions = _detect_ticket_contradictions(ticket_brief, packet) if ticket_brief else []
    fields_present = sum(
        1
        for value in (
            getattr(ticket_brief, "summary", ""),
            getattr(ticket_brief, "component", ""),
            getattr(ticket_brief, "current_behavior", ""),
            getattr(ticket_brief, "expected_behavior", ""),
            getattr(ticket_brief, "priority", ""),
        )
        if value
    )
    ticket_score = int((fields_present / 5) * 100)
    retrieval_sources = int(bool(docs)) + int(bool((learned or {}).get("results"))) + int(bool(similar))
    retrieval_score = min(100, retrieval_sources * 30 + min(len(docs), 4) * 5)
    coverage_refs = _collect_evidence_refs(packet)
    evidence_score = min(100, len(set(coverage_refs)) * 12 + (20 if repo_status in {"complete", "partial"} else 0))
    consistency_score = max(0, 100 - len(contradictions) * 35)
    cited_uacs = sum(1 for row in acceptance_criteria if row.get("evidence_refs"))
    testable_uacs = sum(
        1
        for row in acceptance_criteria
        if row.get("then") and row.get("derivation_classification") != "HUMAN_CLARIFICATION_REQUIRED"
    )
    uac_total = max(1, len(acceptance_criteria))
    uac_score = int(((cited_uacs + testable_uacs) / (uac_total * 2)) * 100)
    trace_score = int(
        (
            float(coverage_matrix.get("uac_coverage_percentage") or 0)
            + float(coverage_matrix.get("evidence_citation_coverage") or 0)
        )
        / 2
    )

    return [
        ConfidenceDimension(
            name="ticket_completeness",
            weight=15,
            score=ticket_score,
            signals=[f"{fields_present}/5 core ticket fields present"],
            evidence_refs=[f"JIRA:{issue.get('issue_key') or packet.get('jira_key')}"],
            deductions=[] if ticket_score >= 80 else ["Ticket missing one or more of component/current/expected/priority."],
            missing_information=(build_enhanced_ticket_analysis(packet, ticket_brief).get("missing_information") if ticket_brief else []),
            recommended_action="Complete Jira Expected/Actual/component fields before final QE sign-off."
            if ticket_score < 80
            else "Ticket fields are adequate.",
        ),
        ConfidenceDimension(
            name="retrieval_quality",
            weight=20,
            score=retrieval_score,
            signals=[
                f"Experience League hits={len(docs)}",
                f"learned behavior hits={len((learned or {}).get('results') or [])}",
                f"similar Jira hits={len(similar)}",
            ],
            evidence_refs=coverage_refs[:8],
            deductions=[] if retrieval_score >= 70 else ["Weak or missing RAG source diversity."],
            recommended_action="Run full VM RAG retrieval or add UAC_Check if semantic evidence is blocked."
            if retrieval_score < 70
            else "Retrieval is sufficiently diverse.",
        ),
        ConfidenceDimension(
            name="evidence_coverage",
            weight=20,
            score=evidence_score,
            signals=[f"evidence refs={len(set(coverage_refs))}", f"repo_status={repo_status or 'unknown'}"],
            evidence_refs=coverage_refs[:10],
            deductions=[] if evidence_score >= 75 else ["Important claims lack authoritative Jira/doc/repo evidence."],
            recommended_action="Add authoritative docs/repo evidence for every P0/P1 claim."
            if evidence_score < 75
            else "Evidence covers the main claims.",
        ),
        ConfidenceDimension(
            name="evidence_consistency",
            weight=10,
            score=consistency_score,
            signals=[f"conflicts={len(contradictions)}"],
            evidence_refs=coverage_refs[:5],
            deductions=contradictions,
            recommended_action="Resolve conflicting expected/current behavior before sign-off."
            if contradictions
            else "No deterministic conflict detected.",
        ),
        ConfidenceDimension(
            name="uac_groundedness_testability",
            weight=20,
            score=uac_score,
            signals=[f"cited_uacs={cited_uacs}", f"testable_uacs={testable_uacs}", f"total_uacs={uac_total}"],
            evidence_refs=coverage_refs[:8],
            deductions=[] if uac_score >= 80 else ["Some UACs are uncited, unclear, or not externally observable."],
            recommended_action="Clarify or remove unsupported UACs before generating final cases."
            if uac_score < 80
            else "UACs are grounded and testable.",
        ),
        ConfidenceDimension(
            name="requirement_traceability",
            weight=15,
            score=trace_score,
            signals=[
                f"uac_coverage={coverage_matrix.get('uac_coverage_percentage', 0)}",
                f"evidence_citation_coverage={coverage_matrix.get('evidence_citation_coverage', 0)}",
            ],
            evidence_refs=coverage_refs[:8],
            deductions=[] if trace_score >= 85 else ["Some UACs/tests are unmapped or missing evidence."],
            missing_information=list(coverage_matrix.get("unmapped_uacs") or []),
            recommended_action="Map every UAC to at least one test or evidence-backed exclusion."
            if trace_score < 85
            else "Traceability is adequate.",
        ),
    ]


def build_qe_review_package(
    jira_key: str,
    correlation_id: str,
    packet: dict[str, Any],
    ticket_analysis: dict[str, Any],
    acceptance_criteria: list[dict[str, Any]],
    test_cases: list[dict[str, Any]],
    coverage_matrix: dict[str, Any],
    score: PipelineScore,
    qe_handoff: QeHandoff,
    validation: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "review_id": f"QE-{jira_key}-{correlation_id[:8]}",
        "review_status": qe_handoff.review_status,
        "reviewer_assignment": qe_handoff.assignee_hint,
        "approve_action": "QE_APPROVED",
        "request_changes_action": "QE_CHANGES_REQUESTED",
        "revision": 1,
        "revision_history": [],
        "ticket_analysis": ticket_analysis,
        "evidence_snapshot": {
            "rag_packet_summary": summarize_rag_packet(packet),
            "repository_evidence_status": packet.get("repo_evidence_status"),
            "diff_evidence_status": packet.get("diff_evidence_status"),
        },
        "acceptance_criteria": acceptance_criteria,
        "test_cases": test_cases,
        "coverage_matrix": coverage_matrix,
        "dimension_scores": [dim.model_dump() for dim in score.dimensions],
        "overall_score": score.overall,
        "score_deductions": [ded for dim in score.dimensions for ded in dim.deductions],
        "assumptions": [a for row in acceptance_criteria for a in (row.get("assumptions") or [])],
        "unresolved_risks": coverage_matrix.get("remaining_risks") or [],
        "prompt_version": "aem-guides-test-plan-pipeline-v2",
        "model_version": os.getenv("LLM_MODEL") or os.getenv("ANTHROPIC_MODEL") or "configured-runtime",
        "retrieval_configuration": {
            "evidence_k": len(packet.get("experience_league_evidence") or []),
            "mcp_fast_mode": packet.get("mcp_fast_mode"),
            "generation_mode": packet.get("generation_mode"),
            "uac_label_gate": packet.get("uac_label_gate"),
        },
        "validation": validation or {},
        "traceability": coverage_matrix,
    }


def build_qe_handoff(
    jira_key: str,
    packet: dict[str, Any],
    uac_intel: dict[str, Any] | None,
    score: PipelineScore,
    brief: TicketBrief,
    draft_md: str | None,
    validation: dict[str, Any] | None,
    workflow: Any | None = None,
    pre_uac: PreUacProductBrief | None = None,
) -> QeHandoff:
    from app.services.draft_test_plan_content_service import build_scenario_rows
    from app.services.ticket_workflow_profile_service import category_display_label

    uac = uac_intel or {}
    test_areas = list((packet.get("planning_seeds") or {}).get("test_area_seed") or [])
    scenarios = build_scenario_rows(test_areas, workflow, pre_uac, brief)
    p0_ids = [s.scenario_id for s in scenarios if str(s.priority).startswith("P0")][:6]
    if not p0_ids:
        p0_ids = [f"S-{i:02d}" for i in range(1, 4)]
    pm_q = [str(q) for q in (uac.get("pm_questions") or [])[:5]]
    qa_q = [str(q) for q in (uac.get("qa_questions") or [])[:5]]
    blocking: list[str] = list(score.blockers)
    if score.human_review_required:
        blocking.extend(score.human_review_reasons)
    if validation and not validation.get("valid"):
        blocking.append("Draft test plan failed validator — agent/QE must refine.")

    if score.tier == "blocked":
        review_status = "Needs human review"
    elif score.human_review_required:
        review_status = "Needs human review"
    elif draft_md:
        review_status = "Ready for QE review"
    else:
        review_status = "Draft"

    artifact_paths = {
        "full_rag_packet": f"docs/qa/test-plans/{jira_key}-full-rag-packet.md",
        "pipeline_draft": f"docs/qa/test-plans/{jira_key}-test-plan-pipeline-draft.md",
        "test_plan": f"docs/qa/test-plans/{jira_key}-test-plan.md",
        "test_data": f"docs/qa/test-data/{jira_key}/",
    }

    next_actions: list[str] = []
    if workflow is not None:
        cat = category_display_label(getattr(workflow, "ticket_category", "other"))
        next_actions.append(f"Confirm ticket type ({cat}) with PM if confidence is low.")
    if score.blockers:
        next_actions.append("Add UAC_Check label on Jira, then re-run pipeline.")
    if score.human_review_required:
        if workflow and getattr(workflow, "ticket_category", "") == "feature_request":
            next_actions.append("Route PM questions — agree Expected Result before UAC sign-off.")
        elif workflow and getattr(workflow, "ticket_category", "") == "bug":
            next_actions.append("Confirm repro steps and Actual Result on Author before locking AC.")
        else:
            next_actions.append("Route PM/QA questions to product owner before finalizing AC.")
    next_actions.append(f"QE: run must-run scenarios ({', '.join(p0_ids)}) on Author.")
    next_actions.append("Update test-plans-registry.json after plan is approved.")
    if review_status == "Ready for QE review":
        next_actions.append("Publish to team UI via POST /api/v1/test-plans or publish_test_plan MCP.")

    return QeHandoff(
        review_status=review_status,  # type: ignore[arg-type]
        must_run_before_release=p0_ids,
        pm_questions=pm_q,
        qa_questions=qa_q,
        blocking_gaps=blocking[:8],
        artifact_paths=artifact_paths,
        next_actions=next_actions,
    )


def summarize_rag_packet(packet: dict[str, Any]) -> dict[str, Any]:
    graph = packet.get("evidence_graph") or {}
    return {
        "generation_mode": packet.get("generation_mode"),
        "mcp_fast_mode": packet.get("mcp_fast_mode"),
        "repo_evidence_status": packet.get("repo_evidence_status"),
        "diff_evidence_status": packet.get("diff_evidence_status"),
        "experience_league_hits": len(packet.get("experience_league_evidence") or []),
        "learned_behavior_available": bool((packet.get("learned_behavior_evidence") or {}).get("available")),
        "planning_seed_counts": {
            k: len((packet.get("planning_seeds") or {}).get(k) or [])
            for k in (
                "blast_radius_seed",
                "bug_hypothesis_seed",
                "test_area_seed",
                "regression_risk_seed",
            )
        },
        "uac_label_gate": packet.get("uac_label_gate"),
        "evidence_graph": {
            "status": graph.get("status"),
            "available": bool(graph.get("available")),
            "influence_mode": packet.get("evidence_graph_influence_mode", "shadow"),
            "used_for_plan": _graph_can_influence(packet),
            "generation_id": (graph.get("generation") or {}).get("id"),
            "path_count": len(graph.get("evidence_paths") or []),
            "leaf_citation_count": len(
                {
                    citation.get("leaf_id")
                    for path in (graph.get("evidence_paths") or [])
                    for citation in (path.get("leaf_citations") or [])
                    if citation.get("leaf_id")
                }
            ),
            "coverage_gaps": list(graph.get("coverage_gaps") or [])[:10],
            "query_runtime": graph.get("query_runtime") or {},
            "evaluation": packet.get("evidence_graph_evaluation") or {},
        },
    }


def write_starling_artifacts(
    starling_root: Path,
    jira_key: str,
    packet: dict[str, Any],
    uac_intel: dict[str, Any] | None,
    draft_md: str | None,
    qe_handoff: QeHandoff,
    pre_uac_brief: PreUacProductBrief | None = None,
    workflow: Any | None = None,
) -> list[str]:
    written: list[str] = []
    plans_dir = starling_root / "docs" / "qa" / "test-plans"
    plans_dir.mkdir(parents=True, exist_ok=True)

    rag_md = render_guides_test_plan_packet_markdown(packet)
    rag_path = plans_dir / f"{jira_key}-full-rag-packet.md"
    rag_path.write_text(rag_md, encoding="utf-8")
    written.append(str(rag_path))

    pipeline_json = {
        "jira_key": jira_key,
        "ticket_workflow": (_workflow_summary(workflow).model_dump() if workflow else None),
        "qe_handoff": qe_handoff.model_dump(),
        "pre_uac_product_brief": (pre_uac_brief.model_dump() if pre_uac_brief else None),
        "uac_intelligence": uac_intel,
        "rag_packet_summary": summarize_rag_packet(packet),
    }
    meta_path = plans_dir / f"{jira_key}-pipeline-result.json"
    meta_path.write_text(json.dumps(pipeline_json, indent=2, default=str), encoding="utf-8")
    written.append(str(meta_path))

    if draft_md:
        draft_path = plans_dir / f"{jira_key}-test-plan-pipeline-draft.md"
        draft_path.write_text(draft_md, encoding="utf-8")
        written.append(str(draft_path))

    return written


def validate_test_plan_markdown(markdown: str) -> dict[str, Any]:
    if not _VALIDATOR.is_file():
        return {"valid": False, "errors": ["Validator script not found."], "output": ""}
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as tmp:
        tmp.write(markdown)
        tmp_path = tmp.name
    try:
        completed = subprocess.run(
            [sys.executable, str(_VALIDATOR), tmp_path],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        errors = [
            line.replace("ERROR: ", "").strip()
            for line in output.splitlines()
            if line.startswith("ERROR:")
        ]
        return {"valid": completed.returncode == 0, "errors": errors, "output": output.strip()}
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def render_pipeline_result_markdown(result: TestPlanPipelineResult) -> str:
    """Human-readable summary for MCP tool responses."""
    brief = result.ticket_brief
    score = result.score
    qe = result.qe_handoff
    pre_uac = result.pre_uac_product_brief
    lines = [
        f"# Test Plan Pipeline — {result.jira_key}",
        "",
        f"**Score:** {score.overall}/100 ({score.tier}) · "
        f"**Human review:** {'Yes' if score.human_review_required else 'No'} · "
        f"**QE status:** {qe.review_status}",
        f"**Stages:** {', '.join(result.stages_completed)} · **Elapsed:** {result.elapsed_ms}ms",
        "",
        "## Ticket brief",
        "",
        f"- **Summary:** {brief.summary}",
        f"- **Component / scope:** {brief.component or brief.scope_hint}",
        f"- **Current:** {brief.current_behavior[:300] or '—'}",
        f"- **Expected:** {brief.expected_behavior[:300] or '—'}",
        "",
    ]
    wf = result.ticket_workflow
    if wf:
        from app.services.ticket_workflow_profile_service import category_display_label

        lines.extend(
            [
                "## Ticket workflow",
                "",
                f"- **Type:** {category_display_label(wf.ticket_category)} "
                f"(Jira issue type: {wf.jira_issue_type or 'n/a'} · confidence: {wf.confidence})",
                f"- **Focus:** {wf.pre_uac_focus[:300]}",
                "",
            ]
        )
    if pre_uac:
        lines.extend(
            [
                "## Pre-UAC — product context",
                "",
                f"- **Area:** {pre_uac.primary_product_area}",
                f"- **What it is:** {pre_uac.summary_plain_english[:400]}",
            ]
        )
        if pre_uac.how_it_works:
            lines.extend(["", "**How users reach it:**", ""])
            lines.extend(f"- {item}" for item in pre_uac.how_it_works[:4])
        if pre_uac.known_product_behavior:
            lines.extend(["", "**Known product behavior (curated):**", ""])
            lines.extend(f"- {item}" for item in pre_uac.known_product_behavior[:4])
        if pre_uac.pre_uac_clarifications:
            lines.extend(["", "**Clarifications before UAC:**", ""])
            lines.extend(f"- {q}" for q in pre_uac.pre_uac_clarifications[:5])
        lines.append("")
    lines.extend(
        [
            "## Score breakdown",
            "",
            f"- Jira: +{score.breakdown.jira_live}",
            f"- Experience League: +{score.breakdown.experience_league}",
            f"- Similar Jiras: +{score.breakdown.similar_jiras}",
            f"- Repository evidence: +{score.breakdown.repository_evidence}",
            f"- UAC quality: +{score.breakdown.uac_quality}",
            f"- UAC labels: +{score.breakdown.uac_labels}",
            f"- Ambiguity penalty: -{score.breakdown.ambiguity_penalty}",
            f"- MCP fast penalty: -{score.breakdown.mcp_fast_penalty}",
            "",
        ]
    )
    if score.dimensions:
        lines.extend(["**Deterministic confidence dimensions:**", ""])
        for dim in score.dimensions:
            lines.append(f"- **{dim.name}:** {dim.score}/100 (weight {dim.weight}%)")
        lines.append("")
    if result.coverage_matrix:
        lines.extend(
            [
                "## Requirement-to-test traceability",
                "",
                f"- UAC coverage: {result.coverage_matrix.get('uac_coverage_percentage', 0)}%",
                f"- Evidence citation coverage: {result.coverage_matrix.get('evidence_citation_coverage', 0)}%",
                f"- Unsupported claims: {result.coverage_matrix.get('unsupported_claim_count', 0)}",
                "",
            ]
        )
    if result.acceptance_criteria:
        lines.extend(["## Grounded sign-off checks", ""])
        for row in result.acceptance_criteria[:5]:
            lines.append(f"- **{row.get('uac_id')}:** {row.get('then') or row.get('behaviour_statement')}")
        lines.append("")
    if score.blockers:
        lines.extend(["**Blockers:**", *[f"- {b}" for b in score.blockers], ""])
    if score.warnings:
        lines.extend(["**Warnings:**", *[f"- {w}" for w in score.warnings[:8]], ""])
    if qe.pm_questions:
        lines.extend(["## PM questions", "", *[f"- {q}" for q in qe.pm_questions], ""])
    if qe.qa_questions:
        lines.extend(["## QA questions", "", *[f"- {q}" for q in qe.qa_questions], ""])
    lines.extend(["## QE next actions", "", *[f"- {a}" for a in qe.next_actions], ""])
    if result.artifacts_written:
        lines.extend(["## Artifacts written", "", *[f"- `{p}`" for p in result.artifacts_written], ""])
    if result.draft_test_plan_markdown:
        lines.extend(
            [
                "",
                "---",
                "",
                "## Draft test plan (preview — first 80 lines)",
                "",
                "```markdown",
                *result.draft_test_plan_markdown.splitlines()[:80],
                "...",
                "```",
            ]
        )
    return "\n".join(lines)


def _fallback_uac_from_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Derive minimal UAC-shaped JSON from the RAG packet when live UAC orchestrator is unavailable."""
    issue = packet.get("issue") or {}
    expected = str(issue.get("expected_behavior") or issue.get("expected_result") or "").strip()
    actual = str(issue.get("actual_behavior") or issue.get("actual_result") or "").strip()
    acceptance: list[str] = []
    if expected:
        acceptance.append(expected[:400])
    if actual and len(acceptance) < 2:
        acceptance.append(f"Repro fails with: {actual[:200]}")
    if not acceptance:
        acceptance.append("Define acceptance from Jira Expected Result after PM review.")

    similar = []
    for item in (packet.get("planning_seeds") or {}).get("regression_risk_seed") or []:
        candidate_key = str(item.get("id") or "").strip().upper() if isinstance(item, dict) else ""
        if _JIRA_KEY_RE.fullmatch(candidate_key):
            similar.append(
                {
                    "jira_key": candidate_key,
                    "why_similar": str(item.get("rationale") or "")[:120],
                    "evidence_origin": "planning_seed",
                    "evidence_refs": [f"JIRA:{candidate_key}"],
                }
            )
    similar = _combined_historical_jira_evidence(
        packet,
        {"similar_jira_evidence": similar},
    )

    clarity = 0.85 if expected else 0.35
    return {
        "acceptance_criteria": acceptance,
        "similar_jira_evidence": similar[:5],
        "ambiguities": [] if expected else [{"severity": "high", "topic": "Expected behavior missing on Jira"}],
        "quality_score": {"evidence_coverage": 0.4, "clarity_of_expectations": clarity},
        "pm_questions": ["Confirm expected behavior and scope boundaries with PM."] if not expected else [],
        "qa_questions": ["Which Author environment and test data path should QE use?"],
        "warnings": ["UAC orchestrator unavailable — using RAG packet fallback."],
    }


def _workflow_summary(workflow: Any) -> TicketWorkflowProfileSummary:
    return TicketWorkflowProfileSummary(
        ticket_category=getattr(workflow, "ticket_category", "other"),
        jira_issue_type=getattr(workflow, "jira_issue_type", "") or "",
        confidence=getattr(workflow, "confidence", "medium"),
        detection_signals=list(getattr(workflow, "detection_signals", []) or [])[:8],
        pre_uac_focus=getattr(workflow, "pre_uac_focus", "") or "",
        must_run_gate_text=getattr(workflow, "must_run_gate_text", "") or "",
    )


def _resolve_starling_path(override: str | None) -> Path:
    raw = (override or os.getenv("STARLING_REPO_PATH") or "C:/starling").strip()
    return Path(raw)


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            for item in value:
                text = str(item).strip()
                if text:
                    return text
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _extract_customer(issue: dict[str, Any]) -> str | None:
    for key in ("customer", "customer_name", "account"):
        val = issue.get(key)
        if val:
            return str(val).strip()
    custom = issue.get("custom_fields") or {}
    if isinstance(custom, dict):
        for key in ("customer", "Customer", "customfield_customer"):
            if custom.get(key):
                return str(custom[key]).strip()
    return None


def _extract_component_from_text(summary: str, description: str) -> str:
    text = f"{summary}\n{description}".lower()
    hints = (
        ("asset status", "REST — Asset Status API"),
        ("/bin/guides", "REST API"),
        ("web editor", "Web Editor"),
        ("publishing", "Publishing"),
        ("folder profile", "Folder Profile"),
        ("translation", "Translation"),
    )
    for needle, label in hints:
        if needle in text:
            return label
    return ""


def _extract_field(text: str, markers: tuple[str, ...]) -> str:
    lines = [line.strip(" \t•*-") for line in str(text or "").splitlines()]
    heading_markers = {
        "customer context",
        "request type",
        "problem / business need",
        "problem",
        "business need",
        "current behavior",
        "current behaviour",
        "actual behavior",
        "actual behaviour",
        "requested enhancement",
        "expected behavior",
        "expected behaviour",
        "expected result",
        "business impact",
        "support investigation summary",
        "attachments / references",
        "next steps requested from engineering",
        "steps to reproduce",
        "environment",
    }
    normalized_markers = tuple(marker.lower() for marker in markers)
    for idx, line in enumerate(lines):
        lowered = line.lower().rstrip(":")
        matched_marker = next(
            (marker for marker in normalized_markers if marker in lowered),
            "",
        )
        if not matched_marker:
            continue
        after_heading = re.sub(
            rf"(?i)^\s*{re.escape(matched_marker)}\s*:?\s*",
            "",
            line,
        ).strip()
        collected: list[str] = [after_heading] if after_heading else []
        for next_line in lines[idx + 1 :]:
            cleaned = next_line.strip()
            if not cleaned:
                if collected:
                    break
                continue
            normalized = cleaned.lower().rstrip(":")
            if normalized in heading_markers:
                break
            if any(normalized == marker for marker in normalized_markers):
                break
            collected.append(cleaned)
            if len(" ".join(collected)) >= 900:
                break
        value = " ".join(part for part in collected if part).strip()
        if value:
            return value[:1000].rstrip()
    return ""


def _split_requirement_statements(text: str) -> list[str]:
    """Split dense Jira expected/requested behavior into testable UAC statements."""
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if not normalized:
        return []
    parts = [
        part.strip(" ;.")
        for part in re.split(r"(?<=[.!?])\s+|;\s+|\s+where applicable[,.]?\s*", normalized)
        if part.strip(" ;.")
    ]
    expanded: list[str] = []
    for part in parts:
        subparts = re.split(r"(?i)\.\s*allow similar treatment|\.\s*column should|\.\s*solution must", part)
        if len(subparts) > 1:
            expanded.extend(piece.strip(" ;.") for piece in subparts if piece.strip(" ;."))
        else:
            expanded.append(part)
    return list(dict.fromkeys(expanded))[:8] or [normalized]


def _infer_scope(summary: str, description: str) -> str:
    combined = f"{summary}\n{description}"
    match = re.search(r"/bin/[^\s\"'<>]+", combined, re.I)
    if match:
        return f"REST — {match.group(0)}"
    return _extract_component_from_text(summary, description)


def _summarize_text(summary: str, description: str, *, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", f"{summary}. {description}".strip())
    return text[:max_chars].rstrip()


def _extract_error_messages(text: str) -> list[str]:
    patterns = (
        r"(?i)(URLDecoder:[^\n\r]+)",
        r"(?i)(Exception[^\n\r]{0,180})",
        r"(?i)(Error[:\s][^\n\r]{0,180})",
        r"(?i)(failed[^\n\r]{0,180})",
    )
    out: list[str] = []
    for pattern in patterns:
        out.extend(match.strip() for match in re.findall(pattern, text or "") if str(match).strip())
    return list(dict.fromkeys(out))[:8]


def _extract_steps(text: str) -> list[str]:
    lines = [line.strip(" -*\t") for line in str(text or "").splitlines()]
    step_lines = [
        line
        for line in lines
        if line
        and (
            re.match(r"^\d+[\).]\s+", line)
            or line.lower().startswith(("open ", "click ", "send ", "observe ", "prepare ", "enable ", "use "))
        )
    ]
    return step_lines[:10]


def _detect_ticket_contradictions(brief: TicketBrief | None, packet: dict[str, Any]) -> list[str]:
    if not brief:
        return []
    contradictions: list[str] = []
    if brief.current_behavior and brief.expected_behavior and brief.current_behavior.strip() == brief.expected_behavior.strip():
        contradictions.append("Current behaviour and expected behaviour are identical.")
    if packet.get("diff_evidence_status") == "available" and not brief.expected_behavior:
        contradictions.append("Implementation diff exists but product expected behaviour is missing.")
    return contradictions


def _build_open_questions(brief: TicketBrief, packet: dict[str, Any], missing: list[str]) -> list[str]:
    questions: list[str] = []
    if "Expected behaviour" in missing:
        questions.append(
            f"What exact observable result should QE accept for `{brief.summary or brief.jira_key}`?"
        )
    if "Current behaviour / Actual result" in missing:
        questions.append("What exact failing response, UI message, log line, or persisted state reproduces the issue?")
    if _is_customer_production(packet, brief):
        questions.append("What response-time, memory, data-size, or environment threshold should QE use for the production/customer case?")
    return questions[:5]


def _first_open_question(brief: TicketBrief, packet: dict[str, Any]) -> str:
    missing = build_enhanced_ticket_analysis(packet, brief).get("missing_information") or []
    questions = _build_open_questions(brief, packet, list(missing))
    return questions[0] if questions else ""


def _graph_can_influence(packet: dict[str, Any]) -> bool:
    if str(packet.get("evidence_graph_influence_mode") or "shadow").strip().lower() != "augment":
        return False
    evaluation = packet.get("evidence_graph_evaluation") or {}
    if evaluation and not bool(evaluation.get("used_for_plan")):
        return False
    return bool((packet.get("evidence_graph") or {}).get("available"))


def _collect_evidence_refs(packet: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    key = str(packet.get("jira_key") or (packet.get("issue") or {}).get("issue_key") or "")
    if key:
        refs.append(f"JIRA:{key}")
    for doc in packet.get("experience_league_evidence") or []:
        url = doc.get("source_url") or doc.get("canonical_url") or doc.get("url")
        if url:
            refs.append(f"DOC:{_canonical_url(str(url))}")
    for doc in (packet.get("learned_behavior_evidence") or {}).get("results") or []:
        url = doc.get("source_url") or doc.get("canonical_url") or doc.get("url")
        if url:
            refs.append(f"DOC:{_canonical_url(str(url))}")
    for doc in packet.get("dita_spec_evidence") or []:
        url = doc.get("url") or doc.get("source_url")
        stable_source = _canonical_url(str(url)) if url else str(doc.get("chunk_id") or doc.get("title") or "")
        if stable_source:
            refs.append(f"SPEC:{stable_source}")
    repo = packet.get("repository_evidence") or {}
    for repo_row in repo.get("repositories") or []:
        for match in (repo_row.get("matches") or [])[:3]:
            path = match.get("path")
            if path:
                refs.append(f"REPO:{repo_row.get('id')}:{path}:{match.get('line', '')}")
    if _graph_can_influence(packet):
        for path in (packet.get("evidence_graph") or {}).get("evidence_paths") or []:
            for citation in path.get("leaf_citations") or []:
                if citation.get("trust_tier") == "candidate":
                    continue
                evidence_ref = _citation_evidence_ref(citation)
                if evidence_ref:
                    refs.append(evidence_ref)
    return list(dict.fromkeys(refs))


def _canonical_url(value: str) -> str:
    text = str(value or "").strip()
    if not text.startswith(("http://", "https://")):
        return text
    parsed = urlsplit(text)
    normalized_path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), normalized_path, parsed.query, ""))


def _citation_evidence_ref(citation: dict[str, Any]) -> str:
    source_ref = str(citation.get("source_ref") or "").strip()
    source_kind = str(citation.get("source_type") or "").strip()
    source_chunk = str(citation.get("source_chunk_id") or "").strip()
    source_record = str(citation.get("source_record_id") or "").strip()
    if _JIRA_KEY_RE.fullmatch(source_ref.upper()):
        return f"JIRA:{source_ref.upper()}"
    if source_ref.startswith(("http://", "https://")):
        prefix = "SPEC" if source_kind.startswith("dita_spec") else "DOC"
        return f"{prefix}:{_canonical_url(source_ref)}"
    if source_chunk:
        return f"CHUNK:{source_kind}:{source_chunk}"
    if source_record:
        return f"SOURCE:{source_kind}:{source_record}"
    return ""


def _combined_historical_jira_evidence(
    packet: dict[str, Any],
    uac_intel: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    current_key = str(packet.get("jira_key") or "").strip().upper()
    candidates: list[dict[str, Any]] = []
    for item in (uac_intel or {}).get("similar_jira_evidence") or []:
        if isinstance(item, dict):
            candidates.append({**item, "evidence_origin": item.get("evidence_origin") or "uac_intelligence"})
    searches = packet.get("jira_history_searches") or {}
    for scope in ("same_customer", "cross_customer"):
        for item in (searches.get(scope) or {}).get("results") or []:
            if isinstance(item, dict):
                candidates.append(
                    {
                        **item,
                        "search_scope": scope,
                        "evidence_origin": "search_jira_history",
                    }
                )
    if _graph_can_influence(packet):
        for item in (packet.get("evidence_graph") or {}).get("same_mechanism_jira_history") or []:
            if not isinstance(item, dict):
                continue
            graph_refs = [
                ref
                for ref in (_citation_evidence_ref(citation) for citation in item.get("leaf_citations") or [])
                if ref
            ]
            candidates.append(
                {
                    **item,
                    "why_similar": item.get("why_similar")
                    or "Shared mechanism: " + ", ".join(item.get("shared_mechanisms") or []),
                    "evidence_origin": "evidence_graph",
                    "evidence_refs": graph_refs,
                }
            )

    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in candidates:
        jira_key = str(item.get("jira_key") or "").strip().upper()
        if not _JIRA_KEY_RE.fullmatch(jira_key) or jira_key == current_key:
            continue
        evidence_refs = [str(ref) for ref in item.get("evidence_refs") or [] if str(ref).strip()]
        evidence_refs.append(f"JIRA:{jira_key}")
        origin = str(item.get("evidence_origin") or "unknown")
        if jira_key not in merged:
            merged[jira_key] = {
                **item,
                "jira_key": jira_key,
                "evidence_origins": [origin],
                "evidence_refs": list(dict.fromkeys(evidence_refs)),
            }
            order.append(jira_key)
            continue
        existing = merged[jira_key]
        existing["evidence_origins"] = list(
            dict.fromkeys([*(existing.get("evidence_origins") or []), origin])
        )
        existing["evidence_refs"] = list(
            dict.fromkeys([*(existing.get("evidence_refs") or []), *evidence_refs])
        )
        for field in ("summary", "why_similar", "root_cause", "qa_oracle", "historical_outcome"):
            if not existing.get(field) and item.get(field):
                existing[field] = item[field]
    return [merged[jira_key] for jira_key in order]


def _classify_requirement_category(text: str, brief: TicketBrief) -> str:
    lowered = f"{text} {brief.scope_hint} {brief.component}".lower()
    if any(token in lowered for token in ("memory", "600", "large", "performance", "scale")):
        return "scale/performance"
    if any(token in lowered for token in ("permission", "security", "access")):
        return "security/permissions"
    if any(token in lowered for token in ("pdf", "html5", "dita-ot", "publish")):
        return "publishing"
    if any(token in lowered for token in ("api", "/bin/", "post", "get")):
        return "api"
    return "functional"


def _case_classification(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("empty", "missing", "invalid", "fail", "negative")):
        return "negative"
    if any(token in lowered for token in ("large", "boundary", "limit", "600", "%")):
        return "boundary/scale"
    return "positive"


def _given_for_brief(brief: TicketBrief) -> str:
    return brief.scope_hint or brief.component or "AEM Guides Author environment with required test data"


def _when_for_brief(brief: TicketBrief) -> str:
    if "/bin/" in brief.scope_hint:
        return f"the affected API is invoked for {brief.scope_hint}"
    return "the user performs the Jira reproduction flow"


def _then_from_text(text: str) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return "Observable expected result must be clarified."
    if re.search(r"\b(status|HTTP|response|message|property|file|PDF|HTML5|report|dialog|log)\b", clean, re.I):
        return clean[:500]
    return f"Pass if this observable behaviour is seen: {clean[:430]}"


def _case_title(area: str, criterion: dict[str, Any]) -> str:
    statement = str(criterion.get("behaviour_statement") or "").strip()
    prefix = statement[:70].rstrip(".") if statement else area
    return f"{prefix} — {area}"[:140]


def _test_level_for_scope(scope: str) -> str:
    lowered = str(scope or "").lower()
    if "/bin/" in lowered or "api" in lowered:
        return "API / integration"
    if any(token in lowered for token in ("web editor", "ui", "report", "dashboard")):
        return "UI"
    return "system"


def _controlled_data_for_brief(brief: TicketBrief) -> list[str]:
    data = [f"Jira-specific dataset for {brief.jira_key}"]
    if "600" in f"{brief.summary} {brief.current_behavior} {brief.expected_behavior}":
        data.append("Large map with about 600 topics")
    if "%" in f"{brief.summary} {brief.current_behavior} {brief.expected_behavior}":
        data.append("DITA table colspec with percentage colwidth")
    if "/bin/" in brief.scope_hint:
        data.append("API request payload including positive and malformed variants")
    return data


def _steps_for_case(brief: TicketBrief, criterion: dict[str, Any], area: str) -> list[str]:
    if "/bin/" in brief.scope_hint:
        return [
            f"Prepare the request for {brief.scope_hint}.",
            "Send the positive/control payload and record status/body/persisted state.",
            "Send the Jira reproduction payload.",
            f"Verify: {criterion.get('then')}",
        ]
    return [
        f"Prepare test data for {area}.",
        "Run the Jira reproduction flow in Author.",
        "Capture UI, network/API, backend log, and persisted-state evidence where applicable.",
        f"Verify: {criterion.get('then')}",
    ]


def _automation_suitability(packet: dict[str, Any]) -> str:
    status = str(packet.get("repo_evidence_status") or "").lower()
    if status == "complete":
        return "Automatable — exact product and automation repo evidence available"
    if status == "partial":
        return "Partially automatable — repo evidence exists but needs step/assertion review"
    return "Manual first — automation repo evidence missing"


def _recommended_automation_repo(brief: TicketBrief) -> str:
    scope = f"{brief.scope_hint} {brief.component}".lower()
    if "/bin/" in scope or "api" in scope:
        return "dxml-it-tests"
    if any(token in scope for token in ("ui", "web editor", "report", "dashboard")):
        return "guides-ui-tests"
    return "guides-ui-tests or dxml-it-tests after owner review"


def _automation_match_summary(packet: dict[str, Any]) -> str:
    repo = packet.get("repository_evidence") or {}
    matches = []
    for row in repo.get("repositories") or []:
        if row.get("match_count"):
            matches.append(f"{row.get('id')}:{row.get('match_count')}")
    return ", ".join(matches[:6]) or "No exact automation match found"


def _case_risks(packet: dict[str, Any], criterion: dict[str, Any]) -> list[str]:
    risks = [str(item) for item in (criterion.get("assumptions") or [])]
    for item in (packet.get("planning_seeds") or {}).get("regression_risk_seed") or []:
        if isinstance(item, str):
            risks.append(item)
        elif isinstance(item, dict):
            risks.append(str(item.get("risk") or item.get("summary") or item.get("rationale") or ""))
    return [r for r in risks if r][:4]


def _duplicate_test_count(test_cases: list[dict[str, Any]]) -> int:
    titles = [str(case.get("title") or "").strip().lower() for case in test_cases]
    return len(titles) - len(set(titles))


def _score_reason_codes(
    packet: dict[str, Any],
    brief: TicketBrief | None,
    acceptance_criteria: list[dict[str, Any]],
    coverage_matrix: dict[str, Any],
) -> list[str]:
    codes: list[str] = []
    if packet.get("generation_mode") == "blocked":
        codes.append("UAC_CHECK_LABEL_MISSING")
    if not brief or not brief.expected_behavior:
        codes.append("EXPECTED_BEHAVIOUR_MISSING")
    if not (packet.get("experience_league_evidence") or []):
        codes.append("NO_PRODUCT_DOC_EVIDENCE")
    if not ((packet.get("learned_behavior_evidence") or {}).get("results") or []):
        codes.append("NO_LEARNED_BEHAVIOR_EVIDENCE")
    if str(packet.get("repo_evidence_status") or "").lower() not in {"complete", "partial"}:
        codes.append("REPOSITORY_EVIDENCE_MISSING")
    if any(not row.get("evidence_refs") for row in acceptance_criteria):
        codes.append("UAC_WITHOUT_EVIDENCE")
    if coverage_matrix.get("unmapped_uacs"):
        codes.append("UNMAPPED_UAC")
    return list(dict.fromkeys(codes))


def _dimension_warnings(dimensions: list[ConfidenceDimension]) -> list[str]:
    return [
        f"{dim.name}: {deduction}"
        for dim in dimensions
        for deduction in dim.deductions[:2]
        if deduction
    ][:8]


def _mandatory_human_reasons(
    packet: dict[str, Any],
    brief: TicketBrief | None,
    acceptance_criteria: list[dict[str, Any]],
    coverage_matrix: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if not brief or not brief.expected_behavior:
        reasons.append("Expected behaviour is missing or not externally observable.")
    if _detect_ticket_contradictions(brief, packet):
        reasons.append("Authoritative/current expected evidence conflicts and needs clarification.")
    if any(
        row.get("priority") == "P0" and not row.get("evidence_refs") for row in acceptance_criteria
    ):
        reasons.append("A critical UAC has no supporting evidence.")
    combined = f"{getattr(brief, 'summary', '')} {getattr(brief, 'current_behavior', '')} {getattr(brief, 'expected_behavior', '')}".lower()
    if any(token in combined for token in ("permission", "security", "delete", "data loss", "migration", "backward compatibility", "p1", "p2", "production")):
        reasons.append("High-risk security/data-loss/migration/customer-production behaviour requires human confirmation.")
    if coverage_matrix.get("unsupported_claim_count"):
        reasons.append("Unsupported UAC claims remain in the coverage matrix.")
    return list(dict.fromkeys(reasons))


def _is_customer_production(packet: dict[str, Any], brief: TicketBrief) -> bool:
    text = f"{brief.summary} {brief.current_behavior} {brief.expected_behavior} {(packet.get('issue') or {}).get('description', '')}".lower()
    return "production" in text or "customer" in text or "p1" in text or "p2" in text


__all__ = [
    "run_test_plan_pipeline",
    "build_ticket_brief",
    "score_pipeline_readiness",
    "compose_draft_test_plan",
    "build_qe_handoff",
    "render_pipeline_result_markdown",
    "write_starling_artifacts",
    "validate_test_plan_markdown",
]
