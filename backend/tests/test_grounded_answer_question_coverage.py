from app.api.routes.remote_mcp import _relevant_mcp_citations
from app.services.chat_service import _question_shape_hint


def test_multi_part_searchtitle_request_requires_every_qa_oracle():
    question = (
        "Provide source DITA, publishing steps, expected HTML/JCR output, negative cases, mapping scope, "
        "evidence source, and explicitly list every behavior that is not yet verified for searchtitle."
    )

    hint = _question_shape_hint(question)

    assert "multi-part QA-oracle request" in hint
    assert "Source DITA" in hint
    assert "Publishing steps" in hint
    assert "Expected HTML/JCR output" in hint
    assert "Negative cases" in hint
    assert "Mapping scope" in hint
    assert "Evidence sources" in hint
    assert "Unverified behaviors" in hint
    assert "never silently omit" in hint
    assert "verified AEM Guides mapping" in hint


def test_baseline_request_rejects_adjacent_sources_as_product_proof():
    hint = _question_shape_hint(
        "How should baseline publishing resolve map versions, working copies, keyrefs, conrefs, and metadata?"
    )

    assert "baseline's captured map/topic versions" in hint
    assert "legacy versus New Baseline" in hint
    assert "do not use release-note or DITA-spec adjacency" in hint


def test_remote_mcp_citations_prefer_exact_construct_sources():
    citations = [
        {"title": "Fixed issues 5.2.0", "uri": "https://example.test/fixed-issues"},
        {"title": "AEM Guides searchtitle legacy mapping", "uri": "https://example.test/searchtitle-mapping"},
        {"title": "General AEM publishing", "uri": "https://example.test/publishing"},
    ]

    ranked = _relevant_mcp_citations(
        "How is searchtitle mapped in published AEM Sites output?",
        citations,
    )

    assert [item["title"] for item in ranked] == ["AEM Guides searchtitle legacy mapping"]
