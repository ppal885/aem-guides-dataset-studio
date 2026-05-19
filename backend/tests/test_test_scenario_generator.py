"""Tests for Jira test scenario generator."""

from __future__ import annotations

from services.test_scenario_generator import generate_test_scenarios


def _anchors_from_enriched(en: dict) -> set[str]:
    keys = [en.get("jira_key") or ""]
    for k in ("dita_entities", "affected_outputs", "components", "customer_names", "labels"):
        for x in en.get(k) or []:
            keys.append(str(x))
    return {s for s in keys if s}


def test_generate_scenarios_grounding_and_cap():
    en = {
        "jira_key": "GUIDES-100",
        "summary": "Native PDF glossary",
        "dita_entities": ["glossStatus"],
        "affected_outputs": ["native_pdf"],
        "components": ["PDF Publishing"],
        "symptoms": ["wrong TOC"],
    }
    sim = [
        {
            "jira_key": "GUIDES-99",
            "scores": {"final": 0.9},
            "matching_entities": ["glossStatus"],
        }
    ]
    out = generate_test_scenarios(en, sim)
    assert len(out) <= 7
    allow = _anchors_from_enriched(en) | {"GUIDES-99"}
    for sc in out:
        blob = " ".join([sc["title"], sc["preconditions"], sc["expected_result"]] + sc["steps"])
        assert any(a and (a in blob or a.upper() in blob.upper()) for a in allow), blob
        assert sc["test_layer"] in ("UI", "API", "Publishing", "Manual")
        assert sc["automation_candidate"] in ("yes", "no", "partial")
        assert sc["priority"] in ("P0", "P1", "P2")
    assert any("GUIDES-99" in " ".join([s["title"], *s["steps"]]) for s in out)


def test_empty_enrichment_returns_empty():
    assert generate_test_scenarios({}, []) == []


def test_fingerprints_unique():
    en = {
        "jira_key": "GUIDES-1",
        "dita_entities": ["e1", "e2"],
        "affected_outputs": ["o1"],
        "components": ["c1"],
    }
    out = generate_test_scenarios(en, [])
    titles = [s["title"] for s in out]
    assert len(titles) == len(set(titles))
