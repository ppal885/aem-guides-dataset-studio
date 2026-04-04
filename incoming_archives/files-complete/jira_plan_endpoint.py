"""
ADD THIS ENDPOINT TO backend/app/api/v1/routes/jira.py
(paste after the existing /search and /issue endpoints)
"""

# ── Add this import at top of jira.py ────────────────────────────────────────
# from app.services.dita_authoring_planner import create_dita_authoring_plan


@router.post("/plan")
async def plan_dita_for_issue(body: dict):
    """
    Planning agent — analyzes a Jira issue and returns a structured DITA plan.
    Author reviews and approves the plan BEFORE generation starts.

    Input:  { "issue_key": "AEM-123" }
            OR pass the full issue dict directly to skip re-fetching
    Output: DitaAuthoringPlan as dict
    """
    try:
        from app.services.dita_authoring_planner import create_dita_authoring_plan

        # Accept either just issue_key or full issue dict
        issue = body.get("issue") or {}
        issue_key = body.get("issue_key") or issue.get("issue_key", "")

        # Fetch from Jira if only key provided
        if not issue and issue_key:
            from app.services.jira_client import JiraClient, extract_description_from_issue
            jira = JiraClient()
            raw = jira.get_issue(issue_key)
            fields = raw.get("fields", {})
            issue = {
                "issue_key": raw.get("key"),
                "summary": fields.get("summary", ""),
                "description": extract_description_from_issue(raw),
                "issue_type": fields.get("issuetype", {}).get("name", ""),
                "status": fields.get("status", {}).get("name", ""),
                "priority": fields.get("priority", {}).get("name", ""),
                "labels": fields.get("labels", []),
                "comments": [],
            }
            # Fetch comments for richer planning
            try:
                comments = jira.get_issue_comments(issue_key)
                issue["comments"] = comments
            except Exception:
                pass

        if not issue:
            return {"error": "issue_key or issue dict required"}

        plan = await create_dita_authoring_plan(issue)
        return plan.to_dict()

    except Exception as e:
        return {"error": str(e), "topics": []}
