"""Index Jira issues into Chroma `jira_qa` collection for QA RAG."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from app.core.structured_logging import get_structured_logger
from app.db.jira_enrichment_repository import insert_jira_chunks, upsert_jira_issue
from app.db.session import SessionLocal
from app.services.embedding_service import embed_texts_batched, is_embedding_available
from app.services.jira_client import JiraClient
from app.services.jira_enrichment_service import enrich_jira
from app.services.jira_qa_chunking_service import (
    CHUNK_TYPES,
    JIRA_QA_DESCRIPTION_LONG_PART_MAX,
    build_jira_qa_chunks,
)
from app.services.jira_index_dashboard_service import append_jira_index_failure
from app.services.jira_sync_state import (
    JiraQaIndexSyncState,
    build_backfill_jql,
    build_incremental_jql,
    load_jira_qa_sync_state,
    merge_failed_keys,
    save_jira_qa_sync_state,
)
from app.services.vector_store_service import (
    CHROMA_COLLECTION_JIRA_QA,
    add_documents,
    delete_documents,
    is_chroma_available,
)

logger = get_structured_logger(__name__)


def _format_jira_index_search_error(exc: Exception) -> str:
    """User-actionable message for Jira /search failures (no secrets)."""

    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code if exc.response is not None else 0
        if code == 401:
            return (
                "HTTP 401 — Jira rejected credentials. For Jira Cloud use email + API token; "
                "for corp/on-prem check JIRA_USERNAME/JIRA_PASSWORD and VPN."
            )
        if code == 403:
            return (
                "HTTP 403 — authenticated user cannot run this JQL (no Browse permission on the project, "
                "or Jira blocked the search). Fix: set JIRA_PROJECT_KEY in backend/.env to a project you can browse, "
                "match the JQL to that project, use an API token if password-only SSO is restricted, "
                "and keep JIRA_API_VERSION=2 for typical on-prem Jira."
            )
        if code == 404:
            return (
                "HTTP 404 — Jira REST path not found. Check JIRA_URL and JIRA_API_VERSION (v2 for on-prem, v3 for Cloud)."
            )
    return str(exc)


JIRA_SQL_ENRICHMENT = os.getenv("JIRA_SQL_ENRICHMENT", "true").lower() in ("true", "1", "yes")
JIRA_INDEX_RETRY_ATTEMPTS = max(1, int(os.getenv("JIRA_INDEX_RETRY_ATTEMPTS", "3")))
JIRA_INDEX_RETRY_SLEEP_SECONDS = max(0.0, float(os.getenv("JIRA_INDEX_RETRY_SLEEP_SECONDS", "0.25")))


def _with_retry(operation: str, fn, *, jira_key: str | None = None):  # noqa: ANN001
    """Run transient Jira/index operations with bounded retries and structured logs."""

    last_exc: Exception | None = None
    for attempt in range(1, JIRA_INDEX_RETRY_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - indexer must record all recoverable failures
            last_exc = exc
            logger.warning_structured(
                "jira_qa_index_retry",
                extra_fields={
                    "operation": operation,
                    "jira_key": jira_key,
                    "attempt": attempt,
                    "max_attempts": JIRA_INDEX_RETRY_ATTEMPTS,
                    "error": str(exc),
                },
            )
            if attempt < JIRA_INDEX_RETRY_ATTEMPTS and JIRA_INDEX_RETRY_SLEEP_SECONDS > 0:
                time.sleep(JIRA_INDEX_RETRY_SLEEP_SECONDS)
    assert last_exc is not None
    raise last_exc


def _resolve_index_limit(limit: int | None) -> int | None:
    """
    Maximum issues to process this run. ``None`` = use ``JIRA_QA_RAG_DEFAULT_LIMIT`` env, or unlimited
    if env is ``0``, empty, or ``all``.
    """
    if limit is not None:
        return max(int(limit), 1)
    raw = (os.getenv("JIRA_QA_RAG_DEFAULT_LIMIT") or "").strip().lower()
    if not raw or raw in ("all", "none", "unlimited", "0"):
        return None
    try:
        v = int(raw)
        return None if v <= 0 else v
    except ValueError:
        return 1000


def _max_issues_per_run() -> int | None:
    """Safety cap per run (``None`` = no extra cap beyond ``limit``)."""
    raw = (os.getenv("JIRA_QA_RAG_MAX_ISSUES_PER_RUN") or "200000").strip().lower()
    if raw in ("all", "none", "unlimited", "0"):
        return None
    try:
        v = int(raw)
        return None if v <= 0 else v
    except ValueError:
        return 200000


def _search_page_size_indexer() -> int:
    """Page size for /search when pulling keys (falls back to ``JIRA_SEARCH_PAGE_SIZE``)."""
    raw = (os.getenv("JIRA_INDEX_SEARCH_PAGE_SIZE") or os.getenv("JIRA_SEARCH_PAGE_SIZE") or "100").strip()
    try:
        v = int(raw)
    except ValueError:
        v = 100
    return max(1, min(v, 100))


def _issues_per_embed_batch() -> int:
    raw = (os.getenv("JIRA_INDEX_ISSUES_PER_EMBED_BATCH") or "32").strip()
    try:
        v = int(raw)
    except ValueError:
        v = 32
    return max(1, min(v, 500))


def _index_run_stats(
    *,
    lim: int | None,
    jira_total: int,
    keys_fetched_from_search: int,
    issues_indexed: int,
    issues_failed: int,
    errors: list[str],
    chunks: int,
) -> dict[str, Any]:
    """Return JSON-serializable primitives only (middleware buffers response bodies)."""
    jt = int(jira_total)
    kfs = int(keys_fetched_from_search)
    ii = int(issues_indexed)
    iff = int(issues_failed)
    ch = int(chunks)
    avg = float(round(float(ch) / float(ii), 3)) if ii else None
    return {
        "jira_total": jt,
        "keys_requested": lim,
        "keys_returned": kfs,
        "indexed_issues": ii,
        "issues_indexed": ii,
        "issues_failed": iff,
        "errors_count": int(len(errors)),
        "chunks": ch,
        "chunks_avg_per_indexed_issue": avg,
    }


# Comma-separated field list for search + get_issue (Jira REST)
JIRA_QA_ISSUE_FIELDS = os.getenv(
    "JIRA_QA_ISSUE_FIELDS",
    "summary,description,labels,components,priority,status,created,updated,issuetype,"
    "fixVersions,versions,issuelinks,attachment,comment",
).strip()


def _jira_configured(client: JiraClient) -> bool:
    has_auth = (client.username and client.password) or (client.email and client.api_token)
    return bool(client.base_url and has_auth)


def _linked_issue_refs(fields: dict) -> list[str]:
    links = fields.get("issuelinks") or []
    if not isinstance(links, list):
        return []
    keys: list[str] = []
    for link in links:
        if not isinstance(link, dict):
            continue
        for direction in ("inwardIssue", "outwardIssue"):
            iss = link.get(direction)
            if isinstance(iss, dict) and iss.get("key"):
                keys.append(str(iss["key"]))
    return list(dict.fromkeys(keys))[:25]


def fetch_issue_bundle(client: JiraClient, issue_key: str) -> dict[str, Any]:
    """Full issue dict, comments list, linked summaries."""
    issue = client.get_issue(issue_key, fields=JIRA_QA_ISSUE_FIELDS)
    comments = client.get_issue_comments(issue_key)
    fields = issue.get("fields") or {}
    linked_summaries: list[dict[str, str]] = []
    if isinstance(fields, dict):
        for lk in _linked_issue_refs(fields):
            try:
                other = client.get_issue(lk, fields="summary,issuetype,status")
                of = other.get("fields") or {}
                linked_summaries.append(
                    {
                        "key": lk,
                        "summary": str(of.get("summary") or "")[:500],
                    }
                )
            except Exception as exc:
                logger.debug_structured("linked_issue_fetch_skipped", extra_fields={"key": lk, "error": str(exc)})
    return {"issue": issue, "comments": comments, "linked_issues": linked_summaries}


def _cmp_jira_updated(a: str | None, b: str | None) -> bool:
    """Return True if ``a`` is newer than ``b`` (lexicographic ok for Jira ISO timestamps)."""
    if not a:
        return False
    if not b:
        return True
    return str(a) > str(b)


def _flush_chunk_rows(
    all_chunk_rows: list[dict[str, Any]],
    *,
    force_reindex: bool,
) -> tuple[int, str | None]:
    """Embed + upsert buffer. Returns (chunk_count, error_message)."""
    if not all_chunk_rows:
        return 0, None
    if force_reindex:
        delete_documents(CHROMA_COLLECTION_JIRA_QA, [r["chunk_id"] for r in all_chunk_rows])
    docs = [r["document"] for r in all_chunk_rows]
    embeddings = embed_texts_batched(docs, batch_size=48)
    if embeddings is None:
        return 0, "Embedding batch failed."
    ids = [r["chunk_id"] for r in all_chunk_rows]
    metas = []
    for r in all_chunk_rows:
        m = dict(r["metadata"])
        clean = {k: v for k, v in m.items() if isinstance(v, (str, int, float, bool))}
        metas.append(clean)
    emb_list = [embeddings[i].tolist() for i in range(len(ids))]
    ok = add_documents(CHROMA_COLLECTION_JIRA_QA, ids, docs, metas, emb_list)
    if not ok:
        return 0, "Chroma upsert failed."
    return len(ids), None


def _persist_jira_qa_sync_state_fields(
    *,
    persist_sync_state: bool,
    state_id: str,
    prior_state: JiraQaIndexSyncState,
    issues_indexed: int,
    errors: list[str],
    max_updated_seen: str | None,
    last_key_ok: str | None,
    successful_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Write sync JSON if enabled. Watermark advances only when at least one issue indexed successfully."""
    sid = (state_id or "").strip()
    if not persist_sync_state or not sid:
        return {}
    recovered = {str(k).strip().upper() for k in (successful_keys or []) if str(k).strip()}
    failed_keys = [
        k
        for k in merge_failed_keys(
            prior_state.failed_keys,
            [e.split(":", 1)[0] for e in errors if ":" in e],
        )
        if str(k).strip().upper() not in recovered
    ]
    new_time = max_updated_seen if issues_indexed > 0 else prior_state.last_successful_sync_time
    new_key = last_key_ok if issues_indexed > 0 else prior_state.last_indexed_jira_key
    new_state = JiraQaIndexSyncState(
        last_successful_sync_time=new_time,
        last_indexed_jira_key=new_key,
        total_indexed=prior_state.total_indexed + issues_indexed,
        failed_keys=failed_keys,
    )
    try:
        save_jira_qa_sync_state(sid, new_state)
        return {"sync_state": new_state.model_dump(mode="json"), "sync_state_id": sid}
    except (OSError, ValueError) as exc:
        logger.warning_structured("jira_qa_sync_state_save_failed", extra_fields={"error": str(exc)})
        return {}


def index_jql_to_chroma(
    jql: str,
    *,
    limit: int | None = None,
    force_reindex: bool = False,
    jira_client: JiraClient | None = None,
    persist_sync_state: bool = False,
    sync_state_id: str | None = None,
) -> dict[str, Any]:
    """Pull issues matching JQL with paged /search, chunk, embed in batches, upsert into Chroma."""
    client = jira_client or JiraClient()
    empty_stats = _index_run_stats(
        lim=None,
        jira_total=0,
        keys_fetched_from_search=0,
        issues_indexed=0,
        issues_failed=0,
        errors=[],
        chunks=0,
    )
    if not _jira_configured(client):
        return {
            "error": "Jira is not configured (JIRA_URL / credentials).",
            **empty_stats,
        }
    if not is_chroma_available():
        return {"error": "ChromaDB is not available.", **empty_stats}
    if not is_embedding_available():
        return {"error": "Embedding model is not available.", **empty_stats}

    lim = _resolve_index_limit(limit)
    run_cap = _max_issues_per_run()
    effective_cap: int | None = lim
    if effective_cap is None:
        effective_cap = run_cap
    elif run_cap is not None:
        effective_cap = min(effective_cap, run_cap)

    page_size = _search_page_size_indexer()
    embed_stride = _issues_per_embed_batch()

    state_id = (sync_state_id or "default").strip() or "default"
    prior_state = load_jira_qa_sync_state(state_id) if persist_sync_state else JiraQaIndexSyncState()

    errors: list[str] = []
    keys_seen: list[str] = []
    issues_indexed = 0
    issues_failed = 0
    total_chunks_upserted = 0
    batch_logs: list[dict[str, Any]] = []

    buffer_rows: list[dict[str, Any]] = []
    buffer_issue_count = 0

    jira_total = 0
    start_at = 0
    batch_num = 0
    max_updated_seen: str | None = prior_state.last_successful_sync_time
    last_key_ok: str | None = prior_state.last_indexed_jira_key
    fetched_run = 0

    while True:
        batch_num += 1
        try:
            page_issues, page_total = _with_retry(
                "jira_search_page",
                lambda: client.search_issues_key_page(jql, start_at=start_at, page_size=page_size),
            )
        except Exception as exc:
            errors.append(f"search:startAt={start_at}: {_format_jira_index_search_error(exc)}")
            logger.warning_structured(
                "jira_qa_index_search_failed",
                extra_fields={"start_at": start_at, "error": str(exc)},
            )
            break

        if jira_total == 0:
            jira_total = page_total

        if not page_issues:
            logger.info_structured(
                "jira_qa_index_batch",
                extra_fields={
                    "batch": batch_num,
                    "start_at": start_at,
                    "fetched": 0,
                    "indexed": 0,
                    "failed": 0,
                    "jira_total": jira_total,
                },
            )
            break

        batch_fetched = len(page_issues)
        batch_indexed = 0
        batch_failed = 0

        for row in page_issues:
            if effective_cap is not None and fetched_run >= effective_cap:
                break
            if not isinstance(row, dict):
                continue
            key = str(row.get("key") or "").strip()
            if not key:
                continue
            fields = row.get("fields") if isinstance(row.get("fields"), dict) else {}
            cand_updated = fields.get("updated")
            cand_s = str(cand_updated) if cand_updated is not None else ""

            fetched_run += 1

            try:
                bundle = _with_retry("fetch_issue_bundle", lambda: fetch_issue_bundle(client, key), jira_key=key)
                issue = bundle["issue"]
                ifull = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
                upd_full = ifull.get("updated")
                upd_s = str(upd_full) if upd_full is not None else cand_s

                enriched = enrich_jira(issue)
                crows = build_jira_qa_chunks(
                    key,
                    issue,
                    comments=bundle["comments"],
                    linked_issues=bundle["linked_issues"],
                    attachment_search_blobs=None,
                    enriched=enriched,
                )
                if JIRA_SQL_ENRICHMENT:
                    db = SessionLocal()
                    try:
                        upsert_jira_issue(db, enriched)
                        insert_jira_chunks(db, key, crows, enrichment=enriched)
                        db.commit()
                    except Exception as sql_exc:
                        db.rollback()
                        logger.warning_structured(
                            "jira_sql_enrichment_persist_failed",
                            extra_fields={"key": key, "error": str(sql_exc)},
                        )
                    finally:
                        db.close()

                if force_reindex and crows:
                    delete_documents(CHROMA_COLLECTION_JIRA_QA, [r["chunk_id"] for r in crows])

                buffer_rows.extend(crows)
                buffer_issue_count += 1
                issues_indexed += 1
                batch_indexed += 1
                keys_seen.append(key)
                last_key_ok = key
                if _cmp_jira_updated(upd_s, max_updated_seen):
                    max_updated_seen = upd_s
            except Exception as exc:
                err = f"{key}: {exc}"
                errors.append(err)
                issues_failed += 1
                batch_failed += 1
                append_jira_index_failure(
                    jira_key=key,
                    error=str(exc),
                    sync_state_id=state_id,
                )
                logger.warning_structured("jira_qa_index_issue_failed", extra_fields={"key": key, "error": str(exc)})

            if buffer_issue_count >= embed_stride:
                n, err = _flush_chunk_rows(buffer_rows, force_reindex=False)
                if err:
                    return {
                        "error": err,
                        **_index_run_stats(
                            lim=lim,
                            jira_total=jira_total,
                            keys_fetched_from_search=fetched_run,
                            issues_indexed=issues_indexed,
                            issues_failed=issues_failed,
                            errors=errors,
                            chunks=total_chunks_upserted,
                        ),
                        "errors": errors[:20],
                        "batch_logs": batch_logs,
                    }
                total_chunks_upserted += n
                buffer_rows.clear()
                buffer_issue_count = 0

            if effective_cap is not None and fetched_run >= effective_cap:
                break

        logger.info_structured(
            "jira_qa_index_batch",
            extra_fields={
                "batch": batch_num,
                "start_at": start_at,
                "fetched": batch_fetched,
                "indexed": batch_indexed,
                "failed": batch_failed,
                "jira_total": jira_total,
            },
        )
        batch_logs.append(
            {
                "batch": int(batch_num),
                "start_at": int(start_at),
                "fetched": int(batch_fetched),
                "indexed": int(batch_indexed),
                "failed": int(batch_failed),
            }
        )

        start_at += batch_fetched
        if start_at >= jira_total:
            break
        if effective_cap is not None and fetched_run >= effective_cap:
            break

    if buffer_rows:
        n, err = _flush_chunk_rows(buffer_rows, force_reindex=False)
        if err:
            return {
                "error": err,
                **_index_run_stats(
                    lim=lim,
                    jira_total=jira_total,
                    keys_fetched_from_search=fetched_run,
                    issues_indexed=issues_indexed,
                    issues_failed=issues_failed,
                    errors=errors,
                    chunks=total_chunks_upserted,
                ),
                "errors": errors[:20],
                "batch_logs": batch_logs,
            }
        total_chunks_upserted += n
        buffer_rows.clear()
        buffer_issue_count = 0

    err_sample = errors[:20]
    base_stats = _index_run_stats(
        lim=lim,
        jira_total=jira_total,
        keys_fetched_from_search=fetched_run,
        issues_indexed=issues_indexed,
        issues_failed=issues_failed,
        errors=errors,
        chunks=total_chunks_upserted,
    )

    sync_extra = _persist_jira_qa_sync_state_fields(
        persist_sync_state=persist_sync_state,
        state_id=state_id,
        prior_state=prior_state,
        issues_indexed=issues_indexed,
        errors=errors,
        max_updated_seen=max_updated_seen,
        last_key_ok=last_key_ok,
        successful_keys=keys_seen,
    )

    if not keys_seen:
        return {
            **base_stats,
            **sync_extra,
            "errors": err_sample,
            "message": "No issues indexed (empty JQL result, search failure, or limit reached before any success).",
            "batch_logs": batch_logs,
        }

    if total_chunks_upserted == 0:
        return {
            **base_stats,
            **sync_extra,
            "errors": err_sample,
            "message": "No chunks produced (check JQL or issue access).",
            "batch_logs": batch_logs,
        }

    out: dict[str, Any] = {
        **base_stats,
        **sync_extra,
        "errors": err_sample,
        "collection": CHROMA_COLLECTION_JIRA_QA,
        "batch_logs": batch_logs,
        "pagination": {
            "page_size": int(page_size),
            "start_at_final": int(start_at),
            "issues_per_embed_batch": int(embed_stride),
        },
    }

    return out


def index_jira_project_backfill(
    project_key: str,
    *,
    limit: int | None = None,
    force_reindex: bool = False,
    jira_client: JiraClient | None = None,
    sync_state_id: str | None = None,
) -> dict[str, Any]:
    """Index ``project = KEY ORDER BY updated ASC`` and persist sync state when ``sync_state_id`` is set."""
    jql = build_backfill_jql(project_key)
    sid = sync_state_id or f"project:{project_key.strip()}"
    return index_jql_to_chroma(
        jql,
        limit=limit,
        force_reindex=force_reindex,
        jira_client=jira_client,
        persist_sync_state=True,
        sync_state_id=sid,
    )


def index_jira_project_incremental(
    project_key: str,
    *,
    limit: int | None = None,
    force_reindex: bool = False,
    jira_client: JiraClient | None = None,
    sync_state_id: str | None = None,
) -> dict[str, Any]:
    """Incremental index using last sync time from state; run backfill first if no state."""
    sid = sync_state_id or f"project:{project_key.strip()}"
    st = load_jira_qa_sync_state(sid)
    if not st.last_successful_sync_time:
        return {
            "error": "No prior sync for this sync_state_id; run backfill first.",
            **_index_run_stats(
                lim=_resolve_index_limit(limit),
                jira_total=0,
                keys_fetched_from_search=0,
                issues_indexed=0,
                issues_failed=0,
                errors=[],
                chunks=0,
            ),
            "sync_state_id": sid,
        }
    jql = build_incremental_jql(project_key, st.last_successful_sync_time)
    return index_jql_to_chroma(
        jql,
        limit=limit,
        force_reindex=force_reindex,
        jira_client=jira_client,
        persist_sync_state=True,
        sync_state_id=sid,
    )


def recover_failed_jira_keys(
    sync_state_id: str,
    *,
    limit: int | None = None,
    force_reindex: bool = True,
    jira_client: JiraClient | None = None,
) -> dict[str, Any]:
    """Retry failed Jira keys captured in persisted sync state."""

    sid = (sync_state_id or "").strip()
    if not sid:
        return {"error": "sync_state_id is required", **_index_run_stats(
            lim=_resolve_index_limit(limit),
            jira_total=0,
            keys_fetched_from_search=0,
            issues_indexed=0,
            issues_failed=0,
            errors=[],
            chunks=0,
        )}
    state = load_jira_qa_sync_state(sid)
    keys = [k.strip().upper() for k in state.failed_keys if str(k).strip()]
    if limit is not None:
        keys = keys[: max(1, int(limit))]
    if not keys:
        return {
            "message": "No failed Jira keys to recover.",
            "sync_state_id": sid,
            **_index_run_stats(
                lim=_resolve_index_limit(limit),
                jira_total=0,
                keys_fetched_from_search=0,
                issues_indexed=0,
                issues_failed=0,
                errors=[],
                chunks=0,
            ),
        }
    quoted = ", ".join(f'"{k}"' for k in keys)
    jql = f"key in ({quoted}) ORDER BY updated ASC"
    logger.info_structured(
        "jira_qa_failed_recovery_start",
        extra_fields={"sync_state_id": sid, "key_count": len(keys), "limit": limit},
    )
    out = index_jql_to_chroma(
        jql,
        limit=len(keys),
        force_reindex=force_reindex,
        jira_client=jira_client,
        persist_sync_state=True,
        sync_state_id=sid,
    )
    out["recovery"] = {"sync_state_id": sid, "requested_failed_keys": keys}
    return out


def delete_jira_key_chunks(jira_key: str, chunk_defs: list[dict] | None = None) -> bool:
    """Delete all chunk ids for a jira key. If chunk_defs not passed, deletes known chunk type slots."""
    from app.services.jira_chunking_service import SMART_JIRA_CHUNK_TYPES

    if chunk_defs:
        ids = [c["chunk_id"] for c in chunk_defs]
        return delete_documents(CHROMA_COLLECTION_JIRA_QA, ids)
    merged_types = CHUNK_TYPES | SMART_JIRA_CHUNK_TYPES
    ids = [f"{jira_key}::{ct}::0" for ct in merged_types]
    for i in range(JIRA_QA_DESCRIPTION_LONG_PART_MAX):
        ids.append(f"{jira_key}::description_long_part::{i}")
    for ct in SMART_JIRA_CHUNK_TYPES:
        for idx in range(1, 6):
            ids.append(f"{jira_key}::{ct}::{idx}")
    return delete_documents(CHROMA_COLLECTION_JIRA_QA, ids)
