"""Jira routes for the Authoring page."""
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app.api.v1.routes._api_errors import raise_api_error
from app.core.auth import CurrentUser, UserIdentity

router = APIRouter()


def _public_issue_payload(issue: dict) -> dict:
    attachments = []
    for att in issue.get("attachments") or []:
        if not isinstance(att, dict):
            continue
        attachment_id = str(att.get("id") or "")
        filename = str(att.get("filename") or "")
        download_url = ""
        if attachment_id and filename:
            download_url = f"/api/v1/jira/attachment/{issue.get('issue_key')}/{attachment_id}/{quote(filename)}"

        attachments.append(
            {
                **att,
                "stored_path": "",
                "download_url": download_url,
            }
        )

    return {
        **issue,
        "attachments": attachments,
    }


@router.post("/search")
async def search_jira_issues(request: Request, body: dict, user: UserIdentity = CurrentUser):
    """Search Jira issues by JQL. Used by Authoring page left panel."""
    try:
        from app.services.jira_dita_fetch_service import fetch_jira_issues
        from app.services.tenant_service import build_jira_client, get_authorized_tenant_id

        tenant_id = get_authorized_tenant_id(request, user)
        jql = body.get("jql", "assignee = currentUser() ORDER BY updated DESC")
        max_results = int(body.get("max_results", 30))
        issues = fetch_jira_issues(
            jql,
            max_results=max_results,
            jira_client=build_jira_client(tenant_id),
            fetch_comments=False,
        )
        return {"issues": issues}
    except Exception as exc:
        raise_api_error(exc, default_detail="Failed to search Jira issues")


@router.get("/issue/{issue_key}")
async def get_jira_issue(request: Request, issue_key: str, user: UserIdentity = CurrentUser):
    """Fetch a single Jira issue by key e.g. AEM-123."""
    try:
        from app.services.jira_issue_context_service import load_issue_context
        from app.services.tenant_service import build_jira_client, get_authorized_tenant_id

        jira = build_jira_client(get_authorized_tenant_id(request, user))
        issue = load_issue_context(issue_key, jira_client=jira, include_comments=True, download_media=True)
        return _public_issue_payload(issue)
    except Exception as exc:
        raise_api_error(exc, default_detail=f"Failed to fetch Jira issue '{issue_key}'")


@router.get("/attachment/{issue_key}/{attachment_id}/{filename:path}")
async def download_jira_attachment(
    request: Request,
    issue_key: str,
    attachment_id: str,
    filename: str,
    user: UserIdentity = CurrentUser,
):
    """Download a cached Jira attachment for authoring inspection."""
    try:
        from app.services.jira_issue_context_service import load_issue_context
        from app.services.tenant_service import build_jira_client, get_authorized_tenant_id

        jira = build_jira_client(get_authorized_tenant_id(request, user))
        issue = load_issue_context(issue_key, jira_client=jira, include_comments=False, download_media=True)
        attachment = next(
            (
                item
                for item in issue.get("attachments") or []
                if str(item.get("id")) == attachment_id and str(item.get("filename")) == filename
            ),
            None,
        )
        if not attachment or not attachment.get("stored_path"):
            raise FileNotFoundError(f"Attachment '{filename}' is not available")

        return FileResponse(
            path=str(attachment["stored_path"]),
            filename=filename,
            media_type=attachment.get("mime_type") or None,
        )
    except Exception as exc:
        raise_api_error(exc, default_detail=f"Failed to download attachment '{filename}'")


@router.post("/comment")
async def post_comment_to_jira(request: Request, body: dict, user: UserIdentity = CurrentUser):
    """Post a comment back to a Jira issue after DITA generation."""
    try:
        from app.services.tenant_service import build_jira_client, get_authorized_tenant_id

        issue_key = body.get("issue_key", "")
        comment = body.get("comment", "")
        if not issue_key or not comment:
            raise ValueError("issue_key and comment are required")
        jira = build_jira_client(get_authorized_tenant_id(request, user))
        jira._request(
            "POST",
            f"/rest/api/{jira._api}/issue/{issue_key}/comment",
            json_data={"body": comment},
        )
        return {"success": True, "issue_key": issue_key}
    except Exception as exc:
        raise_api_error(exc, default_detail="Failed to post Jira comment")


@router.post("/query-plan")
async def generate_query_plan_endpoint(request: Request, body: dict, user: UserIdentity = CurrentUser):
    """Generate research queries for an issue before running retrieval."""
    try:
        from app.services.jira_issue_context_service import issue_has_full_context, load_issue_context
        from app.services.query_planner import generate_query_plan
        from app.services.tenant_service import build_jira_client, get_authorized_tenant_id

        issue = body.get("issue") or {}
        issue_key = body.get("issue_key") or issue.get("issue_key", "")
        tenant_id = get_authorized_tenant_id(request, user)
        if issue_key and (not issue.get("summary") or not issue_has_full_context(issue)):
            jira = build_jira_client(tenant_id)
            issue = load_issue_context(issue_key, jira_client=jira, issue=issue, include_comments=True, download_media=True)
        if not issue:
            raise ValueError("issue_key or issue is required")
        plan = await generate_query_plan(issue, tenant_id=tenant_id)
        return plan.to_dict()
    except Exception as exc:
        raise_api_error(exc, default_detail="Failed to generate authoring query plan")


@router.post("/execute-queries")
async def execute_queries_endpoint(request: Request, body: dict, user: UserIdentity = CurrentUser):
    """Execute approved research queries and return a structured context."""
    try:
        from app.services.query_executor import execute_query_plan
        from app.services.tenant_service import get_authorized_tenant_id

        issue_key = body.get("issue_key", "unknown")
        queries = body.get("queries", [])
        approved = [query for query in queries if query.get("approved", True)]
        if not approved:
            raise ValueError("No approved queries to execute")
        context = await execute_query_plan(
            issue_key=issue_key,
            approved_queries=approved,
            tenant_id=get_authorized_tenant_id(request, user),
        )
        return context.to_dict()
    except Exception as exc:
        raise_api_error(exc, default_detail="Failed to execute authoring research queries")
