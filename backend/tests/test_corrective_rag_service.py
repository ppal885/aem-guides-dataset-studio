import pytest

from app.services import corrective_rag_service, tavily_search_service
from app.services.corrective_rag_service import CorrectiveRagResult, RetrievalCandidate


@pytest.mark.anyio
async def test_chat_corrective_rag_rewrites_weak_queries(monkeypatch):
    def fake_retrieve_mode_candidates(query: str, *, tenant_id: str, mode: str, category: str = ""):
        if "dita" in query.lower():
            return [
                RetrievalCandidate(
                    source="dita_spec",
                    label="DITA Spec",
                    text="DITA guidance for hover behavior and authoring structure.",
                )
            ]
        return []

    monkeypatch.setattr(corrective_rag_service, "_retrieve_mode_candidates", fake_retrieve_mode_candidates)
    monkeypatch.setattr(corrective_rag_service, "_persist_trace", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(corrective_rag_service, "record_query_result", lambda *_args, **_kwargs: None)

    async def fake_llm_query(*_args, **_kwargs):
        return ""

    monkeypatch.setattr(corrective_rag_service, "_llm_refined_query", fake_llm_query)

    result = await corrective_rag_service.run_chat_corrective_rag("hover issue", tenant_id="kone")

    assert isinstance(result, CorrectiveRagResult)
    assert result.correction_applied is True
    assert "DITA" in result.corrected_query
    assert result.retrieval_summary["correction_applied"] is True


@pytest.mark.anyio
async def test_chat_corrective_rag_expands_author_view_reference_queries(monkeypatch):
    seen_queries: list[str] = []

    def fake_retrieve_mode_candidates(query: str, *, tenant_id: str, mode: str, category: str = ""):
        seen_queries.append(query)
        if "topicref href conref conkeyref keyref" in query.lower():
            return [
                RetrievalCandidate(
                    source="aem_guides",
                    label="Experience League",
                    text="In AEM Guides, topicref href and content references are resolved through the map context.",
                    url="https://experienceleague.adobe.com/example",
                )
            ]
        return []

    monkeypatch.setattr(corrective_rag_service, "_retrieve_mode_candidates", fake_retrieve_mode_candidates)
    monkeypatch.setattr(corrective_rag_service, "_persist_trace", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(corrective_rag_service, "record_query_result", lambda *_args, **_kwargs: None)

    async def fake_llm_query(*_args, **_kwargs):
        return ""

    monkeypatch.setattr(corrective_rag_service, "_llm_refined_query", fake_llm_query)

    result = await corrective_rag_service.run_chat_corrective_rag(
        "Do we require href in Hasinstance, how should it get resolved in Author view of AEM Guides",
        tenant_id="kone",
    )

    assert isinstance(result, CorrectiveRagResult)
    assert result.correction_applied is True
    assert any("topicref href conref conkeyref keyref" in query.lower() for query in seen_queries)
    assert result.assessment.strength != "weak"


@pytest.mark.anyio
async def test_chat_corrective_rag_uses_live_experience_league_only_for_adobe_queries(monkeypatch):
    monkeypatch.setattr(tavily_search_service, "is_chat_tavily_enabled", lambda: True)
    monkeypatch.setattr(corrective_rag_service, "_persist_trace", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(corrective_rag_service, "record_query_result", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(corrective_rag_service, "_retrieve_mode_candidates", lambda *_args, **_kwargs: [])

    async def fake_live_candidates(query: str):
        return [
            RetrievalCandidate(
                source="aem_guides",
                label="Experience League",
                text=f"Live Adobe result for {query}",
                url="https://experienceleague.adobe.com/example",
            )
        ]

    monkeypatch.setattr(corrective_rag_service, "_retrieve_experience_league_candidates", fake_live_candidates)

    async def fake_llm_query(*_args, **_kwargs):
        return ""

    monkeypatch.setattr(corrective_rag_service, "_llm_refined_query", fake_llm_query)

    adobe = await corrective_rag_service.run_chat_corrective_rag(
        "How does Author view resolve keyref in AEM Guides?",
        tenant_id="kone",
    )
    assert any(candidate.url == "https://experienceleague.adobe.com/example" for candidate in adobe.candidates)

    general = await corrective_rag_service.run_chat_corrective_rag(
        "Explain probability theory basics",
        tenant_id="kone",
    )
    assert not any(candidate.url == "https://experienceleague.adobe.com/example" for candidate in general.candidates)


@pytest.mark.anyio
async def test_chat_corrective_rag_live_fallback_for_dita_structure_questions(monkeypatch):
    """Weak local RAG still augments from Experience League for DITA/AEM structure questions."""
    monkeypatch.setattr(tavily_search_service, "is_chat_tavily_enabled", lambda: True)
    monkeypatch.setattr(corrective_rag_service, "_persist_trace", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(corrective_rag_service, "record_query_result", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(corrective_rag_service, "_retrieve_mode_candidates", lambda *_args, **_kwargs: [])

    async def fake_live_candidates(query: str):
        return [
            RetrievalCandidate(
                source="aem_guides",
                label="Experience League",
                text=f"Live Adobe result for {query}",
                url="https://experienceleague.adobe.com/example",
            )
        ]

    monkeypatch.setattr(corrective_rag_service, "_retrieve_experience_league_candidates", fake_live_candidates)

    async def fake_llm_query(*_args, **_kwargs):
        return ""

    monkeypatch.setattr(corrective_rag_service, "_llm_refined_query", fake_llm_query)

    result = await corrective_rag_service.run_chat_corrective_rag(
        "What is a properties table in a DITA reference topic?",
        tenant_id="kone",
    )
    assert any(candidate.url == "https://experienceleague.adobe.com/example" for candidate in result.candidates)


@pytest.mark.anyio
async def test_chat_corrective_rag_skips_experience_league_when_chat_tavily_disabled(monkeypatch):
    """CHAT_TAVILY_ENABLED=false disables Experience League Tavily, not only general web fallback."""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    monkeypatch.setenv("CHAT_TAVILY_ENABLED", "false")

    monkeypatch.setattr(corrective_rag_service, "_persist_trace", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(corrective_rag_service, "record_query_result", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(corrective_rag_service, "_retrieve_mode_candidates", lambda *_args, **_kwargs: [])

    called: list[str] = []

    async def fake_live_candidates(query: str):
        called.append(query)
        return [
            RetrievalCandidate(
                source="aem_guides",
                label="Experience League",
                text="should not run",
                url="https://experienceleague.adobe.com/example",
            )
        ]

    monkeypatch.setattr(corrective_rag_service, "_retrieve_experience_league_candidates", fake_live_candidates)

    async def fake_llm_query(*_args, **_kwargs):
        return ""

    monkeypatch.setattr(corrective_rag_service, "_llm_refined_query", fake_llm_query)

    await corrective_rag_service.run_chat_corrective_rag(
        "How does Author view resolve keyref in AEM Guides?",
        tenant_id="kone",
    )
    assert called == []


def test_query_alias_config_expands_author_view_and_hasinstance_terms():
    variants = corrective_rag_service._deterministic_query_variants(
        "Do we require href in Hasinstance and how does it resolve in Author view of AEM Guides?",
        mode="chat",
    )

    lowered = [variant.lower() for variant in variants]
    assert any("map editor author view" in variant for variant in lowered)
    assert any("subject scheme hasinstance" in variant for variant in lowered)


def test_query_decomposition_splits_compound_questions():
    clauses = corrective_rag_service._decompose_query_clauses(
        "Do we require href in Hasinstance, and how should it get resolved in Author view of AEM Guides?"
    )

    assert len(clauses) == 2
    assert clauses[0].lower().startswith("do we require href")
    assert clauses[1].lower().startswith("how should it get resolved")


@pytest.mark.anyio
async def test_research_corrective_rag_only_uses_web_when_allowed(monkeypatch):
    monkeypatch.setattr(corrective_rag_service, "_retrieve_mode_candidates", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(corrective_rag_service, "_persist_trace", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(corrective_rag_service, "record_query_result", lambda *_args, **_kwargs: None)

    async def fake_tavily(*_args, **_kwargs):
        return [
            RetrievalCandidate(
                source="tavily",
                label="Web Result",
                text="AEM Guides workaround from web search.",
                url="https://example.com/workaround",
            )
        ]

    async def fake_llm_query(*_args, **_kwargs):
        return ""

    monkeypatch.setattr(corrective_rag_service, "_retrieve_tavily_candidates", fake_tavily)
    monkeypatch.setattr(corrective_rag_service, "_llm_refined_query", fake_llm_query)

    rag_only = await corrective_rag_service.run_research_corrective_rag(
        "hover issue",
        tenant_id="kone",
        category="aem_guides",
        requested_source="rag",
    )
    assert not any(candidate.source == "tavily" for candidate in rag_only.candidates)

    with_web = await corrective_rag_service.run_research_corrective_rag(
        "hover issue",
        tenant_id="kone",
        category="aem_guides",
        requested_source="tavily",
    )
    assert any(candidate.source == "tavily" for candidate in with_web.candidates)
