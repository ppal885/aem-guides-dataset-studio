"""UAC critic service (rule-based path)."""

from __future__ import annotations

from unittest.mock import patch

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_retrieval_service import RetrievedJira
from app.services.uac_critic_service import critic_refine_uac_answer


@patch("app.services.uac_critic_service.is_llm_available", return_value=False)
def test_critic_caps_and_strips_generic(_mock_llm):
    en = JiraEnrichedDocument(
        jira_key="GUIDES-10",
        summary="PDF glossary issue",
        description="glossStatus wrong in native PDF for bookmap.",
        dita_entities=["glossstatus", "bookmap"],
        affected_outputs=["native_pdf"],
        components=["Publishing"],
        customer_names=["Cisco"],
    )
    sim = [
        RetrievedJira(
            jira_key="GUIDES-2",
            title="PDF regression",
            document="Similar native PDF glossary defect.",
            why_similar="shared native_pdf output",
            metadata={},
        )
    ]
    draft = """### 1. Jira Classification
- **Domain:** publishing

### 2. Why This Jira Is Risky
- glossStatus in Native PDF for GUIDES-10 (current: description).
- Verify UI everywhere with no ticket link.
- glossStatus in Native PDF for GUIDES-10 (current: description).

### 3. Similar Historical Tickets
Intro line.

**GUIDES-2**
- **Similarity reason:** native PDF
- **What we learned from it:** check output

**GUIDES-9**
- **Similarity reason:** other
- **What we learned from it:** n/a

### 4. Must-Test Scenarios
Scenario: glossStatus in PDF for bookmap
Why: Matches GUIDES-10 description
Evidence: current Jira description
Test Layer: Publishing

Scenario: glossStatus in PDF for bookmap
Why: dup
Evidence: current Jira description
Test Layer: Publishing

### 5. Missing Clarifications for UAC
- Does GUIDES-10 repro on Native PDF for Cisco bookmap?
- Verify UI only?

### 6. Automation Fit
- **Fit:** Partial
"""
    out = critic_refine_uac_answer(en, sim, draft)
    assert "Verify UI" not in out
    assert "GUIDES-10" in out
    assert out.count("Scenario:") <= 7
    # duplicate risk bullet removed or merged
    assert out.lower().count("glossstatus in native pdf for guidelines-10") <= 1 or "- glossStatus" in out


@patch("app.services.uac_critic_service.is_llm_available", return_value=False)
def test_critic_unstructured_falls_back_to_gate(_mock_llm):
    en = JiraEnrichedDocument(
        jira_key="X-1",
        summary="PDF glossary issue",
        description="glossStatus wrong in native PDF for bookmap.",
        dita_entities=["glossstatus"],
        affected_outputs=["native_pdf"],
    )
    from textwrap import dedent

    blob = dedent(
        """\
        - glossstatus in Native PDF for X-1 bookmap per description
        - verify UI with no anchors
        """
    )
    out = critic_refine_uac_answer(en, [], blob)
    assert "glossstatus" in out.lower()
    assert "verify ui" not in out.lower()
