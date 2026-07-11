"""Compute, persist, and aggregate chat answer quality for eval + self-learning."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.db.chat_models import ChatMessage, ChatMessageFeedback, ChatSession
from app.db.chat_quality_models import ChatAnswerQuality
from app.db.session import SessionLocal
from app.services.chat_service import _filter_chat_sessions_query
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

WEAK_PHRASE_PATTERNS = (
    r"couldn['\u2019]?t verify",
    r"don['\u2019]?t have enough (verified )?information",
    r"indexed evidence is too thin",
    r"grounding limit reached",
    r"i don['\u2019]?t have enough indexed evidence",
)

AEM_TOPIC_HINTS = (
    "output preset",
    "aem guides",
    "native pdf",
    "experience manager",
    "baseline",
    "publish profile",
)


def _parse_tool_results(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def detect_weak_phrases(content: str) -> bool:
    text = (content or "").lower()
    return any(re.search(pat, text) for pat in WEAK_PHRASE_PATTERNS)


def compute_quality_score(
    *,
    grounding: dict[str, Any] | None,
    answer_content: str,
    rating: str | None = None,
) -> int:
    grounding = grounding or {}
    status = str(grounding.get("status") or "none").lower()
    confidence = float(grounding.get("confidence") or 0.0)
    thin = bool(grounding.get("thin_evidence"))
    citations = grounding.get("citations") or []
    weak = detect_weak_phrases(answer_content)

    base = int(round(max(0.0, min(1.0, confidence)) * 100))
    if status == "none" and not grounding:
        base = 55
    if status == "grounded":
        base = max(base, 75)
    elif status == "partial":
        base = max(base, 55)
    elif status == "conflict":
        base = min(base, 45)
    elif status == "abstain":
        base = min(base, 35)

    if thin:
        base -= 15
    if weak:
        base -= 20
    if not citations and status not in {"none", ""}:
        base -= 10
    if rating == "up":
        base += 10
    elif rating == "down":
        base -= 15

    return max(0, min(100, base))


def build_improvement_hints(
    *,
    grounding: dict[str, Any] | None,
    answer_content: str,
    question: str = "",
) -> list[dict[str, str]]:
    grounding = grounding or {}
    hints: list[dict[str, str]] = []
    status = str(grounding.get("status") or "none").lower()
    reason = str(grounding.get("reason") or "").strip()
    combined = f"{question} {answer_content}".lower()

    if detect_weak_phrases(answer_content):
        hints.append(
            {
                "type": "weak_answer",
                "message": "Answer used abstention or weak-evidence phrasing. Add a learned Q&A seed or re-index RAG for this topic.",
            }
        )
    if status == "abstain":
        hints.append(
            {
                "type": "abstain",
                "message": reason or "Grounding abstained — indexed docs did not support a confident answer.",
            }
        )
    if grounding.get("thin_evidence"):
        hints.append(
            {
                "type": "thin_evidence",
                "message": "Evidence was thin. Run Experience League crawl or add a manual doc chunk for this topic.",
            }
        )
    if any(term in combined for term in AEM_TOPIC_HINTS):
        hints.append(
            {
                "type": "aem_guides",
                "message": "AEM Guides product topic — verify Experience League RAG and learned_qa seed coverage.",
                "action": "/settings",
            }
        )
    if not hints:
        hints.append(
            {
                "type": "general",
                "message": "Review citations in chat grounding panel; promote strong pairs to learned QA from Eval dashboard.",
            }
        )
    return hints


def extract_source_domain(grounding: dict[str, Any] | None) -> str | None:
    if not grounding:
        return None
    retrieval = grounding.get("retrieval") or {}
    if isinstance(retrieval, dict):
        domain = retrieval.get("source_domain")
        if domain:
            return str(domain)
    return None


def is_langsmith_tracing_enabled() -> bool:
    api_key = bool((os.getenv("LANGSMITH_API_KEY") or "").strip())
    tracing = (
        os.getenv("LANGSMITH_TRACING", "").lower() in ("true", "1", "yes")
        or os.getenv("LANGCHAIN_TRACING_V2", "").lower() in ("true", "1", "yes")
    )
    return api_key and tracing


def get_current_langsmith_run_id() -> str | None:
    if not is_langsmith_tracing_enabled():
        return None
    try:
        from langsmith.run_helpers import get_current_run_tree

        run = get_current_run_tree()
        if run is not None and getattr(run, "id", None):
            return str(run.id)
    except Exception:
        pass
    return None


def build_langsmith_trace_url(run_id: str | None) -> str | None:
    if not run_id:
        return None
    org = (os.getenv("LANGSMITH_ORG") or "").strip()
    project = (os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT") or "default").strip()
    if org:
        return f"https://smith.langchain.com/o/{org}/projects/p/{project}/r/{run_id}"
    # Public run link works without org slug when user is logged into LangSmith.
    return f"https://smith.langchain.com/public/{run_id}/r"


def record_chat_answer_quality(
    session_id: str,
    assistant_message_id: str,
    answer_content: str,
    *,
    tool_results: dict[str, Any] | None = None,
    user_message_id: str | None = None,
    langsmith_run_id: str | None = None,
) -> None:
    """Upsert quality row after assistant message is persisted."""
    db = SessionLocal()
    try:
        assistant = (
            db.query(ChatMessage)
            .filter(ChatMessage.id == assistant_message_id, ChatMessage.session_id == session_id)
            .first()
        )
        if assistant is None:
            return

        tool_data = tool_results if tool_results is not None else _parse_tool_results(assistant.tool_results)
        grounding = tool_data.get("_grounding") if isinstance(tool_data.get("_grounding"), dict) else {}

        if not user_message_id:
            user_msg = (
                db.query(ChatMessage)
                .filter(
                    ChatMessage.session_id == session_id,
                    ChatMessage.role == "user",
                    ChatMessage.created_at <= assistant.created_at,
                )
                .order_by(desc(ChatMessage.created_at))
                .first()
            )
            user_message_id = user_msg.id if user_msg else None

        question = ""
        if user_message_id:
            um = db.query(ChatMessage).filter(ChatMessage.id == user_message_id).first()
            question = str(um.content or "") if um else ""

        feedback = (
            db.query(ChatMessageFeedback)
            .filter(ChatMessageFeedback.message_id == assistant_message_id)
            .order_by(desc(ChatMessageFeedback.created_at))
            .first()
        )
        rating = feedback.rating if feedback else None

        weak = detect_weak_phrases(answer_content)
        status = str(grounding.get("status") or "none").lower()
        score = compute_quality_score(grounding=grounding, answer_content=answer_content, rating=rating)
        needs_review = weak or status == "abstain" or score < 60 or rating == "down"
        hints = build_improvement_hints(grounding=grounding, answer_content=answer_content, question=question)
        trace_url = build_langsmith_trace_url(langsmith_run_id)

        row = db.query(ChatAnswerQuality).filter(ChatAnswerQuality.message_id == assistant_message_id).first()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if row is None:
            row = ChatAnswerQuality(
                id=str(uuid4()),
                message_id=assistant_message_id,
                session_id=session_id,
                user_message_id=user_message_id,
                created_at=now,
            )
            db.add(row)

        row.user_message_id = user_message_id
        row.grounding_status = status
        row.confidence = float(grounding.get("confidence")) if grounding.get("confidence") is not None else None
        row.thin_evidence = bool(grounding.get("thin_evidence"))
        row.has_conflict = bool(grounding.get("has_conflict"))
        row.source_domain = extract_source_domain(grounding)
        row.answer_kind = str(grounding.get("answer_kind") or "") or None
        row.source_policy = str(grounding.get("source_policy") or "") or None
        row.quality_score = score
        row.weak_phrases_detected = weak
        row.needs_review = needs_review
        if rating == "down":
            row.needs_review = True
        row.improvement_hints_json = json.dumps(hints)
        if langsmith_run_id:
            row.langsmith_run_id = langsmith_run_id
            row.langsmith_trace_url = trace_url
        row.updated_at = now
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning_structured(
            "Failed to record chat answer quality",
            extra_fields={"message_id": assistant_message_id, "error": str(exc)},
        )
    finally:
        db.close()


def apply_feedback_to_quality(
    session: Session,
    *,
    message_id: str,
    rating: str,
    correction_text: str | None = None,
) -> None:
    row = session.query(ChatAnswerQuality).filter(ChatAnswerQuality.message_id == message_id).first()
    assistant = session.query(ChatMessage).filter(ChatMessage.id == message_id).first()
    if row is None and assistant is not None:
        record_chat_answer_quality(
            assistant.session_id,
            message_id,
            str(assistant.content or ""),
        )
        row = session.query(ChatAnswerQuality).filter(ChatAnswerQuality.message_id == message_id).first()
    if row is None:
        return

    grounding = {}
    if assistant and assistant.tool_results:
        tool_data = _parse_tool_results(assistant.tool_results)
        grounding = tool_data.get("_grounding") if isinstance(tool_data.get("_grounding"), dict) else {}

    row.quality_score = compute_quality_score(
        grounding=grounding,
        answer_content=str(assistant.content if assistant else ""),
        rating=rating,
    )
    if rating == "down":
        row.needs_review = True
        hints = json.loads(row.improvement_hints_json or "[]")
        if correction_text:
            hints.append({"type": "user_feedback", "message": correction_text.strip()[:500]})
        row.improvement_hints_json = json.dumps(hints)
    elif rating == "up":
        row.needs_review = False
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    session.flush()


def serialize_quality_row(row: ChatAnswerQuality | None) -> dict[str, Any] | None:
    if row is None:
        return None
    hints: list[dict] = []
    try:
        hints = json.loads(row.improvement_hints_json or "[]")
    except json.JSONDecodeError:
        hints = []
    return {
        "quality_score": row.quality_score,
        "grounding_status": row.grounding_status,
        "confidence": row.confidence,
        "thin_evidence": row.thin_evidence,
        "has_conflict": row.has_conflict,
        "source_domain": row.source_domain,
        "weak_phrases_detected": row.weak_phrases_detected,
        "needs_review": row.needs_review,
        "review_status": row.review_status,
        "langsmith_run_id": row.langsmith_run_id,
        "langsmith_trace_url": row.langsmith_trace_url,
        "improvement_hints": hints,
    }


def backfill_quality_from_messages(db: Session, *, limit: int = 5000) -> dict[str, int]:
    """Populate chat_answer_quality from existing assistant messages."""
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.role == "assistant")
        .order_by(desc(ChatMessage.created_at))
        .limit(limit)
        .all()
    )
    created = 0
    for msg in rows:
        existing = db.query(ChatAnswerQuality).filter(ChatAnswerQuality.message_id == msg.id).first()
        if existing:
            continue
        record_chat_answer_quality(msg.session_id, msg.id, str(msg.content or ""))
        created += 1
    return {"processed": len(rows), "created": created}


def get_chat_eval_trends(
    db: Session,
    *,
    user_id: str | None,
    tenant_id: str | None,
    is_admin: bool,
    days: int = 30,
) -> dict[str, Any]:
    allowed = db.query(ChatSession.id)
    allowed = _filter_chat_sessions_query(allowed, user_id=user_id, tenant_id=tenant_id, is_admin=is_admin)
    allowed_ids = [r[0] for r in allowed.all()]
    if not allowed_ids:
        return {"days": days, "series": []}

    since = datetime.utcnow() - timedelta(days=max(1, min(days, 90)))
    qualities = (
        db.query(ChatAnswerQuality)
        .filter(
            ChatAnswerQuality.session_id.in_(allowed_ids),
            ChatAnswerQuality.created_at >= since,
        )
        .all()
    )

    by_day: dict[str, dict[str, Any]] = {}
    for q in qualities:
        day = q.created_at.strftime("%Y-%m-%d") if q.created_at else "unknown"
        bucket = by_day.setdefault(
            day,
            {"date": day, "answers": 0, "quality_sum": 0, "abstain": 0, "weak": 0},
        )
        bucket["answers"] += 1
        bucket["quality_sum"] += int(q.quality_score or 0)
        if q.grounding_status == "abstain":
            bucket["abstain"] += 1
        if q.weak_phrases_detected:
            bucket["weak"] += 1

    series = []
    for day in sorted(by_day.keys()):
        b = by_day[day]
        count = b["answers"] or 1
        series.append(
            {
                "date": b["date"],
                "answers": b["answers"],
                "avg_quality": round(b["quality_sum"] / count, 1),
                "abstain_count": b["abstain"],
                "weak_count": b["weak"],
            }
        )
    return {"days": days, "series": series}


def get_chat_eval_breakdown(
    db: Session,
    *,
    user_id: str | None,
    tenant_id: str | None,
    is_admin: bool,
) -> dict[str, Any]:
    allowed = db.query(ChatSession.id)
    allowed = _filter_chat_sessions_query(allowed, user_id=user_id, tenant_id=tenant_id, is_admin=is_admin)
    allowed_ids = [r[0] for r in allowed.all()]
    if not allowed_ids:
        return {
            "by_grounding_status": [],
            "by_source_domain": [],
            "by_rating": [],
            "confidence_buckets": [],
        }

    qualities = db.query(ChatAnswerQuality).filter(ChatAnswerQuality.session_id.in_(allowed_ids)).all()

    status_counts: dict[str, int] = {}
    domain_counts: dict[str, int] = {}
    conf_buckets = {"0-25": 0, "26-50": 0, "51-75": 0, "76-100": 0}
    for q in qualities:
        status_counts[q.grounding_status or "none"] = status_counts.get(q.grounding_status or "none", 0) + 1
        dom = q.source_domain or "unknown"
        domain_counts[dom] = domain_counts.get(dom, 0) + 1
        score = int(q.quality_score or 0)
        if score <= 25:
            conf_buckets["0-25"] += 1
        elif score <= 50:
            conf_buckets["26-50"] += 1
        elif score <= 75:
            conf_buckets["51-75"] += 1
        else:
            conf_buckets["76-100"] += 1

    feedback_rows = (
        db.query(ChatMessageFeedback.rating, func.count(ChatMessageFeedback.id))
        .filter(ChatMessageFeedback.session_id.in_(allowed_ids))
        .group_by(ChatMessageFeedback.rating)
        .all()
    )
    rating_map = {str(r): int(c) for r, c in feedback_rows}
    assistant_count = (
        db.query(func.count(ChatMessage.id))
        .filter(ChatMessage.role == "assistant", ChatMessage.session_id.in_(allowed_ids))
        .scalar()
        or 0
    )
    rated = sum(rating_map.values())
    rating_map["none"] = max(0, int(assistant_count) - rated)

    avg_quality = (
        round(sum(int(q.quality_score or 0) for q in qualities) / len(qualities), 1) if qualities else 0.0
    )
    abstain_count = sum(1 for q in qualities if q.grounding_status == "abstain")

    return {
        "avg_quality_score": avg_quality,
        "abstain_rate": round(abstain_count / len(qualities), 3) if qualities else 0.0,
        "by_grounding_status": [{"label": k, "count": v} for k, v in sorted(status_counts.items())],
        "by_source_domain": [{"label": k, "count": v} for k, v in sorted(domain_counts.items())],
        "by_rating": [{"label": k, "count": v} for k, v in sorted(rating_map.items())],
        "confidence_buckets": [{"label": k, "count": v} for k, v in conf_buckets.items()],
    }


def promote_eval_pair_to_learned_qa(
    db: Session,
    *,
    message_id: str,
    user_id: str | None,
    tenant_id: str | None,
    is_admin: bool,
) -> dict[str, Any]:
    """Create a pending learned-QA entry from an eval dashboard pair."""
    from app.services.learned_qa_service import LEARNED_QA_ANSWER_STYLE, upsert_learned_prompt_entry

    assistant = db.query(ChatMessage).filter(ChatMessage.id == message_id, ChatMessage.role == "assistant").first()
    if assistant is None:
        raise LookupError("Assistant message not found")

    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == assistant.session_id)
        .first()
    )
    if session is None:
        raise LookupError("Session not found")

    allowed = _filter_chat_sessions_query(
        db.query(ChatSession).filter(ChatSession.id == session.id),
        user_id=user_id,
        tenant_id=tenant_id,
        is_admin=is_admin,
    )
    if allowed.first() is None:
        raise PermissionError("Not authorized for this session")

    user_message = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == assistant.session_id,
            ChatMessage.role == "user",
            ChatMessage.created_at <= assistant.created_at,
        )
        .order_by(desc(ChatMessage.created_at))
        .first()
    )
    if user_message is None:
        raise LookupError("User question not found for this answer")

    prompt = str(user_message.content or "").strip()
    final_answer = str(assistant.content or "").strip()
    if not prompt or not final_answer:
        raise ValueError("Question and answer must be non-empty")

    entry, created, dedupe_kind = upsert_learned_prompt_entry(
        db,
        prompt=prompt,
        final_answer=final_answer,
        source_type="eval_promote",
        status="pending_review",
        answer_style=LEARNED_QA_ANSWER_STYLE,
        session_id=assistant.session_id,
        message_id=message_id,
    )
    db.commit()
    return {
        "entry_id": entry.id,
        "created": created,
        "dedupe_kind": dedupe_kind,
        "status": entry.status,
    }


def set_eval_pair_review_status(
    db: Session,
    *,
    message_id: str,
    review_status: str,
    user_id: str | None,
    tenant_id: str | None,
    is_admin: bool,
) -> dict[str, Any]:
    """Admin review marker for eval dashboard quality rows."""
    if review_status not in {"pass", "fail", "needs_seed"}:
        raise ValueError("review_status must be pass, fail, or needs_seed")

    assistant = db.query(ChatMessage).filter(ChatMessage.id == message_id, ChatMessage.role == "assistant").first()
    if assistant is None:
        raise LookupError("Assistant message not found")

    allowed = _filter_chat_sessions_query(
        db.query(ChatSession).filter(ChatSession.id == assistant.session_id),
        user_id=user_id,
        tenant_id=tenant_id,
        is_admin=is_admin,
    )
    if allowed.first() is None:
        raise PermissionError("Not authorized for this session")

    row = db.query(ChatAnswerQuality).filter(ChatAnswerQuality.message_id == message_id).first()
    if row is None:
        record_chat_answer_quality(assistant.session_id, message_id, str(assistant.content or ""))
        row = db.query(ChatAnswerQuality).filter(ChatAnswerQuality.message_id == message_id).first()
    if row is None:
        raise LookupError("Quality record not found")

    row.review_status = review_status
    if review_status == "pass":
        row.needs_review = False
    else:
        row.needs_review = True
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return serialize_quality_row(row) or {}
