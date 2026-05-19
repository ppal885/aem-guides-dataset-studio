"""Recorder session API and capture service tests."""

from __future__ import annotations

import json

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.recorder_capture_service import (
    get_recorder_sessions_root,
    redact_capture_document,
    validate_capture,
)


def _headers():
    return {"Authorization": "Bearer test-token"}


def _minimal_capture(jira: bool = True) -> dict:
    cap = {
        "session_id": "rec-test",
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:05:00Z",
        "app_url": "https://aem.local/",
        "browser": "Chrome",
        "viewport": {"width": 1280, "height": 720},
        "workflow_name": "repository search",
        "user_notes": "capture test",
        "aem_guides_context": {"primary_panel": "Repository", "screen": "search"},
        "steps": [
            {
                "step_id": "s1",
                "action_type": "click",
                "timestamp": "2026-01-01T00:01:00Z",
                "target_summary": "Open search",
                "visible_text": "Search",
                "accessible_name": "Search repository",
                "role": "button",
                "aria": "",
                "stable_attributes": {"data-testid": "repo-search"},
                "locator_candidates": ['//*[@role="searchbox"]'],
                "dom_snippet": "<button>Search</button>",
                "ancestor_context": "Repository toolbar",
                "scroll_context": None,
                "redaction_applied": False,
                "confidence": 0.9,
            }
        ],
    }
    if jira:
        cap["jira_key"] = "GUIDES-999"
    return cap


def test_validate_capture_flags_fragile_xpath():
    cap = _minimal_capture()
    cap["steps"][0]["locator_candidates"] = ["//div[2]/button[1]"]
    v = validate_capture(cap)
    assert v["ok"] is True
    assert any("fragile" in w.lower() for w in v["warnings"])


def test_redact_capture_masks_bearerish():
    cap = _minimal_capture()
    cap["user_notes"] = "token sk-12345678901234567890 here"
    doc = {"capture": cap, "meta": {"id": "x"}}
    red = redact_capture_document(doc)
    assert "sk-" not in red["capture"]["user_notes"] or "REDACTED" in red["capture"]["user_notes"]


@pytest.fixture()
def isolated_recorder_storage(monkeypatch):
    import shutil

    base = Path(__file__).resolve().parent / "_recorder_test_workdir"
    base.mkdir(exist_ok=True)
    for p in base.iterdir():
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.is_file():
            p.unlink(missing_ok=True)
    monkeypatch.setenv("RECORDER_SESSIONS_PATH", str(base))
    root = get_recorder_sessions_root()
    assert str(root.resolve()) == str(base.resolve())
    yield base


def test_recorder_crud_and_evidence_alias(isolated_recorder_storage):
    client = TestClient(app)
    cap = _minimal_capture()
    r = client.post(
        "/api/v1/recorder/sessions",
        headers=_headers(),
        json={"capture": cap, "redact": False},
    )
    assert r.status_code == 200
    sid = r.json()["id"]
    r_list = client.get("/api/v1/recorder/sessions", headers=_headers())
    assert r_list.status_code == 200
    assert any(x["id"] == sid for x in r_list.json()["sessions"])
    r_get = client.get(f"/api/v1/recorder/sessions/{sid}", headers=_headers())
    assert r_get.status_code == 200
    r_pi = client.post(f"/api/v1/recorder/sessions/{sid}/plan-input", headers=_headers())
    assert r_pi.status_code == 200
    body = r_pi.json()
    assert "repro_steps" in body
    assert "GUIDES-999" in (body.get("jira_key") or "")
    r_alias = client.post(
        "/api/v1/evidence/upload-capture-json",
        headers=_headers(),
        json={"capture": _minimal_capture(jira=False)},
    )
    assert r_alias.status_code == 200
    r_del = client.delete(f"/api/v1/recorder/sessions/{sid}", headers=_headers())
    assert r_del.status_code == 200


def test_plan_with_recorder_session_enriches_notes(isolated_recorder_storage):
    client = TestClient(app)
    cap = _minimal_capture()
    r = client.post("/api/v1/recorder/sessions", headers=_headers(), json={"capture": cap})
    sid = r.json()["id"]
    pr = client.post(
        "/api/v1/qa-studio/plan",
        headers=_headers(),
        json={
            "jira_summary": "Test",
            "expected_behavior": "The export shows the map title on the PDF cover page.",
            "repro_steps": "Manual baseline repro",
            "recorder_session_id": sid,
        },
    )
    assert pr.status_code == 200
    data = pr.json()
    assert data.get("blocked") is False
    rec = data.get("recorder_evidence") or {}
    assert rec.get("recorder_session_id") == sid
    ev = json.dumps(data)
    assert "Recorder capture" in ev or "recorder" in ev.lower()
