"""
Agent routes — 3 trigger types for the AEM release agent.
Add to: backend/app/api/v1/routes/agent.py
Register in router.py: api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
"""
from fastapi import APIRouter, BackgroundTasks, Request

router = APIRouter()


# ── TRIGGER 1: Webhook ────────────────────────────────────────────────────────
@router.post("/aem-release")
async def webhook_aem_release(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook trigger — Adobe/AEM fires this when new release drops.

    Configure in Adobe Admin Console:
    Webhook URL: https://your-server.com/api/v1/agent/aem-release
    Events: content.published, release.created

    Also works as manual trigger from UI.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    version = (
        body.get("version")
        or body.get("release_version")
        or body.get("data", {}).get("version")
    )

    # Run in background so webhook returns immediately (< 200ms)
    background_tasks.add_task(_run_agent_background, version)

    return {
        "status":    "accepted",
        "message":   "AEM release agent triggered via webhook",
        "version":   version or "detecting...",
        "triggered_at": __import__("datetime").datetime.utcnow().isoformat(),
    }


# ── TRIGGER 2: Manual / UI button ────────────────────────────────────────────
@router.post("/check-aem-release")
async def manual_check_release(background_tasks: BackgroundTasks):
    """
    Manual trigger — user clicks "Check for updates" in UI.
    Returns immediately, runs agent in background.
    Frontend polls /agent/status for results.
    """
    background_tasks.add_task(_run_agent_background, None)
    return {
        "status":  "started",
        "message": "Checking for new AEM releases...",
        "poll_url": "/api/v1/agent/status",
    }


# ── TRIGGER 3: Force re-index (manual override) ───────────────────────────────
@router.post("/force-reindex")
async def force_reindex(background_tasks: BackgroundTasks, body: dict = {}):
    """
    Force re-index regardless of whether new release detected.
    Use when you want to refresh RAG manually.
    """
    version = body.get("version")
    background_tasks.add_task(_force_reindex_background, version)
    return {
        "status":  "started",
        "message": "Force re-indexing AEM documentation into RAG...",
        "poll_url": "/api/v1/agent/status",
    }


# ── Status endpoint (frontend polls this) ────────────────────────────────────
@router.get("/status")
async def get_agent_status():
    """
    Get current agent state.
    Frontend polls this after triggering agent to show results.
    """
    try:
        from app.services.aem_release_agent import get_agent_status
        return get_agent_status()
    except Exception as e:
        return {"error": str(e)}


# ── Background task helpers ───────────────────────────────────────────────────

async def _run_agent_background(version=None):
    """Run full release agent in background."""
    try:
        from app.services.aem_release_agent import run_aem_release_agent
        result = await run_aem_release_agent()
        from app.core.structured_logging import get_structured_logger
        get_structured_logger(__name__).info_structured(
            "Agent background run complete",
            extra_fields=result,
        )
    except Exception as e:
        from app.core.structured_logging import get_structured_logger
        get_structured_logger(__name__).error_structured(
            "Agent background run failed",
            extra_fields={"error": str(e)},
        )


async def _force_reindex_background(version=None):
    """Force re-index in background."""
    try:
        from app.services.aem_release_agent import auto_index_new_release
        await auto_index_new_release(version=version)
    except Exception as e:
        from app.core.structured_logging import get_structured_logger
        get_structured_logger(__name__).error_structured(
            "Force reindex failed",
            extra_fields={"error": str(e)},
        )
