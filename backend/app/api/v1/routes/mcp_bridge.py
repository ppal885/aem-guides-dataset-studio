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
# screenshot-to-dita
# ---------------------------------------------------------------------------

class ScreenshotToDitaRequest(BaseModel):
    """
    All fields are JSON-safe so the MCP server can call this without multipart.

    image_base64:    base64-encoded screenshot bytes (PNG / JPEG / WebP).
    image_path:      Alternative — absolute local path to the screenshot file.
                     Resolved server-side; only works when MCP server and backend
                     share the same filesystem (typical local dev).
    image_filename:  Suggested filename (e.g. 'ui-screenshot.png').
    image_mime_type: MIME type override (inferred from filename when absent).
    prompt:          User instruction (e.g. 'Convert this settings UI to a reference topic').
    reference_xml:   Optional reference DITA XML string to guide style/structure.
    dita_type:       Force topic type: 'concept' | 'task' | 'reference' | 'topic' (auto when absent).
    jira_context:    Optional Jira issue body to merge into the authoring prompt.
    """

    image_base64: str | None = None
    image_path: str | None = None
    image_filename: str = "screenshot.png"
    image_mime_type: str | None = None
    prompt: str = ""
    reference_xml: str | None = None
    dita_type: str | None = None  # concept | task | reference | topic
    jira_context: str | None = None


def _save_bytes_as_asset(
    *,
    content: bytes,
    kind: str,
    filename: str,
    mime_type: str,
    user_id: str,
    session_id: str,
):
    """Persist raw bytes using the same layout as chat_asset_service.save_upload_asset."""
    from app.services.chat_asset_service import (
        _asset_dir,
        _asset_payload_path,
        _asset_url,
        _write_asset_metadata,
    )
    from app.services.chat_authoring_governance import sha256_hex_bytes, store_asset_content_sha256
    from app.core.schemas_chat_authoring import ChatAttachmentRef

    asset_id = str(uuid4())
    asset_dir = _asset_dir(asset_id)
    asset_dir.mkdir(parents=True, exist_ok=True)
    payload_path = _asset_payload_path(asset_id, filename)
    payload_path.write_bytes(content)

    preview = ""
    if kind == "reference_dita":
        preview = content.decode("utf-8", errors="ignore")[:1500]

    metadata: dict = {
        "asset_id": asset_id,
        "session_id": session_id,
        "user_id": user_id,
        "kind": kind,
        "filename": filename,
        "mime_type": mime_type,
        "size_bytes": len(content),
        "payload_path": str(payload_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "content_preview": preview,
    }
    if store_asset_content_sha256():
        metadata["content_sha256"] = sha256_hex_bytes(content)
    _write_asset_metadata(asset_id, metadata)

    return ChatAttachmentRef(
        asset_id=asset_id,
        kind=kind,  # type: ignore[arg-type]
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(content),
        url=_asset_url(asset_id),
        storage_path=str(payload_path),
        content_preview=preview or None,
    )


@router.post("/screenshot-to-dita")
async def screenshot_to_dita(body: ScreenshotToDitaRequest, user: UserIdentity = CurrentUser):
    """
    Run the full screenshot-guided DITA authoring pipeline.

    Accepts a base64-encoded screenshot (or local file path) and optional
    reference DITA XML. Returns generated DITA XML, validation results,
    and the semantic plan used during generation.
    """
    from app.core.schemas_chat_authoring import (
        ChatAuthoringRequestPayload,
        ChatDitaGenerationOptions,
    )
    from app.services.chat_dita_authoring_service import ChatDitaAuthoringService

    # ------------------------------------------------------------------
    # 1. Resolve image bytes
    # ------------------------------------------------------------------
    if body.image_base64:
        try:
            image_bytes = base64.b64decode(body.image_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid base64 image data: {exc}")
    elif body.image_path:
        img_path = Path(body.image_path)
        if not img_path.is_file():
            raise HTTPException(status_code=400, detail=f"image_path not found: {body.image_path}")
        image_bytes = img_path.read_bytes()
    else:
        raise HTTPException(status_code=400, detail="Provide either image_base64 or image_path.")

    filename = body.image_filename or "screenshot.png"
    mime_type = body.image_mime_type or mimetypes.guess_type(filename)[0] or "image/png"

    session_id = f"mcp-{uuid4()}"

    # ------------------------------------------------------------------
    # 2. Save image asset
    # ------------------------------------------------------------------
    image_ref = _save_bytes_as_asset(
        content=image_bytes,
        kind="image",
        filename=filename,
        mime_type=mime_type,
        user_id=user.id,
        session_id=session_id,
    )
    attachments = [image_ref]

    # ------------------------------------------------------------------
    # 3. Optionally save reference DITA asset
    # ------------------------------------------------------------------
    if body.reference_xml:
        ref_bytes = body.reference_xml.encode("utf-8")
        ref_ref = _save_bytes_as_asset(
            content=ref_bytes,
            kind="reference_dita",
            filename="reference.dita",
            mime_type="application/xml",
            user_id=user.id,
            session_id=session_id,
        )
        attachments.append(ref_ref)

    # ------------------------------------------------------------------
    # 4. Build generation options
    # ------------------------------------------------------------------
    gen_opts = ChatDitaGenerationOptions(
        dita_type=body.dita_type,  # type: ignore[arg-type]
        strict_validation=True,
        style_strictness="medium",
    )

    payload = ChatAuthoringRequestPayload(
        content=body.prompt or "Convert this screenshot to DITA XML.",
        attachments=attachments,
        generation_options=gen_opts,
        jira_context=body.jira_context,
    )

    # ------------------------------------------------------------------
    # 5. Run pipeline
    # ------------------------------------------------------------------
    svc = ChatDitaAuthoringService()
    result = await svc.generate_topic_from_request(
        payload=payload,
        session_id=session_id,
        user_id=user.id,
        tenant_id="default",
    )

    # ------------------------------------------------------------------
    # 6. Return clean response
    # ------------------------------------------------------------------
    validation = result.validation_result if hasattr(result, "validation_result") else {}
    return {
        "status": result.status,
        "title": result.title,
        "dita_type": result.dita_type,
        "xml": result.xml_preview,
        "saved_asset_path": result.saved_asset_path,
        "artifact_url": result.artifact_url,
        "validation": validation.model_dump(mode="json") if hasattr(validation, "model_dump") else validation,
        "assumptions": [a.text for a in result.assumptions],
        "semantic_plan": result.semantic_plan.model_dump(mode="json") if result.semantic_plan else None,
        "screenshot_confidence": result.screenshot_confidence,
        "message": getattr(result, "message", ""),
    }
