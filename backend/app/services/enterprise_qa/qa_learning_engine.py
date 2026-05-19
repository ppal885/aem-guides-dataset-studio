"""Append-only learning log for future scoring tuning (JSONL under storage)."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

from app.storage import get_storage

_LOCK = Lock()


def _path() -> Path:
    base = get_storage().base_path / "qa_learning"
    base.mkdir(parents=True, exist_ok=True)
    return base / "feedback.jsonl"


def record_feedback(event_type: str, payload: dict[str, Any]) -> None:
    row = {"event_type": event_type, "payload": payload}
    line = json.dumps(row, ensure_ascii=False)[:8000]
    with _LOCK:
        with _path().open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def recent_hints(*, limit_lines: int = 80) -> list[str]:
    p = _path()
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit_lines:]
    hints: list[str] = []
    for line in lines:
        try:
            o = json.loads(line)
            et = o.get("event_type")
            if et == "production_escape":
                hints.append("Past production escape — increase regression breadth for similar components.")
            elif et == "flaky_history":
                hints.append("Historical flake — prefer API contracts over UI timing for this area.")
        except json.JSONDecodeError:
            continue
    return hints[-10:]


def clear_learning_store_for_tests() -> None:
    p = _path()
    if p.exists():
        p.unlink()
