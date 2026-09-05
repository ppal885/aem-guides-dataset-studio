"""Canonical draft -> SQL Human correction -> reviewed runtime investigation."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from app.core.schemas_shared_uac_learning import (
    UacDraftContent, UacFeedbackCapture, UacLessonReview,
)
from app.db.shared_uac_learning_models import UacLearningDraft
from app.services import shared_uac_learning_service as storage
from app.services.qe_pattern_mcp_service import QePatternResolver
from test_shared_learning_pattern_provider import _contract_projection, _runtime_run
from test_shared_uac_learning import approval, db as learning_db, person


def test_real_canonical_draft_binds_correction_and_approved_sql_lesson_reaches_next_case(
        learning_db, monkeypatch):
    original = _runtime_run(monkeypatch, mode="DISABLED", tenant_id="kone")
    original_draft = original.rendered_output
    criterion = next(row["statement"] for row in original.output_payload["acceptance_candidates"]
        if row["statement"] in original_draft)
    receipt = storage.capture_feedback(learning_db, user=person(), body=UacFeedbackCapture(
        tenant_id="kone", jira_key="GUIDES-82003", idempotency_key="canonical-correction",
        raw_feedback="The investigation missed alternate mechanisms for changed publishing behavior.",
        proposed_correction="Ask which alternate mechanism is affected before adding a criterion.",
        delta_type="OPEN_QUESTION_ADDED", source_kind="HUMAN_CORRECTION",
        evidence_bundle_id=original.evidence_bundle_id, run_id=original.run_id, ac_id="AC-01",
        draft=UacDraftContent(draft_markdown=original_draft, criteria={"AC-01": criterion},
            evidence_bundle_id=original.evidence_bundle_id, run_id=original.run_id)))
    learning_db.commit()
    assert receipt["binding_status"] == "BOUND" and receipt["learning_status"] == "CANDIDATE"
    assert receipt["plan_fingerprint"] == hashlib.sha256(original_draft.encode()).hexdigest()
    draft = learning_db.query(UacLearningDraft).filter_by(id=receipt["draft_id"]).one()
    assert draft.evidence_bundle_id == original.evidence_bundle_id
    assert draft.run_id == original.run_id
    assert draft.content["criteria"]["AC-01"] == criterion
    assert draft.content["evidence_authority_verified"] is False
    assert storage.load_shared_learning_publication(tenant_id="kone", session=learning_db)["lessons"] == []

    reviewed = approval(jira="GUIDES-82003")
    reviewed.lesson.delta_type = "OPEN_QUESTION_ADDED"
    reviewed.lesson.domains = ["PUBLISHING"]
    reviewed.lesson.surfaces = ["CHANGED_BEHAVIOR"]
    reviewed.lesson.signals = ["CHANGED_BEHAVIOR"]
    reviewed.lesson.families = ["ALTERNATE_MECHANISMS"]
    reviewed.lesson.scope.subject_terms = []
    reviewed.lesson.scope.publishing_modes = ["Native PDF"]
    reviewed.lesson.guidance = "Investigate alternate mechanisms for the changed publishing behavior."
    approved = storage.review_lesson(learning_db, user=person(), feedback_id=receipt["feedback_id"], body=reviewed)
    learning_db.commit()
    authorization = approved["lesson"]["human_approval"]["authorization"]
    assert authorization["policy"] == "LIVE_JIRA_QE_ASSIGNEE"
    assert authorization["jira_key"] == "GUIDES-82003"
    assert authorization["field_name"] == "QE Assignee"
    assert approved["publication_review_status"] == "QE_APPROVED"
    assert approved["reuse_eligible"] is True
    publication = storage.load_shared_learning_publication(tenant_id="kone", session=learning_db)
    published_lesson = next(row for row in publication["lessons"] if row["lesson_id"] == receipt["feedback_id"])

    class EmptyBaseline:
        def load(self):
            return [], "baseline", "c" * 64

    resolver = QePatternResolver(EmptyBaseline(), shared_loader=lambda **kwargs:
        storage.load_shared_learning_publication(session=learning_db, **kwargs))
    current = _runtime_run(monkeypatch, resolver=resolver, tenant_id="kone")
    assert current.output_payload["qe_investigation"]["matched_human_patterns"] == []
    disabled = _runtime_run(monkeypatch, mode="DISABLED", resolver=resolver,
        tenant_id="kone", jira_key="GUIDES-82004")
    enabled = _runtime_run(monkeypatch, resolver=resolver, tenant_id="kone", jira_key="GUIDES-82004")
    matches = enabled.output_payload["qe_investigation"]["matched_human_patterns"]
    assert len(matches) == 1 and matches[0]["lesson_id"] == receipt["feedback_id"]
    assert matches[0]["lesson_kind"] == "SCOPED_CASE"
    assert any(row["dimension"] == "ALTERNATE_MECHANISMS" and row["blocking"] is False
        for row in enabled.output_payload["missing_questions"])
    questions = [row for row in enabled.output_payload["missing_questions"]
        if row["dimension"] == "ALTERNATE_MECHANISMS"]
    question_ids = {row["question_id"] for row in questions}
    dispositions = [row for row in enabled.output_payload["coverage_dispositions"]
        if question_ids.intersection(row.get("source_question_ids", []))]
    assert dispositions and all(row["disposition"] != "ACCEPTANCE_CONTRACT" for row in dispositions)
    assert _contract_projection(enabled) == _contract_projection(disabled)
    assert enabled.output_payload["promotion_decisions"] == disabled.output_payload["promotion_decisions"]

    revocation = storage.review_lesson(learning_db, user=person(), feedback_id=receipt["feedback_id"],
        body=UacLessonReview(expected_revision=2, decision="REVOKE", idempotency_key="canonical-revoke",
            note="The lesson no longer applies."))
    learning_db.commit()
    revoked = _runtime_run(monkeypatch, resolver=resolver, tenant_id="kone", jira_key="GUIDES-82004")
    assert revoked.output_payload["qe_investigation"]["matched_human_patterns"] == []
    assert _contract_projection(revoked) == _contract_projection(disabled)
    assert revoked.output_payload["missing_questions"] == disabled.output_payload["missing_questions"]
    assert revoked.output_payload["coverage_dispositions"] == disabled.output_payload["coverage_dispositions"]
    revoked_publication = storage.load_shared_learning_publication(tenant_id="kone", session=learning_db)
    assert revoked_publication["lessons"] == []

    # An opt-in proof artifact contains only observed results from this isolated
    # synthetic SQL/runtime test. It is not evidence of VM deployment or indexing.
    proof_path = os.environ.get("SHARED_UAC_LEARNING_PROOF_PATH", "").strip()
    if proof_path:
        def contract_fingerprint(result):
            rows = sorted(_contract_projection(result))
            return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()

        proof = {
            "schema_version": "shared-uac-local-learning-proof-v1",
            "verification_scope": "LOCAL_ISOLATED",
            "synthetic_fixture": True,
            "vm_verified": False,
            "live_vector_index_verified": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "test": "test_real_canonical_draft_binds_correction_and_approved_sql_lesson_reaches_next_case",
            "source_case": {"jira_key": "GUIDES-82003", "run_id": original.run_id,
                "evidence_bundle_id": original.evidence_bundle_id,
                "plan_fingerprint": receipt["plan_fingerprint"]},
            "capture": {key: receipt[key] for key in (
                "feedback_id", "draft_id", "persisted", "binding_status", "learning_status",
                "index_status", "source_kind", "source_hash", "submitter_id")},
            "review": {"learning_status": approved["learning_status"],
                "revision": approved["review_revision"],
                "named_human_approval": approved["lesson"]["human_approval"],
                "authorization_policy": authorization["policy"],
                "authorization_jira_key": authorization["jira_key"],
                "live_qe_assignment_verified": approved["reuse_eligible"]},
            "publication": {"publication_id": publication["publication_id"],
                "lesson_id": published_lesson["lesson_id"], "lesson_version": published_lesson["version"]},
            "next_case": {"jira_key": "GUIDES-82004", "run_id": enabled.run_id,
                "evidence_bundle_id": enabled.evidence_bundle_id, "shared_lesson_matches": matches,
                "linked_questions": questions, "linked_dispositions": dispositions},
            "acceptance_contract_assertions": {
                "no_acceptance_contract_change": _contract_projection(enabled) == _contract_projection(disabled),
                "no_promotion_change": enabled.output_payload["promotion_decisions"] == disabled.output_payload["promotion_decisions"],
                "disabled_contract_hash": contract_fingerprint(disabled),
                "enabled_contract_hash": contract_fingerprint(enabled)},
            "revocation": {"learning_status": revocation["learning_status"],
                "revision": revocation["review_revision"], "publication_id": revoked_publication["publication_id"],
                "published_lesson_count": len(revoked_publication["lessons"]),
                "shared_lesson_matches": revoked.output_payload["qe_investigation"]["matched_human_patterns"],
                "missing_questions_match_disabled": revoked.output_payload["missing_questions"] == disabled.output_payload["missing_questions"],
                "coverage_dispositions_match_disabled": revoked.output_payload["coverage_dispositions"] == disabled.output_payload["coverage_dispositions"],
                "no_acceptance_contract_change": _contract_projection(revoked) == _contract_projection(disabled)},
        }
        target = Path(proof_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
