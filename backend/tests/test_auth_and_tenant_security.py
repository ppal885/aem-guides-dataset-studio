import json
import shutil
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.core import auth as auth_module
from app.services import tenant_service


def _request(headers: dict[str, str] | None = None) -> Request:
    normalized_headers = [
        (key.lower().encode("utf-8"), value.encode("utf-8"))
        for key, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": normalized_headers,
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def test_missing_auth_rejected_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_DEV_AUTH_BYPASS", "false")
    monkeypatch.delenv("AUTH_TOKENS_JSON", raising=False)
    monkeypatch.delenv("API_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("ADMIN_BEARER_TOKEN", raising=False)

    request = _request()
    with pytest.raises(HTTPException) as exc:
        auth_module.get_current_user(request=request, credentials=None)

    assert exc.value.status_code == 401


def test_static_token_auth_returns_scoped_user(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_DEV_AUTH_BYPASS", "false")
    monkeypatch.setenv(
        "AUTH_TOKENS_JSON",
        json.dumps(
            {
                "writer-token": {
                    "id": "writer-1",
                    "email": "writer@example.com",
                    "roles": ["writer"],
                    "allowed_tenants": ["kone"],
                }
            }
        ),
    )

    request = _request({"Authorization": "Bearer writer-token"})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="writer-token")
    user = auth_module.get_current_user(request=request, credentials=credentials)

    assert user.id == "writer-1"
    assert user.allowed_tenants == ["kone"]
    assert request.state.user.id == "writer-1"


def test_tenant_access_is_enforced(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    user = auth_module.UserIdentity(id="writer-1", roles=["writer"], allowed_tenants=["kone"])

    request = _request({"X-Tenant-ID": "acme"})
    with pytest.raises(HTTPException) as exc:
        tenant_service.get_authorized_tenant_id(request, user)

    assert exc.value.status_code == 403


def test_chat_route_rejects_unauthorized_tenant_header(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_DEV_AUTH_BYPASS", "false")
    monkeypatch.setenv(
        "AUTH_TOKENS_JSON",
        json.dumps(
            {
                "writer-token": {
                    "id": "writer-1",
                    "email": "writer@example.com",
                    "roles": ["writer"],
                    "allowed_tenants": ["kone"],
                }
            }
        ),
    )

    session_response = client.post(
        "/api/v1/chat/sessions",
        headers={"Authorization": "Bearer writer-token"},
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["session_id"]

    response = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        headers={
            "Authorization": "Bearer writer-token",
            "X-Tenant-ID": "acme",
        },
        json={"content": "Summarize this issue"},
    )

    assert response.status_code == 403
    assert "tenant" in response.text.lower()


def test_rag_status_route_rejects_unauthorized_tenant_header(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_DEV_AUTH_BYPASS", "false")
    monkeypatch.setenv(
        "AUTH_TOKENS_JSON",
        json.dumps(
            {
                "writer-token": {
                    "id": "writer-1",
                    "email": "writer@example.com",
                    "roles": ["writer"],
                    "allowed_tenants": ["kone"],
                }
            }
        ),
    )

    response = client.get(
        "/api/v1/ai/rag-status",
        headers={
            "Authorization": "Bearer writer-token",
            "X-Tenant-ID": "acme",
        },
    )

    assert response.status_code == 403
    assert "tenant" in response.text.lower()


def test_tenant_token_is_persisted_encrypted(monkeypatch):
    monkeypatch.setenv("TENANT_SECRET_KEY", "unit-test-tenant-secret")
    monkeypatch.setenv("ALLOW_PLAINTEXT_TENANT_SECRETS", "false")
    temp_root = Path(__file__).resolve().parents[1] / ".test_workdirs"
    temp_root.mkdir(parents=True, exist_ok=True)
    tenants_dir = temp_root / f"tenant-secrets-{uuid.uuid4().hex}"
    shutil.rmtree(tenants_dir, ignore_errors=True)
    tenants_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tenant_service, "_tenants_dir", lambda: tenants_dir)

    try:
        created = tenant_service.create_tenant(
            tenant_id="securetenant",
            name="Secure Tenant",
            jira_url="https://jira.example.com",
            jira_token="super-secret-token",
            jira_email="jira@example.com",
        )

        raw_payload = json.loads(
            (tenants_dir / "securetenant" / "config.json").read_text(encoding="utf-8")
        )
        assert created.jira_token == "super-secret-token"
        assert raw_payload.get("jira_token_encrypted", "").startswith("enc:v1:")
        assert "jira_token" not in raw_payload

        loaded = tenant_service.get_tenant("securetenant")
        assert loaded.jira_token == "super-secret-token"
    finally:
        shutil.rmtree(tenants_dir, ignore_errors=True)


def test_get_tenant_default_resolves_to_builtin_kone():
    """Settings UI and RAG routes pass tenant_id=default; must map to built-in tenant, not raise."""
    cfg = tenant_service.get_tenant("default")
    assert cfg.tenant_id == tenant_service.DEFAULT_TENANT
    assert cfg.rag_collection == f"{tenant_service.DEFAULT_TENANT}_rag"


def test_x_tenant_id_default_allowed_when_user_has_kone(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    user = auth_module.UserIdentity(id="writer-1", roles=["writer"], allowed_tenants=["kone"])
    request = _request({"X-Tenant-ID": "default"})
    assert tenant_service.get_authorized_tenant_id(request, user) == "kone"
