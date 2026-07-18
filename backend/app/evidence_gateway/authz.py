from __future__ import annotations

import json
import os

from app.core.auth import UserIdentity
from app.evidence_gateway.config import EvidenceGatewaySettings


def _roles(user: UserIdentity) -> set[str]:
    return {role.lower() for role in (user.roles or [])}


def _user_keys(user: UserIdentity) -> set[str]:
    return {item for item in (user.id, user.email or "") if item}


def _grant_map() -> dict[str, dict]:
    raw = os.getenv("EVIDENCE_USER_GRANTS_JSON", "").strip()
    if not raw:
        return {}
    payload = json.loads(raw)
    return payload if isinstance(payload, dict) else {}


def ensure_gateway_access(user: UserIdentity, settings: EvidenceGatewaySettings) -> None:
    required = settings.required_role.strip().lower()
    if required and required not in _roles(user):
        raise PermissionError("User is not authorized for the evidence gateway.")


def authorized_corpora(user: UserIdentity, settings: EvidenceGatewaySettings) -> set[str]:
    ensure_gateway_access(user, settings)
    if user.is_admin:
        return set(settings.corpora)
    grants = _grant_map()
    for key in _user_keys(user):
        entry = grants.get(key)
        if isinstance(entry, dict):
            return set(entry.get("corpora") or settings.default_corpora) & set(settings.corpora)
    return set(settings.default_corpora) & set(settings.corpora)


def authorized_repositories(user: UserIdentity, settings: EvidenceGatewaySettings) -> set[str]:
    ensure_gateway_access(user, settings)
    if user.is_admin:
        return set(settings.repositories)
    grants = _grant_map()
    for key in _user_keys(user):
        entry = grants.get(key)
        if isinstance(entry, dict):
            return set(entry.get("repositories") or ()) & set(settings.repositories)
    return set()


def require_corpora(user: UserIdentity, settings: EvidenceGatewaySettings, requested: list[str]) -> list[str]:
    allowed = authorized_corpora(user, settings)
    requested_ids = requested or sorted(allowed)
    denied = [corpus for corpus in requested_ids if corpus not in allowed]
    if denied:
        raise PermissionError("One or more requested corpora are not authorized.")
    return requested_ids


def require_repository(user: UserIdentity, settings: EvidenceGatewaySettings, alias: str) -> None:
    if alias not in authorized_repositories(user, settings):
        raise PermissionError("Requested repository is not authorized.")

