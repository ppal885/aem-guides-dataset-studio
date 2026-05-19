"""Tests for UAC Copilot analyze API."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_uac_ping(client):
    r = client.get("/api/v1/ai/uac/ping", headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_uac_analyze_validation_400(client):
    r = client.post(
        "/api/v1/ai/uac/analyze",
        json={"jira_key": "bad", "include_similar": True, "max_similar": 8},
        headers={"Authorization": "Bearer test-token"},
    )
    assert r.status_code == 400


@patch("app.api.v1.routes.uac_copilot.run_uac_analyze", new_callable=AsyncMock)
def test_uac_analyze_happy_path(mock_run, client):
    mock_run.return_value = {
        "jira_key": "EPV-123",
        "classification": {"domain": "publishing"},
        "similar_jiras": [],
        "uac_answer": "### 1. Jira Classification\n",
        "dropped_generic_points": [],
        "retrieval_debug": {"domain": "publishing", "entities": [], "outputs": [], "scores": []},
    }
    r = client.post(
        "/api/v1/ai/uac/analyze",
        json={"jira_key": "EPV-12345", "include_similar": True, "max_similar": 8},
        headers={"Authorization": "Bearer test-token"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["jira_key"] == "EPV-123"
    assert "uac_answer" in data


def test_enriched_from_db_row_roundtrip():
    from app.services.uac_copilot_analyze_service import _enriched_from_db_row

    row = {
        "jira_key": "EPV-1",
        "summary": "S",
        "description": "D",
        "issue_type": "Bug",
        "status": "Open",
        "priority": "High",
        "labels": ["a"],
        "components": ["c"],
        "customer_names": ["X"],
        "domain": "native_pdf",
        "sub_domain": "",
        "affected_outputs": ["pdf"],
        "affected_features": [],
        "dita_entities": ["ditaval"],
        "symptoms": [],
        "expected_behavior": "",
        "actual_behavior": "",
        "qa_risk_tags": [],
        "automation_fit": "Partial (5)",
        "missing_info": [],
        "raw_text": "blob",
        "enrichment_debug": {"source": "test"},
    }
    en = _enriched_from_db_row(row)
    assert isinstance(en, JiraEnrichedDocument)
    assert en.jira_key == "EPV-1"
    assert en.enrichment_debug["source"] == "test"


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://jira.example/rest/api/2/issue/EPV-1")
    resp = httpx.Response(status_code, request=req)
    return httpx.HTTPStatusError("boom", request=req, response=resp)


def test_safe_jira_fetch_error_message_is_actionable_without_secrets():
    from app.services.uac_copilot_analyze_service import _safe_jira_fetch_error_message

    assert "authentication failed (401)" in _safe_jira_fetch_error_message("EPV-1", _http_status_error(401))
    assert "permission denied (403)" in _safe_jira_fetch_error_message("EPV-1", _http_status_error(403))
    assert "JIRA_URL/JIRA_API_VERSION" in _safe_jira_fetch_error_message("EPV-1", _http_status_error(404))
    assert "password" not in _safe_jira_fetch_error_message("EPV-1", _http_status_error(500)).lower()


def test_uac_analyze_returns_exact_insufficient_evidence_message():
    from app.services.jira_retrieval_service import INSUFFICIENT_EVIDENCE_MESSAGE
    from app.services.uac_copilot_analyze_service import run_uac_analyze

    enriched = JiraEnrichedDocument(
        jira_key="EPV-2",
        summary="Native PDF publish issue",
        description="Native PDF output does not render expected DITAVAL content.",
        domain="native_pdf",
        affected_outputs=["native_pdf"],
        dita_entities=["ditaval"],
    )
    with patch("app.services.uac_copilot_analyze_service._load_or_fetch_enriched", return_value=(enriched, "db")):
        with patch("app.services.uac_copilot_analyze_service.retrieve_similar_jiras", return_value=[]):
            out = asyncio.run(run_uac_analyze("EPV-2", include_similar=True, max_similar=8, debug=True))
    assert out["insufficient_similar_evidence"] is True
    assert out["uac_answer"] == INSUFFICIENT_EVIDENCE_MESSAGE
    assert out.get("uac_ui") and out["uac_ui"]["version"] == 1
    assert out["uac_ui"]["risk_badge"]["level"]


def test_uac_analyze_llm_off_returns_structured_grounded_fallback():
    from app.services.jira_retrieval_service import RetrievedJira
    from app.services.uac_copilot_analyze_service import run_uac_analyze

    enriched = JiraEnrichedDocument(
        jira_key="EPV-3",
        summary="Keyref fails in Native PDF",
        issue_type="Bug",
        domain="keyref",
        affected_outputs=["native_pdf"],
        dita_entities=["keyref"],
        components=["Publishing"],
        customer_names=["Topcon"],
    )
    similar = [
        RetrievedJira(
            jira_key="EPV-OLD-1",
            title="Keyref native pdf",
            document="keyref native_pdf regression",
            metadata={"enrich_entities": '["keyref"]', "enrich_outputs": '["native_pdf"]'},
            final_score=0.9,
            matching_entities=["keyref"],
            matching_outputs=["native_pdf"],
        ),
        RetrievedJira(
            jira_key="EPV-OLD-2",
            title="Keyscope native pdf",
            document="keyref keyscope native_pdf regression",
            metadata={"enrich_entities": '["keyref"]', "enrich_outputs": '["native_pdf"]'},
            final_score=0.85,
            matching_entities=["keyref"],
            matching_outputs=["native_pdf"],
        ),
    ]
    with patch("app.services.uac_copilot_analyze_service._load_or_fetch_enriched", return_value=(enriched, "db")):
        with patch("app.services.uac_copilot_analyze_service.retrieve_similar_jiras", return_value=similar):
            with patch("app.services.uac_copilot_analyze_service.is_llm_available", return_value=False):
                out = asyncio.run(run_uac_analyze("EPV-3", include_similar=True, max_similar=8, debug=True))

    assert out["insufficient_similar_evidence"] is False
    assert out["classification"]["domain"] == "keyref"
    assert out["risk_summary"]
    assert out["must_test_scenarios"]
    assert out["automation_fit"]
    assert isinstance(out["quality_score"], int)
    assert out["structured_uac"]["classification"]["domain"] == "keyref"
    assert out["structured_uac"]["must_test_scenarios"]
    assert out["retrieval_debug"]["extracted"]["customer_names"] == ["Topcon"]
    assert "rejected_candidates" in out["retrieval_debug"]
    assert "keyref" in out["uac_answer"].lower()
    ui = out["uac_ui"]
    assert ui["must_test_scenario_table"]["rows"]
    assert ui["classification_card"]["jira_key"] == "EPV-3"


def test_uac_analyze_unknown_domain_without_anchors_skips_vector_retrieval():
    from app.services.jira_retrieval_service import INSUFFICIENT_EVIDENCE_MESSAGE
    from app.services.uac_copilot_analyze_service import run_uac_analyze

    enriched = JiraEnrichedDocument(
        jira_key="EPV-4",
        summary="Unclassified issue",
        description="Short description without DITA entity or affected output.",
        domain="unknown",
    )
    with patch("app.services.uac_copilot_analyze_service._load_or_fetch_enriched", return_value=(enriched, "db")):
        with patch("app.services.uac_copilot_analyze_service.retrieve_similar_jiras") as mock_retrieve:
            out = asyncio.run(run_uac_analyze("EPV-4", include_similar=True, max_similar=8, debug=True))

    mock_retrieve.assert_not_called()
    assert out["uac_answer"] == INSUFFICIENT_EVIDENCE_MESSAGE
    assert out["must_test_scenarios"] == []
    assert "lacks domain/entity/output anchors" in out["retrieval_debug"]["note"]
    assert out["uac_ui"]["executive_summary_card"]["summary"]
