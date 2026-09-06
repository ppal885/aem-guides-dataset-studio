"""Thin client contracts and fake delivery; no backend startup or live requests."""
import asyncio
import importlib.util
from pathlib import Path

import httpx
import pytest

from app.core.schemas_shared_uac_learning import UacFeedbackBind, UacFeedbackCapture, UacReviewedJiraUac

ROOT = Path(__file__).resolve().parents[2]
CLIENTS = [
    "mcp_server/server.py",
    "release-artifacts/aem-guides-mcp-client-windows/server.py",
    "release-artifacts/aem-guides-mcp-client-unix/server.py",
]
NEW_TOOLS = {"bind_uac_feedback", "get_uac_feedback_readiness"}
PIN = {"field_id": "customfield_12345", "expected_sha256": "a" * 64,
       "expected_issue_updated": "2026-09-01T00:00:00+00:00",
       "original_reviewed_ac": "  Verify the saved setting.\n"}


@pytest.fixture(params=CLIENTS)
def client(request, monkeypatch):
    monkeypatch.setenv("AEM_STUDIO_URL", "https://backend.example.test")
    monkeypatch.setenv("AEM_STUDIO_TOKEN", "synthetic-identity-credential")
    path = ROOT / request.param
    spec = importlib.util.spec_from_file_location("feedback_client_" + str(CLIENTS.index(request.param)), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_catalog_contains_protected_explicit_tools_and_exact_source_pin(client):
    tools = {tool.name: tool for tool in asyncio.run(client.list_tools())}
    assert NEW_TOOLS <= client.FEEDBACK_TOOL_NAMES
    assert NEW_TOOLS <= set(tools)
    capture = tools["capture_uac_feedback"].inputSchema
    bind = tools["bind_uac_feedback"].inputSchema
    pin = capture["properties"]["reviewed_jira_uac"]
    assert pin == bind["properties"]["reviewed_jira_uac"]
    dto = UacReviewedJiraUac.model_json_schema()
    assert set(pin["properties"]) == set(dto["properties"])
    assert pin["required"] == dto["required"]
    assert pin["additionalProperties"] is False
    for name, prop in pin["properties"].items():
        for constraint in ("type", "pattern", "maxLength", "default"):
            if constraint in dto["properties"][name]:
                assert prop[constraint] == dto["properties"][name][constraint]
    assert bind["oneOf"] == [
        {"required": ["draft_id"], "not": {"required": ["reviewed_jira_uac"]}},
        {"required": ["reviewed_jira_uac"], "not": {"required": ["draft_id"]}},
    ]
    assert tools["get_uac_feedback_readiness"].inputSchema["required"] == ["tenant_id"]


def test_release_client_bytes_match():
    assert (ROOT / CLIENTS[1]).read_bytes() == (ROOT / CLIENTS[2]).read_bytes()


def test_exact_capture_pin_is_forwarded_without_claiming_human_origin(client, monkeypatch):
    calls = []

    async def post(path, body):
        calls.append((path, body))
        return {"persisted": True, "feedback_id": "feedback-1"}

    async def remote(name, args):
        calls.append((name, args))
        return {"persisted": True, "feedback_id": "feedback-1"}

    monkeypatch.setattr(client, "_post", post)
    if hasattr(client, "_remote_mcp_tool"):
        monkeypatch.setattr(client, "_remote_mcp_tool", remote)
    arguments = {"jira_key": "QA-101", "tenant_id": "team_a", "idempotency_key": "capture-1",
                 "raw_feedback": "The selected check needs a configuration branch.", "reviewed_jira_uac": PIN}
    asyncio.run(client._dispatch("capture_uac_feedback", arguments))
    assert len(calls) == 1
    body = calls[0][1]
    assert body["reviewed_jira_uac"] == PIN
    assert UacFeedbackCapture.model_validate(body).source_kind == "UNCONFIRMED"
    assert not body.get("draft") and not body.get("evidence_bundle_id") and not body.get("run_id")


def test_legacy_capture_does_not_add_source_pin(client, monkeypatch):
    calls = []

    async def capture(name, body):
        calls.append(body)
        return {}

    monkeypatch.setattr(client, "_post", capture)
    if hasattr(client, "_remote_mcp_tool"):
        monkeypatch.setattr(client, "_remote_mcp_tool", capture)
    asyncio.run(client._dispatch("capture_uac_feedback", {
        "jira_key": "QA-101", "raw_feedback": "Correction", "idempotency_key": "legacy-1"}))
    assert len(calls) == 1
    assert "reviewed_jira_uac" not in calls[0]


@pytest.mark.parametrize("source", [{"draft_id": "draft-1"}, {"reviewed_jira_uac": PIN}])
def test_bind_forwards_exact_selected_source_once(client, monkeypatch, source):
    calls = []

    async def dispatch(path, body):
        calls.append((path, body))
        return {"binding_status": "BOUND", "learning_status": "CANDIDATE"}

    monkeypatch.setattr(client, "_post", dispatch)
    release = hasattr(client, "_remote_mcp_tool")
    if release:
        monkeypatch.setattr(client, "_remote_mcp_tool", dispatch)
    arguments = {"feedback_id": "feedback-1", "tenant_id": "team_a", "idempotency_key": "bind-1", **source}
    result = asyncio.run(client._dispatch("bind_uac_feedback", arguments))
    assert result["learning_status"] == "CANDIDATE"
    assert len(calls) == 1
    path, body = calls[0]
    if release:
        assert path == "bind_uac_feedback" and body == arguments
        body = {key: value for key, value in body.items() if key != "feedback_id"}
    else:
        assert path == "/api/v1/test-plan-learning/feedback/feedback-1/bind"
    validated = UacFeedbackBind.model_validate(body)
    assert validated.draft_id == source.get("draft_id", "")
    assert (validated.reviewed_jira_uac.model_dump() if validated.reviewed_jira_uac else None) == source.get("reviewed_jira_uac")


def test_readiness_is_get_in_rich_client_or_same_remote_tool(client, monkeypatch):
    calls = []

    async def read(path, params):
        calls.append((path, params))
        return {"status": "CONFIGURATION_ONLY", "actual_learning_proven": False}

    async def forbidden(*args, **kwargs):
        raise AssertionError("Readiness must not POST a write operation")

    monkeypatch.setattr(client, "_post", forbidden)
    if hasattr(client, "_remote_mcp_tool"):
        monkeypatch.setattr(client, "_remote_mcp_tool", read)
        expected = "get_uac_feedback_readiness"
    else:
        monkeypatch.setattr(client, "_get", read)
        expected = "/api/v1/test-plan-learning/readiness"
    result = asyncio.run(client._dispatch("get_uac_feedback_readiness", {"tenant_id": "team_a"}))
    assert result["status"] == "CONFIGURATION_ONLY"
    assert calls == [(expected, {"tenant_id": "team_a"})]


@pytest.mark.parametrize("name", sorted(NEW_TOOLS))
def test_dev_credentials_block_new_tools_before_any_delivery(client, monkeypatch, name):
    monkeypatch.setattr(client, "AUTH_TOKEN", "dev-bypass")

    async def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected network delivery")

    monkeypatch.setattr(client, "_post", forbidden)
    if hasattr(client, "_get"):
        monkeypatch.setattr(client, "_get", forbidden)
    if hasattr(client, "_remote_mcp_tool"):
        monkeypatch.setattr(client, "_remote_mcp_tool", forbidden)
    with pytest.raises(ValueError):
        asyncio.run(client._dispatch(name, {"tenant_id": "team_a", "feedback_id": "feedback-1",
                                           "idempotency_key": "bind-1", "draft_id": "draft-1"}))


@pytest.mark.parametrize("name", sorted(NEW_TOOLS))
def test_failure_is_redacted_and_not_retried(client, monkeypatch, name):
    calls = []

    async def fail(*args, **kwargs):
        calls.append(True)
        request = httpx.Request("POST", "https://backend.example.test")
        response = httpx.Response(503, text="private-correction private-credential", request=request)
        raise httpx.HTTPStatusError("private-response", request=request, response=response)

    monkeypatch.setattr(client, "_post", fail)
    if hasattr(client, "_get"):
        monkeypatch.setattr(client, "_get", fail)
    if hasattr(client, "_remote_mcp_tool"):
        monkeypatch.setattr(client, "_remote_mcp_tool", fail)
    result = asyncio.run(client.call_tool(name, {"tenant_id": "team_a", "feedback_id": "feedback-1",
                                               "idempotency_key": "bind-1", "draft_id": "draft-1"}))
    assert len(calls) == 1
    text = " ".join(item.text for item in result)
    assert "private" not in text
    assert "retried" in text or "retry" in text


def test_rich_shared_sse_cannot_use_new_tools(client, monkeypatch):
    if not hasattr(client, "SHARED_SSE_TRANSPORT"):
        return  # Release clients are stdio only.
    monkeypatch.setattr(client, "SHARED_SSE_TRANSPORT", True)
    for name in NEW_TOOLS:
        with pytest.raises(ValueError, match="shared SSE"):
            asyncio.run(client._dispatch(name, {}))


def test_rich_rejects_feedback_path_injection_and_ambiguous_bind_source(client):
    if hasattr(client, "_remote_mcp_tool"):
        return  # Remote gateway applies its own DTO/lookup validation.
    for identifier in ("../another", "id?tenant_id=other", "id/another"):
        with pytest.raises(ValueError):
            asyncio.run(client._dispatch("bind_uac_feedback", {"feedback_id": identifier}))
    for sources in ({}, {"draft_id": "draft-1", "reviewed_jira_uac": PIN}):
        with pytest.raises(ValueError, match="exactly one"):
            asyncio.run(client._dispatch("bind_uac_feedback", {"feedback_id": "feedback-1", **sources}))
