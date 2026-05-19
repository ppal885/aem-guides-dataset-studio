"""Tests for explain_similarity() concrete overlap explanations."""

from __future__ import annotations

from app.services.jira_retrieval_service import RetrievedJira, explain_similarity


def test_explain_similarity_strong_overlap_and_confidence():
    current = {
        "summary": "Native PDF glossary glossStatus",
        "description": "Customer ACME sees wrong rendering",
        "domain": "publishing",
        "sub_domain": "pdf",
        "dita_entities": ["glossStatus", "bookmap"],
        "affected_outputs": ["Native PDF"],
        "customer_names": ["ACME Corp"],
        "labels": ["pdf", "native"],
        "components": ["Publisher"],
    }
    meta = {
        "jira_key": "GUIDES-200",
        "title": "Glossary Native PDF defect",
        "enrich_domain": "publishing",
        "enrich_sub_domain": "pdf",
        "enrich_entities": '["glossStatus", "bookmap"]',
        "enrich_outputs": '["Native PDF"]',
        "enrich_customers": '["ACME Corp"]',
        "labels": '["pdf", "customer"]',
        "components": '["publisher"]',
    }
    cand = RetrievedJira(
        jira_key="GUIDES-200",
        title="Glossary Native PDF defect",
        chunk_type="full_ticket_summary",
        document="glossStatus in glossary for Native PDF output",
        metadata=meta,
        vector_score=0.72,
        keyword_score=0.12,
        metadata_score=0.85,
        final_score=0.8,
        why_similar="legacy",
    )
    out = explain_similarity(current, cand)
    assert out["jira_key"] == "GUIDES-200"
    assert out["summary"]
    assert "native pdf" in out["matching_outputs"][0].lower()
    assert "glossstatus" in " ".join(out["matching_entities"]).lower() or any(
        "gloss" in x.lower() for x in out["matching_entities"]
    )
    assert "both tickets involve" in out["why_similar"].lower()
    assert "semantic" not in out["why_similar"].lower()
    assert out["confidence_score"] >= 0.55
    assert out["what_we_learned"]
    assert "GUIDES-200" in out["what_we_learned"]


def test_explain_similarity_weak_overlap_low_confidence():
    current = {
        "summary": "Unrelated infra ticket about LDAP",
        "description": "",
        "domain": "unknown",
        "dita_entities": [],
        "affected_outputs": [],
        "customer_names": [],
        "labels": [],
        "components": [],
    }
    meta = {
        "jira_key": "GUIDES-999",
        "title": "Different LDAP sync issue",
        "enrich_domain": "unknown",
        "enrich_entities": "[]",
        "enrich_outputs": "[]",
    }
    cand = RetrievedJira(
        jira_key="GUIDES-999",
        title="Different LDAP sync issue",
        document="ldap timeout",
        metadata=meta,
        vector_score=0.48,
        keyword_score=0.02,
        metadata_score=0.05,
        final_score=0.35,
        why_similar="",
    )
    out = explain_similarity(current, cand)
    assert out["matching_entities"] == []
    assert out["matching_outputs"] == []
    assert out["confidence_score"] <= 0.45
    assert "weak" in out["what_we_learned"].lower() or "thin" in out["why_similar"].lower()
