"""Unit tests for Jira QA Customer Intelligence Engine."""

from __future__ import annotations

import json
import pytest

from app.services.customer_intelligence_engine import (
    CustomerIntelligenceEngine,
    customer_index_metadata_for_chunks,
    customer_metadata_from_issue_chunks,
    detect_customer_labels_from_issue,
    enhance_labels_for_customer_boost,
    extract_customer_metadata_from_issue,
    resolve_effective_customer_for_copilot,
)


def test_detect_customer_labels_from_issue_order_and_dedupe() -> None:
    labels = ["cisco", "Cisco", "pdf", "customer-escalation"]
    out = detect_customer_labels_from_issue(labels)
    assert out == ["Cisco"]


def test_extract_customer_metadata_merges_custom_field_and_labels() -> None:
    fields = {
        "summary": "PDF fails",
        "labels": ["cisco", "customer-escalation"],
        "issuetype": {"name": "Bug"},
        "priority": {"name": "Major"},
        "description": {"type": "doc", "version": 1, "content": []},
    }
    meta = extract_customer_metadata_from_issue(fields)
    assert meta["customer"] == "Cisco"
    assert meta["customer_key"] == "cisco"
    assert meta["customer_escalation"] is True
    assert meta["customer_type"] == "enterprise"


def test_customer_index_metadata_for_chroma() -> None:
    fields = {
        "summary": "x",
        "labels": ["internal"],
        "issuetype": {"name": "Task"},
        "priority": {"name": "Low"},
        "description": {"type": "doc", "version": 1, "content": []},
    }
    flat = customer_index_metadata_for_chunks(fields)
    assert flat["customer"] == "Internal"
    assert flat["customer_key"] == "internal"
    assert flat["customer_type"] == "internal"
    assert flat["customer_escalation"] == 0
    assert "Internal" in flat["customer_labels"]


def test_resolve_effective_customer_for_copilot() -> None:
    chunks = [
        {
            "metadata": {
                "customer": "ABS",
                "customer_key": "abs",
            }
        }
    ]
    assert resolve_effective_customer_for_copilot("Cisco", chunks) == "Cisco"
    assert resolve_effective_customer_for_copilot(None, chunks) == "ABS"
    assert resolve_effective_customer_for_copilot("", [{"metadata": {"customer_key": "topcon"}}]) == "Topcon"


def test_enhance_labels_for_customer_boost() -> None:
    base = ["pdf-output"]
    out = enhance_labels_for_customer_boost(base, "Cisco")
    lowered = {x.lower() for x in out}
    assert "cisco" in lowered


def test_customer_metadata_from_issue_chunks() -> None:
    md = customer_metadata_from_issue_chunks(
        [
            {"metadata": {"other": "x"}},
            {"metadata": {"customer": "Swift", "customer_type": "enterprise", "customer_escalation": 1}},
        ]
    )
    assert md["customer"] == "Swift"
    assert md["customer_type"] == "enterprise"
    assert md["escalation"] is True


def test_intelligence_engine_aggregate(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "document": "Regression in PDF for customer",
            "metadata": {
                "jira_key": "GUIDES-1",
                "chunk_type": "regression_risks",
                "title": "PDF publish regression",
                "components": json.dumps(["pdf", "pdf"]),
                "updated_at": "2025-01-02",
            },
        },
        {
            "document": "Second regression chunk",
            "metadata": {
                "jira_key": "GUIDES-1",
                "chunk_type": "regression_risks",
                "title": "PDF publish regression",
                "components": json.dumps(["pdf"]),
                "updated_at": "2025-01-02",
            },
        },
        {
            "document": "Summary",
            "metadata": {
                "jira_key": "GUIDES-2",
                "chunk_type": "full_ticket_summary",
                "title": "Editor lock issue",
                "components": json.dumps(["editor"]),
                "updated_at": "2025-01-03",
            },
        },
    ]

    def fake_where(coll: str, where: dict, limit: int = 0) -> list:
        assert where.get("customer_key") == "cisco"
        return rows

    monkeypatch.setattr(
        "app.services.customer_intelligence_engine.get_documents_where",
        fake_where,
    )
    eng = CustomerIntelligenceEngine()
    rep = eng.build_intelligence_report("Cisco")
    assert rep["customer"] == "Cisco"
    assert any("GUIDES-1" in x for x in rep["repeated_issues"])
    assert rep["recent_related_tickets"]
    assert any("pdf" in x.lower() for x in rep["frequently_affected_components"])
