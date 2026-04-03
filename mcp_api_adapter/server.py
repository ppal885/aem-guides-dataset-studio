"""FastMCP server: tools are thin wrappers around Dataset Studio /api/v1 REST."""

from __future__ import annotations

import json
import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_api_adapter.http_client import DatasetStudioApiClient

mcp = FastMCP("dataset-studio-api")

_client: DatasetStudioApiClient | None = None


def _api() -> DatasetStudioApiClient:
    global _client
    if _client is None:
        _client = DatasetStudioApiClient()
    return _client


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _uuid(label: str, value: str) -> str:
    try:
        return str(uuid.UUID((value or "").strip()))
    except ValueError as exc:
        raise ValueError(f"{label} must be a valid UUID string") from exc


@mcp.tool()
def list_presets() -> str:
    """List recipe presets from the API (GET /api/v1/presets)."""
    return _dump(_api().request_json("GET", "/api/v1/presets"))


@mcp.tool()
def create_job(config: dict) -> str:
    """Create and run a dataset job immediately (POST /api/v1/jobs). Body: { \"config\": <job config dict> }."""
    return _dump(_api().request_json("POST", "/api/v1/jobs", json_body={"config": config}))


@mcp.tool()
def get_job(job_id: str) -> str:
    """Get one job by id (GET /api/v1/jobs/{job_id})."""
    jid = _uuid("job_id", job_id)
    return _dump(_api().request_json("GET", f"/api/v1/jobs/{jid}"))


@mcp.tool()
def schedule_job(config: dict, scheduled_at: str, timezone: str = "UTC") -> str:
    """Schedule a future job (POST /api/v1/jobs/schedule). scheduled_at: ISO-8601 string."""
    body = {"config": config, "scheduled_at": scheduled_at, "timezone": timezone}
    return _dump(_api().request_json("POST", "/api/v1/jobs/schedule", json_body=body))


@mcp.tool()
def search_dataset_files(job_id: str, query: str, file_type: str = "") -> str:
    """Search files inside a completed dataset (GET /api/v1/datasets/{job_id}/search)."""
    jid = _uuid("job_id", job_id)
    params: dict[str, str] = {"query": query}
    if file_type.strip():
        params["file_type"] = file_type.strip()
    return _dump(_api().request_json("GET", f"/api/v1/datasets/{jid}/search", params=params))


@mcp.tool()
def save_recipe(
    name: str,
    recipe_config: dict,
    description: str = "",
    is_public: bool = False,
    tags: list | None = None,
) -> str:
    """Save a reusable recipe (POST /api/v1/recipes/save)."""
    body: dict[str, Any] = {
        "name": name,
        "recipe_config": recipe_config,
        "is_public": is_public,
        "tags": tags or [],
    }
    if description.strip():
        body["description"] = description.strip()
    return _dump(_api().request_json("POST", "/api/v1/recipes/save", json_body=body))


@mcp.tool()
def preview_conref_recipe(
    topic_count: int = 50,
    reusable_elements_per_topic: int = 3,
    conref_density: float = 0.3,
    include_map: bool = True,
    pretty_print: bool = True,
) -> str:
    """Preview conref pack recipe estimates (POST /api/v1/aem-recipes/conref/preview)."""
    body = {
        "topic_count": topic_count,
        "reusable_elements_per_topic": reusable_elements_per_topic,
        "conref_density": conref_density,
        "include_map": include_map,
        "pretty_print": pretty_print,
    }
    return _dump(_api().request_json("POST", "/api/v1/aem-recipes/conref/preview", json_body=body))


@mcp.tool()
def preview_glossary_recipe(
    entry_count: int = 100,
    include_acronyms: bool = True,
    include_map: bool = True,
) -> str:
    """Preview glossary pack recipe estimates (POST /api/v1/specialized/glossary/preview)."""
    body = {
        "entry_count": entry_count,
        "include_acronyms": include_acronyms,
        "include_map": include_map,
    }
    return _dump(_api().request_json("POST", "/api/v1/specialized/glossary/preview", json_body=body))


@mcp.tool()
def get_rag_status(tenant_id: str = "default") -> str:
    """RAG / vector index status (GET /api/v1/ai/rag-status)."""
    return _dump(
        _api().request_json("GET", "/api/v1/ai/rag-status", params={"tenant_id": tenant_id})
    )


@mcp.tool()
def generate_from_text(
    text: str,
    instructions: str = "",
    async_mode: bool = False,
    skip_rag_check: bool = True,
) -> str:
    """Generate DITA from raw text via API (POST /api/v1/ai/generate-from-text)."""
    body: dict[str, str] = {"text": text}
    if instructions.strip():
        body["instructions"] = instructions.strip()
    params = {"async": async_mode, "skip_rag_check": skip_rag_check}
    return _dump(_api().request_json("POST", "/api/v1/ai/generate-from-text", params=params, json_body=body))


@mcp.tool()
def create_chat_session() -> str:
    """Create a new chat session (POST /api/v1/chat/sessions)."""
    return _dump(_api().request_json("POST", "/api/v1/chat/sessions", json_body={}))


@mcp.tool()
def send_chat_message(
    session_id: str,
    content: str,
    context: dict | None = None,
    human_prompts: bool | None = None,
) -> str:
    """Send a chat message; aggregates SSE chunks into assistant_text (POST /api/v1/chat/sessions/{id}/messages)."""
    sid = _uuid("session_id", session_id)
    body: dict[str, Any] = {"content": content}
    if context is not None:
        body["context"] = context
    if human_prompts is not None:
        body["human_prompts"] = human_prompts
    return _dump(_api().post_sse_chat(f"/api/v1/chat/sessions/{sid}/messages", body))


@mcp.tool()
def regenerate_chat_response(
    session_id: str,
    context: dict | None = None,
    human_prompts: bool | None = None,
) -> str:
    """Regenerate last assistant reply; aggregates SSE (POST /api/v1/chat/sessions/{id}/regenerate)."""
    sid = _uuid("session_id", session_id)
    body: dict[str, Any] = {}
    if context is not None:
        body["context"] = context
    if human_prompts is not None:
        body["human_prompts"] = human_prompts
    return _dump(_api().post_sse_chat(f"/api/v1/chat/sessions/{sid}/regenerate", body))
