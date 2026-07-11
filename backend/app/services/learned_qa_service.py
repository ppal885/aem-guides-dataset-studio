"""Learned prompt-answer corpus persistence, indexing, and retrieval."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.chat_models import ChatMessage
from app.db.learned_prompt_models import LearnedPromptEntry
from app.db.session import SessionLocal
from app.services.embedding_service import embed_query, embed_texts_batched, is_embedding_available
from app.services.source_review_state_service import (
    load_source_state,
    record_source_failure,
    record_source_success,
    save_source_state,
)
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
LEARNED_QA_FALLBACK_MIN_SCORE = 0.18

_CHAT_HUMAN_PREFIX_PATTERNS = (
    re.compile(r"^quick question for our docs team:\s*", re.IGNORECASE),
    re.compile(r"^i'?m trying to explain this to a new writer\s*[—:-]\s*", re.IGNORECASE),
    re.compile(r"^can you walk me through this like a senior tech writer would\?\s*", re.IGNORECASE),
    re.compile(r"^we hit this in a customer map today\.\s*", re.IGNORECASE),
    re.compile(r"^need a senior answer here\s*[—:-]\s*", re.IGNORECASE),
)
LEARNED_QA_ANSWER_STYLE = "senior_technical_docs"
LEARNED_QA_NEAR_DUP_THRESHOLD = 0.72
LEARNED_QA_DEFAULT_K = 4
_LEARNED_QA_SYNC_LOCK = Lock()

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


def strip_humanized_chat_prefix(prompt: str) -> str:
    """Remove conversational wrappers so routing/retrieval match seed prompts."""
    text = str(prompt or "").strip()
    if not text:
        return ""
    for pattern in _CHAT_HUMAN_PREFIX_PATTERNS:
        updated = pattern.sub("", text).strip()
        if updated:
            text = updated
    return text


def _match_learned_qa_from_seed(query: str) -> dict[str, Any] | None:
    """Fast lexical match against the bundled seed corpus (no Chroma sync)."""
    text = strip_humanized_chat_prefix(query)
    if not text:
        return None
    try:
        items = _read_seed_items()
    except Exception:
        return None
    query_norm = normalize_prompt(text)
    dita_ot_explicit = bool(
        re.search(
            r"\b(dita-ot|dita open toolkit)\b.{0,80}\b("
            r"preprocess(?:ing)?|module|copy-to|conrefpush|profile step|command arguments?"
            r")\b|\b("
            r"preprocess(?:ing)?|copy-to preprocess|conrefpush|profile step"
            r")\b.{0,80}\b(dita-ot|dita open toolkit)\b",
            text,
            re.IGNORECASE,
        )
    )
    for item in items:
        prompt_norm = normalize_prompt(str(item.get("prompt") or ""))
        if prompt_norm and prompt_norm == query_norm:
            return {**item, "score": 1.0}
    best_score = 0.0
    best_item: dict[str, Any] | None = None
    for item in items:
        prompt = str(item.get("prompt") or "")
        prompt_norm = normalize_prompt(prompt)
        if not prompt_norm:
            continue
        overlap = _jaccard_similarity(prompt_norm, query_norm)
        if prompt_norm in query_norm or query_norm in prompt_norm:
            overlap = max(overlap, 0.95)
        if overlap > best_score:
            best_score = overlap
            best_item = item
    if not best_item:
        return None
    if best_score >= 0.95 or normalize_prompt(str(best_item.get("prompt") or "")) in query_norm:
        return {**best_item, "score": round(best_score, 4)}
    if dita_ot_explicit:
        return None
    if best_score >= 0.35:
        return {**best_item, "score": round(best_score, 4)}
    return None


def _format_learned_qa_answer(answer: str) -> str:
    text = str(answer or "").strip()
    if not text:
        return ""
    if not text.lstrip().startswith("#"):
        return f"## Short answer\n{text}"
    return text


def try_build_learned_qa_fallback_answer(query: str) -> str:
    """Return a trusted learned Q&A answer when retrieval confidence is high."""
    text = strip_humanized_chat_prefix(query)
    seed_hit = _match_learned_qa_from_seed(query)
    if seed_hit:
        return _format_learned_qa_answer(str(seed_hit.get("final_answer") or ""))

    if not text:
        return ""

    dita_ot_explicit = bool(
        re.search(
            r"\b(dita-ot|dita open toolkit)\b.{0,80}\b("
            r"preprocess(?:ing)?|module|copy-to|conrefpush|profile step|command arguments?"
            r")\b|\b("
            r"preprocess(?:ing)?|copy-to preprocess|conrefpush|profile step"
            r")\b.{0,80}\b(dita-ot|dita open toolkit)\b",
            text,
            re.IGNORECASE,
        )
    )
    if dita_ot_explicit:
        return ""

    if re.search(
        r"\b(dita command|dita\s+--|--input|--format|--output|--filter)\b",
        text,
        re.IGNORECASE,
    ):
        return ""

    rows = retrieve_learned_qa(text, k=2)
    if not rows:
        return ""
    top = rows[0]
    answer = str(top.get("final_answer") or "").strip()
    if len(answer) < 80:
        return ""
    score = float(top.get("score") or 0.0)
    top_prompt = normalize_prompt(str(top.get("prompt") or ""))
    query_norm = normalize_prompt(text)
    prompt_overlap = _jaccard_similarity(top_prompt, query_norm) if top_prompt and query_norm else 0.0
    if score >= 0.45 or prompt_overlap >= 0.28:
        return _format_learned_qa_answer(answer)
    if score >= LEARNED_QA_FALLBACK_MIN_SCORE and (
        top_prompt in query_norm or query_norm in top_prompt or prompt_overlap >= 0.18
    ):
        return _format_learned_qa_answer(answer)
    return ""


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


def _read_seed_items() -> list[dict[str, Any]]:
    if not LEARNED_QA_SEED_PATH.is_file():
        raise FileNotFoundError(f"Missing learned QA seed file: {LEARNED_QA_SEED_PATH}")
    raw = json.loads(LEARNED_QA_SEED_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("learned_qa_seed.json must contain a list")
    return [item for item in raw if isinstance(item, dict)]


def _seed_file_metadata() -> dict[str, Any]:
    payload = LEARNED_QA_SEED_PATH.read_bytes()
    item_count = len(_read_seed_items())
    return {
        "seed_file": str(LEARNED_QA_SEED_PATH),
        "seed_hash": hashlib.sha256(payload).hexdigest(),
        "seed_item_count": item_count,
        "seed_file_mtime": datetime.fromtimestamp(
            LEARNED_QA_SEED_PATH.stat().st_mtime,
            tz=timezone.utc,
        ).isoformat(),
    }


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
    raw = _read_seed_items()
    created = 0
    updated = 0
    for item in raw:
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


def sync_learned_qa_corpus(
    session: Session | None = None,
    *,
    force_seed: bool = False,
    force_reindex: bool = False,
    reason: str = "auto",
) -> dict[str, Any]:
    created_session = session is None
    db = session or SessionLocal()
    try:
        with _LEARNED_QA_SYNC_LOCK:
            metadata = _seed_file_metadata()
            state = load_source_state(CHROMA_COLLECTION_LEARNED_QA)
            last_stats = dict(state.last_stats or {})

            approved_seed_count = (
                db.query(LearnedPromptEntry)
                .filter(
                    LearnedPromptEntry.status == "approved",
                    LearnedPromptEntry.source_type == "seed",
                )
                .count()
            )
            approved_total_count = (
                db.query(LearnedPromptEntry)
                .filter(LearnedPromptEntry.status == "approved")
                .count()
            )
            chroma_ok = is_chroma_available()
            auto_index_ready = chroma_ok and is_embedding_available()
            indexed_count = get_collection_count(CHROMA_COLLECTION_LEARNED_QA) if chroma_ok else 0

            seed_changed = (
                force_seed
                or last_stats.get("seed_hash") != metadata["seed_hash"]
                or int(last_stats.get("seed_item_count") or -1) != int(metadata["seed_item_count"])
            )
            seed_missing_in_db = int(metadata["seed_item_count"] or 0) > 0 and approved_seed_count == 0
            index_out_of_sync = chroma_ok and approved_total_count != indexed_count

            needs_seed = bool(seed_changed or seed_missing_in_db)
            needs_reindex = bool(
                force_reindex
                or needs_seed
                or (auto_index_ready and index_out_of_sync)
                or (auto_index_ready and approved_total_count > 0 and indexed_count == 0)
            )

            seed_stats: dict[str, Any] = {
                "created": 0,
                "updated": 0,
                "total": 0,
                "skipped": True,
                "reason": "up_to_date",
            }
            index_stats: dict[str, Any] = {
                "collection": CHROMA_COLLECTION_LEARNED_QA,
                "indexed": indexed_count,
                "errors": [],
                "skipped": True,
                "reason": "up_to_date",
            }

            if needs_seed:
                seed_stats = seed_learned_qa(db)
                approved_total_count = (
                    db.query(LearnedPromptEntry)
                    .filter(LearnedPromptEntry.status == "approved")
                    .count()
                )
                needs_reindex = True

            if needs_reindex:
                index_stats = index_approved_learned_qa(
                    db,
                    force_reindex=bool(force_reindex or needs_seed or index_out_of_sync),
                )
                indexed_count = int(index_stats.get("indexed") or 0)

            sync_stats = {
                **last_stats,
                **metadata,
                "approved_count": int(approved_total_count or 0),
                "indexed": int(indexed_count or 0),
                "performed_seed": bool(needs_seed),
                "performed_reindex": bool(needs_reindex),
                "sync_reason": reason,
            }

            if index_stats.get("errors"):
                record_source_failure(
                    source_id=CHROMA_COLLECTION_LEARNED_QA,
                    operation="auto_sync",
                    error="; ".join(str(err) for err in index_stats.get("errors") or []),
                    failed_items=list(index_stats.get("errors") or []),
                    stats=sync_stats,
                )
            elif needs_seed or needs_reindex:
                record_source_success(
                    source_id=CHROMA_COLLECTION_LEARNED_QA,
                    operation="auto_sync",
                    stats=sync_stats,
                )
            else:
                state.last_stats = sync_stats
                save_source_state(state)

            return {
                "seed": seed_stats,
                "index": index_stats,
                "performed_seed": bool(needs_seed),
                "performed_reindex": bool(needs_reindex),
                "seed_changed": bool(seed_changed),
                "seed_missing_in_db": bool(seed_missing_in_db),
                "approved_count": int(approved_total_count or 0),
                "indexed_count": int(indexed_count or 0),
                "reason": reason,
                "seed_file": metadata["seed_file"],
                "seed_item_count": int(metadata["seed_item_count"] or 0),
            }
    except Exception as exc:
        record_source_failure(
            source_id=CHROMA_COLLECTION_LEARNED_QA,
            operation="auto_sync",
            error=str(exc),
            failed_items=[str(exc)],
        )
        raise
    finally:
        if created_session:
            db.close()


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
    try:
        sync_learned_qa_corpus(reason="chat_retrieval")
    except Exception:
        pass

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


def capture_rejected_learned_from_chat_feedback(
    session: Session,
    *,
    session_id: str,
    message_id: str,
    rating: str,
) -> dict[str, Any] | None:
    """Record a rejected learned-QA stub on thumbs-down for dedupe (not indexed)."""
    if rating != "down":
        return None
    assistant = (
        session.query(ChatMessage)
        .filter(ChatMessage.id == message_id, ChatMessage.session_id == session_id, ChatMessage.role == "assistant")
        .first()
    )
    if assistant is None:
        return None
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
    if not prompt:
        return None
    entry, created, dedupe_kind = upsert_learned_prompt_entry(
        session,
        prompt=prompt,
        final_answer=final_answer or "(rejected answer)",
        source_type="chat_feedback_rejected",
        status="rejected",
        answer_style=LEARNED_QA_ANSWER_STYLE,
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
