"""Retrieve and rerank Jira QA chunks from Chroma."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from app.services.embedding_service import embed_query, is_embedding_available
from app.services.jira_qa_copilot_cache import cache_get_embedding_vector, cache_set_embedding_vector
from app.services.vector_store_service import (
    CHROMA_COLLECTION_JIRA_QA,
    get_documents_where,
    is_chroma_available,
)
from app.services.enterprise_qa.enterprise_reranking_engine import (
    EnterpriseRerankingEngine,
    build_rerank_base_from_issue_chunks,
)

_SIGNAL_TYPES = frozenset({"full_ticket_summary", "customer_problem", "similar_ticket_signals"})


def _parse_json_list(raw: str) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).lower() for x in data if x]
        return []
    except (json.JSONDecodeError, TypeError):
        return []


def _norm_customer_token(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def get_chunks_for_jira_key(jira_key: str, *, limit: int = 64) -> list[dict[str, Any]]:
    """All indexed chunks for one issue."""
    if not is_chroma_available():
        return []
    rows = get_documents_where(
        CHROMA_COLLECTION_JIRA_QA,
        {"jira_key": jira_key},
        limit=limit,
    )
    return [
        {
            "jira_key": (r.get("metadata") or {}).get("jira_key", ""),
            "chunk_type": (r.get("metadata") or {}).get("chunk_type", ""),
            "document": r.get("document") or "",
            "score": 1.0,
            "metadata": r.get("metadata") or {},
        }
        for r in rows
    ]


_LIVE_ISSUE_FIELDS = (
    "summary,description,status,issuetype,priority,labels,components,created,updated,comment"
)


def _flatten_jira_text_field(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, dict):
        raw = json.dumps(val, ensure_ascii=False)
        return raw.strip()[:8000]
    return str(val).strip()[:8000]


def live_jira_snapshot_chunk(jira_key: str) -> dict[str, Any] | None:
    """One synthetic chunk from live Jira REST for the primary key (current fields, esp. description/comments).

    Controlled by ``JIRA_QA_COPILOT_LIVE_ISSUE`` (default true). Requires ``JIRA_*`` credentials like indexing.
    """
    flag = os.getenv("JIRA_QA_COPILOT_LIVE_ISSUE", "true").lower()
    if flag not in ("1", "true", "yes", "on"):
        return None
    from app.services.jira_client import JiraClient

    client = JiraClient()
    has_auth = (client.username and client.password) or (client.email and client.api_token)
    if not client.base_url or not has_auth:
        return None
    try:
        issue = client.get_issue(jira_key.strip(), fields=_LIVE_ISSUE_FIELDS)
    except Exception:
        return None
    fields = issue.get("fields") or {}
    if not isinstance(fields, dict):
        return None
    summary = str(fields.get("summary") or "").strip()
    st = fields.get("status") or {}
    status = str(st.get("name") or st or "").strip()
    it = fields.get("issuetype") or {}
    itype = str(it.get("name") or it or "").strip()
    desc = _flatten_jira_text_field(fields.get("description"))[:8000]
    comments_raw = fields.get("comment") or {}
    comments_list: list[Any] = []
    if isinstance(comments_raw, dict):
        comments_list = comments_raw.get("comments") or []
    if not isinstance(comments_list, list):
        comments_list = []
    c_lines: list[str] = []
    for c in comments_list[-10:]:
        if not isinstance(c, dict):
            continue
        body = _flatten_jira_text_field(c.get("body"))[:1200]
        who = c.get("author") or {}
        who_n = str(who.get("displayName") or who.get("name") or "") if isinstance(who, dict) else ""
        line = f"- {who_n}: {body}".strip()
        c_lines.append(line)
        if sum(len(x) for x in c_lines) > 4000:
            break
    cblob = "\n".join(c_lines)
    lines = [
        "[LIVE JIRA at request time — verify status/comments in Jira UI]",
        f"Key: {jira_key.strip()}",
        f"Summary: {summary}",
        f"Status: {status}",
        f"Issue type: {itype}",
        "",
        "Description (truncated):",
        desc or "(empty)",
    ]
    if cblob:
        lines.extend(["", "Recent comments (truncated, newest last):", cblob])
    doc = "\n".join(lines)[:16000]
    if len(doc.strip()) < 24:
        return None
    return {
        "jira_key": jira_key.strip(),
        "chunk_type": "live_jira_snapshot",
        "document": doc,
        "score": 1.0,
        "metadata": {
            "jira_key": jira_key.strip(),
            "chunk_type": "live_jira_snapshot",
            "title": summary[:500],
            "issue_type": itype,
            "status": status,
            "source_type": "live_jira",
        },
    }


def build_signal_text_for_issue(jira_key: str) -> str:
    """Merge signal chunk documents for embedding as related-ticket query."""
    parts: list[str] = []
    for row in get_chunks_for_jira_key(jira_key):
        ct = row.get("chunk_type") or ""
        if ct in _SIGNAL_TYPES:
            doc = (row.get("document") or "").strip()
            if doc:
                parts.append(doc)
    if parts:
        return "\n\n".join(parts)[:12000]
    return jira_key


def semantic_search_jira_qa(
    query_text: str,
    *,
    top_k: int = 15,
    exclude_jira_key: str | None = None,
    customer: str | None = None,
    base_labels: list[str] | None = None,
    base_components: list[str] | None = None,
    label_expanded_tokens: frozenset[str] | None = None,
    rerank_base: dict[str, Any] | None = None,
    domain: str | None = None,
    dita_entities: list[str] | None = None,
    affected_outputs: list[str] | None = None,
    customer_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Hybrid retrieval over jira_qa (vector + keyword overlap + enrichment metadata + diversity)."""
    from app.services.jira_retrieval_service import retrieve_similar_jiras, retrieved_to_legacy_hit

    if not query_text.strip() or not is_chroma_available() or not is_embedding_available():
        return []
    qt = query_text[:12000]
    cached = cache_get_embedding_vector(qt)
    if cached is not None:
        emb = cached
    else:
        qv = embed_query(qt)
        if qv is None:
            return []
        emb = qv.tolist() if hasattr(qv, "tolist") else list(qv)
        cache_set_embedding_vector(qt, emb)

    names = list(customer_names or [])
    if customer and str(customer).strip():
        names.append(str(customer).strip())

    retrieved = retrieve_similar_jiras(
        qt,
        domain=domain,
        dita_entities=dita_entities or [],
        affected_outputs=affected_outputs or [],
        customer_names=names,
        limit=top_k,
        query_embedding=emb,
        exclude_jira_key=exclude_jira_key,
        base_labels=base_labels,
        base_components=base_components,
        label_expanded_tokens=label_expanded_tokens,
        require_non_vector_evidence=False,
    )
    ranked_full = [retrieved_to_legacy_hit(r) for r in retrieved]
    if rerank_base and ranked_full:
        ranked_full = EnterpriseRerankingEngine().rerank_hits(base=rerank_base, hits=ranked_full)
    return ranked_full[:top_k]


def related_tickets_for_issue(
    base_jira_key: str,
    *,
    top_k: int = 10,
    customer: str | None = None,
    label_expanded_tokens: frozenset[str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Return ranked related jira keys + signal text used for query."""
    from app.services.jira_retrieval_service import extract_hybrid_filters_from_issue_rows

    base_meta_rows = get_chunks_for_jira_key(base_jira_key)
    labels: list[str] = []
    components: list[str] = []
    cust = customer or ""
    for row in base_meta_rows:
        m = row.get("metadata") or {}
        if not cust:
            cust = str(m.get("customer") or "")
        if not labels:
            labels = _parse_json_list(str(m.get("labels") or ""))
        if not components:
            components = _parse_json_list(str(m.get("components") or ""))
    signal = build_signal_text_for_issue(base_jira_key)
    rerank_base = build_rerank_base_from_issue_chunks(
        jira_key=base_jira_key,
        rows=base_meta_rows,
        extra_blob=signal,
    )
    hy = extract_hybrid_filters_from_issue_rows(base_meta_rows)
    cust_names = list(hy.get("customer_names") or [])
    if cust and str(cust).strip():
        c0 = str(cust).strip()
        if _norm_customer_token(c0) not in {_norm_customer_token(x) for x in cust_names}:
            cust_names.insert(0, c0)

    hits = semantic_search_jira_qa(
        signal,
        top_k=top_k,
        exclude_jira_key=base_jira_key,
        customer=cust or None,
        base_labels=labels,
        base_components=components,
        label_expanded_tokens=label_expanded_tokens,
        rerank_base=rerank_base,
        domain=hy.get("domain"),
        dita_entities=hy.get("dita_entities") or [],
        affected_outputs=hy.get("affected_outputs") or [],
        customer_names=cust_names,
    )
    return hits, signal


def extract_jira_key_from_text(text: str) -> str | None:
    m = re.search(r"\b[A-Z][A-Z0-9]+-\d+\b", text or "")
    return m.group(0) if m else None
