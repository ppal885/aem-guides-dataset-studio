"""Unit tests for UAC QA handoff JSON normalization (no live LLM)."""

from __future__ import annotations

from services.uac import qa_handoff_service as qh


def test_parse_llm_json_raw_object():
    raw = '{"regression_breadth": "smoke", "smoke_checks": ["A"]}'
    parsed = qh._parse_llm_json(raw)
    assert parsed is not None
    assert parsed["regression_breadth"] == "smoke"


def test_parse_llm_json_fenced():
    raw = """Here is JSON:
```json
{"regression_breadth": "full", "smoke_checks": ["x"]}
```
"""
    parsed = qh._parse_llm_json(raw)
    assert parsed is not None
    assert parsed["regression_breadth"] == "full"


def test_normalize_plan_caps_and_blocking_roles():
    raw = {
        "regression_breadth": "bogus",
        "smoke_checks": [f"item-{i}" for i in range(10)],
        "blocking_for_signoff": [
            {"question": "  Q1? ", "owner_role": "DEV"},
            {"question": "", "owner_role": "qa"},
            {"question": "Q2", "owner_role": "nope"},
        ],
        "jira_test_script": {
            "title": "T",
            "preconditions": ["p"],
            "steps": [f"s{i}" for i in range(12)],
            "expected_result": "ok",
        },
    }
    norm = qh._normalize_plan(raw)
    assert norm["regression_breadth"] == ""
    assert len(norm["smoke_checks"]) == 5
    assert len(norm["blocking_for_signoff"]) == 2
    assert norm["blocking_for_signoff"][0]["owner_role"] == "dev"
    assert norm["blocking_for_signoff"][1]["owner_role"] == "other"
    assert len(norm["jira_test_script"]["steps"]) == 8


def test_build_user_prompt_contains_key_fields():
    from app.core.schemas_jira_enrichment import JiraEnrichedDocument

    en = JiraEnrichedDocument(
        jira_key="EPV-7",
        summary="S",
        description="D",
        domain="native_pdf",
        dita_entities=["keyref"],
    )
    p = qh._build_user_prompt(
        en,
        uac_answer="# brief",
        similar_slim=[{"jira_key": "EPV-1", "title": "t", "why": "w"}],
        scenario_titles=["Scenario one"],
        risk_level="high",
        insufficient_similar=False,
    )
    assert "EPV-7" in p
    assert "keyref" in p
    assert "insufficient_similar_ticket_pool" in p
    assert "ground truth" in p.lower()
