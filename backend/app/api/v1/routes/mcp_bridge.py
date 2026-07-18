"""MCP bridge routes — direct tool invocations for the MCP server.

These endpoints bypass the chat-session layer and invoke backend services
directly so the mcp_server/ subprocess can call them without managing a
streaming chat session.  Not intended for the main frontend.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.auth import CurrentUser, UserIdentity
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class TextQuery(BaseModel):
    query: str


class AttributeQuery(BaseModel):
    attribute_name: str


class XmlPayload(BaseModel):
    xml: str
    filename: str = "topic.dita"


class JiraSearchRequest(BaseModel):
    query: str
    limit: int = 5


class GuidesTestPlanRequest(BaseModel):
    jira_key: str
    tenant_id: str = "kone"
    evidence_k: int = 8


# ---------------------------------------------------------------------------
# find-recipes
# ---------------------------------------------------------------------------

@router.post("/find-recipes")
def find_recipes(body: TextQuery, user: UserIdentity = CurrentUser):
    """Search recipe specs by keyword."""
    from app.generator.recipe_manifest import discover_recipe_specs

    query_tokens = body.query.lower().split()
    results = []
    for spec in discover_recipe_specs():
        searchable = " ".join([
            spec.id, spec.title, spec.description,
            " ".join(spec.tags), " ".join(spec.constructs),
            " ".join(spec.intent_tags), " ".join(spec.trigger_phrases),
        ]).lower()
        if any(tok in searchable for tok in query_tokens):
            results.append({
                "id": spec.id,
                "title": spec.title,
                "description": spec.description,
                "tags": spec.tags,
                "topic_type": spec.topic_type,
                "complexity": spec.complexity,
                "mechanism_family": spec.mechanism_family,
                "params_schema": spec.params_schema,
                "default_params": spec.default_params,
            })

    return {"recipes": results[:15], "total_matched": len(results)}


# ---------------------------------------------------------------------------
# lookup-dita-spec
# ---------------------------------------------------------------------------

@router.post("/lookup-dita-spec")
def lookup_dita_spec(body: TextQuery, user: UserIdentity = CurrentUser):
    """Return structured element spec + DITA knowledge RAG chunks."""
    from app.services.dita_spec_registry_service import get_element_spec
    from app.services.dita_query_interpreter import extract_element_names
    from app.services.dita_knowledge_retriever import retrieve_dita_knowledge

    element_specs = []
    for el in extract_element_names(body.query)[:3]:
        spec = get_element_spec(el)
        if spec:
            element_specs.append({
                "element": spec.name,
                "description": spec.description,
                "allowed_children": spec.allowed_children[:20],
                "allowed_parents": spec.allowed_parents[:10],
                "supported_attributes": spec.supported_attributes[:20],
                "attribute_usage": spec.attribute_usage,
                "usage_contexts": spec.usage_contexts,
                "common_mistakes": spec.common_mistakes,
                "correct_examples": spec.correct_examples[:3],
                "source_url": spec.source_url,
            })

    rag_chunks: list[dict] = []
    try:
        raw = retrieve_dita_knowledge(body.query, k=5)
        rag_chunks = [
            {
                "text": c.get("text_content", c.get("snippet", c.get("text", ""))),
                "source": c.get("element_name", c.get("url", c.get("source", ""))),
            }
            for c in (raw or [])[:5]
        ]
    except Exception as exc:
        logger.warning_structured("DITA spec RAG failed", extra_fields={"error": str(exc)})

    return {"element_specs": element_specs, "rag_chunks": rag_chunks, "query": body.query}


# ---------------------------------------------------------------------------
# lookup-aem-guides
# ---------------------------------------------------------------------------

@router.post("/lookup-aem-guides")
def lookup_aem_guides(body: TextQuery, user: UserIdentity = CurrentUser):
    """Retrieve AEM Guides Experience League doc chunks."""
    from app.services.doc_retriever_service import retrieve_relevant_docs

    try:
        chunks = retrieve_relevant_docs(body.query, k=8)
        results = [
            {"text": c.get("snippet", c.get("text", "")), "source": c.get("url", c.get("source", ""))}
            for c in chunks
        ]
    except Exception as exc:
        logger.warning_structured("AEM Guides RAG failed", extra_fields={"error": str(exc)})
        results = []

    return {"results": results, "query": body.query, "count": len(results)}


# ---------------------------------------------------------------------------
# lookup-dita-attribute
# ---------------------------------------------------------------------------

@router.post("/lookup-dita-attribute")
def lookup_dita_attribute(body: AttributeQuery, user: UserIdentity = CurrentUser):
    """Look up a DITA attribute from the catalog."""
    from app.services.dita_attribute_catalog import get_attribute_spec

    spec = get_attribute_spec(body.attribute_name)
    if spec:
        return {
            "attribute": body.attribute_name,
            "spec": {
                "all_valid_values": spec.all_valid_values,
                "supported_elements": spec.supported_elements[:20],
                "combination_attributes": spec.combination_attributes,
                "default_scenarios": spec.default_scenarios[:5],
                "usage_contexts": spec.usage_contexts,
                "common_mistakes": spec.common_mistakes,
                "correct_examples": spec.correct_examples[:3],
                "syntax": spec.syntax,
                "semantic_class": spec.semantic_class,
                "source_url": spec.source_url,
            },
        }

    # Fallback: DITA knowledge RAG
    rag_chunks: list[dict] = []
    try:
        from app.services.dita_knowledge_retriever import retrieve_dita_knowledge
        raw = retrieve_dita_knowledge(f"DITA @{body.attribute_name} attribute", k=4)
        rag_chunks = [
            {
                "text": c.get("text_content", c.get("snippet", c.get("text", ""))),
                "source": c.get("element_name", c.get("url", c.get("source", ""))),
            }
            for c in (raw or [])[:4]
        ]
    except Exception as exc:
        logger.warning_structured("Attribute RAG fallback failed", extra_fields={"error": str(exc)})

    return {"attribute": body.attribute_name, "spec": None, "rag_chunks": rag_chunks}


# ---------------------------------------------------------------------------
# review-dita-xml
# ---------------------------------------------------------------------------

@router.post("/review-dita-xml")
def review_dita_xml(body: XmlPayload, user: UserIdentity = CurrentUser):
    """Validate a DITA XML string and return errors/warnings."""
    import xml.etree.ElementTree as ET
    from app.utils.dita_validator import validate_dita_folder

    with tempfile.TemporaryDirectory() as tmp:
        fpath = Path(tmp) / body.filename
        fpath.write_text(body.xml, encoding="utf-8")
        result = validate_dita_folder(Path(tmp))

    # Ensure parse errors are surfaced even if validator doesn't catch them
    parse_errors: list[str] = []
    try:
        ET.fromstring(body.xml)
    except ET.ParseError as exc:
        parse_errors.append(f"XML parse error: {exc}")

    return {
        "filename": body.filename,
        "parse_errors": parse_errors,
        "validation": result,
        "valid": not parse_errors and not result.get("errors"),
    }


# ---------------------------------------------------------------------------
# fix-dita-xml
# ---------------------------------------------------------------------------

@router.post("/fix-dita-xml")
def fix_dita_xml(body: XmlPayload, user: UserIdentity = CurrentUser):
    """Auto-repair common DITA XML issues and return fixed XML."""
    from app.services.dita_auto_fix_service import auto_fix_dita_folder

    with tempfile.TemporaryDirectory() as tmp:
        fpath = Path(tmp) / body.filename
        fpath.write_text(body.xml, encoding="utf-8")
        fix_result = auto_fix_dita_folder(Path(tmp))
        fixed_xml = fpath.read_text(encoding="utf-8")

    return {"fixed_xml": fixed_xml, "filename": body.filename, "fix_report": fix_result}


# ---------------------------------------------------------------------------
# search-jira
# ---------------------------------------------------------------------------

@router.post("/search-jira")
def search_jira(body: JiraSearchRequest, user: UserIdentity = CurrentUser):
    """Search Jira issues via live Jira API or indexed cache."""
    from app.services.jira_chat_search_service import search_related_jira_issues

    # search_related_jira_issues requires a tenant_id; use default for MCP callers
    result = search_related_jira_issues(
        body.query,
        tenant_id="default",
        max_results=body.limit,
    )
    return result


# ---------------------------------------------------------------------------
# guides-test-plan-generator
# ---------------------------------------------------------------------------

@router.post("/guides-test-plan-generator")
def guides_test_plan_generator(body: GuidesTestPlanRequest, user: UserIdentity = CurrentUser):
    """Build the evidence packet for `/guides-test-plan-generator GUIDES-12345`."""
    from app.services.guides_test_plan_generator_service import build_guides_test_plan_packet

    return build_guides_test_plan_packet(
        body.jira_key,
        tenant_id=body.tenant_id,
        evidence_k=max(3, min(body.evidence_k, 12)),
    )


# ---------------------------------------------------------------------------
# screenshot-to-dita (removed)
# ---------------------------------------------------------------------------

_SCREENSHOT_DITA_GONE = (
    "Screenshot-to-DITA authoring is no longer available. "
    "Use AI Chat with /generate_dita, /review_dita, or /fix_dita instead."
)


@router.post("/screenshot-to-dita")
async def screenshot_to_dita(user: UserIdentity = CurrentUser):
    """Legacy MCP endpoint — screenshot authoring was removed from the product."""
    raise HTTPException(status_code=410, detail=_SCREENSHOT_DITA_GONE)
