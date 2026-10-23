"""Record and read on-demand UAC requests for the release runner.

The backend never generates or posts a UAC itself: a request is a JSON file in the directory the runner's
``--on-demand`` mode watches (``scripts/uac_release/uac_request_queue.py``). The runner generates the UAC
with every check of the nightly run, writes it to the ticket, and records the outcome on the same file.
``UAC_REQUESTS_DIR`` must point at the runner's ``<output_dir>/requests`` on the VM.
"""
from __future__ import annotations

import importlib.util
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_QUEUE_MODULE = _REPO_ROOT / "scripts" / "uac_release" / "uac_request_queue.py"
_DEFAULT_DIR = _REPO_ROOT / "output" / "uac_requests"


@lru_cache(maxsize=1)
def _queue_module():
    spec = importlib.util.spec_from_file_location("uac_request_queue", _QUEUE_MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"UAC request queue module not found: {_QUEUE_MODULE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def requests_dir() -> Path:
    return Path(os.getenv("UAC_REQUESTS_DIR", "").strip() or _DEFAULT_DIR)


def _queue():
    return _queue_module().UacRequestQueue(requests_dir())


def create_request(jira_key: str, *, requested_by: str = "", note: str = "") -> tuple[dict[str, Any], bool]:
    """Queue a UAC request. Returns ``(public_view, created)``; an open request for the ticket is reused."""
    module = _queue_module()
    request, created = _queue().create(jira_key, requested_by=requested_by, note=note)
    logger.info_structured(
        "uac_request_created" if created else "uac_request_reused",
        extra_fields={"request_id": request["request_id"], "jira_key": request["jira_key"],
                      "requested_by": request.get("requested_by") or ""},
    )
    return module.public_view(request), created


def get_request(request_id: str) -> dict[str, Any] | None:
    module = _queue_module()
    try:
        request = _queue().get(request_id)
    except ValueError:
        return None
    return module.public_view(request) if request else None


def list_requests(*, jira_key: str | None = None, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    module = _queue_module()
    key = module.normalize_jira_key(jira_key) if jira_key else None
    return [module.public_view(r) for r in _queue().list(jira_key=key, status=status, limit=limit)]


def valid_statuses() -> tuple[str, ...]:
    return tuple(_queue_module().STATUSES)
