"""Fresh-review remote MCP transport proofs without backend startup or live IO."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_current_user
from app.db import session as session_module
from app.db.base import Base
from app.db.shared_uac_learning_models import (
    UacFeedbackBinding, UacFeedbackDelta, UacLearningDraft, UacLearningOutbox, UacLessonRevision,
)
from app.services import shared_uac_qe_authorization as jira_authority
from test_shared_uac_learning import db as learning_db, person
from test_shared_uac_learning_cross_client import capture_body, headers, rpc, shared_client


FIELD = "customfield_13400"
MARKDOWN = "## Acceptance Criteria\nAC-01: Generate the output."
PIN = {"field_id": FIELD, "expected_sha256": hashlib.sha256(MARKDOWN.encode()).hexdigest(),
       "original_reviewed_ac": "Generate the output."}


@pytest.fixture
def remote_jira(shared_client, monkeypatch):
    original = jira_authority._QeAuthorizationJiraClient.get_issue_with_names
    state = {"text": MARKDOWN, "calls": []}

    def read(client, key, fields=None):
        state["calls"].append(fields)
        if fields == "customfield_18512,updated":
            return original(client, key, fields)
        assert fields == FIELD + ",updated"
        if state.get("fail"):
            raise RuntimeError("synthetic-sensitive-upstream-detail")
        return {"key": key, "fields": {FIELD: state["text"], "updated": "2026-09-07T09:00:00Z"},
                "names": {FIELD: "Acceptance Criteria"}}

    monkeypatch.delenv("JIRA_ACCEPTANCE_CRITERIA_FIELD_ID", raising=False)
    monkeypatch.setattr(jira_authority._QeAuthorizationJiraClient, "get_issue_with_names", read)
    return state


def _error(client, name, arguments, actor="claude"):
    response = client.post("/mcp", headers=headers(actor), json={"id": 10, "method": "tools/call",
        "params": {"name": name, "arguments": arguments}})
    assert response.status_code == 200
    envelope = response.json()
    if "error" in envelope:
        assert envelope["error"]["code"] == -32602
        return {"http_status": 422, "response": response.text}
    assert envelope["result"]["isError"] is True
    return {**json.loads(envelope["result"]["content"][0]["text"]), "response": response.text}


def _counts(factory):
    with factory() as db:
        return tuple(db.query(model).count() for model in (
            UacLearningDraft, UacFeedbackDelta, UacFeedbackBinding, UacLessonRevision, UacLearningOutbox))


def test_remote_readiness_never_constructs_session_or_checks_jira(shared_client, remote_jira, monkeypatch):
    client, _factory = shared_client

    def forbidden():
        pytest.fail("Readiness constructed a SQL session")

    monkeypatch.setattr(session_module, "SessionLocal", forbidden)
    result = rpc(client, "get_uac_feedback_readiness", {"tenant_id": "team_a"}, "qe")
    assert result["status"] == "CONFIGURATION_ONLY"
    assert result["identity"]["jira_identity_mapping_present"] is True
    assert result["identity"]["review_authority"] == "NOT_VERIFIED_REQUIRES_LIVE_QE_ASSIGNEE"
    assert result["capture"]["persistence"] == result["learning"]["publication"] == "NOT_PROBED"
    assert result["learning"]["actual_learning_proven"] is False
    assert not any(result["actions"].values())
    assert remote_jira["calls"] == []


def test_remote_readiness_denies_cross_tenant_and_identity_claims_without_session(shared_client, monkeypatch):
    client, _factory = shared_client
    monkeypatch.setattr(session_module, "SessionLocal", lambda: pytest.fail("Readiness constructed a SQL session"))
    denied = _error(client, "get_uac_feedback_readiness", {"tenant_id": "team_a"}, "other")
    assert denied["http_status"] == 403
    spoofed = _error(client, "get_uac_feedback_readiness", {
        "tenant_id": "team_a", "review_authority": "synthetic-sensitive-approval"})
    assert spoofed["http_status"] == 422
    assert "synthetic-sensitive-approval" not in spoofed["response"]
    unauthenticated = client.post("/mcp", json={"id": 1, "method": "tools/call",
        "params": {"name": "get_uac_feedback_readiness", "arguments": {"tenant_id": "team_a"}}})
    assert unauthenticated.status_code == 401


def test_remote_pending_bind_is_explicit_qe_only_and_readiness_grants_no_authority(shared_client, remote_jira):
    client, factory = shared_client
    body = capture_body()
    body.pop("draft")
    initial = rpc(client, "capture_uac_feedback", body)
    assert initial["binding_status"] == "PENDING_BINDING"
    before = _counts(factory)
    readiness = rpc(client, "get_uac_feedback_readiness", {"tenant_id": "team_a"})
    assert readiness["identity"]["review_authority"].startswith("NOT_VERIFIED")
    arguments = {"tenant_id": "team_a", "feedback_id": initial["feedback_id"],
                 "idempotency_key": "deliberate-source-binding", "reviewed_jira_uac": PIN}
    denied = _error(client, "bind_uac_feedback", arguments)
    assert denied["http_status"] == 403
    assert _counts(factory) == before
    assert remote_jira["calls"] == []
    bound = rpc(client, "bind_uac_feedback", arguments, "qe")
    assert bound["binding_status"] == "BOUND" and bound["learning_status"] == "CANDIDATE"
    assert bound["revision"] == 2 and bound["index_status"] == "SKIPPED"
    assert bound["reviewed_jira_uac"]["source_hash"] == PIN["expected_sha256"]
    assert bound["automatic_authority_promotion"] is False
    assert bound["reuse_eligible"] is False
    assert rpc(client, "get_uac_feedback_status", {"tenant_id": "team_a",
        "feedback_id": initial["feedback_id"]}, "codex")["reviewed_jira_uac"] == bound["reviewed_jira_uac"]
    repeated = rpc(client, "bind_uac_feedback", arguments, "qe")
    assert repeated["revision"] == 2 and _counts(factory) == (1, 1, 1, 2, 2)


@pytest.mark.parametrize("failure", ["stale_hash", "missing_quote", "bad_label", "network", "mixed_source", "claimed_authority"])
def test_remote_capture_snapshot_failures_do_not_mutate_sql(shared_client, remote_jira, failure):
    client, factory = shared_client
    body = capture_body()
    body.pop("draft")
    pin = dict(PIN)
    if failure == "stale_hash":
        pin["expected_sha256"] = "0" * 64
    elif failure == "missing_quote":
        pin["original_reviewed_ac"] = "An invented criterion."
    elif failure == "bad_label":
        body["ac_id"] = "AC-02"
    elif failure == "network":
        remote_jira["fail"] = True
    elif failure == "mixed_source":
        body["run_id"] = "synthetic-generation"
    else:
        pin["source_kind"] = "synthetic-sensitive-approval"
    body["reviewed_jira_uac"] = pin
    result = _error(client, "capture_uac_feedback", body)
    assert result["http_status"] == (503 if failure == "network" else 422
        if failure in {"mixed_source", "claimed_authority"} else 409)
    assert "synthetic-sensitive" not in result["response"]
    assert _counts(factory) == (0, 0, 0, 0, 0)


def test_remote_failed_bind_leaves_only_original_pending_correction(shared_client, remote_jira):
    client, factory = shared_client
    body = capture_body()
    body.pop("draft")
    pending = rpc(client, "capture_uac_feedback", body)
    before = _counts(factory)
    invalid = {"tenant_id": "team_a", "feedback_id": pending["feedback_id"],
        "idempotency_key": "failed-deliberate-bind", "reviewed_jira_uac": {**PIN, "expected_sha256": "0" * 64}}
    assert _error(client, "bind_uac_feedback", invalid, "qe")["http_status"] == 409
    assert _counts(factory) == before == (0, 1, 0, 1, 1)
    status = rpc(client, "get_uac_feedback_status", {"tenant_id": "team_a", "feedback_id": pending["feedback_id"]})
    assert status["learning_status"] == "PENDING_BINDING" and status["revision"] == 1


def test_remote_readiness_fresh_process_does_not_import_persistence_or_start_backend(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    script = '''
import importlib.abc, json, socket, sys
forbidden = {"app.db.session", "app.services.shared_uac_learning_service", "app.main", "chromadb", "sentence_transformers"}
class BlockPersistence(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in forbidden:
            raise AssertionError("READINESS_IMPORTED_PERSISTENCE:" + fullname)
sys.meta_path.insert(0, BlockPersistence())
def no_network(*args, **kwargs):
    raise AssertionError("READINESS_STARTED_NETWORK")
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.routes.remote_mcp import router
from app.core.auth import UserIdentity, get_current_user
app = FastAPI()
app.include_router(router)
app.dependency_overrides[get_current_user] = lambda: UserIdentity(id="person", auth_method="token", principal_type="human", allowed_tenants=["team_a"])
with TestClient(app) as client:
    # Windows creates asyncio's local wake-up socketpair when the portal starts.
    # Block connections after that test infrastructure exists, before the call.
    socket.socket.connect = no_network
    response = client.post("/mcp", json={"id": 1, "method": "tools/call", "params": {"name": "get_uac_feedback_readiness", "arguments": {"tenant_id": "team_a"}}})
assert response.status_code == 200 and not response.json()["result"]["isError"], response.text
result = json.loads(response.json()["result"]["content"][0]["text"])
assert not any(result["actions"].values())
assert not forbidden.intersection(sys.modules)
print("REMOTE_READINESS_NO_PERSISTENCE_OR_STARTUP")
'''
    run = subprocess.run([sys.executable, "-c", script], cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(backend), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    assert "REMOTE_READINESS_NO_PERSISTENCE_OR_STARTUP" in run.stdout
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("case", ["test_feedback_api_records_lists_and_summarizes", "test_feedback_api_rejects_untraceable_execution"])
def test_legacy_feedback_api_existing_tests_without_startup(learning_db, case):
    from app.api.v1.routes.test_plans import router
    from app.db.test_plan_feedback_models import TestPlanQualityFeedback
    import test_test_plan_feedback_api as legacy_tests

    Base.metadata.create_all(learning_db.bind, tables=[TestPlanQualityFeedback.__table__])
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: person()
    app.dependency_overrides[session_module.get_db] = lambda: learning_db
    getattr(legacy_tests, case)(TestClient(app), {"Authorization": "Bearer synthetic-test"})
