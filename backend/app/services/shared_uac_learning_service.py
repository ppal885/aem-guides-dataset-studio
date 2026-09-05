"""Shared, reviewed UAC memory. SQL is authoritative; vector indexing is a projection.

Capture never promotes AI classifications or user prose. Immutable source bindings
and named Human review produce versioned lessons; retrieval checks current SQL state
on every call so a stale vector document cannot resurrect a revoked lesson.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
import uuid

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError

from app.core.schemas_shared_uac_learning import (
    UacDraftRegistration, UacFeedbackBind, UacFeedbackCapture, UacLessonReview,
)
from app.db.shared_uac_learning_models import (
    UacFeedbackBinding, UacFeedbackDelta, UacLearningDraft, UacLearningOutbox,
    UacLessonRevision, utcnow,
)
from app.services.evidence_graph_contract import sanitize_excerpt
from app.services.tenant_service import ensure_user_can_access_tenant

CONTRACT_VERSION = "shared-uac-feedback-v1"
PUBLICATION_VERSION = "shared-uac-learning-publication-v1"
COLLECTION_NAME = "uac_feedback"
_BUNDLE_RE = re.compile(r"^(?:bundle:[a-f0-9]{64}|evidence:[A-Z][A-Z0-9]+-\d+:[a-f0-9]{64})$")
_JIRA_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
_PRESENTATION_DELTAS = {"LANGUAGE_SIMPLIFIED", "AC_MERGED", "AC_SPLIT", "IMPLEMENTATION_DETAIL_REMOVED"}
_SUBMITTED_SECRET_RE = re.compile(r"(?i)\b(?:secret|auth[_ -]?token|passwd)\s*[:=]\s*[^\s,;]+")
_URL_CREDENTIAL_RE = re.compile(r"(?i)(https?://)[^/@\s:]+:[^/@\s]+@")
_SECRET_FIELDS = {"secret", "password", "passwd", "authorization", "token", "api_key",
                  "access_token", "refresh_token", "auth_token", "client_secret"}


class LearningConflict(ValueError):
    """A stale revision or reused idempotency token; expose as HTTP 409."""


def _sha(value: Any) -> str:
    raw = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def _key(value: str) -> str:
    key = value.strip().upper()
    if not _JIRA_RE.fullmatch(key):
        raise ValueError("jira_key must be a Jira issue key.")
    return key


def _bundle(value: str, jira_key: str) -> str:
    value = value.strip()
    if value and not _BUNDLE_RE.fullmatch(value):
        raise ValueError("evidence_bundle_id must be a canonical bundle or legacy evidence snapshot ID.")
    if value.startswith("evidence:") and value.split(":")[1] != jira_key:
        raise LearningConflict("Evidence snapshot belongs to a different Jira issue.")
    return value


def _text(value: str, limit: int) -> str:
    # Preserve the submitted structure while applying the shared secret/PII redactor.
    value = _SUBMITTED_SECRET_RE.sub("[redacted-secret]", value)
    value = _URL_CREDENTIAL_RE.sub(r"\1[redacted-credentials]@", value)
    return "\n".join(sanitize_excerpt(line, max_chars=limit)[0] for line in value.splitlines())[:limit]


def _safe_json(value: Any, *, depth: int = 0, max_fields: int = 30) -> Any:
    if depth > 4:
        raise ValueError("Structured feedback exceeds the maximum nesting depth.")
    if isinstance(value, str):
        if len(value) > 2000:
            raise ValueError("Structured feedback strings must be at most 2000 characters.")
        return _text(value, 2000)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, list) and len(value) <= 100:
        return [_safe_json(item, depth=depth + 1) for item in value]
    if isinstance(value, dict) and len(value) <= max_fields:
        safe = {}
        for key, item in value.items():
            if not str(key).strip() or len(str(key)) > 100:
                raise ValueError("Structured feedback field names must be bounded nonblank text.")
            safe_key = _text(str(key), 100)
            if safe_key in safe:
                raise ValueError("Structured feedback field names collide after redaction.")
            normalized_key = re.sub(r"[\s-]+", "_", str(key).strip().lower())
            safe[safe_key] = "[redacted-secret]" if normalized_key in _SECRET_FIELDS else _safe_json(item, depth=depth + 1)
        return safe
    raise ValueError("Structured feedback must contain bounded JSON values.")


def _context(value) -> dict:
    data = value.model_dump() if hasattr(value, "model_dump") else dict(value or {})
    # Retain opaque linking fingerprints, not whole sessions or raw session identifiers.
    return {key: (_sha(item) if key in {"session_id", "message_id"} and item else item)
            for key, item in data.items()}


def _identity(tenant_id, user, operation, token, payload):
    if not token.strip():
        raise ValueError("idempotency_key must not be blank.")
    request_hash = _sha(payload)
    digest = _sha([tenant_id, user.id, operation, token])
    return dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL, "shared-uac:" + digest)),
                tenant_id=tenant_id, actor_id=user.id, idempotency_key=digest,
                request_hash=request_hash)


def _source_policy(jira_key=""):
    """Read only split identities, never benchmark answers or expected UAC text."""
    configured = os.getenv("SHARED_UAC_BENCHMARK_SPLIT_MANIFEST", "").strip()
    path = Path(configured) if configured else Path(__file__).resolve().parents[3] / "benchmark/v2/manifests/split_manifest.json"
    try:
        if path.stat().st_size > 2_000_000:
            raise ValueError("Oversized protection metadata")
        raw = path.read_text(encoding="utf-8")
        policy = json.loads(raw)
        partitions = policy["jira_ids"]
        if (policy.get("schema_version") != "aem-guides-human-uac-benchmark-v2" or not isinstance(partitions, dict)
                or not all(isinstance(partitions.get(partition), list) for partition in ("train", "validation", "blind"))):
            raise ValueError("Invalid source-protection metadata")
        all_ids = [str(key).upper() for partition in ("train", "validation", "blind") for key in partitions[partition]]
        if len(all_ids) != len(set(all_ids)) or any(not _JIRA_RE.fullmatch(key) for key in all_ids):
            raise ValueError("Overlapping or malformed benchmark source identities")
        protected = {str(key).upper() for partition in ("validation", "blind") for key in partitions[partition]}
        return {"status": "PROTECTED" if jira_key.upper() in protected else "ELIGIBLE", "manifest_hash": _sha(raw)}
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "UNVERIFIED", "manifest_hash": ""}


def _existing(session, model, identity):
    row = session.query(model).filter_by(idempotency_key=identity["idempotency_key"]).one_or_none()
    if row is not None and row.request_hash != identity["request_hash"]:
        raise LearningConflict("Idempotency key was already used with a different request.")
    return row


def _insert(session, model, identity, **values):
    existing = _existing(session, model, identity)
    if existing is not None:
        return existing, False
    row = model(**identity, **values)
    try:
        connection = session.connection()
        if connection.dialect.name == "sqlite" and not connection.connection.driver_connection.in_transaction:
            # Python's sqlite driver does not BEGIN on SELECT. An outer BEGIN is
            # essential: otherwise releasing the first SAVEPOINT commits source
            # rows before their lesson/outbox transaction is complete.
            connection.exec_driver_sql("BEGIN")
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError as exc:
        existing = _existing(session, model, identity)
        if existing is not None:
            return existing, False
        raise LearningConflict("A concurrent change won; reload the latest revision and retry.") from exc
    return row, True


def _named_human(user) -> bool:
    return (getattr(user, "principal_type", "unknown") == "human"
            and user.auth_method in {"token", "oidc", "sso"}
            and bool(user.id.strip()) and user.id not in {"unknown-user", "dev-user", "system"})


def _reviewer(user, *, tenant_id, jira_key):
    from app.services.shared_uac_qe_authorization import authorize_qe_review
    return authorize_qe_review(user, tenant_id=tenant_id, jira_key=jira_key)


def _eligible_reviewed_revision(session, tenant, revision, *, seen=frozenset(), _context=None):
    """SQL authorization lineage wins over old or stale indexed approval flags.

    Reassignment affects new review requests, not valid historical decisions.
    Revoking/superseding a supporting decision invalidates its derived lessons
    until they are deliberately re-reviewed against the new source revision.
    """
    if (revision is None or revision.tenant_id != tenant or revision.state != "APPROVED"
            or revision.lesson_id in seen or len(seen) >= 100):
        return False
    context = _context if _context is not None else {"memo": {}, "latest": {}, "remaining": 1000}
    key = (revision.lesson_id, revision.version)
    if key in context["memo"]:
        return context["memo"][key]
    if context["remaining"] <= 0:
        return False
    context["remaining"] -= 1
    # A failed/cyclic/over-budget dependency is never assumed reviewed. Memoize
    # within this decision only, not across review requests or publications.
    context["memo"][key] = False
    payload = revision.payload
    approval = payload.get("human_approval") or {}
    authorization = approval.get("authorization") or {}
    if (authorization.get("policy") != "LIVE_JIRA_QE_ASSIGNEE"
            or not authorization.get("checked_at")
            or approval.get("reviewer_id") != revision.actor_id
            or authorization.get("jira_key") not in payload.get("source_case_ids", [])):
        return False
    cases = payload.get("source_case_ids", [])
    if not cases or any(_source_policy(case)["status"] != "ELIGIBLE" for case in cases):
        return False
    supports = payload.get("supporting_lesson_revisions", [])
    if not isinstance(supports, list) or len(supports) > 100:
        return False
    expected_ids = set(payload.get("delta_ids", [])) - {revision.lesson_id}
    if any(not isinstance(ref, dict) or set(ref) != {"lesson_id", "version"}
           or not isinstance(ref["lesson_id"], str) or type(ref["version"]) is not int for ref in supports):
        return False
    if {ref["lesson_id"] for ref in supports} != expected_ids:
        return False
    for ref in supports:
        if ref["lesson_id"] not in context["latest"]:
            context["latest"][ref["lesson_id"]] = _latest(session, tenant, ref["lesson_id"])
        support = context["latest"][ref["lesson_id"]]
        if (support is None or support.version != ref["version"]
                or not _eligible_reviewed_revision(session, tenant, support,
                    seen=seen | {revision.lesson_id}, _context=context)):
            return False
    context["memo"][key] = True
    return True


def _draft_receipt(row, created):
    return {"contract_version": CONTRACT_VERSION, "draft_id": row.id,
            "tenant_id": row.tenant_id, "jira_key": row.jira_key,
            "plan_fingerprint": row.plan_fingerprint,
            "evidence_bundle_id": row.evidence_bundle_id, "run_id": row.run_id,
            "criteria_fingerprints": row.content.get("criteria_fingerprints", {}),
            "created": created, "persisted": True}


def register_draft(session, *, user, body: UacDraftRegistration) -> dict:
    tenant = ensure_user_can_access_tenant(user, body.tenant_id)
    jira = _key(body.jira_key)
    fingerprint = _sha(body.draft_markdown)
    if body.plan_fingerprint and body.plan_fingerprint != fingerprint:
        raise LearningConflict("plan_fingerprint does not match the submitted draft bytes.")
    evidence = _bundle(body.evidence_bundle_id, jira)
    if not body.draft_markdown.strip():
        raise ValueError("draft_markdown must not be blank.")
    if any(text not in body.draft_markdown for text in body.criteria.values()):
        raise LearningConflict("Every criterion must occur verbatim in the registered draft.")
    safe_markdown = _text(body.draft_markdown, 100_000)
    identity = _identity(tenant, user, "draft", body.idempotency_key, body.model_dump(mode="json"))
    row, created = _insert(session, UacLearningDraft, identity, jira_key=jira,
        plan_fingerprint=fingerprint, evidence_bundle_id=evidence, run_id=body.run_id,
        content={"draft_markdown": safe_markdown, "source_hash": fingerprint,
                 "content_hash": _sha(safe_markdown),
                 "criteria": {key: _text(value, 12_000) for key, value in body.criteria.items()},
                 "criteria_fingerprints": {key: _sha(value) for key, value in body.criteria.items()},
                 "client_context": _context(body.client_context), "principal_type": getattr(user, "principal_type", "unknown"),
                 "evidence_authority_verified": False})
    return _draft_receipt(row, created)


def _resolve_draft(session, tenant, jira, draft_id="", fingerprint="", evidence="", run_id=""):
    query = session.query(UacLearningDraft).filter_by(tenant_id=tenant, jira_key=jira)
    if draft_id:
        row = query.filter_by(id=draft_id).one_or_none()
        if row and ((fingerprint and row.plan_fingerprint != fingerprint)
                    or (evidence and row.evidence_bundle_id != evidence)
                    or (run_id and row.run_id != run_id)):
            raise LearningConflict("Draft reference does not match the submitted plan, evidence, or run.")
        return row
    if not fingerprint:
        return None
    query = query.filter_by(plan_fingerprint=fingerprint)
    if evidence:
        query = query.filter_by(evidence_bundle_id=evidence)
    if run_id:
        query = query.filter_by(run_id=run_id)
    rows = query.limit(2).all()
    return rows[0] if len(rows) == 1 else None


def _latest(session, tenant, lesson_id):
    return session.query(UacLessonRevision).filter_by(tenant_id=tenant, lesson_id=lesson_id).order_by(UacLessonRevision.version.desc()).first()


def _delta(session, tenant, feedback_id):
    row = session.query(UacFeedbackDelta).filter_by(tenant_id=tenant, id=feedback_id).one_or_none()
    if row is None:
        raise HTTPException(404, "Feedback not found.")
    return row


def _binding(session, tenant, delta_id):
    return session.query(UacFeedbackBinding).filter_by(tenant_id=tenant, delta_id=delta_id).one_or_none()


def _append_revision(session, identity, *, lesson_id, version, state, payload):
    row, created = _insert(session, UacLessonRevision, identity, lesson_id=lesson_id,
                           version=version, state=state, payload=payload)
    if created:
        session.add(UacLearningOutbox(id=str(uuid.uuid4()), tenant_id=row.tenant_id,
                                     revision_id=row.id,
                                     status="PENDING" if state in {"APPROVED", "REVOKED", "REJECTED"} else "SKIPPED"))
        session.flush()
    return row


def capture_feedback(session, *, user, body: UacFeedbackCapture) -> dict:
    tenant = ensure_user_can_access_tenant(user, body.tenant_id)
    jira = _key(body.jira_key)
    evidence = _bundle(body.evidence_bundle_id, jira)
    if not body.raw_feedback.strip():
        raise ValueError("raw_feedback must not be blank.")
    identity = _identity(tenant, user, "capture", body.idempotency_key, body.model_dump(mode="json"))
    existing = _existing(session, UacFeedbackDelta, identity)
    if existing is not None:
        return {**get_feedback_status(session, user=user, tenant_id=tenant, feedback_id=existing.id), "created": False}
    draft_id = body.draft_id
    if body.draft:
        registered = register_draft(session, user=user, body=UacDraftRegistration(
            **body.draft.model_dump(), tenant_id=tenant, jira_key=jira,
            plan_fingerprint=body.plan_fingerprint, idempotency_key="capture:" + _sha(body.idempotency_key)))
        if draft_id and draft_id != registered["draft_id"]:
            raise LearningConflict("Supply either an existing draft reference or inline draft content.")
        draft_id = registered["draft_id"]
    draft = _resolve_draft(session, tenant, jira, draft_id, body.plan_fingerprint, evidence, body.run_id)
    if draft and body.ac_id and body.ac_id not in draft.content.get("criteria", {}):
        raise LearningConflict("ac_id does not exist in the registered draft.")
    delta, created = _insert(session, UacFeedbackDelta, identity, jira_key=jira,
        plan_fingerprint=body.plan_fingerprint or (draft.plan_fingerprint if draft else ""),
        raw_feedback=_text(body.raw_feedback, 12_000), proposed_correction=_text(body.proposed_correction, 12_000),
        delta_type=body.delta_type, content={"source": "UNCONFIRMED_SUBMISSION",
            "source_kind": body.source_kind, "source_policy_at_capture": _source_policy(jira),
            "submitted_text_hash": _sha(body.raw_feedback), "correction_hash": _sha(body.proposed_correction),
            "ai_classification": _safe_json(body.ai_classification),
            "client_context": _context(body.client_context), "ac_id": body.ac_id,
            "requested_draft_id": draft_id, "evidence_bundle_id": evidence, "run_id": body.run_id,
            "principal_type": getattr(user, "principal_type", "unknown"),
            "automatic_authority_promotion": False})
    if created:
        if draft:
            _insert(session, UacFeedbackBinding,
                _identity(tenant, user, "capture-binding", body.idempotency_key, {"delta": delta.id, "draft": draft.id}),
                delta_id=delta.id, draft_id=draft.id)
        _append_revision(session, _identity(tenant, user, "capture-lesson", body.idempotency_key, {"delta": delta.id}),
            lesson_id=delta.id, version=1, state="CANDIDATE" if draft else "PENDING_BINDING",
            payload={"delta_ids": [delta.id], "source_case_ids": [jira], "draft_id": draft.id if draft else "",
                     "delta_type": body.delta_type, "guidance": "", "automatic_authority_promotion": False})
    return {**get_feedback_status(session, user=user, tenant_id=tenant, feedback_id=delta.id), "created": created}


def bind_feedback(session, *, user, feedback_id: str, body: UacFeedbackBind) -> dict:
    tenant = ensure_user_can_access_tenant(user, body.tenant_id)
    delta = _delta(session, tenant, feedback_id)
    authorization = _reviewer(user, tenant_id=tenant, jira_key=delta.jira_key)
    identity = _identity(tenant, user, "bind:" + feedback_id, body.idempotency_key, body.model_dump())
    existing = _existing(session, UacFeedbackBinding, identity)
    if existing:
        return get_feedback_status(session, user=user, tenant_id=tenant, feedback_id=feedback_id)
    if _binding(session, tenant, feedback_id):
        raise LearningConflict("Feedback is already bound; capture a new correction to change its source.")
    draft = _resolve_draft(session, tenant, delta.jira_key, body.draft_id, delta.plan_fingerprint,
                           delta.content.get("evidence_bundle_id", ""), delta.content.get("run_id", ""))
    if draft is None:
        raise HTTPException(404, "Matching registered draft not found.")
    if delta.content.get("ac_id") and delta.content["ac_id"] not in draft.content.get("criteria", {}):
        raise LearningConflict("ac_id does not exist in the registered draft.")
    _insert(session, UacFeedbackBinding, identity, delta_id=delta.id, draft_id=draft.id)
    previous = _latest(session, tenant, feedback_id)
    _append_revision(session, _identity(tenant, user, "bind-lesson:" + feedback_id, body.idempotency_key, body.model_dump()),
        lesson_id=feedback_id, version=previous.version + 1, state="CANDIDATE",
        payload={**previous.payload, "draft_id": draft.id, "binding_authorization": authorization})
    return get_feedback_status(session, user=user, tenant_id=tenant, feedback_id=feedback_id)


def _validated_lesson(session, tenant, delta, definition, user, at, *, version):
    from app.core.schemas_canonical_test_plan_runtime import (
        AbstractSignalKind, ChangeSurfaceKind, IssueDomain, SemanticDimension, EvidenceSourceType,
    )
    payload = definition.model_dump(mode="json")
    # A reviewed lesson is normalized prose, not the immutable Human correction
    # or registered draft. Keep those source bytes separate and unchanged.
    payload["guidance"] = " ".join(payload["guidance"].split())
    for name, enum in (("domains", IssueDomain), ("surfaces", ChangeSurfaceKind),
                       ("signals", AbstractSignalKind), ("families", SemanticDimension)):
        allowed = {item.value for item in enum}
        if len(payload[name]) != len(set(payload[name])) or any(value not in allowed for value in payload[name]):
            raise ValueError(f"{name} must contain unique canonical selector values.")
    if not all(payload[name] for name in ("domains", "surfaces", "signals")):
        raise ValueError("An approved lesson requires explicit domain, surface, and signal selectors.")
    if any(value not in {item.value for item in EvidenceSourceType} for value in payload["preferred_evidence"]):
        raise ValueError("preferred_evidence must contain canonical evidence source types.")
    presentation = payload["delta_type"] in _PRESENTATION_DELTAS
    if not payload["families"] and not presentation:
        raise ValueError("An approved lesson requires at least one investigation family.")
    if payload["delta_type"] == "UNCLASSIFIED":
        raise ValueError("Human review must classify the feedback delta before approval.")
    if presentation and payload["families"]:
        raise ValueError("Presentation feedback cannot modify investigation families.")
    payload["influence_kind"] = "AUTHORING_GUIDANCE" if presentation else "INVESTIGATION_CANDIDATE"
    if payload["delta_type"] == "COVERAGE_ADDED" and payload["first_failed_stage"] not in {
        "DISCOVERY", "VERSION_EVIDENCE", "CONFLICT_RESOLUTION", "SCOPE", "ENTRY_POINT", "REPRO_DIMENSION",
        "CANDIDATE_COMPLETENESS", "SYNTHESIS", "RENDERING",
    }:
        raise ValueError("COVERAGE_ADDED requires a reviewed first_failed_stage.")
    for name in ("preferred_evidence", "counterexamples", "hard_negatives"):
        if any(not str(item).strip() or len(item) > 2000 for item in payload[name]):
            raise ValueError(f"{name} must contain bounded nonblank text.")
    for values in payload["scope"].values():
        if any(not value.strip() or len(value) > 200 for value in values):
            raise ValueError("Scope qualifiers must contain bounded nonblank text.")
    if payload["scope"]["jira_keys"]:
        raise ValueError("Jira keys are source provenance, never applicability selectors.")
    payload["scope"].pop("jira_keys")
    if re.search(r"\b[A-Z][A-Z0-9]+-\d+\b", json.dumps({"scope": payload["scope"], "guidance": payload["guidance"]}), re.I):
        raise ValueError("Jira keys belong only in source provenance, not lesson guidance or applicability selectors.")
    if payload["kind"] == "SCOPED_CASE" and not any(payload["scope"].values()):
        raise ValueError("A scoped lesson requires an explicit applicability qualifier.")
    ids = list(dict.fromkeys([delta.id, *payload.pop("supporting_delta_ids")]))
    cases = set()
    supporting_revisions = []
    for delta_id in ids:
        supporting = _delta(session, tenant, delta_id)
        if supporting.content.get("source_kind") == "AI_PROPOSAL":
            raise ValueError("An AI proposal cannot become Human supervisory learning.")
        protection = _source_policy(supporting.jira_key)
        if protection["status"] != "ELIGIBLE":
            raise LearningConflict("Source is protected or source-protection metadata is unavailable; publication is quarantined.")
        if not _binding(session, tenant, delta_id):
            raise LearningConflict("Every supporting correction must be bound to a registered draft.")
        if delta_id != delta.id:
            support = _latest(session, tenant, delta_id)
            if not _eligible_reviewed_revision(session, tenant, support):
                raise LearningConflict("Each supporting correction requires its own QE Assignee approval before reuse.")
            supporting_revisions.append({"lesson_id": delta_id, "version": support.version})
            cases.update(support.payload.get("source_case_ids", []))
        cases.add(supporting.jira_key)
    groups = payload["independent_support_groups"]
    group_ids = [group["group_id"].strip() for group in groups]
    grouped = [case for group in groups for case in group["case_ids"]]
    if (not group_ids or not all(group_ids) or len(group_ids) != len(set(group_ids))
            or len(grouped) != len(set(grouped)) or set(grouped) != cases):
        raise ValueError("Every stored source case must belong to exactly one independent support group.")
    exception = payload.get("exception_attestation")
    if exception:
        if not exception["rationale"].strip() or any(not ref.strip() for ref in exception["evidence_refs"]):
            raise ValueError("An exception requires a concrete rationale and supporting evidence references.")
        if exception["kind"] == "SEVERE_P0_P1" and payload["materiality"] not in {"P0", "P1"}:
            raise ValueError("A severe-failure exception requires P0 or P1 materiality.")
        exception.update(reviewer_id=user.id, reviewed_at=at)
    if payload["kind"] == "GENERIC_PATTERN" and len(groups) < 2 and not exception:
        raise ValueError("A generic pattern requires two independent cases or a reviewed normative/severe exception.")
    binding = _binding(session, tenant, delta.id)
    draft = session.query(UacLearningDraft).filter_by(id=binding.draft_id, tenant_id=tenant).one()
    payload.update(delta_ids=ids, source_case_ids=sorted(cases), draft_id=draft.id,
        supporting_lesson_revisions=supporting_revisions,
        plan_fingerprint=draft.plan_fingerprint, evidence_bundle_id=draft.evidence_bundle_id,
        human_approval={"reviewer_id": user.id, "reviewed_at": at, "origin_confirmed": True,
                        "applicability_confirmed": True, "counterexamples_checked": True},
        source="HUMAN_FEEDBACK", automatic_authority_promotion=False,
        expected_behavior_authority=False, published_at=at, revoked_at=None)
    payload["source_origin"] = delta.content.get("source_kind", "UNCONFIRMED")
    payload["source_protection_manifest_hash"] = protection["manifest_hash"]
    # The server's versioned lesson adds audit/lineage fields beyond the public
    # DTO. Enlarge only this root; nested and submitted JSON keep their limits.
    safe = _safe_json(payload, max_fields=64)
    # Authentication owns actor identity. Keep its unique reviewer ID intact even
    # when it is an email address; source text redaction must not erase provenance.
    safe["human_approval"]["reviewer_id"] = user.id
    if safe.get("exception_attestation"):
        safe["exception_attestation"]["reviewer_id"] = user.id
    # Do not persist APPROVED content that will invalidate the complete shared
    # publication at its consumer boundary. The final publication supplies its
    # own hash; this placeholder only validates the finalized lesson contract.
    from app.services.shared_learning_pattern_provider import SharedLearningPatternLibraryProvider
    try:
        SharedLearningPatternLibraryProvider._record(
            {**safe, "lesson_id": delta.id, "version": version}, "0" * 64)
    except ValidationError:
        # Pydantic's rendered error includes input values. Never echo the
        # correction, internal metadata or identity through an HTTP 400 detail.
        raise ValueError("Reviewed lesson does not satisfy the shared publication contract.") from None
    return safe


def review_lesson(session, *, user, feedback_id: str, body: UacLessonReview) -> dict:
    tenant = ensure_user_can_access_tenant(user, body.tenant_id)
    delta = _delta(session, tenant, feedback_id)
    authorization = _reviewer(user, tenant_id=tenant, jira_key=delta.jira_key)
    if not body.note.strip():
        raise ValueError("Every review decision requires a nonblank reason note.")
    identity = _identity(tenant, user, "review:" + feedback_id, body.idempotency_key, body.model_dump(mode="json"))
    existing = _existing(session, UacLessonRevision, identity)
    if existing:
        return {**get_feedback_status(session, user=user, tenant_id=tenant, feedback_id=feedback_id),
                "review_revision": existing.version, "created": False}
    current = _latest(session, tenant, feedback_id)
    if current.version != body.expected_revision:
        raise LearningConflict("The lesson changed; reload its latest revision before reviewing.")
    at = _iso(utcnow())
    if body.decision in {"APPROVE", "SUPERSEDE"}:
        if body.decision == "SUPERSEDE" and current.state != "APPROVED":
            raise LearningConflict("Only an approved lesson can be superseded.")
        if not _binding(session, tenant, feedback_id):
            raise LearningConflict("Resolve the draft binding before approval.")
        if not (body.origin_confirmed and body.applicability_confirmed and body.counterexamples_checked):
            raise ValueError("Approval requires explicit Human origin, applicability, and counterexample attestations.")
        if body.lesson is None:
            raise ValueError("Approval requires an explicit reviewed lesson definition.")
        payload = _validated_lesson(session, tenant, delta, body.lesson, user, at,
            version=current.version + 1)
        state = "APPROVED"
    else:
        if body.decision == "REVOKE" and current.state != "APPROVED":
            raise LearningConflict("Only an approved lesson can be revoked.")
        payload = dict(current.payload)
        payload.update(revoked_at=at, review_actor_id=user.id, reviewed_at=at)
        state = "REJECTED" if body.decision == "REJECT" else "REVOKED"
    payload["review_note"] = _text(body.note, 2000)
    payload["review_authorization"] = authorization
    if state == "APPROVED":
        payload["human_approval"]["authorization"] = authorization
    revision = _append_revision(session, identity, lesson_id=feedback_id,
        version=current.version + 1, state=state, payload=payload)
    return {**get_feedback_status(session, user=user, tenant_id=tenant, feedback_id=feedback_id),
            "review_revision": revision.version, "created": True}


def get_feedback_status(session, *, user, tenant_id: str, feedback_id: str) -> dict:
    tenant = ensure_user_can_access_tenant(user, tenant_id)
    delta = _delta(session, tenant, feedback_id)
    binding = _binding(session, tenant, feedback_id)
    draft = session.query(UacLearningDraft).filter_by(id=binding.draft_id, tenant_id=tenant).one() if binding else None
    revision = _latest(session, tenant, feedback_id)
    outbox = session.query(UacLearningOutbox).filter_by(tenant_id=tenant, revision_id=revision.id).one_or_none()
    eligibility = "AI_ONLY" if delta.content.get("source_kind") == "AI_PROPOSAL" else _source_policy(delta.jira_key)["status"]
    reuse_eligible = _eligible_reviewed_revision(session, tenant, revision)
    return {"contract_version": CONTRACT_VERSION, "feedback_id": delta.id, "lesson_id": delta.id,
        "tenant_id": tenant, "jira_key": delta.jira_key, "persisted": True,
        "binding_status": "BOUND" if binding else "PENDING_BINDING",
        "draft_id": binding.draft_id if binding else "", "plan_fingerprint": draft.plan_fingerprint if draft else delta.plan_fingerprint,
        "learning_status": revision.state, "revision": revision.version,
        "index_status": outbox.status if outbox else "MISSING", "index_attempts": outbox.attempts if outbox else 0,
        "index_error": outbox.last_error if outbox else "", "created_at": _iso(delta.created_at),
        "raw_feedback": delta.raw_feedback, "proposed_correction": delta.proposed_correction,
        "delta_type": delta.delta_type, "ai_classification": delta.content.get("ai_classification", {}),
        "submitter_id": delta.actor_id, "submitter_identity_kind": delta.content.get("principal_type", "unknown"),
        "source_kind": delta.content.get("source_kind", "UNCONFIRMED"), "publication_eligibility": eligibility,
        "review_policy": "LIVE_JIRA_QE_ASSIGNEE", "reuse_eligible": reuse_eligible,
        "publication_review_status": ("QE_APPROVED" if reuse_eligible else
            "RE_REVIEW_REQUIRED" if revision.state == "APPROVED" else "PENDING_REVIEW"),
        "source_hash": delta.content.get("submitted_text_hash"), "correction_hash": delta.content.get("correction_hash"),
        "lesson": revision.payload, "automatic_authority_promotion": False}


def list_learning(session, *, user, tenant_id="kone", jira_key="", plan_fingerprint="", limit=50):
    tenant = ensure_user_can_access_tenant(user, tenant_id)
    query = session.query(UacFeedbackDelta).filter_by(tenant_id=tenant)
    if jira_key:
        query = query.filter_by(jira_key=_key(jira_key))
    if plan_fingerprint:
        bound_ids = session.query(UacFeedbackBinding.delta_id).join(UacLearningDraft,
            UacFeedbackBinding.draft_id == UacLearningDraft.id).filter(
            UacFeedbackBinding.tenant_id == tenant, UacLearningDraft.tenant_id == tenant,
            UacLearningDraft.plan_fingerprint == plan_fingerprint)
        query = query.filter(or_(UacFeedbackDelta.plan_fingerprint == plan_fingerprint,
                                 UacFeedbackDelta.id.in_(bound_ids)))
    rows = query.order_by(UacFeedbackDelta.created_at.desc(), UacFeedbackDelta.id.desc()).limit(max(1, min(limit, 200))).all()
    return {"items": [get_feedback_status(session, user=user, tenant_id=tenant, feedback_id=row.id) for row in rows],
            "count": len(rows)}


@contextmanager
def _session_scope(session=None):
    if session is not None:
        yield session
        return
    from app.db.session import SessionLocal
    with SessionLocal() as owned:
        yield owned


def load_shared_learning_publication(*, tenant_id: str, cutoff_at: datetime | None = None,
                                     excluded_source_case_ids: set[str] | None = None, session=None) -> dict:
    """Trusted service boundary; HTTP callers must authorize the tenant first.

    Revocation always uses current state, including for temporal replay. A cutoff
    excludes later publications; it never resurrects a currently revoked lesson.
    """
    tenant = tenant_id.strip().lower()
    if not tenant:
        raise ValueError("A tenant is required for shared learning retrieval.")
    if cutoff_at is not None and cutoff_at.tzinfo is None:
        raise ValueError("cutoff_at requires a timezone.")
    excluded = {str(value).upper() for value in (excluded_source_case_ids or set())}
    with _session_scope(session) as db:
        latest = db.query(UacLessonRevision.lesson_id, func.max(UacLessonRevision.version).label("version")).filter_by(tenant_id=tenant).group_by(UacLessonRevision.lesson_id).subquery()
        query = db.query(UacLessonRevision).join(latest, and_(UacLessonRevision.lesson_id == latest.c.lesson_id,
                    UacLessonRevision.version == latest.c.version)).filter(UacLessonRevision.tenant_id == tenant)
        rows = query.order_by(UacLessonRevision.lesson_id).all()
        lessons = []
        for row in rows:
            if not _eligible_reviewed_revision(db, tenant, row):
                continue
            published = row.payload.get("published_at")
            if cutoff_at and (not published or datetime.fromisoformat(published) > cutoff_at):
                continue
            if excluded.intersection(str(case).upper() for case in row.payload.get("source_case_ids", [])):
                continue
            if any(_source_policy(case)["status"] != "ELIGIBLE" for case in row.payload.get("source_case_ids", [])):
                continue
            lessons.append({**row.payload, "lesson_id": row.lesson_id, "version": row.version})
        projection = [[row.lesson_id, row.version, row.state, row.request_hash] for row in rows]
        source_policy = _source_policy()
        publication_id = _sha({"tenant": tenant, "revisions": projection, "lessons": lessons,
            "source_policy": source_policy, "cutoff": _iso(cutoff_at), "excluded": sorted(excluded)})
        return {"contract_version": PUBLICATION_VERSION, "tenant_id": tenant,
                "publication_id": publication_id, "published_at": max((_iso(row.created_at) for row in rows), default=None),
                "lessons": lessons, "source_protection_status": source_policy["status"],
                "source_protection_manifest_hash": source_policy["manifest_hash"]}


def _index_revision(revision):
    from app.services.embedding_service import embed_texts_batched
    from app.services.vector_store_service import add_documents
    document = json.dumps({"source": "HUMAN_FEEDBACK_CANDIDATE", "state": revision.state,
                           "lesson": revision.payload}, sort_keys=True)
    vectors = embed_texts_batched([document], batch_size=1)
    if vectors is None:
        return False
    vector = vectors[0].tolist() if hasattr(vectors[0], "tolist") else list(vectors[0])
    return add_documents(COLLECTION_NAME, [f"{revision.tenant_id}:{revision.lesson_id}:{revision.version}"],
        [document], [{"tenant_id": revision.tenant_id, "lesson_id": revision.lesson_id,
                      "version": revision.version, "state": revision.state, "authority": "candidate_only"}], [vector])


def _remove_revisions(revisions):
    if not revisions:
        return True
    from app.services.vector_store_service import delete_documents
    return delete_documents(COLLECTION_NAME,
        [f"{row.tenant_id}:{row.lesson_id}:{row.version}" for row in revisions])


def _bounded_projection(operation, revisions, timeout_seconds):
    """Kill the complete projection process on timeout, preventing late writes."""
    payload = {"operation": operation, "revisions": [
        {"tenant_id": row.tenant_id, "lesson_id": row.lesson_id, "version": row.version,
         "state": row.state, "payload": row.payload} for row in revisions]}
    result = subprocess.run([sys.executable, "-m", "app.services.shared_uac_learning_index_worker"],
        input=json.dumps(payload), capture_output=True, text=True, timeout=timeout_seconds,
        cwd=str(Path(__file__).resolve().parents[2]),
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        check=False)
    # Output is deliberately not logged: imported clients may emit environment
    # diagnostics. Success is an exit status, never a substring in mixed logs.
    return result.returncode == 0


def drain_learning_outbox(*, tenant_id: str, limit: int = 20, max_attempts: int = 5,
                          session=None, index_writer=None, index_remover=None,
                          max_duration_seconds: float = 60, index_timeout_seconds: float = 30) -> dict:
    """Bounded, lease-based worker. Failure stays durable and explicit; never approves.

    An injected session is dedicated to this worker: claims/results commit separately.
    The caller must not pass a request transaction with unrelated pending writes.
    """
    limit = max(1, min(limit, 100))
    max_attempts = max(1, min(max_attempts, 20))
    deadline = time.monotonic() + max(1, min(max_duration_seconds, 300))
    def project(operation, revisions):
        if not revisions:
            return True
        timeout = min(max(1, min(index_timeout_seconds, 60)), max(0.1, deadline - time.monotonic()))
        return _bounded_projection(operation, revisions, timeout)
    write_projection = index_writer or (lambda row: project("index", [row]))
    remove_projection = index_remover or (lambda rows: project("remove", rows))
    indexed = failed = claimed = skipped = 0
    with _session_scope(session) as db:
        for _ in range(limit):
            if time.monotonic() >= deadline:
                break
            now = utcnow()
            ready = and_(UacLearningOutbox.tenant_id == tenant_id,
                UacLearningOutbox.attempts < max_attempts,
                UacLearningOutbox.next_attempt_at <= now,
                or_(UacLearningOutbox.status.in_(["PENDING", "FAILED"]),
                    and_(UacLearningOutbox.status == "PROCESSING", UacLearningOutbox.lease_until < now)))
            row = db.query(UacLearningOutbox).filter(ready).order_by(UacLearningOutbox.created_at, UacLearningOutbox.id).first()
            if row is None:
                break
            claim = str(uuid.uuid4())
            changed = db.query(UacLearningOutbox).filter(ready, UacLearningOutbox.id == row.id).update(
                {"status": "PROCESSING", "lease_owner": claim, "lease_until": now + timedelta(minutes=5),
                 "attempts": UacLearningOutbox.attempts + 1}, synchronize_session=False)
            db.commit()
            if not changed:
                continue
            claimed += 1
            row = db.query(UacLearningOutbox).filter_by(id=row.id).populate_existing().one()
            revision = db.query(UacLessonRevision).filter_by(id=row.revision_id, tenant_id=tenant_id).one()
            latest = _latest(db, tenant_id, revision.lesson_id)
            observed_latest_version = latest.version
            latest_eligible = _eligible_reviewed_revision(db, tenant_id, latest)
            eligible = revision.id == latest.id and latest_eligible
            try:
                if eligible:
                    ok = bool(write_projection(revision))
                    # A review may change while embedding/vector I/O is in flight.
                    # SQL eligibility is checked again before acknowledging indexing.
                    db.expire_all()
                    latest = _latest(db, tenant_id, revision.lesson_id)
                    if latest.id != revision.id or not _eligible_reviewed_revision(db, tenant_id, latest):
                        eligible = False
                        ok = bool(remove_projection([revision]))
                    elif ok:
                        old = db.query(UacLessonRevision).filter(
                            UacLessonRevision.tenant_id == tenant_id,
                            UacLessonRevision.lesson_id == revision.lesson_id,
                            UacLessonRevision.version < revision.version,
                            UacLessonRevision.state == "APPROVED").all()
                        ok = bool(remove_projection(old))
                else:
                    obsolete = db.query(UacLessonRevision).filter(
                        UacLessonRevision.tenant_id == tenant_id,
                        UacLessonRevision.lesson_id == revision.lesson_id,
                        # A newer approval may already have been indexed while
                        # this worker held an older revoked/ineligible snapshot.
                        UacLessonRevision.version <= observed_latest_version,
                        UacLessonRevision.state == "APPROVED")
                    if latest_eligible:
                        obsolete = obsolete.filter(UacLessonRevision.version < observed_latest_version)
                    ok = bool(remove_projection(obsolete.all()))
                error = "" if ok else "Index service unavailable"
            except Exception as exc:
                ok, error = False, f"Indexing failed ({type(exc).__name__})"
            finished = utcnow()
            db.query(UacLearningOutbox).filter_by(id=row.id, lease_owner=claim, status="PROCESSING").update(
                {"status": ("INDEXED" if eligible else "SKIPPED") if ok else "FAILED", "last_error": error,
                 "indexed_at": finished if ok and eligible else None, "lease_owner": None, "lease_until": None,
                 "next_attempt_at": finished + timedelta(seconds=min(3600, 2 ** min(row.attempts, 12)))},
                synchronize_session=False)
            db.commit()
            indexed += int(ok and eligible)
            skipped += int(ok and not eligible)
            failed += int(not ok)
    return {"tenant_id": tenant_id, "claimed": claimed, "indexed": indexed, "skipped": skipped, "failed": failed,
            "max_attempts": max_attempts, "collection": COLLECTION_NAME}


def retry_failed_index(session, *, user, tenant_id="kone", feedback_id="", limit=100):
    tenant = ensure_user_can_access_tenant(user, tenant_id)
    if not user.is_admin:
        raise HTTPException(403, "Admin access is required to retry exhausted index work.")
    query = session.query(UacLearningOutbox).filter_by(tenant_id=tenant, status="FAILED")
    if feedback_id:
        _delta(session, tenant, feedback_id)
        revisions = session.query(UacLessonRevision.id).filter_by(tenant_id=tenant, lesson_id=feedback_id)
        query = query.filter(UacLearningOutbox.revision_id.in_(revisions))
    ids = [row.id for row in query.order_by(UacLearningOutbox.created_at).limit(max(1, min(limit, 100))).all()]
    if ids:
        session.query(UacLearningOutbox).filter(UacLearningOutbox.id.in_(ids), UacLearningOutbox.tenant_id == tenant).update(
            {"status": "PENDING", "attempts": 0, "last_error": "", "next_attempt_at": utcnow(),
             "lease_owner": None, "lease_until": None}, synchronize_session=False)
    return {"tenant_id": tenant, "reset_count": len(ids)}
