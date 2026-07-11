"""Tests for chat evaluation dashboard Q&A listing and quality metrics."""

import json
from datetime import datetime, timedelta
from uuid import uuid4

from app.db.chat_models import ChatMessage, ChatMessageFeedback, ChatSession
from app.db.chat_quality_models import ChatAnswerQuality
from app.db.session import SessionLocal
from app.services.chat_eval_dashboard_service import get_chat_eval_stats, list_chat_eval_pairs
from app.services.chat_quality_service import (
    compute_quality_score,
    detect_weak_phrases,
    get_chat_eval_breakdown,
    get_chat_eval_trends,
    record_chat_answer_quality,
    serialize_quality_row,
)


def _seed_pair(
    *,
    question: str,
    answer: str,
    user_id: str = "dev-user",
    rating: str | None = None,
    grounding: dict | None = None,
) -> tuple[str, str]:
    session_id = str(uuid4())
    user_msg_id = str(uuid4())
    assistant_msg_id = str(uuid4())
    db = SessionLocal()
    try:
        base = datetime.utcnow()
        db.add(
            ChatSession(
                id=session_id,
                user_id=user_id,
                tenant_id="default",
                title=f"Eval {question[:24]}",
                created_at=base,
                updated_at=base,
            )
        )
        db.flush()
        tool_results = json.dumps({"_grounding": grounding}) if grounding else None
        db.add(
            ChatMessage(
                id=user_msg_id,
                session_id=session_id,
                role="user",
                content=question,
                created_at=base,
            )
        )
        db.add(
            ChatMessage(
                id=assistant_msg_id,
                session_id=session_id,
                role="assistant",
                content=answer,
                tool_results=tool_results,
                created_at=base + timedelta(seconds=1),
            )
        )
        if rating:
            db.add(
                ChatMessageFeedback(
                    id=str(uuid4()),
                    message_id=assistant_msg_id,
                    session_id=session_id,
                    rating=rating,
                    auto_detected=False,
                    created_at=base + timedelta(seconds=2),
                )
            )
        db.commit()
    finally:
        db.close()
    record_chat_answer_quality(session_id, assistant_msg_id, answer, tool_results={"_grounding": grounding} if grounding else None)
    return session_id, assistant_msg_id


def test_list_chat_eval_pairs_returns_question_and_answer():
    question = f"What is conref? {uuid4()}"
    answer = f"Conref reuses content. {uuid4()}"
    _seed_pair(question=question, answer=answer)

    db = SessionLocal()
    try:
        result = list_chat_eval_pairs(
            db,
            user_id="dev-user",
            tenant_id="default",
            is_admin=False,
            search=question,
            limit=20,
        )
    finally:
        db.close()

    match = next((item for item in result["items"] if item["question"] == question), None)
    assert match is not None
    assert match["answer"] == answer
    assert match["rating"] is None
    assert "quality_score" in match


def test_list_chat_eval_pairs_filters_by_rating():
    question = f"PDF theme question {uuid4()}"
    answer = f"Use --theme for PDF styling. {uuid4()}"
    _seed_pair(question=question, answer=answer, rating="up")

    db = SessionLocal()
    try:
        result = list_chat_eval_pairs(
            db,
            user_id="dev-user",
            tenant_id="default",
            is_admin=False,
            search=question,
            rating="up",
            limit=20,
        )
    finally:
        db.close()

    assert any(item["question"] == question and item["rating"] == "up" for item in result["items"])


def test_get_chat_eval_stats_includes_pair_counts():
    question = f"Stats pair question {uuid4()}"
    answer = f"Stats pair answer {uuid4()}"
    _seed_pair(question=question, answer=answer)

    db = SessionLocal()
    try:
        stats = get_chat_eval_stats(
            db,
            user_id="dev-user",
            tenant_id="default",
            is_admin=False,
        )
    finally:
        db.close()

    assert stats["total_pairs"] >= 1
    assert stats["total_sessions"] >= 1
    assert "thumbs_up" in stats
    assert "unrated_pairs" in stats
    assert "avg_quality_score" in stats


def test_compute_quality_score_abstain_penalty():
    score = compute_quality_score(
        grounding={"status": "abstain", "confidence": 0.2, "thin_evidence": True, "citations": []},
        answer_content="I couldn't verify this directly from the indexed evidence.",
    )
    assert score < 50
    assert detect_weak_phrases("I couldn't verify this directly from the indexed evidence.")


def test_weak_only_filter():
    question = f"Weak abstain question {uuid4()}"
    answer = "I couldn't verify this directly from the indexed evidence."
    _seed_pair(
        question=question,
        answer=answer,
        grounding={"status": "abstain", "confidence": 0.15, "thin_evidence": True, "citations": []},
    )

    db = SessionLocal()
    try:
        result = list_chat_eval_pairs(
            db,
            user_id="dev-user",
            tenant_id="default",
            is_admin=False,
            search=question,
            weak_only=True,
            limit=20,
        )
    finally:
        db.close()

    assert any(item["question"] == question for item in result["items"])


def test_get_chat_eval_trends_and_breakdown():
    question = f"Trend question {uuid4()}"
    answer = f"Trend answer {uuid4()}"
    _seed_pair(
        question=question,
        answer=answer,
        grounding={"status": "grounded", "confidence": 0.85, "citations": [{"id": "E1"}]},
    )

    db = SessionLocal()
    try:
        trends = get_chat_eval_trends(
            db,
            user_id="dev-user",
            tenant_id="default",
            is_admin=False,
            days=30,
        )
        breakdown = get_chat_eval_breakdown(
            db,
            user_id="dev-user",
            tenant_id="default",
            is_admin=False,
        )
        row = db.query(ChatAnswerQuality).filter(ChatAnswerQuality.session_id.isnot(None)).first()
        serialized = serialize_quality_row(row)
    finally:
        db.close()

    assert "series" in trends
    assert "by_grounding_status" in breakdown
    assert "confidence_buckets" in breakdown
    if serialized:
        assert "improvement_hints" in serialized
