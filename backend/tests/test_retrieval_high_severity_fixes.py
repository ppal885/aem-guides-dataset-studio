"""Regression tests for the high-severity Jira QA retrieval fixes."""

from __future__ import annotations

import json
from datetime import date

from app.models.jira_models import JiraIssueSearchResult
from app.rag.hybrid_search import HybridJiraSearch
from app.rag.metadata_filtering import (
    JiraMetadataCriteria,
    matches_metadata,
    metadata_has_escalation,
    metadata_score,
    within_time_window,
)
from app.services.retrieval_service import QaCopilotRetrievalService


def _hit(key: str, metadata: dict, *, score: float = 0.7, document: str = "Topic publishing fails.") -> dict:
    return {
        "jira_key": key,
        "title": metadata.get("title", key),
        "score": score,
        "document": document,
        "metadata": {"jira_key": key, **metadata},
    }


def _search(monkeypatch, hits: list[dict], criteria: JiraMetadataCriteria):
    monkeypatch.setattr("app.rag.semantic_search.semantic_search_jira_qa", lambda *a, **k: hits)
    return HybridJiraSearch().search(criteria, limit=5)


# --- pattern detection -----------------------------------------------------------------------


def test_guides_product_name_is_not_a_uuid_mismatch() -> None:
    svc = QaCopilotRetrievalService(search_engine=object())
    patterns = svc._detect_patterns_in_text("AEM Guides web editor: remove a topic from the map")
    assert "UUID mismatch" not in patterns
    # "remove" must not count as a move/rename.
    assert "stale references after rename or move" not in patterns


def test_pattern_detection_still_matches_whole_words_and_plurals() -> None:
    svc = QaCopilotRetrievalService(search_engine=object())
    patterns = svc._detect_patterns_in_text("GUID changed after the topic was moved; UUIDs differ in Native PDF")
    assert "UUID mismatch" in patterns
    assert "stale references after rename or move" in patterns
    assert "publishing regression" in patterns


def test_async_is_not_editor_synchronization() -> None:
    svc = QaCopilotRetrievalService(search_engine=object())
    assert "editor synchronization issues" not in svc._detect_patterns_in_text("async job queue stalls")


# --- customer fallback -----------------------------------------------------------------------


def test_customer_fallback_never_returns_another_customers_issue(monkeypatch) -> None:
    other = _hit("GUIDES-1", {"customer": "Cisco", "issue_type": "Bug"})
    result = _search(monkeypatch, [other], JiraMetadataCriteria(customer="Topcon", issue_type="Bug"))
    assert result.hits == []
    assert result.debug["fallback_reason"] == "metadata_filters_matched_zero_candidates"


def test_customer_fallback_keeps_issue_with_no_customer_recorded(monkeypatch) -> None:
    unknown = _hit("GUIDES-2", {"customer": "", "issue_type": "Bug"})
    other = _hit("GUIDES-3", {"customer_labels": json.dumps(["Cisco"]), "issue_type": "Bug"})
    result = _search(monkeypatch, [unknown, other], JiraMetadataCriteria(customer="Topcon", issue_type="Bug"))
    assert [h["jira_key"] for h in result.hits] == ["GUIDES-2"]
    assert result.semantic_fallback_used is True


def test_hard_filters_are_not_dropped_when_nothing_matches(monkeypatch) -> None:
    task = _hit("GUIDES-4", {"issue_type": "Task"})
    result = _search(monkeypatch, [task], JiraMetadataCriteria(issue_type="Bug"))
    assert result.hits == []


# --- escalation and time window --------------------------------------------------------------


def test_escalation_ignores_ticket_body_words() -> None:
    meta = {"labels": json.dumps(["publishing"]), "priority": "Major", "title": "PDF output slow"}
    assert not metadata_has_escalation(meta, "This is a critical blocker; please escalate.")


def test_escalation_uses_labels_title_and_priority() -> None:
    assert metadata_has_escalation({"labels": json.dumps(["customer-escalation"])})
    assert metadata_has_escalation({"title": "Escalation: PDF fails for customer"})
    assert metadata_has_escalation({"priority": "Blocker"})
    assert metadata_has_escalation({"priority": "Critical"})


def test_time_window_excludes_old_issues_and_keeps_undated_ones() -> None:
    today = date(2026, 11, 9)
    assert within_time_window(90, {"jira_updated_at": "2026-10-01T10:00:00.000+0000"}, today=today)
    assert not within_time_window(90, {"jira_updated_at": "2025-01-01T10:00:00.000+0000"}, today=today)
    assert within_time_window(90, {}, today=today)
    assert within_time_window(None, {"jira_updated_at": "2001-01-01"}, today=today)


def test_matches_metadata_applies_time_window() -> None:
    criteria = JiraMetadataCriteria(time_window_days=30)
    assert not matches_metadata(criteria, {"updated_at": "2001-01-01T00:00:00"})


def test_editor_type_is_a_rerank_signal() -> None:
    _, reasons = metadata_score(JiraMetadataCriteria(editor_type="web editor"), {"labels": json.dumps(["web-editor"])})
    assert "editor_type_match" in reasons


# --- live snapshot precedence ----------------------------------------------------------------


def test_live_jira_snapshot_metadata_wins_over_indexed_chunks() -> None:
    issue = JiraIssueSearchResult(issue_key="GUIDES-9", summary="s", similarity_score=0.5, metadata={})
    chunks = [
        {"chunk_type": "live_jira_snapshot", "document": "live", "metadata": {"status": "Closed", "issue_type": "Bug"}},
        {"chunk_type": "description", "document": "indexed", "metadata": {"status": "Open", "issue_type": "Story"}},
    ]
    details = QaCopilotRetrievalService(search_engine=object())._chunks_to_details(issue, chunks)
    assert details.metadata["status"] == "Closed"
    assert details.metadata["issue_type"] == "Bug"
    # Document order is unchanged: the live snapshot still leads the evidence.
    assert details.evidence_chunks[0]["chunk_type"] == "live_jira_snapshot"
