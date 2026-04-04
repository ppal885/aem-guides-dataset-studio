from fastapi import APIRouter, Request

from app.api.v1.routes._api_errors import raise_api_error
from app.core.auth import CurrentUser, UserIdentity

router = APIRouter()


@router.post("/analyse")
async def analyse_route(request: Request, body: dict, user: UserIdentity = CurrentUser):
    try:
        from app.services.smart_suggestions_service import build_review_snapshot
        from app.services.tenant_service import get_authorized_tenant_id

        tenant_id = get_authorized_tenant_id(request, user)
        review = await build_review_snapshot(
            xml=body.get("xml", ""),
            issue=body.get("issue", {}),
            tenant_id=tenant_id,
            audience_id=body.get("audience_id", ""),
            research_context=body.get("research_context"),
        )
        report = review.get("suggestions_report", {})
        return {
            **report,
            "updated_review": review,
        }
    except Exception as exc:
        raise_api_error(exc, default_detail="Failed to analyse XML suggestions")


@router.post("/apply-fix")
async def apply_fix_route(request: Request, body: dict, user: UserIdentity = CurrentUser):
    try:
        from app.services.smart_suggestions_service import apply_fix_with_review
        from app.services.tenant_service import get_authorized_tenant_id

        tenant_id = get_authorized_tenant_id(request, user)
        return await apply_fix_with_review(
            xml=body.get("xml", ""),
            suggestion=body.get("suggestion", {}),
            issue=body.get("issue", {}),
            tenant_id=tenant_id,
            research_context=body.get("research_context"),
            audience_id=body.get("audience_id", ""),
        )
    except Exception as exc:
        raise_api_error(exc, default_detail="Failed to apply XML suggestion")


@router.post("/refine-completions")
async def refine_completions_route(request: Request, body: dict, user: UserIdentity = CurrentUser):
    try:
        from app.services.smart_suggestions_service import analyse_content
        from app.services.tenant_service import get_authorized_tenant_id

        tenant_id = get_authorized_tenant_id(request, user)
        partial = (body.get("partial") or "").lower()
        report = await analyse_content(
            xml=body.get("xml", ""),
            issue=body.get("issue", {}),
            tenant_id=tenant_id,
            research_context=body.get("research_context"),
            validation=body.get("validation"),
            quality_breakdown=body.get("quality_breakdown"),
        )
        completions = report.refine_completions
        if partial:
            completions = [item for item in completions if partial in item.lower()]
        return {"completions": completions[:6]}
    except Exception as exc:
        raise_api_error(exc, default_detail="Failed to load refinement completions")


@router.post("/section-suggestions")
async def section_suggestions_route(request: Request, body: dict, user: UserIdentity = CurrentUser):
    try:
        from app.services.smart_suggestions_service import analyse_content
        from app.services.tenant_service import get_authorized_tenant_id

        tenant_id = get_authorized_tenant_id(request, user)
        section = body.get("section", "")
        report = await analyse_content(
            xml=body.get("xml", ""),
            issue=body.get("issue", {}),
            tenant_id=tenant_id,
            research_context=body.get("research_context"),
            validation=body.get("validation"),
            quality_breakdown=body.get("quality_breakdown"),
        )
        relevant = [
            suggestion.to_dict()
            for suggestion in report.suggestions
            if suggestion.section == section or section in suggestion.rule_id
        ]
        return {"section": section, "suggestions": relevant}
    except Exception as exc:
        raise_api_error(exc, default_detail="Failed to load section suggestions")


@router.post("/fix-all")
async def fix_all_route(request: Request, body: dict, user: UserIdentity = CurrentUser):
    try:
        from app.services.smart_suggestions_service import fix_all_safe
        from app.services.tenant_service import get_authorized_tenant_id

        tenant_id = get_authorized_tenant_id(request, user)
        return await fix_all_safe(
            xml=body.get("xml", ""),
            issue=body.get("issue", {}),
            tenant_id=tenant_id,
            research_context=body.get("research_context"),
            audience_id=body.get("audience_id", ""),
        )
    except Exception as exc:
        raise_api_error(exc, default_detail="Failed to apply bulk XML fixes")
