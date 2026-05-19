"""CRUD for chat bulk dataset presets + launch job from preset."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.core.structured_logging import get_structured_logger
from app.db.chat_bulk_preset_models import ChatBulkDatasetPreset
from app.db.session import SessionLocal
from app.jobs import crud

logger = get_structured_logger(__name__)

_LABEL_SANITIZE = re.compile(r"[^\w\s\-]+", re.UNICODE)


def _safe_label(raw: str) -> str:
    s = (raw or "").strip()
    s = _LABEL_SANITIZE.sub("", s).strip()
    return (s[:200] if s else "preset") or "preset"


def save_bulk_preset(
    *,
    user_id: str,
    tenant_id: str,
    label: str,
    job_id: str,
    runner_script_relpath: str | None = None,
    jira_key: str | None = None,
    classification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist job.config for reuse from chat. Upserts on (user_id, tenant_id, label)."""
    uid = (user_id or "chat-user").strip() or "chat-user"
    tid = (tenant_id or "default").strip() or "default"
    jid = (job_id or "").strip()
    if not jid:
        return {"error": "job_id is required to save a bulk preset"}

    session = SessionLocal()
    try:
        job = crud.get_job(session, jid)
        if not job:
            return {"error": f"Job not found: {jid}"}
        if str(job.user_id) != uid:
            return {"error": "You can only save presets from your own jobs"}

        cfg = job.config if isinstance(job.config, dict) else {}
        if not cfg.get("recipes"):
            return {"error": "Job has no recipes in config; nothing to save"}

        lab = _safe_label(label)
        row = (
            session.query(ChatBulkDatasetPreset)
            .filter(
                ChatBulkDatasetPreset.user_id == uid,
                ChatBulkDatasetPreset.tenant_id == tid,
                ChatBulkDatasetPreset.label == lab,
            )
            .first()
        )
        if row:
            row.config = dict(cfg)
            row.source_job_id = jid
            row.updated_at = datetime.utcnow()
            if runner_script_relpath is not None:
                row.runner_script_relpath = (runner_script_relpath or "").strip() or None
            if jira_key is not None:
                jk = (jira_key or "").strip()[:32]
                row.jira_key = jk or None
            if classification is not None:
                row.classification = classification if isinstance(classification, dict) else None
        else:
            row = ChatBulkDatasetPreset(
                user_id=uid,
                tenant_id=tid,
                label=lab,
                source_job_id=jid,
                config=dict(cfg),
            )
            if runner_script_relpath is not None:
                row.runner_script_relpath = (runner_script_relpath or "").strip() or None
            if jira_key is not None:
                jk = (jira_key or "").strip()[:32]
                row.jira_key = jk or None
            if classification is not None:
                row.classification = classification if isinstance(classification, dict) else None
            session.add(row)
        session.commit()
        session.refresh(row)
        return {
            "preset_id": str(row.id),
            "label": lab,
            "source_job_id": jid,
            "runner_script_relpath": getattr(row, "runner_script_relpath", None),
            "jira_key": getattr(row, "jira_key", None),
            "message": f"Saved bulk preset “{lab}”. Say **run bulk preset {lab}** to regenerate or reuse the ZIP.",
        }
    except IntegrityError:
        session.rollback()
        return {"error": "Could not save preset (duplicate or database error)"}
    except Exception as exc:
        session.rollback()
        logger.warning_structured("save_bulk_preset_failed", extra_fields={"error": str(exc)})
        return {"error": str(exc)}
    finally:
        session.close()


def list_bulk_presets(*, user_id: str, tenant_id: str, limit: int = 25) -> dict[str, Any]:
    uid = (user_id or "chat-user").strip() or "chat-user"
    tid = (tenant_id or "default").strip() or "default"
    lim = min(max(limit, 1), 50)
    session = SessionLocal()
    try:
        rows = (
            session.query(ChatBulkDatasetPreset)
            .filter(ChatBulkDatasetPreset.user_id == uid, ChatBulkDatasetPreset.tenant_id == tid)
            .order_by(ChatBulkDatasetPreset.created_at.desc())
            .limit(lim)
            .all()
        )
        presets = [
            {
                "preset_id": str(r.id),
                "label": r.label,
                "source_job_id": r.source_job_id,
                "runner_script_relpath": getattr(r, "runner_script_relpath", None),
                "jira_key": getattr(r, "jira_key", None),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
        return {"presets": presets, "count": len(presets)}
    finally:
        session.close()


def load_preset_for_user(*, user_id: str, tenant_id: str, label_or_id: str) -> dict[str, Any] | None:
    """Return {"preset_id", "label", "config"} or None."""
    uid = (user_id or "chat-user").strip() or "chat-user"
    tid = (tenant_id or "default").strip() or "default"
    key = (label_or_id or "").strip()
    if not key:
        return None
    session = SessionLocal()
    try:
        row = (
            session.query(ChatBulkDatasetPreset)
            .filter(ChatBulkDatasetPreset.user_id == uid, ChatBulkDatasetPreset.tenant_id == tid, ChatBulkDatasetPreset.id == key)
            .first()
        )
        if not row:
            row = (
                session.query(ChatBulkDatasetPreset)
                .filter(ChatBulkDatasetPreset.user_id == uid, ChatBulkDatasetPreset.tenant_id == tid, ChatBulkDatasetPreset.label == key)
                .first()
            )
        if not row:
            return None
        return {
            "preset_id": str(row.id),
            "label": str(row.label),
            "config": dict(row.config) if isinstance(row.config, dict) else {},
            "runner_script_relpath": getattr(row, "runner_script_relpath", None),
            "jira_key": getattr(row, "jira_key", None),
            "classification": row.classification if isinstance(getattr(row, "classification", None), dict) else None,
        }
    finally:
        session.close()


def get_bulk_preset_runner_for_download(
    *,
    user_id: str,
    tenant_id: str,
    preset_id: str,
) -> dict[str, Any]:
    """Return runner script relative path for a preset owned by the user, or ``{"error": ...}``."""
    uid = (user_id or "chat-user").strip() or "chat-user"
    tid = (tenant_id or "default").strip() or "default"
    pid = (preset_id or "").strip()
    if not pid:
        return {"error": "preset_id is required"}
    session = SessionLocal()
    try:
        row = (
            session.query(ChatBulkDatasetPreset)
            .filter(ChatBulkDatasetPreset.user_id == uid, ChatBulkDatasetPreset.tenant_id == tid, ChatBulkDatasetPreset.id == pid)
            .first()
        )
        if not row:
            return {"error": "Preset not found"}
        rel = (getattr(row, "runner_script_relpath", None) or "").strip()
        if not rel:
            return {"error": "No runner script was saved for this preset"}
        return {"runner_script_relpath": rel, "label": str(row.label or "")}
    finally:
        session.close()
