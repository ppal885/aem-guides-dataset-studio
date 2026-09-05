"""Server identity provenance for shared-learning authorization (no live accounts)."""

import json

from app.core import auth


def test_untyped_identity_is_not_implicitly_human():
    assert auth.UserIdentity(id="individual").principal_type == "unknown"
    assert auth.UserIdentity(id="individual").jira_identity is None


def test_configured_named_identity_keeps_server_owned_type(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("ADMIN_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("API_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("AUTH_TOKENS_JSON", json.dumps({
        "synthetic-test-credential": {
            "id": "named-reviewer", "principal_type": "human",
            "roles": ["uac_learning_reviewer"], "allowed_tenants": ["team-a"],
            "jira_identity": {"server_url": "https://jira.example.test", "user_key": "synthetic-key"},
        }
    }))
    identity = auth._load_token_config_map()["synthetic-test-credential"]
    assert identity.principal_type == "human"
    assert identity.auth_method == "token"
    assert identity.allowed_tenants == ["team-a"]
    assert identity.roles == ["uac_learning_reviewer"]
    assert identity.jira_identity.user_key == "synthetic-key"
    assert identity.jira_identity.server_url == "https://jira.example.test"


def test_shared_and_service_shortcuts_cannot_become_named_reviewers(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("AUTH_TOKENS_JSON", raising=False)
    monkeypatch.setenv("ADMIN_BEARER_TOKEN", "synthetic-admin-credential")
    monkeypatch.setenv("API_BEARER_TOKEN", "synthetic-service-credential")
    monkeypatch.setenv("API_BEARER_ROLES", "admin,uac_learning_reviewer")
    identities = auth._load_token_config_map()
    assert identities["synthetic-admin-credential"].principal_type == "shared"
    assert identities["synthetic-service-credential"].principal_type == "service"
    assert identities["synthetic-admin-credential"].jira_identity is None
    assert identities["synthetic-service-credential"].jira_identity is None
    assert auth._default_dev_user().principal_type == "shared"


def test_bad_identity_type_fails_closed_without_breaking_legacy_auth():
    identity = auth._build_identity(
        {"id": "named-reviewer", "principal_type": "HUMAN_CONFIRMED_BY_MODEL"},
        auth_method="token",
    )
    assert identity.principal_type == "unknown"


def test_malformed_jira_mapping_only_disables_review_not_existing_auth():
    malformed = [
        {"server_url": "https://jira.example.test", "displayName": "Same display name"},
        {"server_url": "https://jira.example.test", "user_key": "a", "account_id": "b"},
        {"server_url": "https://jira.example.test", "user_key": True},
        {"server_url": "https://jira.example.test", "user_key": "   "},
        {"server_url": "https://jira.example.test", "user_key": "key\nvalue"},
        "client-supplied-name",
    ]
    for mapping in malformed:
        identity = auth._build_identity({"id": "person", "principal_type": "human",
            "jira_identity": mapping}, auth_method="token")
        assert identity.id == "person" and identity.principal_type == "human"
        assert identity.jira_identity is None


def test_cloud_identity_uses_account_id_without_username_inference():
    identity = auth._build_identity({"id": "person", "principal_type": "human",
        "jira_identity": {"server_url": "https://jira.example.test", "account_id": "cloud-user"}}, auth_method="token")
    assert identity.jira_identity.account_id == "cloud-user"
    assert identity.jira_identity.user_key == ""
