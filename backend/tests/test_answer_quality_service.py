"""Tests for anti-generic answer specificity scoring."""

from __future__ import annotations

from services.answer_quality_service import (
    generic_phrases_removed_between,
    score_answer_specificity,
)


def _current() -> dict:
    return {
        "jira_key": "GUIDES-100",
        "summary": "Native PDF fails when conkeyref resolves in bookmap",
        "description": "Publishing pipeline regresses for customer ACME on bookmap output.",
        "domain": "publishing",
        "sub_domain": "pdf",
        "labels": ["pdf", "native-publishing"],
        "components": ["Publisher"],
        "customer_names": ["ACME"],
        "affected_outputs": ["Native PDF", "HTML5"],
        "dita_entities": ["conkeyref", "bookmap"],
        "missing_info": ["AEM version not stated"],
    }


def test_specific_answer_scores_high():
    ans = """### 1. Jira Classification
- **Domain:** publishing / pdf
### 2. Why This Jira Is Risky
- Native PDF breaks for conkeyref in bookmap (current: summary)
- Prior art GUIDES-99 had same pipeline (similar: GUIDES-99 — publishing)
### 3. Similar Historical Tickets
**GUIDES-99**
- **Similarity reason:** same native pdf
- **What we learned from it:** validate bookmap
### 4. Must-Test Scenarios
```
Scenario: PDF with conkeyref
Why: bookmap and Native PDF per evidence
Evidence: GUIDES-100 summary
Test Layer: Publishing
```
### 5. Missing Clarifications for UAC
- What AEM version reproduces Native PDF failure (missing_info_flags)?
### 6. Automation Fit
- **Fit:** Partial
- **Best Layer:** Publishing
- **Reason:** DITA OT path
- **Suggested test name:** test_native_pdf_acme_bookmap
"""
    similar = [
        {
            "jira_key": "GUIDES-99",
            "title": "pdf regression bookmap",
            "document_excerpt": "native pdf publishing pipeline",
        }
    ]
    out = score_answer_specificity(ans, _current(), similar)
    assert out["score"] >= 70
    assert out["recommendation"] == "accept"
    assert isinstance(out["generic_phrases_found"], list)
    assert isinstance(out["missing_specificity"], list)


def test_generic_answer_low_score_and_rewrite_or_reject():
    ans = """We should test everything and validate thoroughly with general regression.
It depends on the team. Follow best practices and ensure quality.
### 2. Why
- Something risky without citations
"""
    similar = [{"jira_key": "GUIDES-99", "title": "other", "document_excerpt": "snippet about dita ot"}]
    out = score_answer_specificity(ans, _current(), similar)
    assert out["score"] < 70
    assert out["recommendation"] in ("rewrite", "reject")
    assert out["generic_phrases_found"]
    assert any("Jira" in m or "generic" in m.lower() for m in out["missing_specificity"])


def test_generic_phrases_removed_between():
    before = "We should test everything and validate thoroughly."
    after = "Verify Native PDF output per GUIDES-100."
    removed = generic_phrases_removed_between(before, after)
    assert r"\btest everything\b" in removed
    assert r"\bvalidate thoroughly\b" in removed


def test_empty_similar_skips_similar_penalty():
    ans = """### 1. Jira Classification
Mentions GUIDES-100, publishing, Native PDF, conkeyref, bookmap, ACME, Publisher.
### 4. Must-Test
```
Scenario: x
Why: Native PDF + conkeyref for ACME
Evidence: current
Test Layer: API
```
### 5. Missing
- AEM version?
"""
    out = score_answer_specificity(ans, _current(), [])
    assert out["score"] >= 70
