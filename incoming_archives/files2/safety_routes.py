"""
Safety routes — author control and audit endpoints.
Add to router.py:
  from app.api.v1.routes import safety
  api_router.include_router(safety.router, prefix="/safety", tags=["safety"])
"""
from fastapi import APIRouter
router = APIRouter()


@router.post("/check-relevance")
async def check_relevance(body: dict):
    """
    Check if generated DITA is relevant to the Jira issue.
    Called automatically after every generation.
    Returns relevance score + warnings + recommendation.
    """
    try:
        from app.services.author_safety_service import check_relevance
        issue   = body.get("issue", {})
        content = body.get("content", "")
        dtype   = body.get("dita_type", "task")
        if not issue or not content:
            return {"error": "issue and content required"}
        result = check_relevance(issue, content, dtype)
        return result.to_dict()
    except Exception as e:
        return {"error": str(e)}


@router.post("/save-version")
async def save_version(body: dict):
    """
    Save a new version of a DITA file.
    Called on every edit, generate, and approve action.
    """
    try:
        from app.services.author_safety_service import save_version
        entry = save_version(
            issue_key = body.get("issue_key", ""),
            filename  = body.get("filename", ""),
            content   = body.get("content", ""),
            author    = body.get("author", "unknown"),
            action    = body.get("action", "edited"),
            comment   = body.get("comment", ""),
        )
        return {"version": entry.version, "ai_percent": entry.ai_percent, "timestamp": entry.timestamp}
    except Exception as e:
        return {"error": str(e)}


@router.get("/version-history/{issue_key}/{filename}")
async def version_history(issue_key: str, filename: str):
    """Get full version history for a DITA file."""
    try:
        from app.services.author_safety_service import get_version_history
        return {"history": get_version_history(issue_key, filename)}
    except Exception as e:
        return {"error": str(e)}


@router.get("/version-diff/{issue_key}/{filename}")
async def version_diff(issue_key: str, filename: str, v1: int = 1, v2: int = 2):
    """Get diff between two versions."""
    try:
        from app.services.author_safety_service import get_version_diff
        return get_version_diff(issue_key, filename, v1, v2)
    except Exception as e:
        return {"error": str(e)}


@router.get("/audit-log/{issue_key}")
async def audit_log(issue_key: str):
    """Get full audit log for an issue — every AI and human action tracked."""
    try:
        from app.services.author_safety_service import get_audit_log
        return {"entries": get_audit_log(issue_key)}
    except Exception as e:
        return {"error": str(e)}


@router.post("/approve")
async def approve(body: dict):
    """Author approves a DITA file for publishing."""
    try:
        from app.services.author_safety_service import approve_file
        record = approve_file(
            issue_key   = body.get("issue_key", ""),
            filename    = body.get("filename", ""),
            approved_by = body.get("approved_by", "author"),
            notes       = body.get("notes", ""),
        )
        return record.to_dict()
    except Exception as e:
        return {"error": str(e)}


@router.post("/reject")
async def reject(body: dict):
    """Author rejects a DITA file — blocks publishing until revised."""
    try:
        from app.services.author_safety_service import reject_file
        record = reject_file(
            issue_key        = body.get("issue_key", ""),
            filename         = body.get("filename", ""),
            rejected_by      = body.get("rejected_by", "author"),
            rejection_reason = body.get("reason", ""),
        )
        return record.to_dict()
    except Exception as e:
        return {"error": str(e)}


@router.get("/approval-status/{issue_key}/{filename}")
async def approval_status(issue_key: str, filename: str):
    """Check approval status before publishing."""
    try:
        from app.services.author_safety_service import get_approval_status
        return get_approval_status(issue_key, filename)
    except Exception as e:
        return {"error": str(e)}


@router.post("/scratch-mode")
async def scratch_mode(body: dict):
    """
    Author rejects AI and starts from scratch.
    Returns a clean DITA template for the appropriate topic type.
    """
    try:
        from app.services.author_safety_service import start_scratch_mode
        return start_scratch_mode(
            issue_key = body.get("issue_key", ""),
            dita_type = body.get("dita_type", "task"),
            author    = body.get("author", "author"),
        )
    except Exception as e:
        return {"error": str(e)}
