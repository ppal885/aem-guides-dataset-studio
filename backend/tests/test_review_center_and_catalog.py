from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.db.chat_models import ChatMessage, ChatSession
from app.db.learned_prompt_models import LearnedPromptEntry
from app.db.session import SessionLocal
from app.services.learned_qa_service import sync_learned_qa_corpus
from app.services.source_review_state_service import load_source_state
from app.services.vector_store_service import CHROMA_COLLECTION_LEARNED_QA


def test_recipe_catalog_endpoint(client, auth_headers):
    response = client.get("/api/v1/recipes/catalog", headers=auth_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total_count"] > 0
    assert payload["entries"]
    assert payload["quick_workflows"]
    first = payload["entries"][0]
    assert "id" in first
    assert "params_schema" in first
    assert "full_example_xml" in first
    assert "expected_result" in first

    ids = {entry["id"] for entry in payload["entries"]}
    assert "xref.external_url" in ids
    assert "xref_external_url" not in ids

    by_id = {entry["id"]: entry for entry in payload["entries"]}
    bookmap_entry = by_id["bookmap_elements_reference"]
    assert "<bookmap" in bookmap_entry["full_example_xml"]
    curated = by_id["curated_realtime_corpus"]
    assert "source:stackoverflow" in curated["full_example_xml"]
    assert "source:blockchain" in curated["full_example_xml"]
    assert "<title>Tags</title>" in curated["full_example_xml"]
    assert "curated_root_sample.ditamap" in curated["full_example_xml"]
    assert "topics/curated/" in curated["full_example_xml"]
    audience = by_id["metadata.audience_platform_basic"]
    assert 'audience="admin"' in audience["full_example_xml"]
    assert "Representative output for this recipe" not in audience["full_example_xml"]
    assert "metadata.audience_platform_basic" in audience["expected_result"]
    choicetable = by_id["choicetable_tasks"]
    assert "choicetable" in choicetable["full_example_xml"]
    assert "Representative output for this recipe" not in choicetable["full_example_xml"]
    assert by_id["dita_conref_title_dataset_recipe"]["params_schema"]["variables"] == "list"


def test_seeded_learned_qa_appears_in_review_center_and_rag_status(client, auth_headers, monkeypatch):
    expected_count = len(
        json.loads(
            (Path(__file__).resolve().parents[1] / "app" / "storage" / "learned_qa_seed.json").read_text(encoding="utf-8")
        )
    )
    monkeypatch.setattr(
        "app.api.v1.routes.review_center.index_approved_learned_qa",
        lambda session, force_reindex=True: {"collection": CHROMA_COLLECTION_LEARNED_QA, "indexed": expected_count, "errors": []},
    )
    monkeypatch.setattr("app.services.vector_store_service.is_chroma_available", lambda: True)
    monkeypatch.setattr(
        "app.services.vector_store_service.get_collection_count",
        lambda collection: expected_count if collection == CHROMA_COLLECTION_LEARNED_QA else 0,
    )
    monkeypatch.setattr("app.services.review_center_service.is_chroma_available", lambda: True)
    monkeypatch.setattr(
        "app.services.review_center_service.get_collection_count",
        lambda collection: expected_count if collection == CHROMA_COLLECTION_LEARNED_QA else 0,
    )

    seed_response = client.post("/api/v1/ai/learned-qa/seed", headers=auth_headers)
    assert seed_response.status_code == 200, seed_response.text
    seed_payload = seed_response.json()
    assert (seed_payload["seed"]["created"] + seed_payload["seed"]["updated"]) >= 1

    review_response = client.get("/api/v1/ai/review-center", headers=auth_headers)
    assert review_response.status_code == 200, review_response.text
    review_payload = review_response.json()
    learned_source = next(source for source in review_payload["sources"] if source["source_id"] == "learned_qa")
    assert learned_source["chunk_count"] == expected_count
    assert review_payload["candidate_counts"]["approved"] >= 1

    rag_response = client.get("/api/v1/ai/rag-status", headers=auth_headers)
    assert rag_response.status_code == 200, rag_response.text
    rag_payload = rag_response.json()
    assert "learned_qa" in rag_payload
    assert rag_payload["learned_qa"]["chunk_count"] == expected_count


def test_feedback_capture_only_learns_latest_assistant_draft(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.routes.review_center.index_approved_learned_qa",
        lambda session, force_reindex=True: {"collection": CHROMA_COLLECTION_LEARNED_QA, "indexed": 1, "errors": []},
    )

    now = datetime.utcnow()
    session_id = f"sess-review-{uuid4()}"
    user_message_id = f"msg-user-{uuid4()}"
    assistant_old_id = f"msg-assistant-{uuid4()}"
    assistant_new_id = f"msg-assistant-{uuid4()}"
    db = SessionLocal()
    try:
        session_row = ChatSession(
            id=session_id,
            user_id="test-user-1",
            tenant_id="kone",
            title="review",
            created_at=now,
            updated_at=now,
        )
        db.add(session_row)
        db.commit()

        unique_prompt = f"Transient review-center capture proof {uuid4()} zebra quartz nebula"
        user_msg = ChatMessage(id=user_message_id, session_id=session_id, role="user", content=unique_prompt, created_at=now)
        assistant_old = ChatMessage(
            id=assistant_old_id,
            session_id=session_id,
            role="assistant",
            content="Older draft answer",
            created_at=now + timedelta(seconds=1),
        )
        assistant_new = ChatMessage(
            id=assistant_new_id,
            session_id=session_id,
            role="assistant",
            content="Final accepted answer about keyscope.",
            created_at=now + timedelta(seconds=2),
        )
        db.add_all([user_msg, assistant_old, assistant_new])
        db.commit()
    finally:
        db.close()

    skipped_response = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages/{assistant_old_id}/feedback",
        headers=auth_headers,
        json={"rating": "up"},
    )
    assert skipped_response.status_code == 200, skipped_response.text
    assert skipped_response.json()["learned_capture"]["reason"] == "superseded_assistant_draft"

    accepted_response = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages/{assistant_new_id}/feedback",
        headers=auth_headers,
        json={"rating": "up"},
    )
    assert accepted_response.status_code == 200, accepted_response.text
    capture = accepted_response.json()["learned_capture"]
    assert capture["entry"]["status"] == "pending_review"
    assert capture["entry"]["final_answer"] == "Final accepted answer about keyscope."

    candidates_response = client.get(
        "/api/v1/ai/review-center/candidates?status=pending_review",
        headers=auth_headers,
    )
    assert candidates_response.status_code == 200, candidates_response.text
    candidates = candidates_response.json()["items"]
    assert any(item["prompt"] == unique_prompt for item in candidates)

    entry_id = capture["entry"]["id"]
    approve_response = client.post(
        f"/api/v1/ai/review-center/candidates/{entry_id}/approve",
        headers=auth_headers,
    )
    assert approve_response.status_code == 200, approve_response.text
    assert approve_response.json()["entry"]["status"] == "approved"

    db = SessionLocal()
    try:
        stored = db.query(LearnedPromptEntry).filter(LearnedPromptEntry.id == entry_id).first()
        assert stored is not None
        assert stored.status == "approved"
    finally:
        db.close()


def test_review_center_and_rag_status_auto_sync_learned_qa(client, auth_headers, monkeypatch):
    calls: list[str] = []

    def fake_sync(session, **kwargs):
        del session
        calls.append(str(kwargs.get("reason") or ""))
        return {
            "seed": {"created": 0, "updated": 0, "total": 0},
            "index": {"collection": CHROMA_COLLECTION_LEARNED_QA, "indexed": 0, "errors": []},
            "performed_seed": False,
            "performed_reindex": False,
            "approved_count": 0,
            "indexed_count": 0,
            "seed_item_count": 0,
        }

    monkeypatch.setattr("app.api.v1.routes.review_center.sync_learned_qa_corpus", fake_sync)
    monkeypatch.setattr("app.services.learned_qa_service.sync_learned_qa_corpus", fake_sync)

    review_response = client.get(f"/api/v1/ai/review-center?cache_bust={uuid4()}", headers=auth_headers)
    assert review_response.status_code == 200, review_response.text

    rag_response = client.get(f"/api/v1/ai/rag-status?cache_bust={uuid4()}", headers=auth_headers)
    assert rag_response.status_code == 200, rag_response.text

    assert "review_center" in calls
    assert "rag_status" in calls


def test_sync_learned_qa_corpus_skips_reindex_when_seed_is_unchanged(monkeypatch, tmp_path):
    unique_prompt = f"How should auto sync handle unique learned QA prompt {uuid4()}?"
    seed_path = tmp_path / "learned_qa_seed.json"
    seed_path.write_text(
        json.dumps(
            [
                {
                    "prompt": unique_prompt,
                    "final_answer": "Direct answer first.\n\nUse a single approved prompt-answer pair for the test.",
                    "tags": ["dita", "testing"],
                    "topic": "dita_general",
                    "answer_style": "senior_technical_docs",
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    state_dir = tmp_path / "knowledge_source_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    indexed = {"count": 0}
    index_calls = {"count": 0}

    def fake_index(session, force_reindex=False):
        del force_reindex
        index_calls["count"] += 1
        indexed["count"] = (
            session.query(LearnedPromptEntry)
            .filter(LearnedPromptEntry.status == "approved")
            .count()
        )
        return {
            "collection": CHROMA_COLLECTION_LEARNED_QA,
            "indexed": indexed["count"],
            "errors": [],
        }

    monkeypatch.setattr("app.services.learned_qa_service.LEARNED_QA_SEED_PATH", seed_path)
    monkeypatch.setattr("app.services.source_review_state_service._state_dir", lambda: state_dir)
    monkeypatch.setattr("app.services.learned_qa_service.index_approved_learned_qa", fake_index)
    monkeypatch.setattr("app.services.learned_qa_service.is_chroma_available", lambda: True)
    monkeypatch.setattr(
        "app.services.learned_qa_service.get_collection_count",
        lambda collection: indexed["count"] if collection == CHROMA_COLLECTION_LEARNED_QA else 0,
    )

    db = SessionLocal()
    try:
        first = sync_learned_qa_corpus(db, reason="test_auto_sync")
        second = sync_learned_qa_corpus(db, reason="test_auto_sync")
    finally:
        db.close()

    assert first["performed_seed"] is True
    assert first["performed_reindex"] is True
    assert second["performed_seed"] is False
    assert second["performed_reindex"] is False
    assert index_calls["count"] == 1

    state = load_source_state(CHROMA_COLLECTION_LEARNED_QA)
    assert state.last_stats["seed_hash"]
    assert int(state.last_stats["seed_item_count"]) == 1
