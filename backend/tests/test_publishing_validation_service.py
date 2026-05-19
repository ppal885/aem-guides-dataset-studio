"""Tests for publishing_validation_service (deterministic publishing UAC helpers)."""

from __future__ import annotations

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from services.publishing_validation_service import build_publishing_validation_payload


def _empty() -> dict[str, list[str]]:
    return {
        "required_artifacts": [],
        "validation_points": [],
        "cross_output_parity": [],
        "high_risk_checks": [],
    }


def test_out_of_scope_returns_empty():
    doc = JiraEnrichedDocument(
        jira_key="GUIDES-1",
        domain="unknown",
        summary="generic internal discussion",
    )
    assert build_publishing_validation_payload(doc) == _empty()


def test_publishing_scope_native_pdf_populates():
    doc = JiraEnrichedDocument(
        jira_key="GUIDES-77",
        domain="native_pdf",
        dita_entities=["bookmap", "topicref"],
        affected_outputs=["native_pdf"],
        summary="TOC wrong in PDF output",
    )
    out = build_publishing_validation_payload(doc)
    assert out["required_artifacts"]
    assert any("Native PDF job log" in a for a in out["required_artifacts"])
    assert any("TOC" in v or "chapter" in v.lower() for v in out["validation_points"])


def test_dita_ot_mention_adds_ot_artifacts():
    doc = JiraEnrichedDocument(
        jira_key="GUIDES-88",
        domain="editor",
        dita_entities=["task"],
        affected_outputs=["native_pdf"],
        summary="Regression after DITA-OT plug-in upgrade for PDF transtype",
    )
    out = build_publishing_validation_payload(doc)
    assert any("DITA-OT" in a for a in out["required_artifacts"])


def test_response_shape_keys():
    doc = JiraEnrichedDocument(
        jira_key="GUIDES-99",
        domain="keyref",
        dita_entities=["keyref"],
        affected_outputs=["native_pdf", "sites"],
        summary="Key resolves in preview but PDF breaks",
    )
    out = build_publishing_validation_payload(doc)
    assert set(out.keys()) == {"required_artifacts", "validation_points", "cross_output_parity", "high_risk_checks"}
    assert isinstance(out["validation_points"], list)
