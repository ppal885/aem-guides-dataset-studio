"""Tests for UAC anti-repetition memory (SQLite-backed dedupe / anchor strengthening)."""

from __future__ import annotations

import uuid

import pytest

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.db.session import SessionLocal
from app.db.uac_memory_models import UacAntiRepetitionMemory
from services.uac.anti_repetition_service import (
    _norm_domain,
    apply_anti_repetition,
)


def _scenario_row(title: str) -> dict:
    return {
        "scenario": title,
        "why": "Regression risk for this workflow.",
        "evidence": ["chunk-1"],
        "test_layer": "Manual",
        "priority": "P2",
    }


def _base_payload(domain_jira: str, scenarios: list[dict], drivers: list[str], questions: list[str]) -> dict:
    return {
        "classification": {"jira_key": domain_jira, "domain": "publishing"},
        "risk_summary": {"level": "medium", "risk_score": 5, "drivers": drivers},
        "similar_jiras": [],
        "must_test_scenarios": scenarios,
        "missing_clarifications": [{"question": q, "why": "Gap"} for q in questions],
        "confidence": {"overall": 0.75},
        "uac_answer": "# placeholder",
        "structured_uac": {},
    }


def _cleanup_domain(sess, domain_norm: str) -> None:
    sess.query(UacAntiRepetitionMemory).filter(UacAntiRepetitionMemory.domain == domain_norm).delete(
        synchronize_session=False
    )
    sess.commit()


def test_memory_collision_rewrites_duplicate_scenario():
    domain_token = f"pub_coll_{uuid.uuid4().hex[:12]}"
    domain_norm = _norm_domain(domain_token)
    enriched = JiraEnrichedDocument(
        jira_key="GUIDES-MEM1",
        domain=domain_token,
        dita_entities=["install_topic"],
        affected_outputs=["native_pdf"],
        summary="customer reported inconsistent numbering headers",
    )
    dup_title = "Verify consolidated publishing pipeline outputs predictable results for large maps"
    session = SessionLocal()
    try:
        _cleanup_domain(session, domain_norm)
        for _ in range(2):
            session.add(
                UacAntiRepetitionMemory(
                    id=str(uuid.uuid4()),
                    domain=domain_norm,
                    jira_key="GUIDES-OLD",
                    scenario_titles=[dup_title],
                    risk_drivers=["prior driver"],
                    clarification_questions=["prior q"],
                    payload_hash="x",
                )
            )
        session.commit()

        payload = _base_payload(
            "GUIDES-MEM1",
            [_scenario_row(dup_title)],
            ["Concrete risk about install_topic in native_pdf output."],
            ["What repro steps exist for the customer site?"],
        )
        meta = apply_anti_repetition(payload, enriched, lenient=False, session=session, format_markdown_fn=None)
        out_title = payload["must_test_scenarios"][0]["scenario"]
        assert meta.scenarios_rewritten_memory >= 1
        assert "guides-mem1" in out_title.lower()
    finally:
        _cleanup_domain(session, domain_norm)
        session.close()


def test_anchor_ratio_strengthens_weak_scenarios():
    domain_token = f"pub_anchor_{uuid.uuid4().hex[:12]}"
    domain_norm = _norm_domain(domain_token)
    enriched = JiraEnrichedDocument(
        jira_key="GUIDES-ANC9",
        domain=domain_token,
        dita_entities=["topicref"],
        affected_outputs=["html5"],
        components=["Editor"],
        summary="unexpected behavior when merging branches",
    )
    scenarios = [
        _scenario_row("Exercise end to end approval workflow without regression"),
        _scenario_row("Confirm administrator settings persist as expected after reload"),
        _scenario_row("Validate search indexing returns stable ordering"),
        _scenario_row("Check notification emails arrive within expected window"),
        _scenario_row("Ensure version labels remain consistent across sessions"),
    ]
    session = SessionLocal()
    try:
        _cleanup_domain(session, domain_norm)
        payload = _base_payload(
            "GUIDES-ANC9",
            scenarios,
            ["Risk concentrated on topicref merge paths affecting html5 output."],
            ["Which build confirms the customer symptom?"],
        )
        meta = apply_anti_repetition(payload, enriched, lenient=False, session=session, format_markdown_fn=None)
        assert meta.scenarios_strengthened_anchor >= 1
        titles = [str(r.get("scenario") or "").lower() for r in payload["must_test_scenarios"]]
        anchored = sum(
            1
            for t in titles
            if "guides-anc9" in t or "topicref" in t or "html5" in t or "editor" in t or "merging" in t
        )
        assert anchored >= 3
    finally:
        _cleanup_domain(session, domain_norm)
        session.close()


def test_generic_driver_dropped_and_clarification_rewritten():
    domain_token = f"pub_generic_{uuid.uuid4().hex[:12]}"
    domain_norm = _norm_domain(domain_token)
    enriched = JiraEnrichedDocument(
        jira_key="GUIDES-GEN1",
        domain=domain_token,
        dita_entities=["keyref"],
        affected_outputs=["pdf"],
    )
    session = SessionLocal()
    try:
        _cleanup_domain(session, domain_norm)
        payload = _base_payload(
            "GUIDES-GEN1",
            [_scenario_row("Validate keyref resolution after map edits")],
            [
                "keyref mismatches can cascade into broken pdf links for this ticket.",
                "We should follow best practices when testing.",
            ],
            ["It depends on the environment without more detail from QA."],
        )
        meta = apply_anti_repetition(payload, enriched, lenient=False, session=session, format_markdown_fn=None)
        assert meta.drivers_dropped_generic >= 1
        assert meta.clarifications_rewritten >= 1
        drivers = payload["risk_summary"]["drivers"]
        assert all("follow best practices" not in d.lower() for d in drivers)
        q = payload["missing_clarifications"][0]["question"].lower()
        assert "guides-gen1" in q or "keyref" in q
    finally:
        _cleanup_domain(session, domain_norm)
        session.close()


def test_driver_rewritten_when_matching_memory():
    domain_token = f"pub_drv_mem_{uuid.uuid4().hex[:12]}"
    domain_norm = _norm_domain(domain_token)
    driver_text = "Installation misses silently corrupt the rendered PDF bookmarks structure"
    enriched = JiraEnrichedDocument(
        jira_key="GUIDES-DRV1",
        domain=domain_token,
        dita_entities=["install_map"],
        affected_outputs=["pdf"],
    )
    session = SessionLocal()
    try:
        _cleanup_domain(session, domain_norm)
        session.add(
            UacAntiRepetitionMemory(
                id=str(uuid.uuid4()),
                domain=domain_norm,
                jira_key="GUIDES-PREV",
                scenario_titles=["other"],
                risk_drivers=[driver_text],
                clarification_questions=[],
                payload_hash="h",
            )
        )
        session.commit()
        payload = _base_payload(
            "GUIDES-DRV1",
            [_scenario_row("Smoke test install_map publication")],
            [driver_text],
            ["Which logs show the silent failure?"],
        )
        meta = apply_anti_repetition(payload, enriched, lenient=False, session=session, format_markdown_fn=None)
        assert meta.drivers_rewritten >= 1
        assert payload["risk_summary"]["drivers"][0].lower().startswith("guides-drv1:")
    finally:
        _cleanup_domain(session, domain_norm)
        session.close()


def test_disabled_short_circuits(monkeypatch):
    monkeypatch.setattr("services.uac.anti_repetition_service._ENABLED", False)
    enriched = JiraEnrichedDocument(jira_key="GUIDES-OFF", domain="publishing")
    payload = _base_payload("GUIDES-OFF", [_scenario_row("Something")], ["d1"], ["q1"])
    meta = apply_anti_repetition(payload, enriched, lenient=False, format_markdown_fn=None)
    assert meta.skipped is True
    assert meta.reasons
