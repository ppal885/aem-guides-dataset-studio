"""Learned prompt-answer corpus persistence, indexing, and retrieval."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.chat_models import ChatMessage
from app.db.learned_prompt_models import LearnedPromptEntry
from app.db.session import SessionLocal
from app.services.embedding_service import embed_query, embed_texts_batched, is_embedding_available
from app.services.source_review_state_service import load_source_state
from app.services.vector_store_service import (
    CHROMA_COLLECTION_LEARNED_QA,
    add_documents,
    delete_collection,
    get_collection_count,
    is_chroma_available,
    query_collection,
)

LEARNED_QA_SEED_PATH = Path(__file__).resolve().parent.parent / "storage" / "learned_qa_seed.json"
LEARNED_QA_EXPORT_FILENAME = "learned_qa_pairs.json"
LEARNED_QA_ANSWER_STYLE = "senior_technical_docs"
LEARNED_QA_NEAR_DUP_THRESHOLD = 0.72
LEARNED_QA_DEFAULT_K = 4

_KNOWN_TAGS: tuple[str, ...] = (
    "morerows",
    "table",
    "simpletable",
    "keyscope",
    "keyref",
    "conref",
    "processing-role",
    "resource-only",
    "chunk",
    "mapref",
    "subject scheme",
    "subjectscheme",
    "ditavalref",
    "draft-comment",
    "required-cleanup",
    "ditaval",
    "draft filtering",
    "native pdf",
    "dita-ot",
    "publishing",
    "topicgroup",
    "topichead",
)


def normalize_prompt(prompt: str) -> str:
    text = re.sub(r"\s+", " ", str(prompt or "").strip().lower())
    text = re.sub(r"[“”‘’`\"]", "", text)
    return text


def prompt_hash(normalized_prompt: str) -> str:
    return hashlib.sha256(str(normalized_prompt or "").encode("utf-8")).hexdigest()


def _json_loads_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    out: list[str] = []
    for item in parsed:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _json_dumps_tags(tags: list[str] | None) -> str:
    return json.dumps([str(tag).strip() for tag in (tags or []) if str(tag).strip()], ensure_ascii=False)


def _tokenize(text: str) -> set[str]:
    cleaned = re.sub(r"[^\w\s@<>:-]", " ", str(text or "").lower())
    return {token for token in cleaned.split() if len(token) >= 2}


def _jaccard_similarity(left: str, right: str) -> float:
    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    union = left_tokens | right_tokens
    if not union:
        return 0.0
    return len(left_tokens & right_tokens) / len(union)


def _coerce_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def infer_tags(prompt: str, answer: str = "") -> list[str]:
    haystack = f"{prompt}\n{answer}".lower()
    tags: list[str] = []
    for tag in _KNOWN_TAGS:
        if tag in haystack and tag not in tags:
            tags.append(tag)
    element_tags = re.findall(r"<([a-zA-Z][a-zA-Z0-9_-]*)", answer or "")
    for tag in element_tags[:6]:
        lowered = tag.lower()
        if lowered not in tags:
            tags.append(lowered)
    attr_tags = re.findall(r"@([a-zA-Z_:][a-zA-Z0-9_.:-]*)", f"{prompt} {answer}")
    for tag in attr_tags[:6]:
        lowered = tag.lower()
        if lowered not in tags:
            tags.append(lowered)
    return tags[:10]


def infer_topic(prompt: str, tags: list[str] | None = None) -> str:
    lowered = str(prompt or "").lower()
    joined = " ".join(tags or [])
    corpus = f"{lowered} {joined}"
    if any(marker in corpus for marker in ("native pdf", "dita-ot", "publishing", "ditaval", "draft filtering")):
        return "publishing"
    if any(marker in corpus for marker in ("table", "simpletable", "morerows")):
        return "tables"
    if any(marker in corpus for marker in ("keyscope", "keyref", "conref", "mapref", "processing-role")):
        return "reuse_and_maps"
    if "subject scheme" in corpus or "subjectscheme" in corpus:
        return "controlled_values"
    return "dita_general"


def _document_text(entry: LearnedPromptEntry) -> str:
    tags = ", ".join(_json_loads_tags(getattr(entry, "tags_json", None)))
    return (
        f"Prompt: {entry.prompt}\n\n"
        f"Answer:\n{entry.final_answer}\n\n"
        f"Topic: {entry.topic or ''}\n"
        f"Tags: {tags}\n"
        f"Answer style: {entry.answer_style or LEARNED_QA_ANSWER_STYLE}"
    ).strip()


def _serialize_entry(entry: LearnedPromptEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "prompt": entry.prompt,
        "normalized_prompt": entry.normalized_prompt,
        "prompt_hash": entry.prompt_hash,
        "final_answer": entry.final_answer,
        "tags": _json_loads_tags(entry.tags_json),
        "topic": entry.topic,
        "source_type": entry.source_type,
        "answer_style": entry.answer_style,
        "status": entry.status,
        "accepted_at": entry.accepted_at.isoformat() if entry.accepted_at else None,
        "approved_at": entry.approved_at.isoformat() if entry.approved_at else None,
        "session_id": entry.session_id,
        "message_id": entry.message_id,
        "support_count": int(entry.support_count or 0),
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


def get_learned_qa_summary(session: Session) -> dict[str, Any]:
    total = session.query(LearnedPromptEntry).count()
    approved = session.query(LearnedPromptEntry).filter(LearnedPromptEntry.status == "approved").count()
    pending = session.query(LearnedPromptEntry).filter(LearnedPromptEntry.status == "pending_review").count()
    rejected = session.query(LearnedPromptEntry).filter(LearnedPromptEntry.status == "rejected").count()
    state = load_source_state(CHROMA_COLLECTION_LEARNED_QA)
    return {
        "total_count": int(total),
        "approved_count": int(approved),
        "pending_review_count": int(pending),
        "rejected_count": int(rejected),
        "indexed_count": int(get_collection_count(CHROMA_COLLECTION_LEARNED_QA)) if is_chroma_available() else 0,
        "last_indexed_time": state.last_successful_run,
        "last_error": state.last_error,
        "failed_item_count": int(state.failed_item_count or 0),
        "failed_items": list(state.failed_items or []),
    }


def list_learned_prompt_entries(
    session: Session,
    *,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    query = session.query(LearnedPromptEntry)
    if status:
        query = query.filter(LearnedPromptEntry.status == status)
    rows = (
        query
        .order_by(LearnedPromptEntry.updated_at.desc(), LearnedPromptEntry.created_at.desc())
        .offset(max(0, int(offset)))
        .limit(max(1, min(int(limit), 500)))
        .all()
    )
    return [_serialize_entry(row) for row in rows]


def _status_priority(status: str) -> int:
    return {"rejected": 0, "pending_review": 1, "approved": 2}.get(str(status or "").strip(), 1)


def _find_near_duplicate(
    session: Session,
    normalized: str,
    *,
    exclude_id: str | None = None,
) -> LearnedPromptEntry | None:
    rows = session.query(LearnedPromptEntry).filter(LearnedPromptEntry.status.in_(("approved", "pending_review"))).all()
    best: LearnedPromptEntry | None = None
    best_score = 0.0
    for row in rows:
        if exclude_id and row.id == exclude_id:
            continue
        score = _jaccard_similarity(normalized, row.normalized_prompt or "")
        if score >= LEARNED_QA_NEAR_DUP_THRESHOLD and score > best_score:
            best = row
            best_score = score
    return best


def upsert_learned_prompt_entry(
    session: Session,
    *,
    prompt: str,
    final_answer: str,
    source_type: str,
    status: str,
    answer_style: str = LEARNED_QA_ANSWER_STYLE,
    accepted_at: datetime | None = None,
    approved_at: datetime | None = None,
    session_id: str | None = None,
    message_id: str | None = None,
    tags: list[str] | None = None,
    topic: str | None = None,
) -> tuple[LearnedPromptEntry, bool, str]:
    accepted_at = _coerce_naive_utc(accepted_at)
    approved_at = _coerce_naive_utc(approved_at)
    normalized = normalize_prompt(prompt)
    phash = prompt_hash(normalized)
    resolved_tags = list(tags or infer_tags(prompt, final_answer))
    resolved_topic = topic or infer_topic(prompt, resolved_tags)
    entry = session.query(LearnedPromptEntry).filter(LearnedPromptEntry.prompt_hash == phash).first()
    dedupe_kind = "exact" if entry else "new"
    if entry is None:
        entry = _find_near_duplicate(session, normalized)
        if entry is not None:
            dedupe_kind = "near"

    created = False
    if entry is None:
        entry = LearnedPromptEntry(
            id=str(uuid4()),
            prompt=prompt.strip(),
            normalized_prompt=normalized,
            prompt_hash=phash,
            final_answer=final_answer.strip(),
            tags_json=_json_dumps_tags(resolved_tags),
            topic=resolved_topic,
            source_type=source_type,
            answer_style=answer_style,
            status=status,
            accepted_at=accepted_at,
            approved_at=approved_at,
            session_id=session_id,
            message_id=message_id,
            support_count=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(entry)
        created = True
        return entry, created, dedupe_kind

    previous_status = str(entry.status or "").strip()
    previous_priority = _status_priority(previous_status)
    next_priority = _status_priority(status)
    accepted_is_newer = bool(
        accepted_at
        and (
            entry.accepted_at is None
            or accepted_at >= entry.accepted_at
        )
    )
    should_replace_answer = (
        next_priority > previous_priority
        or (status == previous_status and accepted_is_newer)
    )

    entry.prompt = prompt.strip() or entry.prompt
    entry.normalized_prompt = normalized
    entry.prompt_hash = phash
    if should_replace_answer and final_answer.strip():
        entry.final_answer = final_answer.strip()
        entry.source_type = source_type or entry.source_type
        entry.answer_style = answer_style or entry.answer_style
        entry.session_id = session_id or entry.session_id
        entry.message_id = message_id or entry.message_id
    entry.tags_json = _json_dumps_tags(resolved_tags)
    entry.topic = resolved_topic
    entry.support_count = int(entry.support_count or 0) + 1
    if accepted_at and (entry.accepted_at is None or accepted_at > entry.accepted_at):
        entry.accepted_at = accepted_at
    if approved_at and (entry.approved_at is None or approved_at > entry.approved_at):
        entry.approved_at = approved_at
    if next_priority > previous_priority:
        entry.status = status
    entry.updated_at = datetime.utcnow()
    return entry, created, dedupe_kind


def seed_learned_qa(session: Session) -> dict[str, Any]:
    if not LEARNED_QA_SEED_PATH.is_file():
        raise FileNotFoundError(f"Missing learned QA seed file: {LEARNED_QA_SEED_PATH}")
    raw = json.loads(LEARNED_QA_SEED_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("learned_qa_seed.json must contain a list")
    created = 0
    updated = 0
    for item in raw:
        if not isinstance(item, dict):
            continue
        prompt = str(item.get("prompt") or "").strip()
        final_answer = str(item.get("final_answer") or "").strip()
        if not prompt or not final_answer:
            continue
        entry, was_created, _dedupe_kind = upsert_learned_prompt_entry(
            session,
            prompt=prompt,
            final_answer=final_answer,
            tags=[str(tag).strip() for tag in item.get("tags") or [] if str(tag).strip()],
            topic=str(item.get("topic") or "").strip() or None,
            source_type="seed",
            status="approved",
            answer_style=str(item.get("answer_style") or LEARNED_QA_ANSWER_STYLE),
            accepted_at=datetime.now(timezone.utc),
            approved_at=datetime.now(timezone.utc),
        )
        if was_created:
            created += 1
        else:
            entry.status = "approved"
            if entry.approved_at is None:
                entry.approved_at = datetime.now(timezone.utc)
            updated += 1
    session.commit()
    return {"created": created, "updated": updated, "total": created + updated}


def index_approved_learned_qa(session: Session, *, force_reindex: bool = False) -> dict[str, Any]:
    rows = (
        session.query(LearnedPromptEntry)
        .filter(LearnedPromptEntry.status == "approved")
        .order_by(LearnedPromptEntry.updated_at.desc())
        .all()
    )
    if force_reindex:
        delete_collection(CHROMA_COLLECTION_LEARNED_QA)
    if not rows:
        return {
            "collection": CHROMA_COLLECTION_LEARNED_QA,
            "indexed": 0,
            "errors": [],
        }
    docs = [_document_text(row) for row in rows]
    embeddings = embed_texts_batched(docs, batch_size=32)
    if embeddings is None:
        return {
            "collection": CHROMA_COLLECTION_LEARNED_QA,
            "indexed": 0,
            "errors": ["Embedding batch failed."],
        }
    ids = [row.id for row in rows]
    metas = [
        {
            "entry_id": row.id,
            "topic": str(row.topic or ""),
            "source_type": str(row.source_type or ""),
            "status": str(row.status or ""),
            "answer_style": str(row.answer_style or ""),
            "support_count": int(row.support_count or 0),
            "prompt_hash": row.prompt_hash,
        }
        for row in rows
    ]
    emb_list = [embeddings[index].tolist() for index in range(len(ids))]
    ok = add_documents(CHROMA_COLLECTION_LEARNED_QA, ids, docs, metas, emb_list)
    return {
        "collection": CHROMA_COLLECTION_LEARNED_QA,
        "indexed": len(ids) if ok else 0,
        "errors": [] if ok else ["Chroma upsert failed."],
    }


def export_approved_learned_qa_pairs(
    session: Session,
    *,
    output_path: str | None = None,
) -> dict[str, Any]:
    rows = (
        session.query(LearnedPromptEntry)
        .filter(LearnedPromptEntry.status == "approved")
        .order_by(LearnedPromptEntry.updated_at.desc())
        .all()
    )
    path = Path(output_path) if output_path else (Path(__file__).resolve().parent.parent.parent / "storage" / LEARNED_QA_EXPORT_FILENAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "prompt": row.prompt,
            "answer": row.final_answer,
            "tags": _json_loads_tags(row.tags_json),
            "topic": row.topic,
            "answer_style": row.answer_style,
            "source_type": row.source_type,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        }
        for row in rows
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(path), "count": len(payload)}


def retrieve_learned_qa(query: str, k: int = LEARNED_QA_DEFAULT_K) -> list[dict[str, Any]]:
    text = str(query or "").strip()
    if not text:
        return []
    result_limit = max(1, min(int(k), 10))

    if is_chroma_available() and is_embedding_available() and get_collection_count(CHROMA_COLLECTION_LEARNED_QA) > 0:
        emb = embed_query(text[:4000])
        if emb is not None:
            vec = emb.tolist() if hasattr(emb, "tolist") else list(emb)
            rows = query_collection(CHROMA_COLLECTION_LEARNED_QA, vec, k=result_limit)
            if rows:
                ordered_ids = [str(row.get("id") or "").strip() for row in rows if str(row.get("id") or "").strip()]
                db = SessionLocal()
                try:
                    entries = {
                        entry.id: entry
                        for entry in db.query(LearnedPromptEntry)
                        .filter(LearnedPromptEntry.id.in_(ordered_ids), LearnedPromptEntry.status == "approved")
                        .all()
                    }
                    out: list[dict[str, Any]] = []
                    for row in rows:
                        entry = entries.get(str(row.get("id") or ""))
                        if not entry:
                            continue
                        distance = float(row.get("distance") or 0.0)
                        out.append(
                            {
                                **_serialize_entry(entry),
                                "score": max(0.0, round(1.0 - distance, 4)),
                                "distance": distance,
                            }
                        )
                    if out:
                        return out[:result_limit]
                finally:
                    db.close()

    db = SessionLocal()
    try:
        rows = db.query(LearnedPromptEntry).filter(LearnedPromptEntry.status == "approved").all()
        scored: list[tuple[float, LearnedPromptEntry]] = []
        norm = normalize_prompt(text)
        for row in rows:
            score = _jaccard_similarity(norm, row.normalized_prompt or "")
            if score <= 0:
                haystack = f"{row.prompt}\n{row.final_answer}\n{' '.join(_json_loads_tags(row.tags_json))}"
                score = _jaccard_similarity(norm, normalize_prompt(haystack))
            if score > 0:
                scored.append((score, row))
        scored.sort(key=lambda item: (-item[0], -(item[1].support_count or 0)))
        return [
            {
                **_serialize_entry(row),
                "score": round(score, 4),
                "distance": round(1.0 - score, 4),
            }
            for score, row in scored[:result_limit]
        ]
    finally:
        db.close()


def format_learned_qa_for_prompt(query: str, k: int = 3) -> str:
    rows = retrieve_learned_qa(query, k=k)
    if not rows:
        return ""
    parts: list[str] = []
    for index, row in enumerate(rows, 1):
        tags = ", ".join(row.get("tags") or [])
        parts.append(
            f"[{index}] Prompt: {row.get('prompt')}\n"
            f"Answer:\n{str(row.get('final_answer') or '')[:1800]}\n"
            f"Topic: {row.get('topic') or ''}\n"
            f"Tags: {tags}\n"
            f"Score: {row.get('score')}"
        )
    return "LEARNED PROMPT CORPUS:\n" + "\n\n".join(parts)


def capture_learned_candidate_from_chat_feedback(
    session: Session,
    *,
    session_id: str,
    message_id: str,
    rating: str,
) -> dict[str, Any] | None:
    if rating != "up":
        return None
    assistant = (
        session.query(ChatMessage)
        .filter(ChatMessage.id == message_id, ChatMessage.session_id == session_id, ChatMessage.role == "assistant")
        .first()
    )
    if assistant is None:
        return None
    next_user = (
        session.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session_id,
            ChatMessage.role == "user",
            ChatMessage.created_at > assistant.created_at,
        )
        .order_by(ChatMessage.created_at.asc())
        .first()
    )
    lineage_query = (
        session.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session_id,
            ChatMessage.role == "assistant",
            ChatMessage.created_at >= assistant.created_at,
        )
    )
    if next_user is not None:
        lineage_query = lineage_query.filter(ChatMessage.created_at < next_user.created_at)
    latest_prompt_assistant = lineage_query.order_by(ChatMessage.created_at.desc()).first()
    if latest_prompt_assistant is None or latest_prompt_assistant.id != assistant.id:
        return {
            "skipped": True,
            "reason": "superseded_assistant_draft",
        }
    user_message = (
        session.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session_id,
            ChatMessage.role == "user",
            ChatMessage.created_at <= assistant.created_at,
        )
        .order_by(ChatMessage.created_at.desc())
        .first()
    )
    if user_message is None:
        return None
    prompt = str(user_message.content or "").strip()
    final_answer = str(assistant.content or "").strip()
    if not prompt or not final_answer:
        return None
    accepted_at = datetime.now(timezone.utc)
    entry, created, dedupe_kind = upsert_learned_prompt_entry(
        session,
        prompt=prompt,
        final_answer=final_answer,
        source_type="chat_feedback",
        status="pending_review",
        answer_style=LEARNED_QA_ANSWER_STYLE,
        accepted_at=accepted_at,
        session_id=session_id,
        message_id=message_id,
    )
    session.commit()
    return {
        "entry": _serialize_entry(entry),
        "created": created,
        "dedupe_kind": dedupe_kind,
    }


def approve_learned_prompt_entry(session: Session, entry_id: str) -> dict[str, Any]:
    entry = session.query(LearnedPromptEntry).filter(LearnedPromptEntry.id == entry_id).first()
    if entry is None:
        raise LookupError("Learned prompt entry not found")
    entry.status = "approved"
    entry.approved_at = datetime.now(timezone.utc)
    entry.updated_at = datetime.utcnow()
    session.commit()
    return _serialize_entry(entry)


def reject_learned_prompt_entry(session: Session, entry_id: str) -> dict[str, Any]:
    entry = session.query(LearnedPromptEntry).filter(LearnedPromptEntry.id == entry_id).first()
    if entry is None:
        raise LookupError("Learned prompt entry not found")
    entry.status = "rejected"
    entry.updated_at = datetime.utcnow()
    session.commit()
    return _serialize_entry(entry)
