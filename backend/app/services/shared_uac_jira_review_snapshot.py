"""Read and verify a pinned Jira UAC snapshot without fetching chat history.

Only the tenant's configured Jira origin and bounded, TLS-verified issue reader
are used. This proves reviewed field provenance, not generation or approval.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
import re

from fastapi import HTTPException

from app.services import shared_uac_qe_authorization as jira_authority
from app.services.tenant_service import ensure_user_can_access_tenant


class JiraReviewMismatch(ValueError):
    """The reviewed source no longer matches; never silently capture a new one."""


_FIELD_NAMES = {"Acceptance Criteria", "Acceptance Criterion", "UAC"}
# The prefix alternatives are disjoint: long markup-only lines must not trigger
# nested-quantifier backtracking while verifying a bounded, untrusted Jira field.
_LABEL = re.compile(r"(?im)^[ \t*#>\-]*(?:h[1-6]\.[ \t*#>\-]*)?((?:UAC|AC)[-_ ]?\d+)\b")
_ID = re.compile(r"(?:UAC|AC)[-_ ]?\d+", re.I)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 80:
        raise ValueError("Invalid issue timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Issue timestamp lacks timezone")
    return parsed


def _validate_excerpt(markdown: str, excerpt: str, ac_id: str) -> None:
    if ac_id and not excerpt.strip():
        raise JiraReviewMismatch("ac_id requires an exact original_reviewed_ac excerpt.")
    if not excerpt:
        return
    if not excerpt.strip() or markdown.count(excerpt) != 1:
        raise JiraReviewMismatch("original_reviewed_ac must occur verbatim exactly once in the reviewed Jira field.")
    if ac_id and _ID.fullmatch(ac_id):
        start = markdown.index(excerpt)
        end = start + len(excerpt)
        labels = list(_LABEL.finditer(markdown))
        previous = [match for match in labels if match.start() <= start]
        selected = ([previous[-1]] if previous else []) + [match for match in labels if start < match.start() < end]
        normalize = lambda value: re.sub(r"[-_ ]", "", value).upper()
        if any(normalize(match[1]) != normalize(ac_id) for match in selected):
            raise JiraReviewMismatch("ac_id does not match the criterion label in the reviewed Jira field.")


def read_reviewed_jira_uac(*, user, tenant_id: str, jira_key: str, reference, ac_id: str = "") -> dict | None:
    """Return verified raw bytes/provenance, or None when the original is empty.

    Missing/empty content cannot bind. Changed content is a conflict, and failed
    reads remain retriable errors. No writes or fallback to other Jira origins.
    """
    tenant = ensure_user_can_access_tenant(user, tenant_id)
    if not jira_authority._ISSUE_KEY.fullmatch(jira_key):
        raise ValueError("jira_key must be a Jira issue key.")
    try:
        config = jira_authority.get_tenant(tenant)
        if config.is_active is not True:
            raise ValueError("Inactive tenant")
        server = jira_authority._origin(str(config.jira_url or ""))
        configured = os.getenv("JIRA_ACCEPTANCE_CRITERIA_FIELD_ID", "").strip()
        if configured and not jira_authority._CUSTOM_FIELD.fullmatch(configured):
            raise ValueError("Invalid acceptance field configuration")
        if configured and reference.field_id != configured:
            raise JiraReviewMismatch("The reviewed field does not match the configured Jira UAC field.")
        client = jira_authority._tenant_client(config, server)
        issue = client.get_issue_with_names(jira_key, fields=f"{reference.field_id},updated")
        if not isinstance(issue, dict) or issue.get("key") != jira_key:
            raise ValueError("Mismatched Jira issue")
        fields, names = issue.get("fields"), issue.get("names")
        if not isinstance(fields, dict) or not isinstance(names, dict):
            raise ValueError("Invalid Jira field response")
        name = names.get(reference.field_id)
        if (name not in _FIELD_NAMES or (not configured
                and sum(value in _FIELD_NAMES for value in names.values() if isinstance(value, str)) != 1)):
            raise JiraReviewMismatch("The reviewed field is not an unambiguous Jira acceptance-criteria field.")
        markdown = fields.get(reference.field_id)
        if markdown is None or (isinstance(markdown, str) and not markdown.strip()):
            return None
        if not isinstance(markdown, str):
            raise JiraReviewMismatch("The Jira UAC field must contain raw text; rendered or structured content cannot be bound.")
        if len(markdown) > 100_000:
            raise ValueError("Oversized Jira UAC field")
        fingerprint = _sha(markdown)
        if fingerprint != reference.expected_sha256:
            raise JiraReviewMismatch("The Jira UAC changed or its hash does not match the reviewed snapshot; review the original before retrying.")
        updated = fields.get("updated")
        updated_at = _timestamp(updated) if updated is not None else None
        if reference.expected_issue_updated and (updated_at is None
                or updated_at != _timestamp(reference.expected_issue_updated)):
            raise JiraReviewMismatch("The Jira issue changed since the reviewed snapshot; confirm the reviewed version before retrying.")
        _validate_excerpt(markdown, reference.original_reviewed_ac, ac_id)
        return {"draft_markdown": markdown, "provenance": {
            "source_kind": "JIRA_REVIEW_SNAPSHOT", "jira_key": jira_key,
            "jira_server": server, "field_id": reference.field_id, "field_name": name,
            "issue_updated": updated_at.isoformat() if updated_at else "",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source_hash": fingerprint,
            "original_reviewed_ac_hash": _sha(reference.original_reviewed_ac) if reference.original_reviewed_ac else "",
            "generation_lineage_verified": False,
        }}
    except JiraReviewMismatch:
        raise
    except Exception:
        # Jira errors may include credentials, tenant configuration, or source
        # content; never reflect those details through the capture endpoint.
        raise HTTPException(503, "The reviewed Jira UAC could not be verified; no source binding was created.") from None
