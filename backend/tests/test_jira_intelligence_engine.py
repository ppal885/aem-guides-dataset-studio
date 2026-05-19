"""Tests for public Jira Intelligence facades."""

from __future__ import annotations

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_retrieval_service import RetrievedJira
from prompts.uac import load_uac_domain_template
from services.jira_chunking_service import JiraSmartChunkingService
from services.jira_enrichment_service import JiraEnrichmentPipeline
from services.jira_intelligence_engine import JiraIntelligenceEngine, JiraIntelligenceRequest


def test_public_enrichment_and_chunking_facades():
    issue = {
        "key": "GUIDES-INT-1",
        "fields": {
            "summary": "Native PDF glossStatus bug for Topcon",
            "description": "Expected: PDF shows glossStatus. Actual: Native PDF drops it.",
            "issuetype": {"name": "Bug"},
            "labels": ["customer:Topcon"],
            "components": [{"name": "Publishing"}],
        },
    }

    enriched = JiraEnrichmentPipeline().enrich_issue(issue)
    chunks = JiraSmartChunkingService().create_chunks(enriched)

    assert enriched.jira_key == "GUIDES-INT-1"
    assert "Topcon" in enriched.customer_names
    assert chunks
    assert all(row["jira_key"] == "GUIDES-INT-1" for row in chunks)


def test_domain_prompt_template_loader():
    template = load_uac_domain_template("native_pdf")
    assert "UAC Grounding Contract" in template
    assert "Native PDF UAC Focus" in template
    assert "navtitle" in template
    assert "CSS" in template
    assert "generic QA checklist" in template


def test_uac_domain_templates_include_aem_guides_reasoning():
    keyref = load_uac_domain_template("conkeyref")
    assert "duplicate keys" in keyref
    assert "root-map vs submap precedence" in keyref
    assert "nested maps" in keyref

    ditaval = load_uac_domain_template("ditaval")
    assert "info/warning roles" in ditaval
    assert "invalid val structure" in ditaval

    image = load_uac_domain_template("image")
    assert "dc:format" in image
    assert ".ai/.eps/.svg" in image

    uuid = load_uac_domain_template("uuid")
    assert "BTree" in uuid
    assert "BSON" in uuid


def test_jira_intelligence_engine_builds_grounded_structured_uac(monkeypatch):
    enriched = JiraEnrichedDocument(
        jira_key="GUIDES-INT-2",
        summary="Keyref fails in Native PDF",
        issue_type="Bug",
        domain="keyref",
        affected_outputs=["native_pdf"],
        dita_entities=["keyref", "keyscope"],
        components=["Publishing"],
    )

    def _fake_retrieve(**_kwargs):
        return [
            RetrievedJira(
                jira_key="GUIDES-OLD-1",
                title="Keyref native pdf regression",
                document="keyref failed in native_pdf",
                metadata={
                    "enrich_domain": "keyref",
                    "enrich_entities": '["keyref"]',
                    "enrich_outputs": '["native_pdf"]',
                },
                final_score=0.9,
                metadata_score=0.9,
                vector_score=0.8,
                keyword_score=0.5,
                matching_entities=["keyref"],
                matching_outputs=["native_pdf"],
                why_similar="exact entity/output overlap",
            )
        ]

    monkeypatch.setattr("services.jira_intelligence_engine.retrieve_similar_jiras", _fake_retrieve)

    out = JiraIntelligenceEngine().build_uac(
        JiraIntelligenceRequest(enriched_jira=enriched, include_similar=True, max_similar=3)
    )

    assert out["structured_uac"]["classification"]["domain"] == "keyref"
    assert out["structured_uac"]["must_test_scenarios"]
    joined = str(out["structured_uac"]).lower()
    assert "keyref" in joined
    assert "native_pdf" in joined
