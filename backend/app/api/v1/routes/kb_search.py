"""Jira knowledge-base browse/search endpoints (SQLite only — no Chroma dependency)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from sqlalchemy import func

from app.core.auth import CurrentUser, UserIdentity
from app.db.jira_enrichment_models import JiraEnrichedIssue
from app.db.jira_enrichment_repository import search_jira_kb
from app.db.session import SessionLocal

router = APIRouter()


@router.get("/search")
def kb_search(
    q: Optional[str] = None,
    domain: Optional[str] = None,
    output: Optional[str] = None,
    entity: Optional[str] = None,
    issue_type: Optional[str] = None,
    limit: int = 100,
    user: UserIdentity = CurrentUser,
):
    """
    Search the indexed Jira knowledge base.

    Query params:
    - **q**: keyword substring (matches summary, description, entities, outputs, features)
    - **domain**: exact domain slug (e.g. `native_pdf`, `publishing`, `unknown`)
    - **output**: substring match inside affected_outputs (e.g. `Native PDF`, `AEM Sites`)
    - **entity**: substring match inside dita_entities (e.g. `conkeyref`, `xref`)
    - **issue_type**: substring match on issue type (e.g. `Bug`, `Customer Request`)
    - **limit**: max results (1–500, default 100)
    """
    del user
    limit = max(1, min(limit, 500))
    db = SessionLocal()
    try:
        results = search_jira_kb(
            db,
            q=q or None,
            domain=domain or None,
            output=output or None,
            entity=entity or None,
            issue_type=issue_type or None,
            limit=limit,
        )
    finally:
        db.close()
    return {"total": len(results), "results": results}


@router.get("/domains")
def kb_domains(user: UserIdentity = CurrentUser):
    """List all distinct domains and their ticket counts in the indexed knowledge base."""
    del user
    db = SessionLocal()
    try:
        rows = (
            db.query(JiraEnrichedIssue.domain, func.count(JiraEnrichedIssue.id).label("count"))
            .group_by(JiraEnrichedIssue.domain)
            .order_by(func.count(JiraEnrichedIssue.id).desc())
            .all()
        )
        total = db.query(JiraEnrichedIssue).count()
    finally:
        db.close()
    return {
        "total_indexed": total,
        "domains": [{"domain": r[0] or "unknown", "count": r[1]} for r in rows],
    }


@router.get("/stats")
def kb_stats(user: UserIdentity = CurrentUser):
    """Summary statistics of the indexed knowledge base."""
    del user
    db = SessionLocal()
    try:
        total = db.query(JiraEnrichedIssue).count()
        by_domain = (
            db.query(JiraEnrichedIssue.domain, func.count(JiraEnrichedIssue.id))
            .group_by(JiraEnrichedIssue.domain)
            .order_by(func.count(JiraEnrichedIssue.id).desc())
            .all()
        )
        by_type = (
            db.query(JiraEnrichedIssue.issue_type, func.count(JiraEnrichedIssue.id))
            .group_by(JiraEnrichedIssue.issue_type)
            .order_by(func.count(JiraEnrichedIssue.id).desc())
            .all()
        )
        by_priority = (
            db.query(JiraEnrichedIssue.priority, func.count(JiraEnrichedIssue.id))
            .group_by(JiraEnrichedIssue.priority)
            .order_by(func.count(JiraEnrichedIssue.id).desc())
            .all()
        )
    finally:
        db.close()
    return {
        "total_indexed": total,
        "by_domain": [{"domain": r[0] or "unknown", "count": r[1]} for r in by_domain],
        "by_issue_type": [{"issue_type": r[0] or "unknown", "count": r[1]} for r in by_type],
        "by_priority": [{"priority": r[0] or "unknown", "count": r[1]} for r in by_priority],
    }
