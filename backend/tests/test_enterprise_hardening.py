import json

from app.api.v1.routes import ai_dataset
from app.core.runtime_safety import validate_runtime_safety


def test_runtime_safety_blocks_production_dev_bypass_and_wildcard(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_DEV_AUTH_BYPASS", "true")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    monkeypatch.delenv("AUTH_TOKENS_JSON", raising=False)
    monkeypatch.delenv("API_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("ADMIN_BEARER_TOKEN", raising=False)

    result = validate_runtime_safety()

    assert result["errors"]
    combined = " ".join(result["errors"]).lower()
    assert "allow_dev_auth_bypass" in combined
    assert "wildcard cors" in combined
    assert "bearer token" in combined


def test_runtime_safety_allows_production_when_auth_and_cors_are_configured(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_DEV_AUTH_BYPASS", "false")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://studio.internal.example")
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

    result = validate_runtime_safety()

    assert result["errors"] == []


def test_generate_status_is_scoped_to_owner_and_tenant(client, monkeypatch):
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
                },
                "other-token": {
                    "id": "writer-2",
                    "email": "writer2@example.com",
                    "roles": ["writer"],
                    "allowed_tenants": ["acme"],
                },
            }
        ),
    )

    run_id = "run-secure-123"
    ai_dataset._generate_progress[run_id] = {
        "status": "running",
        "user_id": "writer-1",
        "tenant_id": "kone",
    }

    try:
        response = client.get(
            f"/api/v1/ai/generate-status/{run_id}",
            headers={"Authorization": "Bearer other-token", "X-Tenant-ID": "acme"},
        )
        assert response.status_code == 404
    finally:
        ai_dataset._generate_progress.pop(run_id, None)


def test_agentic_config_patch_is_admin_only(client, monkeypatch):
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

    response = client.patch(
        "/api/v1/ai/agentic-config",
        headers={"Authorization": "Bearer writer-token"},
        json={"max_validation_retries": 9},
    )

    assert response.status_code == 403
