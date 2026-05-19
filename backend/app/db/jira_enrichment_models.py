"""SQLAlchemy models for enriched Jira metadata + per-chunk rows (separate from legacy `jira_issues`)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import JSON

from app.db.base import Base


class CustomerAlias(Base):
    """Optional map from raw alias (lowercased in API) to canonical customer display name."""

    __tablename__ = "customer_aliases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alias = Column(String(120), nullable=False, unique=True, index=True)
    canonical_name = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class JiraEnrichedIssue(Base):
    """
    Enriched Jira issue row for SQL-side filtering (domain, customers, entities).
    Table name avoids collision with legacy `jira_issues` used by JiraIssue ORM.
    """

    __tablename__ = "jira_enriched_issues"
    __table_args__ = (UniqueConstraint("jira_key", name="uq_jira_enriched_issues_jira_key"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    jira_key = Column(String(50), nullable=False, index=True)
    summary = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    issue_type = Column(String(120), nullable=True)
    status = Column(String(120), nullable=True)
    priority = Column(String(120), nullable=True)
    labels = Column(JSON, nullable=True)  # list[str]; JSONB on PostgreSQL
    components = Column(JSON, nullable=True)
    customer_names = Column(JSON, nullable=True)
    domain = Column(String(80), nullable=False, index=True, default="unknown")
    sub_domain = Column(String(120), nullable=True, index=True)
    affected_outputs = Column(JSON, nullable=True)
    affected_features = Column(JSON, nullable=True)
    dita_entities = Column(JSON, nullable=True)
    symptoms = Column(JSON, nullable=True)
    expected_behavior = Column(Text, nullable=True)
    actual_behavior = Column(Text, nullable=True)
    qa_risk_tags = Column(JSON, nullable=True)
    automation_fit = Column(String(200), nullable=True)
    missing_info = Column(JSON, nullable=True)
    raw_text = Column(Text, nullable=True)
    customer_detection_debug = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    indexed_at = Column(DateTime, nullable=True, index=True)


class JiraEnrichmentReviewQueue(Base):
    """Weak Jira enrichment cases queued for manual taxonomy / rules review."""

    __tablename__ = "jira_enrichment_review_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    jira_key = Column(String(50), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    raw_text = Column(Text, nullable=True)
    suggested_domain = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class JiraIssueChunk(Base):
    """Denormalized chunk row linked to enriched issue (for metadata filters without joining JSON blobs)."""

    __tablename__ = "jira_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    jira_key = Column(
        String(50),
        ForeignKey("jira_enriched_issues.jira_key", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_type = Column(String(80), nullable=False, index=True)
    chunk_text = Column(Text, nullable=False)
    domain = Column(String(80), nullable=True, index=True)
    customer_names = Column(JSON, nullable=True)
    affected_outputs = Column(JSON, nullable=True)
    dita_entities = Column(JSON, nullable=True)
    # Serialized float list when pgvector is not used; use JSON for cross-dialect consistency.
    embedding = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
