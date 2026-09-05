"""Deterministic, privacy-safe test-plan quality feedback contracts."""

from __future__ import annotations

from collections import Counter
from datetime import timezone
import hashlib
import hmac
import json
import os
import re
import uuid
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.test_plan_feedback_models import TestPlanQualityFeedback
from app.services.evidence_graph_contract import normalize_text, sanitize_excerpt


FEEDBACK_CONTRACT_VERSION = "test-plan-quality-feedback-v1"
SUMMARY_CONTRACT_VERSION = "test-plan-quality-summary-v1"
EVENT_TYPES = frozenset(
    {"review_decision", "ac_edit", "execution_outcome", "escaped_defect"}
)
REVIEW_DECISIONS = frozenset({"QE_APPROVED", "QE_CHANGES_REQUESTED", "REJECTED"})
EXECUTION_OUTCOMES = frozenset({"PASS", "FAIL", "BLOCKED", "SKIPPED"})
JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
HEX64_RE = re.compile(r"^[a-f0-9]{64}$")
EVIDENCE_SNAPSHOT_RE = re.compile(r"^(?:bundle:[a-f0-9]{64}|evidence:[A-Z][A-Z0-9]+-\d+:[a-f0-9]{64})$")

PAYLOAD_ALLOWLIST = {
    "review_decision": frozenset(
        {"reason_codes", "sections_changed", "review_status", "comment_category"}
    ),
    "ac_edit": frozenset(
        {"changed_fields", "reason_codes", "human_accepted", "source_clause_id"}
    ),
    "execution_outcome": frozenset(
        {
            "environment",
            "build",
            "output_type",
            "duration_ms",
            "failure_category",
            "automation_run_id",
            "test_case_id",
            "release_channel",
        }
    ),
    "escaped_defect": frozenset(
        {
            "escaped_jira_key",
            "severity",
            "component",
            "output_type",
            "root_cause_category",
            "detected_stage",
            "release",
        }
    ),
}


def _normalize_jira_key(value: Any, *, field: str = "jira_key") -> str:
    key = normalize_text(value).upper()
    if not JIRA_KEY_RE.fullmatch(key):
        raise ValueError(f"{field} must be a Jira key such as GUIDES-12345.")
    return key


def _normalize_hex64(value: Any, *, field: str, required: bool = False) -> str:
    text = normalize_text(value).casefold()
    if not text and not required:
        return ""
    if not HEX64_RE.fullmatch(text):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest.")
    return text


def _actor_hash(actor_id: str) -> str:
    secret = (
        os.getenv("TEST_PLAN_FEEDBACK_HASH_KEY")
        or os.getenv("EVIDENCE_GRAPH_AUDIT_HASH_KEY")
        or os.getenv("TENANT_SECRET_KEY")
        or os.getenv("SECRET_KEY")
        or "local-development-only"
    )
    return hmac.new(
        secret.encode("utf-8", errors="strict"),
        normalize_text(actor_id or "system").encode("utf-8", errors="strict"),
        hashlib.sha256,
    ).hexdigest()


def _sanitize_payload(event_type: str, payload: dict[str, Any] | None) -> tuple[dict[str, Any], int]:
    allowed = PAYLOAD_ALLOWLIST[event_type]
    clean: dict[str, Any] = {}
    redactions = 0
    for key in sorted(allowed):
        value = (payload or {}).get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, bool):
            clean[key] = value
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            clean[key] = max(0, min(value, 86_400_000)) if key == "duration_ms" else value
            continue
        if isinstance(value, list):
            items = []
            for item in value[:30]:
                text, count = sanitize_excerpt(item, max_chars=160)
                redactions += count
                if text:
                    items.append(text)
            if items:
                clean[key] = list(dict.fromkeys(items))
            continue
        if isinstance(value, dict):
            continue
        text, count = sanitize_excerpt(value, max_chars=240)
        redactions += count
        if text:
            clean[key] = text
    return clean, redactions


def _validate_event_contract(
    *,
    event_type: str,
    ac_id: str,
    ac_fingerprint: str,
    decision: str,
    outcome: str,
    before_hash: str,
    after_hash: str,
    payload: dict[str, Any],
) -> None:
    if event_type == "review_decision":
        if decision not in REVIEW_DECISIONS:
            raise ValueError("review_decision requires QE_APPROVED, QE_CHANGES_REQUESTED, or REJECTED.")
        return
    if event_type == "ac_edit":
        if not ac_id or not ac_fingerprint or not before_hash or not after_hash:
            raise ValueError("ac_edit requires ac_id, ac_fingerprint, before_hash, and after_hash.")
        if before_hash == after_hash:
            raise ValueError("ac_edit before_hash and after_hash must differ.")
        return
    if event_type == "execution_outcome":
        if outcome not in EXECUTION_OUTCOMES:
            raise ValueError("execution_outcome requires PASS, FAIL, BLOCKED, or SKIPPED.")
        if not ac_id or not ac_fingerprint:
            raise ValueError("execution_outcome requires ac_id and ac_fingerprint.")
        return
    escaped_key = normalize_text(payload.get("escaped_jira_key")).upper()
    if not JIRA_KEY_RE.fullmatch(escaped_key):
        raise ValueError("escaped_defect requires payload.escaped_jira_key.")
    if not normalize_text(payload.get("severity")):
        raise ValueError("escaped_defect requires payload.severity.")


def _serialize(row: TestPlanQualityFeedback) -> dict[str, Any]:
    created_at = row.created_at
    if created_at and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return {
        "contract_version": FEEDBACK_CONTRACT_VERSION,
        "id": row.id,
        "tenant_id": row.tenant_id,
        "jira_key": row.jira_key,
        "correlation_id": row.correlation_id or "",
        "plan_fingerprint": row.plan_fingerprint,
        "evidence_snapshot_id": row.evidence_snapshot_id,
        "event_type": row.event_type,
        "ac_id": row.ac_id or "",
        "ac_fingerprint": row.ac_fingerprint or "",
        "decision": row.decision or "",
        "outcome": row.outcome or "",
        "before_hash": row.before_hash or "",
        "after_hash": row.after_hash or "",
        "payload": dict(row.payload or {}),
        "redaction_count": int(row.redaction_count or 0),
        "created_at": created_at.isoformat() if created_at else None,
    }


def record_test_plan_feedback(
    session: Session,
    *,
    tenant_id: str,
    jira_key: str,
    correlation_id: str,
    plan_fingerprint: str,
    evidence_snapshot_id: str,
    event_type: str,
    actor_id: str,
    ac_id: str = "",
    ac_fingerprint: str = "",
    decision: str = "",
    outcome: str = "",
    before_hash: str = "",
    after_hash: str = "",
    payload: dict[str, Any] | None = None,
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Append one immutable event and deduplicate safe client retries."""
    normalized_event = normalize_text(event_type).casefold().replace("-", "_")
    if normalized_event not in EVENT_TYPES:
        raise ValueError(f"Unsupported feedback event_type: {event_type}")
    normalized_jira = _normalize_jira_key(jira_key)
    normalized_plan = _normalize_hex64(
        plan_fingerprint,
        field="plan_fingerprint",
        required=True,
    )
    normalized_snapshot = normalize_text(evidence_snapshot_id)
    if not EVIDENCE_SNAPSHOT_RE.fullmatch(normalized_snapshot):
        raise ValueError("evidence_snapshot_id must reference an immutable pipeline evidence snapshot.")
    if normalized_snapshot.startswith("evidence:") and normalized_snapshot.split(":")[1] != normalized_jira:
        raise ValueError("evidence_snapshot_id must belong to the feedback Jira issue.")
    normalized_ac_id = normalize_text(ac_id).upper()
    if normalized_ac_id and not re.fullmatch(r"UAC-\d{2,3}", normalized_ac_id):
        raise ValueError("ac_id must use the deterministic UAC-01 format.")
    normalized_ac_fingerprint = _normalize_hex64(
        ac_fingerprint,
        field="ac_fingerprint",
    )
    normalized_before = _normalize_hex64(before_hash, field="before_hash")
    normalized_after = _normalize_hex64(after_hash, field="after_hash")
    normalized_decision = normalize_text(decision).upper().replace("-", "_").replace(" ", "_")
    normalized_outcome = normalize_text(outcome).upper().replace("-", "_").replace(" ", "_")
    clean_payload, redaction_count = _sanitize_payload(normalized_event, payload)
    if normalized_event == "escaped_defect" and clean_payload.get("escaped_jira_key"):
        clean_payload["escaped_jira_key"] = _normalize_jira_key(
            clean_payload["escaped_jira_key"],
            field="payload.escaped_jira_key",
        )
    _validate_event_contract(
        event_type=normalized_event,
        ac_id=normalized_ac_id,
        ac_fingerprint=normalized_ac_fingerprint,
        decision=normalized_decision,
        outcome=normalized_outcome,
        before_hash=normalized_before,
        after_hash=normalized_after,
        payload=clean_payload,
    )
    actor_hash = _actor_hash(actor_id)
    normalized_tenant = normalize_text(tenant_id).casefold() or "kone"
    normalized_correlation = normalize_text(correlation_id)[:160]
    event_payload = {
        "contract_version": FEEDBACK_CONTRACT_VERSION,
        "tenant_id": normalized_tenant,
        "jira_key": normalized_jira,
        "correlation_id": normalized_correlation,
        "plan_fingerprint": normalized_plan,
        "evidence_snapshot_id": normalized_snapshot,
        "event_type": normalized_event,
        "actor_hash": actor_hash,
        "ac_id": normalized_ac_id,
        "ac_fingerprint": normalized_ac_fingerprint,
        "decision": normalized_decision,
        "outcome": normalized_outcome,
        "before_hash": normalized_before,
        "after_hash": normalized_after,
        "payload": clean_payload,
    }
    retry_token = normalize_text(idempotency_key)
    if retry_token:
        idempotency_payload = f"client:{normalized_tenant}:{normalized_jira}:{actor_hash}:{retry_token}"
    else:
        idempotency_payload = json.dumps(
            event_payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    event_idempotency = hashlib.sha256(idempotency_payload.encode("utf-8")).hexdigest()
    existing = session.query(TestPlanQualityFeedback).filter_by(
        idempotency_key=event_idempotency
    ).one_or_none()
    if existing is not None:
        return {**_serialize(existing), "created": False}

    row = TestPlanQualityFeedback(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"test-plan-feedback:{event_idempotency}")),
        tenant_id=normalized_tenant,
        jira_key=normalized_jira,
        correlation_id=normalized_correlation or None,
        plan_fingerprint=normalized_plan,
        evidence_snapshot_id=normalized_snapshot,
        event_type=normalized_event,
        actor_hash=actor_hash,
        ac_id=normalized_ac_id or None,
        ac_fingerprint=normalized_ac_fingerprint or None,
        decision=normalized_decision or None,
        outcome=normalized_outcome or None,
        before_hash=normalized_before or None,
        after_hash=normalized_after or None,
        payload=clean_payload,
        redaction_count=redaction_count,
        idempotency_key=event_idempotency,
    )
    try:
        connection = session.connection()
        if connection.dialect.name == "sqlite" and not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN")
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        existing = session.query(TestPlanQualityFeedback).filter_by(
            idempotency_key=event_idempotency
        ).one_or_none()
        if existing is None:
            raise
        return {**_serialize(existing), "created": False}
    return {**_serialize(row), "created": True}


def list_test_plan_feedback(
    session: Session,
    *,
    tenant_id: str,
    jira_key: str,
    plan_fingerprint: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    normalized_jira = _normalize_jira_key(jira_key)
    normalized_tenant = normalize_text(tenant_id).casefold() or "kone"
    query = session.query(TestPlanQualityFeedback).filter_by(
        tenant_id=normalized_tenant,
        jira_key=normalized_jira,
    )
    if normalize_text(plan_fingerprint):
        query = query.filter_by(
            plan_fingerprint=_normalize_hex64(
                plan_fingerprint,
                field="plan_fingerprint",
                required=True,
            )
        )
    rows = query.order_by(
        TestPlanQualityFeedback.created_at.desc(),
        TestPlanQualityFeedback.id.desc(),
    ).limit(max(1, min(int(limit or 200), 1000))).all()
    return [_serialize(row) for row in rows]


def summarize_test_plan_quality(
    session: Session,
    *,
    tenant_id: str,
    jira_key: str,
    plan_fingerprint: str = "",
) -> dict[str, Any]:
    events = list_test_plan_feedback(
        session,
        tenant_id=tenant_id,
        jira_key=jira_key,
        plan_fingerprint=plan_fingerprint,
        limit=1000,
    )
    review_counts = Counter(
        item["decision"] for item in events if item["event_type"] == "review_decision"
    )
    execution_counts = Counter(
        item["outcome"] for item in events if item["event_type"] == "execution_outcome"
    )
    ac_edits = [item for item in events if item["event_type"] == "ac_edit"]
    escaped = [item for item in events if item["event_type"] == "escaped_defect"]
    executed = sum(execution_counts.values())
    passed = execution_counts.get("PASS", 0)
    failed_ac_ids = sorted(
        {
            item["ac_id"]
            for item in events
            if item["event_type"] == "execution_outcome" and item["outcome"] == "FAIL" and item["ac_id"]
        }
    )
    flags = []
    if escaped:
        flags.append("escaped_defect_recorded")
    if failed_ac_ids:
        flags.append("acceptance_criteria_failed_execution")
    if ac_edits and review_counts.get("QE_APPROVED"):
        flags.append("acceptance_criteria_changed_after_review_activity")
    coverage = {
        "review_decision_captured": bool(review_counts),
        "ac_edit_captured": bool(ac_edits),
        "execution_outcome_captured": bool(executed),
        "escaped_defect_captured": bool(escaped),
    }
    candidate_signals = []
    if ac_edits:
        candidate_signals.append(
            {
                "signal": "human_ac_edits",
                "count": len(ac_edits),
                "reuse_policy": "candidate_only_until_benchmark_and_QE_review",
            }
        )
    if failed_ac_ids:
        candidate_signals.append(
            {
                "signal": "failed_acceptance_criteria",
                "ac_ids": failed_ac_ids,
                "reuse_policy": "regression_seed_only_not_expected_behavior",
            }
        )
    if escaped:
        candidate_signals.append(
            {
                "signal": "escaped_defects",
                "count": len(escaped),
                "reuse_policy": "risk_seed_only_with_leaf_issue_validation",
            }
        )
    latest = events[0]["created_at"] if events else None
    return {
        "contract_version": SUMMARY_CONTRACT_VERSION,
        "tenant_id": normalize_text(tenant_id).casefold() or "kone",
        "jira_key": _normalize_jira_key(jira_key),
        "plan_fingerprint": normalize_text(plan_fingerprint).casefold(),
        "event_count": len(events),
        "distinct_plan_fingerprints": len({item["plan_fingerprint"] for item in events}),
        "latest_feedback_at": latest,
        "coverage": coverage,
        "review_decisions": dict(sorted(review_counts.items())),
        "ac_edit_count": len(ac_edits),
        "edited_ac_count": len({item["ac_id"] for item in ac_edits if item["ac_id"]}),
        "execution_outcomes": dict(sorted(execution_counts.items())),
        "execution_pass_rate": round(passed / executed, 4) if executed else None,
        "failed_ac_ids": failed_ac_ids,
        "escaped_defect_count": len(escaped),
        "quality_flags": flags,
        "candidate_learning_signals": candidate_signals,
        "learning_policy": {
            "automatic_authority_promotion": False,
            "expected_behavior_source": "current Jira/UAC and authoritative direct evidence only",
            "feedback_use": "benchmark calibration, regression seeds, and reviewer analytics",
        },
    }
