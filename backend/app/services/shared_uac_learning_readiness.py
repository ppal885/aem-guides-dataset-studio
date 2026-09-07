"""Authenticated configuration observability, not a write or learning health probe.

Do not import the learning persistence service, a database session, app.main,
Chroma, or Jira here. Checking readiness must not initialize any of those systems.
"""
from __future__ import annotations

import os

from fastapi import HTTPException

from app.core.auth import UserIdentity
from app.core.schemas_qe_pattern_mcp import SharedLearningMode
from app.core.shared_uac_learning_http import require_shared_learning_transport_identity
from app.services.qe_pattern_mcp_service import configured_shared_learning_mode
from app.services.tenant_service import ensure_user_can_access_tenant


def get_shared_uac_learning_readiness(*, user: UserIdentity, tenant_id: str) -> dict:
    """Return a bounded, secret-free view of the authenticated caller's tenant.

    A configured token/worker/mode is not evidence of persisted feedback, a
    working scheduler, an indexed lesson, or influence on a generated UAC.
    Existing per-feedback status and run traces provide those separate proofs.
    """
    require_shared_learning_transport_identity(user)
    if not isinstance(tenant_id, str) or not 1 <= len(tenant_id.strip()) <= 120:
        raise HTTPException(400, "A bounded tenant ID is required.")
    try:
        tenant = ensure_user_can_access_tenant(user, tenant_id)
    except ValueError as exc:
        raise HTTPException(400, "Invalid tenant access configuration or tenant ID.") from exc
    personal = user.principal_type == "human" and bool(user.id.strip()) and user.id not in {
        "unknown-user", "dev-user", "system",
    }
    mode = configured_shared_learning_mode()
    raw_mode = os.getenv("SHARED_UAC_LEARNING_MODE", "SHADOW").strip().upper()
    mode_valid = raw_mode in {item.value for item in SharedLearningMode}
    # Match the existing startup setting exactly; this is not scheduler health.
    worker_enabled = os.getenv("SHARED_UAC_LEARNING_WORKER_ENABLED", "true").lower() == "true"
    warnings = ["CONFIGURATION_ONLY_NOT_END_TO_END_LEARNING_PROOF"]
    if not personal:
        warnings.append("PERSONAL_IDENTITY_REQUIRED_FOR_QE_REVIEW")
    if not user.jira_identity:
        warnings.append("JIRA_IDENTITY_MAPPING_MISSING")
    if not mode_valid:
        warnings.append("INVALID_LEARNING_MODE_FAILS_CLOSED_TO_DISABLED")
    if not worker_enabled:
        warnings.append("INDEX_WORKER_CONFIGURED_PAUSED")
    if mode == SharedLearningMode.SHADOW:
        warnings.append("SHADOW_DOES_NOT_CHANGE_UAC_OUTPUT")
    return {
        "schema_version": "shared-uac-learning-readiness-v1",
        "status": "CONFIGURATION_ONLY",
        "tenant_id": tenant,
        "capabilities": {"capture": True, "reviewed_jira_uac": True},
        "identity": {
            "authenticated_token": True,
            "personal_identity": personal,
            "jira_identity_mapping_present": bool(user.jira_identity),
            "review_authority": "NOT_VERIFIED_REQUIRES_LIVE_QE_ASSIGNEE",
        },
        "capture": {
            "transport": "AUTHENTICATED",
            "persistence": "NOT_PROBED",
            "automatic_jira_comment_ingest": False,
        },
        "learning": {
            "configured_mode": mode.value,
            "mode_configuration_valid": mode_valid,
            "influence_configured": mode == SharedLearningMode.ENABLED,
            "actual_learning_proven": False,
            "publication": "NOT_PROBED",
            "index": "NOT_PROBED",
            "authority": "CURRENT_SQL_PUBLICATION_NOT_VECTOR_INDEX_STATUS",
        },
        "worker": {
            "configured_enabled": worker_enabled,
            "status": ("CONFIGURED_ENABLED_RUNTIME_UNVERIFIED" if worker_enabled else "CONFIGURED_PAUSED"),
            "running": None,
        },
        "evidence_needed": {
            "saved_reviewed_indexed": "GET /api/v1/test-plan-learning/feedback/{feedback_id}?tenant_id=...",
            "actual_use": "Run trace: publication, lesson, investigation question and disposition",
        },
        "actions": {
            "database_read": False, "database_write": False, "migration": False,
            "index_read": False, "index_write": False, "jira_request": False,
            "worker_start": False, "generation": False,
        },
        "warnings": warnings,
    }
