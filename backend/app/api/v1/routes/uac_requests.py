"""On-demand UAC requests: ask the release runner to generate and post a UAC for one ticket.

``POST`` only records the request; the runner's ``--on-demand`` mode generates the UAC with every check of
the nightly run, writes it into the ticket's Acceptance Criteria field and reports back on the same
request. Callers poll ``GET /uac-requests/{id}`` (or watch the ``QEVision_UAC_DONE`` label). The same
capability is exposed over MCP as ``request_uac`` / ``request_uac_status``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.core.auth import CurrentUser, UserIdentity
from app.services import uac_request_service

router = APIRouter(prefix="/uac-requests", tags=["uac-requests"])


class UacRequestCreate(BaseModel):
    jira_key: str = Field(..., min_length=3, max_length=40, description="Ticket key, for example GUIDES-60001")
    requested_by: str = Field("", max_length=120, description="Who or what asks, for example 'vision'")
    note: str = Field("", max_length=500, description="Optional free text recorded with the request")


@router.post("", status_code=202)
def create_uac_request(body: UacRequestCreate, response: Response, user: UserIdentity = CurrentUser) -> dict:
    try:
        request, created = uac_request_service.create_request(
            body.jira_key, requested_by=body.requested_by or user.id, note=body.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not created:
        response.status_code = 200  # an open request for this ticket already exists; poll that one
    return request


@router.get("/{request_id}")
def get_uac_request(request_id: str, user: UserIdentity = CurrentUser) -> dict:
    request = uac_request_service.get_request(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Unknown UAC request")
    return request


@router.get("")
def list_uac_requests(
    jira_key: str | None = Query(None, max_length=40),
    status: str | None = Query(None, max_length=20),
    limit: int = Query(50, ge=1, le=200),
    user: UserIdentity = CurrentUser,
) -> dict:
    if status and status not in uac_request_service.valid_statuses():
        raise HTTPException(status_code=422, detail=f"status must be one of {', '.join(uac_request_service.valid_statuses())}")
    try:
        items = uac_request_service.list_requests(jira_key=jira_key, status=status, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"items": items, "count": len(items)}
