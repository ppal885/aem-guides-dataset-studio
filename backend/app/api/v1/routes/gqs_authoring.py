"""Authoring API aligned with Guides QA Studio — preview (no LLM), plan, generate."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.core.auth import CurrentUser
from app.services.integration_readiness_service import llm_authoring_readiness
from app.services.qa_studio_plan_gate import plan_readiness
from app.services.qa_studio_rag_evidence import build_rag_evidence_bundle
from app.services.qa_studio_retrieve_for_plan import retrieve_for_plan
from app.api.v1.routes.qa_studio import (
    GenerateRequest,
    PlanRequest,
    qa_generate,
    qa_plan,
    resolve_authoring_with_recorder,
)
from app.services.qa_studio_llm_authoring import llm_authoring_probe

router = APIRouter(dependencies=[CurrentUser])


def _normalize_jira_fields(body: PlanRequest) -> tuple[str, str]:
    summary = body.jira_summary.strip()
    desc = body.jira_description.strip()
    if body.jira_raw.strip():
        blob = body.jira_raw
        if not summary:
            summary = blob[:500]
        if not desc:
            desc = blob
    return summary, desc


@router.get("/readiness")
async def authoring_readiness(probe: bool = Query(default=False)) -> dict[str, Any]:
    """LLM authoring readiness; set probe=true for a short provider reachability check."""
    base = llm_authoring_readiness()
    if probe and base.get("state") == "configured":
        p = await llm_authoring_probe()
        if p.get("ok"):
            base["state"] = "ready"
            base["probe_ok"] = True
        else:
            base["state"] = "error"
            base["probe_ok"] = False
            base["probe_error"] = p.get("error")
    return base


@router.post("/preview")
async def authoring_preview(body: PlanRequest) -> dict[str, Any]:
    """Grounding + RAG evidence bundle without invoking an LLM (planning gate still applies)."""
    summary, desc = _normalize_jira_fields(body)
    repro_steps, manual_notes, target_area, eff_jira, rec_sidecar = resolve_authoring_with_recorder(body)
    blocked, blocking, fields = plan_readiness(
        repro_steps=repro_steps,
        expected_behavior=body.expected_behavior,
        acceptance_criteria=body.acceptance_criteria,
        jira_summary=summary,
        jira_description=desc,
    )
    if blocked:
        rag_evidence = build_rag_evidence_bundle(
            blocked=True,
            plan_draft=None,
            fields=fields,
            jira_summary=summary,
            target_area=target_area,
            manual_notes=manual_notes,
        )
        retrieval = retrieve_for_plan(
            fields=fields,
            jira_summary=summary,
            jira_description=body.jira_description,
            jira_raw=body.jira_raw,
            repro_steps=repro_steps,
            target_area=target_area,
            manual_notes=manual_notes,
            jira_key=eff_jira,
        )
        return {
            "blocked": True,
            "blocking_questions": blocking,
            "extracted_fields": fields,
            "plan_draft": None,
            "rag_evidence": rag_evidence,
            "rag_grounding": {
                "retrieval_query_excerpt": retrieval.get("retrieval_query_excerpt"),
                "jira_similar": retrieval.get("jira_similar"),
                "digest_json": retrieval.get("digest_json"),
            },
            "note": "Resolve planning gate fields to unlock full grounding preview with Then-aligned traceability.",
            "recorder_evidence": rec_sidecar,
        }

    retrieval = retrieve_for_plan(
        fields=fields,
        jira_summary=summary,
        jira_description=body.jira_description,
        jira_raw=body.jira_raw,
        repro_steps=repro_steps,
        target_area=target_area,
        manual_notes=manual_notes,
        jira_key=eff_jira,
    )
    rag_evidence = build_rag_evidence_bundle(
        blocked=False,
        plan_draft=None,
        fields=fields,
        jira_summary=summary,
        target_area=target_area,
        manual_notes=manual_notes,
    )
    return {
        "blocked": False,
        "blocking_questions": [],
        "extracted_fields": fields,
        "plan_draft": None,
        "rag_evidence": rag_evidence,
        "rag_grounding": {
            "retrieval_query_excerpt": retrieval.get("retrieval_query_excerpt"),
            "jira_similar": retrieval.get("jira_similar"),
            "digest_json": retrieval.get("digest_json"),
            "grounding_digest": retrieval.get("grounding_digest"),
        },
        "note": "Preview only — call POST /api/v1/authoring/plan for LLM plan when configured.",
        "recorder_evidence": rec_sidecar,
    }


@router.post("/plan")
async def authoring_plan(body: PlanRequest) -> dict[str, Any]:
    return await qa_plan(body)


@router.post("/generate")
async def authoring_generate(body: GenerateRequest) -> dict[str, Any]:
    return await qa_generate(body)
