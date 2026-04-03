"""
Smart Suggestions Routes
Register in router.py:
  from app.api.v1.routes import smart_suggestions
  api_router.include_router(smart_suggestions.router, prefix="/smart", tags=["smart"])
"""
from fastapi import APIRouter, Request
router = APIRouter()


@router.post("/analyse")
async def analyse(request: Request, body: dict):
    """
    Full content analysis. Returns all suggestions.
    Called: after generation, after manual edit, before publish.

    Input:  { "xml": "...", "issue": {...} }
    Output: SuggestionReport with all issues, before/after, fix prompts
    """
    try:
        from app.services.smart_suggestions_service import analyse_content
        from app.services.tenant_service import get_tenant_id_from_request
        tenant_id = get_tenant_id_from_request(request)
        report = await analyse_content(
            xml       = body.get("xml", ""),
            issue     = body.get("issue", {}),
            tenant_id = tenant_id,
            audience_id = body.get("audience_id", ""),
        )
        return report.to_dict()
    except Exception as e:
        return {"error": str(e), "total": 0, "suggestions": []}


@router.post("/apply-fix")
async def apply_fix(request: Request, body: dict):
    """
    Apply a specific fix to the XML.
    Returns updated XML.

    Input:  { "xml": "...", "issue": {...}, "suggestion": { suggestion dict } }
    Output: { "xml": "updated xml...", "applied": true }
    """
    try:
        from app.services.smart_suggestions_service import apply_fix
        from app.services.tenant_service import get_tenant_id_from_request
        tenant_id = get_tenant_id_from_request(request)
        updated = await apply_fix(
            xml        = body.get("xml", ""),
            suggestion = body.get("suggestion", {}),
            issue      = body.get("issue", {}),
            tenant_id  = tenant_id,
        )
        return {"xml": updated, "applied": True}
    except Exception as e:
        return {"error": str(e), "applied": False}


@router.post("/refine-completions")
async def refine_completions(request: Request, body: dict):
    """
    Get smart completions for the refine bar.
    Called on focus of refine input.

    Input:  { "xml": "...", "issue": {...}, "partial": "add p..." }
    Output: { "completions": ["Add prereq section", ...] }
    """
    try:
        from app.services.smart_suggestions_service import analyse_content
        from app.services.tenant_service import get_tenant_id_from_request
        tenant_id = get_tenant_id_from_request(request)
        report = await analyse_content(
            xml       = body.get("xml", ""),
            issue     = body.get("issue", {}),
            tenant_id = tenant_id,
        )
        partial = (body.get("partial") or "").lower()
        completions = report.refine_completions
        if partial:
            completions = [c for c in completions if partial in c.lower()]
        return {"completions": completions[:6]}
    except Exception as e:
        return {"completions": [], "error": str(e)}


@router.post("/section-suggestions")
async def section_suggestions(request: Request, body: dict):
    """
    Get inline suggestions for a specific section.
    Called on hover/click of a section in the editor.

    Input:  { "xml": "...", "section": "shortdesc", "issue": {...} }
    Output: { "suggestions": [...] } filtered to that section
    """
    try:
        from app.services.smart_suggestions_service import analyse_content
        from app.services.tenant_service import get_tenant_id_from_request
        tenant_id = get_tenant_id_from_request(request)
        section   = body.get("section", "")
        report    = await analyse_content(
            xml       = body.get("xml", ""),
            issue     = body.get("issue", {}),
            tenant_id = tenant_id,
        )
        relevant = [
            s.to_dict() for s in report.suggestions
            if s.section == section or section in s.rule_id
        ]
        return {"suggestions": relevant, "section": section}
    except Exception as e:
        return {"error": str(e), "suggestions": []}


@router.post("/fix-all")
async def fix_all(request: Request, body: dict):
    """
    Apply all error + warning fixes in one call.
    For the 'Fix all issues' button in checklist.

    Input:  { "xml": "...", "issue": {...} }
    Output: { "xml": "fixed xml...", "fixed_count": 3 }
    """
    try:
        from app.services.smart_suggestions_service import analyse_content, apply_fix
        from app.services.tenant_service import get_tenant_id_from_request
        tenant_id = get_tenant_id_from_request(request)
        xml   = body.get("xml", "")
        issue = body.get("issue", {})

        report = await analyse_content(xml=xml, issue=issue, tenant_id=tenant_id)

        # Apply errors first, then warnings
        fixed = 0
        for sug in report.suggestions:
            if sug.severity in ("error", "warning"):
                xml   = await apply_fix(xml=xml, suggestion=sug.to_dict(), issue=issue, tenant_id=tenant_id)
                fixed += 1

        return {"xml": xml, "fixed_count": fixed}
    except Exception as e:
        return {"error": str(e), "fixed_count": 0}
