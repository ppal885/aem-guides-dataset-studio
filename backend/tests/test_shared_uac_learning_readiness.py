"""No live services, persistence fixtures, accounts or publication changes."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.v1.routes.test_plan_learning_readiness import router
from app.core.auth import JiraReviewIdentity, UserIdentity, get_current_user
from app.services import shared_uac_learning_readiness as readiness


def _user(**changes):
    fields = dict(id="named-person", principal_type="human", auth_method="token",
                  allowed_tenants=["team_a"],
                  jira_identity=JiraReviewIdentity(server_url="https://jira.example.test", user_key="private-key"))
    return UserIdentity(**{**fields, **changes})


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.delenv("SHARED_UAC_LEARNING_MODE", raising=False)
    monkeypatch.delenv("SHARED_UAC_LEARNING_WORKER_ENABLED", raising=False)


def test_defaults_are_configuration_only_not_learning_proof():
    result = readiness.get_shared_uac_learning_readiness(user=_user(), tenant_id="team_a")
    assert result["schema_version"] == "shared-uac-learning-readiness-v1"
    assert result["capabilities"] == {"capture": True, "reviewed_jira_uac": True}
    assert result["identity"]["personal_identity"] is True
    assert result["identity"]["jira_identity_mapping_present"] is True
    assert result["identity"]["review_authority"] == "NOT_VERIFIED_REQUIRES_LIVE_QE_ASSIGNEE"
    assert result["learning"]["configured_mode"] == "SHADOW"
    assert result["learning"]["actual_learning_proven"] is False
    assert result["learning"]["index"] == "NOT_PROBED"
    assert result["capture"]["persistence"] == "NOT_PROBED"
    assert result["capture"]["automatic_jira_comment_ingest"] is False
    assert result["worker"]["running"] is None
    assert not any(result["actions"].values())


@pytest.mark.parametrize("kind", ["service", "shared", "unknown"])
def test_nonpersonal_token_can_inspect_but_does_not_gain_review_authority(kind):
    result = readiness.get_shared_uac_learning_readiness(
        user=_user(principal_type=kind, roles=["admin"], jira_identity=None), tenant_id="team_a")
    assert result["identity"]["personal_identity"] is False
    assert result["identity"]["jira_identity_mapping_present"] is False
    assert "PERSONAL_IDENTITY_REQUIRED_FOR_QE_REVIEW" in result["warnings"]
    assert result["identity"]["review_authority"].startswith("NOT_VERIFIED")


@pytest.mark.parametrize("method", ["dev_bypass", "test_token", "unknown"])
def test_transport_must_be_real_authenticated_token(method):
    with pytest.raises(HTTPException) as error:
        readiness.get_shared_uac_learning_readiness(user=_user(auth_method=method), tenant_id="team_a")
    assert error.value.status_code == 403


def test_cross_tenant_is_denied():
    with pytest.raises(HTTPException) as error:
        readiness.get_shared_uac_learning_readiness(user=_user(), tenant_id="team_b")
    assert error.value.status_code == 403


@pytest.mark.parametrize("tenant", ["", " ", "x" * 121, "invalid-tenant", None])
def test_unbounded_or_empty_tenant_is_denied(tenant):
    with pytest.raises(HTTPException) as error:
        readiness.get_shared_uac_learning_readiness(user=_user(), tenant_id=tenant)
    assert error.value.status_code == 400


@pytest.mark.parametrize("mode", ["DISABLED", "SHADOW", "ENABLED", "unknown-config-value"])
def test_exact_canonical_mode_and_invalid_fail_closed(monkeypatch, mode):
    monkeypatch.setenv("SHARED_UAC_LEARNING_MODE", mode)
    result = readiness.get_shared_uac_learning_readiness(user=_user(), tenant_id="team_a")
    assert result["learning"]["configured_mode"] == (mode if mode != "unknown-config-value" else "DISABLED")
    assert result["learning"]["influence_configured"] is (mode == "ENABLED")
    assert result["learning"]["actual_learning_proven"] is False
    assert "unknown-config-value" not in json.dumps(result)


@pytest.mark.parametrize("setting,enabled", [("false", False), ("true", True), ("TRUE", True), (" true ", False)])
def test_worker_matches_startup_setting_but_never_claims_runtime_health(monkeypatch, setting, enabled):
    monkeypatch.setenv("SHARED_UAC_LEARNING_WORKER_ENABLED", setting)
    result = readiness.get_shared_uac_learning_readiness(user=_user(), tenant_id="team_a")
    assert result["worker"]["configured_enabled"] is enabled
    assert result["worker"]["running"] is None
    assert result["worker"]["status"] == ("CONFIGURED_ENABLED_RUNTIME_UNVERIFIED" if enabled else "CONFIGURED_PAUSED")


def test_no_secret_profile_or_correction_data_returned(monkeypatch):
    monkeypatch.setenv("AUTH_TOKENS_JSON", "private-token-settings")
    monkeypatch.setenv("DATABASE_URL", "private-db-credential")
    user = _user(id="private-person-id", email="private@example.test", name="Private Name")
    result = json.dumps(readiness.get_shared_uac_learning_readiness(user=user, tenant_id="team_a"))
    for secret in ["private-token-settings", "private-db-credential", "private-person-id",
                   "private@example.test", "Private Name", "private-key", "https://jira.example.test"]:
        assert secret not in result


def _client(user):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_http_route_no_store_and_no_persistence_dependency():
    response = _client(_user()).get("/api/v1/test-plan-learning/readiness?tenant_id=team_a")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["capabilities"]["reviewed_jira_uac"] is True


def test_http_cross_tenant_error_is_sanitized():
    response = _client(_user(id="secret-user")).get("/api/v1/test-plan-learning/readiness?tenant_id=private_tenant")
    assert response.status_code == 403
    assert "secret-user" not in response.text
    assert "private_tenant" not in response.text


def test_http_requires_tenant_and_rejects_dev_identity():
    assert _client(_user()).get("/api/v1/test-plan-learning/readiness").status_code == 422
    assert _client(_user(auth_method="dev_bypass")).get(
        "/api/v1/test-plan-learning/readiness?tenant_id=team_a").status_code == 403


def test_http_missing_token_is_unauthorized_not_readiness(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_DEV_AUTH_BYPASS", "false")
    monkeypatch.setenv("AUTH_TOKENS_JSON", "{}")
    monkeypatch.delenv("ADMIN_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("API_BEARER_TOKEN", raising=False)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    response = TestClient(app).get("/api/v1/test-plan-learning/readiness?tenant_id=team_a")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_http_malformed_tenant_is_bounded_error():
    response = _client(_user()).get("/api/v1/test-plan-learning/readiness?tenant_id=invalid-tenant")
    assert response.status_code == 400
    assert "invalid-tenant" not in response.text


def test_http_does_not_accept_client_supplied_identity_claims():
    response = _client(_user(principal_type="service", jira_identity=None)).get(
        "/api/v1/test-plan-learning/readiness?tenant_id=team_a&principal_type=human&review_authority=APPROVED")
    assert response.status_code == 200
    assert response.json()["identity"]["personal_identity"] is False
    assert response.json()["identity"]["review_authority"].startswith("NOT_VERIFIED")


def test_fresh_process_does_not_import_or_initialize_persistence_network_or_runtime(tmp_path):
    # No backend startup/conftest fixture: a readiness import/call must stand alone.
    backend = Path(__file__).resolve().parents[1]
    script = '''
import os, socket, sys
def forbidden(*args, **kwargs):
    raise AssertionError("READINESS_UNEXPECTED_IO")
socket.socket.connect = forbidden
from app.core.auth import UserIdentity
from app.services.shared_uac_learning_readiness import get_shared_uac_learning_readiness
from app.services import tenant_service
tenant_service.get_storage = forbidden
os.mkdir = forbidden
user = UserIdentity(id="person", auth_method="token", principal_type="human", allowed_tenants=["team_a"])
result = get_shared_uac_learning_readiness(user=user, tenant_id="team_a")
assert not any(result["actions"].values())
for name in ("app.db.session", "app.services.shared_uac_learning_service", "app.main", "chromadb", "sentence_transformers"):
    assert name not in sys.modules, name
print("READINESS_NO_PERSISTENCE_OR_RUNTIME_IMPORT")
'''
    env = {**os.environ, "PYTHONPATH": str(backend), "PYTHONDONTWRITEBYTECODE": "1"}
    run = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env,
                         capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    assert "READINESS_NO_PERSISTENCE_OR_RUNTIME_IMPORT" in run.stdout
    assert list(tmp_path.iterdir()) == []
