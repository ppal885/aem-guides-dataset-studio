"""On-demand UAC requests: one JSON file per request, shared by the backend API and the release runner.

A caller (the Vision agent, a developer's script, an MCP client) asks the backend for a UAC on a ticket;
the backend only records the request here. The runner's ``--on-demand`` mode picks queued requests up,
generates and checks the UAC exactly as the nightly run does, writes it to Jira, and records the outcome
on the same file, which the API reads back. Nothing here talks to Jira or to Copilot.

Stdlib only: the backend loads this module from the repository checkout, and the runner imports it next
to ``common.py``. Writes are atomic (temp file + rename) so a half-written request is never read.

Statuses: ``queued`` -> ``running`` -> ``posted`` | ``failed`` | ``skipped``. ``skipped`` carries a
``reason`` the caller can act on (``FIELD_KEPT``: the field already had text, read that UAC;
``NOT_REQUIRED``: the ticket carries the not-required label; ``CLOSURE_ASKED``, ``OPS_REQUEST``,
``ALREADY_POSTED``). ``failed`` means the UAC did not pass the runner's checks; nothing was written to Jira.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")
STATUSES = ("queued", "running", "posted", "failed", "skipped")
OPEN_STATUSES = frozenset({"queued", "running"})
REQUEST_ID_RE = re.compile(r"^req_[0-9a-f]{12}$")

# The runner's final state for a ticket -> the request status and the reason a caller sees.
_RUNNER_STATE_TO_STATUS: dict[str, tuple[str, str]] = {
    "POSTED": ("posted", ""),
    "READY": ("posted", "DRY_RUN"),  # dry runs generate and check but write nothing; callers see it as such
    "FIELD_KEPT": ("skipped", "FIELD_KEPT"),
    "NOT_REQUIRED": ("skipped", "NOT_REQUIRED"),
    "CLOSURE_ASKED": ("skipped", "CLOSURE_ASKED"),
    "OPS_REQUEST": ("skipped", "OPS_REQUEST"),
    "WRITTEN_UNRENDERED": ("failed", "WRITTEN_UNRENDERED"),
    "FAILED": ("failed", "CHECKS_FAILED"),
    "ERROR": ("failed", "ERROR"),
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _created_order(row: dict[str, Any]) -> tuple[float, str, str]:
    """Creation order: the float timestamp first (sub-second), then the text time, then the id."""
    try:
        ts = float(row.get("created_ts") or 0.0)
    except (TypeError, ValueError):
        ts = 0.0
    return ts, str(row.get("created_at") or ""), str(row.get("request_id") or "")


def normalize_jira_key(value: str) -> str:
    key = (value or "").strip().upper()
    if not JIRA_KEY_RE.match(key):
        raise ValueError("jira_key must look like PROJECT-123")
    return key


class UacRequestQueue:
    """Directory-backed queue of UAC requests. Safe for one writer per request at a time."""

    def __init__(self, directory: Path | str):
        self.directory = Path(directory)

    # -- storage -------------------------------------------------------------------------------------

    def _path(self, request_id: str) -> Path:
        if not REQUEST_ID_RE.match(request_id or ""):
            raise ValueError("request_id must look like req_0123456789ab")
        return self.directory / f"{request_id}.json"

    def _write(self, request: dict[str, Any]) -> dict[str, Any]:
        self.directory.mkdir(parents=True, exist_ok=True)
        request["updated_at"] = _now()
        target = self._path(request["request_id"])
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(request, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, target)
        return request

    def get(self, request_id: str) -> dict[str, Any] | None:
        path = self._path(request_id)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def list(self, *, jira_key: str | None = None, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Requests newest first, optionally for one ticket or one status."""
        rows: list[dict[str, Any]] = []
        if not self.directory.is_dir():
            return rows
        for path in self.directory.glob("req_*.json"):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if jira_key and row.get("jira_key") != jira_key:
                continue
            if status and row.get("status") != status:
                continue
            rows.append(row)
        rows.sort(key=_created_order, reverse=True)
        return rows[: max(1, int(limit))]

    # -- API side ------------------------------------------------------------------------------------

    def create(self, jira_key: str, *, requested_by: str = "", note: str = "") -> tuple[dict[str, Any], bool]:
        """Record a request for ``jira_key``. Returns ``(request, created)``.

        A ticket with a request still queued or running gets that request back (``created`` False) instead
        of a second one: the runner would skip the duplicate anyway, and the caller wants one id to poll."""
        key = normalize_jira_key(jira_key)
        for row in self.list(jira_key=key, limit=20):
            if row.get("status") in OPEN_STATUSES:
                return row, False
        request = {
            "request_id": "req_" + uuid.uuid4().hex[:12],
            "jira_key": key,
            "requested_by": (requested_by or "").strip()[:120],
            "note": (note or "").strip()[:500],
            "status": "queued",
            "reason": "",
            "created_at": _now(),
            "created_ts": time.time(),
            "run_id": "",
            "runner_state": "",
            "ac_count": None,
            "problems": [],
        }
        return self._write(request), True

    # -- runner side ---------------------------------------------------------------------------------

    def queued(self, *, limit: int = 3) -> list[dict[str, Any]]:
        """Oldest queued requests first, one per ticket."""
        rows = [r for r in self.list(status="queued", limit=1000)]
        rows.sort(key=_created_order)
        picked: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            key = str(row.get("jira_key") or "")
            if key in seen:
                continue
            seen.add(key)
            picked.append(row)
            if len(picked) >= max(1, int(limit)):
                break
        return picked

    def mark_running(self, request_id: str, *, run_id: str) -> dict[str, Any] | None:
        request = self.get(request_id)
        if not request or request.get("status") != "queued":
            return None
        request.update(status="running", run_id=run_id, started_at=_now())
        return self._write(request)

    def finish(self, request_id: str, *, runner_state: str, problems: list[str] | None = None,
               ac_count: int | None = None, error: str = "") -> dict[str, Any] | None:
        """Record the runner's outcome for a request from the ticket's final state."""
        request = self.get(request_id)
        if not request:
            return None
        status, reason = _RUNNER_STATE_TO_STATUS.get(runner_state, ("failed", runner_state or "UNKNOWN"))
        if runner_state == "SKIPPED":
            status, reason = "skipped", "ALREADY_POSTED"
        request.update(status=status, reason=reason, runner_state=runner_state,
                       problems=list(problems or [])[:10], ac_count=ac_count, finished_at=_now())
        if error:
            request["error"] = error[:500]
        return self._write(request)

    def requeue_stale_running(self, *, max_age_seconds: int) -> list[str]:
        """A request left ``running`` by a run that died goes back to ``queued`` once it is old enough."""
        requeued: list[str] = []
        cutoff = time.time() - max_age_seconds
        for row in self.list(status="running", limit=1000):
            path = self._path(row["request_id"])
            try:
                if path.stat().st_mtime > cutoff:
                    continue
            except OSError:
                continue
            row.update(status="queued", run_id="", reason="REQUEUED_AFTER_STALE_RUN")
            self._write(row)
            requeued.append(row["request_id"])
        return requeued


def public_view(request: dict[str, Any]) -> dict[str, Any]:
    """The fields a caller gets back; internal bookkeeping stays out."""
    keys = ("request_id", "jira_key", "requested_by", "note", "status", "reason", "created_at", "updated_at",
            "started_at", "finished_at", "run_id", "runner_state", "ac_count", "problems", "error")
    view = {k: request.get(k) for k in keys if k in request}
    view["poll_url"] = f"/api/v1/uac-requests/{request.get('request_id', '')}"
    return view
