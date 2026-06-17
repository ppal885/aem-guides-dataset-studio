"""File-backed knowledge-source run state and failure log helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.storage import get_storage

_SOURCE_ID_RE = re.compile(r"^[a-zA-Z0-9:_-]+$")


class KnowledgeSourceState(BaseModel):
    """Persisted health/status for one knowledge source."""

    model_config = ConfigDict(extra="ignore")

    source_id: str
    last_operation: str | None = None
    last_successful_run: str | None = None
    last_error: str | None = None
    failed_item_count: int = 0
    failed_items: list[str] = Field(default_factory=list)
    last_stats: dict[str, Any] = Field(default_factory=dict)


def _state_dir() -> Path:
    base = get_storage().base_path / "knowledge_source_state"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _validate_source_id(source_id: str) -> str:
    source = (source_id or "").strip()
    if not _SOURCE_ID_RE.match(source):
        raise ValueError("source_id must match [a-zA-Z0-9:_-]+")
    return source


def _state_path(source_id: str) -> Path:
    return _state_dir() / f"{_validate_source_id(source_id)}.json"


def _failure_log_path() -> Path:
    return _state_dir() / "failure_log.jsonl"


def load_source_state(source_id: str) -> KnowledgeSourceState:
    path = _state_path(source_id)
    if not path.is_file():
        return KnowledgeSourceState(source_id=_validate_source_id(source_id))
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return KnowledgeSourceState.model_validate(raw)
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return KnowledgeSourceState(source_id=_validate_source_id(source_id))


def save_source_state(state: KnowledgeSourceState) -> None:
    path = _state_path(state.source_id)
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")


def _trim_failed_items(items: list[str], *, cap: int = 50) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text[:500])
        if len(out) >= cap:
            break
    return out


def append_source_failure_log(
    *,
    source_id: str,
    operation: str,
    error: str,
    failed_items: list[str] | None = None,
) -> None:
    try:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "source_id": _validate_source_id(source_id),
            "operation": str(operation or "").strip() or "unknown",
            "error": str(error or "").strip()[:4000],
            "failed_items": _trim_failed_items(list(failed_items or []), cap=25),
        }
        with _failure_log_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        return


def record_source_success(
    *,
    source_id: str,
    operation: str,
    failed_items: list[str] | None = None,
    stats: dict[str, Any] | None = None,
) -> KnowledgeSourceState:
    state = load_source_state(source_id)
    state.last_operation = str(operation or "").strip() or "unknown"
    state.last_successful_run = datetime.now(timezone.utc).isoformat()
    state.last_error = None
    state.failed_items = _trim_failed_items(list(failed_items or []))
    state.failed_item_count = len(state.failed_items)
    state.last_stats = dict(stats or {})
    save_source_state(state)
    return state


def record_source_failure(
    *,
    source_id: str,
    operation: str,
    error: str,
    failed_items: list[str] | None = None,
    stats: dict[str, Any] | None = None,
) -> KnowledgeSourceState:
    state = load_source_state(source_id)
    state.last_operation = str(operation or "").strip() or "unknown"
    state.last_error = str(error or "").strip()[:1000]
    state.failed_items = _trim_failed_items(list(failed_items or []))
    state.failed_item_count = len(state.failed_items)
    state.last_stats = dict(stats or {})
    save_source_state(state)
    append_source_failure_log(
        source_id=source_id,
        operation=operation,
        error=error,
        failed_items=failed_items,
    )
    return state


def read_recent_source_failures(*, limit: int = 50, source_id: str | None = None) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 200))
    path = _failure_log_path()
    if not path.is_file():
        return []
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines[-1000:]:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if source_id and row.get("source_id") != source_id:
            continue
        rows.append(row)
    rows.sort(key=lambda item: str(item.get("ts") or ""), reverse=True)
    return rows[:lim]
