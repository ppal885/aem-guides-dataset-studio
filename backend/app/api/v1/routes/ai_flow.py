from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.auth import CurrentUser, UserIdentity

router = APIRouter()


@router.get("/ai/flow-intelligence")
async def get_flow_intelligence(request: Request, user: UserIdentity = CurrentUser):
    from app.services.ai_flow_intelligence_service import get_tenant_flow_intelligence
    from app.services.tenant_service import get_authorized_tenant_id

    tenant_id = get_authorized_tenant_id(request, user)
    return get_tenant_flow_intelligence(tenant_id)
