"""On-demand UAC requests over REST and MCP: queue, dedupe, status, and the runner-side outcome."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import uac_request_service

_QUEUE_MODULE = Path(__file__).resolve().parents[2] / "scripts" / "uac_release" / "uac_request_queue.py"


def _queue_module():
    spec = importlib.util.spec_from_file_location("uac_request_queue_test", _QUEUE_MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def requests_dir(tmp_path, monkeypatch):
    directory = tmp_path / "requests"
    monkeypatch.setenv("UAC_REQUESTS_DIR", str(directory))
    return directory


HEADERS = {"Authorization": "Bearer test-token"}


def test_post_queues_a_request_and_get_reads_it_back(requests_dir):
    client = TestClient(app)
    created = client.post("/api/v1/uac-requests", json={"jira_key": "guides-60001", "requested_by": "vision"}, headers=HEADERS)
    assert created.status_code == 202, created.text
    body = created.json()
    assert body["status"] == "queued"
    assert body["jira_key"] == "GUIDES-60001", "keys are normalised to upper case"
    assert body["requested_by"] == "vision"
    assert body["poll_url"] == f"/api/v1/uac-requests/{body['request_id']}"
    assert (requests_dir / f"{body['request_id']}.json").is_file(), "the runner reads this file"

    fetched = client.get(body["poll_url"], headers=HEADERS)
    assert fetched.status_code == 200
    assert fetched.json()["request_id"] == body["request_id"]

    listed = client.get("/api/v1/uac-requests", params={"jira_key": "GUIDES-60001"}, headers=HEADERS)
    assert listed.status_code == 200
    assert [r["request_id"] for r in listed.json()["items"]] == [body["request_id"]]


def test_second_request_for_an_open_ticket_returns_the_existing_one(requests_dir):
    client = TestClient(app)
    first = client.post("/api/v1/uac-requests", json={"jira_key": "GUIDES-60002"}, headers=HEADERS)
    second = client.post("/api/v1/uac-requests", json={"jira_key": "GUIDES-60002"}, headers=HEADERS)
    assert first.status_code == 202
    assert second.status_code == 200, "already queued: same id, not a duplicate"
    assert second.json()["request_id"] == first.json()["request_id"]
    assert len(list(requests_dir.glob("req_*.json"))) == 1


def test_invalid_key_and_unknown_request_are_rejected(requests_dir):
    client = TestClient(app)
    assert client.post("/api/v1/uac-requests", json={"jira_key": "not a key"}, headers=HEADERS).status_code == 422
    assert client.get("/api/v1/uac-requests/req_000000000000", headers=HEADERS).status_code == 404
    assert client.get("/api/v1/uac-requests/../etc/passwd", headers=HEADERS).status_code in (404, 422)
    assert client.get("/api/v1/uac-requests", params={"status": "bogus"}, headers=HEADERS).status_code == 422


def test_runner_outcome_is_visible_to_the_caller(requests_dir):
    """The runner marks the request on the same file; the API reflects posted / failed / skipped."""
    client = TestClient(app)
    queue = _queue_module().UacRequestQueue(requests_dir)
    posted = client.post("/api/v1/uac-requests", json={"jira_key": "GUIDES-60003"}, headers=HEADERS).json()
    kept = client.post("/api/v1/uac-requests", json={"jira_key": "GUIDES-60004"}, headers=HEADERS).json()
    failed = client.post("/api/v1/uac-requests", json={"jira_key": "GUIDES-60005"}, headers=HEADERS).json()

    assert queue.mark_running(posted["request_id"], run_id="run-1")["status"] == "running"
    queue.finish(posted["request_id"], runner_state="POSTED", ac_count=6)
    queue.finish(kept["request_id"], runner_state="FIELD_KEPT")
    queue.finish(failed["request_id"], runner_state="FAILED", problems=["UAC.md has 0 Acceptance Criteria (expected 1-10)"])

    posted_view = client.get(posted["poll_url"], headers=HEADERS).json()
    assert (posted_view["status"], posted_view["ac_count"], posted_view["run_id"]) == ("posted", 6, "run-1")
    kept_view = client.get(kept["poll_url"], headers=HEADERS).json()
    assert (kept_view["status"], kept_view["reason"]) == ("skipped", "FIELD_KEPT")
    failed_view = client.get(failed["poll_url"], headers=HEADERS).json()
    assert (failed_view["status"], failed_view["reason"]) == ("failed", "CHECKS_FAILED")
    assert failed_view["problems"] == ["UAC.md has 0 Acceptance Criteria (expected 1-10)"]

    # a finished ticket can be requested again: the open-request dedupe only covers queued/running
    again = client.post("/api/v1/uac-requests", json={"jira_key": "GUIDES-60003"}, headers=HEADERS)
    assert again.status_code == 202
    assert again.json()["request_id"] != posted["request_id"]


def test_mcp_tools_request_and_read_status(requests_dir):
    client = TestClient(app)
    tools = client.post("/mcp", headers=HEADERS, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    names = [t["name"] for t in tools.json()["result"]["tools"]]
    assert "request_uac" in names and "request_uac_status" in names

    call = client.post("/mcp", headers=HEADERS, json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "request_uac", "arguments": {"jira_key": "GUIDES-60010", "requested_by": "vision"}},
    })
    assert call.status_code == 200, call.text
    result = call.json()["result"]
    assert not result.get("isError"), result
    payload = json.loads(result["content"][0]["text"]) if isinstance(result.get("content"), list) else result
    assert payload["status"] == "queued" and payload["created"] is True
    assert (requests_dir / f"{payload['request_id']}.json").is_file()

    status = client.post("/mcp", headers=HEADERS, json={
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "request_uac_status", "arguments": {"request_id": payload["request_id"]}},
    })
    result = status.json()["result"]
    view = json.loads(result["content"][0]["text"]) if isinstance(result.get("content"), list) else result
    assert view["jira_key"] == "GUIDES-60010" and view["status"] == "queued"


def test_service_uses_the_env_directory(requests_dir):
    assert uac_request_service.requests_dir() == requests_dir
