"""Chat tools - generate_dita, create_job for AI assistant."""
import asyncio
import json
import re
from typing import Any
from uuid import uuid4

from app.core.structured_logging import get_structured_logger
from app.services.chat_multimodal_service import generate_image, generate_xml_flowchart
from app.services.dataset_job_service import (
    build_dataset_job_urls,
    create_dataset_job_record,
    enforce_concurrent_job_limit,
    start_dataset_job_in_background,
)
from app.services.generate_from_text_service import run_generate_from_text, update_generate_progress
from app.services.jira_chat_search_service import search_related_jira_issues

# Control characters and null bytes - strip from tool output
_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_DITA_ATTRIBUTE_QUERY_PATTERN = re.compile(
    r"@([A-Za-z_:][A-Za-z0-9_.:-]*)|"
    r"\battribute\s+`?@?([A-Za-z_:][A-Za-z0-9_.:-]*)`?\b|"
    r"\b`?@?([A-Za-z_:][A-Za-z0-9_.:-]*)`?\s+attribute\b",
    re.IGNORECASE,
)
_DITA_ATTRIBUTE_STOPWORDS = frozenset({"attribute", "dita", "xml", "topic", "map"})
_DITA_ATTRIBUTE_TOKEN_PATTERN = re.compile(r"@?[A-Za-z_:][A-Za-z0-9_.:-]*")
_DITA_CONTENT_MODEL_QUERY_PATTERN = re.compile(
    r"\b("
    r"what\s+can\s+go\s+inside|"
    r"what\s+can\s+go\s+in|"
    r"what\s+is\s+allowed\s+in|"
    r"what\s+may\s+appear\s+in|"
    r"content\s+model(?:\s+of|\s+for)?|"
    r"children\s+of|"
    r"inside\s+<?"
    r")",
    re.IGNORECASE,
)
_DITA_PLACEMENT_QUERY_PATTERN = re.compile(
    r"\b("
    r"where\s+can|"
    r"where\s+does|"
    r"where\s+is|"
    r"which\s+elements?\s+can\s+contain|"
    r"which\s+parents?\s+contain"
    r")\b",
    re.IGNORECASE,
)


def _sanitize_tool_result(obj: Any) -> Any:
    """Recursively strip control chars from strings in tool result. Leaves structure intact."""
    if obj is None:
        return obj
    if isinstance(obj, str):
        return _CONTROL_CHAR_PATTERN.sub("", obj)
    if isinstance(obj, dict):
        return {k: _sanitize_tool_result(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_tool_result(v) for v in obj]
    return obj

logger = get_structured_logger(__name__)
RECIPE_TYPE_ALLOWLIST = frozenset({
    # Specialized Content
    "task_topics", "concept_topics", "reference_topics", "glossary_pack",
    "bookmap_structure", "choicetable_tasks", "choicetable_references",
    "properties_table_reference", "bookmap_elements_reference",
    "table_semantics_reference", "topic_ph_keyword_related_links",
    # Map Structure
    "maps_topicgroup_basic", "maps_topicgroup_nested", "maps_topicref_basic",
    "maps_nested_topicrefs", "maps_mapref_basic", "maps_topichead_basic",
    "maps_reltable_basic", "maps_topicset_basic", "maps_navref_basic",
    # Content Reuse
    "conref_pack", "dita_conref_title_dataset_recipe", "dita_conref_keyref_dataset_recipe",
    "dita_subject_scheme_dataset_recipe", "dita_glossary_abbrev_dataset_recipe",
    "customer_reuse_pack",
    # Advanced Features
    "relationship_table", "advanced_relationships", "conditional_content",
    "media_rich_content", "topic_svg_mathml_foreign", "inline_formatting_nested",
    "nested_topic_inline", "self_conrefend_range", "self_xref_conref_positive",
    # Performance & Scale
    "incremental_topicref_maps", "insurance_incremental", "large_scale",
    "deep_hierarchy", "wide_branching", "map_parse_stress",
    "heavy_topics_tables_codeblocks", "heavy_conditional_topic_6000_lines",
    "bulk_dita_map_topics", "flat_hierarchical_dita", "large_root_map_1000_topics_100kb",
    # Metadata & Keys
    "keyscope_demo", "keyword_metadata", "keyref_nested_keydef_chain_map_to_map_to_topic",
    # Workflow & Localization
    "workflow_enabled_content", "localized_content",
    # Output Optimization
    "output_optimized",
    # Legacy Patterns
    "hub_spoke_inbound", "keydef_heavy", "map_cyclic",
    # Enterprise Scenarios
    "parent_child_maps_keys_conref_conkeyref_selfrefs",
    "compact_parent_child_key_resolution", "conrefend_cyclic_duplicate_id",
    # Validation & Negative
    "validation_duplicate_id_negative", "validation_invalid_child_negative",
    "validation_missing_body_negative",
})

_TOOL_UI_META: dict[str, dict[str, Any]] = {
    "generate_dita": {
        "slash_alias": "generate_dita",
        "title": "Generate DITA",
        "category": "Creation",
        "primary_arg": "text",
    },
    "create_job": {
        "slash_alias": "create_job",
        "title": "Generate Dataset",
        "category": "Creation",
    },
    "search_jira_issues": {
        "slash_alias": "search_jira_issues",
        "title": "Search Jira Issues",
        "category": "Research",
        "primary_arg": "query",
    },
    "lookup_dita_spec": {
        "slash_alias": "lookup_dita_spec",
        "title": "Lookup DITA Spec",
        "category": "Research",
        "primary_arg": "query",
    },
    "review_dita_xml": {
        "slash_alias": "review_dita_xml",
        "title": "Review DITA XML",
        "category": "Review",
        "primary_arg": "xml",
    },
    "find_recipes": {
        "slash_alias": "find_recipes",
        "title": "Find Recipes",
        "category": "Research",
        "primary_arg": "query",
    },
    "get_job_status": {
        "slash_alias": "get_job_status",
        "title": "Get Job Status",
        "category": "Inspect",
        "primary_arg": "job_id",
    },
    "lookup_aem_guides": {
        "slash_alias": "lookup_aem_guides",
        "title": "Lookup AEM Guides",
        "category": "Research",
        "primary_arg": "query",
    },
    "search_tenant_knowledge": {
        "slash_alias": "search_tenant_knowledge",
        "title": "Search Knowledge Base",
        "category": "Research",
        "primary_arg": "query",
    },
    "lookup_output_preset": {
        "slash_alias": "lookup_output_preset",
        "title": "Lookup Output Preset",
        "category": "Research",
        "primary_arg": "query",
    },
    "list_jobs": {
        "slash_alias": "list_jobs",
        "title": "List Jobs",
        "category": "Inspect",
    },
    "fix_dita_xml": {
        "slash_alias": "fix_dita_xml",
        "title": "Fix DITA XML",
        "category": "Review",
        "primary_arg": "xml",
    },
    "lookup_dita_attribute": {
        "slash_alias": "lookup_dita_attribute",
        "title": "Lookup DITA Attribute",
        "category": "Research",
        "primary_arg": "attribute_name",
    },
    "list_indexed_pdfs": {
        "slash_alias": "list_indexed_pdfs",
        "title": "List Indexed PDFs",
        "category": "Inspect",
    },
    "generate_native_pdf_config": {
        "slash_alias": "generate_native_pdf_config",
        "title": "Generate Native PDF Config",
        "category": "Creation",
        "primary_arg": "query",
    },
    "browse_dataset": {
        "slash_alias": "browse_dataset",
        "title": "Browse Dataset",
        "category": "Inspect",
        "primary_arg": "job_id",
    },
    "generate_xml_flowchart": {
        "slash_alias": "generate_xml_flowchart",
        "title": "Generate XML Flowchart",
        "category": "Visualization",
        "primary_arg": "xml",
    },
    "generate_image": {
        "slash_alias": "generate_image",
        "title": "Generate Image",
        "category": "Visualization",
        "primary_arg": "prompt",
    },
}

_TOOL_KIND_BY_NAME: dict[str, str] = {
    "generate_dita": "generation",
    "create_job": "job",
    "search_jira_issues": "search",
    "lookup_dita_spec": "guidance",
    "review_dita_xml": "review",
    "find_recipes": "search",
    "get_job_status": "job",
    "lookup_aem_guides": "guidance",
    "search_tenant_knowledge": "search",
    "lookup_output_preset": "guidance",
    "list_jobs": "job",
    "fix_dita_xml": "review",
    "lookup_dita_attribute": "guidance",
    "list_indexed_pdfs": "browse",
    "generate_native_pdf_config": "guidance",
    "browse_dataset": "browse",
    "generate_xml_flowchart": "artifact",
    "generate_image": "artifact",
}


def _extract_dita_attribute_from_query(query: str) -> str:
    matches = _extract_dita_attributes_from_query(query)
    return matches[0] if matches else ""


def _extract_dita_attributes_from_query(query: str) -> list[str]:
    from app.services.dita_query_interpreter import extract_attribute_names

    return extract_attribute_names(query)


def _extract_dita_elements_from_query(
    query: str,
    explicit_elements: list[str] | None = None,
) -> list[str]:
    from app.services.dita_query_interpreter import extract_element_names

    return extract_element_names(query, explicit_elements=explicit_elements)


def _detect_dita_spec_query_type(query: str) -> str:
    from app.services.dita_query_interpreter import interpret_dita_query

    mode = interpret_dita_query(query).mode
    if mode == "content_model_query":
        return "content_model"
    if mode == "allowed_usage_query":
        return "placement"
    if mode == "attribute_values":
        return "attribute_values"
    if mode == "attribute_comparison":
        return "attribute_comparison"
    if mode == "element_comparison":
        return "element_comparison"
    return "element_definition"


def _format_dita_name(name: str) -> str:
    clean = str(name or "").strip().strip("<>")
    return f"<{clean}>" if clean else "DITA"


def _format_inline_list(values: list[str], *, limit: int = 8) -> str:
    cleaned = [str(item).strip() for item in values if str(item).strip()]
    if not cleaned:
        return ""
    preview = [f"`{item}`" for item in cleaned[:limit]]
    if len(cleaned) == 1:
        return preview[0]
    if len(cleaned) == 2:
        return f"{preview[0]} and {preview[1]}"
    if len(cleaned) <= limit:
        return f"{', '.join(preview[:-1])}, and {preview[-1]}"
    return f"{', '.join(preview)}, and {len(cleaned) - limit} more"


def _first_sentence(text: str, *, limit: int = 320) -> str:
    compact = " ".join(str(text or "").split()).strip()
    if not compact:
        return ""
    sentence_match = re.search(r"(.+?[.!?])(?:\s|$)", compact)
    if sentence_match:
        return sentence_match.group(1).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _find_parent_elements(element_name: str) -> list[str]:
    from app.services.dita_spec_registry_service import get_element_spec

    spec = get_element_spec(element_name)
    return list(spec.allowed_parents) if spec is not None else []


def _collect_exact_spec_chunks(query: str, element_name: str) -> list[dict[str, Any]]:
    from app.services.dita_knowledge_retriever import retrieve_dita_knowledge

    target = str(element_name or "").strip().lower()
    if not target:
        return []

    merged: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for search_query in (query, target):
        if not str(search_query or "").strip():
            continue
        for chunk in retrieve_dita_knowledge(str(search_query), k=12):
            if not isinstance(chunk, dict):
                continue
            chunk_name = str(chunk.get("element_name") or "").strip().lower()
            if chunk_name != target:
                continue
            text_content = str(chunk.get("text_content") or "").strip()
            key = (chunk_name, text_content[:160])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            merged.append(chunk)
    return merged[:5]


def _build_dita_attribute_comparison_guidance(query: str, attribute_names: list[str]) -> dict[str, Any] | None:
    from app.services.dita_attribute_catalog import get_attribute_spec

    comparisons: list[dict[str, Any]] = []
    missing: list[str] = []
    for attribute_name in attribute_names[:4]:
        spec = get_attribute_spec(attribute_name)
        if spec is None:
            missing.append(attribute_name)
            continue
        comparisons.append(
            {
                "attribute_name": spec.attribute_name,
                "all_valid_values": spec.all_valid_values,
                "supported_elements": spec.supported_elements,
                "combination_attributes": spec.combination_attributes,
                "usage_contexts": spec.usage_contexts,
                "common_mistakes": spec.common_mistakes,
                "correct_examples": spec.correct_examples,
                "attribute_semantic_class": spec.semantic_class,
                "attribute_syntax": spec.syntax,
                "text_content": (spec.text_content or "")[:1200],
                "source_url": spec.source_url,
            }
        )

    if not comparisons:
        return None

    summary = (
        f"Compared DITA attributes {_format_inline_list([item['attribute_name'] for item in comparisons], limit=4)}."
    )
    warnings: list[str] = []
    if missing:
        warnings.append(
            f"No structured attribute evidence was found for {_format_inline_list(missing, limit=4)}."
        )

    return {
        "query": query,
        "query_type": "attribute_comparison",
        "comparison_type": "attribute",
        "attribute_names": [item["attribute_name"] for item in comparisons],
        "comparisons": comparisons,
        "summary": summary,
        "warnings": warnings,
        "spec_chunks": [],
        "graph_knowledge": "",
    }


def _build_dita_element_comparison_guidance(query: str, element_names: list[str]) -> dict[str, Any] | None:
    from app.services.dita_spec_registry_service import get_element_spec

    comparisons: list[dict[str, Any]] = []
    missing: list[str] = []
    for element_name in element_names[:4]:
        spec = get_element_spec(element_name)
        if spec is None:
            missing.append(element_name)
            continue
        comparisons.append(
            {
                "element_name": spec.name,
                "allowed_children": spec.allowed_children,
                "parent_elements": spec.allowed_parents,
                "supported_attributes": spec.supported_attributes,
                "text_content": spec.description[:1200],
                "source_url": spec.source_url,
                "usage_contexts": spec.usage_contexts,
                "common_mistakes": spec.common_mistakes,
                "correct_examples": spec.correct_examples,
            }
        )

    if not comparisons:
        return None

    summary = (
        f"Compared DITA elements {_format_inline_list([item['element_name'] for item in comparisons], limit=4)}."
    )
    warnings: list[str] = []
    if missing:
        warnings.append(
            f"No structured element evidence was found for {_format_inline_list(missing, limit=4)}."
        )

    return {
        "query": query,
        "query_type": "element_comparison",
        "comparison_type": "element",
        "element_names": [item["element_name"] for item in comparisons],
        "comparisons": comparisons,
        "summary": summary,
        "warnings": warnings,
        "spec_chunks": [],
        "graph_knowledge": "",
    }


def _build_dita_element_guidance(
    query: str,
    elements: list[str] | None = None,
) -> dict[str, Any] | None:
    from app.services.dita_graph_service import get_attributes_of, get_children_of, get_element_summary
    from app.services.dita_query_interpreter import interpret_dita_query
    from app.services.dita_knowledge_retriever import retrieve_dita_graph_knowledge
    from app.services.dita_spec_registry_service import get_element_spec

    intent = interpret_dita_query(query, explicit_elements=elements)
    matched_elements = intent.element_names
    if not matched_elements:
        return None

    if intent.mode == "element_comparison" and len(matched_elements) >= 2:
        return _build_dita_element_comparison_guidance(query, matched_elements)

    element_name = matched_elements[0]
    query_type = _detect_dita_spec_query_type(query)
    exact_chunks = _collect_exact_spec_chunks(query, element_name)
    registry_spec = get_element_spec(element_name)
    children = list(registry_spec.allowed_children) if registry_spec is not None else [
        str(item).strip() for item in get_children_of(element_name) if str(item).strip()
    ]
    parent_elements = list(registry_spec.allowed_parents) if registry_spec is not None else _find_parent_elements(element_name)
    attributes = dict(registry_spec.attribute_usage) if registry_spec is not None else get_attributes_of(element_name)
    summary_text = (
        str(registry_spec.description or "").strip()
        if registry_spec is not None
        else str(get_element_summary(element_name) or "").strip()
    )
    exact_text = next(
        (str(chunk.get("text_content") or "").strip() for chunk in exact_chunks if str(chunk.get("text_content") or "").strip()),
        "",
    )
    source_url = next(
        (str(chunk.get("source_url") or "").strip() for chunk in exact_chunks if str(chunk.get("source_url") or "").strip()),
        "",
    )
    if not source_url and registry_spec is not None:
        source_url = str(registry_spec.source_url or "").strip()
    graph_knowledge = retrieve_dita_graph_knowledge(elements=[element_name])
    text_content = exact_text or summary_text

    content_model_summary = ""
    placement_summary = ""
    if children and query_type == "content_model":
        content_model_summary = (
            f"Inside {_format_dita_name(element_name)}, DITA allows { _format_inline_list(children, limit=10) }."
        )
    if parent_elements and query_type == "placement":
        placement_summary = (
            f"{_format_dita_name(element_name)} can appear inside { _format_inline_list(parent_elements, limit=10) }."
        )

    summary = (
        content_model_summary
        or placement_summary
        or _first_sentence(text_content)
        or (f"Retrieved DITA element guidance for `{element_name}`." if exact_chunks or graph_knowledge else "")
    )

    if not summary and not children and not parent_elements and not text_content and not graph_knowledge:
        return None

    warnings: list[str] = []
    if not source_url and (children or parent_elements or graph_knowledge):
        warnings.append(
            f"Exact spec excerpts for `{element_name}` were limited, so this answer leans on the internal DITA structure graph."
        )

    return {
        "query": query,
        "query_type": query_type,
        "element_name": element_name,
        "matched_elements": matched_elements,
        "content_model_summary": content_model_summary,
        "placement_summary": placement_summary,
        "allowed_children": children,
        "parent_elements": parent_elements,
        "supported_attributes": sorted(str(key).strip() for key in (attributes or {}).keys() if str(key).strip()),
        "attribute_usage": {str(key): str(value) for key, value in (attributes or {}).items()},
        "text_content": text_content[:1200],
        "source_url": source_url,
        "usage_contexts": list(registry_spec.usage_contexts) if registry_spec is not None else [],
        "common_mistakes": list(registry_spec.common_mistakes) if registry_spec is not None else [],
        "correct_examples": list(registry_spec.correct_examples) if registry_spec is not None else [],
        "spec_chunks": [
            {
                "element_name": chunk.get("element_name"),
                "text_content": (chunk.get("text_content") or "")[:800],
                "source_url": chunk.get("source_url") or "",
            }
            for chunk in exact_chunks[:4]
        ],
        "graph_knowledge": graph_knowledge,
        "matched_via": "element_graph",
        "summary": summary,
        "warnings": warnings,
    }


_NATIVE_PDF_GUIDANCE: dict[str, dict[str, Any]] = {
    "watermark": {
        "matched_terms": ["watermark", "draft mark", "confidential"],
        "short_answer": (
            "Use the Native PDF page layout and stylesheet together so the watermark is anchored at the page level, "
            "not embedded in the topic body."
        ),
        "recommended_actions": [
            "Start from the page layout used by the target topic pages, chapter pages, or front matter pages.",
            "Apply the watermark as page-level styling so it repeats consistently across generated pages.",
            "Scope the watermark to the correct page class instead of applying it globally to every page type.",
            "Verify the output preset is pointing at the intended Native PDF template before testing changes.",
        ],
        "relevant_settings": [
            "Page layout or master page assignment for the affected page type",
            "Watermark background asset, text, or overlay styling",
            "Opacity, positioning, repeat behavior, and layer ordering",
            "Output preset selection for the Native PDF template",
        ],
        "xml_or_css_snippets": [
            "@page body-page {\n  background-image: url(\"watermark.svg\");\n  background-repeat: no-repeat;\n  background-position: center center;\n}",
        ],
        "common_mistakes": [
            "Applying the watermark inside topic content instead of the page layout or page stylesheet",
            "Editing the template but testing with an output preset that still points to a different Native PDF template",
            "Using full-opacity artwork that makes body text hard to read",
        ],
    },
    "page_layout": {
        "matched_terms": ["page layout", "layout", "master page", "page size", "margin"],
        "short_answer": (
            "Define the page geometry in the Native PDF page layout first, then keep the stylesheet focused on visual styling."
        ),
        "recommended_actions": [
            "Choose the correct page layout for body, front matter, chapter, and appendix page types.",
            "Set page size, orientation, margins, and header/footer regions in the layout.",
            "Test odd, even, and first-page behavior separately if the template supports different page classes.",
        ],
        "relevant_settings": [
            "Page size and orientation",
            "Margins and region sizing",
            "First/odd/even page variants",
            "Template-to-output-preset mapping",
        ],
        "xml_or_css_snippets": [],
        "common_mistakes": [
            "Trying to solve page geometry only in CSS after the wrong page layout has already been selected",
            "Using one page layout for all page types when the PDF needs different first-page or chapter behavior",
        ],
    },
    "toc": {
        "matched_terms": ["toc", "table of contents", "bookmarks", "bookmark"],
        "short_answer": (
            "Treat TOC styling and bookmark behavior as separate concerns: style the visible TOC, then verify which headings and map entries generate PDF bookmarks."
        ),
        "recommended_actions": [
            "Adjust TOC typography and spacing in the Native PDF template styles.",
            "Verify the heading levels and map structure that feed the visible TOC and PDF bookmarks.",
            "Test long titles and nested entries to confirm indentation and wrapping stay readable.",
        ],
        "relevant_settings": [
            "TOC title and entry styles",
            "Heading level inclusion",
            "Bookmark generation behavior",
            "Indentation and page-number alignment",
        ],
        "xml_or_css_snippets": [],
        "common_mistakes": [
            "Changing visual TOC styles without checking whether the right structural levels are actually included",
            "Assuming bookmark structure will automatically match the visible TOC without validating heading depth",
        ],
    },
    "headers_footers": {
        "matched_terms": ["header", "footer", "running header", "running footer", "page number"],
        "short_answer": (
            "Configure headers and footers in the page layout regions, then bind the displayed text, page numbers, and variables through the template styling."
        ),
        "recommended_actions": [
            "Edit the relevant header and footer regions on the body and chapter page layouts.",
            "Confirm which variables or text fields should appear on first, odd, and even pages.",
            "Test page numbering format and chapter/title truncation with long content.",
        ],
        "relevant_settings": [
            "Header/footer region content",
            "Page numbering format",
            "First/odd/even page variants",
            "Variable or metadata insertion points",
        ],
        "xml_or_css_snippets": [],
        "common_mistakes": [
            "Updating one page layout but forgetting that chapter or front-matter layouts have their own header/footer definitions",
            "Using overly long running header content that collides with page numbers",
        ],
    },
    "tables": {
        "matched_terms": ["table", "tables", "cell", "column", "row", "thead", "tbody"],
        "short_answer": (
            "Handle table readability with Native PDF table styles and column rules, then verify that wide tables still fit the chosen page layout."
        ),
        "recommended_actions": [
            "Review the table style set used by body topics and reference topics.",
            "Test header row styling, cell padding, borders, and overflow behavior.",
            "Validate wide tables against the actual page size and margins used by the target layout.",
        ],
        "relevant_settings": [
            "Header-row emphasis",
            "Cell padding and border styling",
            "Column width behavior",
            "Landscape or alternate page layouts for wide tables",
        ],
        "xml_or_css_snippets": [],
        "common_mistakes": [
            "Trying to fix a wide table only with font-size reduction instead of considering a better page layout",
            "Ignoring header-row contrast and ending up with unreadable dense tables",
        ],
    },
    "metadata_variables": {
        "matched_terms": ["metadata", "variable", "variables", "map metadata", "book metadata"],
        "short_answer": (
            "Use Native PDF variables and metadata bindings for repeated document-level values such as title, product, version, or chapter context."
        ),
        "recommended_actions": [
            "Identify which metadata fields should appear in cover pages, headers, or footers.",
            "Bind those values through the Native PDF variable or template metadata mechanism.",
            "Test missing metadata cases so fallback text or empty regions behave acceptably.",
        ],
        "relevant_settings": [
            "Available metadata fields",
            "Variable placeholders in the template",
            "Fallback behavior for missing metadata",
        ],
        "xml_or_css_snippets": [],
        "common_mistakes": [
            "Hard-coding document metadata in the template when the values should come from the map or topic metadata",
            "Not testing what happens when optional metadata is blank",
        ],
    },
    "output_presets": {
        "matched_terms": ["output preset", "preset", "native pdf template", "pdf generation", "publish"],
        "short_answer": (
            "Start with the output preset because it decides which Native PDF template and generation options are actually used during publishing."
        ),
        "recommended_actions": [
            "Confirm the output preset points to the intended Native PDF template.",
            "Review preset-level generation options before debugging the template itself.",
            "Use one known-good preset as the baseline before cloning and modifying new variants.",
        ],
        "relevant_settings": [
            "Template selection in the output preset",
            "Preset-level publish and output options",
            "Variant-specific preset naming and ownership",
        ],
        "xml_or_css_snippets": [],
        "common_mistakes": [
            "Editing a template while the output preset still references a different template",
            "Changing multiple presets at once and losing track of which one produced the PDF under test",
        ],
    },
    "css_styling": {
        "matched_terms": ["css", "stylesheet", "style", "styling", "font", "color"],
        "short_answer": (
            "Keep the stylesheet focused on presentation rules and use the page layout for page geometry and region placement."
        ),
        "recommended_actions": [
            "Adjust typography, spacing, color, and inline element presentation in the stylesheet layer.",
            "Keep page size, margins, and header/footer structure in the page layout layer.",
            "Test one style override at a time against a fixed output preset.",
        ],
        "relevant_settings": [
            "Type scale and font mapping",
            "Color and emphasis styles",
            "Spacing and block styling",
            "Inline code, UI control, and note styling",
        ],
        "xml_or_css_snippets": [],
        "common_mistakes": [
            "Trying to solve page-region issues in CSS that should live in the page layout",
            "Stacking multiple stylesheet overrides without isolating which rule changed the output",
        ],
    },
    "general": {
        "matched_terms": [],
        "short_answer": (
            "For Native PDF issues, start by identifying the right layer: output preset, page layout, stylesheet, or metadata/variables. Then test changes in that layer against a single known output preset."
        ),
        "recommended_actions": [
            "Confirm the output preset and template pair that is actually generating the PDF.",
            "Classify the issue as page layout, visual styling, TOC/bookmarks, metadata, or table behavior.",
            "Change one layer at a time and retest with the same sample map.",
        ],
        "relevant_settings": [
            "Output preset selection",
            "Native PDF template",
            "Page layout",
            "Stylesheet rules",
        ],
        "xml_or_css_snippets": [],
        "common_mistakes": [
            "Troubleshooting the wrong layer first",
            "Testing with inconsistent output presets or template versions",
        ],
    },
}


def _detect_native_pdf_area(query: str, config_type: str) -> str:
    text = " ".join(((query or ""), (config_type or ""))).lower()
    for area in (
        "watermark",
        "toc",
        "headers_footers",
        "tables",
        "metadata_variables",
        "page_layout",
        "output_presets",
        "css_styling",
    ):
        terms = _NATIVE_PDF_GUIDANCE[area]["matched_terms"]
        if any(term in text for term in terms):
            return area
    return "general"


async def execute_generate_dita(
    text: str,
    instructions: str | None = None,
    bundle_contract: dict[str, Any] | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
    user_id: str = "chat-user",
    tenant_id: str = "kone",
) -> dict[str, Any]:
    """
    Generate DITA from text or natural language.
    Returns dict with jira_id, run_id, download_url, scenarios.
    When run_id is provided, progress is written to _generate_progress for streaming.
    When session_id is provided, last generation is stored for conversational refinement.
    """
    run_id = run_id or str(uuid4())
    source_text = (text or "").strip()
    if not source_text:
        return {"error": "Text is required for DITA generation"}

    update_generate_progress(run_id, status="running", stage="starting", jira_id=f"TEXT-{run_id[:8]}")

    try:
        result = await run_generate_from_text(
            text=source_text,
            instructions=instructions,
            bundle_contract=bundle_contract,
            run_id=run_id,
            request=None,
            user_id=user_id,
            tenant_id=tenant_id,
            skip_rag_check=True,
            progress_run_id=run_id,
        )
        jira_id = result.get("jira_id", f"TEXT-{run_id[:8]}")
        run_id = result.get("run_id", run_id)
        download_url = f"/api/v1/ai/bundle/{jira_id}/{run_id}/download"
        out = {
            "jira_id": jira_id,
            "run_id": run_id,
            "download_url": download_url,
            "scenarios": result.get("scenarios", []),
            "message": "DITA bundle generated. User can download from the link.",
            "bundle_summary": result.get("bundle_summary"),
            "artifact_counts": result.get("artifact_counts"),
            "representative_files": result.get("representative_files"),
            "generation_contract": result.get("generation_contract") or bundle_contract,
            "contract_summary": result.get("contract_summary"),
            "contract_compliance": result.get("contract_compliance"),
        }
        rw = result.get("resolution_warning")
        if rw:
            out["resolution_warning"] = rw
        if session_id:
            from app.services.chat_service import set_session_last_generation
            text_for_session = result.get("resolved_source_text") or source_text
            set_session_last_generation(
                session_id,
                text=text_for_session,
                instructions=instructions,
                jira_id=jira_id,
                run_id=run_id,
                download_url=download_url,
            )
        return out
    except Exception as e:
        logger.warning_structured(
            "generate_dita tool failed",
            extra_fields={"error": str(e)},
        )
        return {"error": str(e)}


async def execute_create_job(
    recipe_type: str,
    config: dict | None = None,
    user_id: str = "chat-user",
) -> dict[str, Any]:
    """
    Create a dataset generation job.
    recipe_type must be in allowlist. config is optional overrides.
    """
    recipe_type = (recipe_type or "").strip().lower()
    if not recipe_type:
        return {"error": "recipe_type is required"}
    if recipe_type not in RECIPE_TYPE_ALLOWLIST:
        return {
            "error": f"recipe_type must be one of: {', '.join(sorted(RECIPE_TYPE_ALLOWLIST))}",
        }

    # Build minimal config from recipe type
    base_config: dict = {
        "name": f"Chat Job - {recipe_type}",
        "seed": "chat-seed",
        "root_folder": "/content/dam/dataset-studio",
        "windows_safe_filenames": True,
        "recipes": [{"type": recipe_type}],
    }
    if recipe_type == "task_topics":
        base_config["recipes"] = [{
            "type": "task_topics",
            "topic_count": 10,
            "steps_per_task": 5,
            "include_prereq": True,
            "include_result": True,
            "include_map": True,
            "pretty_print": True,
        }]
    elif recipe_type == "concept_topics":
        base_config["recipes"] = [{
            "type": "concept_topics",
            "topic_count": 10,
            "sections_per_concept": 3,
            "include_map": True,
            "pretty_print": True,
        }]
    elif recipe_type == "syntax_diagram_reference":
        base_config["recipes"] = [{
            "type": "syntax_diagram_reference",
            "topic_count": 10,
            "include_map": True,
            "pretty_print": True,
        }]
    elif recipe_type == "glossary_pack":
        base_config["recipes"] = [{
            "type": "glossary_pack",
            "entry_count": 20,
            "include_acronyms": True,
            "include_map": True,
            "pretty_print": True,
        }]
    elif recipe_type == "bulk_dita_map_topics":
        base_config["recipes"] = [{
            "type": "bulk_dita_map_topics",
            "topic_count": 100,
            "include_readme": True,
            "pretty_print": True,
        }]
    else:
        base_config["recipes"] = [{"type": recipe_type, "pretty_print": True}]

    if config and isinstance(config, dict):
        if "recipes" in config and config["recipes"]:
            base_config["recipes"] = config["recipes"]
        for k, v in config.items():
            if k != "recipes" and v is not None:
                base_config[k] = v

    try:
        enforce_concurrent_job_limit(user_id)
        job = create_dataset_job_record(
            base_config,
            user_id=user_id,
            name=str(base_config.get("name") or "Chat Job"),
        )
        job_id = str(job.get("id") or "").strip()
        if not job_id:
            raise RuntimeError("Dataset job creation did not return a job id")
        start_dataset_job_in_background(job_id, base_config)
        urls = build_dataset_job_urls(job_id)
        return {
            "job_id": job_id,
            "name": str(job.get("name") or base_config.get("name") or "Chat Job"),
            "recipe_type": recipe_type,
            "status": str(job.get("status") or "pending"),
            **urls,
            "message": "Dataset generation started. The in-chat status card will update when the ZIP is ready.",
        }
    except Exception as e:
        logger.warning_structured(
            "create_job tool failed",
            extra_fields={"recipe_type": recipe_type, "error": str(e)},
        )
        return {"error": str(e)}


async def execute_search_jira_issues(
    query: str,
    *,
    tenant_id: str = "kone",
) -> dict[str, Any]:
    try:
        return search_related_jira_issues(query, tenant_id=tenant_id)
    except Exception as e:
        logger.warning_structured(
            "search_jira_issues tool failed",
            extra_fields={"query": query, "tenant_id": tenant_id, "error": str(e)},
        )
        return {"query": query, "issues": [], "source": "unavailable", "message": str(e), "error": str(e)}


async def execute_lookup_dita_spec(
    query: str,
    elements: list[str] | None = None,
) -> dict[str, Any]:
    """Look up DITA spec details for elements/attributes using seed + graph knowledge."""
    from app.services.dita_knowledge_retriever import (
        retrieve_dita_knowledge,
        retrieve_dita_graph_knowledge,
    )

    try:
        chunks = retrieve_dita_knowledge(query, k=5)
        graph_text = ""
        if elements:
            graph_text = retrieve_dita_graph_knowledge(elements=elements)
        elif query:
            graph_text = retrieve_dita_graph_knowledge(element_hint=query)
        return {
            "spec_chunks": [
                {
                    "element_name": c.get("element_name"),
                    "text_content": (c.get("text_content") or "")[:800],
                }
                for c in chunks[:5]
            ],
            "graph_knowledge": graph_text,
            "query": query,
        }
    except Exception as e:
        logger.warning_structured(
            "lookup_dita_spec tool failed",
            extra_fields={"query": query, "error": str(e)},
        )
        return {"error": str(e)}


_REVIEW_LABEL_RULE_IDS = {
    "XML declaration present": "validation_xml_declaration",
    "Required DTD header present": "validation_dtd_header",
    "shortdesc present": "missing_shortdesc",
    "xml:lang present": "validation_xml_lang",
    "taskbody present": "validation_taskbody",
    "steps present": "validation_steps",
    "cmd in steps": "validation_cmd",
    "conbody present": "validation_conbody",
    "refbody present": "validation_refbody",
    "body present": "validation_body",
    "glossterm present": "validation_glossterm",
    "glossdef present": "validation_glossdef",
    "map title present": "validation_map_title",
    "map structure present": "validation_map_structure",
}

_REVIEW_LABEL_DISPLAY = {
    "XML declaration present": "XML declaration",
    "Required DTD header present": "Required DTD header",
    "shortdesc present": "shortdesc",
    "xml:lang present": "xml:lang",
    "taskbody present": "taskbody",
    "steps present": "steps",
    "cmd in steps": "cmd elements in steps",
    "conbody present": "conbody",
    "refbody present": "refbody",
    "body present": "body",
    "glossterm present": "glossterm",
    "glossdef present": "glossdef",
    "map title present": "map title",
    "map structure present": "map references or branches",
}

_REVIEW_RECOMMENDATIONS = {
    "XML declaration present": 'Add `<?xml version="1.0" encoding="UTF-8"?>` at the top of the file.',
    "Required DTD header present": "Add the correct DITA DOCTYPE immediately after the XML declaration.",
    "shortdesc present": "Add a concise, user-facing `<shortdesc>` immediately after the title.",
    "xml:lang present": 'Add `xml:lang="en-US"` or the correct locale on the root element.',
    "taskbody present": "Wrap procedural content in `<taskbody>`.",
    "steps present": "Add ordered `<steps>` with one clear action per step.",
    "cmd in steps": "Ensure each `<step>` contains a `<cmd>` element.",
    "conbody present": "Add `<conbody>` with the conceptual explanation.",
    "refbody present": "Add `<refbody>` with structured reference sections.",
    "body present": "Add `<body>` with the main topic content.",
    "glossterm present": "Add `<glossterm>` to name the glossary term.",
    "glossdef present": "Add `<glossdef>` to define the glossary term.",
    "map title present": "Add a concise `<title>` as the first map child.",
    "map structure present": "Add real map children such as `<topicref>`, `<keydef>`, `<mapref>`, `<topichead>`, `<topicgroup>`, or `<reltable>`.",
}


def _review_display_label(label: str) -> str:
    cleaned = " ".join(str(label or "").split()).strip()
    if cleaned in _REVIEW_LABEL_DISPLAY:
        return _REVIEW_LABEL_DISPLAY[cleaned]
    return cleaned.removesuffix(" present").strip() or "DITA check"


def _normalize_review_validation_checks(
    validation: list[dict[str, Any]],
    dita_type: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    map_like = str(dita_type or "").strip().lower() in {"map", "bookmap"}
    for raw in validation or []:
        if not isinstance(raw, dict):
            continue
        label = " ".join(str(raw.get("label") or raw.get("rule_id") or raw.get("message") or "").split()).strip()
        if not label:
            continue
        passing = bool(raw.get("passing"))
        rule_id = str(raw.get("rule_id") or _REVIEW_LABEL_RULE_IDS.get(label) or "").strip()
        display = _review_display_label(label)
        if map_like and label == "body present":
            item = {
                "label": display,
                "rule_id": rule_id or "validation_body",
                "severity": "not_applicable",
                "passing": True,
                "message": "DITA maps do not use a standalone `<body>`; they organize deliverables with map children.",
                "recommendation": "Use map constructs such as `<topicref>`, `<keydef>`, `<mapref>`, or `<reltable>` instead of `<body>`.",
                "impact": "Prevents topic-only guidance from being applied to map files.",
            }
        elif passing:
            item = {
                "label": display,
                "rule_id": rule_id,
                "severity": "pass",
                "passing": True,
                "message": f"{display} is present.",
                "recommendation": "",
                "impact": "",
            }
        else:
            item = {
                "label": display,
                "rule_id": rule_id,
                "severity": "error",
                "passing": False,
                "message": str(raw.get("message") or f"{display} is missing.").strip(),
                "recommendation": _REVIEW_RECOMMENDATIONS.get(label, "Update the XML so this validation check passes."),
                "impact": "This lowers structure/readiness score and can affect import, validation, or publishing quality.",
            }
            issues.append(item)
        normalized.append(item)
    return normalized, issues


def _normalize_review_suggestions(suggestions_report: dict[str, Any]) -> list[dict[str, Any]]:
    raw_suggestions = suggestions_report.get("suggestions") if isinstance(suggestions_report, dict) else []
    normalized: list[dict[str, Any]] = []
    for raw in raw_suggestions or []:
        if not isinstance(raw, dict):
            continue
        title = " ".join(str(raw.get("title") or raw.get("rule_id") or "Improve DITA quality").split()).strip()
        why = " ".join(str(raw.get("why") or "").split()).strip()
        recommendation = " ".join(str(raw.get("after") or raw.get("fix_prompt") or "").split()).strip()
        if not title and not why and not recommendation:
            continue
        normalized.append(
            {
                "title": title,
                "severity": str(raw.get("severity") or "info").strip() or "info",
                "section": str(raw.get("section") or "").strip(),
                "description": why,
                "recommendation": recommendation,
                "impact": str(raw.get("impact") or "").strip(),
                "rule_id": str(raw.get("rule_id") or "").strip(),
                "fix_type": str(raw.get("fix_type") or "").strip(),
                "confidence": raw.get("confidence"),
            }
        )
    return normalized


def _build_review_priority_fixes(
    normalized_suggestions: list[dict[str, Any]],
    normalized_issues: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    priority: list[dict[str, Any]] = []
    seen: set[str] = set()
    severity_rank = {"error": 0, "warning": 1, "info": 2}
    for suggestion in sorted(
        normalized_suggestions,
        key=lambda item: severity_rank.get(str(item.get("severity") or "info"), 9),
    ):
        key = str(suggestion.get("rule_id") or suggestion.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        priority.append(
            {
                "title": suggestion.get("title"),
                "severity": suggestion.get("severity"),
                "reason": suggestion.get("description"),
                "recommendation": suggestion.get("recommendation"),
                "impact": suggestion.get("impact"),
                "rule_id": suggestion.get("rule_id"),
            }
        )
        if len(priority) >= limit:
            return priority
    for issue in normalized_issues:
        key = str(issue.get("rule_id") or issue.get("label") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        priority.append(
            {
                "title": issue.get("message"),
                "severity": issue.get("severity"),
                "reason": issue.get("impact"),
                "recommendation": issue.get("recommendation"),
                "impact": issue.get("impact"),
                "rule_id": issue.get("rule_id"),
            }
        )
        if len(priority) >= limit:
            break
    return priority


_REVIEW_LARGE_XML_CHARS = 60_000
_REVIEW_LARGE_ELEMENT_COUNT = 220


def _build_review_document_profile(xml: str) -> dict[str, Any]:
    raw = xml or ""
    without_declaration = re.sub(r"<\?xml[^>]*\?>", "", raw, flags=re.IGNORECASE).strip()
    root_match = re.search(r"<([A-Za-z_][A-Za-z0-9_.:-]*)\b", without_declaration)
    root_element = root_match.group(1).split(":")[-1].lower() if root_match else ""
    element_names = [
        match.group(1).split(":")[-1].lower()
        for match in re.finditer(r"<(?![!?/])([A-Za-z_][A-Za-z0-9_.:-]*)\b", raw)
    ]
    tag_counts: dict[str, int] = {}
    for name in element_names:
        tag_counts[name] = tag_counts.get(name, 0) + 1
    top_tags = sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    char_count = len(raw)
    line_count = len(raw.splitlines()) or 1
    element_count = len(element_names)
    map_like = root_element in {"map", "bookmap"}
    large_document = char_count > _REVIEW_LARGE_XML_CHARS or element_count > _REVIEW_LARGE_ELEMENT_COUNT
    return {
        "root_element": root_element or "unknown",
        "xml_char_count": char_count,
        "line_count": line_count,
        "element_count": element_count,
        "large_document": large_document,
        "map_like": map_like,
        "topicref_count": tag_counts.get("topicref", 0),
        "keydef_count": tag_counts.get("keydef", 0),
        "xref_count": tag_counts.get("xref", 0),
        "conref_count": len(re.findall(r"\bconref\s*=", raw, re.IGNORECASE)),
        "keyref_count": len(re.findall(r"\bkeyref\s*=", raw, re.IGNORECASE)),
        "top_tags": [{"tag": tag, "count": count} for tag, count in top_tags],
    }


def _review_scope_from_profile(profile: dict[str, Any], dita_type: str) -> tuple[str, str, list[str]]:
    root = str(profile.get("root_element") or dita_type or "DITA").strip()
    large_document = bool(profile.get("large_document"))
    map_like = bool(profile.get("map_like")) or str(dita_type or "").strip().lower() in {"map", "bookmap"}
    if large_document:
        scope = "large_document_structural_scan"
        explanation = (
            "Large DITA review: the tool scored the full XML for structural readiness and shows the most important "
            "findings first rather than repeating every similar issue."
        )
    else:
        scope = "full_structural_scan"
        explanation = "Full DITA review: the tool checked document structure, required containers, metadata, and quality signals."
    warnings: list[str] = []
    if large_document:
        warnings.append(
            f"Large {root} detected ({profile.get('element_count')} elements, {profile.get('line_count')} lines); findings are prioritized so the card stays readable."
        )
    if map_like:
        warnings.append(
            "Map review mode is active: topic-only checks such as <body>, <taskbody>, and <shortdesc> are not treated as map requirements."
        )
    return scope, explanation, warnings


def _score_band(score: Any) -> str:
    try:
        numeric = int(score)
    except Exception:
        return "reviewed"
    if numeric >= 80:
        return "strong"
    if numeric >= 60:
        return "usable but needs cleanup"
    return "not production-ready yet"


def _build_review_text_fields(
    *,
    dita_type: str,
    quality_score: Any,
    validation_issues: list[dict[str, Any]],
    normalized_suggestions: list[dict[str, Any]],
    priority_fixes: list[dict[str, Any]],
    document_profile: dict[str, Any] | None = None,
    review_scope: str = "",
) -> dict[str, str]:
    score_text = f"{quality_score}/100" if quality_score is not None else "not scored"
    issue_count = len(validation_issues)
    suggestion_count = len(normalized_suggestions)
    band = _score_band(quality_score)
    type_label = dita_type or "DITA"
    large_prefix = "large " if document_profile and document_profile.get("large_document") else ""
    scope_note = ""
    if review_scope == "large_document_structural_scan":
        scope_note = " Findings are prioritized for a large document so repeated low-value details do not hide the top fixes."
    if issue_count:
        summary = (
            f"Reviewed this {large_prefix}DITA {type_label} and scored it {score_text}. "
            f"It is {band}; fix the {issue_count} blocking validation issue"
            f"{'s' if issue_count != 1 else ''} first, then work through the "
            f"{suggestion_count} quality suggestion{'s' if suggestion_count != 1 else ''}.{scope_note}"
        )
    else:
        summary = (
            f"Reviewed this {large_prefix}DITA {type_label} and scored it {score_text}. "
            f"No blocking validation issues were found; the remaining work is quality/readiness improvement.{scope_note}"
        )
    if priority_fixes:
        fix_titles = "; ".join(str(item.get("title") or item.get("recommendation") or "").strip() for item in priority_fixes[:3])
        guidance = f"Fastest score lift: {fix_titles}."
    else:
        guidance = "No immediate structural fixes were identified from the available review checks."
    return {
        "summary": summary,
        "review_summary": summary,
        "score_improvement_guidance": guidance,
    }


async def execute_review_dita_xml(
    xml: str,
    context: str | None = None,
    tenant_id: str = "kone",
) -> dict[str, Any]:
    """Validate and review DITA XML — returns quality score, validation issues, suggestions."""
    from app.services.smart_suggestions_service import build_review_snapshot

    if not xml or not xml.strip():
        return {"error": "XML content is required"}
    issue = {"issue_key": "REVIEW", "summary": context or "User-provided XML for review"}
    document_profile = _build_review_document_profile(xml)
    try:
        snapshot = await build_review_snapshot(xml=xml, issue=issue, tenant_id=tenant_id)
        dita_type = str(snapshot.get("dita_type") or "").strip()
        validation = (snapshot.get("validation") or [])[:20]
        suggestions_report = snapshot.get("suggestions_report", {}) or {}
        validation_checks, normalized_issues = _normalize_review_validation_checks(validation, dita_type)
        normalized_suggestions = _normalize_review_suggestions(suggestions_report)
        priority_fixes = _build_review_priority_fixes(normalized_suggestions, normalized_issues)
        review_scope, review_scope_explanation, review_warnings = _review_scope_from_profile(document_profile, dita_type)
        text_fields = _build_review_text_fields(
            dita_type=dita_type,
            quality_score=snapshot.get("quality_score"),
            validation_issues=normalized_issues,
            normalized_suggestions=normalized_suggestions,
            priority_fixes=priority_fixes,
            document_profile=document_profile,
            review_scope=review_scope,
        )
        return {
            **text_fields,
            "dita_type": dita_type,
            "quality_score": snapshot.get("quality_score"),
            "quality_breakdown": snapshot.get("quality_breakdown"),
            "validation_issues": validation,
            "validation_checks": validation_checks,
            "normalized_validation_issues": normalized_issues,
            "suggestions": suggestions_report,
            "normalized_suggestions": normalized_suggestions,
            "priority_fixes": priority_fixes,
            "document_profile": document_profile,
            "review_scope": review_scope,
            "review_scope_explanation": review_scope_explanation,
            "warnings": review_warnings,
            "review_counts": {
                "validation_issues": len(normalized_issues),
                "suggestions": len(normalized_suggestions),
                "errors": int((suggestions_report or {}).get("errors") or 0),
                "warnings": int((suggestions_report or {}).get("warnings") or 0),
            },
            "sources_used": snapshot.get("sources_used", []),
        }
    except Exception as e:
        logger.warning_structured(
            "review_dita_xml tool failed",
            extra_fields={"error": str(e)},
        )
        return {"error": str(e)}


async def execute_find_recipes(
    query: str,
    k: int = 5,
) -> dict[str, Any]:
    """Search available dataset recipes by intent/description."""
    from app.services.recipe_retriever import retrieve_recipes

    k = min(max(k, 1), 10)
    try:
        results = await retrieve_recipes(query, k=k)
        recipes = []
        for r in results:
            spec = r.get("spec")
            recipes.append({
                "recipe_id": r.get("recipe_id"),
                "score": round(r.get("score", 0), 2),
                "rationale": r.get("rationale", ""),
                "description": getattr(spec, "description", "") if spec else "",
            })
        return {"query": query, "recipes": recipes, "count": len(recipes)}
    except Exception as e:
        logger.warning_structured(
            "find_recipes tool failed",
            extra_fields={"query": query, "error": str(e)},
        )
        return {"error": str(e)}


async def execute_get_job_status(job_id: str) -> dict[str, Any]:
    """Check status of a dataset generation job by ID."""
    from app.services.dataset_job_service import get_dataset_job_summary, build_dataset_job_urls

    if not job_id or not job_id.strip():
        return {"error": "job_id is required"}
    job_id = job_id.strip()
    try:
        summary = get_dataset_job_summary(job_id)
        if not summary:
            return {"error": f"No job found with ID: {job_id}"}
        urls = build_dataset_job_urls(job_id)
        return {**summary, **urls}
    except Exception as e:
        logger.warning_structured(
            "get_job_status tool failed",
            extra_fields={"job_id": job_id, "error": str(e)},
        )
        return {"error": str(e)}


async def execute_lookup_aem_guides(query: str, k: int = 5) -> dict[str, Any]:
    """Search AEM Guides Experience League documentation."""
    from app.services.doc_retriever_service import retrieve_relevant_docs_with_diagnostics
    from app.services.tavily_search_service import is_chat_tavily_enabled, tavily_search_sync

    k = min(max(k, 1), 10)
    try:
        live_results: list[dict[str, Any]] = []
        live_search: dict[str, Any] = {
            "provider": "tavily",
            "enabled": bool(is_chat_tavily_enabled()),
            "strategy": "experience_league_first",
            "result_count": 0,
        }
        if live_search["enabled"]:
            payload = await asyncio.to_thread(
                lambda: tavily_search_sync(query, category="aem_guides", max_results=k)
            )
            if isinstance(payload, dict):
                for item in (payload.get("results") or [])[:k]:
                    if not isinstance(item, dict):
                        continue
                    snippet = " ".join(str(item.get("content") or "").split()).strip()
                    url = str(item.get("url") or "").strip()
                    title = str(item.get("title") or url or "Experience League result").strip()
                    if not snippet:
                        continue
                    live_results.append(
                        {
                            "url": url,
                            "title": title,
                            "snippet": snippet[:800],
                            "source": "tavily",
                        }
                    )
                live_answer = " ".join(str(payload.get("answer") or "").split()).strip()
                if live_answer:
                    live_search["answer"] = live_answer[:1000]
            live_search["result_count"] = len(live_results)

        retrieval = retrieve_relevant_docs_with_diagnostics(
            query,
            k=k,
            allowed_host_suffixes=("experienceleague.adobe.com",),
        )
        local_results = [
            {
                "url": d.get("url", ""),
                "title": d.get("title", ""),
                "snippet": (d.get("snippet") or "")[:800],
                "source": "local_rag",
            }
            for d in (retrieval.get("results") or [])
        ]
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in [*live_results, *local_results]:
            key = str(item.get("url") or item.get("title") or item.get("snippet") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            results.append(item)
            if len(results) >= k:
                break

        summary = ""
        if results:
            top_snippet = " ".join(str(results[0].get("snippet") or "").split()).strip()
            if top_snippet:
                summary = top_snippet
        elif retrieval.get("error"):
            summary = str(retrieval.get("error") or "").strip()
        return {
            "query": query,
            "summary": summary,
            "results": results,
            "count": len(results),
            "retrieval_mode": str(retrieval.get("retrieval_mode") or "none"),
            "semantic_required": bool(retrieval.get("semantic_required")),
            "embedding": retrieval.get("embedding") or {},
            "live_search": live_search,
            "warnings": list(retrieval.get("warnings") or []),
            **({"error": str(retrieval.get("error") or "").strip()} if retrieval.get("error") else {}),
        }
    except Exception as e:
        logger.warning_structured(
            "lookup_aem_guides tool failed",
            extra_fields={"query": query, "error": str(e)},
        )
        return {"error": str(e)}


async def execute_search_tenant_knowledge(
    query: str,
    tenant_id: str = "kone",
    k: int = 5,
) -> dict[str, Any]:
    """Search tenant's uploaded knowledge base (style guides, product docs)."""
    from app.services.tenant_service import retrieve_tenant_context, list_tenant_knowledge_snippets
    from app.services.doc_pdf_index_service import list_indexed_docs

    k = min(max(k, 1), 8)
    try:
        indexed = list_indexed_docs(tenant_id)
        snippets = list_tenant_knowledge_snippets(tenant_id)
        if not indexed and not snippets:
            return {
                "query": query, "results": [], "count": 0,
                "indexed_doc_count": 0,
                "snippet_count": 0,
                "message": "No documents or knowledge snippets indexed for this tenant yet.",
            }
        results_raw = retrieve_tenant_context(query, tenant_id=tenant_id, k=k)
        results = [
            {
                "content": (r.get("content") or "")[:800],
                "label": (r.get("metadata") or {}).get("label", ""),
                "doc_type": (r.get("metadata") or {}).get("doc_type", ""),
                "snippet_type": (r.get("metadata") or {}).get("snippet_type", ""),
            }
            for r in (results_raw or [])
        ]
        return {
            "query": query, "results": results, "count": len(results),
            "indexed_doc_count": len(indexed),
            "snippet_count": len(snippets),
        }
    except Exception as e:
        logger.warning_structured(
            "search_tenant_knowledge tool failed",
            extra_fields={"query": query, "tenant_id": tenant_id, "error": str(e)},
        )
        return {"error": str(e)}


async def execute_lookup_output_preset(
    query: str,
    output_type: str | None = None,
    k: int = 5,
) -> dict[str, Any]:
    """Look up AEM output preset configuration and publishing details."""
    from app.services.dita_knowledge_retriever import retrieve_dita_knowledge
    from app.services.doc_retriever_service import retrieve_relevant_docs

    k = min(max(k, 1), 10)
    enriched = f"{output_type.replace('_', ' ')}: {query}" if output_type else query
    try:
        seed_chunks = retrieve_dita_knowledge(enriched, k=k)
        doc_chunks = retrieve_relevant_docs(
            enriched,
            k=3,
            allowed_host_suffixes=("experienceleague.adobe.com",),
        )
        seed_results = [
            {
                "element_name": c.get("element_name"),
                "text_content": (c.get("text_content") or "")[:800],
            }
            for c in (seed_chunks or [])
        ]
        doc_results = [
            {
                "url": d.get("url", ""),
                "title": d.get("title", ""),
                "snippet": (d.get("snippet") or "")[:500],
            }
            for d in (doc_chunks or [])
        ]
        return {
            "query": query, "output_type": output_type,
            "seed_results": seed_results, "doc_results": doc_results,
        }
    except Exception as e:
        logger.warning_structured(
            "lookup_output_preset tool failed",
            extra_fields={"query": query, "error": str(e)},
        )
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Phase 14 tools: list_jobs, fix_dita_xml, lookup_dita_attribute,
#                 list_indexed_pdfs, generate_native_pdf_config, browse_dataset
# ---------------------------------------------------------------------------


async def execute_list_jobs(
    status: str | None = None,
    limit: int = 10,
    user_id: str = "chat-user",
) -> dict[str, Any]:
    """List recent dataset generation jobs for the current user."""
    from app.db.session import SessionLocal
    from app.jobs.crud import get_user_jobs

    limit = min(max(limit, 1), 25)
    try:
        session = SessionLocal()
        try:
            jobs, total = get_user_jobs(
                session, user_id=user_id, status=status, limit=limit,
            )
            items = []
            for j in jobs:
                items.append({
                    "id": j.id,
                    "name": j.name,
                    "status": j.status,
                    "progress_percent": j.progress_percent,
                    "files_generated": j.files_generated,
                    "total_files_estimated": j.total_files_estimated,
                    "current_stage": j.current_stage,
                    "created_at": j.created_at.isoformat() if j.created_at else None,
                    "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                })
            return {"jobs": items, "total_count": total, "limit": limit}
        finally:
            session.close()
    except Exception as e:
        logger.warning_structured(
            "list_jobs tool failed",
            extra_fields={"error": str(e)},
        )
        return {"error": str(e)}


async def execute_fix_dita_xml(
    xml: str,
    fix_rule_id: str | None = None,
    context: str | None = None,
    tenant_id: str = "kone",
) -> dict[str, Any]:
    """Apply auto-fix to DITA XML. Optionally target a specific rule from review_dita_xml."""
    from app.services.smart_suggestions_service import apply_fix_with_review

    if not xml or not xml.strip():
        return {"error": "XML content is required"}

    suggestion: dict[str, Any] = {}
    if fix_rule_id:
        suggestion["rule_id"] = fix_rule_id
    issue = {"issue_key": "FIX", "summary": context or "Auto-fix from chat"}

    try:
        result = await apply_fix_with_review(
            xml=xml,
            suggestion=suggestion,
            issue=issue,
            tenant_id=tenant_id,
            allow_llm=True,
        )
        return {
            "fixed_xml": result.get("xml", xml),
            "changed": result.get("changed", False),
            "applied_rule_id": result.get("applied_rule_id", ""),
            "change_summary": result.get("change_summary", ""),
            "quality_score": (result.get("updated_review") or {}).get("quality_score"),
            "remaining_suggestions": result.get("suggestions_report", {}),
        }
    except Exception as e:
        logger.warning_structured(
            "fix_dita_xml tool failed",
            extra_fields={"error": str(e)},
        )
        return {"error": str(e)}


async def execute_lookup_dita_attribute(
    attribute_name: str,
) -> dict[str, Any]:
    """Look up a DITA attribute's valid values, supported elements, and combinations."""
    from app.services.dita_attribute_catalog import get_attribute_spec

    raw_query = (attribute_name or "").strip()
    if not raw_query:
        return {"error": "attribute_name is required"}
    attr_names = _extract_dita_attributes_from_query(raw_query)
    if not attr_names:
        fallback_attr = raw_query.strip().strip("`'\"?.,;:!()[]{}").lstrip("@").lower()
        if fallback_attr and fallback_attr not in _DITA_ATTRIBUTE_STOPWORDS:
            attr_names = [fallback_attr]
    try:
        specs: list[dict[str, Any]] = []
        missing_attrs: list[str] = []
        for attr in attr_names[:6]:
            spec = get_attribute_spec(attr)
            if spec is None:
                missing_attrs.append(attr)
                continue
            specs.append(
                {
                    "attribute_name": spec.attribute_name,
                    "all_valid_values": spec.all_valid_values,
                    "supported_elements": spec.supported_elements,
                    "combination_attributes": spec.combination_attributes,
                    "default_scenarios": spec.default_scenarios,
                    "usage_contexts": spec.usage_contexts,
                    "common_mistakes": spec.common_mistakes,
                    "correct_examples": spec.correct_examples,
                    "attribute_semantic_class": spec.semantic_class,
                    "attribute_syntax": spec.syntax,
                    "text_content": (spec.text_content or "")[:1200],
                    "source_url": spec.source_url,
                }
            )

        if not specs:
            attempted = ", ".join(attr_names) if attr_names else raw_query.lower()
            return {
                "error": f"Attribute '{attempted}' not found in DITA spec catalog.",
                "hint": "Try common attributes: format, scope, type, conref, conkeyref, href, keyref, audience, platform, product, props, otherprops, chunk, processing-role, linking, toc, print.",
            }

        if len(specs) == 1:
            result = dict(specs[0])
            if raw_query.lower() != result["attribute_name"]:
                result["resolved_from_query"] = raw_query
            if missing_attrs:
                result["warnings"] = [
                    f"Some attribute names in the request could not be resolved: {', '.join(missing_attrs[:4])}."
                ]
            return result

        names = [str(item["attribute_name"]).strip() for item in specs if str(item.get("attribute_name") or "").strip()]
        summary_names = ", ".join(f"`{name}`" for name in names[:4])
        if len(names) > 4:
            summary_names += ", ..."
        warnings: list[str] = []
        if missing_attrs:
            warnings.append(
                f"Some attribute names in the request could not be resolved: {', '.join(missing_attrs[:4])}."
            )
        return {
            "attribute_names": names,
            "attributes": specs,
            "resolved_from_query": raw_query,
            "summary": f"Retrieved DITA attribute guidance for {summary_names}.",
            "warnings": warnings,
        }
    except Exception as e:
        logger.warning_structured(
            "lookup_dita_attribute tool failed",
            extra_fields={"attribute_name": raw_query, "error": str(e)},
        )
        return {"error": str(e)}


async def execute_list_indexed_pdfs(
    tenant_id: str = "kone",
) -> dict[str, Any]:
    """List all PDF documents indexed in the tenant's knowledge base."""
    from app.services.doc_pdf_index_service import list_indexed_docs

    try:
        docs = list_indexed_docs(tenant_id)
        items = [
            {
                "filename": d.get("filename", ""),
                "label": d.get("label", ""),
                "doc_type": d.get("doc_type", ""),
                "chunks": d.get("chunks", 0),
                "pages": d.get("pages", 0),
                "indexed_at": d.get("indexed_at", ""),
                "file_hash": d.get("file_hash", ""),
            }
            for d in (docs or [])
        ]
        return {
            "tenant_id": tenant_id,
            "documents": items,
            "count": len(items),
            "message": (
                f"{len(items)} PDF document{'s' if len(items) != 1 else ''} indexed."
                if items else
                "No PDFs indexed. Upload via the Knowledge Base page or /api/v1/pdf/index-pdf."
            ),
        }
    except Exception as e:
        logger.warning_structured(
            "list_indexed_pdfs tool failed",
            extra_fields={"tenant_id": tenant_id, "error": str(e)},
        )
        return {"error": str(e)}


async def execute_generate_native_pdf_config(
    query: str,
    config_type: str = "template",
) -> dict[str, Any]:
    """Generate Native PDF output preset snippets and template guidance for AEM Guides.

    Combines DITA knowledge + AEM Guides docs to produce actionable configuration
    for Native PDF templates, page layouts, stylesheets, headers/footers, TOC, etc.
    """
    from app.services.dita_knowledge_retriever import retrieve_dita_knowledge
    from app.services.doc_retriever_service import retrieve_relevant_docs

    enriched = f"Native PDF {config_type}: {query}"
    config_area = _detect_native_pdf_area(query, config_type)
    guidance = _NATIVE_PDF_GUIDANCE.get(config_area, _NATIVE_PDF_GUIDANCE["general"])
    try:
        seed_chunks = retrieve_dita_knowledge(enriched, k=5)
        doc_chunks = retrieve_relevant_docs(enriched, k=5)

        seed_results = [
            {
                "element_name": c.get("element_name"),
                "text_content": (c.get("text_content") or "")[:800],
            }
            for c in (seed_chunks or [])
        ]
        doc_results = [
            {
                "url": d.get("url", ""),
                "title": d.get("title", ""),
                "snippet": (d.get("snippet") or "")[:600],
            }
            for d in (doc_chunks or [])
        ]

        evidence = [
            {
                "title": item["title"],
                "url": item["url"],
                "snippet": item["snippet"],
            }
            for item in doc_results
            if item.get("title") or item.get("url")
        ][:5]
        seed_signals = [
            str(item.get("element_name") or "").strip()
            for item in seed_results
            if str(item.get("element_name") or "").strip()
        ][:6]
        matched_keywords = [
            term for term in guidance.get("matched_terms", []) if term in f"{query} {config_type}".lower()
        ]

        return {
            "query": query,
            "config_type": config_type,
            "config_area": config_area,
            "short_answer": guidance.get("short_answer", ""),
            "recommended_actions": list(guidance.get("recommended_actions", []))[:6],
            "relevant_settings": list(guidance.get("relevant_settings", []))[:6],
            "xml_or_css_snippets": list(guidance.get("xml_or_css_snippets", []))[:3],
            "common_mistakes": list(guidance.get("common_mistakes", []))[:6],
            "matched_keywords": matched_keywords,
            "seed_signals": seed_signals,
            "evidence": evidence,
            "warnings": [] if evidence else [
                "No Native PDF documentation hits were retrieved for this query, so the answer is based on the built-in guidance playbook."
            ],
            "seed_results": seed_results,
            "doc_results": doc_results,
        }
    except Exception as e:
        logger.warning_structured(
            "generate_native_pdf_config tool failed",
            extra_fields={"query": query, "error": str(e)},
        )
        return {"error": str(e)}


async def execute_browse_dataset(
    job_id: str,
    file_path: str | None = None,
) -> dict[str, Any]:
    """Browse a generated dataset — view structure or read a specific file."""
    from app.storage import get_storage

    job_id = (job_id or "").strip()
    if not job_id:
        return {"error": "job_id is required"}

    try:
        storage = get_storage()
        if not storage.exists(job_id):
            return {"error": f"Dataset not found for job {job_id}"}

        # If a specific file is requested, read it
        if file_path:
            zip_bytes = storage.get_dataset_zip(job_id)
            if not zip_bytes:
                return {"error": "Dataset ZIP not found"}
            import zipfile
            from io import BytesIO

            raw = zip_bytes.getvalue() if hasattr(zip_bytes, "getvalue") else zip_bytes
            with zipfile.ZipFile(BytesIO(raw), "r") as zf:
                try:
                    content = zf.read(file_path).decode("utf-8", errors="replace")
                except KeyError:
                    return {"error": f"File '{file_path}' not found in dataset"}
            # Truncate large files
            truncated = len(content) > 5000
            return {
                "job_id": job_id,
                "file_path": file_path,
                "content": content[:5000],
                "truncated": truncated,
                "size_bytes": len(content),
            }

        # Otherwise return structure
        structure = storage.get_dataset_structure(job_id)
        if not structure:
            return {"error": "Could not load dataset structure"}

        # Summarize: list first 50 files
        files = structure.get("files", [])
        dirs = structure.get("directories", [])
        return {
            "job_id": job_id,
            "total_files": len(files),
            "total_directories": len(dirs),
            "files": files[:50],
            "directories": dirs[:30],
            "truncated_files": len(files) > 50,
            "truncated_dirs": len(dirs) > 30,
        }
    except Exception as e:
        logger.warning_structured(
            "browse_dataset tool failed",
            extra_fields={"job_id": job_id, "error": str(e)},
        )
        return {"error": str(e)}


async def execute_generate_xml_flowchart(
    xml: str,
    xml_kind: str = "auto",
    render_mode: str = "both",
) -> dict[str, Any]:
    """Generate Mermaid + SVG structural flowchart from DITA topic/map XML."""
    if not xml or not xml.strip():
        return {"error": "xml is required"}
    try:
        return await generate_xml_flowchart(
            xml,
            xml_kind=xml_kind or "auto",
            render_mode=render_mode or "both",
        )
    except Exception as e:
        logger.warning_structured(
            "generate_xml_flowchart tool failed",
            extra_fields={"error": str(e), "xml_kind": xml_kind},
        )
        return {"error": str(e)}


async def execute_generate_image(
    prompt: str,
    size: str = "1024x1024",
    style: str | None = None,
    count: int = 1,
) -> dict[str, Any]:
    """Generate prompt-to-image artifacts for chat."""
    if not prompt or not prompt.strip():
        return {"error": "prompt is required"}
    try:
        return await generate_image(
            prompt.strip(),
            size=size or "1024x1024",
            style=style,
            count=int(count or 1),
        )
    except Exception as e:
        logger.warning_structured(
            "generate_image tool failed",
            extra_fields={"error": str(e)},
        )
        return {"error": str(e)}


def _tool_title_from_name(name: str) -> str:
    return name.replace("_", " ").title()


def _clean_summary_text(value: str, *, max_len: int = 240) -> str:
    text = " ".join((value or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _coerce_warning_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _append_source(
    sources: list[dict[str, str]],
    *,
    label: str,
    url: str = "",
    snippet: str = "",
) -> None:
    label = label.strip()
    url = url.strip()
    snippet = _clean_summary_text(snippet, max_len=180).strip()
    if not label and not url:
        return
    entry = {"label": label or url, "url": url, "snippet": snippet}
    if entry in sources:
        return
    sources.append(entry)


def _extract_tool_sources(name: str, result: dict[str, Any]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    existing_sources = result.get("sources")
    if isinstance(existing_sources, list):
        for item in existing_sources:
            if isinstance(item, dict):
                _append_source(
                    sources,
                    label=str(item.get("label") or item.get("title") or item.get("id") or item.get("issue_key") or "").strip(),
                    url=str(item.get("url") or item.get("uri") or "").strip(),
                    snippet=str(item.get("snippet") or item.get("summary") or item.get("text_content") or "").strip(),
                )
            else:
                text = str(item).strip()
                if text:
                    _append_source(sources, label=text)

    if name in {"lookup_aem_guides", "lookup_output_preset", "generate_native_pdf_config"}:
        for item in (result.get("evidence") or result.get("doc_results") or result.get("results") or [])[:6]:
            if isinstance(item, dict):
                _append_source(
                    sources,
                    label=str(item.get("title") or item.get("url") or "").strip(),
                    url=str(item.get("url") or "").strip(),
                    snippet=str(item.get("snippet") or "").strip(),
                )

    if name == "lookup_dita_spec":
        for item in (result.get("comparisons") or [])[:6]:
            if isinstance(item, dict):
                _append_source(
                    sources,
                    label=str(
                        item.get("attribute_name")
                        or item.get("element_name")
                        or "DITA comparison evidence"
                    ).strip(),
                    url=str(item.get("source_url") or "").strip(),
                    snippet=str(item.get("text_content") or "").strip(),
                )
        if result.get("element_name"):
            _append_source(
                sources,
                label=str(result.get("element_name") or "DITA element").strip(),
                url=str(result.get("source_url") or "").strip(),
                snippet=str(
                    result.get("content_model_summary")
                    or result.get("placement_summary")
                    or result.get("text_content")
                    or ""
                ).strip(),
            )
        if result.get("attribute_name"):
            _append_source(
                sources,
                label=str(result.get("attribute_name") or "DITA attribute").strip(),
                url=str(result.get("source_url") or "").strip(),
                snippet=str(result.get("text_content") or "").strip(),
            )
        for item in (result.get("spec_chunks") or [])[:5]:
            if isinstance(item, dict):
                _append_source(
                    sources,
                    label=str(item.get("element_name") or "DITA spec excerpt").strip(),
                    snippet=str(item.get("text_content") or "").strip(),
                )
        graph_knowledge = str(result.get("graph_knowledge") or "").strip()
        if graph_knowledge:
            _append_source(sources, label="DITA graph knowledge", snippet=graph_knowledge)

    if name == "lookup_dita_attribute":
        for item in (result.get("attributes") or [])[:6]:
            if isinstance(item, dict):
                _append_source(
                    sources,
                    label=str(item.get("attribute_name") or "DITA attribute").strip(),
                    url=str(item.get("source_url") or "").strip(),
                    snippet=str(item.get("text_content") or "").strip(),
                )
        if result.get("attribute_name"):
            _append_source(
                sources,
                label=str(result.get("attribute_name") or "DITA attribute").strip(),
                url=str(result.get("source_url") or "").strip(),
                snippet=str(result.get("text_content") or result.get("description") or "").strip(),
            )

    if name == "search_tenant_knowledge":
        for item in (result.get("results") or [])[:5]:
            if isinstance(item, dict):
                _append_source(
                    sources,
                    label=str(item.get("label") or item.get("doc_type") or "Tenant knowledge").strip(),
                    snippet=str(item.get("content") or "").strip(),
                )

    if name == "search_jira_issues":
        for item in (result.get("issues") or [])[:5]:
            if isinstance(item, dict):
                _append_source(
                    sources,
                    label=str(item.get("issue_key") or "").strip(),
                    url=str(item.get("url") or "").strip(),
                    snippet=str(item.get("summary") or "").strip(),
                )

    if name == "review_dita_xml":
        for item in (result.get("sources_used") or [])[:5]:
            if isinstance(item, dict):
                _append_source(
                    sources,
                    label=str(item.get("label") or item.get("title") or item.get("url") or "").strip(),
                    url=str(item.get("url") or "").strip(),
                    snippet=str(item.get("snippet") or "").strip(),
                )
            else:
                text = str(item).strip()
                if text:
                    _append_source(sources, label=text)

    if name == "find_recipes":
        for item in (result.get("recipes") or [])[:5]:
            if isinstance(item, dict):
                _append_source(
                    sources,
                    label=str(item.get("recipe_id") or "").strip(),
                    snippet=str(item.get("description") or item.get("rationale") or "").strip(),
                )

    if name == "list_jobs":
        for item in (result.get("jobs") or [])[:5]:
            if isinstance(item, dict):
                _append_source(
                    sources,
                    label=str(item.get("id") or item.get("job_id") or item.get("name") or "Job").strip(),
                    snippet=str(item.get("status") or "").strip(),
                )

    if name == "list_indexed_pdfs":
        for item in (result.get("documents") or [])[:5]:
            if isinstance(item, dict):
                _append_source(
                    sources,
                    label=str(item.get("label") or item.get("filename") or "").strip(),
                    snippet=str(item.get("doc_type") or "").strip(),
                )

    return sources[:8]


def _extract_tool_warnings(result: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    warnings.extend(_coerce_warning_list(result.get("warnings")))
    warnings.extend(_coerce_warning_list(result.get("warning")))
    warnings.extend(_coerce_warning_list(result.get("resolution_warning")))
    return warnings[:6]


def _tool_result_summary(name: str, result: dict[str, Any]) -> str:
    explicit = str(result.get("summary") or "").strip()
    if explicit:
        return _clean_summary_text(explicit)
    if name == "generate_dita":
        jira_id = str(result.get("jira_id") or "the requested issue").strip()
        bundle_summary = str(result.get("bundle_summary") or "").strip()
        if bundle_summary:
            return bundle_summary
        return f"Generated a DITA bundle for {jira_id}."
    if name == "create_job":
        recipe_type = str(result.get("recipe_type") or "").strip()
        job_id = str(result.get("job_id") or "").strip()
        label = f"Started dataset job `{job_id}`" if job_id else "Started a dataset generation job"
        if recipe_type:
            label += f" for recipe `{recipe_type}`"
        return label + "."
    if name == "search_jira_issues":
        issues = result.get("issues") or []
        query = str(result.get("query") or "the request").strip()
        if issues:
            return f"Found {len(issues)} Jira issue match{'es' if len(issues) != 1 else ''} for `{query}`."
        return f"No Jira issues matched `{query}`."
    if name == "lookup_dita_spec":
        attr = str(result.get("attribute_name") or "").strip()
        if attr:
            values = result.get("all_valid_values") or []
            elements = result.get("supported_elements") or []
            value_clause = ""
            if isinstance(values, list) and values:
                preview = ", ".join(str(item).strip() for item in values[:4] if str(item).strip())
                if preview:
                    suffix = ", ..." if len(values) > 4 else ""
                    value_clause = f" Common values include {preview}{suffix}."
            element_clause = ""
            if isinstance(elements, list) and elements:
                preview = ", ".join(str(item).strip() for item in elements[:4] if str(item).strip())
                if preview:
                    suffix = ", ..." if len(elements) > 4 else ""
                    element_clause = f" It is commonly used on {preview}{suffix}."
            return f"Retrieved DITA attribute guidance for `{attr}`.{value_clause}{element_clause}"
        element_name = str(result.get("element_name") or "").strip()
        if element_name:
            content_model_summary = str(result.get("content_model_summary") or "").strip()
            placement_summary = str(result.get("placement_summary") or "").strip()
            if content_model_summary:
                return _clean_summary_text(content_model_summary)
            if placement_summary:
                return _clean_summary_text(placement_summary)
            text_content = str(result.get("text_content") or "").strip()
            if text_content:
                return _clean_summary_text(_first_sentence(text_content))
            return f"Retrieved DITA element guidance for `{element_name}`."
        chunks = result.get("spec_chunks") or []
        query = str(result.get("query") or "the request").strip()
        if chunks or result.get("graph_knowledge"):
            return f"Retrieved DITA specification guidance for `{query}`."
        return f"No DITA specification evidence was found for `{query}`."
    if name == "review_dita_xml":
        issues = result.get("normalized_validation_issues") or result.get("validation_issues") or []
        score = result.get("quality_score")
        if score is not None:
            return f"Reviewed the DITA XML with a quality score of {score} and found {len(issues)} validation issue{'s' if len(issues) != 1 else ''}."
        return f"Reviewed the DITA XML and found {len(issues)} validation issue{'s' if len(issues) != 1 else ''}."
    if name == "find_recipes":
        recipes = result.get("recipes") or []
        query = str(result.get("query") or "the request").strip()
        if recipes:
            top = recipes[0] if isinstance(recipes[0], dict) else {}
            top_id = str(top.get("recipe_id") or "").strip()
            if top_id:
                return f"Found {len(recipes)} matching recipes for `{query}`; the top match is `{top_id}`."
            return f"Found {len(recipes)} matching recipes for `{query}`."
        return f"No matching dataset recipes were found for `{query}`."
    if name == "get_job_status":
        job_id = str(result.get("id") or result.get("job_id") or "").strip()
        job_status = str(result.get("status") or "unknown").strip()
        return f"Job `{job_id}` is currently `{job_status}`." if job_id else f"The dataset job status is `{job_status}`."
    if name == "lookup_aem_guides":
        count = int(result.get("count") or len(result.get("results") or []))
        query = str(result.get("query") or "the request").strip()
        if count:
            top = (result.get("results") or [None])[0]
            top_title = str((top or {}).get("title") or "").strip() if isinstance(top, dict) else ""
            if top_title:
                return f"Found {count} AEM Guides documentation match{'es' if count != 1 else ''} for `{query}`; top match: `{top_title}`."
            return f"Found {count} AEM Guides documentation match{'es' if count != 1 else ''} for `{query}`."
        return f"No AEM Guides documentation matches were found for `{query}`."
    if name == "search_tenant_knowledge":
        count = int(result.get("count") or len(result.get("results") or []))
        query = str(result.get("query") or "the request").strip()
        if count:
            top = (result.get("results") or [None])[0]
            top_label = str((top or {}).get("label") or "").strip() if isinstance(top, dict) else ""
            if top_label:
                return f"Found {count} tenant knowledge match{'es' if count != 1 else ''} for `{query}`; top hit: `{top_label}`."
            return f"Found {count} tenant knowledge match{'es' if count != 1 else ''} for `{query}`."
        return f"No tenant knowledge matches were found for `{query}`."
    if name == "lookup_output_preset":
        query = str(result.get("query") or "the request").strip()
        docs = result.get("doc_results") or []
        seeds = result.get("seed_results") or []
        if docs or seeds:
            top_doc = docs[0] if isinstance(docs, list) and docs else {}
            top_seed = seeds[0] if isinstance(seeds, list) and seeds else {}
            top_label = ""
            if isinstance(top_doc, dict):
                top_label = str(top_doc.get("title") or "").strip()
            if not top_label and isinstance(top_seed, dict):
                top_label = str(top_seed.get("element_name") or "").strip()
            if top_label:
                return f"Retrieved output preset guidance for `{query}` using `{top_label}` as a primary signal."
            return f"Retrieved output preset guidance for `{query}`."
        return f"No output preset guidance was found for `{query}`."
    if name == "list_jobs":
        jobs = result.get("jobs") or []
        if jobs and isinstance(jobs, list):
            running = sum(1 for item in jobs if isinstance(item, dict) and str(item.get("status") or "").strip().lower() == "running")
            completed = sum(1 for item in jobs if isinstance(item, dict) and str(item.get("status") or "").strip().lower() == "completed")
            return f"Listed {len(jobs)} recent dataset job{'s' if len(jobs) != 1 else ''}; {running} running and {completed} completed."
        return f"Listed {len(jobs)} recent dataset job{'s' if len(jobs) != 1 else ''}."
    if name == "fix_dita_xml":
        changed = bool(result.get("changed"))
        change_summary = str(result.get("change_summary") or "").strip()
        base = "Applied a safe DITA XML fix." if changed else "No DITA XML changes were needed."
        if change_summary:
            base += f" {change_summary}"
        return base
    if name == "lookup_dita_attribute":
        attrs = result.get("attribute_names") or []
        if isinstance(attrs, list) and attrs:
            preview = ", ".join(f"`{str(item).strip()}`" for item in attrs[:4] if str(item).strip())
            if preview:
                suffix = ", ..." if len(attrs) > 4 else ""
                return f"Retrieved DITA attribute guidance for {preview}{suffix}."
        attr = str(result.get("attribute_name") or "the requested attribute").strip()
        return f"Retrieved DITA attribute guidance for `{attr}`."
    if name == "list_indexed_pdfs":
        count = int(result.get("count") or len(result.get("documents") or []))
        return f"Found {count} indexed PDF document{'s' if count != 1 else ''}."
    if name == "generate_native_pdf_config":
        short_answer = str(result.get("short_answer") or "").strip()
        if short_answer:
            return _clean_summary_text(short_answer)
        query = str(result.get("query") or "the request").strip()
        return f"Generated Native PDF configuration guidance for `{query}`."
    if name == "browse_dataset":
        if result.get("file_path"):
            return f"Opened `{result.get('file_path')}` from the generated dataset."
        total_files = int(result.get("total_files") or len(result.get("files") or []))
        job_id = str(result.get("job_id") or "").strip()
        return f"Browsed dataset `{job_id}` and listed {total_files} file{'s' if total_files != 1 else ''}." if job_id else f"Browsed a dataset containing {total_files} file{'s' if total_files != 1 else ''}."
    if name == "generate_xml_flowchart":
        visible_nodes = int(result.get("visible_node_count") or result.get("node_count") or 0)
        total_nodes = int(result.get("total_node_count") or visible_nodes)
        omitted_nodes = int(result.get("omitted_node_count") or 0)
        preview_available = bool(result.get("preview_svg_data_url") or result.get("preview_svg") or result.get("inline_svg"))
        suffix = " with an SVG preview." if preview_available else " with Mermaid source only."
        if omitted_nodes:
            return (
                f"Generated a scoped XML structure overview showing {visible_nodes} of {total_nodes} nodes "
                f"({omitted_nodes} omitted for readability){suffix}"
            )
        return f"Generated a structural XML flowchart with {visible_nodes} node{'s' if visible_nodes != 1 else ''}{suffix}"
    if name == "generate_image":
        artifacts = result.get("artifacts") or []
        if artifacts and isinstance(artifacts, list):
            first = artifacts[0] if isinstance(artifacts[0], dict) else {}
            mime = str((first or {}).get("mime_type") or "").strip() if isinstance(first, dict) else ""
            preview = "preview-ready" if str((first or {}).get("preview_url") or "").strip() or str((first or {}).get("inline_svg") or "").strip() else "download-only"
            if mime:
                return f"Generated {len(artifacts)} image artifact{'s' if len(artifacts) != 1 else ''}; first artifact is {mime} and {preview}."
        return f"Generated {len(artifacts)} image artifact{'s' if len(artifacts) != 1 else ''}."
    message = str(result.get("message") or "").strip()
    if message:
        return _clean_summary_text(message)
    return f"{_tool_title_from_name(name)} completed."


def _tool_status_tone(name: str, result: dict[str, Any], warnings: list[str], sources: list[dict[str, str]]) -> str:
    if result.get("error"):
        return "error"
    if warnings:
        return "warning"
    if name in {"search_jira_issues", "lookup_aem_guides", "search_tenant_knowledge", "lookup_output_preset", "lookup_dita_spec", "find_recipes", "list_indexed_pdfs"} and not sources:
        return "warning"
    if name in {"create_job", "get_job_status", "list_jobs"}:
        raw_status = str(result.get("status") or "").strip().lower()
        if raw_status in {"failed", "error", "cancelled", "canceled"}:
            return "warning"
    return "success"


def _normalize_tool_result(name: str, result: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(result)
    warnings = _extract_tool_warnings(normalized)
    sources = _extract_tool_sources(name, normalized)
    tone = _tool_status_tone(name, normalized, warnings, sources)
    normalized["kind"] = _TOOL_KIND_BY_NAME.get(name, "guidance")
    if not str(normalized.get("summary") or "").strip():
        normalized["summary"] = _tool_result_summary(name, normalized)
    normalized["warnings"] = warnings
    normalized["sources"] = sources
    if "status" not in normalized or not str(normalized.get("status") or "").strip():
        normalized["status"] = tone
    normalized["status_tone"] = tone
    return normalized


def get_tool_catalog() -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for tool in get_tool_definitions():
        name = str(tool.get("name") or "").strip()
        meta = _TOOL_UI_META.get(name, {})
        catalog.append(
            {
                "name": name,
                "slash_alias": meta.get("slash_alias") or name,
                "title": meta.get("title") or _tool_title_from_name(name),
                "description": tool.get("description") or "",
                "category": meta.get("category") or "General",
                "args_schema": tool.get("input_schema") or {"type": "object", "properties": {}, "required": []},
                "approval_required": name in _TOOL_APPROVAL_REQUIRED,
                "review_first": name in _TOOL_REVIEW_FIRST,
                "execution_mode": "preview_then_generate" if name in _TOOL_REVIEW_FIRST else "direct",
                "read_only": name in _TOOL_READ_ONLY,
                "enabled": True,
                "primary_arg": meta.get("primary_arg") or "",
            }
        )
    return catalog


def parse_tool_intent_from_content(content: str) -> dict[str, Any] | None:
    text = (content or "").strip()
    if not text.startswith("/"):
        return None
    lines = text.splitlines()
    if not lines:
        return None
    first = lines[0].strip()
    alias = first[1:].split()[0].strip().lower()
    if not alias:
        return None

    catalog = get_tool_catalog()
    by_alias = {str(tool["slash_alias"]).lower(): tool for tool in catalog}
    tool = by_alias.get(alias)
    if not tool:
        return None

    args_schema = tool.get("args_schema") or {}
    properties = args_schema.get("properties") or {}
    primary_arg = str(tool.get("primary_arg") or "").strip()
    required = set(args_schema.get("required") or [])
    args: dict[str, Any] = {}

    inline_primary = first[len(alias) + 2 :].strip()
    header_lines: list[str] = []
    body_lines: list[str] = []
    in_body = False
    for line in lines[1:]:
        if not in_body and not line.strip():
            in_body = True
            continue
        if in_body:
            body_lines.append(line)
        else:
            header_lines.append(line)

    for raw in header_lines:
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip()
        if key in properties:
            args[key] = value.strip()

    if primary_arg and primary_arg in properties:
        primary_value = "\n".join(body_lines).strip() or inline_primary
        if primary_value:
            args[primary_arg] = primary_value
    elif inline_primary:
        first_string_key = next(
            (key for key, spec in properties.items() if isinstance(spec, dict) and spec.get("type") == "string"),
            "",
        )
        if first_string_key:
            args[first_string_key] = inline_primary

    for key, spec in properties.items():
        if key not in args:
            continue
        value = args[key]
        if not isinstance(spec, dict):
            continue
        spec_type = str(spec.get("type") or "")
        if spec_type == "integer":
            try:
                args[key] = int(str(value))
            except Exception:
                pass
        elif spec_type == "number":
            try:
                args[key] = float(str(value))
            except Exception:
                pass
        elif spec_type == "array":
            parts = [part.strip() for part in re.split(r"[,|]", str(value)) if part.strip()]
            args[key] = parts
        elif spec_type == "object":
            try:
                args[key] = json.loads(str(value))
            except Exception:
                pass

    if required and not required.issubset(args.keys()):
        return None
    return {"name": tool["name"], "args": args, "source": "slash"}


def get_tool_definitions() -> list[dict]:
    """Return Anthropic-style tool definitions for the chat LLM."""
    return [
        {
            "name": "generate_dita",
            "description": "Prepare a DITA-only bundle from text or natural language, then show a review-first preview before generation. Use when the user pastes Jira content or asks to create DITA. Ask one scoped clarification when the request is materially ambiguous, especially for bundle counts or glossary subject areas.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text or natural language description. For refinements, use the previous generation text from USER CONTEXT.",
                    },
                    "instructions": {
                        "type": "string",
                        "description": "Optional refinement instructions (e.g. 'add a concept topic for glossary terms', 'make steps more detailed')",
                    },
                },
                "required": ["text"],
            },
        },
        {
            "name": "create_job",
            "description": "Create a dataset generation job with a specific recipe type. Use find_recipes first to discover available types if the user hasn't specified one.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "recipe_type": {
                        "type": "string",
                        "description": "Recipe type identifier (e.g. task_topics, conref_pack, maps_reltable_basic). Use find_recipes to discover available types.",
                    },
                    "config": {
                        "type": "object",
                        "description": "Optional config overrides (e.g. topic_count)",
                    },
                },
                "required": ["recipe_type"],
            },
        },
        {
            "name": "search_jira_issues",
            "description": "Search related Jira issues for a user query. Use when the user explicitly asks to fetch, find, or list Jira issues or tickets.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The raw user request or Jira search topic.",
                    }
                },
                "required": ["query"],
            },
        },
        {
            "name": "lookup_dita_spec",
            "description": (
                "Look up DITA specification details for elements or attributes. Returns content models, "
                "nesting rules, allowed attributes, and spec excerpts. Use BEFORE answering any question "
                "about specific DITA elements, their attributes, or content models to ensure accuracy."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language question or element name (e.g. 'topicref attributes', 'what can go inside taskbody').",
                    },
                    "elements": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional explicit list of DITA element names (e.g. ['topicref', 'mapref']).",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "review_dita_xml",
            "description": (
                "Validate and review DITA XML content. Returns quality score, validation errors, and "
                "improvement suggestions. Use when the user pastes DITA XML and asks for review, "
                "validation, quality check, or improvement suggestions."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "xml": {
                        "type": "string",
                        "description": "The DITA XML content to review.",
                    },
                    "context": {
                        "type": "string",
                        "description": "Optional context about the content purpose.",
                    },
                },
                "required": ["xml"],
            },
        },
        {
            "name": "find_recipes",
            "description": (
                "Search available dataset recipes by description or intent. Returns matching recipes "
                "with descriptions. Use when the user asks what recipes are available, which recipe "
                "fits their needs, or wants to explore options before creating a dataset job."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What the user wants (e.g. 'conref reuse patterns', 'large scale testing', 'glossary').",
                    },
                    "k": {
                        "type": "integer",
                        "description": "Number of results (default 5, max 10).",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "get_job_status",
            "description": (
                "Check the status of a dataset generation job. Use when the user asks about job "
                "progress or wants to know if a job is done."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The job ID returned when the job was created.",
                    }
                },
                "required": ["job_id"],
            },
        },
        {
            "name": "lookup_aem_guides",
            "description": (
                "Search AEM Guides Experience League documentation. Returns relevant doc "
                "chunks with URLs. Use when user asks about AEM Guides features, configuration, "
                "publishing workflows, output presets, Native PDF, AEM Sites output, baselines, "
                "bulk activation, or any AEM product question."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query about AEM Guides.",
                    },
                    "k": {
                        "type": "integer",
                        "description": "Number of results (default 5, max 10).",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "search_tenant_knowledge",
            "description": (
                "Search the tenant's uploaded knowledge base (style guides, product docs, "
                "terminology). Use when user asks about their custom rules, conventions, "
                "or references uploaded documents."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query about tenant knowledge.",
                    },
                    "k": {
                        "type": "integer",
                        "description": "Number of results (default 5, max 8).",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "lookup_output_preset",
            "description": (
                "Look up AEM output preset configuration, publishing workflows, and template "
                "details. Covers Native PDF, AEM Sites, HTML5, DITA-OT PDF. Returns configuration "
                "details, common mistakes, and examples. Use when user asks about PDF output, "
                "AEM Sites publishing, output preset settings, Native PDF templates, baselines, "
                "bulk activation, or publishing troubleshooting."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Question about output/publishing.",
                    },
                    "output_type": {
                        "type": "string",
                        "enum": ["native_pdf", "aem_sites", "html5", "custom_pdf", "json", "knowledge_base"],
                        "description": "Optional filter by output type.",
                    },
                    "k": {
                        "type": "integer",
                        "description": "Number of results (default 5, max 10).",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "list_jobs",
            "description": (
                "List recent dataset generation jobs with status, progress, and file counts. "
                "Use when the user asks 'what jobs have I run?', 'show my recent datasets', "
                "'list my jobs', or wants an overview of their generation history."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "running", "completed", "failed"],
                        "description": "Optional filter by job status.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max jobs to return (default 10, max 25).",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "fix_dita_xml",
            "description": (
                "Auto-fix DITA XML content. Use after review_dita_xml to apply suggested fixes, "
                "or when user says 'fix this XML', 'auto-fix', 'correct this DITA'. "
                "Optionally target a specific rule_id from review results."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "xml": {
                        "type": "string",
                        "description": "The DITA XML content to fix.",
                    },
                    "fix_rule_id": {
                        "type": "string",
                        "description": "Optional: specific rule_id from review_dita_xml suggestions to target.",
                    },
                    "context": {
                        "type": "string",
                        "description": "Optional context about the content purpose.",
                    },
                },
                "required": ["xml"],
            },
        },
        {
            "name": "lookup_dita_attribute",
            "description": (
                "Look up valid values, supported elements, and combination attributes for a DITA attribute. "
                "Use when user asks 'what values can format have?', 'which elements support conkeyref?', "
                "'what are valid scope values?', or any question about a specific DITA attribute."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "attribute_name": {
                        "type": "string",
                        "description": "DITA attribute name (e.g. 'format', 'scope', 'conref', 'conkeyref', 'type', 'chunk', 'linking').",
                    },
                },
                "required": ["attribute_name"],
            },
        },
        {
            "name": "list_indexed_pdfs",
            "description": (
                "List all PDF documents indexed in the tenant's knowledge base. "
                "Use when user asks 'what PDFs are indexed?', 'show my uploaded docs', "
                "'what's in my knowledge base?', or wants to see available reference documents."
            ),
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "generate_native_pdf_config",
            "description": (
                "Get Native PDF template configuration guidance for AEM Guides. Returns "
                "relevant DITA knowledge and AEM Guides documentation for configuring Native PDF "
                "output presets, page layouts, CSS stylesheets, headers/footers, TOC, cover pages, "
                "watermarks, and conditional styling. Use when user asks about Native PDF templates, "
                "PDF page layout, PDF styling, or DITA-to-PDF configuration."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Question about Native PDF configuration (e.g. 'how to add page numbers', 'custom header with logo', 'conditional TOC levels').",
                    },
                    "config_type": {
                        "type": "string",
                        "enum": ["template", "page_layout", "stylesheet", "header_footer", "toc", "cover_page", "watermark", "conditional"],
                        "description": "Optional: specific config area to focus on.",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "browse_dataset",
            "description": (
                "Browse a generated dataset — view its file/directory structure or read a specific file. "
                "Use when user asks 'show me what was generated', 'list files in my dataset', "
                "'open topic_00001.dita from the dataset', or wants to inspect generated content."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The job ID of the completed dataset.",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Optional: specific file path within the dataset to read. Omit to get the directory structure.",
                    },
                },
                "required": ["job_id"],
            },
        },
        {
            "name": "generate_xml_flowchart",
            "description": (
                "Generate a structural flowchart from DITA topic or map XML. Returns Mermaid source and "
                "an SVG preview. Use when the user pastes XML and asks for a flowchart, diagram, "
                "visualization, or structure view."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "xml": {
                        "type": "string",
                        "description": "The DITA topic or map XML to visualize.",
                    },
                    "xml_kind": {
                        "type": "string",
                        "enum": ["auto", "topic", "map"],
                        "description": "Optional hint for the XML kind.",
                    },
                    "render_mode": {
                        "type": "string",
                        "enum": ["both", "svg", "preview", "mermaid"],
                        "description": "Optional preview mode.",
                    },
                },
                "required": ["xml"],
            },
        },
        {
            "name": "generate_image",
            "description": (
                "Generate prompt-to-image artifacts for the chat thread. Returns image previews and "
                "downloadable artifacts. Use when the user asks to create an image, illustration, "
                "poster, or concept visual from a text prompt."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The image prompt.",
                    },
                    "size": {
                        "type": "string",
                        "description": "Optional image size such as 1024x1024 or 1536x1024.",
                    },
                    "style": {
                        "type": "string",
                        "description": "Optional style hint such as editorial, schematic, or vibrant.",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Optional number of image artifacts to request.",
                    },
                },
                "required": ["prompt"],
            },
        },
    ]


async def run_tool(
    name: str,
    params: dict,
    user_id: str = "chat-user",
    session_id: str | None = None,
    run_id: str | None = None,
    tenant_id: str = "kone",
) -> dict[str, Any]:
    """Execute a tool by name and return the result. Output is sanitized to strip control chars.
    For generate_dita, pass run_id from caller so progress can be streamed before tool completes."""
    result: dict[str, Any]
    if name == "generate_dita":
        rid = run_id or str(uuid4())
        result = await execute_generate_dita(
            text=params.get("text", ""),
            instructions=params.get("instructions"),
            bundle_contract=params.get("bundle_contract"),
            run_id=rid,
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
        )
    elif name == "create_job":
        result = await execute_create_job(
            recipe_type=params.get("recipe_type", ""),
            config=params.get("config"),
            user_id=user_id,
        )
    elif name == "search_jira_issues":
        result = await execute_search_jira_issues(
            query=params.get("query", ""),
            tenant_id=tenant_id,
        )
    elif name == "lookup_dita_spec":
        result = await execute_lookup_dita_spec(
            query=params.get("query", ""),
            elements=params.get("elements"),
        )
    elif name == "review_dita_xml":
        result = await execute_review_dita_xml(
            xml=params.get("xml", ""),
            context=params.get("context"),
            tenant_id=tenant_id,
        )
    elif name == "find_recipes":
        result = await execute_find_recipes(
            query=params.get("query", ""),
            k=params.get("k", 5),
        )
    elif name == "get_job_status":
        result = await execute_get_job_status(
            job_id=params.get("job_id", ""),
        )
    elif name == "lookup_aem_guides":
        result = await execute_lookup_aem_guides(
            query=params.get("query", ""),
            k=params.get("k", 5),
        )
    elif name == "search_tenant_knowledge":
        result = await execute_search_tenant_knowledge(
            query=params.get("query", ""),
            tenant_id=tenant_id,
            k=params.get("k", 5),
        )
    elif name == "lookup_output_preset":
        result = await execute_lookup_output_preset(
            query=params.get("query", ""),
            output_type=params.get("output_type"),
            k=params.get("k", 5),
        )
    elif name == "list_jobs":
        result = await execute_list_jobs(
            status=params.get("status"),
            limit=params.get("limit", 10),
            user_id=user_id,
        )
    elif name == "fix_dita_xml":
        result = await execute_fix_dita_xml(
            xml=params.get("xml", ""),
            fix_rule_id=params.get("fix_rule_id"),
            context=params.get("context"),
            tenant_id=tenant_id,
        )
    elif name == "lookup_dita_attribute":
        result = await execute_lookup_dita_attribute(
            attribute_name=params.get("attribute_name", ""),
        )
    elif name == "list_indexed_pdfs":
        result = await execute_list_indexed_pdfs(
            tenant_id=tenant_id,
        )
    elif name == "generate_native_pdf_config":
        result = await execute_generate_native_pdf_config(
            query=params.get("query", ""),
            config_type=params.get("config_type", "template"),
        )
    elif name == "browse_dataset":
        result = await execute_browse_dataset(
            job_id=params.get("job_id", ""),
            file_path=params.get("file_path"),
        )
    elif name == "generate_xml_flowchart":
        result = await execute_generate_xml_flowchart(
            xml=params.get("xml", ""),
            xml_kind=params.get("xml_kind", "auto"),
            render_mode=params.get("render_mode", "both"),
        )
    elif name == "generate_image":
        result = await execute_generate_image(
            prompt=params.get("prompt", ""),
            size=params.get("size", "1024x1024"),
            style=params.get("style"),
            count=params.get("count", 1),
        )
    elif name == "lookup_dita_spec":
        result = await execute_lookup_dita_spec(
            query=params.get("query", ""),
            elements=params.get("elements"),
        )
    elif name == "review_dita_xml":
        result = await execute_review_dita_xml(
            xml=params.get("xml", ""),
            context=params.get("context"),
            tenant_id=tenant_id,
        )
    elif name == "find_recipes":
        result = await execute_find_recipes(
            query=params.get("query", ""),
            k=int(params.get("k", 5)),
        )
    elif name == "get_job_status":
        result = await execute_get_job_status(
            job_id=params.get("job_id", ""),
        )
    elif name == "lookup_aem_guides":
        result = await execute_lookup_aem_guides(
            query=params.get("query", ""),
            k=int(params.get("k", 5)),
        )
    elif name == "search_tenant_knowledge":
        result = await execute_search_tenant_knowledge(
            query=params.get("query", ""),
            tenant_id=tenant_id,
            k=int(params.get("k", 5)),
        )
    elif name == "lookup_output_preset":
        result = await execute_lookup_output_preset(
            query=params.get("query", ""),
            output_type=params.get("output_type"),
            k=int(params.get("k", 5)),
        )
    elif name == "list_jobs":
        result = await execute_list_jobs(
            status=params.get("status"),
            limit=int(params.get("limit", 10)),
            user_id=user_id,
        )
    elif name == "fix_dita_xml":
        result = await execute_fix_dita_xml(
            xml=params.get("xml", ""),
            fix_rule_id=params.get("fix_rule_id"),
            context=params.get("context"),
            tenant_id=tenant_id,
        )
    elif name == "lookup_dita_attribute":
        result = await execute_lookup_dita_attribute(
            attribute_name=params.get("attribute_name", ""),
        )
    elif name == "list_indexed_pdfs":
        result = await execute_list_indexed_pdfs(
            tenant_id=tenant_id,
        )
    elif name == "generate_native_pdf_config":
        result = await execute_generate_native_pdf_config(
            query=params.get("query", ""),
            config_type=params.get("config_type", "template"),
        )
    elif name == "browse_dataset":
        result = await execute_browse_dataset(
            job_id=params.get("job_id", ""),
            file_path=params.get("file_path"),
        )
    # ── Phase F: Content Intelligence Tools ──
    elif name == "generate_shortdesc":
        from app.services.shortdesc_generator_service import generate_shortdesc
        result = await generate_shortdesc(
            xml_string=params.get("xml", ""),
            use_llm=True,
        )
    elif name == "advise_topic_type":
        from app.services.topic_type_advisor_service import analyze_topic_type
        result = analyze_topic_type(
            xml_content=params.get("xml", ""),
        )
    elif name == "check_style_guide":
        from app.services.style_guide_enforcer_service import enforce
        result = enforce(
            dita_xml=params.get("xml", ""),
        )
    # ── Phase G: Agentic Workflow Tools ──
    elif name == "migrate_content":
        from app.services.content_migration_service import migrate_content
        result = migrate_content(
            content=params.get("content", ""),
            source_format=params.get("source_format", "auto"),
        )
    # ── Phase I: Visual & Interactive Tools ──
    elif name == "visualize_map":
        from app.services.map_visualizer_service import parse_map_to_graph
        result = parse_map_to_graph(
            xml=params.get("xml", ""),
        )
    elif name == "generate_diagram":
        from app.services.diagram_generation_service import generate_diagram
        result = await generate_diagram(
            xml=params.get("xml", ""),
            diagram_type=params.get("diagram_type", "auto"),
        )
    else:
        result = {"error": f"Unknown tool: {name}"}
    return _sanitize_tool_result(_normalize_tool_result(name, result))
