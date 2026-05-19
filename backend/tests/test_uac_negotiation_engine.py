"""UAC negotiation engine tests (rule path, no LLM)."""

from __future__ import annotations

import pytest

from app.services.uac_negotiation_engine import (
    UACNegotiationEngine,
    format_uac_negotiation_markdown,
)


@pytest.mark.asyncio
async def test_build_populates_audiences_from_gaps() -> None:
    gap = {
        "gaps": [
            {
                "type": "missing_acceptance_criteria",
                "impact": "high",
                "question_to_ask": "What are the AC?",
            },
            {
                "type": "missing_validation_points",
                "impact": "medium",
                "question_to_ask": "Where do we assert output?",
            },
        ]
    }
    risk = {"risk_level": "medium", "risk_areas": ["publishing_pipeline"]}
    out = await UACNegotiationEngine().build(
        jira_key="GUIDES-1",
        issue_type="Bug",
        labels=["regression", "pdf"],
        customer_context={"customer": "Acme", "customer_type": "enterprise", "escalation": False},
        risk_analysis=risk,
        gap_analysis=gap,
        context_excerpt="Publish to PDF output",
    )
    assert out["questions_for_product_manager"]
    assert out["questions_for_developers"] or out["questions_for_qa"]
    assert out["challenge_during_uac"]
    md = format_uac_negotiation_markdown(out)
    assert "Product Manager" in md or "Developers" in md
    assert "challenge" in md.lower() or "UAC" in md
