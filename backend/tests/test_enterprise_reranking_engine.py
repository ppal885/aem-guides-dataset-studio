"""Tests for EnterpriseRerankingEngine."""

from __future__ import annotations

import json

from app.services.enterprise_qa.enterprise_reranking_engine import (
    EnterpriseRerankingEngine,
    build_rerank_base_from_issue_chunks,
)


def _meta(**kwargs: object) -> dict:
    m: dict[str, object] = {}
    if "labels" in kwargs:
        m["labels"] = json.dumps(kwargs["labels"])
    if "components" in kwargs:
        m["components"] = json.dumps(kwargs["components"])
    for k in ("issue_type", "status", "customer", "customer_key", "title"):
        if k in kwargs:
            m[k] = kwargs[k]
    return m


def test_build_rerank_base_merges_chunks() -> None:
    rows = [
        {
            "chunk_type": "full_ticket_summary",
            "document": "NPE in /api/guides/v1/maps publish",
            "metadata": _meta(
                labels=["regression", "cisco"],
                components=["pdf"],
                issue_type="Bug",
                status="Open",
                customer="Cisco",
                customer_key="cisco",
            ),
        }
    ]
    base = build_rerank_base_from_issue_chunks(jira_key="GUIDES-1", rows=rows, extra_blob="user asks about publish")
    assert base["jira_key"] == "GUIDES-1"
    assert "regression" in base["labels"]
    assert "cisco" in base["labels"]
    assert "pdf" in base["components"]
    assert "/api/guides/v1/maps" in base["blob"]


def test_rerank_prefers_shared_customer_and_api() -> None:
    base = {
        "jira_key": "GUIDES-1",
        "labels": {"regression", "cisco"},
        "components": {"editor"},
        "issue_type": "bug",
        "status": "open",
        "customer": "cisco",
        "customer_key": "cisco",
        "blob": "Error at com.adobe.guides.Foo.publish\n/api/guides/v1/output",
        "chunk_types": {"regression_risks"},
        "updated_at": "",
    }
    low = {
        "jira_key": "GUIDES-9",
        "title": "Unrelated doc",
        "chunk_type": "full_ticket_summary",
        "score": 0.55,
        "document": "Cosmetic typo",
        "metadata": _meta(labels=["documentation"], components=["misc"], issue_type="task", status="closed"),
    }
    high = {
        "jira_key": "GUIDES-2",
        "title": "Publish failure",
        "chunk_type": "regression_risks",
        "score": 0.48,
        "document": "Same NPE at com.adobe.guides.Foo.publish calling /api/guides/v1/output",
        "metadata": _meta(
            labels=["regression", "cisco"],
            components=["editor"],
            issue_type="bug",
            status="open",
            customer="Cisco",
            customer_key="cisco",
        ),
    }
    eng = EnterpriseRerankingEngine()
    out = eng.rerank_hits(base=base, hits=[low, high])
    assert out[0]["jira_key"] == "GUIDES-2"
    assert out[0]["rerank"]["final_score"] >= out[1]["rerank"]["final_score"]
    assert "shared_api_paths" in out[0]["rerank"]["boost_reasons"]


def test_score_candidate_returns_shape() -> None:
    base = build_rerank_base_from_issue_chunks(
        jira_key="X-1",
        rows=[{"chunk_type": "x", "document": "a", "metadata": _meta(labels=["a"], components=["b"])}],
        extra_blob="",
    )
    cand = {"jira_key": "Y-1", "score": 0.4, "document": "b", "metadata": _meta(labels=["z"], issue_type="story")}
    r = EnterpriseRerankingEngine().score_candidate(base=base, candidate=cand, vector_score=0.4)
    assert "final_score" in r
    assert "boost_reasons" in r
    assert "penalty_reasons" in r
    assert 0.0 <= r["final_score"] <= 1.0
