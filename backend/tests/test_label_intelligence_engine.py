"""Tests for Label Intelligence Engine."""

from __future__ import annotations

from app.services.label_intelligence_engine import (
    LabelIntelligenceEngine,
    analyze_issue_labels,
    expanded_label_tokens_for_retrieval,
)


def test_analyze_groups_regression_publishing_customer() -> None:
    labels = ["regression", "publishing", "cisco", "customer-escalation", "flaky"]
    out = analyze_issue_labels(labels)
    assert "regression" in out["risk_domains"] or "regression" in " ".join(out["risk_domains"])
    assert "publishing" in out["feature_domains"] or "publish" in out["feature_domains"]
    assert "cisco" in [x.lower() for x in out["customer_domains"]] or "Cisco" in out["customer_domains"]
    assert any("escalation" in x.lower() for x in out["testing_implications"] + out["uac_focus_points"]) or any(
        "customer-escalation" in str(x) for x in out["risk_domains"]
    )
    assert any("flaky" in x.lower() for x in out["automation_implications"])


def test_baseline_metadata_accessibility_implications() -> None:
    out = analyze_issue_labels(["baseline", "metadata", "accessibility", "performance"])
    assert out["feature_domains"]
    ti = " ".join(out["testing_implications"]).lower()
    assert "version" in ti or "baseline" in ti
    assert "metadata" in ti or "property" in ti
    assert "accessibility" in ti or "keyboard" in ti
    assert "scale" in ti or "load" in ti or "resource" in ti


def test_expanded_tokens_includes_publishing_synonyms() -> None:
    ex = expanded_label_tokens_for_retrieval(["Publishing"])
    assert "publishing" in ex
    assert "pdf" in ex or "output" in ex


def test_label_intelligence_engine_class() -> None:
    eng = LabelIntelligenceEngine()
    r = eng.analyze(["new-editor", "scalability"])
    assert isinstance(r, dict)
    assert "new-editor" in r["feature_domains"] or "editor" in " ".join(r["feature_domains"])
