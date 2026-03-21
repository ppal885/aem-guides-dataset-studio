"""Jira routes for the Authoring page."""
from fastapi import APIRouter

router = APIRouter()


@router.post("/search")
async def search_jira_issues(body: dict):
    """Search Jira issues by JQL. Used by Authoring page left panel."""
    try:
        from backend.app.services.jira_dita_fetch_service import fetch_jira_issues
        jql = body.get("jql", "assignee = currentUser() ORDER BY updated DESC")
        max_results = int(body.get("max_results", 30))
        issues = fetch_jira_issues(jql, max_results=max_results, fetch_comments=False)
        return {"issues": issues}
    except Exception as e:
        return {"issues": [], "error": str(e)}


@router.get("/issue/{issue_key}")
async def get_jira_issue(issue_key: str):
    """Fetch a single Jira issue by key e.g. AEM-123."""
    try:
        from backend.app.services.jira_client import JiraClient, extract_description_from_issue
        jira = JiraClient()
        issue = jira.get_issue(issue_key)
        fields = issue.get("fields", {})
        return {
            "issue_key": issue.get("key"),
            "summary": fields.get("summary", ""),
            "description": extract_description_from_issue(issue),
            "issue_type": fields.get("issuetype", {}).get("name", ""),
            "status": fields.get("status", {}).get("name", ""),
            "priority": fields.get("priority", {}).get("name", ""),
            "labels": fields.get("labels", []),
        }
    except Exception as e:
        return {"error": str(e)}


@router.post("/comment")
async def post_comment_to_jira(body: dict):
    """Post a comment back to a Jira issue after DITA generation."""
    try:
        from backend.app.services.jira_client import JiraClient
        issue_key = body.get("issue_key", "")
        comment = body.get("comment", "")
        if not issue_key or not comment:
            return {"error": "issue_key and comment are required"}
        jira = JiraClient()
        jira._request(
            "POST",
            f"/rest/api/{jira._api}/issue/{issue_key}/comment",
            json_data={"body": comment},
        )
        return {"success": True, "issue_key": issue_key}
    except Exception as e:
        return {"success": False, "error": str(e)}
