"""Fresh Jira QE Assignee authorization, distinct from ordinary issue assignment.

Only server-configured Jira identity mappings are considered. A display name,
email, submitter identity, administrator role, or standard Assignee never grants
review rights. Authorization reads are uncached, bounded, and TLS-verified.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
import time
from urllib.parse import urlsplit

from fastapi import HTTPException
import httpx

from app.services.jira_client import JiraClient
from app.services.tenant_service import ensure_user_can_access_tenant, get_tenant


_ISSUE_KEY = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
_CUSTOM_FIELD = re.compile(r"^customfield_[1-9][0-9]{0,9}$")
_MAX_RESPONSE_BYTES = 512_000
_READ_DEADLINE_SECONDS = 8.0
_DENIED = "Live Jira QE Assignee authorization was not confirmed."
_UNAVAILABLE = "Live Jira QE Assignee verification is unavailable; no review was authorized."


def _deny():
    raise HTTPException(403, _DENIED)


def _origin(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"} or any(ord(char) < 33 for char in value)):
        raise ValueError("Invalid pinned Jira origin")
    port = parsed.port
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    return f"https://{host}" + (f":{port}" if port and port != 443 else "")


def _stable_identifier(value) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 255:
        _deny()
    if any(ord(char) < 33 or ord(char) == 127 for char in value):
        _deny()
    return value


class _QeAuthorizationJiraClient(JiraClient):
    """Reuse Jira's raw issue contract without its broad fallback/retry settings."""

    def __init__(self, *, server_url: str, auth=None, bearer_token: str = ""):
        # Do not call the legacy constructor: it silently merges global credentials
        # into explicitly configured tenant credentials, including a global PAT.
        self.base_url = server_url
        self._auth = auth
        self.bearer_token = bearer_token
        self._api = os.getenv("JIRA_API_VERSION", "2").strip()
        if self._api not in {"2", "3"}:
            raise ValueError("Unsupported Jira API version")

    def _request(self, method, path, params=None, json_data=None):
        if method != "GET" or not re.fullmatch(r"/rest/api/[23]/issue/[A-Z][A-Z0-9]+-\d+", path):
            raise ValueError("Unsupported authorization read")
        deadline = time.monotonic() + _READ_DEADLINE_SECONDS
        timeout = httpx.Timeout(connect=3.0, read=2.0, write=2.0, pool=1.0)
        # No shared token-bucket wait: that limiter can block indefinitely. This
        # bounded read performs one request, follows no redirects, and never retries.
        with httpx.Client(auth=self._auth, timeout=timeout, verify=True, follow_redirects=False) as client:
            headers = self._headers()
            headers["cache-control"] = "no-cache, no-store"
            with client.stream(method, self.base_url + path, params=params, headers=headers) as response:
                if response.status_code != 200:
                    raise ValueError("Jira authorization read was not successful")
                chunks = []
                size = 0
                for chunk in response.iter_bytes():
                    if time.monotonic() > deadline:
                        raise TimeoutError("Jira authorization read exceeded its deadline")
                    size += len(chunk)
                    if size > _MAX_RESPONSE_BYTES:
                        raise ValueError("Jira authorization response is oversized")
                    chunks.append(chunk)
                if time.monotonic() > deadline:
                    raise TimeoutError("Jira authorization read exceeded its deadline")
                payload = json.loads(b"".join(chunks))
                if not isinstance(payload, dict):
                    raise ValueError("Jira authorization response is not an object")
                return payload


def _tenant_client(config, server_url: str) -> _QeAuthorizationJiraClient:
    email = str(config.jira_email or "").strip()
    tenant_token = str(config.jira_token or "").strip()
    if email or tenant_token:
        if not (email and tenant_token):
            raise ValueError("Incomplete tenant Jira credentials")
        return _QeAuthorizationJiraClient(server_url=server_url, auth=httpx.BasicAuth(email, tenant_token))

    # Global credentials are permitted only for an explicitly configured tenant
    # whose Jira origin is identical. Never fallback after tenant lookup failure.
    global_url = os.getenv("JIRA_BASE_URL") or os.getenv("JIRA_URL", "")
    if _origin(global_url) != server_url:
        raise ValueError("Global Jira credentials belong to a different origin")
    bearer = os.getenv("JIRA_BEARER_TOKEN") or os.getenv("JIRA_PAT", "")
    if bearer:
        if any(ord(char) < 33 or ord(char) == 127 for char in bearer):
            raise ValueError("Invalid Jira credential configuration")
        return _QeAuthorizationJiraClient(server_url=server_url, bearer_token=bearer)
    username = os.getenv("JIRA_USERNAME", "")
    password = os.getenv("JIRA_PASSWORD", "")
    api_token = os.getenv("JIRA_API_TOKEN", "")
    global_email = os.getenv("JIRA_EMAIL", "")
    if username and password:
        auth = httpx.BasicAuth(username, password)
    elif username and api_token:
        auth = httpx.BasicAuth(username, api_token)
    elif global_email and api_token:
        auth = httpx.BasicAuth(global_email, api_token)
    else:
        raise ValueError("Jira authority credentials are not configured")
    return _QeAuthorizationJiraClient(server_url=server_url, auth=auth)


def authorize_qe_review(user, *, tenant_id: str, jira_key: str) -> dict:
    """Authorize the current named Human against the live QE Assignee only.

    All error text is constant: Jira responses, configuration, profile attributes,
    submitted values, and credentials are never returned or logged on failure.
    """
    try:
        if (getattr(user, "principal_type", "unknown") != "human"
                or getattr(user, "auth_method", "unknown") != "token"
                or not str(getattr(user, "id", "")).strip()
                or str(user.id).lower() in {"unknown-user", "dev-user", "system"}):
            _deny()
        tenant = ensure_user_can_access_tenant(user, tenant_id)
        if not isinstance(jira_key, str) or not _ISSUE_KEY.fullmatch(jira_key):
            _deny()
        mapping = getattr(user, "jira_identity", None)
        if mapping is None:
            _deny()
        user_key = getattr(mapping, "user_key", "")
        account_id = getattr(mapping, "account_id", "")
        if bool(user_key) == bool(account_id):
            _deny()
        identity_kind, response_key, identity_value = (
            ("user_key", "key", _stable_identifier(user_key)) if user_key
            else ("account_id", "accountId", _stable_identifier(account_id)))
        config = get_tenant(tenant)
        if config.is_active is not True:
            _deny()
        server_url = _origin(str(config.jira_url or ""))
        if _origin(str(getattr(mapping, "server_url", ""))) != server_url:
            _deny()
        field_id = os.getenv("SHARED_UAC_QE_FIELD_ID", "customfield_18512").strip()
        if not _CUSTOM_FIELD.fullmatch(field_id):
            raise ValueError("Invalid QE field configuration")
        client = _tenant_client(config, server_url)
        issue = client.get_issue_with_names(jira_key, fields=f"{field_id},updated")
        if not isinstance(issue, dict) or issue.get("key") != jira_key:
            _deny()
        fields, names = issue.get("fields"), issue.get("names")
        if not isinstance(fields, dict) or not isinstance(names, dict):
            _deny()
        if names.get(field_id) != "QE Assignee" or sum(name == "QE Assignee" for name in names.values()) != 1:
            _deny()
        assignee = fields.get(field_id)
        if not isinstance(assignee, dict) or assignee.get("active") is not True:
            _deny()
        if _stable_identifier(assignee.get(response_key)) != identity_value:
            _deny()
        proof = {"policy": "LIVE_JIRA_QE_ASSIGNEE", "jira_key": jira_key,
            "jira_server": server_url, "field_id": field_id, "field_name": "QE Assignee",
            "identity_kind": identity_kind, "identity_value": identity_value,
            "checked_at": datetime.now(timezone.utc).isoformat()}
        updated = fields.get("updated")
        if updated is not None:
            if not isinstance(updated, str) or len(updated) > 80:
                raise ValueError("Invalid issue update timestamp")
            parsed_updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            if parsed_updated.tzinfo is None:
                raise ValueError("Issue update timestamp lacks timezone")
            proof["issue_updated"] = parsed_updated.isoformat()
        return proof
    except HTTPException as exc:
        raise HTTPException(403 if exc.status_code in {401, 403, 404} else 503,
            _DENIED if exc.status_code in {401, 403, 404} else _UNAVAILABLE) from None
    except Exception:
        raise HTTPException(503, _UNAVAILABLE) from None
