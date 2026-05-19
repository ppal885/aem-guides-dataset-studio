"""Persist stdlib-only runner scripts (from ``render_jobs_api_python_script``) under storage."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from app.core.structured_logging import get_structured_logger
from app.storage import get_storage
from app.utils.fs_guard import SecurityError, safe_join

logger = get_structured_logger(__name__)


def _safe_segment(s: str, *, max_len: int) -> str:
    t = re.sub(r"[^\w\-.]+", "_", (s or "").strip(), flags=re.UNICODE)
    t = t.strip("._") or "x"
    return t[:max_len]


def persist_cli_script_file(
    *,
    tenant_id: str,
    label: str,
    issue_key: str,
    script_body: str,
) -> str:
    """
    Write UTF-8 ``script_body`` under ``runner_scripts/{tenant}/{label}_{issue}.py``.

    Returns a storage-relative POSIX path (e.g. ``runner_scripts/default/foo_GUIDES_1.py``).
    """
    storage = get_storage()
    base = Path(storage.base_path).resolve()
    tid = _safe_segment(tenant_id, max_len=120)
    lab = _safe_segment(label, max_len=80)
    ik = _safe_segment(issue_key.replace("-", "_"), max_len=40)
    fname = f"{lab}_{ik}_{uuid4().hex[:8]}.py"
    rel = f"runner_scripts/{tid}/{fname}"
    dest = safe_join(base, rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(script_body, encoding="utf-8", newline="\n")
    logger.info_structured("runner_script_persisted", extra_fields={"path": rel})
    return rel.replace("\\", "/")


def read_cli_script_file(*, relative_path: str) -> bytes:
    """Read a previously persisted runner script; raises SecurityError on traversal."""
    storage = get_storage()
    base = Path(storage.base_path).resolve()
    rel = (relative_path or "").strip().lstrip("/")
    if ".." in rel or not rel.startswith("runner_scripts/"):
        raise SecurityError("Invalid runner script path")
    path = safe_join(base, rel)
    return path.read_bytes()
