"""Bounded, fresh SQL lineage checks; synthetic graph, no Jira or vector I/O."""
from types import SimpleNamespace

from fastapi import HTTPException
from pydantic import BaseModel
import pytest

from app.services import shared_uac_learning_service as service
from test_shared_uac_learning import approval, capture, db as learning_db, person


def node(identifier, *dependencies):
    return SimpleNamespace(tenant_id="team", lesson_id=identifier, version=2,
        actor_id="qe", state="APPROVED", payload={
            "source_case_ids": ["TEST-1"], "delta_ids": [identifier, *dependencies],
            "human_approval": {"reviewer_id": "qe", "authorization": {
                "policy": "LIVE_JIRA_QE_ASSIGNEE", "jira_key": "TEST-1",
                "checked_at": "2026-09-06T00:00:00+00:00"}},
            "supporting_lesson_revisions": [{"lesson_id": dep, "version": 2} for dep in dependencies]})


def test_overlapping_support_graph_is_memoized_only_within_one_decision(monkeypatch):
    rows = {"leaf": node("leaf")}
    previous = ["leaf"]
    for level in range(12):
        current = [f"left-{level}", f"right-{level}"]
        rows.update({name: node(name, *previous) for name in current})
        previous = current
    root = node("root", *previous)
    calls = []

    def latest(session, tenant, identifier):
        calls.append(identifier)
        return rows.get(identifier)

    monkeypatch.setattr(service, "_latest", latest)
    monkeypatch.setattr(service, "_source_policy", lambda case: {"status": "ELIGIBLE"})
    assert service._eligible_reviewed_revision(None, "team", root)
    assert len(calls) == len(rows)
    assert len(set(calls)) == len(calls)
    rows["leaf"].state = "REVOKED"
    calls.clear()
    assert not service._eligible_reviewed_revision(None, "team", root)
    assert "leaf" in calls  # No cross-request cached approval.


def test_cyclic_and_over_budget_lineage_fails_closed(monkeypatch):
    rows = {"first": node("first", "second"), "second": node("second", "first")}
    monkeypatch.setattr(service, "_latest", lambda session, tenant, key: rows.get(key))
    monkeypatch.setattr(service, "_source_policy", lambda case: {"status": "ELIGIBLE"})
    assert not service._eligible_reviewed_revision(None, "team", rows["first"])
    rows["second"] = node("second")
    assert not service._eligible_reviewed_revision(None, "team", rows["first"],
        _context={"memo": {}, "latest": {}, "remaining": 1})
    assert service._eligible_reviewed_revision(None, "team", rows["first"])


def test_different_tenant_or_proofless_history_cannot_become_eligible(monkeypatch):
    row = node("legacy")
    monkeypatch.setattr(service, "_source_policy", lambda case: {"status": "ELIGIBLE"})
    assert not service._eligible_reviewed_revision(None, "other-team", row)
    row.payload["human_approval"].pop("authorization")
    assert not service._eligible_reviewed_revision(None, "team", row)


def test_publication_validation_error_does_not_echo_internal_input(learning_db, monkeypatch):
    from app.api.v1.routes.test_plan_learning import _write
    from app.services.shared_learning_pattern_provider import SharedLearningPatternLibraryProvider

    class InternalRecord(BaseModel):
        field: int

    def reject_internal_record(*args):
        InternalRecord.model_validate({"field": "sensitive-note-never-echo"})

    receipt = capture(learning_db)
    monkeypatch.setattr(SharedLearningPatternLibraryProvider, "_record", reject_internal_record)
    with pytest.raises(HTTPException) as error:
        _write(learning_db, service.review_lesson, user=person(),
            feedback_id=receipt["feedback_id"], body=approval())
    assert error.value.status_code == 400
    assert error.value.detail == "Reviewed lesson does not satisfy the shared publication contract."
    assert "sensitive-note-never-echo" not in str(error.value)
    assert service.get_feedback_status(learning_db, user=person(), tenant_id="kone",
        feedback_id=receipt["feedback_id"])["learning_status"] == "CANDIDATE"
