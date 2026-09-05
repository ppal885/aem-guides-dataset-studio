"""Bounded SQL-outbox projection job; never captures, approves or generates UACs."""
from __future__ import annotations

import logging
import time

from sqlalchemy import or_, and_

logger = logging.getLogger(__name__)


def run_shared_learning_publication_job() -> dict:
    """At most ten tenants and twenty events per tick, with per-event leases.

    Exhausted events remain visible in SQL for operator review. The scheduler runs
    this synchronous job in its executor, never on the request event loop.
    """
    from app.db.session import SessionLocal
    from app.db.shared_uac_learning_models import UacLearningOutbox, utcnow
    from app.services.shared_uac_learning_service import drain_learning_outbox

    totals = {"claimed": 0, "indexed": 0, "skipped": 0, "failed": 0}
    deadline = time.monotonic() + 60
    try:
        with SessionLocal() as session:
            now = utcnow()
            tenants = session.query(UacLearningOutbox.tenant_id).filter(
                UacLearningOutbox.attempts < 5,
                UacLearningOutbox.next_attempt_at <= now,
                or_(UacLearningOutbox.status.in_(["PENDING", "FAILED"]),
                    and_(UacLearningOutbox.status == "PROCESSING", UacLearningOutbox.lease_until < now)),
            ).distinct().order_by(UacLearningOutbox.tenant_id).limit(10).all()
        for (tenant_id,) in tenants:
            remaining = deadline - time.monotonic()
            if totals["claimed"] >= 20 or remaining < 1:
                break
            result = drain_learning_outbox(tenant_id=tenant_id, limit=min(5, 20 - totals["claimed"]),
                max_attempts=5, max_duration_seconds=remaining)
            for key in totals:
                totals[key] += result[key]
        return totals
    except Exception as exc:
        # Do not log correction text, SQL parameters, credentials or provider bodies.
        logger.warning("Shared feedback index tick unavailable (%s); SQL outbox retained", type(exc).__name__)
        return {**totals, "status": "UNAVAILABLE", "error_class": type(exc).__name__}
