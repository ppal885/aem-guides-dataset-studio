"""Persistence for enriched Jira issues + SQL-backed chunks (filters: domain, entities, customers)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Text, func, or_
from sqlalchemy.orm import Session

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.db.jira_enrichment_models import CustomerAlias, JiraEnrichedIssue, JiraEnrichmentReviewQueue, JiraIssueChunk


def load_customer_aliases(session: Session) -> dict[str, str]:
    """Lowercased alias -> canonical_name for customer normalization (empty if table missing)."""
    try:
        rows = session.query(CustomerAlias).all()
    except Exception:
        return {}
    out: dict[str, str] = {}
    for r in rows:
        a = (r.alias or "").strip()
        c = (r.canonical_name or "").strip()
        if a and c:
            out[a.lower()] = c
    return out


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def weak_enrichment_review_reasons(enriched_doc: JiraEnrichedDocument) -> list[str]:
    """
    Reasons to queue an issue for taxonomy review (OR semantics across flags).
    """
    reasons: list[str] = []
    domain = (enriched_doc.domain or "").strip().lower()
    if domain == "unknown" or not domain:
        reasons.append("domain_unknown")
    if not (enriched_doc.dita_entities or []):
        reasons.append("entities_empty")
    if len(enriched_doc.missing_info or []) > 3:
        reasons.append("missing_info_gt_3")
    return reasons


def suggested_domain_for_review(enriched_doc: JiraEnrichedDocument) -> str:
    """Heuristic hint when domain is weak; sub_domain or first affected_feature."""
    if (enriched_doc.domain or "").strip().lower() not in ("unknown", ""):
        return ""
    sub = (enriched_doc.sub_domain or "").strip()
    if sub:
        return sub[:120]
    feats = enriched_doc.affected_features or []
    if feats:
        return str(feats[0]).strip()[:120]
    return ""


def enqueue_weak_enrichment_review(
    session: Session,
    enriched_doc: JiraEnrichedDocument,
) -> bool:
    """
    If enrichment is weak, append a review queue row. Returns True if enqueued.
    Errors are swallowed by design — queue must not block indexing.
    """
    flags = weak_enrichment_review_reasons(enriched_doc)
    if not flags:
        return False
    jira_key = str(enriched_doc.jira_key or "").strip()
    if not jira_key:
        return False
    try:
        reason = ";".join(flags)
        raw = (enriched_doc.raw_text or "")[:65000]
        sugg = suggested_domain_for_review(enriched_doc) or None
        with session.begin_nested():
            row = JiraEnrichmentReviewQueue(
                jira_key=jira_key,
                reason=reason,
                raw_text=raw or None,
                suggested_domain=sugg,
            )
            session.add(row)
            session.flush()
        return True
    except Exception:
        return False


def list_enrichment_review_queue(session: Session, *, limit: int = 200) -> list[dict[str, Any]]:
    """Newest first."""
    lim = max(1, min(int(limit), 2000))
    try:
        rows = (
            session.query(JiraEnrichmentReviewQueue)
            .order_by(JiraEnrichmentReviewQueue.created_at.desc())
            .limit(lim)
            .all()
        )
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "jira_key": r.jira_key,
                "reason": r.reason,
                "raw_text": r.raw_text,
                "suggested_domain": r.suggested_domain,
                "created_at": _iso(r.created_at),
            }
        )
    return out


def upsert_jira_issue(session: Session, enriched_doc: JiraEnrichedDocument) -> JiraEnrichedIssue:
    """Insert or update a row in ``jira_enriched_issues`` keyed by ``jira_key``."""
    data = enriched_doc.model_dump()
    jira_key = str(data.get("jira_key") or "").strip()
    if not jira_key:
        raise ValueError("enriched_doc.jira_key is required")

    now = datetime.utcnow()
    row = session.query(JiraEnrichedIssue).filter(JiraEnrichedIssue.jira_key == jira_key).first()
    if row is None:
        row = JiraEnrichedIssue(jira_key=jira_key, created_at=now)
        session.add(row)

    row.summary = data.get("summary") or None
    row.description = data.get("description") or None
    row.issue_type = data.get("issue_type") or None
    row.status = data.get("status") or None
    row.priority = data.get("priority") or None
    row.labels = data.get("labels") or []
    row.components = data.get("components") or []
    row.customer_names = data.get("customer_names") or []
    row.domain = (data.get("domain") or "unknown")[:80]
    row.sub_domain = (data.get("sub_domain") or "")[:120] or None
    row.affected_outputs = data.get("affected_outputs") or []
    row.affected_features = data.get("affected_features") or []
    row.dita_entities = data.get("dita_entities") or []
    row.symptoms = data.get("symptoms") or []
    row.expected_behavior = data.get("expected_behavior") or None
    row.actual_behavior = data.get("actual_behavior") or None
    row.qa_risk_tags = data.get("qa_risk_tags") or []
    row.automation_fit = (data.get("automation_fit") or "")[:200] or None
    row.missing_info = data.get("missing_info") or []
    row.raw_text = data.get("raw_text") or None
    row.customer_detection_debug = data.get("customer_detection_debug") or {}
    row.updated_at = now
    row.indexed_at = now
    session.flush()
    enqueue_weak_enrichment_review(session, enriched_doc)
    return row


def insert_jira_chunks(
    session: Session,
    jira_key: str,
    chunks: list[dict[str, Any]],
    *,
    enrichment: JiraEnrichedDocument | None = None,
) -> int:
    """
    Replace all ``jira_chunks`` rows for ``jira_key`` with ``chunks`` (RAG chunk dicts from
    ``build_jira_qa_chunks``: ``chunk_id``, ``document``, ``metadata``). Optional per-chunk
    ``embedding`` (list[float]) is stored in ``embedding`` JSON.
    """
    jira_key = str(jira_key or "").strip()
    if not jira_key:
        raise ValueError("jira_key is required")

    session.query(JiraIssueChunk).filter(JiraIssueChunk.jira_key == jira_key).delete(synchronize_session=False)

    enr = enrichment
    domain = (enr.domain if enr else None) or "unknown"
    cust = list(enr.customer_names) if enr else []
    outs = list(enr.affected_outputs) if enr else []
    ents = list(enr.dita_entities) if enr else []

    n = 0
    now = datetime.utcnow()
    for c in chunks:
        meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
        ctype = str(meta.get("chunk_type") or "").strip() or "unknown"
        text = str(c.get("document") or "").strip()
        if not text:
            continue
        chunk_domain = str(meta.get("enrich_domain") or domain or "unknown")[:80]
        emb = c.get("embedding")
        if emb is not None and not isinstance(emb, list):
            emb = None
        row = JiraIssueChunk(
            jira_key=jira_key,
            chunk_type=ctype[:80],
            chunk_text=text,
            domain=chunk_domain,
            customer_names=cust,
            affected_outputs=outs,
            dita_entities=ents,
            embedding=emb,
            created_at=now,
        )
        session.add(row)
        n += 1
    session.flush()
    return n


def get_jira_by_key(session: Session, jira_key: str) -> dict[str, Any] | None:
    """Return JSON-serializable dict for one enriched issue, or ``None``."""
    row = session.query(JiraEnrichedIssue).filter(JiraEnrichedIssue.jira_key == jira_key.strip()).first()
    if row is None:
        return None
    return {
        "id": row.id,
        "jira_key": row.jira_key,
        "summary": row.summary,
        "description": row.description,
        "issue_type": row.issue_type,
        "status": row.status,
        "priority": row.priority,
        "labels": row.labels,
        "components": row.components,
        "customer_names": row.customer_names,
        "domain": row.domain,
        "sub_domain": row.sub_domain,
        "affected_outputs": row.affected_outputs,
        "affected_features": row.affected_features,
        "dita_entities": row.dita_entities,
        "symptoms": row.symptoms,
        "expected_behavior": row.expected_behavior,
        "actual_behavior": row.actual_behavior,
        "qa_risk_tags": row.qa_risk_tags,
        "automation_fit": row.automation_fit,
        "missing_info": row.missing_info,
        "raw_text": row.raw_text,
        "enrichment_debug": {
            "customer_detection": row.customer_detection_debug or {},
            "source": "jira_enriched_issues",
        },
        "customer_detection_debug": row.customer_detection_debug,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        "indexed_at": _iso(row.indexed_at),
    }


def _norm_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if x is not None]
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except (json.JSONDecodeError, TypeError):
            return [v]
    return [str(v)]


def _overlap_any(haystack: list[str], needles: list[str]) -> bool:
    if not needles:
        return True
    for n in needles:
        nl = n.lower().strip()
        if not nl:
            continue
        for h in haystack:
            hl = h.lower()
            if nl == hl or nl in hl or hl in nl:
                return True
    return False


def _customer_match(row_customers: Any, customer: str, raw_text: str | None) -> bool:
    if not customer or not str(customer).strip():
        return True
    cl = customer.strip().lower()
    for c in _norm_list(row_customers):
        if cl in c.lower() or c.lower() in cl:
            return True
    if raw_text and cl in (raw_text or "").lower():
        return True
    return False


def search_jira_kb(
    session: Session,
    *,
    q: str | None = None,
    domain: str | None = None,
    output: str | None = None,
    entity: str | None = None,
    issue_type: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Keyword + metadata search over the indexed Jira knowledge base.

    - ``q``          : substring match on summary, description, dita_entities, affected_outputs, affected_features
    - ``domain``     : exact domain match (e.g. "native_pdf", "publishing")
    - ``output``     : substring match inside affected_outputs JSON
    - ``entity``     : substring match inside dita_entities JSON
    - ``issue_type`` : substring match on issue_type
    """
    qr = session.query(JiraEnrichedIssue)

    if domain:
        qr = qr.filter(JiraEnrichedIssue.domain == domain.strip().lower())

    if issue_type:
        qr = qr.filter(JiraEnrichedIssue.issue_type.ilike(f"%{issue_type.strip()}%"))

    # Cast JSON columns to Text for portable LIKE search (SQLite + PostgreSQL).
    if q:
        kw = f"%{q.strip().lower()}%"
        qr = qr.filter(
            or_(
                func.lower(JiraEnrichedIssue.summary).like(kw),
                func.lower(JiraEnrichedIssue.description).like(kw),
                func.lower(JiraEnrichedIssue.raw_text).like(kw),
                func.lower(JiraEnrichedIssue.dita_entities.cast(Text)).like(kw),
                func.lower(JiraEnrichedIssue.affected_outputs.cast(Text)).like(kw),
                func.lower(JiraEnrichedIssue.affected_features.cast(Text)).like(kw),
            )
        )

    if output:
        kw_o = f"%{output.strip().lower()}%"
        qr = qr.filter(
            func.lower(JiraEnrichedIssue.affected_outputs.cast(Text)).like(kw_o)
        )

    if entity:
        kw_e = f"%{entity.strip().lower()}%"
        qr = qr.filter(
            func.lower(JiraEnrichedIssue.dita_entities.cast(Text)).like(kw_e)
        )

    rows = qr.order_by(JiraEnrichedIssue.updated_at.desc()).limit(limit).all()

    result: list[dict[str, Any]] = []
    for row in rows:
        result.append({
            "jira_key": row.jira_key,
            "summary": row.summary or "",
            "domain": row.domain or "unknown",
            "sub_domain": row.sub_domain or "",
            "issue_type": row.issue_type or "",
            "status": row.status or "",
            "priority": row.priority or "",
            "affected_outputs": _norm_list(row.affected_outputs),
            "affected_features": _norm_list(row.affected_features),
            "dita_entities": _norm_list(row.dita_entities),
            "labels": _norm_list(row.labels),
            "components": _norm_list(row.components),
            "customer_names": _norm_list(row.customer_names),
            "qa_risk_tags": _norm_list(row.qa_risk_tags),
            "automation_fit": row.automation_fit or "",
            "indexed_at": _iso(row.indexed_at),
        })
    return result


def search_by_metadata(
    session: Session,
    *,
    domain: str | None = None,
    entities: list[str] | None = None,
    customer: str | None = None,
    affected_outputs: list[str] | None = None,
    limit: int = 50,
) -> list[JiraEnrichedIssue]:
    """
    Filter enriched issues. ``entities`` / ``affected_outputs`` match if **any** listed value
    overlaps stored list (case-insensitive). ``customer`` matches substring against stored
    customer_names or raw_text.
    """
    q = session.query(JiraEnrichedIssue)
    if domain:
        q = q.filter(JiraEnrichedIssue.domain == domain)
    # Over-fetch then refine for JSON list overlap (portable across SQLite / PostgreSQL).
    cap = min(max(limit * 20, limit), 2000)
    candidates: list[JiraEnrichedIssue] = (
        q.order_by(JiraEnrichedIssue.updated_at.desc()).limit(cap).all()
    )

    ent_needles = [e.strip() for e in (entities or []) if e and str(e).strip()]
    out_needles = [e.strip() for e in (affected_outputs or []) if e and str(e).strip()]
    cust = (customer or "").strip()

    out: list[JiraEnrichedIssue] = []
    for row in candidates:
        if not _customer_match(row.customer_names, cust, row.raw_text):
            continue
        if ent_needles and not _overlap_any(_norm_list(row.dita_entities), ent_needles):
            continue
        if out_needles and not _overlap_any(_norm_list(row.affected_outputs), out_needles):
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return out
