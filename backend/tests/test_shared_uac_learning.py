"""Shared learning contracts tested in isolated SQL databases; no live indexing."""
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import JiraReviewIdentity, UserIdentity, get_current_user
from app.core.schemas_shared_uac_learning import (
    UacDraftContent, UacDraftRegistration, UacFeedbackBind, UacFeedbackCapture,
    UacLessonDefinition, UacLessonReview, UacLessonScope, UacSupportGroup,
)
from app.db.base import Base
from app.db.session import get_db
from app.db.shared_uac_learning_models import (
    IMMUTABLE_MODELS, UacFeedbackDelta, UacLearningDraft, UacLearningOutbox, UacLessonRevision,
)
from app.services import shared_uac_learning_service as service


def person(*, id="reviewer-1", roles=("uac_learning_reviewer",), principal_type="human",
           auth_method="token", tenants=("kone",), jira_user_key="qe-key-1",
           jira_account_id="", jira_server="https://jira.example", qe_identity=True):
    jira_identity = None
    if qe_identity:
        jira_identity = JiraReviewIdentity(server_url=jira_server,
            user_key=jira_user_key, account_id=jira_account_id)
    return UserIdentity(id=id, roles=list(roles), principal_type=principal_type,
        auth_method=auth_method, allowed_tenants=list(tenants), jira_identity=jira_identity)


@pytest.fixture
def db(tmp_path, monkeypatch):
    import json
    from app.services import shared_uac_qe_authorization as qe_authorization

    assignments = {}

    def issue_with_names(_client, issue_key, fields=None):
        assignment = assignments.get(issue_key, {"key": "qe-key-1", "accountId": "qe-account-1"})
        assert fields == "customfield_18512,updated"
        return {"key": issue_key, "names": {"customfield_18512": "QE Assignee"},
            "fields": {"customfield_18512": {**assignment, "active": True},
                       # A standard Jira assignee is deliberately unrelated to approval authority.
                       "assignee": {"key": "standard-assignee-key", "active": True},
                       "updated": "2026-09-06T00:00:00+00:00"}}

    monkeypatch.setattr(qe_authorization, "get_tenant", lambda tenant_id: SimpleNamespace(
        jira_url="https://jira.example", jira_email="synthetic@example.com",
        jira_token="synthetic-fixture-token", is_active=tenant_id in {"kone", "team_a"}))
    monkeypatch.setattr(qe_authorization._QeAuthorizationJiraClient,
        "get_issue_with_names", issue_with_names)
    policy = tmp_path / "source-split.json"
    policy.write_text(json.dumps({"schema_version": "aem-guides-human-uac-benchmark-v2",
        "jira_ids": {"train": [], "validation": ["GUIDES-999001"], "blind": ["GUIDES-999002"]}}), encoding="utf-8")
    monkeypatch.setenv("SHARED_UAC_BENCHMARK_SPLIT_MANIFEST", str(policy))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    tables = [model.__table__ for model in IMMUTABLE_MODELS] + [UacLearningOutbox.__table__]
    Base.metadata.create_all(engine, tables=tables)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.info["qe_assignments"] = assignments
        yield session
    engine.dispose()


def capture(db, *, user=None, jira="GUIDES-900", token="capture-1", bound=True, **overrides):
    values = dict(tenant_id="kone", jira_key=jira, idempotency_key=token,
        raw_feedback="The criterion must cover the saved configuration.",
        proposed_correction="Verify output uses the selected configuration.", delta_type="ORACLE_CHANGED")
    if bound:
        values.update(ac_id="UAC-01", draft=UacDraftContent(
            draft_markdown="# Draft\n- UAC-01: Verify the generated output.",
            criteria={"UAC-01": "Verify the generated output."},
            evidence_bundle_id="bundle:" + "b" * 64, run_id="canonical-run-1"))
    values.update(overrides)
    result = service.capture_feedback(db, user=user or person(), body=UacFeedbackCapture(**values))
    db.commit()
    return result


def approval(revision=1, *, jira="GUIDES-900", **overrides):
    from app.core.schemas_canonical_test_plan_runtime import SemanticDimension, IssueDomain, ChangeSurfaceKind, AbstractSignalKind
    lesson = UacLessonDefinition(guidance="Check how configuration changes the expected output.",
        delta_type="ORACLE_CHANGED", families=[next(iter(SemanticDimension)).value],
        domains=[next(iter(IssueDomain)).value], surfaces=[next(iter(ChangeSurfaceKind)).value],
        signals=[next(iter(AbstractSignalKind)).value],
        scope=UacLessonScope(subject_terms=["publishing configuration"]),
        independent_support_groups=[UacSupportGroup(group_id="incident-1", case_ids=[jira])])
    values = dict(expected_revision=revision, idempotency_key="approve-1", decision="APPROVE",
        note="Human source, applicability and counterexamples reviewed.",
        lesson=lesson, origin_confirmed=True, applicability_confirmed=True, counterexamples_checked=True)
    values.update(overrides)
    return UacLessonReview(**values)


def test_capture_preserves_delta_binds_canonical_ids_and_deduplicates(db):
    result = capture(db, raw_feedback="Review by qe@example.com: revise the oracle.")
    assert result["binding_status"] == "BOUND"
    assert result["learning_status"] == "CANDIDATE"
    assert result["index_status"] == "SKIPPED"
    assert "qe@example.com" not in result["raw_feedback"]
    repeated = capture(db, raw_feedback="Review by qe@example.com: revise the oracle.")
    assert repeated["feedback_id"] == result["feedback_id"] and not repeated["created"]
    assert db.query(UacFeedbackDelta).count() == 1
    with pytest.raises(service.LearningConflict, match="different request"):
        capture(db, raw_feedback="Changed retry request")
    draft = db.query(UacLearningDraft).one()
    assert draft.content["source_hash"] == draft.plan_fingerprint
    assert draft.content["content_hash"] == hashlib.sha256(draft.content["draft_markdown"].encode()).hexdigest()
    assert service.load_shared_learning_publication(tenant_id="kone", session=db)["lessons"] == []


def test_classification_field_names_are_redacted_as_well_as_values(db):
    result = capture(db, ai_classification={"secret=synthetic-classification-key": "annotation",
        "notes": "secret=synthetic-classification-value", "api_key": "synthetic-classification-token",
        "reference": "https://synthetic-classification-user:synthetic-classification-pass@example.com/path"})
    assert "synthetic-classification" not in str(result["ai_classification"])
    assert "redacted" in str(result["ai_classification"])


def test_server_authenticated_reviewer_identity_is_not_redacted_away(db):
    reviewer = person(id="named.reviewer@example.com")
    result = capture(db, user=reviewer)
    reviewed = service.review_lesson(db, user=reviewer, feedback_id=result["feedback_id"], body=approval())
    assert reviewed["lesson"]["human_approval"]["reviewer_id"] == reviewer.id
    proof = reviewed["lesson"]["human_approval"]["authorization"]
    assert proof["policy"] == "LIVE_JIRA_QE_ASSIGNEE"
    assert proof["jira_key"] == "GUIDES-900"
    assert proof["field_name"] == "QE Assignee"
    assert proof["identity_kind"] == "user_key"
    assert proof["identity_value"] == "qe-key-1"
    assert reviewed["publication_review_status"] == "QE_APPROVED"
    assert reviewed["reuse_eligible"] is True


def test_pending_capture_can_be_bound_without_rewriting_original_delta(db):
    result = capture(db, bound=False)
    assert result["binding_status"] == "PENDING_BINDING"
    with pytest.raises(service.LearningConflict, match="binding"):
        service.review_lesson(db, user=person(), feedback_id=result["feedback_id"], body=approval())
    registered = service.register_draft(db, user=person(), body=UacDraftRegistration(
        jira_key="GUIDES-900", draft_markdown="A retained draft", idempotency_key="draft-later"))
    bound = service.bind_feedback(db, user=person(), feedback_id=result["feedback_id"],
        body=UacFeedbackBind(draft_id=registered["draft_id"], idempotency_key="bind-later"))
    db.commit()
    assert bound["binding_status"] == "BOUND" and bound["revision"] == 2
    assert bound["plan_fingerprint"] == registered["plan_fingerprint"]
    assert db.query(UacFeedbackDelta).count() == 1


def test_arbitrary_criterion_and_draft_hash_are_rejected(db):
    with pytest.raises(service.LearningConflict, match="criterion"):
        service.register_draft(db, user=person(), body=UacDraftRegistration(jira_key="GUIDES-900",
            idempotency_key="draft-1", draft_markdown="Actual draft", criteria={"UAC-01": "Invented AC"}))
    with pytest.raises(service.LearningConflict, match="fingerprint"):
        service.register_draft(db, user=person(), body=UacDraftRegistration(jira_key="GUIDES-900",
            idempotency_key="draft-2", draft_markdown="Actual draft", plan_fingerprint="a" * 64))


@pytest.mark.parametrize("reviewer", [
    person(roles=("uac_learning_reviewer",), qe_identity=False),
    person(roles=("admin",), qe_identity=False),
    person(roles=("admin",), principal_type="shared"),
    person(roles=("admin",), principal_type="service"),
    person(auth_method="dev_bypass"),
    person(principal_type="unknown"),
    person(jira_user_key="not-the-live-qe"),
])
def test_role_admin_or_submitter_cannot_replace_live_qe_assignment(db, reviewer):
    result = capture(db, user=reviewer)
    with pytest.raises(HTTPException) as error:
        service.review_lesson(db, user=reviewer, feedback_id=result["feedback_id"], body=approval())
    assert error.value.status_code == 403


def test_standard_jira_assignee_is_not_qe_review_authority(db):
    result = capture(db, user=person(qe_identity=False))
    standard_assignee = person(id="standard-assignee", roles=("admin",),
        jira_user_key="standard-assignee-key")
    with pytest.raises(HTTPException) as error:
        service.review_lesson(db, user=standard_assignee,
            feedback_id=result["feedback_id"], body=approval())
    assert error.value.status_code == 403


def test_live_qe_reassignment_is_checked_again_for_each_review(db):
    result = capture(db, user=person(qe_identity=False))
    first_qe = person(id="first-qe", jira_user_key="qe-key-1")
    approved = service.review_lesson(db, user=first_qe,
        feedback_id=result["feedback_id"], body=approval())
    assert approved["learning_status"] == "APPROVED"

    db.info["qe_assignments"]["GUIDES-900"] = {"key": "qe-key-2", "accountId": "qe-account-2"}
    revoke = UacLessonReview(expected_revision=2, decision="REVOKE",
        idempotency_key="reassignment-revoke", note="The requirement no longer applies.")
    with pytest.raises(HTTPException) as denied:
        service.review_lesson(db, user=first_qe,
            feedback_id=result["feedback_id"], body=revoke)
    assert denied.value.status_code == 403

    second_qe = person(id="second-qe", roles=(), jira_user_key="qe-key-2")
    revoked = service.review_lesson(db, user=second_qe,
        feedback_id=result["feedback_id"], body=revoke)
    assert revoked["learning_status"] == "REVOKED"
    assert revoked["lesson"]["review_authorization"]["identity_value"] == "qe-key-2"


def test_approval_attestations_scope_independence_and_revision_conflict(db):
    result = capture(db)
    for field in ("origin_confirmed", "applicability_confirmed", "counterexamples_checked"):
        with pytest.raises(ValueError, match="attestations"):
            service.review_lesson(db, user=person(), feedback_id=result["feedback_id"], body=approval(**{field: False}))
    body = approval()
    body.lesson.scope.jira_keys = ["GUIDES-900"]
    with pytest.raises(ValueError, match="provenance"):
        service.review_lesson(db, user=person(), feedback_id=result["feedback_id"], body=body)
    body = approval()
    body.lesson.scope.subject_terms = ["GUIDES-900"]
    with pytest.raises(ValueError, match="provenance"):
        service.review_lesson(db, user=person(), feedback_id=result["feedback_id"], body=body)
    body = approval()
    body.lesson.kind = "GENERIC_PATTERN"
    with pytest.raises(ValueError, match="two independent"):
        service.review_lesson(db, user=person(), feedback_id=result["feedback_id"], body=body)
    approved = service.review_lesson(db, user=person(), feedback_id=result["feedback_id"], body=approval())
    db.commit()
    assert approved["learning_status"] == "APPROVED" and approved["index_status"] == "PENDING"
    with pytest.raises(service.LearningConflict, match="latest revision"):
        service.review_lesson(db, user=person(), feedback_id=result["feedback_id"], body=approval(idempotency_key="stale"))
    retry = service.review_lesson(db, user=person(), feedback_id=result["feedback_id"], body=approval())
    assert retry["created"] is False


def test_publication_checks_tenant_cutoff_source_exclusion_and_fresh_revocation(db):
    result = capture(db)
    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    service.review_lesson(db, user=person(), feedback_id=result["feedback_id"], body=approval())
    db.commit()
    published = service.load_shared_learning_publication(tenant_id="kone", session=db)
    assert len(published["lessons"]) == 1
    assert published["lessons"][0]["expected_behavior_authority"] is False
    assert service.load_shared_learning_publication(tenant_id="other", session=db)["lessons"] == []
    assert service.load_shared_learning_publication(tenant_id="kone", cutoff_at=before, session=db)["lessons"] == []
    assert service.load_shared_learning_publication(tenant_id="kone", excluded_source_case_ids={"GUIDES-900"}, session=db)["lessons"] == []
    before_revoke = datetime.now(timezone.utc)
    service.review_lesson(db, user=person(), feedback_id=result["feedback_id"], body=UacLessonReview(
        expected_revision=2, decision="REVOKE", idempotency_key="revoke", note="No longer applicable."))
    db.commit()
    after = service.load_shared_learning_publication(tenant_id="kone", cutoff_at=before_revoke, session=db)
    assert after["lessons"] == [] and after["publication_id"] != published["publication_id"]


def test_presentation_lessons_never_gain_investigation_families(db):
    result = capture(db, delta_type="LANGUAGE_SIMPLIFIED")
    body = approval()
    body.lesson.delta_type = "LANGUAGE_SIMPLIFIED"
    with pytest.raises(ValueError, match="investigation families"):
        service.review_lesson(db, user=person(), feedback_id=result["feedback_id"], body=body)
    body.lesson.families = []
    reviewed = service.review_lesson(db, user=person(), feedback_id=result["feedback_id"], body=body)
    assert reviewed["lesson"]["influence_kind"] == "AUTHORING_GUIDANCE"


def test_protected_and_ai_only_sources_remain_stored_but_cannot_be_approved(db, monkeypatch):
    protected = capture(db, jira="GUIDES-999001")
    assert protected["publication_eligibility"] == "PROTECTED"
    with pytest.raises(service.LearningConflict, match="quarantined"):
        service.review_lesson(db, user=person(), feedback_id=protected["feedback_id"], body=approval(jira="GUIDES-999001"))
    ai_only = capture(db, token="ai", source_kind="AI_PROPOSAL")
    with pytest.raises(ValueError, match="AI proposal"):
        service.review_lesson(db, user=person(), feedback_id=ai_only["feedback_id"], body=approval())
    monkeypatch.setenv("SHARED_UAC_BENCHMARK_SPLIT_MANIFEST", "C:/missing-uac-test-policy.json")
    unverified = capture(db, token="unknown-policy")
    assert unverified["publication_eligibility"] == "UNVERIFIED"
    with pytest.raises(service.LearningConflict, match="metadata is unavailable"):
        service.review_lesson(db, user=person(), feedback_id=unverified["feedback_id"], body=approval())


def test_sql_bulk_mutation_is_denied(db):
    result = capture(db)
    with pytest.raises(IntegrityError, match="immutable"):
        db.execute(text("UPDATE uac_feedback_deltas SET raw_feedback=:new WHERE id=:id"),
                   {"new": "overwritten", "id": result["feedback_id"]})
    db.rollback()


def test_capture_and_outbox_are_atomic_when_dependent_write_fails(db, monkeypatch):
    def fail_revision(*args, **kwargs):
        raise RuntimeError("simulated outbox failure")
    monkeypatch.setattr(service, "_append_revision", fail_revision)
    with pytest.raises(RuntimeError, match="outbox"):
        capture(db)
    db.rollback()
    assert db.query(UacLearningDraft).count() == 0
    assert db.query(UacFeedbackDelta).count() == 0


def test_concurrent_capture_retries_return_one_immutable_delta(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    engine = create_engine(f"sqlite:///{tmp_path / 'concurrent.db'}", connect_args={"timeout": 10, "check_same_thread": False})
    Base.metadata.create_all(engine, tables=[model.__table__ for model in IMMUTABLE_MODELS] + [UacLearningOutbox.__table__])
    factory = sessionmaker(bind=engine)
    start = Barrier(2)
    def write():
        with factory() as connection:
            start.wait(timeout=5)
            result = service.capture_feedback(connection, user=person(), body=UacFeedbackCapture(
                jira_key="GUIDES-900", idempotency_key="concurrent", raw_feedback="Check retained state"))
            connection.commit()
            return result["feedback_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: write(), range(2)))
    with factory() as connection:
        assert len(set(ids)) == 1
        assert connection.query(UacFeedbackDelta).count() == 1
        assert connection.query(UacLearningOutbox).count() == 1
    engine.dispose()


def test_concurrent_human_reviews_allow_only_one_revision_winner(db, tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    engine = create_engine(f"sqlite:///{tmp_path / 'concurrent-review.db'}",
        connect_args={"timeout": 10, "check_same_thread": False})
    Base.metadata.create_all(engine, tables=[model.__table__ for model in IMMUTABLE_MODELS] + [UacLearningOutbox.__table__])
    factory = sessionmaker(bind=engine)
    with factory() as connection:
        result = capture(connection)
    append = service._append_revision
    start = Barrier(2)
    def simultaneous_append(*args, **kwargs):
        start.wait(timeout=5)
        return append(*args, **kwargs)
    monkeypatch.setattr(service, "_append_revision", simultaneous_append)
    def review(actor):
        with factory() as connection:
            try:
                service.review_lesson(connection, user=person(id=actor), feedback_id=result["feedback_id"],
                    body=approval(idempotency_key="same-version-review"))
                connection.commit()
                return "APPROVED"
            except service.LearningConflict:
                connection.rollback()
                return "CONFLICT"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(review, ["human-reviewer-a", "human-reviewer-b"]))
    assert sorted(outcomes) == ["APPROVED", "CONFLICT"]
    with factory() as connection:
        assert connection.query(UacLessonRevision).count() == 2
        assert connection.query(UacLearningOutbox).count() == 2
    engine.dispose()


def test_supersede_hides_old_revision_and_timeout_can_be_retried(db, monkeypatch):
    import subprocess
    result = capture(db)
    service.review_lesson(db, user=person(), feedback_id=result["feedback_id"], body=approval())
    revised = approval(revision=2, decision="SUPERSEDE", idempotency_key="supersede")
    revised.lesson.guidance = "Check configuration is retained across both runs."
    service.review_lesson(db, user=person(), feedback_id=result["feedback_id"], body=revised)
    db.commit()
    lessons = service.load_shared_learning_publication(tenant_id="kone", session=db)["lessons"]
    assert len(lessons) == 1 and lessons[0]["version"] == 3
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("projection", 1)
    monkeypatch.setattr(service, "_bounded_projection", timeout)
    stats = service.drain_learning_outbox(tenant_id="kone", session=db)
    assert stats["failed"] >= 1
    reset = service.retry_failed_index(db, user=person(roles=("admin",)), tenant_id="kone")
    db.commit()
    assert reset["reset_count"] >= 1
    assert all(row.attempts == 0 for row in db.query(UacLearningOutbox).filter_by(status="PENDING").all())


def test_worker_indexes_only_approved_retries_failure_and_uses_real_vector_contract(db, monkeypatch):
    from app.services import embedding_service, vector_store_service
    result = capture(db)
    assert service.drain_learning_outbox(tenant_id="kone", session=db)["claimed"] == 0
    service.review_lesson(db, user=person(), feedback_id=result["feedback_id"], body=approval())
    db.commit()
    calls = []
    monkeypatch.setattr(embedding_service, "embed_texts_batched", lambda docs, batch_size: [[0.1, 0.2]])
    def add_documents(collection_name, ids, documents, metadatas, embeddings):
        calls.append((collection_name, ids, documents, metadatas, embeddings))
        return len(calls) > 1
    monkeypatch.setattr(vector_store_service, "add_documents", add_documents)
    first = service.drain_learning_outbox(tenant_id="kone", session=db, index_writer=service._index_revision)
    assert first["failed"] == 1
    assert service.get_feedback_status(db, user=person(), tenant_id="kone", feedback_id=result["feedback_id"])["index_status"] == "FAILED"
    db.query(UacLearningOutbox).filter_by(status="FAILED").update({"next_attempt_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
    db.commit()
    second = service.drain_learning_outbox(tenant_id="kone", session=db, index_writer=service._index_revision)
    assert second["indexed"] == 1
    assert calls[-1][0] == "uac_feedback"
    assert calls[-1][3][0]["state"] == "APPROVED"


def test_revocation_during_vector_write_removes_stale_projection(db):
    result = capture(db)
    service.review_lesson(db, user=person(), feedback_id=result["feedback_id"], body=approval())
    db.commit()
    removed = []
    def revoke_during_write(revision):
        service.review_lesson(db, user=person(), feedback_id=result["feedback_id"], body=UacLessonReview(
            expected_revision=2, decision="REVOKE", idempotency_key="revoke-during-index", note="Applicability changed."))
        db.commit()
        return True
    outcome = service.drain_learning_outbox(tenant_id="kone", session=db, index_writer=revoke_during_write,
        index_remover=lambda rows: removed.extend(row.id for row in rows) or True)
    assert outcome["indexed"] == 0 and outcome["skipped"] >= 1 and removed
    assert service.load_shared_learning_publication(tenant_id="kone", session=db)["lessons"] == []


def test_http_409_cross_tenant_denial_and_no_body_reviewer_impersonation(db):
    from app.api.v1.routes.test_plan_learning import router
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: person()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    payload = {"jira_key": "GUIDES-900", "idempotency_key": "http1", "raw_feedback": "Narrow the oracle"}
    captured = client.post("/api/v1/test-plan-learning/feedback", json=payload)
    assert captured.status_code == 200
    changed = client.post("/api/v1/test-plan-learning/feedback", json={**payload, "raw_feedback": "Different correction"})
    assert changed.status_code == 409
    forbidden = client.get("/api/v1/test-plan-learning/feedback?tenant_id=other")
    assert forbidden.status_code == 403
    impersonation = client.post(f"/api/v1/test-plan-learning/feedback/{captured.json()['feedback_id']}/review",
        json={"expected_revision": 1, "idempotency_key": "review1", "decision": "REJECT", "reviewer": "admin"})
    assert impersonation.status_code == 422


def test_validation_does_not_echo_sensitive_shared_capture_in_either_http_route(db):
    from app.api.v1.routes import test_plan_learning, test_plans
    app = FastAPI()
    app.include_router(test_plan_learning.router, prefix="/api/v1")
    app.include_router(test_plans.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: person()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    payload = {"contract_version": "shared-uac-feedback-v1", "jira_key": "GUIDES-900",
        "raw_feedback": "secret=synthetic-sensitive-correction", "idempotency_key": "invalid",
        "source_kind": "synthetic-sensitive-invalid-source"}
    for route in ("/api/v1/test-plan-learning/feedback", "/api/v1/test-plans/GUIDES-900/feedback"):
        response = client.post(route, json=payload)
        assert response.status_code == 422
        assert "synthetic-sensitive" not in response.text
        denied = client.post(route, json={**payload, "source_kind": "UNCONFIRMED",
            "tenant_id": "synthetic_sensitive_tenant"})
        assert denied.status_code == 403 and "synthetic_sensitive_tenant" not in denied.text
    denied_query = client.get("/api/v1/test-plan-learning/feedback?tenant_id=synthetic_sensitive_tenant")
    assert denied_query.status_code == 403 and "synthetic_sensitive_tenant" not in denied_query.text
    legacy = client.post("/api/v1/test-plans/GUIDES-900/feedback", json={"event_type": "invalid"})
    assert legacy.status_code == 422 and isinstance(legacy.json()["detail"], list)


def test_shared_http_capture_and_reads_deny_development_bypass(db):
    from app.api.v1.routes import test_plan_learning, test_plans
    app = FastAPI()
    app.include_router(test_plan_learning.router, prefix="/api/v1")
    app.include_router(test_plans.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: person(auth_method="dev_bypass")
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    payload = {"contract_version": "shared-uac-feedback-v1", "jira_key": "GUIDES-900",
        "raw_feedback": "Selected correction", "idempotency_key": "no-dev-transport"}
    for route in ("/api/v1/test-plan-learning/feedback", "/api/v1/test-plans/GUIDES-900/feedback"):
        assert client.post(route, json=payload).status_code == 403
    for route in ("/api/v1/test-plan-learning/feedback", "/api/v1/test-plan-learning/feedback/missing",
                  "/api/v1/test-plan-learning/publication"):
        assert client.get(route).status_code == 403
    assert db.query(UacFeedbackDelta).count() == 0


@pytest.mark.parametrize("route", ["/api/v1/test-plan-learning/feedback", "/api/v1/test-plans/GUIDES-900/feedback"])
def test_committed_http_capture_survives_lost_response_and_exact_retry(db, route):
    from app.api.v1.routes import test_plan_learning, test_plans
    app = FastAPI()
    app.include_router(test_plan_learning.router, prefix="/api/v1")
    app.include_router(test_plans.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: person()
    app.dependency_overrides[get_db] = lambda: db
    lose_next_response = True

    @app.middleware("http")
    async def lose_committed_response(request, call_next):
        nonlocal lose_next_response
        response = await call_next(request)
        if request.url.path == route and lose_next_response:
            lose_next_response = False
            # The real HTTP handler has already committed its transaction, but
            # its response does not reach the capture client.
            assert db.query(UacFeedbackDelta).count() == 1
            raise ConnectionResetError("Simulated committed response loss")
        return response

    client = TestClient(app)
    registration = client.post("/api/v1/test-plan-learning/drafts", json={
        "jira_key": "GUIDES-900", "idempotency_key": "register-before-capture",
        "draft_markdown": "UAC-01: Verify retained state.",
        "criteria": {"UAC-01": "Verify retained state."}})
    assert registration.status_code == 200
    payload = {"contract_version": "shared-uac-feedback-v1", "jira_key": "GUIDES-900",
        "draft_id": registration.json()["draft_id"], "idempotency_key": "stable-redacted-wire",
        "raw_feedback": "[REDACTED] asks to check retained configuration.",
        "proposed_correction": "Verify the selected configuration is retained.", "ac_id": "UAC-01"}
    with pytest.raises(ConnectionResetError):
        client.post(route, json=payload)
    original_id = db.query(UacFeedbackDelta).one().id
    replay = client.post(route, json=payload)
    assert replay.status_code == 200
    assert replay.json()["feedback_id"] == original_id and replay.json()["created"] is False
    assert replay.json()["binding_status"] == "BOUND"
    assert db.query(UacFeedbackDelta).count() == 1 and db.query(UacLearningOutbox).count() == 1
    changed = client.post(route, json={**payload, "proposed_correction": "Different correction."})
    assert changed.status_code == 409


def test_scheduler_drains_only_bounded_ready_work_and_reports_unavailability(db, monkeypatch):
    from app.db import session as session_module
    from app.services.shared_uac_learning_worker import run_shared_learning_publication_job
    result = capture(db)
    service.review_lesson(db, user=person(), feedback_id=result["feedback_id"], body=approval())
    db.commit()
    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))
    calls = []
    def drain(**kwargs):
        calls.append(kwargs)
        return {"claimed": 1, "indexed": 1, "skipped": 0, "failed": 0}
    monkeypatch.setattr(service, "drain_learning_outbox", drain)
    total = run_shared_learning_publication_job()
    assert total["indexed"] == 1 and calls[0]["tenant_id"] == "kone"
    assert calls[0]["limit"] <= 20 and calls[0]["max_attempts"] == 5
    def fail(**kwargs):
        raise RuntimeError("secret=synthetic-provider-secret")
    monkeypatch.setattr(service, "drain_learning_outbox", fail)
    failed = run_shared_learning_publication_job()
    assert failed["status"] == "UNAVAILABLE" and "synthetic-provider-secret" not in str(failed)


def test_migration_creates_and_removes_only_shared_learning_tables():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    migration_path = Path(__file__).parents[1] / "migrations/versions/20260906_add_shared_uac_learning.py"
    spec = importlib.util.spec_from_file_location("shared_learning_migration", migration_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        assert set(inspect(connection).get_table_names()) == {model.__tablename__ for model in IMMUTABLE_MODELS} | {"uac_learning_outbox"}
        module.downgrade()
        assert inspect(connection).get_table_names() == []
