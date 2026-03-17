"""Jira indexing service for storing issues and attachments in DB."""
import json
import os
import re
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.db.jira_models import JiraIssue, JiraAttachment
from app.services.jira_client import JiraClient
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

USE_JIRA_EMBEDDING = os.getenv("USE_JIRA_EMBEDDING", "true").lower() in ("true", "1", "yes")


def build_text_for_search(issue_dict: dict) -> str:
    """Build searchable text from issue fields."""
    parts = []
    fields = issue_dict.get("fields", {})

    summary = fields.get("summary") or ""
    if summary:
        parts.append(str(summary))

    description = fields.get("description")
    if description:
        if isinstance(description, dict) and "content" in description:
            for block in description.get("content", []):
                if block.get("type") == "paragraph":
                    for c in block.get("content", []):
                        if c.get("type") == "text" and "text" in c:
                            parts.append(c["text"])
        else:
            parts.append(str(description))

    issuetype = fields.get("issuetype", {})
    if isinstance(issuetype, dict) and issuetype.get("name"):
        parts.append(issuetype["name"])

    components = fields.get("components") or []
    if components:
        comp_names = [c.get("name") for c in components if isinstance(c, dict) and c.get("name")]
        parts.extend(comp_names)

    labels = fields.get("labels") or []
    if labels:
        parts.extend(labels)

    text = " ".join(parts)
    return re.sub(r"\s+", " ", text).strip()


def _update_embedding_for_issue(issue: JiraIssue) -> None:
    """Pre-index embedding for an issue when text_for_search is set. Updates issue.embedding_json in place."""
    if not USE_JIRA_EMBEDDING or not issue.text_for_search or not issue.text_for_search.strip():
        return
    try:
        from app.services.embedding_service import embed_query, is_embedding_available

        if not is_embedding_available():
            return
        emb = embed_query(issue.text_for_search[:8000])
        if emb is not None:
            issue.embedding_json = json.dumps(emb.tolist() if hasattr(emb, "tolist") else list(emb))
    except Exception as e:
        logger.warning_structured(
            "Jira embedding skipped",
            extra_fields={"issue_key": issue.issue_key, "error": str(e)},
        )


def _parse_updated(updated_str: Optional[str]) -> Optional[datetime]:
    """Parse Jira updated datetime string (ISO format)."""
    if not updated_str:
        return None
    try:
        s = str(updated_str)
        if "+" in s:
            s = s.split("+")[0].rstrip("Z")
        elif "Z" in s:
            s = s.replace("Z", "")
        return datetime.fromisoformat(s.replace("Z", ""))
    except Exception as e:
        logger.debug("Failed to parse Jira updated string", extra_fields={"updated_str": str(updated_str)[:50], "error": str(e)})
        return None


def upsert_issue(session: Session, issue_key: str, jira_client: Optional[JiraClient] = None) -> Optional[JiraIssue]:
    """Upsert a Jira issue into the database."""
    client = jira_client or JiraClient()
    has_auth = (client.username and client.password) or (client.email and client.api_token)
    if not client.base_url or not has_auth:
        logger.warning_structured("Jira client not configured", extra_fields={"issue_key": issue_key})
        return None

    try:
        issue_data = client.get_issue(issue_key)
    except Exception as e:
        logger.error_structured(
            "Failed to fetch Jira issue",
            extra_fields={"issue_key": issue_key, "error": str(e)},
            exc_info=True,
        )
        raise

    fields = issue_data.get("fields", {})
    text_for_search = build_text_for_search(issue_data)

    summary = (fields.get("summary") or "")
    if isinstance(summary, str):
        summary = summary[:10000]

    description_raw = fields.get("description")
    description = ""
    if description_raw:
        if isinstance(description_raw, dict) and "content" in description_raw:
            for block in description_raw.get("content", []):
                if block.get("type") == "paragraph":
                    for c in block.get("content", []):
                        if c.get("type") == "text" and "text" in c:
                            description += c["text"] + " "
        else:
            description = str(description_raw)[:50000]

    issue_type = ""
    it = fields.get("issuetype")
    if isinstance(it, dict) and it.get("name"):
        issue_type = it["name"]

    status = ""
    st = fields.get("status")
    if isinstance(st, dict) and st.get("name"):
        status = st["name"]

    priority = ""
    pr = fields.get("priority")
    if isinstance(pr, dict) and pr.get("name"):
        priority = pr["name"]

    components = fields.get("components") or []
    components_json = json.dumps([c.get("name", "") for c in components if isinstance(c, dict)])

    labels = fields.get("labels") or []
    labels_json = json.dumps(labels if isinstance(labels, list) else [])

    updated_at = _parse_updated(fields.get("updated"))

    existing = session.query(JiraIssue).filter(JiraIssue.issue_key == issue_key).first()
    if existing:
        existing.summary = summary
        existing.description = description
        existing.issue_type = issue_type
        existing.status = status
        existing.priority = priority
        existing.components_json = components_json
        existing.labels_json = labels_json
        existing.updated_at = updated_at
        existing.text_for_search = text_for_search
        _update_embedding_for_issue(existing)
        session.merge(existing)
        return existing

    issue = JiraIssue(
        issue_key=issue_key,
        summary=summary,
        description=description,
        issue_type=issue_type,
        status=status,
        priority=priority,
        components_json=components_json,
        labels_json=labels_json,
        updated_at=updated_at,
        text_for_search=text_for_search,
    )
    _update_embedding_for_issue(issue)
    session.add(issue)
    return issue


def upsert_attachments(
    session: Session,
    issue_key: str,
    max_attachments: int = 10,
    jira_client: Optional[JiraClient] = None,
) -> list[JiraAttachment]:
    """Upsert attachment metadata for an issue (stored_path initially empty)."""
    client = jira_client or JiraClient()
    if not client.base_url:
        return []

    try:
        attachments_data = client.get_issue_attachments(issue_key)
    except Exception as e:
        logger.warning_structured(
            "Failed to fetch attachments",
            extra_fields={"issue_key": issue_key, "error": str(e)},
        )
        return []

    result = []
    for att in attachments_data[:max_attachments]:
        if not isinstance(att, dict):
            continue
        att_id = att.get("id") or str(uuid.uuid4())
        filename = att.get("filename") or "unknown"
        mime_type = att.get("mimeType") or ""
        size_bytes = att.get("size") or 0
        content_url = att.get("content") or ""

        existing = session.query(JiraAttachment).filter(JiraAttachment.id == att_id).first()
        if existing:
            existing.filename = filename
            existing.mime_type = mime_type
            existing.size_bytes = size_bytes
            existing.jira_url = content_url
            result.append(existing)
            continue

        attachment = JiraAttachment(
            id=att_id,
            issue_key=issue_key,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            jira_url=content_url,
            stored_path=None,
        )
        session.add(attachment)
        result.append(attachment)

    return result


def upsert_comments(
    session: Session,
    issue_key: str,
    jira_client: Optional[JiraClient] = None,
) -> int:
    """Fetch and store comments for an issue. Returns count of comments stored."""
    client = jira_client or JiraClient()
    if not client.base_url:
        return 0

    try:
        comments = client.get_issue_comments(issue_key)
    except Exception as e:
        logger.warning_structured(
            "Failed to fetch comments",
            extra_fields={"issue_key": issue_key, "error": str(e)},
        )
        return 0

    if not comments:
        return 0

    stored = [{"body_text": c.get("body_text", ""), "author": c.get("author", ""), "created": c.get("created", "")} for c in comments]
    comments_json = json.dumps(stored)

    existing = session.query(JiraIssue).filter(JiraIssue.issue_key == issue_key).first()
    if not existing:
        logger.warning_structured(
            "Cannot store comments: issue not indexed",
            extra_fields={"issue_key": issue_key},
        )
        return 0

    existing.comments_json = comments_json
    comment_texts = " ".join(c.get("body_text", "") for c in stored)
    if comment_texts:
        existing_text = existing.text_for_search or ""
        if comment_texts[:2000] not in existing_text:
            existing.text_for_search = (existing_text + " " + comment_texts[:5000]).strip()[:15000]
            _update_embedding_for_issue(existing)
    session.merge(existing)
    return len(stored)


def index_recent_issues(
    session: Session,
    jql: str,
    limit: int = 500,
    jira_client: Optional[JiraClient] = None,
    fetch_attachments: bool = False,
) -> dict:
    """Index recent issues by JQL. Uses search result directly (no per-issue get_issue) for speed.
    Attachments are skipped by default; set fetch_attachments=True to fetch (slower)."""
    client = jira_client or JiraClient()
    has_auth = (client.username and client.password) or (client.email and client.api_token)
    if not client.base_url or not has_auth:
        return {"indexed": 0, "error": "Jira not configured"}

    try:
        issues = client.search_issues(jql, max_results=limit)
    except Exception as e:
        logger.error_structured(
            "Jira search failed",
            extra_fields={"jql": jql, "error": str(e)},
            exc_info=True,
        )
        return {"indexed": 0, "error": str(e)}

    indexed = 0
    for issue_data in issues:
        key = issue_data.get("key")
        if not key:
            continue
        try:
            upsert_issue_from_search_result(session, issue_data)
            if fetch_attachments:
                upsert_attachments(session, key, max_attachments=10, jira_client=jira_client)
            indexed += 1
        except Exception as e:
            logger.warning_structured(
                "Failed to index issue",
                extra_fields={"issue_key": key, "error": str(e)},
            )

    return {"indexed": indexed, "total_fetched": len(issues)}


def upsert_issue_from_search_result(session: Session, issue_data: dict) -> Optional[JiraIssue]:
    """
    Upsert a Jira issue from search API response (no get_issue call).
    Use when get_issue returns 404 but search returns the issue.
    """
    key = issue_data.get("key")
    if not key:
        return None
    fields = issue_data.get("fields", {})
    summary = (fields.get("summary") or "")[:10000]
    status = ""
    if isinstance(fields.get("status"), dict) and fields["status"].get("name"):
        status = fields["status"]["name"]
    issue_type = ""
    if isinstance(fields.get("issuetype"), dict) and fields["issuetype"].get("name"):
        issue_type = fields["issuetype"]["name"]
    text_for_search = f"{summary} {status} {issue_type}".strip()

    existing = session.query(JiraIssue).filter(JiraIssue.issue_key == key).first()
    if existing:
        existing.summary = summary
        existing.status = status
        existing.issue_type = issue_type
        existing.text_for_search = text_for_search
        _update_embedding_for_issue(existing)
        session.merge(existing)
        return existing

    issue = JiraIssue(
        issue_key=key,
        summary=summary,
        description=None,
        issue_type=issue_type,
        status=status,
        priority="",
        components_json="[]",
        labels_json="[]",
        updated_at=None,
        text_for_search=text_for_search,
    )
    _update_embedding_for_issue(issue)
    session.add(issue)
    return issue
