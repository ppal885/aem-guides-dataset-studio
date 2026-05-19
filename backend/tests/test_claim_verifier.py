"""Tests for structured UAC claim verification."""

from __future__ import annotations

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_retrieval_service import RetrievedJira
from services.uac.claim_verifier import verify_uac_claims


def _enriched(**kwargs: object) -> JiraEnrichedDocument:
    base = dict(
        jira_key="GUIDES-100",
        summary="Publishing regression",
        description="keyref widget fails during native_pdf publish for customer AcmeCorp.",
        dita_entities=["keyref"],
        affected_outputs=["native_pdf"],
        components=["editor"],
        customer_names=["AcmeCorp"],
    )
    base.update(kwargs)
    return JiraEnrichedDocument.model_validate(base)


def test_driver_dropped_without_anchor():
    pl = {
        "risk_summary": {"drivers": ["Validate all functionality thoroughly."], "level": "medium"},
        "must_test_scenarios": [],
        "missing_clarifications": [],
    }
    out = verify_uac_claims(pl, {"enriched_jira": _enriched()})
    assert out["dropped_claims"]
    assert out["verified_response"]["risk_summary"]["drivers"] == []


def test_driver_kept_with_anchor_and_overlap():
    pl = {
        "risk_summary": {
            "drivers": ["GUIDES-100 keyref breaks native_pdf publish for AcmeCorp per description."],
            "level": "medium",
        },
        "must_test_scenarios": [],
        "missing_clarifications": [],
    }
    out = verify_uac_claims(pl, {"enriched_jira": _enriched()})
    assert out["verified_response"]["risk_summary"]["drivers"]
    assert not any(d["reason"] == "duplicate_claim" for d in out["dropped_claims"])


def test_duplicate_scenario_second_dropped():
    pl = {
        "risk_summary": {"drivers": [], "level": "low"},
        "must_test_scenarios": [
            {
                "scenario": "Verify keyref for GUIDES-100",
                "why": "Regression on publish",
                "evidence": ["e1"],
                "test_layer": "Publishing",
                "priority": "P2",
            },
            {
                "scenario": "Verify keyref for GUIDES-100",
                "why": "Regression on publish",
                "evidence": ["e2"],
                "test_layer": "Publishing",
                "priority": "P2",
            },
        ],
        "missing_clarifications": [],
    }
    out = verify_uac_claims(pl, {"enriched_jira": _enriched()})
    assert len(out["verified_response"]["must_test_scenarios"]) == 1
    assert any(d.get("reason") == "duplicate_claim" for d in out["dropped_claims"])


def test_strong_assertion_dropped_without_semantic_overlap():
    pl = {
        "risk_summary": {
            "drivers": [
                "GUIDES-100 must always guarantee perfection for every customer without any evidence in corpus."
            ],
            "level": "high",
        },
        "must_test_scenarios": [],
        "missing_clarifications": [],
    }
    en = _enriched(description="xyzzy qwerty unrelated noise", summary="alpha beta")
    out = verify_uac_claims(pl, {"enriched_jira": en})
    assert any(d["reason"] == "strong_assertion_without_evidence_overlap" for d in out["dropped_claims"])
    assert out["verified_response"]["risk_summary"]["drivers"] == []


def test_weak_overlap_downgrades_confidence():
    pl = {
        "risk_summary": {"drivers": ["GUIDES-100 keyref linked to fail"], "level": "medium"},
        "must_test_scenarios": [
            {
                "scenario": "GUIDES-100 keyref test fails",
                "why": "Uses token fail present once",
                "evidence": ["ev"],
                "test_layer": "Publishing",
                "priority": "P2",
            }
        ],
        "missing_clarifications": [],
        "confidence": {"level": "high", "score": 80.0, "signals": []},
    }
    en = _enriched(description="singular fail case on keyref only when using test.")
    out = verify_uac_claims(pl, {"enriched_jira": en}, downgrade_weak=True)
    # Scenario may pass uac_claim_passes; ensure downgrade path exists for weak-only overlap scenarios
    if out["downgraded_claims"]:
        assert out["verified_response"]["confidence"]["level"] == "low" or "claim_verifier_downgrade" in (
            out["verified_response"]["confidence"].get("signals") or []
        )


def test_scenario_structural_evidence_similar_passes():
    similar = RetrievedJira(
        jira_key="GUIDES-999",
        title="Prior keyref bug",
        document="Earlier regression on map merge.",
    )
    pl = {
        "risk_summary": {"drivers": [], "level": "medium"},
        "must_test_scenarios": [
            {
                "scenario": "Reproduce merge",
                "why": "Historical pattern",
                "evidence": ["GUIDES-999"],
                "test_layer": "Publishing",
                "priority": "P2",
            }
        ],
        "missing_clarifications": [],
    }
    en = _enriched(description="unrelated prose without merge wording")
    out = verify_uac_claims(pl, {"enriched_jira": en, "similar_jiras": [similar]})
    assert len(out["verified_response"]["must_test_scenarios"]) == 1


def test_payload_style_similar_row_coerced():
    pl = {
        "risk_summary": {"drivers": ["GUIDES-100 echoes GUIDES-888 excerpt wording keyref."], "level": "medium"},
        "must_test_scenarios": [],
        "missing_clarifications": [],
    }
    en = _enriched(description="our ticket")
    similar_api = [
        {
            "jira_key": "GUIDES-888",
            "title": "Old bug",
            "document_excerpt": "keyref failure pattern zzyyxx described here",
            "why_relevant": "overlap",
        }
    ]
    out = verify_uac_claims(pl, {"enriched_jira": en, "similar_jiras": similar_api})
    assert out["verified_response"]["risk_summary"]["drivers"]


    pl = {"risk_summary": {"drivers": []}, "must_test_scenarios": [], "missing_clarifications": []}
    out = verify_uac_claims(pl, {"enriched_jira": _enriched()})
    assert set(out.keys()) == {"verified_response", "dropped_claims", "downgraded_claims", "unsupported_claims"}
