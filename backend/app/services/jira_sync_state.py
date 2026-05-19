"""Persist Jira QA index run sync metadata (incremental / backfill)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.storage import get_storage

_SYNC_ID_RE = re.compile(r"^[a-zA-Z0-9:_-]+$")


class JiraQaIndexSyncState(BaseModel):
    """Last successful index snapshot for incremental JQL."""

    model_config = ConfigDict(extra="ignore")

    last_successful_sync_time: str | None = None
    last_indexed_jira_key: str | None = None
    total_indexed: int = 0
    failed_keys: list[str] = Field(default_factory=list)


def _state_path(sync_state_id: str) -> Path:
    if not _SYNC_ID_RE.match((sync_state_id or "").strip()):
        raise ValueError("sync_state_id must match [a-zA-Z0-9:_-]+")
    base = get_storage().base_path / "jira_qa_sync"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{sync_state_id.strip()}.json"


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
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")


def merge_failed_keys(existing: list[str], new_failures: list[str], *, cap: int = 5000) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for k in (existing or []) + (new_failures or []):
        s = str(k).strip()
        if not s or s in seen:
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
