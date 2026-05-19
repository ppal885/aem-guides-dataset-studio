"""QA Studio API smoke tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _headers():
    return {"Authorization": "Bearer test-token"}


def test_qa_studio_health():
    client = TestClient(app)
    r = client.get("/api/v1/qa-studio/health", headers=_headers())
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_qa_studio_status_includes_rag_shape():
    client = TestClient(app)
    r = client.get("/api/v1/qa-studio/status", headers=_headers())
    assert r.status_code == 200
    body = r.json()
    assert "rag" in body
    assert "qa_bundled" in body
    assert "qa_studio_llm_authoring" in body
    assert isinstance(body.get("qa_studio_llm_authoring"), bool)
    assert "setup_checklist" in body
    assert isinstance(body.get("setup_checklist"), list)


def test_qa_plan_blocked_without_expected():
    client = TestClient(app)
    r = client.post(
        "/api/v1/qa-studio/plan",
        headers=_headers(),
        json={
            "jira_summary": "Broken",
            "jira_description": "Actual: wrong\n",
            "repro_steps": "1. Open",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("blocked") is True
    rep = data.get("assertion_traceability_report")
    assert isinstance(rep, dict)
    assert rep.get("blocked_no_observable_expected") is True


def test_qa_plan_assertion_traceability_when_unblocked():
    client = TestClient(app)
    r = client.post(
        "/api/v1/qa-studio/plan",
        headers=_headers(),
        json={
            "jira_summary": "Bug",
            "expected_behavior": "The PDF export completes with the map title on the cover.",
            "repro_steps": "Open map",
        },
    )
    assert r.status_code == 200
    data = r.json()
    rep = data.get("assertion_traceability_report")
    assert isinstance(rep, dict)
    assert rep.get("blocked_no_observable_expected") is False
    assert rep.get("ok") is True


def test_qa_validate_assertion_traceability():
    client = TestClient(app)
    r = client.post(
        "/api/v1/qa-studio/validate/assertion-traceability",
        headers=_headers(),
        json={
            "expected_behavior": "User sees a confirmation dialog titled Publish.",
            "feature_text": "Then the confirmation dialog titled Publish is visible\n",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("blocked_no_observable_expected") is False
    assert body.get("then_step_results")


def test_qa_plan_stub_when_expected_present(monkeypatch):
    monkeypatch.setenv("QA_STUDIO_DEMO_PLANS", "1")
    client = TestClient(app)
    r = client.post(
        "/api/v1/qa-studio/plan",
        headers=_headers(),
        json={
            "jira_summary": "Bug",
            "expected_behavior": "PDF should generate",
            "repro_steps": "Open map",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("blocked") is False
    assert data.get("plan_draft")
    assert data.get("llm_mode") == "demo_stub"
    ev = data.get("rag_evidence") or {}
    assert "playbook_matches" in ev
    assert isinstance(ev.get("playbook_matches"), list)


def test_qa_validate_locator_includes_governance():
    client = TestClient(app)
    r = client.post(
        "/api/v1/qa-studio/validate/locator",
        headers=_headers(),
        json={"expression": "//div[@role='tablist']"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("quality") == "reuse"
    assert "suggestions" in data
    assert data.get("governance", {}).get("policy_skipped") is True


def test_qa_generate_disabled_without_llm_flag():
    client = TestClient(app)
    r = client.post(
        "/api/v1/qa-studio/generate",
        headers=_headers(),
        json={
            "plan": {"summary": "x"},
            "expected_behavior": "User sees toast OK",
            "repro_steps": "Click save",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("accepted") is False
    assert data.get("generation_ok") is False