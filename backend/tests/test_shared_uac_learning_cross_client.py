"""Authenticated HTTP/MCP cross-client proof against isolated SQL, never the VM."""
import hashlib
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import remote_mcp
from app.api.v1.routes import mcp_bridge, test_plan_learning
from app.db import session as session_module
from app.db.base import Base
from app.db.shared_uac_learning_models import IMMUTABLE_MODELS, UacLearningOutbox
from app.services import shared_uac_learning_service as learning
from app.services import shared_uac_qe_authorization as qe_authorization


@pytest.fixture
def shared_client(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[m.__table__ for m in IMMUTABLE_MODELS] + [UacLearningOutbox.__table__])
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(session_module, "SessionLocal", factory)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_DEV_AUTH_BYPASS", "false")
    monkeypatch.setenv("SHARED_UAC_LEARNING_MODE", "ENABLED")
    split = tmp_path / "split-metadata.json"
    split.write_text(json.dumps({"schema_version": "aem-guides-human-uac-benchmark-v2", "jira_ids": {
        "train": [], "validation": ["GUIDES-98998"], "blind": ["GUIDES-98999"]}}), encoding="utf-8")
    monkeypatch.setenv("SHARED_UAC_BENCHMARK_SPLIT_MANIFEST", str(split))
    monkeypatch.delenv("ADMIN_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("API_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("AUTH_TOKENS_JSON", json.dumps({
        "synthetic-claude": {"id": "claude-teammate", "principal_type": "human", "roles": ["writer"], "allowed_tenants": ["team_a"]},
        "synthetic-codex": {"id": "codex-teammate", "principal_type": "human", "roles": ["writer"], "allowed_tenants": ["team_a"]},
        "synthetic-qe": {"id": "qe-reviewer", "principal_type": "human", "roles": ["writer"], "allowed_tenants": ["team_a"],
            "jira_identity": {"server_url": "https://jira.example", "user_key": "qe-key-1"}},
        "synthetic-other": {"id": "other-tenant", "principal_type": "human", "roles": ["writer"], "allowed_tenants": ["team_b"]},
    }))
    monkeypatch.setattr(qe_authorization, "get_tenant", lambda tenant_id: type("Tenant", (), {
        "jira_url": "https://jira.example", "jira_email": "synthetic@example.com",
        "jira_token": "synthetic-fixture-token", "is_active": tenant_id == "team_a"})())
    monkeypatch.setattr(qe_authorization._QeAuthorizationJiraClient, "get_issue_with_names",
        lambda _client, issue_key, fields=None: {
            "key": issue_key, "names": {"customfield_18512": "QE Assignee"},
            "fields": {"customfield_18512": {"key": "qe-key-1", "active": True},
                       "assignee": {"key": "claude-teammate", "active": True},
                       "updated": "2026-09-06T00:00:00+00:00"}})
    app = FastAPI()
    app.include_router(test_plan_learning.router, prefix="/api/v1")
    app.include_router(mcp_bridge.router, prefix="/api/v1")
    app.include_router(remote_mcp.router)
    def database():
        with factory() as session:
            yield session
    app.dependency_overrides[session_module.get_db] = database
    yield TestClient(app), factory
    engine.dispose()


def headers(name):
    return {"Authorization": "Bearer synthetic-" + name}


def rpc(client, name, arguments, actor="claude"):
    response = client.post("/mcp", headers=headers(actor), json={"jsonrpc": "2.0", "id": 1,
        "method": "tools/call", "params": {"name": name, "arguments": arguments}})
    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    assert not envelope["result"]["isError"], envelope
    return json.loads(envelope["result"]["content"][0]["text"])


def capture_body(client_type="claude_desktop"):
    return {"tenant_id": "team_a", "jira_key": "GUIDES-98101", "idempotency_key": "selected-human-message-1",
        "raw_feedback": "Please also check the saved publishing configuration.",
        "proposed_correction": "Check that output uses the selected configuration.",
        "delta_type": "ORACLE_CHANGED", "ac_id": "AC-01",
        "client_context": {"client": client_type},
        "draft": {"draft_markdown": "## Acceptance Criteria\nAC-01: Generate the output.",
                  "criteria": {"AC-01": "Generate the output."}, "evidence_bundle_id": "bundle:" + "a" * 64,
                  "run_id": "isolated-canonical-example"}}


def review_body(feedback_id):
    return {"feedback_id": feedback_id, "tenant_id": "team_a", "idempotency_key": "human-approval-1",
        "expected_revision": 1, "decision": "APPROVE", "note": "Reviewed original correction and scope; approve scoped investigation only.",
        "origin_confirmed": True, "applicability_confirmed": True, "counterexamples_checked": True,
        "lesson": {"kind": "SCOPED_CASE", "guidance": "Investigate configuration-dependent output on the changed publishing flow.",
            "delta_type": "ORACLE_CHANGED", "domains": ["PUBLISHING"], "surfaces": ["CHANGED_BEHAVIOR"],
            "signals": ["CHANGED_BEHAVIOR"], "families": ["ALTERNATE_MECHANISMS"],
            "scope": {"subject_terms": ["versioned publishing"]}, "preferred_evidence": ["CURRENT_JIRA"],
            "independent_support_groups": [{"group_id": "reviewed-incident-1", "case_ids": ["GUIDES-98101"]}]}}


def query_body():
    return {"domain": "PUBLISHING", "change_surfaces": ["CHANGED_BEHAVIOR"], "abstract_signals": ["CHANGED_BEHAVIOR"],
        "current_jira_key": "GUIDES-98102", "subject_terms": ["versioned publishing"]}


@pytest.mark.parametrize("sender,reader,client_type", [("claude", "codex", "claude_desktop"), ("codex", "claude", "codex")])
@pytest.mark.parametrize("source", ["generation_draft", "jira_review_snapshot"])
def test_correction_named_approval_publication_other_client_retrieval_and_revocation(shared_client, monkeypatch, sender, reader, client_type, source):
    client, factory = shared_client
    body = capture_body(client_type)
    if source == "jira_review_snapshot":
        original = body.pop("draft")
        markdown = original["draft_markdown"]
        body["source_kind"] = "HUMAN_CORRECTION"
        body["client_context"]["session_id"] = "new-review-chat-without-generation-context"
        body["reviewed_jira_uac"] = {"field_id": "customfield_13400",
            "expected_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "expected_issue_updated": "2026-09-06T00:00:00+00:00",
            "original_reviewed_ac": original["criteria"]["AC-01"]}
        qe_reader = qe_authorization._QeAuthorizationJiraClient.get_issue_with_names

        def issue_reader(jira, key, fields=None):
            if fields == "customfield_13400,updated":
                return {"key": key, "names": {"customfield_13400": "Acceptance Criteria"},
                    "fields": {"customfield_13400": markdown, "updated": "2026-09-06T00:00:00+00:00"}}
            return qe_reader(jira, key, fields)

        monkeypatch.delenv("JIRA_ACCEPTANCE_CRITERIA_FIELD_ID", raising=False)
        monkeypatch.setattr(qe_authorization._QeAuthorizationJiraClient, "get_issue_with_names", issue_reader)
    receipt = rpc(client, "capture_uac_feedback", body, sender)
    assert receipt["persisted"] and receipt["binding_status"] == "BOUND"
    assert receipt["learning_status"] == "CANDIDATE"
    assert receipt["raw_feedback"] == capture_body(client_type)["raw_feedback"]
    if source == "jira_review_snapshot":
        assert receipt["reviewed_jira_uac"]["source_hash"] == body["reviewed_jira_uac"]["expected_sha256"]
        assert receipt["reviewed_jira_uac"]["generation_lineage_verified"] is False
        from app.db.shared_uac_learning_models import UacLearningDraft
        with factory() as session:
            snapshot = session.query(UacLearningDraft).filter_by(id=receipt["draft_id"]).one()
            assert snapshot.evidence_bundle_id == snapshot.run_id == ""
    publication = client.get("/api/v1/test-plan-learning/publication?tenant_id=team_a", headers=headers(reader)).json()
    assert publication["lessons"] == []
    approved = rpc(client, "review_uac_feedback", review_body(receipt["feedback_id"]), "qe")
    assert approved["lesson"]["human_approval"]["reviewer_id"] == "qe-reviewer"
    authorization = approved["lesson"]["human_approval"]["authorization"]
    assert authorization["policy"] == "LIVE_JIRA_QE_ASSIGNEE"
    assert authorization["jira_key"] == "GUIDES-98101"
    assert authorization["identity_value"] == "qe-key-1"
    assert approved["publication_review_status"] == "QE_APPROVED"
    assert approved["reuse_eligible"] is True
    assert approved["revision"] == 2 and approved["learning_status"] == "APPROVED"
    publication = client.get("/api/v1/test-plan-learning/publication?tenant_id=team_a&excluded_source_case_ids=GUIDES-98102", headers=headers(reader)).json()
    shared = client.post("/api/v1/mcp/resolve-qe-patterns?tenant_id=team_a", json=query_body(), headers=headers(reader)).json()["shared_learning"]
    assert shared["publication_id"] == publication["publication_id"]
    assert shared["matched_patterns"][0]["pattern"]["lesson_id"] == receipt["feedback_id"]
    assert shared["matched_patterns"][0]["recommended_families"] == ["ALTERNATE_MECHANISMS"]
    assert shared["matched_patterns"][0]["blocking_recommendations"] == []
    # Index outage does not turn pending/unverified knowledge into acceptance truth.
    assert learning.drain_learning_outbox(tenant_id="team_a", index_writer=lambda _: False)["failed"] == 1
    monkeypatch.setenv("SHARED_UAC_LEARNING_MODE", "SHADOW")
    shadow = rpc(client, "resolve_qe_patterns", {**query_body(), "tenant_id": "team_a"}, reader)["shared_learning"]
    assert shadow["shadow_pattern_ids"] and not shadow["matched_patterns"]
    monkeypatch.setenv("SHARED_UAC_LEARNING_MODE", "ENABLED")
    unrelated = rpc(client, "resolve_qe_patterns", {**query_body(), "tenant_id": "team_a", "subject_terms": ["unrelated editor input"]}, reader)
    assert not unrelated["shared_learning"]["matched_patterns"]
    excluded = rpc(client, "resolve_qe_patterns", {**query_body(), "tenant_id": "team_a", "excluded_source_case_ids": ["GUIDES-98101"]}, reader)
    assert not excluded["shared_learning"]["matched_patterns"]
    revoked = rpc(client, "review_uac_feedback", {"tenant_id": "team_a", "feedback_id": receipt["feedback_id"],
        "expected_revision": 2, "idempotency_key": "human-revocation-1", "decision": "REVOKE", "note": "Requirement changed; stop reuse."}, "qe")
    assert revoked["learning_status"] == "REVOKED"
    # No vector deletion needed for safety: current SQL state always wins.
    after = rpc(client, "resolve_qe_patterns", {**query_body(), "tenant_id": "team_a"}, reader)["shared_learning"]
    assert not after["matched_patterns"] and after["publication_id"] != publication["publication_id"]


def test_gateway_cross_tenant_and_client_approval_claim_fail_closed(shared_client):
    client, _ = shared_client
    receipt = rpc(client, "capture_uac_feedback", capture_body())
    rejected = client.post("/api/v1/test-plan-learning/feedback/" + receipt["feedback_id"] + "/review",
        headers=headers("claude"), json={k: v for k, v in review_body(receipt["feedback_id"]).items() if k != "feedback_id"})
    assert rejected.status_code == 403
    assert client.get("/api/v1/test-plan-learning/feedback/" + receipt["feedback_id"] + "?tenant_id=team_a", headers=headers("other")).status_code == 403
    assert client.post("/api/v1/mcp/resolve-qe-patterns?tenant_id=team_a", headers=headers("other"), json=query_body()).status_code == 403
    bad = client.post("/mcp", headers=headers("claude"), json={"id": 2, "method": "tools/call", "params": {
        "name": " capture_uac_feedback ", "arguments": {**capture_body(), "reviewer_id": "synthetic-sensitive-claim"}}})
    assert bad.json()["error"]["code"] == -32602
    assert "synthetic-sensitive-claim" not in bad.text
    spoofed = client.post("/mcp", headers=headers("claude"), json={"id": 3, "method": "tools/call", "params": {
        "name": "review_uac_feedback", "arguments": {**review_body(receipt["feedback_id"]),
            "jira_identity": {"server_url": "https://jira.example", "user_key": "qe-key-1"}}}})
    assert spoofed.json()["error"]["code"] == -32602
    status = rpc(client, "get_uac_feedback_status", {
        "tenant_id": "team_a", "feedback_id": receipt["feedback_id"]}, "codex")
    assert status["learning_status"] == "CANDIDATE"


def test_remote_tool_catalog_has_same_strict_contracts(shared_client):
    client, _ = shared_client
    response = client.post("/mcp", headers=headers("codex"), json={"id": 3, "method": "tools/list"}).json()
    tools = {item["name"]: item for item in response["result"]["tools"]}
    for name in remote_mcp._LEARNING_TOOL_NAMES:
        assert tools[name]["inputSchema"]["additionalProperties"] is False
    assert "SUPERSEDE" in tools["review_uac_feedback"]["inputSchema"]["properties"]["decision"]["enum"]
