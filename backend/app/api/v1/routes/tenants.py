from fastapi import APIRouter

from app.api.v1.routes._api_errors import raise_api_error
from app.core.auth import AdminUser, UserIdentity

router = APIRouter()


@router.post("")
async def create_tenant_route(body: dict, user: UserIdentity = AdminUser):
    try:
        from app.services.tenant_service import create_tenant

        config = create_tenant(
            tenant_id=body.get("tenant_id", ""),
            name=body.get("name", ""),
            jira_url=body.get("jira_url", ""),
            jira_token=body.get("jira_token", ""),
            jira_email=body.get("jira_email", ""),
            plan=body.get("plan", "standard"),
        )
        return config.to_dict(include_kb=True)
    except Exception as exc:
        raise_api_error(exc, default_detail="Failed to create tenant")


@router.get("")
async def list_tenants_route(user: UserIdentity = AdminUser):
    try:
        from app.services.tenant_service import list_tenants

        return {"tenants": list_tenants()}
    except Exception as exc:
        raise_api_error(exc, default_detail="Failed to list tenants")


@router.get("/{tenant_id}")
async def get_tenant_route(tenant_id: str, user: UserIdentity = AdminUser):
    try:
        from app.services.tenant_service import get_tenant

        return get_tenant(tenant_id).to_dict(include_kb=True)
    except Exception as exc:
        raise_api_error(exc, default_detail=f"Failed to load tenant '{tenant_id}'")


@router.put("/{tenant_id}")
async def update_tenant_route(tenant_id: str, body: dict, user: UserIdentity = AdminUser):
    try:
        from app.services.tenant_service import update_tenant

        config = update_tenant(
            tenant_id,
            name=body.get("name"),
            jira_url=body.get("jira_url"),
            jira_email=body.get("jira_email"),
            jira_token=body.get("jira_token"),
            plan=body.get("plan"),
            is_active=body.get("is_active"),
        )
        return config.to_dict(include_kb=True)
    except Exception as exc:
        raise_api_error(exc, default_detail=f"Failed to update tenant '{tenant_id}'")


@router.put("/{tenant_id}/knowledge-base")
async def update_tenant_knowledge_route(tenant_id: str, body: dict, user: UserIdentity = AdminUser):
    try:
        from app.services.tenant_service import update_tenant_kb

        config = update_tenant_kb(
            tenant_id,
            terminology=body.get("terminology"),
            style_rules=body.get("style_rules"),
            component_map=body.get("component_map"),
            forbidden_terms=body.get("forbidden_terms"),
            custom_audiences=body.get("custom_audiences"),
        )
        return config.to_dict(include_kb=True)
    except Exception as exc:
        raise_api_error(exc, default_detail=f"Failed to update tenant knowledge for '{tenant_id}'")
