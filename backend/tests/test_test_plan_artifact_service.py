from app.services import test_plan_artifact_service as artifacts


def test_save_and_list_test_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "TEST_PLANS_DIR", tmp_path)
    markdown = "# Test Plan: GUIDES-99999 — Demo\n\n**Review status:** Draft\n"
    saved = artifacts.save_test_plan("GUIDES-99999", markdown)
    assert saved["jira_key"] == "GUIDES-99999"
    assert "Draft" in saved["review_status"]
    listed = artifacts.list_test_plans()
    assert len(listed) == 1
    assert listed[0]["jira_key"] == "GUIDES-99999"
    loaded = artifacts.get_test_plan("GUIDES-99999")
    assert "Demo" in loaded["title"]


def test_qe_review_decision_preserves_revision_and_updates_status(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "TEST_PLANS_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "QE_REVIEWS_DIR", tmp_path / ".qe-reviews")
    monkeypatch.setattr(artifacts, "REVISIONS_DIR", tmp_path / ".revisions")
    markdown = "# Test Plan: GUIDES-99998 — Demo\n\n**Review status:** Draft\n"
    artifacts.save_test_plan("GUIDES-99998", markdown)

    requested = artifacts.record_qe_review_decision(
        "GUIDES-99998",
        action="request_changes",
        reviewer="QE1",
        comments="Add negative API case.",
    )
    assert requested["review_status"] == "QE Changes Requested"
    assert requested["decision"]["decision"] == "QE_CHANGES_REQUESTED"
    assert requested["qe_review"]["revision_history"]

    approved = artifacts.record_qe_review_decision(
        "GUIDES-99998",
        action="approve",
        reviewer="QE1",
        comments="Looks good after update.",
    )
    assert approved["review_status"] == "QE Approved"
    assert approved["decision"]["decision"] == "QE_APPROVED"
    assert len(approved["qe_review"]["decisions"]) == 2


def test_pipeline_memory_records_and_recalls_latest_run(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "TEST_PLANS_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "PIPELINE_MEMORY_DIR", tmp_path / ".pipeline-memory")
    monkeypatch.setattr(artifacts, "PIPELINE_MEMORY_INDEX", tmp_path / ".pipeline-memory" / "index.json")
    payload = {
        "jira_key": "GUIDES-99997",
        "correlation_id": "cid-1",
        "stages_completed": ["rag", "draft_test_plan"],
        "ticket_brief": {"jira_key": "GUIDES-99997", "summary": "Demo memory"},
        "score": {"overall": 82, "routing_status": "QE_REVIEW_WITH_FLAGS"},
        "qe_handoff": {"review_status": "Needs human review"},
        "draft_test_plan_markdown": "# Test Plan: GUIDES-99997\n",
    }

    entry = artifacts.record_pipeline_memory(payload)
    assert entry["jira_key"] == "GUIDES-99997"
    assert entry["score"] == 82

    listed = artifacts.list_pipeline_memory("GUIDES-99997")
    assert listed[0]["correlation_id"] == "cid-1"

    recalled = artifacts.get_pipeline_memory("GUIDES-99997")
    assert recalled["ticket_brief"]["summary"] == "Demo memory"
    assert recalled["draft_test_plan_markdown"].startswith("# Test Plan")
