"""Team-shared markdown test plans (blast-radius template)."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, UserIdentity
from app.core.schemas_test_plan_pipeline import (
    TestPlanPipelineRequest,
    TestPlanPipelineResult,
)
from app.db.session import get_db
from app.services import test_plan_artifact_service as artifacts

router = APIRouter(prefix="/test-plans", tags=["test-plans"])


class SaveTestPlanRequest(BaseModel):
    jira_key: str
    markdown: str = Field(min_length=32)


class QeReviewDecisionRequest(BaseModel):
    reviewer: str = "QE / QA owner"
    comments: str = ""


class TestPlanFeedbackRequest(BaseModel):
    tenant_id: str = "kone"
    correlation_id: str = Field(default="", max_length=160)
    plan_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_snapshot_id: str = Field(
        pattern=r"^evidence:[A-Z][A-Z0-9]+-\d+:[a-f0-9]{64}$"
    )
    event_type: Literal[
        "review_decision",
        "ac_edit",
        "execution_outcome",
        "escaped_defect",
    ]
    ac_id: str = ""
    ac_fingerprint: str = ""
    decision: str = ""
    outcome: str = ""
    before_hash: str = ""
    after_hash: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(default="", max_length=240)


@router.post("/pipeline", response_model=TestPlanPipelineResult)
async def run_test_plan_pipeline_route(
    body: TestPlanPipelineRequest,
    user: UserIdentity = CurrentUser,
):
    """
    Run the canonical reasoning pipeline and return the retained REST response
    contract. Prefer this over MCP for long-running evidence retrieval.
    """
    from app.services.test_plan_pipeline_service import run_test_plan_pipeline
    from app.services.tenant_service import ensure_user_can_access_tenant

    try:
        body.tenant_id = ensure_user_can_access_tenant(user, body.tenant_id)
        return await asyncio.to_thread(
            run_test_plan_pipeline,
            body,
            user,
            entry_point="backend_api",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {exc}") from exc


@router.get("")
def list_test_plans(user: UserIdentity = CurrentUser):
    """List all shared test plans on the Dataset Studio VM."""
    return {
        "plans": artifacts.list_test_plans(),
        "storage_root": str(artifacts.TEST_PLANS_DIR),
        "ui_path": "/test-plans",
    }


@router.get("/pipeline-memory")
def list_pipeline_memory(
    jira_key: str | None = None,
    limit: int = 50,
    user: UserIdentity = CurrentUser,
):
    """List retained test-plan pipeline runs for recall/comparison."""
    try:
        return {
            "runs": artifacts.list_pipeline_memory(jira_key, limit=limit),
            "storage_root": str(artifacts.PIPELINE_MEMORY_DIR),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/pipeline-memory/{jira_key}")
def get_pipeline_memory(
    jira_key: str,
    correlation_id: str | None = None,
    user: UserIdentity = CurrentUser,
):
    """Fetch the latest or selected retained pipeline run snapshot."""
    try:
        return artifacts.get_pipeline_memory(jira_key, correlation_id=correlation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{jira_key}")
def get_test_plan(jira_key: str, user: UserIdentity = CurrentUser):
    """Fetch one shared test plan markdown document."""
    try:
        return artifacts.get_test_plan(jira_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{jira_key}/feedback")
def record_test_plan_feedback(
    jira_key: str,
    body: TestPlanFeedbackRequest,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(get_db),
):
    """Append privacy-safe review, edit, execution, or escaped-defect feedback."""
    from app.services.tenant_service import ensure_user_can_access_tenant
    from app.services.test_plan_feedback_service import (
        record_test_plan_feedback as record,
    )

    try:
        tenant_id = ensure_user_can_access_tenant(user, body.tenant_id)
        result = record(
            session,
            tenant_id=tenant_id,
            jira_key=jira_key,
            correlation_id=body.correlation_id,
            plan_fingerprint=body.plan_fingerprint,
            evidence_snapshot_id=body.evidence_snapshot_id,
            event_type=body.event_type,
            actor_id=user.id,
            ac_id=body.ac_id,
            ac_fingerprint=body.ac_fingerprint,
            decision=body.decision,
            outcome=body.outcome,
            before_hash=body.before_hash,
            after_hash=body.after_hash,
            payload=body.payload,
            idempotency_key=body.idempotency_key,
        )
        session.commit()
        return result
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        session.rollback()
        raise


@router.get("/{jira_key}/feedback")
def get_test_plan_feedback(
    jira_key: str,
    tenant_id: str = "kone",
    plan_fingerprint: str = "",
    limit: int = 200,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(get_db),
):
    """List immutable feedback events without raw AC or customer text."""
    from app.services.tenant_service import ensure_user_can_access_tenant
    from app.services.test_plan_feedback_service import list_test_plan_feedback

    try:
        selected_tenant = ensure_user_can_access_tenant(user, tenant_id)
        rows = list_test_plan_feedback(
            session,
            tenant_id=selected_tenant,
            jira_key=jira_key,
            plan_fingerprint=plan_fingerprint,
            limit=limit,
        )
        return {"count": len(rows), "events": rows}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{jira_key}/quality-summary")
def get_test_plan_quality_summary(
    jira_key: str,
    tenant_id: str = "kone",
    plan_fingerprint: str = "",
    user: UserIdentity = CurrentUser,
    session: Session = Depends(get_db),
):
    """Return deterministic quality signals; feedback never becomes authority automatically."""
    from app.services.tenant_service import ensure_user_can_access_tenant
    from app.services.test_plan_feedback_service import summarize_test_plan_quality

    try:
        selected_tenant = ensure_user_can_access_tenant(user, tenant_id)
        return summarize_test_plan_quality(
            session,
            tenant_id=selected_tenant,
            jira_key=jira_key,
            plan_fingerprint=plan_fingerprint,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("")
def save_test_plan(body: SaveTestPlanRequest, user: UserIdentity = CurrentUser):
    """Publish or update a shared test plan and auto-index it into jira_qa for team retrieval."""
    from app.services.test_plan_index_service import index_test_plan

    try:
        saved = artifacts.save_test_plan(body.jira_key, body.markdown)
        validation = artifacts.validate_saved_test_plan(saved["jira_key"])
        index_result = index_test_plan(saved["jira_key"], markdown=body.markdown)
        return {
            **saved,
            "validation": validation,
            "index": index_result,
            "message": "Test plan published and indexed. Open /test-plans in Dataset Studio.",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{jira_key}/index")
def index_test_plan_route(jira_key: str, user: UserIdentity = CurrentUser):
    """Re-index a saved test plan into jira_qa ChromaDB (idempotent — safe to re-run)."""
    from app.services.test_plan_index_service import index_test_plan

    try:
        result = index_test_plan(jira_key)
        if not result["indexed"]:
            raise HTTPException(
                status_code=503, detail=result.get("reason", "Indexing failed")
            )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{jira_key}/validate")
def validate_test_plan(jira_key: str, user: UserIdentity = CurrentUser):
    """Run validate_test_plan.py against a saved shared plan."""
    try:
        return artifacts.validate_saved_test_plan(jira_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{jira_key}/qe-review/approve")
def approve_test_plan(
    jira_key: str,
    body: QeReviewDecisionRequest | None = None,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(get_db),
):
    """Record QE approval; high confidence never auto-approves."""
    try:
        payload = body or QeReviewDecisionRequest()
        result = artifacts.record_qe_review_decision(
            jira_key,
            action="approve",
            reviewer=payload.reviewer,
            comments=payload.comments,
        )
        result["quality_feedback"] = _record_review_feedback_best_effort(
            session,
            jira_key=jira_key,
            decision="QE_APPROVED",
            actor_id=user.id,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{jira_key}/qe-review/request-changes")
def request_test_plan_changes(
    jira_key: str,
    body: QeReviewDecisionRequest | None = None,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(get_db),
):
    """Record QE requested changes and preserve the prior revision."""
    try:
        payload = body or QeReviewDecisionRequest()
        result = artifacts.record_qe_review_decision(
            jira_key,
            action="request_changes",
            reviewer=payload.reviewer,
            comments=payload.comments,
        )
        result["quality_feedback"] = _record_review_feedback_best_effort(
            session,
            jira_key=jira_key,
            decision="QE_CHANGES_REQUESTED",
            actor_id=user.id,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _record_review_feedback_best_effort(
    session: Session,
    *,
    jira_key: str,
    decision: str,
    actor_id: str,
) -> dict[str, Any]:
    """Preserve legacy review flow while recording quality data when a fingerprint exists."""
    from app.services.test_plan_feedback_service import record_test_plan_feedback

    try:
        memory = artifacts.get_pipeline_memory(jira_key)
        plan_fingerprint = str(memory.get("plan_fingerprint") or "")
        evidence_snapshot_id = str(memory.get("evidence_snapshot_id") or "")
        if not plan_fingerprint or not evidence_snapshot_id:
            return {
                "recorded": False,
                "reason": "Latest pipeline memory has no immutable plan/evidence fingerprint.",
            }
        event = record_test_plan_feedback(
            session,
            tenant_id="kone",
            jira_key=jira_key,
            correlation_id=str(memory.get("correlation_id") or ""),
            plan_fingerprint=plan_fingerprint,
            evidence_snapshot_id=evidence_snapshot_id,
            event_type="review_decision",
            actor_id=actor_id,
            decision=decision,
            payload={"review_status": decision},
        )
        session.commit()
        return {"recorded": True, "event": event}
    except Exception as exc:
        session.rollback()
        return {
            "recorded": False,
            "reason": f"Quality feedback unavailable: {type(exc).__name__}: {exc}",
        }
