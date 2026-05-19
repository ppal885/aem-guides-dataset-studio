"""Tests for UAC enterprise guardrails."""

from __future__ import annotations

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from services.uac.uac_guardrails import check_uac_guardrails


def _enriched(**kw: object) -> JiraEnrichedDocument:
    d = {
        "jira_key": "GUIDES-1",
        "summary": "Keyref issue",
        "description": "Problem in native_pdf path.",
        "dita_entities": ["keyref"],
    }
    d.update(kw)
    return JiraEnrichedDocument.model_validate(d)


def test_blocked_secret_bearer():
    r = check_uac_guardrails(
        {
            "uac_answer": "Use header Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
            "must_test_scenarios": [],
            "risk_summary": {"drivers": []},
            "missing_clarifications": [],
            "similar_jiras": [{"jira_key": "X-1"}],
        },
        _enriched(),
    )
    assert any("secret" in b["reason"] for b in r["blocked_claims"])


def test_blocked_customfield_not_in_issue():
    r = check_uac_guardrails(
        {
            "uac_answer": "See customfield_99999 for approval state.",
            "must_test_scenarios": [],
            "risk_summary": {"drivers": []},
            "missing_clarifications": [],
            "similar_jiras": [{"jira_key": "X-1"}],
        },
        _enriched(description="no custom fields here"),
    )
    assert any(b["reason"] == "invented_or_unreferenced_jira_customfield" for b in r["blocked_claims"])


def test_blocked_customer_impact_without_customer_evidence():
    r = check_uac_guardrails(
        {
            "risk_summary": {"drivers": ["Customer impact is production down for all clients."]},
            "must_test_scenarios": [],
            "missing_clarifications": [],
            "similar_jiras": [],
        },
        _enriched(),
    )
    assert any("customer_impact" in b["reason"] for b in r["blocked_claims"])


def test_blocked_historical_without_similar():
    r = check_uac_guardrails(
        {
            "risk_summary": {"drivers": ["Historically this broke in past releases."]},
            "must_test_scenarios": [],
            "missing_clarifications": [],
            "similar_jiras": [],
        },
        _enriched(),
    )
    assert any("historical" in b["reason"] for b in r["blocked_claims"])


def test_warning_automation_yes_without_evidence():
    r = check_uac_guardrails(
        {
            "automation_fit": {"fit": "Yes"},
            "must_test_scenarios": [
                {
                    "scenario": "Do thing",
                    "why": "Because",
                    "evidence": [],
                    "test_layer": "Manual",
                    "priority": "P3",
                }
            ],
            "risk_summary": {"drivers": []},
            "missing_clarifications": [],
            "similar_jiras": [{"jira_key": "A-1"}],
        },
        _enriched(),
    )
    assert any(w["code"] == "automation_not_fully_deterministic" for w in r["warnings"])


def test_warning_too_many_scenarios():
    scen = [
        {
            "scenario": f"S{i}",
            "why": "W",
            "evidence": ["e"],
            "test_layer": "Manual",
            "priority": "P2",
        }
        for i in range(9)
    ]
    r = check_uac_guardrails(
        {
            "must_test_scenarios": scen,
            "risk_summary": {"drivers": []},
            "missing_clarifications": [],
            "similar_jiras": [],
        },
        _enriched(),
    )
    assert any(w["code"] == "too_many_scenarios" for w in r["warnings"])
    assert any(b["reason"] == "scenario_over_policy_limit" for b in r["blocked_claims"])


def test_return_shape():
    r = check_uac_guardrails(
        {"must_test_scenarios": [], "risk_summary": {"drivers": []}, "missing_clarifications": [], "similar_jiras": []},
        _enriched(),
    )
    assert set(r.keys()) == {"warnings", "blocked_claims"}
