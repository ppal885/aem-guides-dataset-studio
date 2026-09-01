"""Remote MCP JSON-RPC endpoint for Claude Code team setups.

The local `mcp_server.py` remains the rich stdio server for developers who have
this repository cloned. This module exposes the core team workflow over the VM
backend at `/mcp`, so users can connect Claude Code to the central VM without
cloning the Dataset Studio repository locally.
"""

from __future__ import annotations

import json
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, ValidationError

from app.core.auth import CurrentUser, UserIdentity
from app.core.structured_logging import get_structured_logger
from app.services.jira_component_metadata_service import (
    CANONICAL_JIRA_COMPONENTS,
)

router = APIRouter(prefix="/mcp", tags=["remote-mcp"])
logger = get_structured_logger(__name__)


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


def _schema(
    properties: dict[str, Any], required: list[str] | None = None
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _tool(name: str, description: str, input_schema: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "description": description, "inputSchema": input_schema}


def _tools() -> list[dict[str, Any]]:
    return [
        _tool(
            "ask_dita_expert",
            "Answer DITA, DITA-OT, and AEM Guides behavior questions using VM-hosted RAG evidence.",
            _schema(
                {
                    "question": {"type": "string"},
                    "tenant_id": {"type": "string", "default": "kone"},
                },
                ["question"],
            ),
        ),
        _tool(
            "generate_dita_ot_output",
            "Generate/publish a spec-driven DITA-OT corpus for PDF, XHTML, HTML5, both, or all outputs.",
            _schema(
                {
                    "prompt": {"type": "string", "default": "DITA-OT PDF smoke test"},
                    "input_map": {"type": "string", "default": ""},
                    "output_format": {"type": "string", "default": "pdf"},
                    "package_name": {"type": "string", "default": ""},
                    "timeout_seconds": {"type": "integer", "default": 180},
                },
            ),
        ),
        _tool(
            "upload_mcp_generated_data_to_aem",
            "Upload an MCP-generated ZIP/folder to AEM Assets by source_path, job_id, or latest=true.",
            _schema(
                {
                    "target_path": {"type": "string"},
                    "source_path": {"type": "string", "default": ""},
                    "job_id": {"type": "string", "default": ""},
                    "latest": {"type": "boolean", "default": False},
                    "aem_base_url": {"type": "string", "default": ""},
                    "username": {"type": "string", "default": ""},
                    "password": {"type": "string", "default": ""},
                    "access_token": {"type": "string", "default": ""},
                    "max_concurrent": {"type": "integer", "default": 20},
                    "max_upload_files": {"type": "integer", "default": 70000},
                },
                ["target_path"],
            ),
        ),
        _tool(
            "upload_dataset_to_aem",
            (
                "Alias for upload_mcp_generated_data_to_aem when the caller has a VM-side "
                "source_path. This does not upload local laptop files."
            ),
            _schema(
                {
                    "source_path": {"type": "string"},
                    "target_path": {"type": "string"},
                    "aem_base_url": {"type": "string", "default": ""},
                    "username": {"type": "string", "default": ""},
                    "password": {"type": "string", "default": ""},
                    "access_token": {"type": "string", "default": ""},
                    "max_concurrent": {"type": "integer", "default": 20},
                    "max_upload_files": {"type": "integer", "default": 70000},
                },
                ["source_path", "target_path"],
            ),
        ),
        _tool(
            "check_rag_status",
            "Return VM RAG/Chroma readiness, evidence-graph health, and indexed corpus counts.",
            _schema({"tenant_id": {"type": "string", "default": "kone"}}),
        ),
        _tool(
            "query_test_evidence_graph",
            (
                "Connect product documentation, DITA constraints, releases, and same-mechanism Jira history "
                "through the audited evidence graph. Graph paths are traceability metadata; every result "
                "includes the underlying Jira, URL, chunk, or DITA leaf citations."
            ),
            _schema(
                {
                    "query": {"type": "string"},
                    "jira_key": {"type": "string", "default": ""},
                    "customer": {"type": "string", "default": ""},
                    "component": {
                        "type": "string",
                        "enum": ["", *CANONICAL_JIRA_COMPONENTS],
                        "default": "",
                    },
                    "outputs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                    },
                    "dita_entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                    },
                    "include_cross_customer": {"type": "boolean", "default": True},
                    "max_depth": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 2,
                        "default": 2,
                    },
                    "top_k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 25,
                        "default": 10,
                    },
                    "max_paths": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "default": 20,
                    },
                    "tenant_id": {"type": "string", "default": "kone"},
                },
                ["query"],
            ),
        ),
        _tool(
            "search_jira_history",
            (
                "Search the indexed customer-reported Jira history (jira_qa collection) for past "
                "tickets similar to a described defect or behaviour. Optionally hard-filter by "
                "Jira Component (Editor, Authoring, Publishing, Platform, Schematron, or Integration) and by "
                "Customer Label so same-area/same-customer tickets rank first. Component filtering "
                "uses normalized scalar component_primary metadata. Returns ranked "
                "matches with key, summary, status, resolution, component, customer, versions, and "
                "any recorded root cause / QA oracle. Use this for 'past similar tickets' and "
                "'known bugs' history mining - do NOT use ask_dita_expert for Jira history, it "
                "searches product documentation, not jira_qa."
            ),
            _schema(
                {
                    "query": {"type": "string"},
                    "component": {
                        "type": "string",
                        "enum": ["", *CANONICAL_JIRA_COMPONENTS],
                        "default": "",
                    },
                    "customer": {"type": "string", "default": ""},
                    "exclude_jira_key": {"type": "string", "default": ""},
                    "top_k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 30,
                        "default": 10,
                    },
                },
                ["query"],
            ),
        ),
        _tool(
            "resolve_qe_patterns",
            (
                "Resolve Human-backed QE question families and relationships to investigate. "
                "This discovery-only tool never generates or approves final acceptance criteria."
            ),
            {
                **_schema(
                    {
                        "domain": {"type": "string", "minLength": 1},
                        "change_surfaces": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                        },
                        "abstract_signals": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                        },
                        "publishing_mode": {"type": "string", "default": ""},
                        "configuration_state": {"type": "string", "default": ""},
                        "scope_constraints": {
                            "type": "object",
                            "properties": {
                                "explicit_out_of_scope": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "default": [],
                                },
                                "excluded_relationships": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "default": [],
                                },
                                "current_product_decisions": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "default": [],
                                },
                            },
                            "additionalProperties": False,
                            "default": {},
                        },
                        "include_analysis_candidates": {
                            "type": "boolean",
                            "default": False,
                        },
                        "max_results": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 50,
                            "default": 10,
                        },
                    },
                    ["domain"],
                ),
                "anyOf": [
                    {
                        "required": ["change_surfaces"],
                        "properties": {"change_surfaces": {"minItems": 1}},
                    },
                    {
                        "required": ["abstract_signals"],
                        "properties": {"abstract_signals": {"minItems": 1}},
                    },
                ],
            },
        ),
        _tool(
            "audit_jira_corpus",
            (
                "Audit the searchable jira_qa corpus by unique Jira issue. Returns represented customers, "
                "components, date coverage, chunks-per-issue distribution, missing metadata, import overlap, "
                "incremental-sync cursor health, and normalized exact-duplicate document signals. Use this instead "
                "of chunk count to measure coverage."
            ),
            _schema(
                {
                    "duplicate_sample_limit": {"type": "integer", "default": 20},
                    "top_components_per_customer": {"type": "integer", "default": 10},
                }
            ),
        ),
        _tool(
            "audit_knowledge_corpora",
            (
                "Audit aem_guides and dita_spec knowledge reliability. Reports authoritative-source coverage, "
                "baseline topic probes, DITA versions, product release coverage, provenance gaps, and duplicates."
            ),
            _schema({"duplicate_sample_limit": {"type": "integer", "default": 10}}),
        ),
    ]


@router.get("")
def remote_mcp_info(user: UserIdentity = CurrentUser) -> dict[str, Any]:
    return {
        "status": "ok",
        "protocol": "json-rpc-2.0",
        "endpoint": "/mcp",
        "serverInfo": {"name": "aem-guides-dataset-studio", "version": "0.1.0"},
        "tools": [tool["name"] for tool in _tools()],
        "usage": "POST JSON-RPC initialize, tools/list, or tools/call requests to this URL.",
    }


@router.get("/health")
def remote_mcp_health(user: UserIdentity = CurrentUser) -> dict[str, Any]:
    return {"status": "alive", "tools": len(_tools())}


@router.post("")
async def remote_mcp_json_rpc(
    payload: JsonRpcRequest,
    request: Request,
    user: UserIdentity = CurrentUser,
) -> dict[str, Any]:
    try:
        if payload.method == "initialize":
            return _rpc_result(
                payload.id,
                {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": "aem-guides-dataset-studio",
                        "version": "0.1.0",
                    },
                    "capabilities": {"tools": {}},
                },
            )
        if payload.method in {"notifications/initialized", "ping"}:
            return _rpc_result(payload.id, {})
        if payload.method == "tools/list":
            return _rpc_result(payload.id, {"tools": _tools()})
        if payload.method == "tools/call":
            call_name = str(payload.params.get("name") or "").strip()
            arguments = payload.params.get("arguments") or {}
            if not isinstance(arguments, dict):
                return _rpc_error(
                    payload.id, -32602, "Tool arguments must be an object"
                )
            result = await _call_tool(call_name, arguments, user=user)
            return _rpc_tool_result(payload.id, result)
        return _rpc_error(payload.id, -32601, f"Method not found: {payload.method}")
    except ValidationError as exc:
        return _rpc_error(payload.id, -32602, f"Invalid input: {exc}")
    except Exception as exc:
        return _rpc_tool_result(
            payload.id, f"{type(exc).__name__}: {exc}", is_error=True
        )


async def _call_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    user: UserIdentity | None = None,
) -> Any:
    tools: dict[str, Callable[[dict[str, Any]], Any]] = {
        "ask_dita_expert": _ask_dita_expert,
        "generate_dita_ot_output": _generate_dita_ot_output,
        "upload_mcp_generated_data_to_aem": _upload_mcp_generated_data_to_aem,
        "upload_dataset_to_aem": _upload_dataset_to_aem,
        "check_rag_status": _check_rag_status,
        "search_jira_history": _search_jira_history,
        "resolve_qe_patterns": _resolve_qe_patterns,
        "audit_jira_corpus": _audit_jira_corpus,
        "audit_knowledge_corpora": _audit_knowledge_corpora,
    }
    if name == "query_test_evidence_graph":
        if user is None:
            raise ValueError(
                "Authenticated user context is required for evidence graph queries."
            )
        return _query_test_evidence_graph(arguments, user)
    if name not in tools:
        raise ValueError(f"Unknown tool: {name}")
    result = tools[name](arguments)
    if hasattr(result, "__await__"):
        result = await result
    return result


async def _ask_dita_expert(arguments: dict[str, Any]) -> str:
    question = str(arguments.get("question") or "").strip()
    if not question:
        return "Provide a question."
    tenant_id = str(arguments.get("tenant_id") or "kone")
    # The canned-incident shortcut is optional: it lives in a module that is not present
    # on every deployed branch. A missing/broken module must NOT crash ask_dita_expert -
    # fall through to the normal grounded chat path instead.
    try:
        from app.services.aem_guides_incident_answer_service import (
            answer_aem_sites_oak_conflict_from_jira,
        )

        incident_answer = answer_aem_sites_oak_conflict_from_jira(question)
        if incident_answer:
            return incident_answer
    except Exception:
        pass
    from app.services import chat_service

    session_id = chat_service.create_session()
    try:
        parts: list[str] = []
        grounding: dict[str, Any] | None = None
        async for event in chat_service.chat_turn(
            session_id,
            question,
            tenant_id=tenant_id,
            human_prompts=True,
            allow_tool_routing=False,
        ):
            if not isinstance(event, dict):
                continue
            if event.get("type") == "chunk":
                parts.append(str(event.get("content") or ""))
            elif event.get("type") == "grounding":
                grounding = event.get("grounding") or {}
        answer = "".join(parts).strip() or "No answer was returned."
        if grounding:
            citations = grounding.get("citations") or []
            source_lines = []
            for citation in _relevant_mcp_citations(question, citations)[:6]:
                if not isinstance(citation, dict):
                    continue
                label = (
                    citation.get("label")
                    or citation.get("title")
                    or citation.get("id")
                    or "Evidence"
                )
                uri = citation.get("uri") or ""
                source_lines.append(f"- {label}{f' - {uri}' if uri else ''}")
            grounding_lines = [
                "## Grounding",
                f"- Status: {grounding.get('status') or 'partial'}",
            ]
            if grounding.get("confidence") is not None:
                grounding_lines.append(f"- Confidence: {grounding.get('confidence')}")
            if grounding.get("evidence_count") is not None:
                grounding_lines.append(
                    f"- Evidence chunks: {grounding.get('evidence_count')}"
                )
            if grounding.get("reason"):
                grounding_lines.append(f"- Reason: {grounding.get('reason')}")
            if source_lines:
                grounding_lines.append("- Sources:")
                grounding_lines.extend(source_lines)
            answer = answer.rstrip() + "\n\n" + "\n".join(grounding_lines)
        return answer
    finally:
        try:
            chat_service.delete_session(session_id)
        except Exception:
            pass


_MCP_CITATION_STOPWORDS = {
    "aem",
    "adobe",
    "guides",
    "dita",
    "output",
    "publish",
    "publishing",
    "behavior",
    "behaviour",
    "expected",
    "source",
    "evidence",
    "verify",
    "verified",
    "documentation",
    "topic",
    "map",
}


def _relevant_mcp_citations(
    question: str, citations: list[Any]
) -> list[dict[str, Any]]:
    """Prefer citations that support the exact named construct or workflow."""
    lowered_question = (question or "").lower()
    question_tokens = {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9._-]+", lowered_question)
        if len(token) >= 4 and token not in _MCP_CITATION_STOPWORDS
    }
    critical_terms = {
        term
        for term in (
            "searchtitle",
            "baseline",
            "copy-to",
            "chunk",
            "keyref",
            "conref",
            "post-generation",
        )
        if term in lowered_question
    }
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, citation in enumerate(citations or []):
        if not isinstance(citation, dict):
            continue
        haystack = " ".join(
            str(citation.get(field) or "") for field in ("label", "title", "uri", "id")
        ).lower()
        critical_matches = sum(1 for term in critical_terms if term in haystack)
        token_matches = sum(1 for token in question_tokens if token in haystack)
        score = critical_matches * 10 + token_matches
        if critical_terms and critical_matches == 0 and token_matches == 0:
            continue
        scored.append((score, -index, citation))
    if not scored:
        return [item for item in (citations or []) if isinstance(item, dict)][:3]
    scored.sort(reverse=True, key=lambda item: (item[0], item[1]))
    return [item[2] for item in scored]


async def _generate_dita_ot_output(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.services.dita_ot_publish_service import publish_with_dita_ot
    from app.services.publishing_dataset_intent_service import (
        normalize_publishing_request,
    )

    normalized = normalize_publishing_request(
        prompt=str(arguments.get("prompt") or "DITA-OT PDF smoke test"),
        output_format=str(arguments.get("output_format") or "pdf"),
        package_name=str(arguments.get("package_name") or ""),
    )
    result = await publish_with_dita_ot(
        input_map=str(arguments.get("input_map") or "").strip() or None,
        prompt=normalized["prompt"],
        output_format=normalized["output_format"],
        package_name=normalized["package_name"],
        timeout_seconds=max(1, int(arguments.get("timeout_seconds") or 180)),
    )
    result["publishing_intent"] = normalized
    return result


def _upload_mcp_generated_data_to_aem(arguments: dict[str, Any]) -> dict[str, Any]:
    target_path = str(arguments.get("target_path") or "").strip()
    if not target_path.startswith("/content/dam/") and not target_path.startswith(
        "content/dam/"
    ):
        raise ValueError("target_path must start with /content/dam/")
    generated = _find_generated_zip(
        source_path=str(arguments.get("source_path") or ""),
        job_id=str(arguments.get("job_id") or ""),
        latest=bool(arguments.get("latest", False)),
    )
    upload_source = _prepare_upload_source(generated)

    from app.core.aem_upload_config import resolve_aem_upload_credentials
    from app.services.aem_upload_service import get_upload_service

    creds = resolve_aem_upload_credentials(
        aem_base_url=str(arguments.get("aem_base_url") or ""),
        username=str(arguments.get("username") or ""),
        password=str(arguments.get("password") or ""),
        access_token=str(arguments.get("access_token") or ""),
    )
    result = get_upload_service().upload_dataset(
        source_path=str(upload_source),
        aem_base_url=creds["base_url"],
        target_path=target_path,
        username=creds["username"],
        password=creds["password"],
        access_token=creds["access_token"],
        max_concurrent=max(1, min(int(arguments.get("max_concurrent") or 20), 100)),
        max_upload_files=max(1, int(arguments.get("max_upload_files") or 70000)),
    )
    return _mask_secrets(result)


def _upload_dataset_to_aem(arguments: dict[str, Any]) -> dict[str, Any]:
    source_path = str(arguments.get("source_path") or "").strip()
    if not source_path:
        raise ValueError("source_path is required")
    return _upload_mcp_generated_data_to_aem(
        {
            "target_path": arguments.get("target_path"),
            "source_path": source_path,
            "job_id": "",
            "latest": False,
            "aem_base_url": arguments.get("aem_base_url", ""),
            "username": arguments.get("username", ""),
            "password": arguments.get("password", ""),
            "access_token": arguments.get("access_token", ""),
            "max_concurrent": arguments.get("max_concurrent", 20),
            "max_upload_files": arguments.get("max_upload_files", 70000),
        }
    )


def _check_rag_status(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.services.vector_store_service import (
        CHROMA_COLLECTION_AEM_GUIDES,
        CHROMA_COLLECTION_DITA_SPEC,
        CHROMA_COLLECTION_JIRA_QA,
        get_collection_count,
        is_chroma_available,
    )
    from app.services.embedding_service import is_embedding_available
    from app.services.jira_sync_cursor_service import resolve_sync_project_key
    from app.services.jira_sync_state import load_jira_qa_sync_state, sync_cursor_health

    chroma_ok = is_chroma_available()
    try:
        jira_project = resolve_sync_project_key()
        sync_state_id = f"project:{jira_project}"
        sync_state = load_jira_qa_sync_state(sync_state_id)
        cursor_health = sync_cursor_health(sync_state, project_key=jira_project)
        cursor_status = {
            "project_key": jira_project,
            "sync_state_id": sync_state_id,
            "valid": bool(cursor_health["valid"]),
            "health": cursor_health,
            "state": sync_state.model_dump(mode="json"),
            "repair_command": (
                f"bash scripts/bootstrap_jira_sync_cursor_vm.sh --project {jira_project} --apply"
            ),
        }
    except ValueError as exc:
        cursor_status = {
            "project_key": None,
            "sync_state_id": None,
            "valid": False,
            "health": {
                "valid": False,
                "missing_or_invalid_fields": ["project_key"],
                "configuration_error": str(exc),
            },
            "state": None,
            "repair_command": None,
        }
    from app.db.session import SessionLocal
    from app.services.evidence_graph_store import graph_status

    session = SessionLocal()
    try:
        evidence_graph = graph_status(session)
    finally:
        session.close()
    failed_keys = []
    if isinstance(cursor_status.get("state"), dict):
        failed_keys = list(cursor_status["state"].get("failed_keys") or [])
    evidence_graph["jira_current_validation"] = {
        "status": "degraded" if "search" in failed_keys else "available",
        "historical_indexed_evidence_usable": True,
        "mutable_jira_facts_verified": "search" not in failed_keys,
        "reason": (
            "Live Jira search is unavailable; indexed history remains usable, but status, resolution, and version facts require live validation."
            if "search" in failed_keys
            else None
        ),
    }
    return {
        "status": "ok",
        "tenant_id": str(arguments.get("tenant_id") or "kone"),
        "chroma_available": chroma_ok,
        "embedding_available": is_embedding_available(),
        "collections": {
            CHROMA_COLLECTION_AEM_GUIDES: get_collection_count(
                CHROMA_COLLECTION_AEM_GUIDES
            )
            if chroma_ok
            else 0,
            CHROMA_COLLECTION_DITA_SPEC: get_collection_count(
                CHROMA_COLLECTION_DITA_SPEC
            )
            if chroma_ok
            else 0,
            CHROMA_COLLECTION_JIRA_QA: get_collection_count(CHROMA_COLLECTION_JIRA_QA)
            if chroma_ok
            else 0,
        },
        "jira_corpus_coverage": {
            "mcp_tool": "audit_jira_corpus",
            "admin_api": "/api/v1/admin/jira-rag/corpus-audit",
            "incremental_sync_cursor": cursor_status,
            "note": "Use the audit for customer, component, date, duplicate, and metadata coverage; chunk count alone is not a coverage measure.",
        },
        "knowledge_corpus_coverage": {
            "mcp_tool": "audit_knowledge_corpora",
            "admin_api": "/api/v1/admin/rag/knowledge-audit",
            "note": "Use the audit to distinguish authoritative coverage from secondary or missing topic evidence.",
        },
        "evidence_graph": evidence_graph,
    }


def _query_test_evidence_graph(
    arguments: dict[str, Any], user: UserIdentity
) -> dict[str, Any]:
    query = str(arguments.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    tenant_id = str(arguments.get("tenant_id") or "kone").strip() or "kone"
    from app.services.tenant_service import ensure_user_can_access_tenant

    normalized_tenant = ensure_user_can_access_tenant(user, tenant_id)
    roles = {str(role).strip().casefold() for role in user.roles}
    allow_cross_customer_details = user.is_admin or "knowledge_reader" in roles
    from app.services.evidence_graph_query_service import query_test_evidence_graph

    result = query_test_evidence_graph(
        query,
        jira_key=str(arguments.get("jira_key") or ""),
        customer=str(arguments.get("customer") or ""),
        component=str(arguments.get("component") or ""),
        outputs=[str(value) for value in (arguments.get("outputs") or [])],
        dita_entities=[str(value) for value in (arguments.get("dita_entities") or [])],
        include_cross_customer=bool(arguments.get("include_cross_customer", True)),
        max_depth=arguments.get("max_depth", 2),
        top_k=arguments.get("top_k", 10),
        max_paths=arguments.get("max_paths", 20),
        tenant_id=normalized_tenant,
        allow_cross_customer_details=allow_cross_customer_details,
        actor_id=user.id,
        influence_mode="interactive",
    )
    from app.services.evidence_graph_contract import stable_digest

    logger.info_structured(
        "evidence_graph_query_audit",
        extra_fields={
            "user_id": user.id,
            "tenant_id": normalized_tenant,
            "query_hash": stable_digest(query, length=24),
            "jira_key": str(arguments.get("jira_key") or "").strip().upper(),
            "component": str(arguments.get("component") or ""),
            "include_cross_customer": bool(
                arguments.get("include_cross_customer", True)
            ),
            "cross_customer_details_authorized": allow_cross_customer_details,
            "generation_id": (result.get("generation") or {}).get("id"),
            "path_count": len(result.get("evidence_paths") or []),
            "cross_customer_aggregate_count": int(
                (result.get("cross_customer_aggregate") or {}).get(
                    "same_mechanism_ticket_count", 0
                )
            ),
        },
    )
    return result


def _search_jira_history(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.services.jira_history_search_service import search_jira_history_evidence

    return search_jira_history_evidence(
        str(arguments.get("query") or ""),
        component=str(arguments.get("component") or ""),
        customer=str(arguments.get("customer") or ""),
        exclude_jira_key=str(arguments.get("exclude_jira_key") or ""),
        top_k=arguments.get("top_k") or 10,
    )


def _resolve_qe_patterns(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.core.schemas_qe_pattern_mcp import (
        QePatternProviderStatus,
        ResolveQePatternsRequest,
    )
    from app.services.qe_pattern_mcp_service import (
        pattern_error_response,
        resolve_qe_patterns,
    )

    try:
        request = ResolveQePatternsRequest.model_validate(arguments)
    except ValidationError:
        return pattern_error_response(
            status=QePatternProviderStatus.INVALID_REQUEST,
            error_code="QE_PATTERN_REQUEST_VALIDATION_FAILED",
            warning="Pattern request rejected; no pattern influenced reasoning.",
        ).model_dump(mode="json")
    return resolve_qe_patterns(request).model_dump(mode="json")


def _audit_jira_corpus(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.services.jira_corpus_audit_service import audit_jira_corpus

    try:
        duplicate_sample_limit = max(
            0, min(int(arguments.get("duplicate_sample_limit", 20)), 100)
        )
    except (TypeError, ValueError):
        duplicate_sample_limit = 20
    try:
        top_components = max(
            1, min(int(arguments.get("top_components_per_customer", 10)), 50)
        )
    except (TypeError, ValueError):
        top_components = 10
    return audit_jira_corpus(
        duplicate_sample_limit=duplicate_sample_limit,
        top_components_per_customer=top_components,
    )


def _audit_knowledge_corpora(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.services.knowledge_corpus_audit_service import audit_knowledge_corpora

    try:
        duplicate_sample_limit = max(
            0, min(int(arguments.get("duplicate_sample_limit", 10)), 100)
        )
    except (TypeError, ValueError):
        duplicate_sample_limit = 10
    return audit_knowledge_corpora(duplicate_sample_limit=duplicate_sample_limit)


def _find_generated_zip(
    *, source_path: str = "", job_id: str = "", latest: bool = False
) -> Path:
    project_root = Path(__file__).resolve().parents[4]
    output_root = (project_root / "output").resolve()
    if source_path:
        candidate = Path(source_path)
        if not candidate.is_absolute():
            candidate = project_root / candidate
        resolved = candidate.resolve()
        if not _is_allowed_project_path(resolved, project_root):
            raise ValueError(f"Refusing source path outside project roots: {resolved}")
        if not resolved.exists():
            raise FileNotFoundError(f"source_path does not exist: {resolved}")
        return resolved
    if job_id:
        matches = sorted(
            output_root.rglob(f"*{job_id}*.zip"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if matches:
            return matches[0]
        job_dir = output_root / job_id
        if job_dir.exists():
            return job_dir.resolve()
        raise FileNotFoundError(f"No generated artifact found for job_id={job_id}")
    if latest:
        candidates = sorted(
            [path for path in output_root.rglob("*.zip") if path.is_file()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return candidates[0].resolve()
        raise FileNotFoundError("No generated ZIP artifacts found under output/")
    raise ValueError("Provide source_path, job_id, or latest=true")


def _prepare_upload_source(path: Path) -> Path:
    if path.is_dir():
        return path
    if path.suffix.lower() != ".zip":
        raise ValueError("source_path must be a directory or .zip file")
    extract_root = Path(tempfile.mkdtemp(prefix="aem_mcp_upload_"))
    root_resolved = extract_root.resolve()
    with zipfile.ZipFile(path, "r") as archive:
        for member in archive.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"Refusing unsafe ZIP entry: {member.filename}")
            destination = (extract_root / member_path).resolve()
            if (
                destination != root_resolved
                and root_resolved not in destination.parents
            ):
                raise ValueError(f"Refusing unsafe ZIP entry: {member.filename}")
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(member))
    children = [child for child in extract_root.iterdir()]
    return children[0] if len(children) == 1 and children[0].is_dir() else extract_root


def _is_allowed_project_path(path: Path, project_root: Path) -> bool:
    allowed_roots = [
        project_root.resolve(),
        (project_root / "output").resolve(),
        (project_root / "incoming_archives").resolve(),
        (project_root / "tmp").resolve(),
    ]
    return any(path == root or root in path.parents for root in allowed_roots)


def _mask_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***"
            if key.lower() in {"password", "token", "access_token", "accesstoken"}
            else _mask_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_mask_secrets(item) for item in value]
    return value


def _rpc_result(request_id: str | int | None, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _rpc_tool_result(
    request_id: str | int | None, value: Any, *, is_error: bool = False
) -> dict[str, Any]:
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, indent=2, default=str)
    )
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [{"type": "text", "text": text}],
            "isError": is_error,
        },
    }


def _rpc_error(request_id: str | int | None, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }
