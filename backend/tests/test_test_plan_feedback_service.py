import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.test_plan_feedback_models import TestPlanQualityFeedback
from app.services.test_plan_feedback_service import (
    list_test_plan_feedback,
    record_test_plan_feedback,
    summarize_test_plan_quality,
)


PLAN = "a" * 64
SNAPSHOT = f"evidence:GUIDES-900:{'b' * 64}"
AC = "c" * 64


@pytest.fixture
def feedback_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'feedback.db'}")
    Base.metadata.create_all(engine, tables=[TestPlanQualityFeedback.__table__])
    Session = sessionmaker(bind=engine, autoflush=True, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _record(session, **overrides):
    values = {
        "tenant_id": "kone",
        "jira_key": "GUIDES-900",
        "correlation_id": "run-1",
        "plan_fingerprint": PLAN,
        "evidence_snapshot_id": SNAPSHOT,
        "event_type": "review_decision",
        "actor_id": "qe@example.com",
        "decision": "QE_APPROVED",
    }
    values.update(overrides)
    return record_test_plan_feedback(session, **values)


def test_feedback_is_idempotent_append_only_and_hides_actor_identity(feedback_session):
    first = _record(
        feedback_session,
        idempotency_key="review-guides-900",
        payload={
            "review_status": "approved by qe@example.com",
            "unapproved_raw_comment": "must never persist",
        },
    )
    feedback_session.commit()
    second = _record(
        feedback_session,
        idempotency_key="review-guides-900",
        payload={"review_status": "different retry body"},
    )

    assert first["created"] is True
    assert second["created"] is False
    assert feedback_session.query(TestPlanQualityFeedback).count() == 1
    assert "actor_hash" not in first
    assert first["payload"] == {"review_status": "approved by [redacted-email]"}
    assert first["redaction_count"] == 1

    row = feedback_session.query(TestPlanQualityFeedback).one()
    row.decision = "REJECTED"
    with pytest.raises(ValueError, match="append-only"):
        feedback_session.flush()
    feedback_session.rollback()

    row = feedback_session.query(TestPlanQualityFeedback).one()
    feedback_session.delete(row)
    with pytest.raises(ValueError, match="append-only"):
        feedback_session.flush()


def test_feedback_contract_rejects_untraceable_or_incomplete_events(feedback_session):
    with pytest.raises(ValueError, match="plan_fingerprint"):
        _record(feedback_session, plan_fingerprint="not-a-hash")
    with pytest.raises(ValueError, match="evidence_snapshot_id"):
        _record(feedback_session, evidence_snapshot_id="missing")
    with pytest.raises(ValueError, match="ac_edit requires"):
        _record(feedback_session, event_type="ac_edit", decision="")
    with pytest.raises(ValueError, match="execution_outcome requires ac_id"):
        _record(
            feedback_session,
            event_type="execution_outcome",
            decision="",
            outcome="PASS",
        )
    with pytest.raises(ValueError, match="escaped_jira_key"):
        _record(
            feedback_session,
            event_type="escaped_defect",
            decision="",
            payload={"severity": "P1"},
        )


def test_quality_summary_surfaces_failures_edits_and_escaped_defects_as_candidates(feedback_session):
    _record(feedback_session)
    _record(
        feedback_session,
        event_type="ac_edit",
        decision="",
        ac_id="UAC-01",
        ac_fingerprint=AC,
        before_hash="d" * 64,
        after_hash="e" * 64,
        payload={"changed_fields": ["then"], "human_accepted": True},
    )
    _record(
        feedback_session,
        event_type="execution_outcome",
        decision="",
        ac_id="UAC-01",
        ac_fingerprint=AC,
        outcome="FAIL",
        payload={"environment": "cloud", "duration_ms": 1234},
    )
    _record(
        feedback_session,
        event_type="escaped_defect",
        decision="",
        payload={
            "escaped_jira_key": "GUIDES-901",
            "severity": "P1",
            "root_cause_category": "missing negative oracle",
        },
    )
    feedback_session.commit()

    rows = list_test_plan_feedback(
        feedback_session,
        tenant_id="kone",
        jira_key="GUIDES-900",
    )
    summary = summarize_test_plan_quality(
        feedback_session,
        tenant_id="kone",
        jira_key="GUIDES-900",
        plan_fingerprint=PLAN,
    )

    assert len(rows) == 4
    assert summary["review_decisions"] == {"QE_APPROVED": 1}
    assert summary["ac_edit_count"] == 1
    assert summary["execution_outcomes"] == {"FAIL": 1}
    assert summary["execution_pass_rate"] == 0.0
    assert summary["failed_ac_ids"] == ["UAC-01"]
    assert summary["escaped_defect_count"] == 1
    assert "escaped_defect_recorded" in summary["quality_flags"]
    assert summary["learning_policy"]["automatic_authority_promotion"] is False
    assert {item["signal"] for item in summary["candidate_learning_signals"]} == {
        "human_ac_edits",
        "failed_acceptance_criteria",
        "escaped_defects",
    }
