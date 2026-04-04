"""
Intent Routes — intent suggestion and confirmation before generation.
Add to router.py:
  from app.api.v1.routes import intent
  api_router.include_router(intent.router, prefix="/intent", tags=["intent"])
"""
from fastapi import APIRouter
router = APIRouter()


@router.post("/suggest")
async def suggest_intent(body: dict):
    """
    Step 0 of authoring flow — before research, before generation.
    Called immediately when author selects a Jira issue.

    Returns 2-3 intent suggestions for author to confirm.

    Input:  { "issue_key": "AEM-456" } OR { "issue": {...} }
    Output: {
      "suggestions": [
        { "intent_type": "troubleshooting_task", "label": "Troubleshooting task",
          "confidence": 0.85, "is_primary": true, ... },
        { "intent_type": "release_note", ... }
      ],
      "suggested_title": "Resolve Keyref in Nested Keyscope",
      "original_title":  "Keyref not resolving in nested keyscope"
    }
    """
    try:
        from app.services.intent_translator import get_intent_suggestions, transform_summary_to_title
        from app.services.jira_client import JiraClient, extract_description_from_issue

        issue = body.get("issue") or {}
        issue_key = body.get("issue_key") or issue.get("issue_key", "")

        # Fetch if only key given
        if not issue.get("summary") and issue_key:
            jira   = JiraClient()
            raw    = jira.get_issue(issue_key)
            fields = raw.get("fields", {})
            issue  = {
                "issue_key":   raw.get("key"),
                "summary":     fields.get("summary", ""),
                "description": extract_description_from_issue(raw),
                "issue_type":  fields.get("issuetype", {}).get("name", ""),
                "labels":      fields.get("labels", []),
                "components":  [c.get("name","") for c in fields.get("components", [])],
                "fix_versions":[v.get("name","") for v in fields.get("fixVersions", [])],
                "comments":    [],
            }

        suggestions = get_intent_suggestions(issue)

        # Suggest transformed title using top intent
        top_intent      = suggestions[0]["intent_type"] if suggestions else "configuration_task"
        suggested_title = transform_summary_to_title(issue.get("summary", ""), top_intent)

        return {
            "suggestions":     suggestions,
            "suggested_title": suggested_title,
            "original_title":  issue.get("summary", ""),
        }

    except Exception as e:
        return {"error": str(e), "suggestions": []}


@router.post("/confirm")
async def confirm_intent(body: dict):
    """
    Author confirms intent and (optionally) edits the title.
    Returns full AuthoringIntent ready for generation.

    Input:
    {
      "issue_key":       "AEM-456",
      "issue":           { ...full issue dict... },
      "chosen_intent":   "troubleshooting_task",
      "custom_title":    "Resolve Keyref in Nested Keyscope",  // optional
      "research_context": "..."  // optional, from query executor
    }

    Output: AuthoringIntent dict — passed directly to generate-dita endpoint
    """
    try:
        from app.services.intent_translator import translate_intent

        issue             = body.get("issue", {})
        chosen_intent     = body.get("chosen_intent", "")
        custom_title      = body.get("custom_title", "")
        research_context  = body.get("research_context", "")

        if not issue and body.get("issue_key"):
            from app.services.jira_client import JiraClient, extract_description_from_issue
            jira   = JiraClient()
            raw    = jira.get_issue(body["issue_key"])
            fields = raw.get("fields", {})
            issue  = {
                "issue_key":   raw.get("key"),
                "summary":     fields.get("summary", ""),
                "description": extract_description_from_issue(raw),
                "issue_type":  fields.get("issuetype", {}).get("name", ""),
                "labels":      fields.get("labels", []),
                "components":  [c.get("name","") for c in fields.get("components", [])],
                "fix_versions":[v.get("name","") for v in fields.get("fixVersions", [])],
                "comments":    [],
            }

        intent = await translate_intent(
            issue            = issue,
            chosen_intent    = chosen_intent or None,
            custom_title     = custom_title or None,
            research_context = research_context,
        )

        return intent.to_dict()

    except Exception as e:
        return {"error": str(e)}


@router.post("/preview-title")
async def preview_title(body: dict):
    """
    Live title preview as author types.
    Called on every keystroke in the title field.

    Input:  { "summary": "Keyref not resolving", "intent_type": "troubleshooting_task" }
    Output: { "title": "Resolve Keyref Issue" }
    """
    try:
        from app.services.intent_translator import transform_summary_to_title
        title = transform_summary_to_title(
            body.get("summary", ""),
            body.get("intent_type", "configuration_task"),
        )
        return {"title": title}
    except Exception as e:
        return {"error": str(e), "title": body.get("summary", "")}
