"""Immutable shared feedback records and a recoverable indexing outbox."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, DDL, ForeignKey, Index, Integer, String, Text, UniqueConstraint, event

from app.db.base import Base


def utcnow():
    return datetime.now(timezone.utc)


class ImmutableRecord:
    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(120), nullable=False, index=True)
    actor_id = Column(String(160), nullable=False)
    idempotency_key = Column(String(64), nullable=False, unique=True)
    request_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class UacLearningDraft(ImmutableRecord, Base):
    __tablename__ = "uac_learning_drafts"
    __table_args__ = (Index("ix_uac_draft_binding", "tenant_id", "jira_key", "plan_fingerprint"),)
    jira_key = Column(String(64), nullable=False)
    plan_fingerprint = Column(String(64), nullable=False)
    evidence_bundle_id = Column(String(180), nullable=False, default="")
    run_id = Column(String(160), nullable=False, default="")
    content = Column(JSON, nullable=False)


class UacFeedbackDelta(ImmutableRecord, Base):
    __tablename__ = "uac_feedback_deltas"
    __table_args__ = (Index("ix_uac_delta_issue_created", "tenant_id", "jira_key", "created_at"),)
    jira_key = Column(String(64), nullable=False)
    plan_fingerprint = Column(String(64), nullable=False, default="")
    raw_feedback = Column(Text, nullable=False)
    proposed_correction = Column(Text, nullable=False, default="")
    delta_type = Column(String(80), nullable=False)
    content = Column(JSON, nullable=False)


class UacFeedbackBinding(ImmutableRecord, Base):
    __tablename__ = "uac_feedback_bindings"
    delta_id = Column(String(36), ForeignKey("uac_feedback_deltas.id"), nullable=False, unique=True)
    draft_id = Column(String(36), ForeignKey("uac_learning_drafts.id"), nullable=False)


class UacLessonRevision(ImmutableRecord, Base):
    __tablename__ = "uac_lesson_revisions"
    __table_args__ = (
        UniqueConstraint("lesson_id", "version", name="uq_uac_lesson_version"),
        Index("ix_uac_lesson_current", "tenant_id", "lesson_id", "version"),
    )
    lesson_id = Column(String(36), ForeignKey("uac_feedback_deltas.id"), nullable=False)
    version = Column(Integer, nullable=False)
    state = Column(String(30), nullable=False)
    payload = Column(JSON, nullable=False)


class UacLearningOutbox(Base):
    __tablename__ = "uac_learning_outbox"
    __table_args__ = (Index("ix_uac_outbox_ready", "tenant_id", "status", "next_attempt_at"),)
    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(120), nullable=False)
    revision_id = Column(String(36), ForeignKey("uac_lesson_revisions.id"), nullable=False, unique=True)
    status = Column(String(30), nullable=False, default="PENDING")
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(String(200), nullable=False, default="")
    lease_owner = Column(String(36), nullable=True)
    lease_until = Column(DateTime(timezone=True), nullable=True)
    next_attempt_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    indexed_at = Column(DateTime(timezone=True), nullable=True)


IMMUTABLE_MODELS = (UacLearningDraft, UacFeedbackDelta, UacFeedbackBinding, UacLessonRevision)


def _reject_mutation(*_args):
    raise ValueError("Shared UAC learning records are immutable; append a new revision.")


for _model in IMMUTABLE_MODELS:
    event.listen(_model, "before_update", _reject_mutation)
    event.listen(_model, "before_delete", _reject_mutation)
    # SQLite create_all is used by development and isolated tests. Production
    # PostgreSQL receives equivalent enforcement through the Alembic migration.
    for _operation in ("UPDATE", "DELETE"):
        event.listen(_model.__table__, "after_create", DDL(
            f"CREATE TRIGGER IF NOT EXISTS {_model.__tablename__}_no_{_operation.lower()} "
            f"BEFORE {_operation} ON {_model.__tablename__} BEGIN "
            "SELECT RAISE(ABORT, 'Shared UAC learning records are immutable'); END"
        ).execute_if(dialect="sqlite"))
