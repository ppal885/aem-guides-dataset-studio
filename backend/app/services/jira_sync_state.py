"""Persist Jira QA index run sync metadata (incremental / backfill)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.storage import get_storage

_SYNC_ID_RE = re.compile(r"^[a-zA-Z0-9:_-]+$")
_JIRA_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*-[0-9]+$")
SYNC_CURSOR_SCHEMA_VERSION = "jira-sync-cursor-v2"


class JiraQaIndexSyncState(BaseModel):
    """Last successful index snapshot for incremental JQL."""

    model_config = ConfigDict(extra="ignore")

    last_successful_sync_time: str | None = None
    last_indexed_jira_key: str | None = None
    total_indexed: int = 0
    failed_keys: list[str] = Field(default_factory=list)
    cursor_schema_version: str = SYNC_CURSOR_SCHEMA_VERSION
    cursor_source: str = "uninitialized"
    cursor_bootstrapped_at: str | None = None
    corpus_issue_count_at_bootstrap: int = 0
    corpus_latest_updated_at_at_bootstrap: str | None = None
    bootstrap_overlap_hours: int = 0
    total_indexed_semantics: str = "cumulative_successful_index_operations"
    historical_backfill_complete: bool | None = None


def parse_jira_timestamp(value: str | None) -> datetime | None:
    """Parse Jira API, Jira CSV, and stored ISO timestamps as UTC."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
        for date_format in (
            "%d/%b/%y %I:%M %p",
            "%d/%b/%y %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ):
            try:
                parsed = datetime.strptime(raw, date_format)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_jira_timestamp(value: str | None) -> str | None:
    parsed = parse_jira_timestamp(value)
    return parsed.isoformat() if parsed is not None else None


def is_jira_issue_key(value: str | None) -> bool:
    return bool(_JIRA_ISSUE_KEY_RE.fullmatch(str(value or "").strip().upper()))


def sync_cursor_health(
    state: JiraQaIndexSyncState,
    *,
    project_key: str | None = None,
) -> dict[str, object]:
    """Return deterministic cursor validity and missing/invalid fields."""
    missing: list[str] = []
    timestamp = normalize_jira_timestamp(getattr(state, "last_successful_sync_time", None))
    if timestamp is None:
        missing.append("last_successful_sync_time")
    jira_key = str(getattr(state, "last_indexed_jira_key", None) or "").strip().upper()
    if not jira_key:
        missing.append("last_indexed_jira_key")
    elif not is_jira_issue_key(jira_key):
        missing.append("last_indexed_jira_key_format")
    project = str(project_key or "").strip().upper()
    if jira_key and project and not jira_key.startswith(f"{project}-"):
        missing.append("last_indexed_jira_key_project_mismatch")
    if int(getattr(state, "total_indexed", 0) or 0) <= 0:
        missing.append("total_indexed")
    return {
        "valid": not missing,
        "missing_or_invalid_fields": missing,
        "normalized_sync_time": timestamp,
        "project_key": project or None,
        "cursor_source": getattr(state, "cursor_source", "uninitialized"),
        "historical_backfill_complete": getattr(state, "historical_backfill_complete", None),
    }


def has_valid_sync_cursor(state: JiraQaIndexSyncState, *, project_key: str | None = None) -> bool:
    return bool(sync_cursor_health(state, project_key=project_key)["valid"])


def _state_path(sync_state_id: str) -> Path:
    if not _SYNC_ID_RE.match((sync_state_id or "").strip()):
        raise ValueError("sync_state_id must match [a-zA-Z0-9:_-]+")
    base = get_storage().base_path / "jira_qa_sync"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{sync_state_id.strip()}.json"


def is_valid_sync_state_id(sync_state_id: str | None) -> bool:
    return bool(_SYNC_ID_RE.fullmatch(str(sync_state_id or "").strip()))


def load_jira_qa_sync_state(sync_state_id: str) -> JiraQaIndexSyncState:
    try:
        path = _state_path(sync_state_id)
    except ValueError:
        return JiraQaIndexSyncState()
    if not path.is_file():
        return JiraQaIndexSyncState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return JiraQaIndexSyncState.model_validate(raw)
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return JiraQaIndexSyncState()


def save_jira_qa_sync_state(sync_state_id: str, state: JiraQaIndexSyncState) -> None:
    path = _state_path(sync_state_id)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def merge_failed_keys(existing: list[str], new_failures: list[str], *, cap: int = 5000) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for k in (existing or []) + (new_failures or []):
        s = str(k).strip().upper()
        if not is_jira_issue_key(s) or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= cap:
            break
    return out


def build_backfill_jql(project_key: str) -> str:
    pk = (project_key or "").strip()
    if not pk:
        raise ValueError("project_key is required")
    return f"project = {pk} ORDER BY updated ASC"


def build_incremental_jql(project_key: str, last_sync_iso: str) -> str:
    pk = (project_key or "").strip()
    if not pk:
        raise ValueError("project_key is required")
    bound = (last_sync_iso or "").strip()
    if not bound:
        raise ValueError("last_sync_iso is required for incremental JQL")
    jq_bound = _jql_datetime_bound(bound)
    return f'project = {pk} AND updated >= "{jq_bound}" ORDER BY updated ASC'


def _jql_datetime_bound(iso_ts: str) -> str:
    """Convert an ISO timestamp to JQL-friendly ``yyyy-MM-dd HH:mm`` in UTC."""
    from datetime import datetime, timezone

    s = iso_ts.strip().replace("Z", "+00:00")
    if not s:
        return s
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            dt = dt.replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        pass
    if "T" in iso_ts:
        return iso_ts[:16].replace("T", " ")
    return iso_ts[:16]
