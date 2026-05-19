"""TestDataIntelligenceEngine — required QA corpora and setup from Jira context."""

from __future__ import annotations

import pytest

from app.services.test_data_intelligence_engine import (
    TestDataIntelligenceEngine,
    format_test_data_intelligence_markdown,
)


@pytest.mark.asyncio
async def test_build_infers_publish_and_maps():
    out = await TestDataIntelligenceEngine().build(
        context_blob="PDF publish fails for customer map on AEM 6.5 with Guides 4.2. Keyref to glossary.",
        labels=["publishing"],
        components=["Publishing"],
        issue_type="Bug",
        jira_key="GUIDES-1",
    )
    for k in (
        "required_topics",
        "required_maps",
        "required_assets",
        "required_metadata",
        "required_conditions",
        "required_baselines",
        "required_versions",
        "required_large_data",
        "required_permissions",
    ):
        assert k in out
        assert isinstance(out[k], list)
    joined = " ".join(out["required_maps"] + out["required_topics"]).lower()
    assert "map" in joined or "ditamap" in joined
    assert any("publish" in x.lower() for x in out["required_conditions"] + out["required_metadata"])
    md = format_test_data_intelligence_markdown(out)
    assert "Test data intelligence" in md
