"""List chat Q&A pairs for the evaluation dashboard."""

from __future__ import annotations

from sqlalchemy import desc, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.db.chat_models import ChatMessage, ChatMessageFeedback, ChatSession
from app.db.chat_quality_models import ChatAnswerQuality
from app.services.chat_service import _filter_chat_sessions_query
from app.services.chat_quality_service import serialize_quality_row

MAX_CONTENT_CHARS = 12000


def _truncate(text: str | None, limit: int = MAX_CONTENT_CHARS) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _allowed_session_ids_subquery(
    db: Session,
    *,
    user_id: str | None,
    tenant_id: str | None,
    is_admin: bool,
):
    query = db.query(ChatSession.id)
    query = _filter_chat_sessions_query(query, user_id=user_id, tenant_id=tenant_id, is_admin=is_admin)
    return query.subquery()


def _latest_user_message(db: Session, *, session_id: str, before) -> ChatMessage | None:
    return (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session_id,
            ChatMessage.role == "user",
            ChatMessage.created_at < before,
        )
        .order_by(desc(ChatMessage.created_at))
        .first()
    )


def _assistant_base_query(
    db: Session,
    *,
    user_id: str | None,
    tenant_id: str | None,
    is_admin: bool,
    search: str | None,
    rating: str | None,
):
    allowed_sessions = _allowed_session_ids_subquery(
        db,
        user_id=user_id,
        tenant_id=tenant_id,
        is_admin=is_admin,
    )

    query = (
        db.query(ChatMessage, ChatSession)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .filter(
            ChatMessage.role == "assistant",
            ChatMessage.session_id.in_(db.query(allowed_sessions.c.id)),
        )
    )

    if search and search.strip():
        needle = f"%{search.strip()}%"
        UserMsg = aliased(ChatMessage)
        user_match = exists(
            select(1).where(
                UserMsg.session_id == ChatMessage.session_id,
                UserMsg.role == "user",
                UserMsg.created_at < ChatMessage.created_at,
                UserMsg.content.ilike(needle),
            )
        )
        query = query.filter(
            or_(
                ChatMessage.content.ilike(needle),
                ChatSession.title.ilike(needle),
                user_match,
            )
        )

    if rating in {"up", "down", "none"}:
        Feedback = aliased(ChatMessageFeedback)
        if rating == "none":
            query = query.filter(
                ~exists(
                    select(1).where(Feedback.message_id == ChatMessage.id)
                )
            )
        else:
            query = query.filter(
                exists(
                    select(1).where(
                        Feedback.message_id == ChatMessage.id,
                        Feedback.rating == rating,
                    )
                )
            )

    return query


def list_chat_eval_pairs(
    db: Session,
    *,
    user_id: str | None = None,
    tenant_id: str | None = None,
    is_admin: bool = False,
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
    rating: str | None = None,
    weak_only: bool = False,
) -> dict:
    """Return paginated user question + assistant answer pairs from stored chat turns."""
    query = _assistant_base_query(
        db,
        user_id=user_id,
        tenant_id=tenant_id,
        is_admin=is_admin,
        search=search,
        rating=rating,
    )

    if weak_only:
        Quality = aliased(ChatAnswerQuality)
        query = query.filter(
            exists(
                select(1).where(
                    Quality.message_id == ChatMessage.id,
                    or_(
                        Quality.quality_score < 60,
                        Quality.grounding_status == "abstain",
                        Quality.weak_phrases_detected.is_(True),
                        Quality.needs_review.is_(True),
                    ),
                )
            )
        )

    total = query.count()
    rows = (
        query.order_by(desc(ChatMessage.created_at))
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 200))
        .all()
    )

    assistant_ids = [assistant_msg.id for assistant_msg, _ in rows]
    feedback_by_message: dict[str, ChatMessageFeedback] = {}
    if assistant_ids:
        feedback_rows = (
            db.query(ChatMessageFeedback)
            .filter(ChatMessageFeedback.message_id.in_(assistant_ids))
            .order_by(desc(ChatMessageFeedback.created_at))
            .all()
        )
        for fb in feedback_rows:
            feedback_by_message.setdefault(fb.message_id, fb)

    quality_by_message: dict[str, ChatAnswerQuality] = {}
    if assistant_ids:
        try:
            quality_rows = (
                db.query(ChatAnswerQuality)
                .filter(ChatAnswerQuality.message_id.in_(assistant_ids))
                .all()
            )
            quality_by_message = {q.message_id: q for q in quality_rows}
        except Exception:
            quality_by_message = {}

    items: list[dict] = []
    for assistant_msg, session in rows:
        user_msg = _latest_user_message(
            db,
            session_id=assistant_msg.session_id,
            before=assistant_msg.created_at,
        )
        feedback = feedback_by_message.get(assistant_msg.id)
        quality = serialize_quality_row(quality_by_message.get(assistant_msg.id))

        item = {
            "session_id": session.id,
            "session_title": session.title or "New Chat",
            "user_message_id": user_msg.id if user_msg else None,
            "assistant_message_id": assistant_msg.id,
            "question": _truncate(user_msg.content if user_msg else None),
            "answer": _truncate(assistant_msg.content),
            "asked_at": user_msg.created_at.isoformat() if user_msg and user_msg.created_at else None,
            "answered_at": assistant_msg.created_at.isoformat() if assistant_msg.created_at else None,
            "rating": feedback.rating if feedback else None,
            "feedback_comment": feedback.correction_text if feedback else None,
        }
        if quality:
            item.update(quality)
        items.append(item)

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "search": search or "",
        "rating": rating or "",
        "weak_only": weak_only,
    }


def get_chat_eval_stats(
    db: Session,
    *,
    user_id: str | None = None,
    tenant_id: str | None = None,
    is_admin: bool = False,
) -> dict:
    """Aggregate counts for the evaluation dashboard header."""
    allowed_sessions = _allowed_session_ids_subquery(
        db,
        user_id=user_id,
        tenant_id=tenant_id,
        is_admin=is_admin,
    )

    assistant_count = (
        db.query(func.count(ChatMessage.id))
        .filter(
            ChatMessage.role == "assistant",
            ChatMessage.session_id.in_(db.query(allowed_sessions.c.id)),
        )
        .scalar()
        or 0
    )

    feedback_rows = (
        db.query(ChatMessageFeedback.rating, func.count(ChatMessageFeedback.id))
        .filter(ChatMessageFeedback.session_id.in_(db.query(allowed_sessions.c.id)))
        .group_by(ChatMessageFeedback.rating)
        .all()
    )
    rating_counts = {str(rating): int(count) for rating, count in feedback_rows}

    session_count = db.query(func.count(allowed_sessions.c.id)).scalar() or 0
    thumbs_up = int(rating_counts.get("up", 0))
    thumbs_down = int(rating_counts.get("down", 0))

    avg_quality = 0.0
    abstain_count = 0
    needs_review_count = 0
    try:
        quality_rows = (
            db.query(ChatAnswerQuality)
            .filter(ChatAnswerQuality.session_id.in_(db.query(allowed_sessions.c.id)))
            .all()
        )
        avg_quality = (
            round(sum(int(q.quality_score or 0) for q in quality_rows) / len(quality_rows), 1)
            if quality_rows
            else 0.0
        )
        abstain_count = sum(1 for q in quality_rows if q.grounding_status == "abstain")
        needs_review_count = sum(1 for q in quality_rows if q.needs_review)
    except Exception:
        # Table may not exist until migrations run on older deployments.
        pass

    return {
        "total_pairs": int(assistant_count),
        "total_sessions": int(session_count),
        "rated_pairs": thumbs_up + thumbs_down,
        "thumbs_up": thumbs_up,
        "thumbs_down": thumbs_down,
        "unrated_pairs": max(int(assistant_count) - thumbs_up - thumbs_down, 0),
        "avg_quality_score": avg_quality,
        "abstain_count": abstain_count,
        "needs_review_count": needs_review_count,
    }
