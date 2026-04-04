"""
User Preferences Routes
Register in router.py:
  from app.api.v1.routes import preferences
  api_router.include_router(preferences.router, prefix="/prefs", tags=["preferences"])
"""
from fastapi import APIRouter
router = APIRouter()


@router.get("/session/{author_id}")
async def get_session(author_id: str = "default"):
    """
    Called when platform loads — restores last session.
    Returns: last issue, preferred dita type, recent issues, stats.
    """
    try:
        from app.services.user_preferences_service import get_session_restore
        return get_session_restore(author_id)
    except Exception as e:
        return {"error": str(e)}


@router.get("/{author_id}")
async def get_prefs(author_id: str = "default"):
    """Get full preferences for an author."""
    try:
        from app.services.user_preferences_service import get_prefs
        return get_prefs(author_id)
    except Exception as e:
        return {"error": str(e)}


@router.post("/author")
async def set_author(body: dict):
    """Set author name and email."""
    try:
        from app.services.user_preferences_service import set_author_name
        return set_author_name(
            author_id    = body.get("author_id", "default"),
            display_name = body.get("display_name", ""),
            email        = body.get("email", ""),
        )
    except Exception as e:
        return {"error": str(e)}


@router.post("/last-issue")
async def remember_issue(body: dict):
    """
    Called every time author selects an issue or changes stage.
    Persists so next session restores where they left off.
    """
    try:
        from app.services.user_preferences_service import remember_last_issue
        return remember_last_issue(
            author_id     = body.get("author_id", "default"),
            issue_key     = body.get("issue_key", ""),
            issue_summary = body.get("issue_summary", ""),
            dita_type     = body.get("dita_type", "task"),
            stage         = body.get("stage", "idle"),
        )
    except Exception as e:
        return {"error": str(e)}


@router.post("/dita-type")
async def set_dita_pref(body: dict):
    """Author sets: for Bug issues, always generate task topics."""
    try:
        from app.services.user_preferences_service import set_dita_type_preference
        return set_dita_type_preference(
            author_id       = body.get("author_id", "default"),
            jira_issue_type = body.get("jira_issue_type", "Bug"),
            dita_type       = body.get("dita_type", "task"),
        )
    except Exception as e:
        return {"error": str(e)}


@router.post("/save-query")
async def save_query(body: dict):
    """Author saves a custom query template for reuse."""
    try:
        from app.services.user_preferences_service import save_custom_query
        return save_custom_query(
            author_id = body.get("author_id", "default"),
            category  = body.get("category", "aem_guides"),
            query     = body.get("query", ""),
            purpose   = body.get("purpose", ""),
        )
    except Exception as e:
        return {"error": str(e)}


@router.post("/ui")
async def update_ui(body: dict):
    """Update a single UI preference (tab, compact mode, quality threshold)."""
    try:
        from app.services.user_preferences_service import update_ui_pref
        return update_ui_pref(
            author_id = body.get("author_id", "default"),
            key       = body.get("key", ""),
            value     = body.get("value"),
        )
    except Exception as e:
        return {"error": str(e)}


@router.post("/record")
async def record_action(body: dict):
    """Track author action stats (generated, approved, rejected, scratch)."""
    try:
        from app.services.user_preferences_service import record_generation
        return record_generation(
            author_id = body.get("author_id", "default"),
            action    = body.get("action", "generated"),
        )
    except Exception as e:
        return {"error": str(e)}
