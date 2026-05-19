"""Tests for strict UAC API payload validation and repair orchestration."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.uac_copilot_analyze_service import _format_structured_uac_markdown
from services.uac.uac_output_validator import (
    apply_strict_uac_validation,
    validate_uac_payload,
)


def _doc() -> JiraEnrichedDocument:
    return JiraEnrichedDocument(
        jira_key="EPV-99",
        summary="Map publish issue",
        domain="native_pdf",
        dita_entities=["map"],
        affected_outputs=["native_pdf"],
    )


def _valid_scenario() -> dict:
    return {
        "scenario": "EPV-99: Validate map assembly in native_pdf",
        "why": "DITA map and native_pdf are grounded anchors for this ticket.",
        "evidence": [{"source": "current_jira", "field": "entity", "value": "map"}],
        "test_layer": "Publishing",
        "priority": "P1",
        "automation_fit": "Partial",
        "related_entity": "map",
        "impacted_output": "native_pdf",
    }


def _valid_payload() -> dict:
    return {
        "jira_key": "EPV-99",
        "classification": {
            "domain": "native_pdf",
            "issue_type": "Bug",
            "customer_names": [],
            "affected_outputs": ["native_pdf"],
            "dita_entities": ["map"],
            "jira_key": "EPV-99",
        },
        "risk_summary": {"level": "high", "drivers": ["EPV-99: historical evidence raises map/native_pdf regression risk."]},
        "similar_jiras": [],
        "must_test_scenarios": [_valid_scenario()],
        "missing_clarifications": [
            {
                "question": "Does EPV-99 require ditaval filtering for native_pdf?",
                "why": "Output scope depends on ditaval.",
                "evidence": [{"source": "current_jira", "field": "dita_entities", "value": "map"}],
                "related_entity": "map",
            }
        ],
        "confidence": {"score": 0.85, "level": "high", "signals": ["grounded"]},
        "structured_uac": {},
        "uac_answer": "draft markdown",
    }


def test_validate_synthetic_payload_passes():
    ok, errs = validate_uac_payload(_valid_payload(), lenient=False)
    assert ok is True
    assert errs == []


def test_validate_missing_classification():
    p = _valid_payload()
    p["classification"] = {}
    ok, errs = validate_uac_payload(p, lenient=False)
    assert ok is False
    assert "missing_classification" in errs


def test_validate_missing_risk_score_and_level():
    p = _valid_payload()
    p["risk_summary"] = {"drivers": ["x"]}
    ok, errs = validate_uac_payload(p, lenient=False)
    assert ok is False
    assert "missing_risk_score_and_level" in errs


def test_validate_scenario_missing_evidence():
    p = _valid_payload()
    p["must_test_scenarios"] = [dict(_valid_scenario(), evidence=[])]
    ok, errs = validate_uac_payload(p, lenient=False)
    assert ok is False
    assert any("missing_evidence" in e for e in errs)


def test_validate_scenario_missing_test_layer():
    p = _valid_payload()
    sc = _valid_scenario()
    sc["test_layer"] = ""
    p["must_test_scenarios"] = [sc]
    ok, errs = validate_uac_payload(p, lenient=False)
    assert ok is False
    assert any("missing_test_layer" in e for e in errs)


def test_validate_scenario_missing_priority():
    p = _valid_payload()
    sc = _valid_scenario()
    del sc["priority"]
    p["must_test_scenarios"] = [sc]
    ok, errs = validate_uac_payload(p, lenient=False)
    assert ok is False
    assert any("missing_priority" in e for e in errs)


def test_validate_too_many_scenarios():
    p = _valid_payload()
    p["must_test_scenarios"] = [_valid_scenario() for _ in range(8)]
    ok, errs = validate_uac_payload(p, lenient=False)
    assert ok is False
    assert any(e.startswith("too_many_scenarios") for e in errs)


def test_validate_too_many_clarifications():
    p = _valid_payload()
    row = p["missing_clarifications"][0]
    p["missing_clarifications"] = [dict(row, question=f"Q{i}?") for i in range(6)]
    ok, errs = validate_uac_payload(p, lenient=False)
    assert ok is False
    assert any(e.startswith("too_many_clarifications") for e in errs)


def test_validate_generic_phrase_in_scenario():
    p = _valid_payload()
    sc = _valid_scenario()
    sc["why"] = "We should verify UI behavior for the output."
    p["must_test_scenarios"] = [sc]
    ok, errs = validate_uac_payload(p, lenient=False)
    assert ok is False
    assert any("generic_phrase" in e for e in errs)


def test_lenient_allows_empty_scenarios_and_empty_confidence():
    p = _valid_payload()
    p["must_test_scenarios"] = []
    p["confidence"] = {}
    ok, errs = validate_uac_payload(p, lenient=True)
    assert ok is True
    assert errs == []


def test_apply_strict_repair_single_llm_call():
    p = _valid_payload()
    del p["must_test_scenarios"][0]["priority"]

    fixed = {
        "risk_summary": p["risk_summary"],
        "must_test_scenarios": [_valid_scenario()],
        "missing_clarifications": p["missing_clarifications"],
        "confidence": p["confidence"],
    }

    async def _run():
        with patch("app.services.llm_service.is_llm_available", return_value=True):
            with patch("app.services.llm_service.generate_json", new_callable=AsyncMock) as gen:
                gen.return_value = fixed
                out = await apply_strict_uac_validation(
                    p,
                    enriched=_doc(),
                    lenient=False,
                    format_markdown_fn=_format_structured_uac_markdown,
                )
        assert gen.call_count == 1
        assert out["uac_validation_ok"] is True
        assert out.get("uac_repair_attempted") is True
        assert out["must_test_scenarios"][0].get("priority") == "P1"
        assert "### 1. Jira Classification" in out["uac_answer"]

    asyncio.run(_run())


def test_apply_strict_partial_when_payload_still_invalid_after_normalize():
    """Normalizer does not repair ``similar_jiras`` type; errors should remain flagged."""

    p = _valid_payload()
    p["similar_jiras"] = "not-a-list"

    async def _run():
        with patch("app.services.llm_service.is_llm_available", return_value=False):
            out = await apply_strict_uac_validation(
                p,
                enriched=_doc(),
                lenient=False,
                format_markdown_fn=lambda pl: "md",
            )
        assert out["uac_validation_ok"] is False
        assert out.get("uac_repair_attempted") is False
        assert "similar_jiras_not_list" in (out.get("uac_validation_errors") or [])
        w = out.get("uac_validation_warnings") or []
        assert w

    asyncio.run(_run())