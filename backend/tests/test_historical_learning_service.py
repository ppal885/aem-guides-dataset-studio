"""Tests for historical_learning_service.extract_learning."""

from __future__ import annotations

import json

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_retrieval_service import RetrievedJira

from services.uac.historical_learning_service import extract_learning


def _current() -> JiraEnrichedDocument:
    return JiraEnrichedDocument(
        jira_key="GUIDES-100",
        summary="PDF fails when map uses keyref",
        domain="publishing",
        dita_entities=["keyref", "map"],
        affected_outputs=["native_pdf", "pdf"],
        customer_names=["Acme"],
        components=["PDF"],
    )


def test_extract_learning_high_confidence_entity_output_overlap() -> None:
    profile = json.dumps(
        {
            "symptoms": ["blank title in PDF", "keyref not resolved"],
            "actual_behavior": "PDF shows keyref text instead of resolved title.",
        }
    )
    sim = RetrievedJira(
        jira_key="GUIDES-50",
        title="Keyref PDF regression",
        document="Long chunk about native PDF and keyref.",
        metadata={
            "enrich_domain": "publishing",
            "enrich_entities": json.dumps(["keyref", "map"]),
            "enrich_outputs": json.dumps(["native_pdf"]),
            "enrich_profile_json": profile,
            "labels": json.dumps(["pdf"]),
            "components": json.dumps(["PDF"]),
        },
        final_score=0.72,
        metadata_score=0.55,
        vector_score=0.5,
        keyword_score=0.1,
        why_similar="",
        matching_entities=["keyref", "map"],
        matching_outputs=["native_pdf"],
        matching_customers=["Acme"],
        matching_components=["PDF"],
        strong_evidence=True,
    )
    out = extract_learning(_current(), sim)
    assert out["jira_key"] == "GUIDES-50"
    assert out["confidence"] in {"high", "medium"}
    why_l = out["why_similar"].lower()
    assert "keyref" in why_l or "native_pdf" in why_l or "pdf" in why_l
    hfp = out["historical_failure_pattern"].lower()
    assert "symptom" in hfp or "actual" in hfp
    assert out["reusable_test_idea"]
    rr = out["risk_relevance"].lower()
    assert "guides-50" in rr or "failure" in rr or "output" in rr


def test_extract_learning_low_confidence_weak_overlap() -> None:
    sim = RetrievedJira(
        jira_key="GUIDES-999",
        title="Unrelated infra ticket",
        document="Disk full on build agent.",
        metadata={
            "enrich_domain": "unknown",
            "enrich_entities": json.dumps([]),
            "enrich_outputs": json.dumps([]),
        },
        final_score=0.25,
        metadata_score=0.1,
        vector_score=0.55,
        keyword_score=0.02,
        why_similar="",
        matching_entities=[],
        matching_outputs=[],
        matching_customers=[],
        matching_components=[],
        strong_evidence=False,
    )
    out = extract_learning(_current(), sim)
    assert out["confidence"] == "low"
    rti = out["reusable_test_idea"].lower()
    rr = out["risk_relevance"].lower()
    assert "exploratory" in rti or "uncertain" in rr
