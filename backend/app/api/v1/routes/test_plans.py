"""Team-shared markdown test plans (blast-radius template)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import CurrentUser, UserIdentity
from app.core.schemas_test_plan_pipeline import TestPlanPipelineRequest, TestPlanPipelineResult
from app.services import test_plan_artifact_service as artifacts

router = APIRouter(prefix="/test-plans", tags=["test-plans"])


class SaveTestPlanRequest(BaseModel):
    jira_key: str
    markdown: str = Field(min_length=32)


class QeReviewDecisionRequest(BaseModel):
    reviewer: str = "QE / QA owner"
    comments: str = ""


@router.post("/pipeline", response_model=TestPlanPipelineResult)
async def run_test_plan_pipeline_route(
    body: TestPlanPipelineRequest,
    user: UserIdentity = CurrentUser,
):
    """
    End-to-end pipeline: ticket intake → full RAG → score → UAC intelligence →
    draft test plan → QE handoff. Prefer this over MCP for long-running full RAG.
    """
    from app.services.test_plan_pipeline_service import run_test_plan_pipeline

    try:
        return await asyncio.to_thread(run_test_plan_pipeline, body)
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


@router.post("")
def save_test_plan(body: SaveTestPlanRequest, user: UserIdentity = CurrentUser):
    """Publish or update a shared test plan visible to all team members in the UI."""
    try:
        saved = artifacts.save_test_plan(body.jira_key, body.markdown)
        validation = artifacts.validate_saved_test_plan(saved["jira_key"])
        return {
            **saved,
            "validation": validation,
            "message": "Test plan published to shared storage. Open /test-plans in Dataset Studio.",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
):
    """Record QE approval; high confidence never auto-approves."""
    try:
        payload = body or QeReviewDecisionRequest()
        return artifacts.record_qe_review_decision(
            jira_key,
            action="approve",
            reviewer=payload.reviewer,
            comments=payload.comments,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{jira_key}/qe-review/request-changes")
def request_test_plan_changes(
    jira_key: str,
    body: QeReviewDecisionRequest | None = None,
    user: UserIdentity = CurrentUser,
):
    """Record QE requested changes and preserve the prior revision."""
    try:
        payload = body or QeReviewDecisionRequest()
        return artifacts.record_qe_review_decision(
            jira_key,
            action="request_changes",
            reviewer=payload.reviewer,
            comments=payload.comments,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
