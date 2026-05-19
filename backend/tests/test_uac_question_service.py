"""Tests for UAC clarification question generator."""

from __future__ import annotations

import re

from services.uac_question_service import generate_uac_questions

_ALLOWED = frozenset({"PM", "Dev", "QA", "Tech Writer"})
_GENERIC = re.compile(
    r"(?i)what\s+is\s+(the\s+)?expected\s+behavior|requirements?\s+clear|what\s+should\s+happen"
)


def test_questions_max_five_and_schema():
    en = {
        "jira_key": "GUIDES-200",
        "dita_entities": ["glossStatus"],
        "affected_outputs": ["native_pdf"],
        "components": ["Native PDF"],
        "missing_info": ["Exact FOP template version"],
    }
    sim = [{"jira_key": "GUIDES-199", "matching_entities": ["glossStatus"], "matching_outputs": ["native_pdf"]}]
    out = generate_uac_questions(en, sim)
    assert len(out) <= 5
    for row in out:
        assert set(row.keys()) == {
            "question",
            "why_it_matters",
            "who_should_answer",
            "related_entity",
            "risk_if_unanswered",
        }
        assert row["who_should_answer"] in _ALLOWED
        q = row["question"]
        rel = row["related_entity"]
        assert rel and (rel in q or rel.lower() in q.lower())


def test_native_pdf_and_glossstatus_grounded():
    en = {
        "jira_key": "GUIDES-201",
        "dita_entities": ["glossStatus"],
        "affected_outputs": ["native_pdf"],
    }
    out = generate_uac_questions(en, [])
    assert out
    joined = " ".join(r["question"] for r in out).lower()
    assert "native_pdf" in joined or "native pdf" in joined
    assert "glossstatus" in joined


def test_thin_enrichment_returns_empty():
    assert generate_uac_questions({}, []) == []


def test_not_only_generic_wording():
    en = {
        "jira_key": "GUIDES-202",
        "dita_entities": ["xref"],
        "affected_outputs": ["html5"],
    }
    out = generate_uac_questions(en, [])
    for row in out:
        q = row["question"]
        if _GENERIC.search(q):
            assert "html5" in q.lower() or "xref" in q.lower() or "GUIDES-202" in q
