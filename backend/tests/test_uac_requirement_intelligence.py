"""Unit tests for UAC Requirement Intelligence orchestrator and API contract."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.core.schemas_uac_intelligence import UacRequirementIntelligenceResponse
from app.main import app
from services.uac.uac_orchestrator import run_requirement_intelligence


def _minimal_enriched() -> JiraEnrichedDocument:
    return JiraEnrichedDocument(
        jira_key="GUIDES-99999",
        summary="Parity check preview vs Native PDF for keyref",
        description="Customer reports mismatch. CALS tables involved.",
        issue_type="Bug",
        status="Open",
        priority="Major",
        labels=["customer_acme"],
        components=["Editor"],
        customer_names=["Acme Corp"],
        domain="keyref",
        sub_domain="",
        affected_outputs=["preview", "native_pdf"],
        dita_entities=["keyref", "keydef"],
        expected_behavior="Preview and Native PDF resolve keyrefs identically for the repro map.",
        actual_behavior="PDF output drops alternate text in one column.",
        qa_risk_tags=["parity"],
        missing_info=[],
        enrichment_debug={"test": True},
    )


@patch("services.uac.uac_orchestrator.retrieve_for_intelligence")
@patch("services.uac.uac_orchestrator._load_or_fetch_enriched")
def test_run_requirement_intelligence_validates(mock_load, mock_retrieve):
    mock_load.return_value = (_minimal_enriched(), "test")
    mock_retrieve.return_value = {
        "similar_jiras": [],
        "experience_league": [],
        "dita_spec": [],
        "debug": {},
    }

    raw = run_requirement_intelligence(
        "GUIDES-99999",
        debug=False,
        include_docs=False,
        max_similar_jiras=0,
        correlation_id="test-corr-1",
    )
    parsed = UacRequirementIntelligenceResponse.model_validate(raw)
    assert parsed.jira_key == "GUIDES-99999"
    assert parsed.correlation_id == "test-corr-1"
    assert isinstance(parsed.evidence_manifest, list)
    assert len(parsed.evidence_manifest) >= 1
    assert parsed.risk_summary.level in ("low", "medium", "high")


@patch("services.uac.uac_orchestrator.retrieve_for_intelligence")
@patch("services.uac.uac_orchestrator._load_or_fetch_enriched")
def test_correlation_id_generated_when_missing(mock_load, mock_retrieve):
    mock_load.return_value = (_minimal_enriched(), "test")
    mock_retrieve.return_value = {
        "similar_jiras": [],
        "experience_league": [],
        "dita_spec": [],
        "debug": {},
    }
    raw = run_requirement_intelligence("GUIDES-99999", correlation_id=None)
    parsed = UacRequirementIntelligenceResponse.model_validate(raw)
    assert parsed.correlation_id
    assert len(parsed.correlation_id) >= 8


@pytest.fixture
def uac_intel_client():
    return TestClient(app)


@patch("services.uac.uac_orchestrator.retrieve_for_intelligence")
@patch("services.uac.uac_orchestrator._load_or_fetch_enriched")
def test_requirement_intelligence_route_ok(mock_load, mock_retrieve, uac_intel_client):
    mock_load.return_value = (_minimal_enriched(), "test")
    mock_retrieve.return_value = {
        "similar_jiras": [],
        "experience_league": [],
        "dita_spec": [],
        "debug": {},
    }

    r = uac_intel_client.post(
        "/api/v1/ai/uac/requirement-intelligence",
        json={
            "jira_key": "GUIDES-99999",
            "debug": False,
            "include_docs": True,
            "max_similar_jiras": 2,
        },
        headers={"Authorization": "Bearer test-token", "X-Correlation-ID": "hdr-corr-xyz"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["jira_key"] == "GUIDES-99999"
    assert data["correlation_id"] == "hdr-corr-xyz"
    assert "acceptance_criteria" in data


@patch("services.uac.uac_orchestrator.retrieve_for_intelligence")
@patch("services.uac.uac_orchestrator._load_or_fetch_enriched")
def test_uac_intelligence_alias_route_ok(mock_load, mock_retrieve, uac_intel_client):
    mock_load.return_value = (_minimal_enriched(), "test")
    mock_retrieve.return_value = {
        "similar_jiras": [],
        "experience_league": [],
        "dita_spec": [],
        "debug": {},
    }

    r = uac_intel_client.post(
        "/api/v1/ai/uac/intelligence",
        json={
            "jira_key": "GUIDES-99999",
            "debug": False,
            "include_docs": True,
            "max_similar_jiras": 2,
        },
        headers={"Authorization": "Bearer test-token", "X-Correlation-ID": "hdr-corr-alias"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["jira_key"] == "GUIDES-99999"
    assert data["correlation_id"] == "hdr-corr-alias"
    assert "acceptance_criteria" in data
