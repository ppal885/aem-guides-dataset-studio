"""AEM Guides QA Studio API — dashboard, bundled knowledge, validators, planning gate (additive)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import CurrentUser
from app.services.qa_studio_automation_validator import validate_automation_artifacts
from app.services.qa_studio_bundled import (
    bundled_counts_and_meta,
    list_playbooks,
    search_playbooks,
    validate_bundled_knowledge,
)
from app.services.qa_studio_locator_quality import assess_locator_full
from app.services.qa_studio_plan_gate import plan_readiness
from app.services.qa_studio_assertion_traceability import (
    build_traceability_report,
    extract_then_lines_from_feature,
    merge_user_and_jira_fields,
)
from app.services.qa_studio_rag_evidence import build_rag_evidence_bundle
from app.services.qa_studio_llm_authoring import (
    llm_authoring_enabled,
    run_llm_generation,
    run_llm_planning,
)
from app.services.gqs_integration_config import demo_plans_enabled, engine_stub
from app.services.framework_index_service import build_framework_indexes, read_framework_qa_health
from app.services.guides_qa_rag_service import guides_rag_full_reindex, guides_rag_health
from app.services.integration_readiness_service import build_setup_checklist, llm_authoring_readiness

router = APIRouter(dependencies=[CurrentUser])


class LocatorValidateRequest(BaseModel):
    expression: str = Field(..., min_length=1, max_length=4000)
    source: str = Field(default="unknown", max_length=64)
    has_dom_evidence: bool = False
    stable_anchor_confirmed: bool | None = None
    approval_status: str = Field(default="none", max_length=32)


class AutomationValidateRequest(BaseModel):
    feature_text: str = ""
    step_defs_text: str = ""
    page_object_text: str = ""
    jira_summary: str = ""
    jira_description: str = ""
    jira_raw: str = ""
    repro_steps: str = ""
    expected_behavior: str = ""
    acceptance_criteria: str = ""
    ui_snapshots: list[dict[str, Any]] = Field(default_factory=list)


def _then_steps_for_trace(plan_draft: dict[str, Any] | None) -> list[str]:
    if not isinstance(plan_draft, dict):
        return []
    ad = plan_draft.get("automation_design")
    if isinstance(ad, dict):
        outline = ad.get("gherkin_outline") or {}
        raw_then = outline.get("then")
        if isinstance(raw_then, list) and raw_then:
            out = [str(x) for x in raw_then if str(x).strip()]
            if out:
                return out
        atr = plan_draft.get("assertion_traceability")
        if isinstance(atr, list):
            return [
                str(x.get("then_step") or "").strip()
                for x in atr
                if isinstance(x, dict) and (str(x.get("then_step") or "").strip())
            ]
    outline = plan_draft.get("gherkin_outline") or {}
    raw_then = outline.get("then")
    if isinstance(raw_then, list):
        return [str(x) for x in raw_then if str(x).strip()]
    return []


def _merge_rag_evidence_into_plan(plan_draft: dict[str, Any], rag_evidence: dict[str, Any]) -> None:
    for k in (
        "playbook_matches",
        "ui_reference_matches",
        "ui_snapshot_matches",
        "dom_pattern_matches",
        "page_object_matches",
        "assertion_source_matches",
    ):
        if k in rag_evidence:
            plan_draft[k] = rag_evidence[k]


def resolve_authoring_with_recorder(
    body: PlanRequest | GenerateRequest,
) -> tuple[str, str, str, str | None, dict[str, Any]]:
    """Apply optional recorder session merge. Returns repro, notes, target_area, effective_jira_key, recorder_sidecar."""
    rid = getattr(body, "recorder_session_id", None)
    if not (rid or "").strip():
        jk = (body.jira_key or "").strip() or None
        return body.repro_steps, body.manual_notes, body.target_area, jk, {}
    from app.services.recorder_capture_service import merge_recorder_into_authoring_fields

    try:
        repro_steps, manual_notes, target_area, sidecar = merge_recorder_into_authoring_fields(
            rid.strip(),
            repro_steps=body.repro_steps,
            manual_notes=body.manual_notes,
            target_area=body.target_area,
            jira_key=body.jira_key,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Recorder session not found") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    eff_jira = (body.jira_key or "").strip() or None
    if not eff_jira:
        rj = sidecar.get("resolved_jira_from_session")
        if isinstance(rj, str) and rj.strip():
            eff_jira = rj.strip()[:50]
    return repro_steps, manual_notes, target_area, eff_jira, sidecar


class PlanRequest(BaseModel):
    jira_key: str | None = Field(None, max_length=50)
    jira_summary: str = ""
    jira_description: str = ""
    jira_raw: str = ""
    repro_steps: str = ""
    expected_behavior: str = ""
    acceptance_criteria: str = ""
    target_area: str = Field("", max_length=200)
    manual_notes: str = ""
    recorder_session_id: str | None = Field(None, max_length=128)


class GenerateRequest(BaseModel):
    plan: dict[str, Any] = Field(default_factory=dict)
    jira_key: str | None = Field(None, max_length=50)
    jira_summary: str = ""
    jira_description: str = ""
    jira_raw: str = ""
    repro_steps: str = ""
    expected_behavior: str = ""
    acceptance_criteria: str = ""
    target_area: str = Field("", max_length=200)
    manual_notes: str = ""
    recorder_session_id: str | None = Field(None, max_length=128)


@router.get("/health")
def qa_studio_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "qa-studio",
        "time_utc": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/status")
def qa_studio_status() -> dict[str, Any]:
    """Aggregate dashboard: app RAG, Guides QA RAG, framework index, LLM readiness, setup checklist."""
    from app.api.v1.router import _get_rag_status

    rag = _get_rag_status()
    bundled = bundled_counts_and_meta()
    fw = read_framework_qa_health()
    gq_rag = guides_rag_health()
    counts = fw.get("counts") or {}
    xpath_n = int(counts.get("xpath_entries") or 0)
    framework_xpath_index = {
        "status": fw.get("status"),
        "reason": fw.get("reason"),
        "count": xpath_n,
        "counts": counts,
        "last_indexed_at": fw.get("last_indexed_at"),
        "index_path": fw.get("index_dir"),
        "index_files": fw.get("index_files"),
        "repo_root": fw.get("repo_root"),
        "expected_path_example": fw.get("expected_path_example"),
    }
    cols = (gq_rag.get("collections") or {})
    embedding_collections = {k: (v.get("chroma_count") or 0) for k, v in cols.items()}
    llm_r = llm_authoring_readiness()
    return {
        "backend_health": "ok",
        "frontend_health": "unknown_ui_probe",
        "rag": rag,
        "qa_bundled": bundled,
        "framework_qa": fw,
        "guides_qa_rag": gq_rag,
        "framework_xpath_index": framework_xpath_index,
        "ui_repo_path": fw.get("repo_root"),
        "embedding_collections": embedding_collections,
        "guides_qa_rag_degraded": bool(gq_rag.get("degraded_bundled_only")),
        "setup_checklist": build_setup_checklist(),
        "llm_authoring": llm_r,
        "engine_stub": engine_stub(),
        "recent_jobs": [],
        "qa_studio_llm_authoring": llm_authoring_enabled(),
        "demo_plans_enabled": demo_plans_enabled(),
    }


@router.get("/bundled/validate")
def qa_validate_bundled() -> dict[str, Any]:
    return validate_bundled_knowledge()


@router.get("/playbooks")
def qa_playbooks(
    area: str | None = None,
    workflow: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    return {"playbooks": search_playbooks(area=area, workflow=workflow, query=q)}


@router.get("/playbooks/all")
def qa_playbooks_all() -> dict[str, Any]:
    return {"playbooks": list_playbooks()}


@router.post("/validate/locator")
def qa_validate_locator(body: LocatorValidateRequest) -> dict[str, Any]:
    return assess_locator_full(
        body.expression.strip(),
        source=body.source,
        has_dom_evidence=body.has_dom_evidence,
        stable_anchor_confirmed=body.stable_anchor_confirmed,
        approval_status=body.approval_status,
    )


@router.post("/validate/automation")
def qa_validate_automation(body: AutomationValidateRequest) -> dict[str, Any]:
    r = validate_automation_artifacts(
        feature_text=body.feature_text,
        step_defs_text=body.step_defs_text,
        page_object_text=body.page_object_text,
        jira_summary=body.jira_summary,
        jira_description=body.jira_description,
        jira_raw=body.jira_raw,
        repro_steps=body.repro_steps,
        expected_behavior=body.expected_behavior,
        acceptance_criteria=body.acceptance_criteria,
        ui_snapshots=list(body.ui_snapshots) if body.ui_snapshots else None,
    )
    return {"ok": r.ok, "errors": r.errors, "warnings": r.warnings}


class AssertionTraceabilityRequest(BaseModel):
    jira_summary: str = ""
    jira_description: str = ""
    jira_raw: str = ""
    repro_steps: str = ""
    expected_behavior: str = ""
    acceptance_criteria: str = ""
    feature_text: str = ""
    then_steps: list[str] = Field(default_factory=list)
    ui_snapshots: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/validate/assertion-traceability")
def qa_validate_assertion_traceability(body: AssertionTraceabilityRequest) -> dict[str, Any]:
    fields = merge_user_and_jira_fields(
        jira_summary=body.jira_summary,
        jira_description=body.jira_description,
        jira_raw=body.jira_raw,
        repro_steps=body.repro_steps,
        expected_behavior=body.expected_behavior,
        acceptance_criteria=body.acceptance_criteria,
    )
    then_steps = list(body.then_steps)
    if not then_steps and body.feature_text.strip():
        then_steps = extract_then_lines_from_feature(body.feature_text)
    ui_snaps = list(body.ui_snapshots) if body.ui_snapshots else None
    return build_traceability_report(fields=fields, then_steps=then_steps, ui_snapshots=ui_snaps)


@router.post("/plan")
async def qa_plan(body: PlanRequest) -> dict[str, Any]:
    """Planning gate; stub plan by default, or LLM plan + judge when QA_STUDIO_LLM_AUTHORING=true."""
    summary = body.jira_summary.strip()
    desc = body.jira_description.strip()
    if body.jira_raw.strip():
        blob = body.jira_raw
        if not summary:
            summary = blob[:500]
        if not desc:
            desc = blob

    repro_steps, manual_notes, target_area, eff_jira, rec_sidecar = resolve_authoring_with_recorder(body)

    blocked, blocking, fields = plan_readiness(
        repro_steps=repro_steps,
        expected_behavior=body.expected_behavior,
        acceptance_criteria=body.acceptance_criteria,
        jira_summary=summary,
        jira_description=desc,
    )

    if blocked:
        trace_report = build_traceability_report(fields=fields, then_steps=[])
        rag_evidence = build_rag_evidence_bundle(
            blocked=True,
            plan_draft=None,
            fields=fields,
            jira_summary=summary,
            target_area=target_area,
            manual_notes=manual_notes,
        )
        return {
            "blocked": True,
            "blocking_questions": blocking,
            "extracted_fields": fields,
            "plan_draft": None,
            "rag_evidence": rag_evidence,
            "assertion_traceability_report": trace_report,
            "llm_mode": None,
            "senior_qa_reasoning": None,
            "rag_grounding": {},
            "recorder_evidence": rec_sidecar,
        }

    use_llm = llm_authoring_enabled()
    llm_meta: dict[str, Any] = {
        "llm_mode": None,
        "senior_qa_reasoning": None,
        "rag_grounding": {},
        "plan_judge_ok": None,
        "plan_judge_critiques": [],
        "planning_structured_issues": [],
        "planning_self_correction_attempts": 0,
        "llm_planning_error": None,
        "setup_message": None,
    }

    plan_draft: dict[str, Any] | None = None
    if use_llm:
        llm_meta["llm_mode"] = "llm"
        llm_out = await run_llm_planning(
            jira_key=eff_jira,
            jira_summary=summary,
            jira_description=desc,
            jira_raw=body.jira_raw,
            repro_steps=repro_steps,
            expected_behavior=body.expected_behavior,
            acceptance_criteria=body.acceptance_criteria,
            target_area=target_area,
            manual_notes=manual_notes,
            fields=fields,
        )
        llm_meta["senior_qa_reasoning"] = llm_out.get("senior_qa_reasoning")
        llm_meta["rag_grounding"] = llm_out.get("rag_grounding") or {}
        llm_meta["plan_judge_ok"] = llm_out.get("plan_judge_ok")
        llm_meta["plan_judge_critiques"] = llm_out.get("plan_judge_critiques") or []
        llm_meta["planning_structured_issues"] = llm_out.get("planning_structured_issues") or []
        llm_meta["planning_self_correction_attempts"] = llm_out.get("planning_self_correction_attempts") or 0
        llm_meta["llm_planning_error"] = llm_out.get("llm_planning_error")
        candidate = llm_out.get("plan_draft")
        if isinstance(candidate, dict) and candidate:
            plan_draft = candidate

    if plan_draft is None and demo_plans_enabled():
        llm_meta["llm_mode"] = "demo_stub"
        acq = (
            (
                fields.get("source_quote")
                or fields.get("acceptance_criteria")
                or fields.get("expected_fixed_behavior")
                or ""
            )
            .strip()
        )
        first_line = (acq.split("\n")[0] or acq).strip()
        if len(first_line) > 200:
            first_line = first_line[:197] + "..."
        then_stub = (
            f"Then {first_line}"
            if first_line
            else "Then Observable outcome matches documented expected behavior or acceptance criteria."
        )

        plan_draft = {
            "scenario_intent": (
                f"Validate AEM Guides behavior for {target_area or 'target area'} "
                f"per Jira expectations (demo stub plan — QA_STUDIO_DEMO_PLANS / GQS_DEMO_PLANS)."
            ),
            "gherkin_outline": {
                "given": ["Preconditions from reproduction (Page Object setup)"],
                "when": ["User actions aligned to repro steps"],
                "then": [then_stub],
            },
            "page_object_calls": [],
            "locator_decisions": [
                {
                    "intent": "Primary panel tabs / menus",
                    "rationale": (
                        "Use role=tablist/tabpanel and scoped Spectrum menu labels per matched playbooks; "
                        "avoid react-spectrum / TabView generated ids."
                    ),
                }
            ],
            "scroll_strategy": ["Prefer scroll-container-aware actions for dialogs/menus"],
            "assertion_traceability": [],
            "risks_and_warnings": fields.get("planning_hints") or [],
            "review_needed": True,
            "note": "Demo mode stub — disable QA_STUDIO_DEMO_PLANS for production; configure the app LLM (same as AI chat) or optional GQS_LLM_* for a separate gateway.",
        }
    elif plan_draft is None:
        llm_meta["llm_mode"] = "unavailable"
        llm_meta["setup_message"] = (
            "LLM planning is not available — configure the same provider as AI chat (e.g. ANTHROPIC_API_KEY). "
            "Optional: set GQS_LLM_API_KEY + GQS_LLM_MODEL for a dedicated OpenAI-compatible endpoint. "
            "To forbid app LLM for QA Studio only, set QA_STUDIO_USE_APP_LLM=false. "
            "Set QA_STUDIO_LLM_AUTHORING=false to disable QA LLM calls while chat stays on. "
            "Enable QA_STUDIO_DEMO_PLANS only for intentional demo stubs. "
            "Use POST /api/v1/authoring/preview for grounding without an LLM."
        )

    then_steps = _then_steps_for_trace(plan_draft) if plan_draft else []
    if plan_draft and not then_steps and isinstance(plan_draft.get("gherkin_outline"), dict):
        then_steps = list((plan_draft["gherkin_outline"].get("then") or []))

    rag_evidence = build_rag_evidence_bundle(
        blocked=False,
        plan_draft=plan_draft,
        fields=fields,
        jira_summary=summary,
        target_area=target_area,
        manual_notes=manual_notes,
    )
    ui_snapshots = rag_evidence.get("ui_snapshot_matches") if isinstance(rag_evidence, dict) else None

    trace_report = build_traceability_report(
        fields=fields, then_steps=then_steps, ui_snapshots=ui_snapshots
    )
    if plan_draft:
        plan_draft["assertion_traceability"] = [
            {
                "then_step": tr["then_text"],
                "mapped_jira_source": tr.get("mapped_source"),
                "mapping_relevance": tr.get("relevance"),
                "source_tr": fields.get("source_quote") or fields.get("acceptance_criteria"),
                "assertion_method": fields.get("assertion_method"),
                "trace_ok": tr.get("ok"),
                "trace_reason": tr.get("reason"),
            }
            for tr in trace_report.get("then_step_results", [])
        ]

    if plan_draft:
        _merge_rag_evidence_into_plan(plan_draft, rag_evidence)

    return {
        "blocked": False,
        "blocking_questions": [],
        "extracted_fields": fields,
        "plan_draft": plan_draft,
        "rag_evidence": rag_evidence,
        "assertion_traceability_report": trace_report,
        **llm_meta,
        "recorder_evidence": rec_sidecar,
    }


@router.post("/generate")
async def qa_generate(body: GenerateRequest) -> dict[str, Any]:
    """Generate feature/steps/PO proposals from a plan (requires QA_STUDIO_LLM_AUTHORING + LLM configured)."""
    summary = body.jira_summary.strip()
    desc = body.jira_description.strip()
    if body.jira_raw.strip():
        blob = body.jira_raw
        if not summary:
            summary = blob[:500]
        if not desc:
            desc = blob

    repro_steps, manual_notes, target_area, eff_jira, rec_sidecar = resolve_authoring_with_recorder(body)

    blocked, blocking, fields = plan_readiness(
        repro_steps=repro_steps,
        expected_behavior=body.expected_behavior,
        acceptance_criteria=body.acceptance_criteria,
        jira_summary=summary,
        jira_description=desc,
    )
    if blocked:
        return {
            "accepted": False,
            "blocked": True,
            "blocking_questions": blocking,
            "extracted_fields": fields,
            "generated": None,
            "compact_plan": {},
            "validation_errors": [],
            "validation_warnings": [],
            "generation_structured_issues": [
                {
                    "severity": "error",
                    "code": "planning_blocked",
                    "message": "Resolve expected behavior / AC before generation.",
                }
            ],
            "generation_ok": False,
            "recorder_evidence": rec_sidecar,
        }

    if not llm_authoring_enabled():
        return {
            "accepted": False,
            "blocked": False,
            "message": (
                "LLM authoring is not available — configure the app LLM (same variables as AI chat), "
                "or set GQS_LLM_API_KEY + GQS_LLM_MODEL for a separate gateway. "
                "If QA_STUDIO_LLM_AUTHORING=false, set it true or unset it."
            ),
            "generated": None,
            "compact_plan": {},
            "validation_errors": [],
            "validation_warnings": [],
            "generation_structured_issues": [],
            "generation_ok": False,
            "recorder_evidence": rec_sidecar,
        }

    plan = body.plan if isinstance(body.plan, dict) else {}
    out = await run_llm_generation(
        plan=plan,
        jira_key=eff_jira,
        jira_summary=summary,
        jira_description=desc,
        jira_raw=body.jira_raw,
        repro_steps=repro_steps,
        expected_behavior=body.expected_behavior,
        acceptance_criteria=body.acceptance_criteria,
        target_area=target_area,
        manual_notes=manual_notes,
        fields=fields,
    )
    gen = out.get("generated") if isinstance(out.get("generated"), dict) else {}
    return {
        "accepted": True,
        "blocked": False,
        "extracted_fields": fields,
        "compact_plan": out.get("compact_plan") or {},
        "generated": gen,
        "feature_text": gen.get("feature_text"),
        "step_defs_text": gen.get("step_defs_text"),
        "page_object_proposals_text": gen.get("page_object_proposals_text"),
        "framework_compliance": gen.get("framework_compliance"),
        "summary": gen.get("summary"),
        "generation_self_correction_attempts": out.get("generation_self_correction_attempts"),
        "validation_errors": out.get("validation_errors") or [],
        "validation_warnings": out.get("validation_warnings") or [],
        "generation_structured_issues": out.get("generation_structured_issues") or [],
        "generation_ok": out.get("generation_ok"),
        "llm_generation_error": out.get("llm_generation_error"),
        "recorder_evidence": rec_sidecar,
    }


@router.post("/admin/reindex/xpath")
def qa_reindex_xpath() -> dict[str, Any]:
    """Build resources/ai_index/*.json under GQS_GUIDES_REPO_ROOT (same as POST /api/v1/framework/reindex)."""
    return build_framework_indexes()


@router.post("/admin/reindex/full-rag")
def qa_reindex_full_rag() -> dict[str, Any]:
    """Populate Guides QA Chroma collections (same as POST /api/v1/rag/reindex)."""
    return guides_rag_full_reindex()
