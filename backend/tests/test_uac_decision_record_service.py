"""Tests for UAC Jira decision record builder."""

from __future__ import annotations

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from services.uac.uac_decision_record_service import build_uac_decision_record


def test_decision_record_shape_and_grounding():
    en = JiraEnrichedDocument(
        jira_key="GUIDES-55",
        domain="keyref",
        summary="Map merge drops keyref",
        dita_entities=["keyref", "map"],
        affected_outputs=["native_pdf"],
        customer_names=["Acme"],
    )
    payload = {
        "jira_key": "GUIDES-55",
        "classification": {"jira_key": "GUIDES-55", "domain": "keyref"},
        "risk_summary": {"level": "high", "risk_score": 3, "drivers": ["keyref unresolved in customer map"]},
        "similar_jiras": [{"jira_key": "GUIDES-40", "title": "Prior"}],
        "must_test_scenarios": [
            {
                "scenario": "GUIDES-55: republish native_pdf after keyscope fix",
                "why": "Customer map regression",
                "evidence": ["e1"],
                "test_layer": "Publishing",
                "priority": "P1",
            }
        ],
        "missing_clarifications": [
            {"question": "Which map root defines keyscope for Acme baseline?", "why": "gap"},
            {"question": "Does the API need a new validation endpoint for keyrefs?", "why": "dev"},
        ],
        "automation_fit": {"fit": "Partial", "primary_test_layer": "Publishing", "framework": "API checks plus pdf diff"},
        "output_parity": {"parity_required": True, "parity_pairs": [{"source": "preview", "target": "native_pdf"}]},
        "uac_validation_ok": True,
        "insufficient_similar_evidence": False,
    }
    out = build_uac_decision_record(payload, en)
    assert set(out.keys()) == {
        "summary",
        "decisions_needed",
        "qa_commitments",
        "dev_questions",
        "automation_plan",
        "dataset_needed",
        "release_risk",
    }
    assert "GUIDES-55" in out["summary"]
    assert "keyref" in out["summary"].lower()
    assert any("map root" in x.lower() for x in out["decisions_needed"])
    assert any("native_pdf" in x.lower() for x in out["qa_commitments"])
    assert any("api" in x.lower() for x in out["dev_questions"])
    assert out["automation_plan"]
    assert "parity" in out["release_risk"].lower() or "risk" in out["release_risk"].lower()


def test_insufficient_similar_adds_dataset_line():
    payload = {
        "jira_key": "X-1",
        "classification": {"domain": "unknown", "dita_entities": []},
        "risk_summary": {"level": "medium"},
        "similar_jiras": [],
        "must_test_scenarios": [],
        "missing_clarifications": [],
        "uac_validation_ok": True,
        "insufficient_similar_evidence": True,
    }
    out = build_uac_decision_record(payload)
    assert any("similar" in x.lower() or "dataset" in x.lower() for x in out["dataset_needed"])
