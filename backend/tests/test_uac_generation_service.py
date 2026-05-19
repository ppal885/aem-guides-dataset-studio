"""Tests for enterprise Jira-aware UAC generation."""

from __future__ import annotations

import re

from services.uac_generation_service import (
    INSUFFICIENT_EVIDENCE_MESSAGE,
    UACGenerationEngine,
    UACPromptBuilder,
    generate_uac_recommendations,
)


_GENERIC = re.compile(
    r"test regression|verify ui|validate functionality|test positive and negative scenarios",
    re.I,
)


def _grounding_blob(value: object) -> str:
    return str(value).lower()


def test_structured_output_schema_and_scenario_traceability():
    enriched = {
        "jira_key": "GUIDES-990",
        "summary": "Native PDF drops glossStatus for glossary bookmap",
        "description": "glossStatus disappears in Native PDF when glossary topic is reused.",
        "issue_type": "Bug",
        "priority": "P1",
        "domain": "native_pdf",
        "dita_entities": ["glossStatus", "bookmap"],
        "affected_outputs": ["native_pdf"],
        "components": ["PDF Publishing"],
        "customer_names": ["Topcon"],
        "missing_info": ["Exact Native PDF preset"],
    }
    similar = [
        {
            "jira_key": "GUIDES-881",
            "title": "PDF glossary regression",
            "document": "Native PDF drops glossStatus for glossary maps.",
            "matching_entities": ["glossStatus"],
            "matching_outputs": ["native_pdf"],
            "scores": {"final": 0.91},
        }
    ]

    out = generate_uac_recommendations(enriched, similar, {"candidate_count": 1})

    assert set(out) == {
        "classification",
        "risk_summary",
        "similar_jiras",
        "must_test_scenarios",
        "missing_clarifications",
        "automation_fit",
        "evidence_summary",
        "confidence",
        "output_parity",
    }
    assert out["classification"]["customer_names"] == ["Topcon"]
    assert out["similar_jiras"][0]["jira_key"] == "GUIDES-881"
    assert out["confidence"]["level"] in {"medium", "high"}
    assert out["must_test_scenarios"]

    required = {
        "scenario",
        "why",
        "evidence",
        "impacted_output",
        "related_entity",
        "test_layer",
        "automation_fit",
    }
    anchors = ("glossstatus", "native_pdf", "guides-881")
    for scenario in out["must_test_scenarios"]:
        assert required <= set(scenario)
        blob = _grounding_blob(scenario)
        assert any(anchor in blob for anchor in anchors), scenario
        assert scenario["evidence"]
        assert scenario["impacted_output"]
        assert scenario["related_entity"]


def test_generic_phrases_do_not_survive_without_specific_evidence():
    enriched = {
        "jira_key": "GUIDES-991",
        "summary": "DITAVAL filters drop platform-specific content",
        "domain": "ditaval",
        "dita_entities": ["ditaval", "platform"],
        "affected_outputs": ["sites"],
    }

    out = generate_uac_recommendations(enriched, [], {})

    for collection_name in ("must_test_scenarios", "missing_clarifications"):
        for row in out[collection_name]:
            blob = _grounding_blob(row)
            if _GENERIC.search(blob):
                assert "ditaval" in blob or "platform" in blob or "sites" in blob or "guides-991" in blob

    all_text = _grounding_blob(out)
    assert "test positive and negative scenarios" not in all_text
    assert "validate functionality" not in all_text


def test_keyref_domain_reasoning_is_specific():
    enriched = {
        "jira_key": "GUIDES-992",
        "summary": "Keyref does not resolve under nested keyscope",
        "domain": "keyref",
        "dita_entities": ["keyref", "keyscope"],
        "affected_outputs": ["editor_preview", "native_pdf"],
    }

    out = generate_uac_recommendations(enriched, [], {})
    joined = _grounding_blob(out["must_test_scenarios"] + out["missing_clarifications"])

    assert "keyref" in joined
    assert "keyscope" in joined or "keydef" in joined
    assert "native_pdf" in joined or "editor_preview" in joined


def test_critic_dedupes_similar_jiras_and_rejects_weak_candidates():
    enriched = {
        "jira_key": "GUIDES-993",
        "summary": "Conref preview differs from output",
        "domain": "conref",
        "dita_entities": ["conref"],
        "affected_outputs": ["native_pdf"],
    }
    similar = [
        {
            "jira_key": "GUIDES-700",
            "title": "Conref output mismatch",
            "document": "conref rendered in native_pdf incorrectly",
            "matching_entities": ["conref"],
            "matching_outputs": ["native_pdf"],
        },
        {
            "jira_key": "GUIDES-700",
            "title": "Duplicate chunk",
            "document": "conref rendered in native_pdf incorrectly",
            "matching_entities": ["conref"],
            "matching_outputs": ["native_pdf"],
        },
        {
            "jira_key": "GUIDES-701",
            "title": "Unrelated admin screen",
            "document": "user profile avatar preference",
            "score": 0.1,
        },
    ]

    out = generate_uac_recommendations(enriched, similar, {})

    keys = [row["jira_key"] for row in out["similar_jiras"]]
    assert keys == ["GUIDES-700"]
    dropped = out["evidence_summary"]["critic"]["dropped"]
    assert any(row["reason"] == "duplicate_jira_key" for row in dropped)
    assert any("weak_evidence" in row["reason"] for row in dropped)


def test_thin_evidence_returns_insufficient_structured_output():
    out = generate_uac_recommendations({}, [], {})

    assert out["risk_summary"]["message"] == INSUFFICIENT_EVIDENCE_MESSAGE
    assert out["must_test_scenarios"] == []
    assert out["missing_clarifications"] == []
    assert out["confidence"]["level"] == "low"
    assert out["confidence"]["score"] == 0.0


def test_jira_key_alone_does_not_generate_generic_scenarios():
    out = generate_uac_recommendations({"jira_key": "GUIDES-994", "summary": "Small fix"}, [], {})

    assert out["risk_summary"]["message"] == INSUFFICIENT_EVIDENCE_MESSAGE
    assert out["must_test_scenarios"] == []
    assert out["missing_clarifications"] == []
    assert out["confidence"]["score"] == 0.0


def test_unknown_domain_ignores_similar_without_current_entity_or_output():
    out = generate_uac_recommendations(
        {
            "jira_key": "GUIDES-995",
            "summary": "Unclassified customer escalation",
            "domain": "unknown",
        },
        [
            {
                "jira_key": "GUIDES-OLD",
                "title": "Potentially similar but structurally thin",
                "document": "historical text without current Jira entity or output overlap",
                "score": 0.9,
            }
        ],
        {"candidate_count": 1},
    )

    assert out["risk_summary"]["message"] == INSUFFICIENT_EVIDENCE_MESSAGE
    assert out["similar_jiras"] == []
    assert out["must_test_scenarios"] == []
    assert any(
        row["reason"] == "ignored_similar_jiras_because_current_jira_has_unknown_domain_and_no_entity_or_output"
        for row in out["evidence_summary"]["critic"]["dropped"]
    )


def test_provider_generic_scenario_is_rejected_even_with_sidecar_evidence():
    class BadProvider:
        provider_name = "bad-test-provider"

        def generate_structured(self, *, system_prompt: str, user_prompt: str, schema_name: str):
            return {
                "must_test_scenarios": [
                    {
                        "scenario": "Validate functionality",
                        "why": "Sidecar fields mention keyref and native_pdf but the scenario itself is generic.",
                        "evidence": [
                            {
                                "source": "current_jira",
                                "jira_key": "GUIDES-996",
                                "field": "dita_entities",
                                "value": "keyref",
                            }
                        ],
                        "impacted_output": "native_pdf",
                        "related_entity": "keyref",
                        "test_layer": "Publishing",
                        "automation_fit": "Partial",
                    }
                ]
            }

    out = UACGenerationEngine(llm_provider=BadProvider()).generate(
        enriched_jira={
            "jira_key": "GUIDES-996",
            "summary": "Keyref fails in Native PDF",
            "domain": "keyref",
            "dita_entities": ["keyref"],
            "affected_outputs": ["native_pdf"],
        },
        similar_jiras=[],
        retrieval_debug={},
    )

    assert all(row["scenario"] != "Validate functionality" for row in out["must_test_scenarios"])
    assert any("generic_phrase_without_specific_evidence" in row["reason"] for row in out["evidence_summary"]["critic"]["dropped"])


def test_prompt_builder_exposes_generation_and_critic_prompts():
    builder = UACPromptBuilder()
    system = builder.build_system_prompt()
    generation = builder.build_generation_prompt(
        enriched_jira={"jira_key": "GUIDES-1"},
        similar_jiras=[],
        retrieval_debug={"candidate_count": 0},
    )
    critic = builder.build_critic_prompt(
        candidate_output={"must_test_scenarios": []},
        enriched_jira={"jira_key": "GUIDES-1"},
        similar_jiras=[],
    )

    assert "Use only supplied evidence" in system
    assert "GUIDES-1" in generation
    assert "hard_reject_phrases" in critic
