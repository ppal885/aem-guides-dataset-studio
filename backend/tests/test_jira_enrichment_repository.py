"""Tests for ``jira_enrichment_repository`` (SQLite in-memory, isolated tables)."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.jira_enrichment_models import JiraEnrichedIssue, JiraEnrichmentReviewQueue, JiraIssueChunk
from app.db.jira_enrichment_repository import (
    get_jira_by_key,
    insert_jira_chunks,
    search_by_metadata,
    upsert_jira_issue,
)
from app.services.jira_enrichment_service import enrich_jira


def _session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=eng,
        tables=[JiraEnrichedIssue.__table__, JiraIssueChunk.__table__, JiraEnrichmentReviewQueue.__table__],
    )
    return sessionmaker(bind=eng, autoflush=False, autocommit=False)()


def test_upsert_insert_get_search():
    s = _session()
    try:
        issue = {
            "key": "GUIDES-501",
            "fields": {
                "summary": "Native PDF fails for Cisco baseline",
                "description": "conref to keyref in ditaval",
                "issuetype": {"name": "Bug"},
                "status": {"name": "Open"},
                "priority": {"name": "High"},
                "labels": ["cisco", "customer-topcon"],
                "components": [{"name": "Publishing"}],
            },
        }
        doc = enrich_jira(issue)
        upsert_jira_issue(s, doc)
        rows = [
            {
                "chunk_id": "GUIDES-501::full_ticket_summary::0",
                "document": "body",
                "metadata": {"chunk_type": "full_ticket_summary", "enrich_domain": doc.domain},
            }
        ]
        n = insert_jira_chunks(s, "GUIDES-501", rows, enrichment=doc)
        assert n == 1
        s.commit()

        got = get_jira_by_key(s, "GUIDES-501")
        assert got is not None
        assert got["jira_key"] == "GUIDES-501"
        assert got["domain"] == doc.domain

        hits = search_by_metadata(s, domain=doc.domain, customer="Cisco", limit=10)
        assert any(r.jira_key == "GUIDES-501" for r in hits)

        hits2 = search_by_metadata(s, entities=["conref"], limit=10)
        assert any(r.jira_key == "GUIDES-501" for r in hits2)
    finally:
        s.close()


def test_insert_replaces_chunks():
    s = _session()
    try:
        issue = {
            "key": "GUIDES-502",
            "fields": {
                "summary": "Second",
                "description": "desc",
                "issuetype": {"name": "Task"},
                "status": {"name": "Open"},
                "priority": {"name": "Low"},
                "labels": [],
                "components": [],
            },
        }
        doc = enrich_jira(issue)
        upsert_jira_issue(s, doc)
        insert_jira_chunks(
            s,
            "GUIDES-502",
            [
                {"chunk_id": "GUIDES-502::a::0", "document": "one", "metadata": {"chunk_type": "a"}},
                {"chunk_id": "GUIDES-502::b::0", "document": "two", "metadata": {"chunk_type": "b"}},
            ],
            enrichment=doc,
        )
        s.commit()
        assert s.query(JiraIssueChunk).filter(JiraIssueChunk.jira_key == "GUIDES-502").count() == 2

        insert_jira_chunks(
            s,
            "GUIDES-502",
            [{"chunk_id": "GUIDES-502::c::0", "document": "three", "metadata": {"chunk_type": "c"}}],
            enrichment=doc,
        )
        s.commit()
        assert s.query(JiraIssueChunk).filter(JiraIssueChunk.jira_key == "GUIDES-502").count() == 1
    finally:
        s.close()
