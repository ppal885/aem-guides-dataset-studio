"""RegressionMemoryEngine — historical regression signals and risk/release hooks."""

from __future__ import annotations

from app.services.regression_memory_engine import (
    RegressionMemoryEngine,
    apply_regression_memory_risk_boost,
    boost_release_readiness_for_regression,
)


def test_analyze_detects_related_regression_and_publishing():
    hits = [
        {
            "jira_key": "GUIDES-10",
            "title": "Publish regression",
            "document": "PDF publish failed again after upgrade; regression in output pipeline.",
        }
    ]
    out = RegressionMemoryEngine().analyze(
        labels=["regression"],
        components=["publishing"],
        related_hits=hits,
        issue_chunks=[],
        jira_key="GUIDES-1",
        failure_intelligence=None,
    )
    assert out["repeat_count"] >= 1
    assert out["regression_confidence"] >= 0.15
    assert any("repeated" in str(h.get("area", "")) for h in out["historical_regressions"])


def test_enrich_merges_failure_intel_without_duplicating_rows():
    base = RegressionMemoryEngine().analyze(
        labels=[],
        components=[],
        related_hits=[],
        issue_chunks=[],
        jira_key=None,
        failure_intelligence=None,
    )
    fi = {
        "related_failures": [{"test": "publish_smoke: pdf baseline compare", "correlation": 0.5}],
        "repeated_failure_signals": ["publish_smoke (x2)"],
        "failure_clusters": [{"signature": "publish", "examples": ["pdf output"], "count": 2}],
    }
    merged = RegressionMemoryEngine().enrich_with_failures(base, fi)
    assert merged["repeat_count"] >= base["repeat_count"]


def test_risk_and_release_boost_when_strong_signal():
    mem = {
        "historical_regressions": [{"area": "x"}] * 3,
        "repeat_count": 8,
        "highly_unstable_areas": ["repeated_publishing_failures"],
        "regression_confidence": 0.62,
    }
    risk = apply_regression_memory_risk_boost(
        {"risk_level": "medium", "why": "test", "confidence": 0.5, "risk_areas": []},
        mem,
    )
    assert risk["risk_level"] == "high"

    rel = boost_release_readiness_for_regression(
        {"release_risk": "low", "weak_areas": [], "manual_focus_areas": []},
        mem,
        current_risk_level="high",
    )
    assert rel["release_risk"] == "high"
