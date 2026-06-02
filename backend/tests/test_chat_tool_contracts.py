import re
from pathlib import Path

import pytest

from app.services import doc_retriever_service, tavily_search_service
from app.services.chat_tools import (
    _extract_dita_attributes_from_query,
    _normalize_tool_result,
    execute_lookup_aem_guides,
    execute_lookup_dita_attribute,
    execute_lookup_dita_spec,
    execute_review_dita_xml,
    get_tool_definitions,
)
from app.services.dita_attribute_catalog import get_attribute_spec, list_attribute_names


def test_normalize_tool_result_adds_common_fields_for_catalog_tools():
    for tool in get_tool_definitions():
        name = str(tool.get("name") or "").strip()
        normalized = _normalize_tool_result(name, {})
        assert "kind" in normalized
        assert "status" in normalized
        assert "status_tone" in normalized
        assert "summary" in normalized
        assert "warnings" in normalized
        assert "sources" in normalized
        assert isinstance(normalized["warnings"], list)
        assert isinstance(normalized["sources"], list)


def test_normalize_tool_result_builds_search_summary_and_sources():
    normalized = _normalize_tool_result(
        "search_jira_issues",
        {
            "query": "door operator",
            "issues": [
                {
                    "issue_key": "KONE-123",
                    "summary": "Door operator terminology needs cleanup",
                    "url": "https://jira.example.invalid/browse/KONE-123",
                }
            ],
        },
    )

    assert normalized["kind"] == "search"
    assert normalized["status_tone"] == "success"
    assert "Found 1 Jira issue match" in str(normalized["summary"])
    assert normalized["sources"]
    assert normalized["sources"][0]["label"] == "KONE-123"


@pytest.mark.anyio
async def test_lookup_aem_guides_allows_dita_ot_docs_for_parameter_queries(monkeypatch):
    captured: dict[str, tuple[str, ...]] = {}

    def fake_retrieve(_query: str, *, k: int, allowed_host_suffixes):
        captured["hosts"] = tuple(allowed_host_suffixes)
        return {
            "results": [
                {
                    "url": "https://www.dita-ot.org/dev/parameters/parameters-base",
                    "title": "DITA-OT base parameters: args.draft",
                    "snippet": "Use --args.draft=yes to include draft comments.",
                }
            ],
            "retrieval_mode": "lexical",
            "warnings": [],
        }

    monkeypatch.setattr(doc_retriever_service, "retrieve_relevant_docs_with_diagnostics", fake_retrieve)
    monkeypatch.setattr(tavily_search_service, "is_chat_tavily_enabled", lambda: False)

    result = await execute_lookup_aem_guides("DITA-OT args.draft draft-comment PDF")

    assert "dita-ot.org" in captured["hosts"]
    assert result["results"][0]["url"] == "https://www.dita-ot.org/dev/parameters/parameters-base"


@pytest.mark.anyio
async def test_review_dita_xml_returns_human_readable_review_contract(monkeypatch):
    async def fake_build_review_snapshot(**_kwargs):
        return {
            "dita_type": "map",
            "quality_score": 33,
            "quality_breakdown": {"structure": 60, "content_richness": 18, "dita_features": 20, "aem_readiness": 33},
            "validation": [
                {"label": "XML declaration present", "passing": True},
                {"label": "Required DTD header present", "passing": False},
                {"label": "map structure present", "passing": False},
            ],
            "suggestions_report": {
                "total": 2,
                "errors": 1,
                "warnings": 0,
                "suggestions": [
                    {
                        "title": "Missing AEM Guides DTD header",
                        "severity": "error",
                        "why": "The output should start with the exact AEM Guides DTD for the topic type.",
                        "after": "Add the exact map DTD header immediately after the XML declaration.",
                        "rule_id": "validation_dtd_header",
                        "impact": "High: validation and import become safer.",
                    },
                    {
                        "title": "Map is missing references or branches",
                        "severity": "error",
                        "why": "A DITA map should organize deliverable content with map constructs.",
                        "after": "Add at least one <topicref href=\"example.dita\"/>.",
                        "rule_id": "validation_map_structure",
                    },
                ],
            },
            "sources_used": [{"label": "Live XML review", "count": 1}],
        }

    monkeypatch.setattr("app.services.smart_suggestions_service.build_review_snapshot", fake_build_review_snapshot)

    result = await execute_review_dita_xml("<map/>")

    assert result["summary"].startswith("Reviewed this DITA map and scored it 33/100")
    assert result["normalized_validation_issues"][0]["message"] == "Required DTD header is missing."
    assert result["normalized_validation_issues"][0]["recommendation"]
    assert result["priority_fixes"][0]["title"] == "Missing AEM Guides DTD header"
    assert result["score_improvement_guidance"].startswith("Fastest score lift")
    assert result["review_scope"] == "full_structural_scan"
    assert result["document_profile"]["root_element"] == "map"
    assert result["warnings"]
    assert "Map review mode" in result["warnings"][0]


@pytest.mark.anyio
async def test_review_dita_xml_marks_large_documents_as_scoped(monkeypatch):
    async def fake_build_review_snapshot(**_kwargs):
        return {
            "dita_type": "map",
            "quality_score": 72,
            "quality_breakdown": {"structure": 80, "content_richness": 60, "dita_features": 70, "aem_readiness": 78},
            "validation": [{"label": "map title present", "passing": True}],
            "suggestions_report": {"total": 0, "errors": 0, "warnings": 0, "suggestions": []},
            "sources_used": [{"label": "Live XML review", "count": 1}],
        }

    monkeypatch.setattr("app.services.smart_suggestions_service.build_review_snapshot", fake_build_review_snapshot)
    topicrefs = "\n".join(f'<topicref href="topics/t-{index}.dita"/>' for index in range(260))
    xml = f"<map id=\"large\"><title>Large</title>{topicrefs}</map>"

    result = await execute_review_dita_xml(xml)

    assert result["review_scope"] == "large_document_structural_scan"
    assert result["document_profile"]["large_document"] is True
    assert result["document_profile"]["topicref_count"] == 260
    assert any("Large map detected" in warning for warning in result["warnings"])
    assert "Findings are prioritized" in result["summary"]


def test_normalize_tool_result_preserves_existing_status_for_jobs():
    normalized = _normalize_tool_result(
        "create_job",
        {
            "job_id": "job-1",
            "recipe_type": "task_topics",
            "status": "queued",
        },
    )

    assert normalized["kind"] == "job"
    assert normalized["status"] == "queued"
    assert normalized["status_tone"] == "success"
    assert "Started dataset job" in str(normalized["summary"])


def test_normalize_tool_result_marks_warning_when_lookup_has_no_sources():
    normalized = _normalize_tool_result(
        "lookup_dita_spec",
        {
            "query": "mystery element",
            "spec_chunks": [],
            "graph_knowledge": "",
        },
    )

    assert normalized["kind"] == "guidance"
    assert normalized["status_tone"] == "warning"
    assert "No DITA specification evidence" in str(normalized["summary"])


def test_normalize_tool_result_collects_explicit_warnings():
    normalized = _normalize_tool_result(
        "generate_image",
        {
            "artifacts": [{"id": "img-1"}],
            "warning": "Local SVG fallback was used.",
        },
    )

    assert normalized["kind"] == "artifact"
    assert normalized["warnings"] == ["Local SVG fallback was used."]
    assert normalized["status_tone"] == "warning"


@pytest.mark.anyio
async def test_lookup_dita_spec_recognizes_attribute_queries():
    result = await execute_lookup_dita_spec("Please provide information about format attribute.")

    assert result["attribute_name"] == "format"
    assert result["matched_via"] == "attribute_catalog"
    assert result["source_url"] == "https://www.oxygenxml.com/dita/1.3/specs/langRef/attributes/theformatattribute.html"
    assert "all_valid_values" in result
    assert "supported_elements" in result
    assert result["attribute_semantic_class"] in {"enum", "path_like", "reference_like"}
    assert not result["spec_chunks"]


@pytest.mark.anyio
async def test_lookup_dita_spec_returns_structured_content_model_for_taskbody():
    result = await execute_lookup_dita_spec("What can go inside taskbody?")

    assert result["element_name"] == "taskbody"
    assert result["query_type"] == "content_model"
    assert "steps" in result["allowed_children"]
    assert "content_model_summary" in result
    assert "<taskbody>" in result["content_model_summary"]
    assert result["summary"] == result["content_model_summary"]


@pytest.mark.anyio
async def test_lookup_dita_spec_returns_structured_placement_for_choicetable():
    result = await execute_lookup_dita_spec("Where can choicetable appear?")

    assert result["element_name"] == "choicetable"
    assert result["query_type"] == "placement"
    assert "step" in result["parent_elements"]
    assert "<choicetable>" in result["placement_summary"]
    assert result["summary"] == result["placement_summary"]


@pytest.mark.anyio
async def test_lookup_dita_spec_returns_structured_content_model_for_ditavalref():
    result = await execute_lookup_dita_spec("What can go inside ditavalref?")

    assert result["element_name"] == "ditavalref"
    assert result["query_type"] == "content_model"
    assert "ditavalmeta" in result["allowed_children"]
    assert "<ditavalref>" in result["content_model_summary"]
    assert result["summary"] == result["content_model_summary"]
    assert "branch filtering" in str(result["text_content"]).lower()


@pytest.mark.anyio
async def test_lookup_dita_spec_returns_structured_attribute_comparison():
    result = await execute_lookup_dita_spec("conref vs conkeyref")

    assert result["query_type"] == "attribute_comparison"
    assert result["comparison_type"] == "attribute"
    assert result["attribute_names"] == ["conref", "conkeyref"]
    assert len(result["comparisons"]) == 2
    assert "Compared DITA attributes" in str(result["summary"])


@pytest.mark.anyio
async def test_lookup_dita_spec_returns_table_family_comparison_for_overview_question():
    result = await execute_lookup_dita_spec("Different types of tables in dita")

    assert result["query_type"] == "element_family_overview"
    assert result["comparison_type"] == "element_family"
    assert result["element_names"][:3] == ["table", "simpletable", "choicetable"]
    assert len(result["comparisons"]) >= 3
    assert any(str(item.get("element_name") or "") == "table" for item in result["comparisons"])
    assert any(str(item.get("element_name") or "") == "simpletable" for item in result["comparisons"])
    assert any(str(item.get("element_name") or "") == "choicetable" for item in result["comparisons"])


@pytest.mark.anyio
async def test_lookup_dita_attribute_parses_natural_language_multi_attribute_queries():
    result = await execute_lookup_dita_attribute("please let me know about conref and conkeyref attributes?")

    assert result["attribute_names"] == ["conref", "conkeyref"]
    assert len(result["attributes"]) == 2
    assert "conref" in result["summary"]
    assert "conkeyref" in result["summary"]
    assert result["attributes"][0]["attribute_name"] == "conref"
    assert result["attributes"][1]["attribute_name"] == "conkeyref"


def test_list_attribute_names_includes_attribute_like_seed_entries():
    names = list_attribute_names()

    assert "scope" in names
    assert "chunk" in names
    assert "scalefit" in names


def test_extract_dita_attributes_from_query_parses_comma_separated_attributes():
    matches = _extract_dita_attributes_from_query("scope,chunk")

    assert matches == ["scope", "chunk"]


def test_interpret_dita_query_treats_chunking_as_chunk_attribute():
    from app.services.dita_query_interpreter import extract_attribute_names

    assert extract_attribute_names("What do you mean by chunking?") == ["chunk"]


@pytest.mark.anyio
async def test_lookup_dita_attribute_returns_both_scope_and_chunk_for_comma_query():
    result = await execute_lookup_dita_attribute("scope,chunk")

    assert result["attribute_names"] == ["scope", "chunk"]
    assert len(result["attributes"]) == 2
    assert {item["attribute_name"] for item in result["attributes"]} == {"scope", "chunk"}


def test_get_attribute_spec_merges_richer_attribute_seed_data_for_conref():
    spec = get_attribute_spec("conref")

    assert spec is not None
    assert spec.attribute_name == "conref"
    assert spec.usage_contexts
    assert spec.common_mistakes
    assert spec.correct_examples
    assert spec.text_content.startswith("@conref")
    assert "conrefend" in spec.combination_attributes
    assert "conaction" in spec.combination_attributes
    assert {"note", "p", "step"}.issubset(set(spec.supported_elements))


def test_get_attribute_spec_treats_attribute_map_keys_as_valid_values_not_combination_attributes():
    scope_spec = get_attribute_spec("scope")
    chunk_spec = get_attribute_spec("chunk")

    assert scope_spec is not None
    assert chunk_spec is not None

    assert {"local", "peer", "external"}.issubset(set(scope_spec.all_valid_values))
    assert "local" not in scope_spec.combination_attributes
    assert "peer" not in scope_spec.combination_attributes
    assert "external" not in scope_spec.combination_attributes
    assert {"to-content", "by-topic", "by-document"}.issubset(set(chunk_spec.all_valid_values))


def test_get_attribute_spec_does_not_treat_keyscope_usage_labels_as_enum_values():
    spec = get_attribute_spec("keyscope")

    assert spec is not None
    assert spec.all_valid_values == []
    assert "space-separated scope names" in spec.text_content.lower()
    assert spec.semantic_class == "map_scoped"
    assert "space-separated scope names" in spec.syntax.lower()
    assert "topicref" in spec.supported_elements
    assert "map" in spec.supported_elements


def test_get_attribute_spec_returns_structured_scalefit_override():
    spec = get_attribute_spec("scalefit")

    assert spec is not None
    assert spec.attribute_name == "scalefit"
    assert spec.semantic_class == "boolean_like"
    assert spec.syntax == "yes, no, or -dita-use-conref-target"
    assert {"yes", "no", "-dita-use-conref-target"}.issubset(set(spec.all_valid_values))
    assert "image" in spec.supported_elements
    assert "height" in spec.combination_attributes
    assert "scaled up or down to fit within available space" in spec.text_content.lower()
    assert spec.source_url == "https://dita-lang.org/dita/langref/base/image"


@pytest.mark.anyio
async def test_lookup_dita_attribute_exposes_semantic_class_and_syntax_for_keyscope():
    result = await execute_lookup_dita_attribute("What is keyscope in dita?")

    assert result["attribute_name"] == "keyscope"
    assert result["attribute_semantic_class"] == "map_scoped"
    assert "space-separated scope names" in str(result["attribute_syntax"]).lower()


@pytest.mark.anyio
async def test_lookup_dita_attribute_returns_structured_scalefit_guidance():
    result = await execute_lookup_dita_attribute("What is a scalefit attribute?")

    assert result["attribute_name"] == "scalefit"
    assert result["attribute_semantic_class"] == "boolean_like"
    assert result["attribute_syntax"] == "yes, no, or -dita-use-conref-target"
    assert {"yes", "no", "-dita-use-conref-target"}.issubset(set(result["all_valid_values"]))
    assert "image" in result["supported_elements"]
    assert "height" in result["combination_attributes"]
    assert "scaled up or down to fit within available space" in str(result["text_content"]).lower()
    assert result["source_url"] == "https://dita-lang.org/dita/langref/base/image"


@pytest.mark.anyio
async def test_lookup_dita_spec_recognizes_scalefit_attribute_queries():
    result = await execute_lookup_dita_spec("What is a scalefit attribute?")

    assert result["attribute_name"] == "scalefit"
    assert result["matched_via"] == "attribute_catalog"
    assert result["attribute_semantic_class"] == "boolean_like"
    assert result["attribute_syntax"] == "yes, no, or -dita-use-conref-target"
    assert "image" in result["supported_elements"]
    assert result["source_url"] == "https://dita-lang.org/dita/langref/base/image"


@pytest.mark.anyio
async def test_lookup_dita_attribute_returns_richer_structured_guidance_for_multi_attribute_queries():
    result = await execute_lookup_dita_attribute("please let me know about conref and conkeyref attributes?")

    conref = next(item for item in result["attributes"] if item["attribute_name"] == "conref")
    conkeyref = next(item for item in result["attributes"] if item["attribute_name"] == "conkeyref")

    assert conref["usage_contexts"]
    assert conref["common_mistakes"]
    assert conref["correct_examples"]
    assert {"note", "p", "step"}.issubset(set(conref["supported_elements"]))
    assert conkeyref["correct_examples"]
    assert conkeyref["combination_attributes"]


def test_normalize_tool_result_summarizes_attribute_aware_spec_lookup():
    normalized = _normalize_tool_result(
        "lookup_dita_spec",
        {
            "query": "format attribute",
            "attribute_name": "format",
            "all_valid_values": ["dita", "ditamap", "html", "pdf"],
            "supported_elements": ["xref", "topicref", "image"],
            "text_content": "The format attribute identifies the format of the resource referenced by href.",
            "source_url": "https://www.oxygenxml.com/dita/1.3/specs/langRef/attributes/theformatattribute.html",
        },
    )

    assert normalized["status_tone"] == "success"
    assert "Retrieved DITA attribute guidance for `format`." in str(normalized["summary"])
    assert normalized["sources"]
    assert normalized["sources"][0]["label"] == "format"
    assert normalized["sources"][0]["url"] == "https://www.oxygenxml.com/dita/1.3/specs/langRef/attributes/theformatattribute.html"


def test_normalize_tool_result_summarizes_content_model_lookup():
    normalized = _normalize_tool_result(
        "lookup_dita_spec",
        {
            "query": "What can go inside taskbody?",
            "element_name": "taskbody",
            "query_type": "content_model",
            "content_model_summary": "Inside <taskbody>, DITA allows `prereq`, `context`, `steps`, `steps-unordered`, `result`, and `postreq`.",
            "allowed_children": ["prereq", "context", "steps", "steps-unordered", "result", "postreq"],
            "text_content": "<taskbody> is the main body element inside a DITA task topic.",
            "source_url": "https://example.com/taskbody",
        },
    )

    assert normalized["status_tone"] == "success"
    assert "Inside <taskbody>" in str(normalized["summary"])
    assert normalized["sources"]
    assert normalized["sources"][0]["label"] == "taskbody"


def test_llm_chat_tool_definitions_are_subset_of_frontend_registry():
    """LLM-facing catalog is minimal; UI registry still lists tools used by agent/grounding cards."""
    llm_names = {str(tool["name"]).strip() for tool in get_tool_definitions()}
    assert llm_names == {"generate_dita", "generate_xml_flowchart"}
    tool_utils_path = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "components"
        / "Chat"
        / "toolResultUtils.ts"
    )
    text = tool_utils_path.read_text(encoding="utf-8")
    match = re.search(r"KNOWN_FIRST_PARTY_TOOLS\s*=\s*new Set\(\[(.*?)\]\);", text, re.S)
    assert match, "KNOWN_FIRST_PARTY_TOOLS set not found in frontend toolResultUtils.ts"
    frontend_names = set(re.findall(r"'([^']+)'", match.group(1)))

    assert llm_names.issubset(frontend_names)


def test_normalize_tool_result_summarizes_multi_attribute_lookup():
    normalized = _normalize_tool_result(
        "lookup_dita_attribute",
        {
            "attribute_names": ["conref", "conkeyref"],
            "attributes": [
                {
                    "attribute_name": "conref",
                    "text_content": "Direct content reuse by file path.",
                    "source_url": "https://example.com/conref",
                },
                {
                    "attribute_name": "conkeyref",
                    "text_content": "Key-based content reuse.",
                    "source_url": "https://example.com/conkeyref",
                },
            ],
        },
    )

    assert normalized["summary"] == "Retrieved DITA attribute guidance for `conref`, `conkeyref`."
    assert len(normalized["sources"]) == 2
    assert normalized["sources"][0]["label"] == "conref"
    assert normalized["sources"][1]["label"] == "conkeyref"


@pytest.mark.anyio
async def test_lookup_aem_guides_surfaces_retrieval_diagnostics(monkeypatch):
    monkeypatch.setattr(tavily_search_service, "is_chat_tavily_enabled", lambda: False)
    monkeypatch.setattr(
        doc_retriever_service,
        "retrieve_relevant_docs_with_diagnostics",
        lambda *args, **kwargs: {
            "results": [
                {
                    "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/workspace-configs/workspace-settings",
                    "title": "Workspace settings in Experience Manager Guides",
                    "snippet": "Open Workspace settings from the profile menu.",
                }
            ],
            "count": 1,
            "retrieval_mode": "lexical",
            "semantic_required": False,
            "embedding": {
                "available": False,
                "configured_model": "all-MiniLM-L6-v2",
                "configured_model_path": "",
                "active_model_identifier": "all-MiniLM-L6-v2",
                "load_mode": "fallback_none",
                "error": "WinError 10013",
            },
            "warnings": ["Semantic retrieval was unavailable, so retrieval used lexical ranking only."],
        },
    )

    result = await execute_lookup_aem_guides("How do I configure workspace settings in AEM Guides?")

    assert result["count"] == 1
    assert result["retrieval_mode"] == "lexical"
    assert result["semantic_required"] is False
    assert result["embedding"]["available"] is False
    assert "lexical ranking only" in result["warnings"][0].lower()
    assert result["live_search"]["enabled"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_lookup_aem_guides_uses_tavily_live_results_before_local_rag(monkeypatch):
    monkeypatch.setattr(tavily_search_service, "is_chat_tavily_enabled", lambda: True)
    monkeypatch.setattr(
        tavily_search_service,
        "tavily_search_sync",
        lambda *args, **kwargs: {
            "answer": "Use the Repository panel New file action for topics and Create > DITA Map for maps.",
            "results": [
                {
                    "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/work-with-editor/create-preview-topics/web-editor-create-topics",
                    "title": "Create topics | Adobe Experience Manager",
                    "content": "In the Repository panel, select the New file icon and then select Topic from the dropdown menu.",
                }
            ],
        },
    )
    monkeypatch.setattr(
        doc_retriever_service,
        "retrieve_relevant_docs_with_diagnostics",
        lambda *args, **kwargs: {
            "results": [
                {
                    "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/output-presets-aemg/aem-sites/generate-output-aem-site-map-dashboard",
                    "title": "AEM Site",
                    "snippet": "Generate article-based output from the Map console.",
                }
            ],
            "retrieval_mode": "lexical",
            "semantic_required": False,
            "embedding": {},
            "warnings": [],
        },
    )

    result = await execute_lookup_aem_guides("How do you create a topic or map in AEM Guides?", k=3)

    assert result["count"] == 2
    assert result["live_search"]["enabled"] is True
    assert result["live_search"]["strategy"] == "experience_league_first"
    assert result["live_search"]["result_count"] == 1
    assert result["results"][0]["source"] == "tavily"
    assert "Repository panel" in result["summary"]
    assert result["results"][1]["source"] == "local_rag"
