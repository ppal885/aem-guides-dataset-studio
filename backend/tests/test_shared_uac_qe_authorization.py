"""Isolated live-QE authorization contracts; all Jira reads are synthetic mocks."""
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

from fastapi import HTTPException
import httpx
import pytest

from app.services import shared_uac_qe_authorization as authorization


def person(**changes):
    values = dict(id="named-person", auth_method="token", principal_type="human",
        roles=[], is_admin=False, allowed_tenants=["kone"],
        jira_identity=SimpleNamespace(server_url="https://jira.example", user_key="qe-key-1", account_id=""))
    values.update(changes)
    return SimpleNamespace(**values)


def issue(key="TEST-123", *, qe=None):
    return {"key": key, "names": {"customfield_18512": "QE Assignee"}, "fields": {
        "customfield_18512": qe if qe is not None else {"key": "qe-key-1", "active": True,
            "displayName": "Synthetic QE", "emailAddress": "synthetic-qe@example.com"},
        "assignee": {"key": "standard-assignee", "active": True},
        "updated": "2026-09-06T00:00:00.000+0000"}}


@pytest.fixture
def authority(monkeypatch):
    for name in ("JIRA_BASE_URL", "JIRA_URL", "JIRA_BEARER_TOKEN", "JIRA_PAT", "JIRA_USERNAME",
                 "JIRA_PASSWORD", "JIRA_API_TOKEN", "JIRA_EMAIL", "JIRA_API_VERSION", "SHARED_UAC_QE_FIELD_ID"):
        monkeypatch.delenv(name, raising=False)
    config = SimpleNamespace(jira_url="https://jira.example", jira_email="synthetic-service@example.com",
        jira_token="synthetic-tenant-token", is_active=True)
    monkeypatch.setattr(authorization, "get_tenant", lambda tenant: config)
    response = issue()
    calls = []

    def get_issue(self, key, fields=None):
        calls.append({"key": key, "fields": fields, "server": self.base_url,
            "auth": self._auth, "bearer": self.bearer_token})
        return deepcopy(response)

    monkeypatch.setattr(authorization._QeAuthorizationJiraClient, "get_issue_with_names", get_issue)
    return SimpleNamespace(config=config, response=response, calls=calls)


def authorize(user=None):
    return authorization.authorize_qe_review(user or person(), tenant_id="kone", jira_key="TEST-123")


def test_exact_live_qe_identity_gets_minimal_proof_not_standard_assignee(authority):
    proof = authorize()
    assert proof["policy"] == "LIVE_JIRA_QE_ASSIGNEE"
    assert proof["identity_kind"] == "user_key" and proof["identity_value"] == "qe-key-1"
    assert proof["field_id"] == "customfield_18512" and proof["field_name"] == "QE Assignee"
    assert proof["jira_server"] == "https://jira.example" and proof["issue_updated"]
    assert authority.calls[0]["fields"] == "customfield_18512,updated"
    assert "emailAddress" not in proof and "displayName" not in proof
    assert "synthetic-tenant-token" not in str(proof)
    standard = person(jira_identity=SimpleNamespace(server_url="https://jira.example",
        user_key="standard-assignee", account_id=""), roles=["admin", "uac_learning_reviewer"], is_admin=True)
    with pytest.raises(HTTPException) as error:
        authorize(standard)
    assert error.value.status_code == 403


def test_cloud_account_identity_is_typed_and_exact(authority):
    authority.response["fields"]["customfield_18512"] = {"accountId": "cloud-account-1", "active": True}
    mapped = person(jira_identity=SimpleNamespace(server_url="https://jira.example",
        user_key="", account_id="cloud-account-1"))
    assert authorize(mapped)["identity_kind"] == "account_id"
    authority.response["fields"]["customfield_18512"] = {"key": "cloud-account-1", "active": True}
    with pytest.raises(HTTPException) as error:
        authorize(mapped)
    assert error.value.status_code == 403


@pytest.mark.parametrize("qe", [None, {}, {"key": "qe-key-1"}, {"key": "qe-key-1", "active": False},
    [{"key": "qe-key-1", "active": True}], {"name": "qe-key-1", "active": True},
    {"displayName": "qe-key-1", "emailAddress": "qe-key-1", "active": True}])
def test_missing_inactive_ambiguous_or_name_only_field_never_authorizes(authority, qe):
    authority.response["fields"]["customfield_18512"] = qe
    with pytest.raises(HTTPException) as error:
        authorize()
    assert error.value.status_code == 403


@pytest.mark.parametrize("names", [{}, {"customfield_18512": "Assignee"},
    {"customfield_18512": "QE Assignee", "customfield_19999": "QE Assignee"}])
def test_field_name_must_be_exact_and_unambiguous(authority, names):
    authority.response["names"] = names
    with pytest.raises(HTTPException) as error:
        authorize()
    assert error.value.status_code == 403


@pytest.mark.parametrize("changes", [{"principal_type": "service"}, {"principal_type": "shared"},
    {"auth_method": "dev_bypass"}, {"id": "unknown-user"}, {"allowed_tenants": ["other"]},
    {"jira_identity": None}])
def test_nonhuman_dev_cross_tenant_and_missing_mapping_fail_before_http(authority, changes):
    with pytest.raises(HTTPException) as error:
        authorize(person(**changes))
    assert error.value.status_code == 403 and authority.calls == []


@pytest.mark.parametrize("mapping", [
    SimpleNamespace(server_url="https://other.example", user_key="qe-key-1", account_id=""),
    SimpleNamespace(server_url="https://jira.example", user_key="qe-key-1", account_id="cloud-account"),
    SimpleNamespace(server_url="https://jira.example", user_key="", account_id=""),
])
def test_wrong_origin_or_ambiguous_mapping_fails_before_http(authority, mapping):
    with pytest.raises(HTTPException) as error:
        authorize(person(jira_identity=mapping))
    assert error.value.status_code == 403 and authority.calls == []


def test_every_authorization_reads_current_assignment_and_reassignment_denies(authority):
    authorize()
    authority.response["fields"]["customfield_18512"]["key"] = "new-qe-key"
    with pytest.raises(HTTPException) as error:
        authorize()
    assert error.value.status_code == 403 and len(authority.calls) == 2


def test_unknown_or_inactive_tenant_never_falls_back(authority, monkeypatch):
    authority.config.is_active = False
    with pytest.raises(HTTPException):
        authorize()
    def unknown(tenant):
        raise ValueError("synthetic-sensitive-tenant-error")
    monkeypatch.setattr(authorization, "get_tenant", unknown)
    with pytest.raises(HTTPException) as error:
        authorize()
    assert error.value.status_code == 503 and "synthetic-sensitive" not in error.value.detail
    assert authority.calls == []


def test_explicit_tenant_credentials_are_not_overridden_by_global_pat(authority, monkeypatch):
    monkeypatch.setenv("JIRA_PAT", "synthetic-global-token")
    monkeypatch.setenv("JIRA_BASE_URL", "https://other.example")
    authorize()
    assert isinstance(authority.calls[0]["auth"], httpx.BasicAuth)
    assert authority.calls[0]["bearer"] == ""


def test_global_credentials_require_matching_explicit_tenant_origin(authority, monkeypatch):
    authority.config.jira_email = authority.config.jira_token = ""
    monkeypatch.setenv("JIRA_PAT", "synthetic-global-token")
    monkeypatch.setenv("JIRA_BASE_URL", "https://other.example")
    with pytest.raises(HTTPException) as error:
        authorize()
    assert error.value.status_code == 503 and authority.calls == []
    monkeypatch.setenv("JIRA_BASE_URL", "https://jira.example:443/")
    authorize()
    assert authority.calls[-1]["bearer"] == "synthetic-global-token"
    authority.config.jira_url = ""
    with pytest.raises(HTTPException):
        authorize()
    assert len(authority.calls) == 1


def test_partial_tenant_credentials_do_not_trigger_global_fallback(authority, monkeypatch):
    authority.config.jira_email = ""
    monkeypatch.setenv("JIRA_BASE_URL", "https://jira.example")
    monkeypatch.setenv("JIRA_PAT", "synthetic-global-token")
    with pytest.raises(HTTPException) as error:
        authorize()
    assert error.value.status_code == 503 and authority.calls == []


def test_timeout_and_auth_errors_are_redacted_without_retry(authority, monkeypatch):
    calls = []
    def fail(self, key, fields=None):
        calls.append(key)
        raise httpx.ReadTimeout("Bearer synthetic-sensitive-token; raw profile")
    monkeypatch.setattr(authorization._QeAuthorizationJiraClient, "get_issue_with_names", fail)
    with pytest.raises(HTTPException) as error:
        authorize()
    assert error.value.status_code == 503 and "synthetic-sensitive" not in str(error.value)
    assert len(calls) == 1


@pytest.mark.parametrize("status", [200, 302, 401, 403])
def test_transport_enforces_tls_no_redirects_bounded_timeout_and_minimal_fields(monkeypatch, status):
    monkeypatch.setenv("JIRA_SSL_VERIFY", "false")
    monkeypatch.setenv("JIRA_API_VERSION", "2")
    observed = []
    class FakeClient:
        def __init__(self, **kwargs):
            observed.append(kwargs)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        @contextmanager
        def stream(self, method, url, **kwargs):
            observed.append({"method": method, "url": url, **kwargs})
            yield httpx.Response(status, json=issue())
    monkeypatch.setattr(httpx, "Client", FakeClient)
    client = authorization._QeAuthorizationJiraClient(server_url="https://jira.example", bearer_token="synthetic-token")
    if status == 200:
        assert client.get_issue_with_names("TEST-123", fields="customfield_18512,updated")["key"] == "TEST-123"
    else:
        with pytest.raises(ValueError):
            client.get_issue_with_names("TEST-123", fields="customfield_18512,updated")
    assert observed[0]["verify"] is True and observed[0]["follow_redirects"] is False
    assert observed[0]["timeout"].connect == 3 and observed[0]["timeout"].read == 2
    assert observed[1]["params"] == {"expand": "names", "fields": "customfield_18512,updated"}
    assert observed[1]["headers"]["cache-control"] == "no-cache, no-store"
    assert len(observed) == 2
