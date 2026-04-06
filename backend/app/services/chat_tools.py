"""Chat tools - generate_dita, create_job for AI assistant."""
import json
import re
from typing import Any
from uuid import uuid4

from app.core.structured_logging import get_structured_logger
from app.services.dataset_job_service import (
    build_dataset_job_urls,
    create_dataset_job_record,
    enforce_concurrent_job_limit,
    start_dataset_job_in_background,
)
from app.services.jira_chat_search_service import search_related_jira_issues

# Control characters and null bytes - strip from tool output
_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


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


async def execute_generate_dita(
    text: str,
    instructions: str | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    Generate DITA from text or natural language.
    Returns dict with jira_id, run_id, download_url, scenarios.
    When run_id is provided, progress is written to _generate_progress for streaming.
    When session_id is provided, last generation is stored for conversational refinement.
    """
    from app.api.v1.routes.ai_dataset import (
        _run_generate_from_text,
        GenerateFromTextRequest,
        _update_generate_progress,
    )

    run_id = run_id or str(uuid4())
    body = GenerateFromTextRequest(text=(text or "").strip(), instructions=instructions)
    if not body.text:
        return {"error": "Text is required for DITA generation"}

    _update_generate_progress(run_id, status="running", stage="starting", jira_id=f"TEXT-{run_id[:8]}")

    try:
        result = await _run_generate_from_text(
            body, run_id, request=None, skip_rag_check=True, progress_run_id=run_id
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
        }
        rw = result.get("resolution_warning")
        if rw:
            out["resolution_warning"] = rw
        if session_id:
            from app.services.chat_service import set_session_last_generation
            text_for_session = result.get("resolved_source_text") or body.text
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
    try:
        snapshot = await build_review_snapshot(xml=xml, issue=issue, tenant_id=tenant_id)
        return {
            "dita_type": snapshot.get("dita_type"),
            "quality_score": snapshot.get("quality_score"),
            "quality_breakdown": snapshot.get("quality_breakdown"),
            "validation_issues": (snapshot.get("validation") or [])[:20],
            "suggestions": snapshot.get("suggestions_report", {}),
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
    from app.services.doc_retriever_service import retrieve_relevant_docs

    k = min(max(k, 1), 10)
    try:
        docs = retrieve_relevant_docs(query, k=k)
        results = [
            {
                "url": d.get("url", ""),
                "title": d.get("title", ""),
                "snippet": (d.get("snippet") or "")[:800],
            }
            for d in (docs or [])
        ]
        return {"query": query, "results": results, "count": len(results)}
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
    from app.services.tenant_service import retrieve_tenant_context
    from app.services.doc_pdf_index_service import list_indexed_docs

    k = min(max(k, 1), 8)
    try:
        indexed = list_indexed_docs(tenant_id)
        if not indexed:
            return {
                "query": query, "results": [], "count": 0,
                "indexed_doc_count": 0,
                "message": "No documents indexed for this tenant. Upload PDFs via the Knowledge Base page.",
            }
        results_raw = retrieve_tenant_context(query, tenant_id=tenant_id, k=k)
        results = [
            {
                "content": (r.get("content") or "")[:800],
                "label": (r.get("metadata") or {}).get("label", ""),
                "doc_type": (r.get("metadata") or {}).get("doc_type", ""),
            }
            for r in (results_raw or [])
        ]
        return {
            "query": query, "results": results, "count": len(results),
            "indexed_doc_count": len(indexed),
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
        doc_chunks = retrieve_relevant_docs(enriched, k=3)
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

    attr = (attribute_name or "").strip().lower()
    if not attr:
        return {"error": "attribute_name is required"}
    try:
        spec = get_attribute_spec(attr)
        if spec is None:
            return {
                "error": f"Attribute '{attr}' not found in DITA spec catalog.",
                "hint": "Try common attributes: format, scope, type, conref, conkeyref, href, keyref, audience, platform, product, props, otherprops, chunk, processing-role, linking, toc, print.",
            }
        return {
            "attribute_name": spec.attribute_name,
            "all_valid_values": spec.all_valid_values,
            "supported_elements": spec.supported_elements,
            "combination_attributes": spec.combination_attributes,
            "default_scenarios": spec.default_scenarios,
            "text_content": (spec.text_content or "")[:1200],
        }
    except Exception as e:
        logger.warning_structured(
            "lookup_dita_attribute tool failed",
            extra_fields={"attribute_name": attr, "error": str(e)},
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

        return {
            "query": query,
            "config_type": config_type,
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


def get_tool_definitions() -> list[dict]:
    """Return Anthropic-style tool definitions for the chat LLM."""
    return [
        {
            "name": "generate_dita",
            "description": "Generate DITA XML from text or natural language. Use when the user pastes Jira content (Issue Summary, Description, etc.) or asks to create DITA (e.g. 'create a task topic about X'). For refinements (e.g. 'add a concept topic', 'make steps more detailed'), use the previous text from USER CONTEXT and pass their request as instructions. Call immediately—do not ask for confirmation.",
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
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": "Optional keyword to filter results.",
                    },
                },
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
        # ── Phase F: Content Intelligence Tools ──
        {
            "name": "generate_shortdesc",
            "description": (
                "Generate a DITA-compliant <shortdesc> for a topic. Analyzes the full topic body and "
                "produces a shortdesc following information-typing rules: task = outcome-focused, "
                "concept = definition-focused, reference = scope-focused. Returns the shortdesc, "
                "alternatives, and an XML snippet showing correct placement."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "xml": {
                        "type": "string",
                        "description": "The full DITA XML topic content.",
                    },
                },
                "required": ["xml"],
            },
        },
        {
            "name": "advise_topic_type",
            "description": (
                "Analyze DITA XML content and recommend the correct topic type (task, concept, "
                "reference, glossentry). Detects misclassified topics — e.g., steps inside a <concept>, "
                "prose-only <task> that should be a concept, or procedural content in a <reference>. "
                "Returns confidence score, structural signals, and suggested fixes."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "xml": {
                        "type": "string",
                        "description": "The DITA XML content to analyze.",
                    },
                },
                "required": ["xml"],
            },
        },
        {
            "name": "check_style_guide",
            "description": (
                "Check DITA XML content against style guide rules. Detects: passive voice, long sentences, "
                "banned terminology ('click on' → 'click', 'in order to' → 'to'), non-imperative step commands, "
                "ambiguous pronouns, future tense in procedures, and more. Returns a score (0-100), "
                "grade (A-F), and actionable violations with suggestions."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "xml": {
                        "type": "string",
                        "description": "The DITA XML content to check.",
                    },
                },
                "required": ["xml"],
            },
        },
        # ── Phase I: Visual & Interactive Tools ──
        {
            "name": "migrate_content",
            "description": (
                "Convert Word, Markdown, HTML, or plain text content into properly structured DITA topics. "
                "Automatically classifies sections as task (procedures), concept (explanations), or reference "
                "(tables/specs). Returns multiple DITA topic files plus a ditamap linking them all. "
                "Use when a user wants to convert existing documentation into DITA format."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The source content to migrate (Markdown, HTML, or plain text).",
                    },
                    "source_format": {
                        "type": "string",
                        "enum": ["auto", "markdown", "html", "plain_text"],
                        "description": "Source format. Use 'auto' to detect automatically.",
                    },
                },
                "required": ["content"],
            },
        },
        {
            "name": "visualize_map",
            "description": (
                "Parse a DITA map (ditamap/bookmap) and return a visual graph structure showing the topic "
                "hierarchy, relationships, and AI suggestions for improving the map organization. "
                "Shows node types (topics, groups, chapters), nesting depth, and relationship table links."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "xml": {
                        "type": "string",
                        "description": "The ditamap or bookmap XML content.",
                    },
                },
                "required": ["xml"],
            },
        },
        {
            "name": "generate_diagram",
            "description": (
                "Generate a Mermaid.js diagram from DITA XML. Supports: task flowcharts (from <steps>), "
                "concept mind maps (from <section> elements), ditamap structure diagrams (from <topicref> hierarchy), "
                "and process flow diagrams (from ordered lists). Returns Mermaid code that renders as a visual diagram."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "xml": {
                        "type": "string",
                        "description": "The DITA XML content (task, concept, map, or any topic with ordered lists).",
                    },
                    "diagram_type": {
                        "type": "string",
                        "enum": ["auto", "flowchart", "mindmap", "map_structure", "process_flow"],
                        "description": "Type of diagram to generate. Use 'auto' to detect from XML structure.",
                    },
                },
                "required": ["xml"],
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
            run_id=rid,
            session_id=session_id,
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
    return _sanitize_tool_result(result)
