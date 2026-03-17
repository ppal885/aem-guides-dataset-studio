"""Database models for Jira indexing."""
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey
from app.db.base import Base


class JiraIssue(Base):
    """Jira issue model for indexing and search."""

    __tablename__ = "jira_issues"

    issue_key = Column(String(50), primary_key=True)
    summary = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    issue_type = Column(String(50), nullable=True)
    status = Column(String(50), nullable=True)
    priority = Column(String(50), nullable=True)
    components_json = Column(Text, nullable=True)  # JSON as string for SQLite
    labels_json = Column(Text, nullable=True)  # JSON as string for SQLite
    updated_at = Column(DateTime, nullable=True)
    text_for_search = Column(Text, nullable=True)
    embedding_json = Column(Text, nullable=True)  # JSON array of floats for semantic search
    comments_json = Column(Text, nullable=True)  # JSON array of {body_text, author, created}
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)


class JiraAttachment(Base):
    """Jira attachment metadata."""

    __tablename__ = "jira_attachments"

    id = Column(String(36), primary_key=True)
    issue_key = Column(String(50), ForeignKey("jira_issues.issue_key"), nullable=False)
    filename = Column(String(500), nullable=False)
    mime_type = Column(String(100), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    jira_url = Column(Text, nullable=True)
    stored_path = Column(Text, nullable=True)
    text_excerpt = Column(Text, nullable=True)
    text_search_blob = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)
