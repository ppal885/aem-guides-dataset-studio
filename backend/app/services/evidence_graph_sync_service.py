"""Durable incremental synchronization and full reconciliation for the evidence graph."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
import os
from typing import Any

from sqlalchemy import or_

from app.db.evidence_graph_models import (
    EvidenceGraphGeneration,
    EvidenceGraphSourceEvent,
    EvidenceGraphSyncRun,
)
from app.db.session import SessionLocal
from app.services.evidence_graph_build_service import (
    rebuild_evidence_graph,
    upsert_dita_record_into_generation,
    upsert_document_chunk_into_generation,
    upsert_jira_issue_into_generation,
)
from app.services.evidence_graph_contract import normalize_text, sanitize_excerpt
from app.services.evidence_graph_store import (
    acquire_graph_lease,
    active_generation,
    audit_generation,
    clone_generation,
    create_generation,
    create_sync_run,
    promote_generation,
    release_graph_lease,
    remove_source_record,
    renew_graph_lease,
    update_source_checkpoint,
)


SOURCE_KINDS = frozenset({"jira", "docs", "dita"})
ASSERTION_KINDS = {
    "jira": ("jira_enriched", "jira_chunk", "jira_chroma"),
    "docs": ("aem_guides_chroma",),
    "dita": ("dita_spec_sql", "dita_spec_chroma"),
}


def _safe_error(exc: Exception | str) -> str:
    value = f"{type(exc).__name__}: {exc}" if isinstance(exc, Exception) else str(exc)
    return sanitize_excerpt(value, max_chars=1000)[0]


def _enabled() -> bool:
    return os.getenv("EVIDENCE_GRAPH_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _retry_event(event: EvidenceGraphSourceEvent, error: str, *, max_retries: int) -> None:
    event.attempts = int(event.attempts or 0) + 1
    event.last_error = _safe_error(error)
    event.completed_at = None
    if event.attempts >= max_retries:
        event.status = "failed"
        event.next_attempt_at = None
    else:
        event.status = "retry"
        event.next_attempt_at = datetime.utcnow() + timedelta(minutes=min(60, 2 ** event.attempts))


def _complete_event(event: EvidenceGraphSourceEvent) -> None:
    event.status = "completed"
    event.last_error = None
    event.next_attempt_at = None
    event.completed_at = datetime.utcnow()


def _pending_events(session, limit: int) -> list[EvidenceGraphSourceEvent]:
    now = datetime.utcnow()
    return (
        session.query(EvidenceGraphSourceEvent)
        .filter(
            EvidenceGraphSourceEvent.status.in_(("pending", "retry")),
            or_(
                EvidenceGraphSourceEvent.next_attempt_at.is_(None),
                EvidenceGraphSourceEvent.next_attempt_at <= now,
            ),
        )
        .order_by(EvidenceGraphSourceEvent.created_at.asc(), EvidenceGraphSourceEvent.id.asc())
        .limit(max(1, min(int(limit or 500), 5000)))
        .all()
    )


def _coalesced_events(events: list[EvidenceGraphSourceEvent]) -> list[EvidenceGraphSourceEvent]:
    latest: dict[tuple[str, str], EvidenceGraphSourceEvent] = {}
    for event in events:
        key = (event.source_kind, event.source_record_id)
        current = latest.get(key)
        if current is None or (event.created_at, event.id) >= (current.created_at, current.id):
            latest[key] = event
    return [latest[key] for key in sorted(latest)]


def _apply_event(session, writer, event: EvidenceGraphSourceEvent) -> dict[str, Any]:
    source_kind = normalize_text(event.source_kind).casefold()
    if source_kind not in SOURCE_KINDS:
        raise ValueError(f"Unsupported evidence graph event source: {event.source_kind}")
    record_id = normalize_text(event.source_record_id)
    if not record_id:
        raise ValueError("Evidence graph event source_record_id is empty.")
    if record_id == "*":
        raise RuntimeError(f"{source_kind} requested full reconciliation")
    assertion_kinds = ASSERTION_KINDS[source_kind]
    if source_kind == "dita":
        assertion_kinds = (
            ("dita_spec_sql",)
            if record_id.startswith("sql:")
            else ("dita_spec_chroma",)
        )
    removal = remove_source_record(
        session,
        generation_id=writer.generation_id,
        source_record_id=record_id.removeprefix("sql:") if source_kind == "dita" else record_id,
        source_kinds=assertion_kinds,
    )
    if event.event_type == "delete" and source_kind != "jira":
        return {"source": source_kind, "record_id": record_id, "deleted": True, **removal}
    if source_kind == "jira":
        upsert = upsert_jira_issue_into_generation(session, writer, record_id)
    elif source_kind == "docs":
        upsert = upsert_document_chunk_into_generation(session, writer, record_id)
    else:
        upsert = upsert_dita_record_into_generation(session, writer, record_id)
    if not upsert.get("found"):
        return {"source": source_kind, "record_id": record_id, "deleted": True, **removal, **upsert}
    return {"source": source_kind, "record_id": record_id, **removal, **upsert}


def drain_evidence_graph_events(
    *,
    max_events: int = 500,
    max_retries: int = 5,
    batch_size: int = 500,
    created_by: str = "scheduler",
) -> dict[str, Any]:
    """Apply queued source mutations to a cloned generation, then audit and atomically promote it."""
    if not _enabled():
        return {"available": False, "success": False, "status": "disabled", "events": 0}
    session = SessionLocal()
    owner = None
    generation: EvidenceGraphGeneration | None = None
    sync_run: EvidenceGraphSyncRun | None = None
    selected_events: list[EvidenceGraphSourceEvent] = []
    try:
        owner = acquire_graph_lease(session, seconds=900)
        if owner is None:
            return {"available": True, "success": True, "status": "lease_held", "events": 0}
        selected_events = _pending_events(session, max_events)
        if not selected_events:
            failed_events = session.query(EvidenceGraphSourceEvent).filter(
                EvidenceGraphSourceEvent.status == "failed"
            ).count()
            if failed_events:
                return {
                    "available": True,
                    "success": False,
                    "status": "failed_events_pending",
                    "events": 0,
                    "failed_events": failed_events,
                    "error": "One or more evidence graph source events exhausted retries and require reindex/requeue.",
                }
            return {"available": True, "success": True, "status": "idle", "events": 0}
        base = active_generation(session)
        if base is None:
            raise RuntimeError("No active graph generation exists; run a full rebuild first.")
        coalesced = _coalesced_events(selected_events)
        if any(event.source_record_id == "*" for event in coalesced):
            raise RuntimeError("A source requested full reconciliation.")

        generation = create_generation(
            session,
            mode="incremental",
            created_by=created_by,
            source_snapshot={
                "base_generation_id": base.id,
                "event_ids": [event.id for event in selected_events],
                "coalesced_records": len(coalesced),
            },
        )
        sync_run = create_sync_run(
            session,
            mode="incremental",
            sources=sorted({event.source_kind for event in coalesced}),
            dry_run=False,
            generation_id=generation.id,
        )
        session.commit()
        writer, clone_counts = clone_generation(
            session,
            source_generation_id=base.id,
            target_generation_id=generation.id,
            batch_size=batch_size,
        )
        session.commit()
        if not renew_graph_lease(session, owner, seconds=900):
            raise RuntimeError("Evidence graph synchronization lease was lost after generation clone.")
        applied = []
        heartbeat_every = max(1, min(25, len(coalesced)))
        for index, event in enumerate(coalesced, 1):
            applied.append(_apply_event(session, writer, event))
            if index % heartbeat_every == 0:
                session.commit()
                if not renew_graph_lease(session, owner, seconds=900):
                    raise RuntimeError(
                        "Evidence graph synchronization lease was lost while applying source events."
                    )
        session.commit()
        if not renew_graph_lease(session, owner, seconds=900):
            raise RuntimeError("Evidence graph synchronization lease was lost before generation audit.")
        audit = audit_generation(session, generation.id)
        if not audit.get("valid"):
            raise RuntimeError("Incremental generation audit failed: " + "; ".join(audit.get("errors") or []))
        generation.status = "ready"
        generation.completed_at = datetime.utcnow()
        generation.counts = audit.get("counts") or {}
        session.flush()
        if not renew_graph_lease(session, owner, seconds=900):
            raise RuntimeError("Evidence graph synchronization lease was lost before promotion.")
        promote_generation(session, generation.id)
        for source_kind in sorted({event.source_kind for event in coalesced}):
            update_source_checkpoint(
                session,
                source_name=f"evidence_graph:{source_kind}",
                generation_id=generation.id,
                counts={"events": sum(1 for event in coalesced if event.source_kind == source_kind)},
                cursor={"mode": "incremental", "completed_at": datetime.utcnow().isoformat()},
            )
        selected_ids = {event.id for event in selected_events}
        for event in selected_events:
            if event.id in selected_ids:
                _complete_event(event)
        sync_run.status = "succeeded"
        sync_run.counters = {
            "events_selected": len(selected_events),
            "records_applied": len(applied),
            "clone": clone_counts,
            "audit": audit.get("counts") or {},
        }
        sync_run.completed_at = datetime.utcnow()
        session.commit()
        return {
            "available": True,
            "success": True,
            "status": "succeeded",
            "generation_id": generation.id,
            "base_generation_id": base.id,
            "events": len(selected_events),
            "records_applied": len(applied),
            "applied": applied,
            "audit": audit,
        }
    except Exception as exc:
        session.rollback()
        error = _safe_error(exc)
        if generation is not None:
            row = session.get(EvidenceGraphGeneration, generation.id)
            if row is not None:
                row.status = "failed"
                row.errors = [error]
                row.completed_at = datetime.utcnow()
        if sync_run is not None:
            row = session.get(EvidenceGraphSyncRun, sync_run.id)
            if row is not None:
                row.status = "failed"
                row.errors = [error]
                row.completed_at = datetime.utcnow()
        for selected in selected_events:
            row = session.get(EvidenceGraphSourceEvent, selected.id)
            if row is not None:
                _retry_event(row, error, max_retries=max(1, int(max_retries or 5)))
        session.commit()
        return {
            "available": True,
            "success": False,
            "status": "failed",
            "events": len(selected_events),
            "generation_id": generation.id if generation else None,
            "error": error,
        }
    finally:
        if owner:
            release_graph_lease(session, owner)
        session.close()


def reconcile_evidence_graph(
    *,
    dry_run: bool = False,
    batch_size: int = 500,
    created_by: str = "nightly-reconciliation",
) -> dict[str, Any]:
    """Run a leased full reconciliation and acknowledge events only after successful promotion."""
    session = SessionLocal()
    owner = None
    event_cutoff = datetime.utcnow()
    try:
        owner = acquire_graph_lease(session, seconds=1800)
        if owner is None:
            return {"available": True, "valid": True, "status": "lease_held", "promoted": False}
    finally:
        session.close()
    try:
        result = rebuild_evidence_graph(
            dry_run=dry_run,
            batch_size=batch_size,
            created_by=created_by,
            _lease_owner=owner,
        )
        if result.get("valid") and (dry_run or result.get("promoted")):
            acknowledge = SessionLocal()
            try:
                if not dry_run:
                    for event in acknowledge.query(EvidenceGraphSourceEvent).filter(
                        EvidenceGraphSourceEvent.status.in_(("pending", "retry", "failed")),
                        EvidenceGraphSourceEvent.created_at <= event_cutoff,
                    ):
                        _complete_event(event)
                    acknowledge.commit()
            finally:
                acknowledge.close()
        return result
    finally:
        release = SessionLocal()
        try:
            if owner:
                release_graph_lease(release, owner)
        finally:
            release.close()
