"""Tests for enterprise QA workshop response formatting."""

from app.services.enterprise_qa.response_builder import (
    enterprise_workshop_brief,
    _extract_question_bullets,
    _dedupe_question_lines,
)


def test_dedupe_question_lines():
    raw = [
        "What are the measurable acceptance criteria?",
        "What are the measurable acceptance criteria?",
        "Can you provide exact repro steps?",
    ]
    assert _dedupe_question_lines(raw, max_items=5) == [
        "What are the measurable acceptance criteria?",
        "Can you provide exact repro steps?",
    ]


def test_extract_question_bullets_skips_headers():
    md = """## UAC
- First question here?
* Second with star
### Nested
- Third
"""
    b = _extract_question_bullets(md)
    assert "First question here?" in b
    assert "Second with star" in b
    assert "Third" in b


def test_enterprise_workshop_brief_includes_sections():
    out = enterprise_workshop_brief(
        executive_summary="**Executive summary** — test",
        qa_understanding="Understanding line.",
        risk_analysis="Level: high\nWhy: x",
        automation_one_liner="Yes (6/10). · **20/100**",
        uac_points="- Q1?\n- Q2?\n- Q1?",
        similar_note="See related.",
    )
    assert "One-page workshop brief" in out
    assert "Questions to align" in out
    assert out.count("Q1?") == 1
