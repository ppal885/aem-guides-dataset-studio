"""Approval/consumer parity and interleaved obsolete-index cleanup regressions."""
import pytest

from app.core.schemas_qe_pattern_mcp import ResolveQePatternsRequest, SharedLearningContext
from app.core.schemas_shared_uac_learning import UacLessonReview, UacSupportGroup
from app.db.shared_uac_learning_models import UacFeedbackDelta, UacLearningOutbox, UacLessonRevision
from app.services import shared_uac_learning_service as service
from app.services.shared_learning_pattern_provider import resolve_shared_learning
from test_shared_uac_learning import approval, capture, db as learning_db, person


def _lesson_with_support(primary_jira, support_jira, support_id):
    body = approval(jira=primary_jira, idempotency_key="approve-derived")
    body.lesson.supporting_delta_ids = [support_id]
    body.lesson.independent_support_groups = [
        UacSupportGroup(group_id="primary-case", case_ids=[primary_jira]),
        UacSupportGroup(group_id="support-case", case_ids=[support_jira]),
    ]
    return body


def test_multiline_reviewed_guidance_is_consumable_without_rewriting_human_source(learning_db):
    raw = "Keep the saved configuration.\nVerify the selected output."
    receipt = capture(learning_db, raw_feedback=raw)
    body = approval()
    body.lesson.guidance = "Check the saved configuration.\n\tVerify the generated output."
    reviewed = service.review_lesson(learning_db, user=person(),
        feedback_id=receipt["feedback_id"], body=body)
    learning_db.commit()
    assert reviewed["learning_status"] == "APPROVED"
    assert reviewed["lesson"]["guidance"] == "Check the saved configuration. Verify the generated output."
    assert learning_db.query(UacFeedbackDelta).one().raw_feedback == raw
    lesson = reviewed["lesson"]
    response = resolve_shared_learning(ResolveQePatternsRequest(
        domain=lesson["domains"][0], change_surfaces=lesson["surfaces"],
        abstract_signals=lesson["signals"], subject_terms=lesson["scope"]["subject_terms"]),
        SharedLearningContext(tenant_id="kone", principal_id="reader", authenticated=True, mode="ENABLED"),
        loader=lambda **kwargs: service.load_shared_learning_publication(session=learning_db, **kwargs))
    assert response.status == "SUCCESS" and len(response.matched_patterns) == 1


def test_invalid_final_consumer_contract_never_creates_approved_revision(learning_db):
    receipt = capture(learning_db)
    body = approval()
    body.lesson.guidance = " \n\t "
    with pytest.raises(ValueError, match="bounded guidance"):
        service.review_lesson(learning_db, user=person(), feedback_id=receipt["feedback_id"], body=body)
    learning_db.commit()
    assert learning_db.query(UacLessonRevision).count() == 1
    assert learning_db.query(UacLearningOutbox).count() == 1
    assert service.get_feedback_status(learning_db, user=person(), tenant_id="kone",
        feedback_id=receipt["feedback_id"])["learning_status"] == "CANDIDATE"


@pytest.mark.parametrize("decision", ["REVOKE", "SUPERSEDE"])
def test_supporting_delta_requires_own_qe_approval_and_exact_revision_stays_current(
        learning_db, decision):
    primary = capture(learning_db, jira="GUIDES-900", token="primary-correction")
    support = capture(learning_db, jira="GUIDES-901", token="support-correction")
    derived = _lesson_with_support("GUIDES-900", "GUIDES-901", support["feedback_id"])

    with pytest.raises(service.LearningConflict, match="own QE Assignee approval"):
        service.review_lesson(learning_db, user=person(),
            feedback_id=primary["feedback_id"], body=derived)

    support_approval = approval(jira="GUIDES-901", idempotency_key="approve-support")
    service.review_lesson(learning_db, user=person(),
        feedback_id=support["feedback_id"], body=support_approval)
    approved = service.review_lesson(learning_db, user=person(),
        feedback_id=primary["feedback_id"], body=derived)
    learning_db.commit()
    assert approved["lesson"]["supporting_lesson_revisions"] == [
        {"lesson_id": support["feedback_id"], "version": 2}]
    assert approved["reuse_eligible"] is True

    vectors = set()

    def write(row):
        vectors.add((row.lesson_id, row.version))
        return True

    def remove(rows):
        for row in rows:
            vectors.discard((row.lesson_id, row.version))
        return True

    first = service.drain_learning_outbox(tenant_id="kone", session=learning_db,
        index_writer=write, index_remover=remove)
    assert first["indexed"] == 2
    assert (primary["feedback_id"], 2) in vectors

    if decision == "REVOKE":
        change = UacLessonReview(expected_revision=2, decision="REVOKE",
            idempotency_key="invalidate-support", note="Supporting requirement changed.")
    else:
        change = approval(revision=2, jira="GUIDES-901", decision="SUPERSEDE",
            idempotency_key="invalidate-support")
        change.lesson.guidance = "Investigate the revised supporting behavior."
    service.review_lesson(learning_db, user=person(jira_user_key="qe-key-1"),
        feedback_id=support["feedback_id"], body=change)
    learning_db.commit()

    publication = service.load_shared_learning_publication(tenant_id="kone", session=learning_db)
    published_ids = {row["lesson_id"] for row in publication["lessons"]}
    assert primary["feedback_id"] not in published_ids
    if decision == "SUPERSEDE":
        assert support["feedback_id"] in published_ids
    else:
        assert support["feedback_id"] not in published_ids
    primary_status = service.get_feedback_status(learning_db, user=person(), tenant_id="kone",
        feedback_id=primary["feedback_id"])
    assert primary_status["learning_status"] == "APPROVED"
    assert primary_status["reuse_eligible"] is False
    assert primary_status["publication_review_status"] == "RE_REVIEW_REQUIRED"

    service.drain_learning_outbox(tenant_id="kone", session=learning_db,
        index_writer=write, index_remover=remove)
    # SQL is the authority boundary. A stale physical projection may remain, but
    # it is not returned or reused after its exact supporting revision changes.
    assert (primary["feedback_id"], 2) in vectors
    status_after_cleanup = service.get_feedback_status(learning_db, user=person(), tenant_id="kone",
        feedback_id=primary["feedback_id"])
    assert status_after_cleanup["index_status"] == "INDEXED"
    assert status_after_cleanup["reuse_eligible"] is False


@pytest.mark.parametrize("decision", ["REVOKE", "SUPERSEDE"])
def test_delayed_projection_never_writes_derived_lesson_after_support_changes(
        learning_db, decision):
    primary = capture(learning_db, jira="GUIDES-900", token="delayed-primary")
    support = capture(learning_db, jira="GUIDES-901", token="delayed-support")
    service.review_lesson(learning_db, user=person(), feedback_id=support["feedback_id"],
        body=approval(jira="GUIDES-901", idempotency_key="approve-delayed-support"))
    service.review_lesson(learning_db, user=person(), feedback_id=primary["feedback_id"],
        body=_lesson_with_support("GUIDES-900", "GUIDES-901", support["feedback_id"]))

    if decision == "REVOKE":
        change = UacLessonReview(expected_revision=2, decision="REVOKE",
            idempotency_key="change-before-projection", note="Supporting requirement changed.")
    else:
        change = approval(revision=2, jira="GUIDES-901", decision="SUPERSEDE",
            idempotency_key="change-before-projection")
        change.lesson.guidance = "Investigate the revised supporting behavior."
    service.review_lesson(learning_db, user=person(), feedback_id=support["feedback_id"], body=change)
    learning_db.commit()

    written = []
    outcome = service.drain_learning_outbox(tenant_id="kone", session=learning_db,
        index_writer=lambda row: written.append((row.lesson_id, row.version)) or True,
        index_remover=lambda rows: True)
    assert (primary["feedback_id"], 2) not in written
    assert outcome["skipped"] >= 2
    status = service.get_feedback_status(learning_db, user=person(), tenant_id="kone",
        feedback_id=primary["feedback_id"])
    assert status["index_status"] == "SKIPPED"
    assert status["reuse_eligible"] is False
    assert status["publication_review_status"] == "RE_REVIEW_REQUIRED"


def test_stale_revocation_cleanup_cannot_remove_newer_indexed_approval(learning_db, monkeypatch):
    receipt = capture(learning_db)
    feedback_id = receipt["feedback_id"]
    service.review_lesson(learning_db, user=person(), feedback_id=feedback_id, body=approval())
    service.review_lesson(learning_db, user=person(), feedback_id=feedback_id,
        body=UacLessonReview(expected_revision=2, decision="REVOKE",
            idempotency_key="revoke-race", note="The applicability changed."))
    learning_db.commit()
    vectors = set()
    removed = []

    def write(row):
        vectors.add(row.version)
        return True

    def remove(rows):
        for row in rows:
            removed.append(row.version)
            vectors.discard(row.version)
        return True

    original_latest = service._latest
    interleaved = False

    def stale_snapshot_with_newer_worker(session, tenant, lesson_id):
        nonlocal interleaved
        snapshot = original_latest(session, tenant, lesson_id)
        if not interleaved and snapshot.state == "REVOKED":
            interleaved = True
            # Deterministic two-worker ordering: the first worker retains v3,
            # while a newer approval and worker finish v4 before old cleanup.
            service.review_lesson(learning_db, user=person(), feedback_id=feedback_id,
                body=approval(revision=3, idempotency_key="new-approval"))
            learning_db.commit()
            service.drain_learning_outbox(tenant_id="kone", session=learning_db,
                index_writer=write, index_remover=remove)
            assert 4 in vectors
        return snapshot

    monkeypatch.setattr(service, "_latest", stale_snapshot_with_newer_worker)
    service.drain_learning_outbox(tenant_id="kone", session=learning_db, limit=1,
        index_writer=write, index_remover=remove)
    latest = original_latest(learning_db, "kone", feedback_id)
    assert latest.version == 4 and latest.state == "APPROVED"
    assert learning_db.query(UacLearningOutbox).filter_by(revision_id=latest.id).one().status == "INDEXED"
    assert vectors == {4}
    assert 4 not in removed
