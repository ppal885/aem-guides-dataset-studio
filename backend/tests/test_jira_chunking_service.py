"""Tests for smart Jira chunking (``jira_chunking_service``)."""

from __future__ import annotations

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_chunking_service import (
    SMART_JIRA_CHUNK_TYPES,
    build_comments_digest,
    create_jira_chunks,
)


def test_create_jira_chunks_has_required_keys():
    doc = JiraEnrichedDocument(
        jira_key="EPV-123",
        summary="Glossary publish",
        description="Expected: gloss works.\nActual: glossStatus wrong.\nSteps to reproduce: 1. open bookmap",
        issue_type="Bug",
        status="Open",
        priority="Major",
        labels=["l10n"],
        components=["Publishing"],
        customer_names=["Cisco"],
        domain="native_pdf",
        sub_domain="glossary",
        dita_entities=["glossentry", "glossStatus", "bookmap"],
        affected_outputs=["Native PDF"],
        expected_behavior="PDF matches editor",
        actual_behavior="glossentry dropped",
        qa_risk_tags=["regression"],
        automation_fit="Partial (5.0)",
        comments_digest="[2024-01-02] dev: verified repro on 4.3",
    )
    chunks = create_jira_chunks(doc)
    types = {c["chunk_type"] for c in chunks}
    assert types >= {
        "summary_chunk",
        "problem_chunk",
        "expected_actual_chunk",
        "comment_chunk",
        "reproduction_chunk",
        "qa_signal_chunk",
        "customer_signal_chunk",
        "domain_entity_chunk",
    }
    for c in chunks:
        assert set(c.keys()) >= {
            "jira_key",
            "chunk_type",
            "chunk_text",
            "domain",
            "customer_names",
            "affected_outputs",
            "dita_entities",
        }
        assert c["jira_key"] == "EPV-123"
        assert c["domain"] == "native_pdf"
    dom = next(x for x in chunks if x["chunk_type"] == "domain_entity_chunk")
    assert "EPV-123" in dom["chunk_text"]
    assert "native_pdf" in dom["chunk_text"].lower() or "glossary" in dom["chunk_text"].lower()
    assert "glossentry" in dom["chunk_text"]


def test_smart_chunk_types_disjoint_from_legacy_names():
    assert "summary_chunk" in SMART_JIRA_CHUNK_TYPES
    assert "full_ticket_summary" not in SMART_JIRA_CHUNK_TYPES


def test_build_comments_digest_filters_short():
    comments = [
        {"author": "a", "created": "t", "body_text": "ok"},
        {"author": "b", "created": "t2", "body_text": "x" * 50 + " regression confirmed in publish"},
    ]
    d = build_comments_digest(comments)
    assert "regression" in d.lower()
    assert "ok" not in d
