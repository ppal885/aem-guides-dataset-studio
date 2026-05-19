"""CRUD for dataset_artifact_index (content-addressed ZIP reuse)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.core.structured_logging import get_structured_logger
from app.db.dataset_artifact_models import DatasetArtifactIndex
from app.db.session import SessionLocal

logger = get_structured_logger(__name__)


def is_artifact_reuse_enabled() -> bool:
    raw = (os.getenv("ARTIFACT_REUSE_ENABLED") or "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def lookup_completed_artifact(tenant_id: str, artifact_key: str) -> DatasetArtifactIndex | None:
    tid = (tenant_id or "default").strip() or "default"
    key = (artifact_key or "").strip()
    if not key:
        return None
    session = SessionLocal()
    try:
        row = (
            session.query(DatasetArtifactIndex)
            .filter(
                DatasetArtifactIndex.tenant_id == tid,
                DatasetArtifactIndex.artifact_key == key,
                DatasetArtifactIndex.status == "completed",
            )
            .first()
        )
        return row
    finally:
        session.close()


def record_artifact_hit(tenant_id: str, artifact_key: str) -> None:
    tid = (tenant_id or "default").strip() or "default"
    key = (artifact_key or "").strip()
    if not key:
        return
    session = SessionLocal()
    try:
        row = (
            session.query(DatasetArtifactIndex)
            .filter(
                DatasetArtifactIndex.tenant_id == tid,
                DatasetArtifactIndex.artifact_key == key,
            )
            .first()
        )
        if row:
            row.hit_count = int(row.hit_count or 0) + 1
            row.last_hit_at = datetime.utcnow()
            session.commit()
    except Exception as exc:
        session.rollback()
        logger.warning_structured(
            "record_artifact_hit_failed",
            extra_fields={"tenant_id": tid, "error": str(exc)},
        )
    finally:
        session.close()


def _recipe_summary_blob(normalized_config: dict[str, Any]) -> str:
    recipes = normalized_config.get("recipes") or []
    types: list[str] = []
    if isinstance(recipes, list):
        for r in recipes:
            if isinstance(r, dict) and r.get("type"):
                types.append(str(r["type"]))
    return json.dumps({"name": normalized_config.get("name"), "recipe_types": types}, sort_keys=True)[:4000]


def register_completed_dataset_artifact(
    tenant_id: str,
    artifact_key: str,
    source_job_id: str,
    user_id: str,
    normalized_config: dict[str, Any],
) -> None:
    """Upsert registry row for a successfully completed canonical job."""
    tid = (tenant_id or "default").strip() or "default"
    key = (artifact_key or "").strip()
    jid = (source_job_id or "").strip()
    if not key or not jid:
        return
    summary = _recipe_summary_blob(normalized_config)
    session = SessionLocal()
    try:
        row = (
            session.query(DatasetArtifactIndex)
            .filter(
                DatasetArtifactIndex.tenant_id == tid,
                DatasetArtifactIndex.artifact_key == key,
            )
            .first()
        )
        if row:
            row.source_job_id = jid
            row.created_by_user_id = (user_id or "unknown").strip()
            row.recipe_summary = summary
            row.status = "completed"
        else:
            row = DatasetArtifactIndex(
                id=str(uuid.uuid4()),
                tenant_id=tid,
                artifact_key=key,
                source_job_id=jid,
                created_by_user_id=(user_id or "unknown").strip(),
                recipe_summary=summary,
                status="completed",
                hit_count=0,
                last_hit_at=None,
            )
            session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            row2 = (
                session.query(DatasetArtifactIndex)
                .filter(
                    DatasetArtifactIndex.tenant_id == tid,
                    DatasetArtifactIndex.artifact_key == key,
                )
                .first()
            )
            if row2:
                row2.source_job_id = jid
                row2.created_by_user_id = (user_id or "unknown").strip()
                row2.recipe_summary = summary
                row2.status = "completed"
                session.commit()
    except Exception as exc:
        session.rollback()
        logger.warning_structured(
            "register_completed_dataset_artifact_failed",
            extra_fields={"tenant_id": tid, "job_id": jid, "error": str(exc)},
        )
    finally:
        session.close()
