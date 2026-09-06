"""Jira review binding across fresh chats, using fake Jira and isolated SQL only."""
from copy import deepcopy
import hashlib
import json
import subprocess
import sys

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from sqlalchemy import event

from app.core.auth import get_current_user
from app.core.schemas_shared_uac_learning import UacFeedbackBind, UacFeedbackCapture, UacLessonReview, UacReviewedJiraUac
from app.db.session import get_db
from app.db.shared_uac_learning_models import UacFeedbackBinding, UacFeedbackDelta, UacLearningDraft, UacLessonRevision
from app.services import shared_uac_learning_service as service
from app.services import shared_uac_qe_authorization as jira_authority
from app.services import shared_uac_jira_review_snapshot as jira_snapshot
from test_shared_uac_learning import approval, capture, db as learning_db, person


FIELD = "customfield_13400"
UPDATED = "2026-09-07T09:00:00+00:00"
QUOTE = "Verify output uses the saved configuration."
MARKDOWN = "h2. Acceptance Criteria\r\n* UAC-01: " + QUOTE + "\r\n* UAC-02: Verify the output title.\r\n"


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def reference(**changes):
    values = dict(field_id=FIELD, expected_sha256=sha(MARKDOWN),
                  expected_issue_updated=UPDATED, original_reviewed_ac=QUOTE)
    values.update(changes)
    return UacReviewedJiraUac(**values)


def request(**changes):
    values = dict(tenant_id="kone", jira_key="GUIDES-900", idempotency_key="new-chat-feedback",
        raw_feedback="The reviewed criterion misses the changed configuration.",
        source_kind="HUMAN_CORRECTION", proposed_correction="Also verify changed configuration.",
        ac_id="UAC-01", reviewed_jira_uac=reference())
    values.update(changes)
    return UacFeedbackCapture(**values)


@pytest.fixture
def jira(learning_db, monkeypatch):
    state = {"key": "GUIDES-900", "fields": {FIELD: MARKDOWN, "updated": UPDATED},
             "names": {FIELD: "Acceptance Criteria"}, "calls": []}
    old_reader = jira_authority._QeAuthorizationJiraClient.get_issue_with_names

    def read(client, issue_key, fields=None):
        if fields == "customfield_18512,updated":
            return old_reader(client, issue_key, fields)
        state["calls"].append((client.base_url, issue_key, fields))
        if state.get("failure"):
            raise RuntimeError("synthetic-private-Jira-response")
        return deepcopy({key: value for key, value in state.items() if key in {"key", "fields", "names"}})

    monkeypatch.delenv("JIRA_ACCEPTANCE_CRITERIA_FIELD_ID", raising=False)
    monkeypatch.setattr(jira_authority._QeAuthorizationJiraClient, "get_issue_with_names", read)
    return state


def test_new_chat_binds_exact_jira_snapshot_without_generation_context(learning_db, jira):
    receipt = service.capture_feedback(learning_db, user=person(), body=request())
    learning_db.commit()
    assert receipt["binding_status"] == "BOUND"
    assert receipt["learning_status"] == "CANDIDATE"
    assert receipt["index_status"] == "SKIPPED"
    assert receipt["automatic_authority_promotion"] is False
    assert receipt["reuse_eligible"] is False
    assert receipt["original_reviewed_ac"] == QUOTE
    proof = receipt["reviewed_jira_uac"]
    assert proof["source_kind"] == "JIRA_REVIEW_SNAPSHOT"
    assert proof["field_id"] == FIELD and proof["field_name"] == "Acceptance Criteria"
    assert proof["source_hash"] == sha(MARKDOWN) == receipt["plan_fingerprint"]
    assert proof["original_reviewed_ac_hash"] == sha(QUOTE)
    assert proof["generation_lineage_verified"] is False
    assert proof["jira_server"] == "https://jira.example"
    assert proof["issue_updated"] == UPDATED and proof["fetched_at"]
    draft = learning_db.query(UacLearningDraft).one()
    assert draft.run_id == draft.evidence_bundle_id == ""
    assert draft.content["criteria"] == {"UAC-01": QUOTE}
    assert draft.content["source_hash"] != draft.content["content_hash"]  # CRLF bytes are pinned exactly.
    assert draft.content["content_hash"] == sha(draft.content["draft_markdown"])
    assert jira["calls"] == [("https://jira.example", "GUIDES-900", FIELD + ",updated")]
    assert service.load_shared_learning_publication(tenant_id="kone", session=learning_db)["lessons"] == []


@pytest.mark.parametrize("pin,ac_id", [
    (reference(expected_sha256="a" * 64), "UAC-01"),
    (reference(expected_issue_updated="2026-09-06T00:00:00Z"), "UAC-01"),
    (reference(original_reviewed_ac="This was never in the reviewed Jira UAC."), "UAC-01"),
    (reference(original_reviewed_ac="Verify the output title."), "UAC-01"),
])
def test_changed_or_invented_review_source_fails_without_records(learning_db, jira, pin, ac_id):
    with pytest.raises(service.LearningConflict):
        service.capture_feedback(learning_db, user=person(), body=request(reviewed_jira_uac=pin, ac_id=ac_id))
    assert learning_db.query(UacLearningDraft).count() == 0
    assert learning_db.query(UacFeedbackDelta).count() == 0


def test_repeated_excerpt_is_ambiguous(learning_db, jira):
    repeated = "* UAC-01: " + QUOTE + "\n* UAC-02: " + QUOTE
    jira["fields"][FIELD] = repeated
    with pytest.raises(service.LearningConflict, match="exactly once"):
        service.capture_feedback(learning_db, user=person(),
            body=request(reviewed_jira_uac=reference(expected_sha256=sha(repeated))))


def test_exact_multiline_excerpt_keeps_whitespace(learning_db, jira):
    quote = "  Verify the saved\n  configuration."
    markdown = "UAC-01:\n" + quote
    jira["fields"][FIELD] = markdown
    result = service.capture_feedback(learning_db, user=person(), body=request(
        reviewed_jira_uac=reference(expected_sha256=sha(markdown), original_reviewed_ac=quote)))
    assert result["original_reviewed_ac"] == quote
    assert result["reviewed_jira_uac"]["original_reviewed_ac_hash"] == sha(quote)


@pytest.mark.parametrize("prefix", ["", "* ", "- **", "### ", "h3. ", " > h2. **"])
def test_label_prefixes_still_check_the_selected_criterion(prefix):
    markdown = prefix + "UAC-01: " + QUOTE
    jira_snapshot._validate_excerpt(markdown, QUOTE, "UAC-01")
    with pytest.raises(jira_snapshot.JiraReviewMismatch, match="criterion label"):
        jira_snapshot._validate_excerpt(markdown, QUOTE, "UAC-02")


def test_long_markup_only_line_does_not_hang_source_verification():
    # Isolate the timeout so reintroducing the vulnerable expression fails this
    # regression instead of hanging the whole suite. No network or app startup.
    program = """
from app.services.shared_uac_jira_review_snapshot import _validate_excerpt, JiraReviewMismatch
for marker in ('*', '-', '#', '>', ' '):
    text = marker * 99000 + '\\n* UAC-01: Original criterion.'
    _validate_excerpt(text, 'Original criterion.', 'UAC-01')
    try:
        _validate_excerpt(text, 'Original criterion.', 'UAC-02')
    except JiraReviewMismatch:
        pass
    else:
        raise AssertionError('criterion identity check was bypassed')
print('BOUNDED_LABEL_SCAN_PASS')
"""
    completed = subprocess.run([sys.executable, "-c", program], capture_output=True,
                               text=True, timeout=15, check=True)
    assert completed.stdout.strip() == "BOUNDED_LABEL_SCAN_PASS"


@pytest.mark.parametrize("unavailable", [None, "", " \r\n"])
def test_missing_original_stays_pending_and_cannot_be_approved(learning_db, jira, unavailable):
    jira["fields"][FIELD] = unavailable
    result = service.capture_feedback(learning_db, user=person(), body=request())
    learning_db.commit()
    assert result["binding_status"] == result["learning_status"] == "PENDING_BINDING"
    assert result["binding_reason"] == "REVIEWED_JIRA_UAC_UNAVAILABLE"
    assert result["reviewed_jira_uac"] is None
    assert result["reviewed_jira_uac_reference"]["expected_sha256"] == sha(MARKDOWN)
    assert learning_db.query(UacLearningDraft).count() == 0
    with pytest.raises(service.LearningConflict, match="binding"):
        service.review_lesson(learning_db, user=person(), feedback_id=result["feedback_id"], body=approval())


def test_bound_retry_returns_original_snapshot_even_after_jira_changes(learning_db, jira):
    first = service.capture_feedback(learning_db, user=person(), body=request())
    learning_db.commit()
    jira["fields"][FIELD] = "New UAC which was not reviewed"
    second = service.capture_feedback(learning_db, user=person(), body=request())
    assert second["feedback_id"] == first["feedback_id"] and second["created"] is False
    assert second["reviewed_jira_uac"] == first["reviewed_jira_uac"]
    assert len(jira["calls"]) == 1
    with pytest.raises(service.LearningConflict):
        service.capture_feedback(learning_db, user=person(), body=request(idempotency_key="different-correction"))


def test_pending_capture_requires_deliberate_qe_bind_and_keeps_immutable_delta(learning_db, jira):
    jira["fields"][FIELD] = None
    initial = service.capture_feedback(learning_db, user=person(), body=request())
    learning_db.commit()
    delta_content = deepcopy(learning_db.query(UacFeedbackDelta).one().content)
    jira["fields"][FIELD] = MARKDOWN
    retry = service.capture_feedback(learning_db, user=person(), body=request())
    assert retry["binding_status"] == "PENDING_BINDING" and len(jira["calls"]) == 1
    bind = UacFeedbackBind(idempotency_key="explicit-bind", reviewed_jira_uac=reference())
    with pytest.raises(HTTPException) as denied:
        service.bind_feedback(learning_db, user=person(jira_user_key="different-qe"),
            feedback_id=initial["feedback_id"], body=bind)
    assert denied.value.status_code == 403 and len(jira["calls"]) == 1
    bound = service.bind_feedback(learning_db, user=person(), feedback_id=initial["feedback_id"], body=bind)
    learning_db.commit()
    assert bound["binding_status"] == "BOUND" and bound["learning_status"] == "CANDIDATE"
    assert bound["revision"] == 2 and bound["binding_reason"] == ""
    assert bound["lesson"]["binding_authorization"]["policy"] == "LIVE_JIRA_QE_ASSIGNEE"
    assert learning_db.query(UacFeedbackDelta).one().content == delta_content
    assert service.bind_feedback(learning_db, user=person(), feedback_id=initial["feedback_id"], body=bind)["revision"] == 2
    assert learning_db.query(UacFeedbackBinding).count() == 1


def test_pending_pin_cannot_be_changed_or_replaced_by_unverified_draft(learning_db, jira):
    jira["fields"][FIELD] = None
    result = service.capture_feedback(learning_db, user=person(), body=request())
    learning_db.commit()
    with pytest.raises(service.LearningConflict, match="cannot be changed"):
        service.bind_feedback(learning_db, user=person(), feedback_id=result["feedback_id"],
            body=UacFeedbackBind(idempotency_key="changed-source", reviewed_jira_uac=reference(expected_sha256="b" * 64)))
    with pytest.raises(service.LearningConflict, match="pinned"):
        service.bind_feedback(learning_db, user=person(), feedback_id=result["feedback_id"],
            body=UacFeedbackBind(idempotency_key="unverified-draft", draft_id="some-registered-draft"))
    assert learning_db.query(UacFeedbackBinding).count() == 0


def test_preexisting_pending_correction_can_bind_from_new_chat(learning_db, jira):
    pending = capture(learning_db, bound=False, source_kind="HUMAN_CORRECTION")
    bound = service.bind_feedback(learning_db, user=person(), feedback_id=pending["feedback_id"],
        body=UacFeedbackBind(idempotency_key="jira-source-bind", reviewed_jira_uac=reference()))
    assert bound["binding_status"] == "BOUND"
    assert bound["reviewed_jira_uac"]["source_hash"] == sha(MARKDOWN)
    assert bound["original_reviewed_ac"] == QUOTE


@pytest.mark.parametrize("field_name", ["Description", "QE Assignee", "Unknown"])
def test_unrelated_field_cannot_be_presented_as_reviewed_uac(learning_db, jira, field_name):
    jira["names"][FIELD] = field_name
    with pytest.raises(service.LearningConflict, match="acceptance-criteria"):
        service.capture_feedback(learning_db, user=person(), body=request())


def test_configured_field_pin_and_ambiguity_fail_closed(learning_db, jira, monkeypatch):
    monkeypatch.setenv("JIRA_ACCEPTANCE_CRITERIA_FIELD_ID", "customfield_10001")
    with pytest.raises(service.LearningConflict, match="configured"):
        service.capture_feedback(learning_db, user=person(), body=request())
    assert jira["calls"] == []
    monkeypatch.delenv("JIRA_ACCEPTANCE_CRITERIA_FIELD_ID")
    jira["names"]["customfield_10001"] = "Acceptance Criteria"
    with pytest.raises(service.LearningConflict, match="unambiguous"):
        service.capture_feedback(learning_db, user=person(), body=request())


def test_network_failure_never_creates_a_binding_or_exposes_jira_details(learning_db, jira):
    jira["failure"] = True
    with pytest.raises(HTTPException) as unavailable:
        service.capture_feedback(learning_db, user=person(), body=request())
    assert unavailable.value.status_code == 503
    assert "synthetic-private" not in unavailable.value.detail
    assert learning_db.query(UacFeedbackDelta).count() == 0


def test_tenant_access_denied_before_any_jira_read(learning_db, jira):
    with pytest.raises(HTTPException) as denied:
        service.capture_feedback(learning_db, user=person(tenants=("other",)), body=request())
    assert denied.value.status_code == 403 and jira["calls"] == []


def test_sensitive_quote_rejected_without_storing_or_rewriting_it(learning_db, jira):
    quote = "Use secret=synthetic-private-value"
    jira["fields"][FIELD] = quote
    with pytest.raises(ValueError, match="sensitive"):
        service.capture_feedback(learning_db, user=person(), body=request(
            reviewed_jira_uac=reference(original_reviewed_ac=quote, expected_sha256=sha(quote))))
    assert learning_db.query(UacLearningDraft).count() == 0 and jira["calls"] == []


def test_jira_snapshot_pii_redacted_separately_from_exact_source_hash(learning_db, jira):
    markdown = MARKDOWN + "Reviewer: synthetic.private@example.com"
    jira["fields"][FIELD] = markdown
    result = service.capture_feedback(learning_db, user=person(), body=request(
        reviewed_jira_uac=reference(expected_sha256=sha(markdown))))
    draft = learning_db.query(UacLearningDraft).one()
    assert "synthetic.private@example.com" not in json.dumps(draft.content)
    assert result["reviewed_jira_uac"]["source_hash"] == sha(markdown)
    assert result["reviewed_jira_uac"]["content_hash"] == sha(draft.content["draft_markdown"])


def test_legacy_capture_idempotency_payload_unchanged(learning_db):
    body = UacFeedbackCapture(jira_key="GUIDES-900", idempotency_key="legacy", raw_feedback="Correction")
    old_payload = body.model_dump(mode="json")
    old_payload.pop("reviewed_jira_uac")
    result = service.capture_feedback(learning_db, user=person(), body=body)
    delta = learning_db.query(UacFeedbackDelta).one()
    assert delta.request_hash == sha(json.dumps(old_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    assert result["binding_status"] == "PENDING_BINDING"


@pytest.mark.parametrize("changes", [
    {"draft_id": "draft"}, {"plan_fingerprint": "a" * 64}, {"run_id": "generation-run"},
    {"evidence_bundle_id": "bundle:" + "a" * 64},
    {"reviewed_jira_uac": reference(original_reviewed_ac="")},
])
def test_snapshot_contract_rejects_mixed_source_or_unpinned_criterion(changes):
    with pytest.raises(ValidationError):
        request(**changes)


def test_get_status_and_listing_do_not_read_jira_or_write_sql(learning_db, jira):
    from app.api.v1.routes.test_plan_learning import router

    receipt = service.capture_feedback(learning_db, user=person(), body=request())
    learning_db.commit()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: person()
    app.dependency_overrides[get_db] = lambda: learning_db
    statements = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.lstrip().split()[0].upper())

    event.listen(learning_db.bind, "before_cursor_execute", record)
    try:
        with TestClient(app) as client:
            status = client.get("/api/v1/test-plan-learning/feedback/" + receipt["feedback_id"])
            listing = client.get("/api/v1/test-plan-learning/feedback", params={"jira_key": "GUIDES-900"})
        assert status.status_code == listing.status_code == 200
        assert status.json()["reviewed_jira_uac"] == receipt["reviewed_jira_uac"]
        assert listing.json()["count"] == 1
    finally:
        event.remove(learning_db.bind, "before_cursor_execute", record)
    assert not set(statements).intersection({"INSERT", "UPDATE", "DELETE", "CREATE", "DROP"})
    assert len(jira["calls"]) == 1
    assert learning_db.query(UacLessonRevision).count() == 1


def test_jira_reviewed_lesson_changes_investigation_trace_and_revocation_removes_it(learning_db, jira, monkeypatch, tmp_path):
    from app.services.qe_pattern_mcp_service import QePatternResolver
    from test_shared_learning_pattern_provider import _contract_projection, _runtime_run

    receipt = service.capture_feedback(learning_db, user=person(), body=request())
    learning_db.commit()
    review = approval()
    review.lesson.delta_type = "OPEN_QUESTION_ADDED"
    review.lesson.domains = ["PUBLISHING"]
    review.lesson.surfaces = review.lesson.signals = ["CHANGED_BEHAVIOR"]
    review.lesson.families = ["ALTERNATE_MECHANISMS"]
    review.lesson.scope.subject_terms = []
    review.lesson.scope.publishing_modes = ["Native PDF"]
    review.lesson.guidance = "Investigate alternate mechanisms for the changed publishing behavior."
    approved = service.review_lesson(learning_db, user=person(), feedback_id=receipt["feedback_id"], body=review)
    learning_db.commit()

    class EmptyBaseline:
        def load(self):
            return [], "baseline", "c" * 64

    resolver = QePatternResolver(EmptyBaseline(), shared_loader=lambda **kwargs:
        service.load_shared_learning_publication(session=learning_db, **kwargs))
    disabled = _runtime_run(monkeypatch, mode="DISABLED", resolver=resolver, tenant_id="kone", jira_key="GUIDES-901")
    enabled = _runtime_run(monkeypatch, resolver=resolver, tenant_id="kone", jira_key="GUIDES-901")
    matches = enabled.output_payload["qe_investigation"]["matched_human_patterns"]
    assert len(matches) == 1 and matches[0]["lesson_id"] == receipt["feedback_id"]
    questions = [row for row in enabled.output_payload["missing_questions"] if row["dimension"] == "ALTERNATE_MECHANISMS"]
    assert questions and all(row["blocking"] is False for row in questions)
    question_ids = {row["question_id"] for row in questions}
    dispositions = [row for row in enabled.output_payload["coverage_dispositions"]
                    if question_ids.intersection(row.get("source_question_ids", []))]
    assert dispositions and all(row["disposition"] != "ACCEPTANCE_CONTRACT" for row in dispositions)
    assert _contract_projection(enabled) == _contract_projection(disabled)
    assert enabled.output_payload["promotion_decisions"] == disabled.output_payload["promotion_decisions"]

    service.review_lesson(learning_db, user=person(), feedback_id=receipt["feedback_id"],
        body=UacLessonReview(expected_revision=2, idempotency_key="revoke-jira-lesson", decision="REVOKE",
                             note="The reviewed lesson no longer applies."))
    learning_db.commit()
    revoked = _runtime_run(monkeypatch, resolver=resolver, tenant_id="kone", jira_key="GUIDES-901")
    assert not revoked.output_payload["qe_investigation"]["matched_human_patterns"]
    assert revoked.output_payload["missing_questions"] == disabled.output_payload["missing_questions"]
    assert revoked.output_payload["coverage_dispositions"] == disabled.output_payload["coverage_dispositions"]
    assert _contract_projection(revoked) == _contract_projection(disabled)
    (tmp_path / "jira-review-learning-proof.json").write_text(json.dumps({
        "schema_version": "jira-review-learning-local-proof-v1",
        "environment": "ISOLATED_SQL_AND_FAKE_JIRA_NOT_VM",
        "capture": receipt,
        "approval": approved,
        "matches": matches,
        "questions": questions,
        "dispositions": dispositions,
        "acceptance_contract_unchanged": _contract_projection(enabled) == _contract_projection(disabled),
        "revocation_removed_influence": not revoked.output_payload["qe_investigation"]["matched_human_patterns"],
        "live_vm_proven": False,
    }, indent=2, default=str), encoding="utf-8")
