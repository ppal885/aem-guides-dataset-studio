"""Bootstrap and inspect Jira incremental-sync cursors from the searchable corpus."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.jira_sync_state import (
    JiraQaIndexSyncState,
    is_jira_issue_key,
    is_valid_sync_state_id,
    load_jira_qa_sync_state,
    merge_failed_keys,
    parse_jira_timestamp,
    save_jira_qa_sync_state,
    sync_cursor_health,
)
from app.services.vector_store_service import (
    CHROMA_COLLECTION_JIRA_QA,
    get_collection_count,
    get_collection_records,
    is_chroma_available,
)


CURSOR_BOOTSTRAP_VERSION = "jira-corpus-cursor-bootstrap-v1"
_PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,29}$")


def _bootstrap_overlap_hours() -> int:
    try:
        configured = int(os.getenv("JIRA_QA_CURSOR_BOOTSTRAP_OVERLAP_HOURS", "24"))
    except ValueError:
        configured = 24
    return max(0, min(configured, 168))


def resolve_sync_project_key(project_key: str | None = None) -> str:
    explicit = str(project_key or "").strip().upper()
    resolved = explicit
    if not resolved:
        for env_name in ("JIRA_QA_RAG_PROJECT_KEY", "JIRA_PROJECT_KEY"):
            configured = str(os.getenv(env_name) or "").strip().upper()
            if configured:
                resolved = configured
                break
    resolved = resolved or "GUIDES"
    if not _PROJECT_KEY_RE.fullmatch(resolved):
        raise ValueError("project_key must match [A-Z][A-Z0-9_]{0,29}")
    return resolved


def _record_jira_key(record: dict[str, Any]) -> str:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    jira_key = str(metadata.get("jira_key") or "").strip().upper()
    if not jira_key:
        record_id = str(record.get("id") or "").strip()
        if "::" in record_id:
            jira_key = record_id.split("::", 1)[0].strip().upper()
    return jira_key


def _project_key_matches(jira_key: str, project_key: str) -> bool:
    return is_jira_issue_key(jira_key) and jira_key.startswith(f"{project_key}-")


def _timestamp_from_metadata(metadata: dict[str, Any]) -> datetime | None:
    return parse_jira_timestamp(
        str(metadata.get("jira_updated_at") or metadata.get("updated_at") or "")
    )


def _percent(count: int, total: int) -> float:
    return round((count / total) * 100, 2) if total else 0.0


def build_corpus_cursor_candidate(
    records: list[dict[str, Any]],
    *,
    project_key: str,
    collection_count: int | None = None,
    sql_updated_by_key: dict[str, Any] | None = None,
    sql_error: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic cursor candidate from a complete Chroma scan."""
    project = resolve_sync_project_key(project_key)
    scanned_count = len(records)
    expected_count = scanned_count if collection_count is None else int(collection_count)
    scan_complete = scanned_count == expected_count
    if not scan_complete:
        return {
            "available": False,
            "candidate_ready": False,
            "project_key": project,
            "scan_complete": False,
            "collection_chunk_count": expected_count,
            "scanned_chunk_count": scanned_count,
            "error": "Partial Chroma scan; refusing to derive an incremental cursor.",
            "sql_error": sql_error,
        }

    project_keys: set[str] = set()
    timestamps: dict[str, datetime] = {}
    timestamp_sources: dict[str, str] = {}
    invalid_timestamp_values: set[str] = set()
    for record in records:
        jira_key = _record_jira_key(record)
        if not _project_key_matches(jira_key, project):
            continue
        project_keys.add(jira_key)
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        raw_timestamp = str(
            metadata.get("jira_updated_at") or metadata.get("updated_at") or ""
        ).strip()
        parsed = _timestamp_from_metadata(metadata)
        if raw_timestamp and parsed is None:
            invalid_timestamp_values.add(raw_timestamp)
        if parsed is not None and (jira_key not in timestamps or parsed > timestamps[jira_key]):
            timestamps[jira_key] = parsed
            timestamp_sources[jira_key] = "chroma_metadata"

    for raw_key, raw_timestamp in (sql_updated_by_key or {}).items():
        jira_key = str(raw_key or "").strip().upper()
        if jira_key not in project_keys:
            continue
        parsed = parse_jira_timestamp(str(raw_timestamp or ""))
        if parsed is not None and (jira_key not in timestamps or parsed > timestamps[jira_key]):
            timestamps[jira_key] = parsed
            timestamp_sources[jira_key] = "sql_jira_updated_at"

    if not project_keys:
        return {
            "available": False,
            "candidate_ready": False,
            "project_key": project,
            "scan_complete": True,
            "collection_chunk_count": expected_count,
            "scanned_chunk_count": scanned_count,
            "error": f"No indexed Jira keys for project {project} were found in jira_qa.",
            "sql_error": sql_error,
        }
    if not timestamps:
        return {
            "available": False,
            "candidate_ready": False,
            "project_key": project,
            "scan_complete": True,
            "collection_chunk_count": expected_count,
            "scanned_chunk_count": scanned_count,
            "unique_project_issue_count": len(project_keys),
            "error": "Indexed Jira records do not contain a valid Jira updated timestamp.",
            "sql_error": sql_error,
        }

    latest_time = max(timestamps.values())
    latest_keys = sorted(key for key, value in timestamps.items() if value == latest_time)
    last_key = latest_keys[-1]
    timestamped_count = len(timestamps)
    return {
        "available": True,
        "candidate_ready": True,
        "project_key": project,
        "scan_complete": True,
        "collection_chunk_count": expected_count,
        "scanned_chunk_count": scanned_count,
        "unique_project_issue_count": len(project_keys),
        "issues_with_valid_updated_at": timestamped_count,
        "issues_missing_valid_updated_at": len(project_keys) - timestamped_count,
        "updated_at_coverage_percent": _percent(timestamped_count, len(project_keys)),
        "invalid_timestamp_value_count": len(invalid_timestamp_values),
        "latest_indexed_jira_updated_at": latest_time.isoformat(),
        "last_indexed_jira_key": last_key,
        "latest_timestamp_source": timestamp_sources.get(last_key, "chroma_metadata"),
        "sql_error": sql_error,
        "historical_backfill_complete": False,
        "note": (
            "This candidate establishes forward freshness tracking from the newest searchable Jira update. "
            "It does not prove that all older Jira history was backfilled."
        ),
    }


def _load_sql_updated_by_key(project_key: str) -> tuple[dict[str, Any], str | None]:
    try:
        from app.db.jira_enrichment_models import JiraEnrichedIssue
        from app.db.session import SessionLocal

        session = SessionLocal()
        try:
            rows = (
                session.query(JiraEnrichedIssue.jira_key, JiraEnrichedIssue.jira_updated_at)
                .filter(JiraEnrichedIssue.jira_key.like(f"{project_key}-%"))
                .all()
            )
            return {
                str(jira_key or "").strip().upper(): updated_at
                for jira_key, updated_at in rows
                if str(jira_key or "").strip()
            }, None
        finally:
            session.close()
    except Exception as exc:
        return {}, str(exc)[:500]


def collect_corpus_cursor_candidate(
    project_key: str,
    *,
    records: list[dict[str, Any]] | None = None,
    collection_count: int | None = None,
    include_sql: bool = True,
) -> dict[str, Any]:
    project = resolve_sync_project_key(project_key)
    if records is None:
        if not is_chroma_available():
            return {
                "available": False,
                "candidate_ready": False,
                "project_key": project,
                "error": "ChromaDB is unavailable.",
            }
        collection_count = get_collection_count(CHROMA_COLLECTION_JIRA_QA)
        records = get_collection_records(CHROMA_COLLECTION_JIRA_QA)
    sql_values, sql_error = _load_sql_updated_by_key(project) if include_sql else ({}, None)
    return build_corpus_cursor_candidate(
        records,
        project_key=project,
        collection_count=collection_count,
        sql_updated_by_key=sql_values,
        sql_error=sql_error,
    )


def inspect_jira_sync_cursor(
    project_key: str | None = None,
    *,
    sync_state_id: str | None = None,
    records: list[dict[str, Any]] | None = None,
    collection_count: int | None = None,
    include_sql: bool = True,
) -> dict[str, Any]:
    project = resolve_sync_project_key(project_key)
    sid = str(sync_state_id or f"project:{project}").strip()
    if not is_valid_sync_state_id(sid):
        return {
            "cursor_version": CURSOR_BOOTSTRAP_VERSION,
            "project_key": project,
            "sync_state_id": sid,
            "valid": False,
            "repair_available": False,
            "error": "sync_state_id must match [a-zA-Z0-9:_-]+",
        }
    state = load_jira_qa_sync_state(sid)
    candidate = collect_corpus_cursor_candidate(
        project,
        records=records,
        collection_count=collection_count,
        include_sql=include_sql,
    )
    health = sync_cursor_health(state, project_key=project)
    return {
        "cursor_version": CURSOR_BOOTSTRAP_VERSION,
        "project_key": project,
        "sync_state_id": sid,
        "valid": bool(health["valid"]),
        "health": health,
        "state": state.model_dump(mode="json"),
        "corpus_candidate": candidate,
        "repair_available": bool(candidate.get("candidate_ready")),
        "repair_command": (
            f"bash scripts/bootstrap_jira_sync_cursor_vm.sh --project {project} --apply"
        ),
    }


def bootstrap_jira_sync_cursor(
    project_key: str | None = None,
    *,
    sync_state_id: str | None = None,
    dry_run: bool = True,
    force: bool = False,
    records: list[dict[str, Any]] | None = None,
    collection_count: int | None = None,
    include_sql: bool = True,
) -> dict[str, Any]:
    """Repair an empty/invalid cursor from indexed Jira timestamps without Jira API access."""
    project = resolve_sync_project_key(project_key)
    sid = str(sync_state_id or f"project:{project}").strip()
    if not is_valid_sync_state_id(sid):
        return {
            "cursor_version": CURSOR_BOOTSTRAP_VERSION,
            "available": False,
            "valid": False,
            "applied": False,
            "dry_run": dry_run,
            "project_key": project,
            "sync_state_id": sid,
            "error": "sync_state_id must match [a-zA-Z0-9:_-]+",
        }
    prior = load_jira_qa_sync_state(sid)
    prior_health = sync_cursor_health(prior, project_key=project)
    if prior_health["valid"] and not force:
        return {
            "cursor_version": CURSOR_BOOTSTRAP_VERSION,
            "available": True,
            "valid": True,
            "applied": False,
            "dry_run": dry_run,
            "project_key": project,
            "sync_state_id": sid,
            "state": prior.model_dump(mode="json"),
            "health": prior_health,
            "message": "Existing incremental sync cursor is already valid; no bootstrap was needed.",
        }

    candidate = collect_corpus_cursor_candidate(
        project,
        records=records,
        collection_count=collection_count,
        include_sql=include_sql,
    )
    if not candidate.get("candidate_ready"):
        return {
            "cursor_version": CURSOR_BOOTSTRAP_VERSION,
            "available": False,
            "valid": False,
            "applied": False,
            "dry_run": dry_run,
            "project_key": project,
            "sync_state_id": sid,
            "prior_state": prior.model_dump(mode="json"),
            "prior_health": prior_health,
            "corpus_candidate": candidate,
            "error": candidate.get("error") or "No safe corpus cursor candidate is available.",
        }

    candidate_time = str(candidate["latest_indexed_jira_updated_at"])
    prior_time = parse_jira_timestamp(prior.last_successful_sync_time)
    candidate_datetime = parse_jira_timestamp(candidate_time)
    overlap_hours = _bootstrap_overlap_hours()
    proposed_time = (
        candidate_datetime - timedelta(hours=overlap_hours)
        if candidate_datetime is not None
        else None
    )
    proposed_key = str(candidate["last_indexed_jira_key"])
    if prior_time is not None and (proposed_time is None or prior_time > proposed_time):
        proposed_time = prior_time
        if prior.last_indexed_jira_key:
            proposed_key = prior.last_indexed_jira_key

    now = datetime.now(timezone.utc).isoformat()
    proposed = JiraQaIndexSyncState(
        last_successful_sync_time=(proposed_time or parse_jira_timestamp(candidate_time)).isoformat(),
        last_indexed_jira_key=proposed_key,
        total_indexed=max(int(prior.total_indexed or 0), int(candidate["unique_project_issue_count"])),
        failed_keys=merge_failed_keys(list(prior.failed_keys or []), []),
        cursor_source="indexed_corpus_bootstrap",
        cursor_bootstrapped_at=prior.cursor_bootstrapped_at or now,
        corpus_issue_count_at_bootstrap=int(candidate["unique_project_issue_count"]),
        corpus_latest_updated_at_at_bootstrap=candidate_time,
        bootstrap_overlap_hours=overlap_hours,
        total_indexed_semantics="distinct_searchable_issues_at_bootstrap",
        historical_backfill_complete=(
            prior.historical_backfill_complete
            if prior.historical_backfill_complete is not None
            else False
        ),
    )
    proposed_health = sync_cursor_health(proposed, project_key=project)
    result = {
        "cursor_version": CURSOR_BOOTSTRAP_VERSION,
        "available": True,
        "valid": bool(proposed_health["valid"]),
        "applied": False,
        "dry_run": dry_run,
        "project_key": project,
        "sync_state_id": sid,
        "prior_state": prior.model_dump(mode="json"),
        "prior_health": prior_health,
        "corpus_candidate": candidate,
        "proposed_state": proposed.model_dump(mode="json"),
        "proposed_health": proposed_health,
        "warnings": [
            "The cursor enables forward incremental freshness tracking only.",
            f"The initial watermark includes a {overlap_hours}-hour overlap to tolerate timezone-naive imports.",
            "historical_backfill_complete remains false until a complete Jira project backfill is verified.",
        ],
    }
    if dry_run:
        result["message"] = "Dry run only; rerun with --apply to persist the proposed cursor."
        return result
    if not proposed_health["valid"]:
        result["available"] = False
        result["error"] = "Proposed cursor failed validation; state was not written."
        return result

    try:
        save_jira_qa_sync_state(sid, proposed)
    except (OSError, ValueError) as exc:
        result.update(
            {
                "available": False,
                "valid": False,
                "error": f"Cursor state could not be persisted: {exc}",
            }
        )
        return result
    persisted = load_jira_qa_sync_state(sid)
    persisted_health = sync_cursor_health(persisted, project_key=project)
    result.update(
        {
            "valid": bool(persisted_health["valid"]),
            "applied": bool(persisted_health["valid"]),
            "state": persisted.model_dump(mode="json"),
            "health": persisted_health,
            "message": "Incremental sync cursor bootstrapped from the searchable Jira corpus.",
        }
    )
    if not persisted_health["valid"]:
        result["available"] = False
        result["error"] = "Cursor state was written but failed read-back validation."
    return result
