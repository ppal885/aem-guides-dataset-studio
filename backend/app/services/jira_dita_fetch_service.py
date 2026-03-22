"""Fetch JIRA issues for DITA analysis pipeline."""
from typing import Optional

from app.services.jira_client import JiraClient, extract_description_from_issue
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


def fetch_jira_issues(
    jql: str,
    max_results: int = 50,
    jira_client: Optional[JiraClient] = None,
    fetch_comments: bool = True,
) -> list[dict]:
    """
    Fetch JIRA issues with full fields for DITA analysis.
    Returns list of dicts: {issue_key, summary, description, labels, comments, priority, status, created, updated}.
    """
    client = jira_client or JiraClient()
    has_auth = (client.username and client.password) or (client.email and client.api_token)
    if not client.base_url or not has_auth:
        logger.warning_structured("Jira client not configured for DITA fetch", extra_fields={"jql": jql[:80]})
        return []

    try:
        issues = client.search_issues_with_fields(
            jql,
            fields="summary,description,labels,priority,status,created,updated,issuetype,components",
            max_results=max_results,
        )
    except Exception as e:
        logger.error_structured(
            "Jira search failed for DITA analysis",
            extra_fields={"jql": jql[:80], "error": str(e)},
            exc_info=True,
        )
        return []

    result = []
    for raw in issues:
        key = raw.get("key")
        if not key:
            continue
        fields = raw.get("fields", {}) or {}
        summary = (fields.get("summary") or "")[:10000]
        description = extract_description_from_issue(raw)
        labels = fields.get("labels") or []
        if not isinstance(labels, list):
            labels = []
        priority = ""
        pr = fields.get("priority")
        if isinstance(pr, dict) and pr.get("name"):
            priority = pr["name"]
        status = ""
        st = fields.get("status")
        if isinstance(st, dict) and st.get("name"):
            status = st["name"]
        created = fields.get("created") or ""
        updated = fields.get("updated") or ""

        comments = []
        if fetch_comments:
            try:
                raw_comments = client.get_issue_comments(key)
                comments = [
                    {"body_text": c.get("body_text", ""), "author": c.get("author", ""), "created": c.get("created", "")}
                    for c in raw_comments
                ]
            except Exception as e:
                logger.debug_structured(
                    "Failed to fetch comments for issue",
                    extra_fields={"issue_key": key, "error": str(e)},
                )

        issue_type = ""
        issue_type_field = fields.get("issuetype")
        if isinstance(issue_type_field, dict) and issue_type_field.get("name"):
            issue_type = issue_type_field["name"]
        components = [
            item.get("name", "")
            for item in (fields.get("components") or [])
            if isinstance(item, dict) and item.get("name")
        ]

        result.append({
            "issue_key": key,
            "summary": summary,
            "description": description,
            "labels": labels,
            "comments": comments,
            "priority": priority,
            "status": status,
            "issue_type": issue_type,
            "components": components,
            "created": created,
            "updated": updated,
        })

    return result
