"""Tests for UAC evidence gating."""

from __future__ import annotations

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_retrieval_service import RetrievedJira
from app.services.uac_evidence_gate import apply_uac_evidence_gate, is_generic_statement


def test_is_generic_statement_phrases():
    assert is_generic_statement("We should verify UI for the fix.")
    assert is_generic_statement("Test regression before handoff.")
    assert is_generic_statement("Validate functionality for the change.")
    assert is_generic_statement("Validate end to end before release")
    assert is_generic_statement("Perform smoke testing on the build")
    assert not is_generic_statement("Confirm glossStatus renders in Native PDF for GUIDES-99")


def test_gate_keeps_grounded_drops_generic():
    en = JiraEnrichedDocument(
        jira_key="GUIDES-99",
        summary="Glossary glossStatus in Native PDF",
        description="glossStatus attribute missing in published PDF for customer Cisco.",
        dita_entities=["glossstatus", "bookmap"],
        affected_outputs=["native_pdf"],
        components=["Publishing"],
        customer_names=["Cisco"],
        qa_risk_tags=["pdf-output"],
    )
    sim = [
        RetrievedJira(
            jira_key="GUIDES-88",
            title="PDF glossary regression",
            document="Native PDF drops glossentry for some maps.",
            why_similar="same native_pdf output",
            metadata={"enrich_outputs": '["native_pdf"]'},
        )
    ]
    draft = """- Validate glossStatus in Native PDF output for GUIDES-99 bookmap (Cisco).
- Verify UI across all screens.
- Confirm GUIDES-88 regression pattern does not recur for publishing component.
- Validate glossStatus in Native PDF output for GUIDES-99 bookmap (Cisco).
- GUIDES-99: perform smoke testing before handoff."""
    out = apply_uac_evidence_gate(en, sim, draft)
    assert "glossstatus" in out.cleaned_answer.lower()
    assert "GUIDES-88" in out.cleaned_answer
    reasons = {d.reason for d in out.dropped_points}
    assert any("duplicate" in r for r in reasons)
    assert "verify ui" not in out.cleaned_answer.lower()
    assert len(out.dropped_points) >= 2


def test_gate_drops_ungrounded():
    en = JiraEnrichedDocument(
        jira_key="GUIDES-1",
        summary="Small fix",
        description="Nothing specific",
    )
    out = apply_uac_evidence_gate(
        en,
        [],
        "- Do something vague without ticket context.\n- GUIDES-1: confirm the small fix matches the summary intent.",
    )
    assert "GUIDES-1" in out.cleaned_answer
    assert len(out.dropped_points) >= 1
