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

from sqlalchemy import func
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
DEFAULT_LEARNED_QA_SEED_PATH = LEARNED_QA_SEED_PATH
LEARNED_QA_EXPORT_FILENAME = "learned_qa_pairs.json"
LEARNED_QA_ANSWER_STYLE = "senior_technical_docs"
LEARNED_QA_NEAR_DUP_THRESHOLD = 0.72
LEARNED_QA_DEFAULT_K = 4
LEARNED_QA_FALLBACK_EMBED_DIM = 384
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
    "topicref",
    "keydef",
    "xref",
    "image",
    "fig",
    "note",
    "steps",
    "step",
    "cmd",
    "ul",
    "ol",
    "li",
    "dl",
    "dlentry",
    "dt",
    "dd",
    "choicetable",
    "properties",
    "reltable",
    "glossentry",
    "indexterm",
    "prolog",
    "metadata",
    "section",
    "shortdesc",
)


def prompt_hash(normalized_prompt: str) -> str:
    return hashlib.sha256(str(normalized_prompt or "").encode("utf-8")).hexdigest()


def normalize_prompt(prompt: str) -> str:
    text = str(prompt or "").strip().lower()
    replacements = {
        "â€œ": '"',
        "â€": '"',
        "â€˜": "'",
        "â€™": "'",
        "â€”": "-",
        "â€“": "-",
        "â€¦": "...",
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u2013": "-",
        "\u2014": "-",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[`\"]", "", text)
    return text


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


def _extract_attribute_query_terms(text: str) -> set[str]:
    normalized = normalize_prompt(text).replace("_", "-")
    explicit = {match.group(1).lower() for match in re.finditer(r"@([a-z][\w:-]*)", normalized)}
    candidates = {
        "morerows", "namest", "nameend", "conref", "conkeyref", "conrefend", "keyref", "keys",
        "keyscope", "processing-role", "copy-to", "collection-type", "locktitle", "lockmeta",
        "navtitle", "searchtitle", "linktext", "cascade", "chunk", "href", "scope", "format",
        "toc", "linking", "audience", "platform", "product", "props", "otherprops", "rev",
        "translate", "xml:lang", "dir", "outputclass", "class", "id", "xml:id", "domains",
        "deliverytarget", "print", "colname", "colnum", "colwidth", "rowsep", "colsep",
        "align", "valign", "char", "charoff", "frame", "pgwide", "orient", "rowheader",
        "headers", "alt", "placement", "height", "width", "scale", "scalefit", "longdescref",
        "keyscopeprefix", "keyscopesuffix", "resourceprefix", "resourcesuffix", "filter",
        "conaction", "ditavalref",
    }
    found = explicit | {candidate for candidate in candidates if re.search(rf"\b{re.escape(candidate)}\b", normalized)}
    if "resource-only" in normalized:
        found.add("processing-role")
    if "branch filtering" in normalized or "branch-filtering" in normalized:
        found |= {"ditavalref", "filter", "keyscopeprefix", "keyscopesuffix", "resourceprefix", "resourcesuffix"}
    if "key scope" in normalized or "key scopes" in normalized:
        found.add("keyscope")
    if "table header" in normalized or "table headers" in normalized or ("accessible" in normalized and "table" in normalized):
        found |= {"headers", "rowheader"}
    if "native pdf" in normalized and "styling" in normalized:
        found.add("outputclass")
    if not found and "attribute" not in normalized and not any(
        domain in normalized
        for domain in ("dita", "cals", "table", "pdf", "webhelp", "oxygen", "aem guides", "branch filtering", "native pdf")
    ):
        return set()
    if not found and "table" in normalized and "attribute" in normalized:
        found |= {"headers", "rowheader", "valign", "align", "colwidth", "rowsep", "colsep", "morerows", "namest", "nameend"}
    if not found and "image" in normalized and "attribute" in normalized:
        found |= {"scale", "scalefit", "width", "height", "placement", "alt", "longdescref"}
    return found


def _retrieve_attribute_qa_candidates(normalized_query: str, result_limit: int) -> list[dict[str, Any]]:
    attrs = _extract_attribute_query_terms(normalized_query)
    if not attrs:
        return []
    db = SessionLocal()
    try:
        rows = (
            db.query(LearnedPromptEntry)
            .filter(
                LearnedPromptEntry.status == "approved",
                LearnedPromptEntry.source_type == "dita_attribute_questions",
            )
            .all()
        )
        scored: list[tuple[float, LearnedPromptEntry]] = []
        for row in rows:
            tags = set(_json_loads_tags(row.tags_json))
            row_text = normalize_prompt(f"{row.prompt}\n{row.final_answer}\n{' '.join(tags)}")
            row_attrs = _extract_attribute_query_terms(row.prompt) | {tag.lower() for tag in tags}
            overlap = attrs & row_attrs
            if not overlap:
                continue
            score = _jaccard_similarity(normalized_query, normalize_prompt(row.prompt))
            score = max(score, _jaccard_similarity(normalized_query, row_text) * 0.7)
            score += 0.75 + min(0.2, 0.05 * len(overlap))
            direct_overlap = {
                attr
                for attr in overlap
                if re.search(rf"\b{re.escape(attr)}\b", normalized_query)
            }
            score += min(0.35, 0.18 * len(direct_overlap))
            if "resource-only" in normalized_query and "processing-role" in overlap:
                score += 0.45
            if "simpletable" in normalized_query and "morerows" in overlap:
                score += 0.1
            if "accessibility" in normalized_query and overlap & {"headers", "rowheader", "alt", "longdescref"}:
                score += 0.18
            if "pdf" in normalized_query and overlap & {"headers", "rowheader", "valign", "scale", "scalefit", "copy-to"}:
                score += 0.08
            scored.append((score, row))
        scored.sort(key=lambda item: (-item[0], item[1].prompt))
        return [
            {
                **_serialize_entry(row),
                "score": round(min(score, 0.99), 4),
                "distance": round(max(0.0, 1.0 - min(score, 0.99)), 4),
            }
            for score, row in scored[:result_limit]
        ]
    finally:
        db.close()


def _extract_dita_ot_query_terms(text: str) -> set[str]:
    normalized = normalize_prompt(text).replace("_", "-")
    terms = {
        "dita-ot", "dita ot", "jenkins", "ci", "pipeline", "docker", "pdf", "pdf2", "fop",
        "xsl-fo", "html5", "webhelp", "ditaval", "branch filtering", "preprocess", "preprocessing",
        "keyref", "conref", "conkeyref", "chunk", "copy-to", "resource-only", "plugin", "plug-in",
        "extension point", "integrator", "catalog", "grammar", "validation", "log", "warning",
        "debug", "temp", "temporary", "xtrf", "xtrc", "css",
        "local", "command-line", "memory", "performance", "upgrade", "migration", "args.filter",
        "args.draft", "clean.temp", "dita.temp.dir", "generate-debug-attributes", "processing-mode",
        "args.grammar.cache", "args.resources", "outer.control", "onlytopic.in.map", "link-crawl",
        "force-unique", "root-chunk-override", "args.css", "args.copycss", "args.csspath",
        "args.rellinks", "pdf.formatter", "customization.dir", "dita install", "plugin.xml",
        "store-type", "parallel", "conserve-memory", "validate", "generate.copy.outer",
        "resourceprefix", "resourcesuffix", "keyscopeprefix", "keyscopesuffix", "generated file",
        "generated file names", "generated filenames", "filtered branch", "filtered branches",
        "draft-comment", "required-cleanup", "release output", "row spans", "row span", "cals",
        "table rows", "table", "morerows", "conrefend", "range reuse", "xref rewriting",
        "related links", "relationship table", "svg", "image", "windows", "linux", "spaces",
        "non-ascii", "case-sensitive", "case sensitive", "path issues", "filenames",
    }
    found = {term for term in terms if term in normalized}
    if "build" in normalized and ("local" in normalized or "jenkins" in normalized or "ci" in normalized):
        found |= {"ci", "jenkins", "pipeline"}
    if "draft-comment" in normalized or "required-cleanup" in normalized:
        found |= {"args.draft", "draft-comment", "required-cleanup"}
    if "release output" in normalized and "draft" in normalized:
        found |= {"args.draft", "draft-comment", "required-cleanup"}
    if "branch" in normalized and ("filter" in normalized or "resource" in normalized or "keyscope" in normalized):
        found |= {"branch filtering", "ditaval", "resourceprefix", "resourcesuffix", "keyscopeprefix"}
    if "filtered branch" in normalized or "filtered branches" in normalized:
        found |= {"branch filtering", "ditaval"}
    if "row span" in normalized or "row spans" in normalized:
        found |= {"cals", "morerows", "table"}
    if "copy-to" in normalized and "chunk" in normalized:
        found |= {"chunk", "copy-to", "xref rewriting"}
    if ("windows" in normalized and "linux" in normalized) or "case-sensitive" in normalized or "case sensitive" in normalized:
        found |= {"windows", "linux", "case-sensitive", "path"}
    if "dita-ot" in normalized or "dita ot" in normalized:
        found.add("dita-ot")
    return found


def _retrieve_dita_ot_complex_candidates(normalized_query: str, result_limit: int) -> list[dict[str, Any]]:
    terms = _extract_dita_ot_query_terms(normalized_query)
    if not terms:
        return []
    db = SessionLocal()
    try:
        rows = (
            db.query(LearnedPromptEntry)
            .filter(
                LearnedPromptEntry.status == "approved",
                LearnedPromptEntry.source_type.in_(("dita_ot_docs_complex", "dita_ot_docs_researched")),
            )
            .all()
        )
        scored: list[tuple[float, LearnedPromptEntry]] = []
        for row in rows:
            tags = {tag.lower() for tag in _json_loads_tags(row.tags_json)}
            row_text = normalize_prompt(f"{row.prompt}\n{row.final_answer}\n{' '.join(tags)}")
            row_terms = tags | _extract_dita_ot_query_terms(row.prompt)
            overlap = terms & row_terms
            if not overlap:
                continue
            score = max(
                _jaccard_similarity(normalized_query, normalize_prompt(row.prompt)),
                _jaccard_similarity(normalized_query, row_text) * 0.75,
            )
            score += 0.72 + min(0.25, 0.05 * len(overlap))
            if {"jenkins", "ci", "pipeline"} & terms and {"jenkins", "ci", "pipeline"} & row_terms:
                score += 0.35
            if "dita-ot" in terms or "dita ot" in terms:
                score += 0.08
            scored.append((score, row))
        scored.sort(key=lambda item: (-item[0], item[1].prompt))
        return [
            {
                **_serialize_entry(row),
                "score": round(min(score, 0.99), 4),
                "distance": round(max(0.0, 1.0 - min(score, 0.99)), 4),
            }
            for score, row in scored[:result_limit]
        ]
    finally:
        db.close()


def _should_prefer_dita_ot_retrieval(normalized_query: str) -> bool:
    parameter_terms = {
        "args.filter", "args.draft", "clean.temp", "dita.temp.dir", "generate-debug-attributes",
        "processing-mode", "args.grammar.cache", "args.resources", "outer.control",
        "onlytopic.in.map", "link-crawl", "force-unique", "root-chunk-override", "args.css",
        "args.copycss", "args.csspath", "args.rellinks", "pdf.formatter", "customization.dir",
        "dita install", "plugin.xml", "store-type", "parallel", "conserve-memory", "validate",
        "generate.copy.outer",
    }
    if any(term in normalized_query for term in parameter_terms):
        return True
    dita_ot_intent_terms = {
        "ditaval", "branch filtering", "resourceprefix", "resourcesuffix", "keyscopeprefix",
        "keyscopesuffix", "draft-comment", "required-cleanup", "release output", "row spans",
        "row span", "cals", "filtered rows", "filtered branch", "filtered branches",
        "conrefend", "range reuse", "xref rewriting", "publishing a submap", "submap alone",
        "related links", "relationship table", "svg", "windows", "linux", "non-ascii",
        "case-sensitive", "case sensitive", "path issues",
    }
    if any(term in normalized_query for term in dita_ot_intent_terms) and "@" not in normalized_query:
        return True
    return (
        ("dita-ot" in normalized_query or "dita ot" in normalized_query)
        and any(term in normalized_query for term in {"command", "parameter", "temp", "plugin", "build", "debug", "html5", "pdf"})
        and "@" not in normalized_query
    )


_LEARNED_QA_DOMAIN_TERMS = {
    "dita",
    "dita-ot",
    "oxygen",
    "webhelp",
    "pdf",
    "pdf chemistry",
    "native pdf",
    "aem guides",
    "author mode",
    "web author",
    "dita maps manager",
    "root map",
    "keyref",
    "keydef",
    "keyscope",
    "conref",
    "conkeyref",
    "xref",
    "topicref",
    "topichead",
    "topicmeta",
    "ditaval",
    "processing-role",
    "resource-only",
    "copy-to",
    "chunk",
    "reltable",
    "relationship table",
    "subject scheme",
    "schematron",
    "specialization",
    "catalog",
    "transformation scenario",
    "publishing template",
    "warnings",
    "publishing warnings",
    "published output",
    "accessibility",
    "context-help",
    "context help",
}


def is_learned_qa_domain_query(query: str) -> bool:
    """Return True when a user query is likely covered by learned DITA/Oxygen expertise."""
    normalized = normalize_prompt(query)
    if not normalized:
        return False
    if any(term in normalized for term in _LEARNED_QA_DOMAIN_TERMS):
        return True
    try:
        matches = retrieve_learned_qa(normalized, k=1)
    except Exception:
        matches = []
    if not matches:
        return False
    try:
        score = float(matches[0].get("score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    source_type = str(matches[0].get("source_type") or "")
    return score >= 0.82 or (score >= 0.68 and source_type in {"oxygen_customer_questions", "customer_paraphrase"})


def _fallback_embedding(text: str, *, dim: int = LEARNED_QA_FALLBACK_EMBED_DIM) -> list[float]:
    """Create a deterministic sparse lexical embedding for offline learned-QA retrieval."""
    tokens = list(_tokenize(text))
    if not tokens:
        return [0.0] * dim
    vector = [0.0] * dim
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        slot = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[slot] += sign
    magnitude = sum(value * value for value in vector) ** 0.5
    if magnitude <= 0:
        return vector
    return [round(value / magnitude, 8) for value in vector]


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
    items = [item for item in raw if isinstance(item, dict)]
    if LEARNED_QA_SEED_PATH == DEFAULT_LEARNED_QA_SEED_PATH:
        from app.services.learned_qa_advanced_seed import get_advanced_dita_seed_items
        from app.services.learned_qa_attribute_seed import get_dita_attribute_seed_items
        from app.services.learned_qa_dita_ot_complex_seed import get_dita_ot_complex_seed_items
        from app.services.learned_qa_dita_ot_researched_seed import get_dita_ot_researched_seed_items
        from app.services.learned_qa_eval_seed import get_dita_expert_eval_seed_items
        from app.services.learned_qa_enterprise_seed import get_enterprise_dita_seed_items
        from app.services.learned_qa_oxygen_customer_seed import get_oxygen_customer_seed_items
        from app.services.learned_qa_reltable_seed import get_reltable_seed_items
        from app.services.learned_qa_senior_seed import get_senior_prompt_seed_items

        items.extend(get_senior_prompt_seed_items())
        items.extend(get_enterprise_dita_seed_items())
        items.extend(get_dita_expert_eval_seed_items())
        items.extend(get_advanced_dita_seed_items())
        items.extend(get_oxygen_customer_seed_items())
        items.extend(get_dita_attribute_seed_items())
        items.extend(get_dita_ot_complex_seed_items())
        items.extend(get_dita_ot_researched_seed_items())
        items.extend(get_reltable_seed_items())

    deduped: list[dict[str, Any]] = []
    seen_prompts: set[str] = set()
    for item in items:
        normalized = normalize_prompt(str(item.get("prompt") or ""))
        if not normalized or normalized in seen_prompts:
            continue
        seen_prompts.add(normalized)
        deduped.append(item)
    return deduped


def _seed_file_metadata() -> dict[str, Any]:
    seed_items = _read_seed_items()
    payload = json.dumps(seed_items, ensure_ascii=False, sort_keys=True).encode("utf-8")
    item_count = len(seed_items)
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
    if any(marker in corpus for marker in ("cms", "root map", "dependency graph", "rename", "move", "standalone topic")):
        return "cms_architecture"
    if any(marker in corpus for marker in ("cache", "preprocessing", "invalidation", "processor-specific", "processor behavior")):
        return "processing_architecture"
    if any(marker in corpus for marker in ("chatbot", "evidence", "specification-defined", "dita specification")):
        return "chatbot_governance"
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
    source_rows = (
        session.query(LearnedPromptEntry.source_type, LearnedPromptEntry.status, func.count(LearnedPromptEntry.id))
        .group_by(LearnedPromptEntry.source_type, LearnedPromptEntry.status)
        .all()
    )
    source_type_counts: dict[str, dict[str, int]] = {}
    for source_type, status, count in source_rows:
        source_key = str(source_type or "unknown")
        status_key = str(status or "unknown")
        source_type_counts.setdefault(source_key, {})
        source_type_counts[source_key][status_key] = int(count or 0)
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
        "source_type_counts": source_type_counts,
        "customer_question_count": int(
            sum(sum(statuses.values()) for source, statuses in source_type_counts.items() if source == "oxygen_customer_questions")
        ),
        "customer_unmapped_count": int(source_type_counts.get("oxygen_customer_questions_unmapped", {}).get("pending_review", 0)),
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
    allow_near_dedupe: bool = True,
) -> tuple[LearnedPromptEntry, bool, str]:
    accepted_at = _coerce_naive_utc(accepted_at)
    approved_at = _coerce_naive_utc(approved_at)
    normalized = normalize_prompt(prompt)
    phash = prompt_hash(normalized)
    resolved_tags = list(tags or infer_tags(prompt, final_answer))
    resolved_topic = topic or infer_topic(prompt, resolved_tags)
    entry = session.query(LearnedPromptEntry).filter(LearnedPromptEntry.prompt_hash == phash).first()
    dedupe_kind = "exact" if entry else "new"
    if entry is None and allow_near_dedupe:
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
            source_type=str(item.get("source_type") or "seed").strip() or "seed",
            status="approved",
            answer_style=str(item.get("answer_style") or LEARNED_QA_ANSWER_STYLE),
            accepted_at=datetime.now(timezone.utc),
            approved_at=datetime.now(timezone.utc),
            allow_near_dedupe=False,
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
            auto_index_ready = chroma_ok
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
    ids = [row.id for row in rows]
    docs = [_document_text(row) for row in rows]
    embeddings = embed_texts_batched(docs, batch_size=32)
    embedding_mode = "semantic"
    if embeddings is None:
        embedding_mode = "lexical_fallback"
        emb_list = [_fallback_embedding(doc) for doc in docs]
    else:
        emb_list = [embeddings[index].tolist() for index in range(len(ids))]
    metas = [
        {
            "entry_id": row.id,
            "topic": str(row.topic or ""),
            "source_type": str(row.source_type or ""),
            "status": str(row.status or ""),
            "answer_style": str(row.answer_style or ""),
            "support_count": int(row.support_count or 0),
            "prompt_hash": row.prompt_hash,
            "embedding_mode": embedding_mode,
        }
        for row in rows
    ]
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

    normalized = normalize_prompt(text)
    exact_hash = prompt_hash(normalized)
    db = SessionLocal()
    try:
        exact_entry = (
            db.query(LearnedPromptEntry)
            .filter(
                LearnedPromptEntry.prompt_hash == exact_hash,
                LearnedPromptEntry.status == "approved",
            )
            .first()
        )
        if exact_entry:
            return [{**_serialize_entry(exact_entry), "score": 1.0, "distance": 0.0}]
    finally:
        db.close()

    if _should_prefer_dita_ot_retrieval(normalized):
        dita_ot_matches = _retrieve_dita_ot_complex_candidates(normalized, result_limit)
        if dita_ot_matches and float(dita_ot_matches[0].get("score") or 0.0) >= 0.78:
            return dita_ot_matches

    attribute_matches = _retrieve_attribute_qa_candidates(normalized, result_limit)
    if attribute_matches and float(attribute_matches[0].get("score") or 0.0) >= 0.78:
        return attribute_matches

    dita_ot_matches = _retrieve_dita_ot_complex_candidates(normalized, result_limit)
    if dita_ot_matches and float(dita_ot_matches[0].get("score") or 0.0) >= 0.78:
        return dita_ot_matches

    if is_chroma_available() and get_collection_count(CHROMA_COLLECTION_LEARNED_QA) > 0:
        emb = embed_query(text[:4000])
        vec = emb.tolist() if hasattr(emb, "tolist") else list(emb) if emb is not None else []
        if vec:
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
        for row in rows:
            score = _jaccard_similarity(normalized, row.normalized_prompt or "")
            if score <= 0:
                haystack = f"{row.prompt}\n{row.final_answer}\n{' '.join(_json_loads_tags(row.tags_json))}"
                score = _jaccard_similarity(normalized, normalize_prompt(haystack))
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
    return (
        "LEARNED PROMPT CORPUS:\n"
        "These are approved senior prompt/answer examples. For close matches, prefer their answer shape, "
        "practical explanation, and XML/example depth over generic source summaries.\n\n"
        + "\n\n".join(parts)
    )


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
