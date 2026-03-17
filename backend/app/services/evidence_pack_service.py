"""Evidence pack builder - primary issue + similar issues + attachment excerpts."""
from typing import Optional

from sqlalchemy.orm import Session

from app.db.jira_models import JiraIssue
from app.services.jira_index_service import upsert_issue, upsert_attachments, upsert_comments
from app.services.jira_similarity_service import find_similar_issues
from app.core.agentic_config import agentic_config
from app.services.jira_attachment_service import enrich_attachments_with_excerpts
from app.services.jira_client import JiraClient
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


def _primary_dict_from_db_issue(issue: JiraIssue) -> dict:
    """Build primary dict from JiraIssue (DB fallback when Jira get_issue 404s)."""
    comments = []
    if issue.comments_json:
        try:
            import json
            comments = json.loads(issue.comments_json)
            if not isinstance(comments, list):
                comments = []
        except (json.JSONDecodeError, TypeError):
            comments = []
    return {
        "issue_key": issue.issue_key,
        "summary": issue.summary or "",
        "description": issue.description or "",
        "description_excerpt": (issue.description or "")[:1000] or (issue.summary or "")[:200],
        "issue_type": issue.issue_type or "",
        "status": issue.status or "",
        "priority": issue.priority or "",
        "components": issue.components_json,
        "labels": issue.labels_json,
        "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
        "attachments": [],
        "comments": comments,
    }


def build_evidence_pack(
    session: Session,
    issue_key: str,
    similar_k: int = 5,
    jira_client: Optional[JiraClient] = None,
) -> dict:
    """
    Build evidence pack: primary issue + similar issues + attachment excerpts.
    Upserts primary and similar issues/attachments into DB.
    Tries DB first (for recently indexed issues); falls back to DB when Jira get_issue returns 404.
    """
    client = jira_client or JiraClient()

    primary_issue = session.query(JiraIssue).filter(JiraIssue.issue_key == issue_key).first()
    if not primary_issue:
        try:
            primary_issue = upsert_issue(session, issue_key, jira_client)
        except Exception as e:
            err_str = str(e).lower()
            if "404" in err_str or "not found" in err_str:
                primary_issue = session.query(JiraIssue).filter(JiraIssue.issue_key == issue_key).first()
                if primary_issue:
                    logger.info_structured(
                        "Using DB fallback for evidence pack (Jira 404)",
                        extra_fields={"issue_key": issue_key},
                    )
            else:
                raise

    if not primary_issue:
        return {"primary": None, "similar": [], "stats": {"error": "Primary issue not found"}}

    upsert_attachments(session, issue_key, max_attachments=10, jira_client=jira_client)
    upsert_comments(session, issue_key, jira_client=jira_client)
    session.refresh(primary_issue)
    primary_attachments = enrich_attachments_with_excerpts(
        session, issue_key, max_files=agentic_config.attachment_max_files, jira_client=jira_client
    )

    primary_dict = _primary_dict_from_db_issue(primary_issue)
    primary_dict["attachments"] = primary_attachments

    query_text = primary_issue.text_for_search or primary_issue.summary or ""
    similar_rows = find_similar_issues(
        session,
        query_text,
        k=similar_k,
        exclude_issue_key=issue_key,
        primary_components_json=primary_issue.components_json,
    )

    similar_list = []
    for row in similar_rows:
        sk = row.get("issue_key")
        if not sk:
            continue
        sim_attachments = enrich_attachments_with_excerpts(
            session, sk, max_files=2, jira_client=jira_client
        )
        similar_list.append({
            "issue_key": sk,
            "summary": row.get("summary"),
            "description_excerpt": (row.get("description") or "")[:500],
            "components": row.get("components_json"),
            "labels": row.get("labels_json"),
            "updated_at": row.get("updated_at"),
            "attachments": sim_attachments,
        })

    return {
        "primary": primary_dict,
        "similar": similar_list,
        "stats": {
            "primary_attachments": len(primary_attachments),
            "similar_count": len(similar_list),
        },
    }
