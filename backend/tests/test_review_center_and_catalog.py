from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.db.chat_models import ChatMessage, ChatSession
from app.db.learned_prompt_models import LearnedPromptEntry
from app.db.session import SessionLocal
from app.services.learned_qa_service import (
    _read_seed_items,
    get_learned_qa_summary,
    is_learned_qa_domain_query,
    normalize_prompt,
    retrieve_learned_qa,
    seed_learned_qa,
    sync_learned_qa_corpus,
)
from app.services.learned_qa_oxygen_customer_seed import get_oxygen_customer_seed_items
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
    assert by_id["bookmap_elements_reference"]["full_example_xml"].lstrip().startswith("<bookmap>")
    assert by_id["dita_conref_title_dataset_recipe"]["params_schema"]["variables"] == "list"


def test_seeded_learned_qa_appears_in_review_center_and_rag_status(client, auth_headers, monkeypatch):
    expected_count = len(_read_seed_items())
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

        unique_prompt = (
            f"Transient review-center capture proof {uuid4()} "
            f"zebra quartz nebula {uuid4()} glacier orbit lantern {uuid4()}"
        )
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


def test_seeded_learned_qa_keeps_similar_tag_prompts_separate(monkeypatch, tmp_path):
    seed_path = tmp_path / "learned_qa_seed.json"
    seed_path.write_text(
        json.dumps(
            [
                {
                    "prompt": "What is topicref in DITA? Show an example.",
                    "final_answer": "## Short answer\nUse `<topicref>` in a map.\n\n```xml\n<topicref href=\"intro.dita\"/>\n```",
                    "tags": ["topicref", "dita"],
                    "topic": "maps",
                    "answer_style": "senior_technical_docs",
                },
                {
                    "prompt": "What is prolog in DITA? Show an example.",
                    "final_answer": "## Short answer\nUse `<prolog>` for metadata.\n\n```xml\n<prolog><metadata/></prolog>\n```",
                    "tags": ["prolog", "dita"],
                    "topic": "dita_authoring",
                    "answer_style": "senior_technical_docs",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("app.services.learned_qa_service.LEARNED_QA_SEED_PATH", seed_path)
    monkeypatch.setattr("app.services.learned_qa_service.is_chroma_available", lambda: False)

    db = SessionLocal()
    try:
        result = seed_learned_qa(db)
        prompts = {
            row.prompt
            for row in db.query(LearnedPromptEntry)
            .filter(LearnedPromptEntry.status == "approved")
            .all()
        }
    finally:
        db.close()

    assert result["total"] == 2
    assert {
        "What is topicref in DITA? Show an example.",
        "What is prolog in DITA? Show an example.",
    }.issubset(prompts)

    topicref = retrieve_learned_qa("What is topicref in DITA? Show an example.", k=1)
    assert topicref[0]["prompt"] == "What is topicref in DITA? Show an example."
    assert "<topicref" in topicref[0]["final_answer"]


def test_default_seed_loader_keeps_first_rich_answer_for_duplicate_eval_prompts():
    items = _read_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    answer = by_prompt["What is the difference between concept, task, and reference topics?"]
    assert "<concept id=\"why_keys\">" in answer
    assert "Senior answer requirements" not in answer


def test_enterprise_dita_seed_records_are_retrievable(monkeypatch):
    monkeypatch.setattr("app.services.learned_qa_service.is_chroma_available", lambda: False)

    db = SessionLocal()
    try:
        seed_learned_qa(db)
    finally:
        db.close()

    direct = retrieve_learned_qa("When should direct addressing be preferred over key-based indirect addressing?", k=1)
    assert direct[0]["prompt"] == "When should direct addressing be preferred over key-based indirect addressing?"
    assert "direct URI addressing" in direct[0]["final_answer"]
    assert "## Must not claim" in direct[0]["final_answer"]

    cms = retrieve_learned_qa("How should a CMS determine the active root map for standalone topic editing?", k=1)
    assert cms[0]["prompt"] == "How should a CMS determine the active root map for standalone topic editing?"
    assert "multiple valid root maps" in cms[0]["final_answer"]

    cache = retrieve_learned_qa("How should caches be invalidated when a key-defining map changes?", k=1)
    assert cache[0]["prompt"] == "How should caches be invalidated when a key-defining map changes?"
    assert "key-defining map" in cache[0]["final_answer"]

    chatbot = retrieve_learned_qa("How should a DITA chatbot distinguish specification-defined behavior from processor-specific behavior?", k=1)
    assert chatbot[0]["prompt"] == "How should a DITA chatbot distinguish specification-defined behavior from processor-specific behavior?"
    assert "DITA-OT behavior is always the DITA specification" in chatbot[0]["final_answer"]

    failure = retrieve_learned_qa(
        "A conkeyref works when publishing the root map but fails when previewing the topic. Why?",
        k=1,
    )
    assert failure[0]["prompt"] == "A conkeyref works when publishing the root map but fails when previewing the topic. Why?"
    assert "topic-only preview" in failure[0]["final_answer"]

    grounding = retrieve_learned_qa(
        "A topic is published correctly but the chatbot gives the wrong explanation of why. How would you design a source-grounded evaluation to detect the hallucination?",
        k=1,
    )
    assert grounding[0]["prompt"].startswith("A topic is published correctly")
    assert "source XML, effective map context, processor logs" in grounding[0]["final_answer"]

    uri = retrieve_learned_qa("What is direct URI-based addressing in DITA?", k=1)
    assert uri[0]["prompt"] == "What is direct URI-based addressing in DITA?"
    assert "source XML points directly" in uri[0]["final_answer"]

    fragment = retrieve_learned_qa("What does the URI topic.dita#topicId/elementId address?", k=1)
    assert fragment[0]["prompt"] == "What does the URI topic.dita#topicId/elementId address?"
    assert "element with ID `elementId`" in fragment[0]["final_answer"]

    duplicate_key = retrieve_learned_qa("How is the effective definition selected when duplicate key definitions exist?", k=1)
    assert duplicate_key[0]["prompt"] == "How is the effective definition selected when duplicate key definitions exist?"
    assert "The last duplicate key always wins universally." in duplicate_key[0]["final_answer"]

    resource_only = retrieve_learned_qa('What is the semantic meaning of processing-role="resource-only"?', k=1)
    assert resource_only[0]["prompt"] == 'What is the semantic meaning of processing-role="resource-only"?'
    assert "supporting material rather than normal reading-order content" in resource_only[0]["final_answer"]

    toc = retrieve_learned_qa('Does toc="no" mean the topic should not be generated?', k=1)
    assert toc[0]["prompt"] == 'Does toc="no" mean the topic should not be generated?'
    assert "omitted from generated navigation" in toc[0]["final_answer"]

    reltable = retrieve_learned_qa("How does a relationship table generate related links?", k=1)
    assert reltable[0]["prompt"] == "How does a relationship table generate related links?"
    assert "Each `relrow` defines a relationship set." in reltable[0]["final_answer"]

    sourceonly = retrieve_learned_qa('What is the effect of linking="sourceonly"?', k=1)
    assert sourceonly[0]["prompt"] == 'What is the effect of linking="sourceonly"?'
    assert "source of generated links" in sourceonly[0]["final_answer"]

    mapref = retrieve_learned_qa(
        "What is the difference between referencing a map with mapref and referencing it using a normal topicref?",
        k=1,
    )
    assert mapref[0]["prompt"] == "What is the difference between referencing a map with mapref and referencing it using a normal topicref?"
    assert "map-to-map composition" in mapref[0]["final_answer"]

    navref = retrieve_learned_qa("How does navref differ from including a submap through mapref?", k=1)
    assert navref[0]["prompt"] == "How does navref differ from including a submap through mapref?"
    assert "navigation-oriented" in navref[0]["final_answer"]

    branch = retrieve_learned_qa("What is branch filtering in DITA?", k=1)
    assert branch[0]["prompt"] == "What is branch filtering in DITA?"
    assert "specific branch of a DITA map" in branch[0]["final_answer"]

    resource_prefix = retrieve_learned_qa("How do resourceprefix and resourcesuffix prevent naming collisions?", k=1)
    assert resource_prefix[0]["prompt"] == "How do resourceprefix and resourcesuffix prevent naming collisions?"
    assert "branch-specific text to generated resource names" in resource_prefix[0]["final_answer"]


def test_oxygen_customer_questions_seed_all_400_records():
    items = get_oxygen_customer_seed_items()

    assert len(items) == 400
    assert all(item["source_type"] == "oxygen_customer_questions" for item in items)
    assert all(item["answer_style"] == "senior_technical_docs" for item in items)
    assert all("## Deterministic checks" in item["final_answer"] for item in items)
    assert all("not an authoritative forum citation" in item["final_answer"] for item in items)

    prompts = {item["prompt"] for item in items}
    assert "Why am I getting DITA-OT warnings in Oxygen 28 that did not appear in Oxygen 26?" in prompts
    assert "Why does my conref work in Author mode but fail during publishing?" in prompts
    assert "Why does a keyref work when publishing the root map but fail when publishing the submap alone?" in prompts
    assert "How can I compare Oxygen desktop publishing, Oxygen Publishing Engine, and CI output to find configuration differences?" in prompts
    assert "How can I exclude the mini-TOC from only selected chapters?" in prompts
    assert "Why are keys defined in a subject-scheme map not available in Oxygen Author mode?" in prompts
    assert "How should review metadata be preserved when topics are moved or renamed?" in prompts


def test_oxygen_customer_questions_are_retrievable_and_counted(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.learned_qa_service.is_chroma_available", lambda: False)
    monkeypatch.setattr("app.services.learned_qa_service.sync_learned_qa_corpus", lambda *args, **kwargs: {})
    sample_questions = {
        "Why am I getting DITA-OT warnings in Oxygen 28 that did not appear in Oxygen 26?",
        "Why does my conref work in Author mode but fail during publishing?",
        "Why does a keyref work when publishing the root map but fail when publishing the submap alone?",
        "How can I compare Oxygen desktop publishing, Oxygen Publishing Engine, and CI output to find configuration differences?",
    }
    seed_path = tmp_path / "learned_qa_seed.json"
    seed_items = [item for item in get_oxygen_customer_seed_items() if item["prompt"] in sample_questions]
    seed_path.write_text(json.dumps(seed_items), encoding="utf-8")
    monkeypatch.setattr("app.services.learned_qa_service.LEARNED_QA_SEED_PATH", seed_path)

    db = SessionLocal()
    try:
        seed_learned_qa(db)
        summary = get_learned_qa_summary(db)
    finally:
        db.close()

    assert summary["customer_question_count"] >= 4
    assert summary["source_type_counts"]["oxygen_customer_questions"]["approved"] >= 4

    upgrade = retrieve_learned_qa("Why am I getting DITA-OT warnings in Oxygen 28 that did not appear in Oxygen 26?", k=1)
    assert upgrade[0]["source_type"] == "oxygen_customer_questions"
    assert "environment and processor-version regression" in upgrade[0]["final_answer"]
    assert "DITA specification behavior" in upgrade[0]["final_answer"]

    conref = retrieve_learned_qa("Why does my conref work in Author mode but fail during publishing?", k=1)
    assert conref[0]["source_type"] == "oxygen_customer_questions"
    assert "active publication" in conref[0]["final_answer"]
    assert "preprocessing context" in conref[0]["final_answer"]
    assert "`@conref` URI" in conref[0]["final_answer"]
    assert "topic ID, element ID" in conref[0]["final_answer"]
    assert "structurally compatible specialization" in conref[0]["final_answer"]
    assert "publication dependency graph" in conref[0]["final_answer"]

    keyref = retrieve_learned_qa("Why does a keyref work when publishing the root map but fail when publishing the submap alone?", k=1)
    assert keyref[0]["source_type"] == "oxygen_customer_questions"
    assert "active root map" in keyref[0]["final_answer"]
    assert "effective key space" in keyref[0]["final_answer"]
    assert "selected key scope" in keyref[0]["final_answer"]
    assert "filtered-out key definitions" in keyref[0]["final_answer"]

    ci = retrieve_learned_qa(
        "How can I compare Oxygen desktop publishing, Oxygen Publishing Engine, and CI output to find configuration differences?",
        k=1,
    )
    assert ci[0]["source_type"] == "oxygen_customer_questions"
    assert "versions" in ci[0]["final_answer"]
    assert "full logs" in ci[0]["final_answer"]


def test_oxygen_customer_normalization_and_domain_detector_handles_customer_wording(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.learned_qa_service.is_chroma_available", lambda: False)
    monkeypatch.setattr("app.services.learned_qa_service.sync_learned_qa_corpus", lambda *args, **kwargs: {})
    sample_questions = {
        "Why does content that published successfully in the previous Oxygen version now generate warnings?",
        "How do I verify which root map Oxygen is using to resolve the key?",
    }
    seed_path = tmp_path / "learned_qa_seed.json"
    seed_items = [item for item in get_oxygen_customer_seed_items() if item["prompt"] in sample_questions]
    seed_path.write_text(json.dumps(seed_items), encoding="utf-8")
    monkeypatch.setattr("app.services.learned_qa_service.LEARNED_QA_SEED_PATH", seed_path)

    db = SessionLocal()
    try:
        seed_learned_qa(db)
    finally:
        db.close()

    assert normalize_prompt("productâ€™s navigation") == "product's navigation"
    assert is_learned_qa_domain_query("Why does content that published successfully now generate warnings?")
    assert is_learned_qa_domain_query("How do I verify which root map Oxygen is using to resolve the key?")
