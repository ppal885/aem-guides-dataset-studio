"""Append-only quality feedback for evidence-backed test plans."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, UniqueConstraint, event

from app.db.base import Base


class TestPlanQualityFeedback(Base):
    __test__ = False

    __tablename__ = "test_plan_quality_feedback"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_test_plan_quality_feedback_idempotency"),
        Index("ix_test_plan_feedback_jira_created", "jira_key", "created_at"),
        Index("ix_test_plan_feedback_plan_created", "plan_fingerprint", "created_at"),
        Index("ix_test_plan_feedback_event_created", "event_type", "created_at"),
        Index("ix_test_plan_feedback_tenant_jira", "tenant_id", "jira_key"),
    )

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(120), nullable=False, default="kone")
    jira_key = Column(String(64), nullable=False)
    correlation_id = Column(String(160), nullable=True)
    plan_fingerprint = Column(String(64), nullable=False)
    evidence_snapshot_id = Column(String(180), nullable=False)
    event_type = Column(String(40), nullable=False)
    actor_hash = Column(String(64), nullable=False)
    ac_id = Column(String(120), nullable=True)
    ac_fingerprint = Column(String(64), nullable=True)
    decision = Column(String(50), nullable=True)
    outcome = Column(String(50), nullable=True)
    before_hash = Column(String(64), nullable=True)
    after_hash = Column(String(64), nullable=True)
    payload = Column(JSON, nullable=False, default=dict)
    redaction_count = Column(Integer, nullable=False, default=0)
    idempotency_key = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


def _reject_mutation(_mapper, _connection, _target) -> None:
    raise ValueError("Test-plan quality feedback is append-only and cannot be changed or deleted.")


event.listen(TestPlanQualityFeedback, "before_update", _reject_mutation)
event.listen(TestPlanQualityFeedback, "before_delete", _reject_mutation)
