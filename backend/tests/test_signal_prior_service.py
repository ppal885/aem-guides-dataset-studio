"""Tests for signal prior scoring service."""
import pytest

from app.services.signal_prior_service import compute_signal_priors, merge_priors_with_llm


def test_keyref_keywords_boost_keyref_score():
    """Evidence with keyref keywords should boost keyref score."""
    text = "keyref keydef duplicate key nested keymap map hierarchy"
    scores = compute_signal_priors(text)
    assert scores["keyref"] >= 0.5
    assert scores["keyref"] > scores.get("xref", 0)


def test_xref_keywords_boost_xref_score():
    """Evidence with xref keywords (and no keyref) should boost xref."""
    text = "xref href cross reference external link"
    scores = compute_signal_priors(text)
    assert scores["xref"] > 0
    assert scores["keyref"] < 0.5


def test_conref_keywords_boost_conref_score():
    """Evidence with conref keywords should boost conref."""
    text = "conref conkeyref content reuse"
    scores = compute_signal_priors(text)
    assert scores["conref"] > 0


def test_merge_priors_with_llm():
    """Merge should combine prior and LLM scores."""
    priors = {"keyref": 0.8, "xref": 0.2}
    llm = {"keyref": 0.6, "xref": 0.4}
    merged = merge_priors_with_llm(priors, llm, prior_weight=0.5)
    assert merged["keyref"] == 0.5 * 0.8 + 0.5 * 0.6
    assert merged["xref"] == 0.5 * 0.2 + 0.5 * 0.4


def test_empty_text_returns_fallback():
    """Empty text returns minimal keyref fallback."""
    scores = compute_signal_priors("")
    assert scores["keyref"] == 0.1
    assert max(scores.values()) <= 0.1
