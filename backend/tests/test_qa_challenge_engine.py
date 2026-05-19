"""QAChallengeEngine — weak-ticket detection for challenge mode."""

from __future__ import annotations

import pytest

from app.services.qa_challenge_engine import QAChallengeEngine, format_qa_challenge_markdown


@pytest.mark.asyncio
async def test_build_returns_four_buckets():
    out = await QAChallengeEngine().build(
        context_blob=(
            "Bug in web editor save. Steps unclear. "
            "Customer uses SVG maps. Upgrade from 4.2 to 4.4 planned."
        ),
        gap_analysis={"gaps": []},
        reasoning={"missing_information": ["Exact AEM patch level"], "assumptions": ["Single author"]},
        labels=["regression"],
        jira_key="GUIDES-1",
    )
    assert set(out) == {
        "challenge_points",
        "hidden_risks",
        "potential_misunderstandings",
        "questions_qa_should_push_back_on",
    }
    assert any("vector" in x.lower() or "svg" in x.lower() for x in out["challenge_points"])
    assert any("compat" in x.lower() or "backward" in x.lower() for x in out["challenge_points"])
    md = format_qa_challenge_markdown(out)
    assert "QA Challenge Mode" in md
