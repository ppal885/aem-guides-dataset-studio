"""Unit tests for QA Studio LLM orchestration (judge, compact plan, retry mock)."""

from __future__ import annotations

import pytest

from app.services.qa_studio_llm_authoring import (
    _compact_plan_for_generation,
    _judge_plan,
    _plan_with_self_correction,
)


def test_judge_plan_passes_minimal_valid():
    fields = {"source_quote": "The PDF export completes with the map title visible."}
    plan = {
        "summary": "s",
        "assertion_traceability": [
            {
                "then_step": "Then the PDF shows the map title",
                "jira_quote": fields["source_quote"],
            }
        ],
        "automation_design": {
            "gherkin_outline": {"then": ["Then the PDF shows the map title"]},
            "step_implementation": [
                {"kind": "when", "text": "export", "page_object_call": "EditorPage.export_pdf()"},
            ],
        },
    }
    ok, critiques, structured = _judge_plan(plan, fields)
    assert ok is True
    assert not critiques
    assert isinstance(structured, list)


def test_judge_plan_fails_missing_traceability():
    fields = {"source_quote": "Expected visible"}
    plan = {"automation_design": {"gherkin_outline": {}, "step_implementation": [{"kind": "when", "page_object_call": "x"}]}}
    ok, critiques, _ = _judge_plan(plan, fields)
    assert ok is False
    assert critiques


def test_compact_plan_for_generation_preserves_keys():
    plan = {
        "jira_analysis": "a",
        "assertion_traceability": [],
        "automation_design": {},
        "summary": "s",
        "playbook_matches": [{"id": "p1"}],
        "noise": "drop",
    }
    compact = _compact_plan_for_generation(plan)
    assert "jira_analysis" in compact
    assert "playbook_matches" in compact
    assert "noise" not in compact


@pytest.mark.asyncio
async def test_plan_self_correction_second_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    async def fake_generate_json(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "summary": "bad",
                "assertion_traceability": [],
                "automation_design": {"gherkin_outline": {"then": []}, "step_implementation": []},
            }
        return {
            "summary": "ok",
            "assertion_traceability": [
                {"then_step": "Then toast visible", "jira_quote": "User sees toast"}
            ],
            "automation_design": {
                "gherkin_outline": {"then": ["Then toast visible"]},
                "step_implementation": [{"kind": "when", "page_object_call": "Shell.click_save()"}],
            },
        }

    monkeypatch.setattr(
        "app.services.qa_studio_llm_authoring.generate_json",
        fake_generate_json,
    )
    plan, last_idx, success, critiques, structured = await _plan_with_self_correction(
        jira_blob="summary: x\nexpected: User sees toast",
        grounding_digest="playbook: …",
        fields={"source_quote": "User sees toast"},
        max_retries=2,
        trace_id=None,
        jira_key=None,
    )
    assert success is True
    assert last_idx == 1
    assert not critiques
    assert plan.get("summary") == "ok"
    assert calls["n"] == 2
    assert structured
