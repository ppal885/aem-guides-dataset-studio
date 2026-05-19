"""Tests for QA reasoning JSON parsing."""

from app.services.qa_reasoning_engine import parse_llm_json_dict


def test_parse_llm_json_pure():
    d = parse_llm_json_dict('{"understanding": "x", "confidence": 0.5}')
    assert d is not None
    assert d["understanding"] == "x"


def test_parse_llm_json_fenced():
    raw = "```json\n{\"understanding\": \"ok\", \"assumptions\": []}\n```"
    d = parse_llm_json_dict(raw)
    assert d is not None
    assert d["understanding"] == "ok"


def test_parse_llm_json_prose_prefix_and_trailing():
    raw = 'Here is the JSON:\n{"understanding": "y", "confidence": 0.9}\nHope this helps.'
    d = parse_llm_json_dict(raw)
    assert d is not None
    assert d["understanding"] == "y"
    assert d["confidence"] == 0.9
