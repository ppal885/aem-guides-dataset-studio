"""Tests for ``uac_ui`` structured contract builder."""

from __future__ import annotations

from app.core.schemas_uac_ui import UacUiContract
from app.services.uac_ui_contract_service import build_uac_ui_contract


def test_build_uac_ui_contract_validates_against_pydantic() -> None:
    payload = {
        "jira_key": "EPV-42",
        "classification": {
            "jira_key": "EPV-42",
            "domain": "native_pdf",
            "dita_entities": ["keyref"],
            "affected_outputs": ["native_pdf"],
        },
        "risk_summary": {"level": "high", "risk_score": 3, "drivers": ["Driver one"]},
        "similar_jiras": [
            {
                "jira_key": "EPV-99",
                "title": "Prior PDF bug",
                "why_similar": "Entity overlap",
                "what_we_learned": "Check keyref chain",
                "confidence_score": 0.8,
                "scores": {"final": 0.9, "confidence": 0.8},
            }
        ],
        "must_test_scenarios": [
            {
                "scenario": "Publish sanity",
                "why": "Regression",
                "evidence": "EPV-99",
                "test_layer": "publish",
                "priority": "P1",
            }
        ],
        "missing_clarifications": [{"question": "Which preset?", "why": "Repro"}],
        "automation_fit": {"fit": "Partial", "primary_test_layer": "API", "framework": "REST"},
        "confidence": {"score": 0.5, "level": "medium", "signals": ["a"]},
        "quality_score": 50,
        "answer_quality": {
            "score": 50,
            "generic_phrases_found": [],
            "missing_specificity": [],
            "recommendation": "rewrite",
        },
        "uac_validation_ok": True,
        "uac_validation_errors": [],
        "insufficient_similar_evidence": False,
        "claim_verification": {"dropped_claims": [], "downgraded_claims": [{}], "unsupported_claims": []},
        "uac_guardrails": {"warnings": [{"code": "x", "message": "watch"}], "blocked_claims": []},
        "uac_decision_record": {
            "summary": "Snap",
            "release_risk": "Risk",
            "decisions_needed": ["Q1"],
            "qa_commitments": ["C1"],
            "dataset_needed": ["Add fixtures"],
        },
        "retrieval_debug": {"domain": "native_pdf", "extracted": {}, "scores": [{"jira_key": "EPV-99"}]},
        "structured_uac": {},
        "regeneration_used": False,
    }
    ui = build_uac_ui_contract(payload, debug=False)
    UacUiContract.model_validate(ui)
    assert ui["risk_badge"]["level"] == "high"
    assert ui["similar_jira_learning_cards"][0]["why_relevant"] == "Entity overlap"
    assert ui["must_test_scenario_table"]["rows"][0]["id"] == "mt-0"
    assert ui["debug_accordion"]["debug_mode"] is False
    assert ui["debug_accordion"]["claim_verification_detail"] is None

    ui_dbg = build_uac_ui_contract(payload, debug=True)
    UacUiContract.model_validate(ui_dbg)
    assert ui_dbg["debug_accordion"]["debug_mode"] is True
    assert ui_dbg["debug_accordion"]["claim_verification_detail"] is not None
