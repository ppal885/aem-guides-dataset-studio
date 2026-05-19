"""Jira QA index dashboard: SQL aggregates, sync state, failure log."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db.jira_enrichment_models import JiraEnrichedIssue, JiraIssueChunk
from app.services.jira_sync_state import load_jira_qa_sync_state
from app.services.vector_store_service import CHROMA_COLLECTION_JIRA_QA, get_collection_count, is_chroma_available
from app.storage import get_storage

FAILURE_LOG_FILENAME = "failure_log.jsonl"


def _failure_log_path() -> Path:
    base = get_storage().base_path / "jira_qa_sync"
    base.mkdir(parents=True, exist_ok=True)
    return base / FAILURE_LOG_FILENAME


def append_jira_index_failure(
    *,
    jira_key: str,
    error: str,
    sync_state_id: str | None = None,
) -> None:
    """Append one JSON line (best-effort; never raises to caller)."""
    key = (jira_key or "").strip()
    if not key:
        return
    try:
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "jira_key": key,
            "error": (error or "")[:4000],
            "sync_state_id": (sync_state_id or "").strip() or None,
        }
        path = _failure_log_path()
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_recent_failure_log(*, limit: int = 100) -> list[dict[str, Any]]:
    """Newest failures first (parses tail of JSONL)."""
    lim = max(1, min(int(limit), 500))
    path = _failure_log_path()
    if not path.is_file():
        return []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    items: list[dict[str, Any]] = []
    for ln in lines[-2000:]:
        try:
            obj = json.loads(ln)
            if isinstance(obj, dict) and obj.get("jira_key"):
                items.append(obj)
        except json.JSONDecodeError:
            continue
    items.sort(key=lambda x: str(x.get("ts") or ""), reverse=True)
    return items[:lim]


def _unique_strings(values: list[str], *, cap: int = 500) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= cap:
            break
    return out


def _sync_state_dir() -> Path:
    return get_storage().base_path / "jira_qa_sync"


def collect_sync_state_summaries() -> list[dict[str, Any]]:
    """Load all persisted Jira QA sync JSON files (excluding failure log)."""
    base = _sync_state_dir()
    if not base.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(base.glob("*.json")):
        sid = p.stem
        try:
            st = load_jira_qa_sync_state(sid)
        except ValueError:
            continue
        out.append(
            {
                "sync_state_id": sid,
                "last_successful_sync_time": st.last_successful_sync_time,
                "last_indexed_jira_key": st.last_indexed_jira_key,
                "total_indexed_recorded": st.total_indexed,
                "failed_keys_count": len(st.failed_keys or []),
            }
        )
    return out


def merged_failed_keys_from_sync_states(*, cap: int = 500) -> list[str]:
    seen: set[str] = set()
    keys: list[str] = []
    for row in collect_sync_state_summaries():
        sid = row["sync_state_id"]
        st = load_jira_qa_sync_state(sid)
        for k in st.failed_keys or []:
            s = str(k).strip()
            if not s or s in seen:
                continue
            seen.add(s)
            keys.append(s)
            if len(keys) >= cap:
                return keys
    return keys


def latest_sync_time_iso(summaries: list[dict[str, Any]], sql_max_indexed_at: str | None) -> str | None:
    candidates: list[str] = []
    if sql_max_indexed_at:
        candidates.append(sql_max_indexed_at)
    for s in summaries:
        t = s.get("last_successful_sync_time")
        if isinstance(t, str) and t.strip():
            candidates.append(t.strip())
    if not candidates:
        return None
    return max(candidates)


def _jira_issue_sample(query, *, limit: int = 25) -> list[dict[str, Any]]:  # noqa: ANN001
    rows = query.order_by(JiraEnrichedIssue.updated_at.desc()).limit(max(1, min(limit, 100))).all()
    return [
        {
            "jira_key": str(row.jira_key or ""),
            "summary": str(row.summary or "")[:300],
            "domain": str(row.domain or "unknown"),
            "customer_names": row.customer_names or [],
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "indexed_at": row.indexed_at.isoformat() if row.indexed_at else None,
        }
        for row in rows
    ]


def build_jira_index_status(session: Session | None) -> dict[str, Any]:
    """Aggregate SQL + Chroma + sync files for the admin dashboard."""
    summaries = collect_sync_state_summaries()
    log_items = read_recent_failure_log(limit=500)
    logged_failed_keys = [str(item.get("jira_key") or "").strip() for item in log_items]
    sync_failed_keys = merged_failed_keys_from_sync_states(cap=500)
    merged_fails = _unique_strings(sync_failed_keys + logged_failed_keys, cap=500)

    chroma_ok = is_chroma_available()
    chroma_chunks = int(get_collection_count(CHROMA_COLLECTION_JIRA_QA)) if chroma_ok else 0

    empty_sql = {
        "enriched_issues_total": 0,
        "distinct_issues_with_sql_chunks": 0,
        "sql_chunk_rows_total": 0,
        "last_sql_indexed_at": None,
        "unknown_domain_total": 0,
        "tickets_missing_expected_or_actual": 0,
        "tickets_with_unknown_domain_sample": [],
        "tickets_missing_expected_or_actual_sample": [],
        "domain_distribution": [],
        "customer_distribution": [],
        "sql_error": None,
    }

    if session is None:
        sql_part = {**empty_sql, "sql_error": "no_database_session"}
    else:
        try:
            enriched_total = session.query(func.count(JiraEnrichedIssue.id)).scalar() or 0
            chunk_rows = session.query(func.count(JiraIssueChunk.id)).scalar() or 0
            distinct_issues = session.query(func.count(func.distinct(JiraIssueChunk.jira_key))).scalar() or 0
            last_idx = session.query(func.max(JiraEnrichedIssue.indexed_at)).scalar()
            last_sql_iso = last_idx.isoformat() if last_idx else None

            dom_lower = func.lower(func.coalesce(JiraEnrichedIssue.domain, ""))
            unknown_total = (
                session.query(func.count(JiraEnrichedIssue.id))
                .filter(or_(dom_lower == "unknown", JiraEnrichedIssue.domain.is_(None), JiraEnrichedIssue.domain == ""))
                .scalar()
                or 0
            )
            unknown_query = session.query(JiraEnrichedIssue).filter(
                or_(dom_lower == "unknown", JiraEnrichedIssue.domain.is_(None), JiraEnrichedIssue.domain == "")
            )

            missing_expected_actual_filter = or_(
                JiraEnrichedIssue.expected_behavior.is_(None),
                JiraEnrichedIssue.expected_behavior == "",
                JiraEnrichedIssue.actual_behavior.is_(None),
                JiraEnrichedIssue.actual_behavior == "",
            )
            miss_ea = session.query(func.count(JiraEnrichedIssue.id)).filter(missing_expected_actual_filter).scalar() or 0
            missing_expected_actual_query = session.query(JiraEnrichedIssue).filter(missing_expected_actual_filter)

            dom_rows = (
                session.query(JiraEnrichedIssue.domain, func.count(JiraEnrichedIssue.id))
                .group_by(JiraEnrichedIssue.domain)
                .order_by(func.count(JiraEnrichedIssue.id).desc())
                .limit(40)
                .all()
            )
            domain_distribution = [
                {"domain": (d or "unknown"), "count": int(c)} for d, c in dom_rows
            ]

            cust_counter: Counter[str] = Counter()
            cust_cap = 20000
            for (raw_cust,) in session.query(JiraEnrichedIssue.customer_names).limit(cust_cap).all():
                if isinstance(raw_cust, list):
                    for x in raw_cust:
                        s = str(x).strip()
                        if s:
                            cust_counter[s] += 1
                elif raw_cust:
                    try:
                        arr = json.loads(raw_cust) if isinstance(raw_cust, str) else raw_cust
                        if isinstance(arr, list):
                            for x in arr:
                                s = str(x).strip()
                                if s:
                                    cust_counter[s] += 1
                    except (json.JSONDecodeError, TypeError):
                        pass
            customer_distribution = [
                {"customer": k, "count": v} for k, v in cust_counter.most_common(30)
            ]

            sql_part = {
                "enriched_issues_total": int(enriched_total),
                "distinct_issues_with_sql_chunks": int(distinct_issues),
                "sql_chunk_rows_total": int(chunk_rows),
                "last_sql_indexed_at": last_sql_iso,
                "unknown_domain_total": int(unknown_total),
                "tickets_missing_expected_or_actual": int(miss_ea),
                "tickets_with_unknown_domain_sample": _jira_issue_sample(unknown_query, limit=25),
                "tickets_missing_expected_or_actual_sample": _jira_issue_sample(missing_expected_actual_query, limit=25),
                "domain_distribution": domain_distribution,
                "customer_distribution": customer_distribution,
                "sql_error": None,
            }
        except Exception as exc:
            sql_part = {**empty_sql, "sql_error": str(exc)[:500]}

    last_sync = latest_sync_time_iso(summaries, sql_part.get("last_sql_indexed_at"))

    enriched = int(sql_part.get("enriched_issues_total") or 0)
    distinct_chunked = int(sql_part.get("distinct_issues_with_sql_chunks") or 0)
    sql_chunk_rows = int(sql_part.get("sql_chunk_rows_total") or 0)
    total_chunks = chroma_chunks if chroma_ok else sql_chunk_rows

    return {
        "chroma_available": chroma_ok,
        "chroma_collection": CHROMA_COLLECTION_JIRA_QA,
        "chroma_chunk_documents_total": chroma_chunks,
        "total_indexed_jira": distinct_chunked,
        "total_enriched_jira": enriched,
        "total_chunks": total_chunks,
        "totals": {
            "total_enriched_jira": enriched,
            "total_indexed_jira": distinct_chunked,
            "total_indexed_jira_sql_distinct": distinct_chunked,
            "total_chunks": total_chunks,
            "total_sql_chunk_rows": sql_chunk_rows,
            "total_chroma_chunk_documents": chroma_chunks,
        },
        "last_sync_time": last_sync,
        "failed_jira_keys": merged_fails,
        "failed_jira_keys_sync_state": sync_failed_keys,
        "failed_jira_keys_failure_log": _unique_strings(logged_failed_keys, cap=500),
        "recent_failure_count": len(log_items),
        "sync_states": summaries,
        "tickets_with_unknown_domain": int(sql_part.get("unknown_domain_total") or 0),
        "tickets_missing_expected_or_actual": int(sql_part.get("tickets_missing_expected_or_actual") or 0),
        **sql_part,
        "notes": (
            "total_enriched_jira counts rows in jira_enriched_issues (SQL enrichment). "
            "total_indexed_jira_sql_distinct is COUNT(DISTINCT jira_key) in jira_chunks. "
            "total_chroma_chunk_documents is the Chroma embedding count (typically multiple chunks per issue). "
            "Values align when indexing runs with JIRA_SQL_ENRICHMENT and the same chunk pipeline."
        ),
    }


def build_recent_failures_payload(*, limit: int = 100) -> dict[str, Any]:
    log_items = read_recent_failure_log(limit=limit)
    sync_fails = merged_failed_keys_from_sync_states(cap=200)
    logged_keys = [str(item.get("jira_key") or "").strip() for item in log_items]
    failed_keys = _unique_strings(sync_fails + logged_keys, cap=max(200, limit))
    return {
        "failed_jira_keys": failed_keys,
        "total_failed_jira_keys": len(failed_keys),
        "failure_log_items": log_items,
        "failed_keys_from_sync_state_sample": sync_fails[: min(50, len(sync_fails))],
        "failed_keys_from_failure_log_sample": _unique_strings(logged_keys, cap=50),
        "count_logged": len(log_items),
    }
