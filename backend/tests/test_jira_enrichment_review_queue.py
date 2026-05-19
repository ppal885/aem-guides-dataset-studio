"""Weak Jira enrichment review queue."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.db.base import Base
from app.db.jira_enrichment_models import JiraEnrichedIssue, JiraEnrichmentReviewQueue, JiraIssueChunk
from app.db.jira_enrichment_repository import (
    list_enrichment_review_queue,
    upsert_jira_issue,
    weak_enrichment_review_reasons,
)


def _session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=eng,
        tables=[
            JiraEnrichedIssue.__table__,
            JiraIssueChunk.__table__,
            JiraEnrichmentReviewQueue.__table__,
        ],
    )
    return sessionmaker(bind=eng, autoflush=False, autocommit=False)()


def test_weak_reasons_or_semantics():
    doc = JiraEnrichedDocument(
        jira_key="X-1",
        domain="unknown",
        dita_entities=["concept"],
        missing_info=["a", "b", "c"],
    )
    assert weak_enrichment_review_reasons(doc) == ["domain_unknown"]

    doc2 = JiraEnrichedDocument(
        jira_key="X-2",
        domain="publishing",
        dita_entities=[],
        missing_info=[],
    )
    assert weak_enrichment_review_reasons(doc2) == ["entities_empty"]

    doc3 = JiraEnrichedDocument(
        jira_key="X-3",
        domain="publishing",
        dita_entities=["map"],
        missing_info=["a", "b", "c", "d"],
    )
    assert weak_enrichment_review_reasons(doc3) == ["missing_info_gt_3"]

    doc4 = JiraEnrichedDocument(
        jira_key="X-4",
        domain="publishing",
        dita_entities=["map"],
        missing_info=["a"],
    )
    assert weak_enrichment_review_reasons(doc4) == []


def test_upsert_inserts_review_row_when_weak():
    s = _session()
    try:
        doc = JiraEnrichedDocument(
            jira_key="GUIDES-WEAK-1",
            summary="s",
            domain="unknown",
            dita_entities=[],
            missing_info=["a", "b", "c", "d"],
            raw_text="raw body",
            sub_domain="native_pdf",
        )
        upsert_jira_issue(s, doc)
        s.commit()
        qrows = s.query(JiraEnrichmentReviewQueue).all()
        assert len(qrows) == 1
        assert qrows[0].jira_key == "GUIDES-WEAK-1"
        assert "domain_unknown" in qrows[0].reason
        assert "entities_empty" in qrows[0].reason
        assert "missing_info_gt_3" in qrows[0].reason
        assert qrows[0].suggested_domain == "native_pdf"
    finally:
        s.close()


def test_list_enrichment_review_queue_descending():
    s = _session()
    try:
        d1 = JiraEnrichedDocument(jira_key="A-1", domain="unknown", raw_text="t1")
        d2 = JiraEnrichedDocument(jira_key="A-2", domain="unknown", raw_text="t2")
        upsert_jira_issue(s, d1)
        upsert_jira_issue(s, d2)
        s.commit()
        items = list_enrichment_review_queue(s, limit=10)
        assert len(items) == 2
        assert items[0]["jira_key"] == "A-2"
        assert items[1]["jira_key"] == "A-1"
    finally:
        s.close()
