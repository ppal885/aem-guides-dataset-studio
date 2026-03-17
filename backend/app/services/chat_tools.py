"""Chat tools - generate_dita, create_job for AI assistant."""
import json
import re
from typing import Any
from uuid import uuid4

from app.core.structured_logging import get_structured_logger

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
from app.db.session import SessionLocal
from app.jobs import crud as job_crud

logger = get_structured_logger(__name__)
RECIPE_TYPE_ALLOWLIST = frozenset({
    "task_topics", "concept_topics", "reference_topics", "glossary_pack",
    "bookmap_structure", "conditional_content", "relationship_table",
    "conref_pack", "keyscope_demo", "keyword_metadata", "media_rich_content",
    "maps_topicgroup_basic", "maps_topicgroup_nested", "maps_topicref_basic",
    "maps_nested_topicrefs", "maps_mapref_basic", "maps_topichead_basic",
    "maps_reltable_basic", "maps_topicset_basic", "maps_navref_basic",
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
        if session_id:
            from app.services.chat_service import set_session_last_generation
            set_session_last_generation(session_id, text=body.text, instructions=instructions, jira_id=jira_id, run_id=run_id, download_url=download_url)
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
    else:
        base_config["recipes"] = [{"type": recipe_type, "pretty_print": True}]

    if config and isinstance(config, dict):
        if "recipes" in config and config["recipes"]:
            base_config["recipes"] = config["recipes"]
        for k, v in config.items():
            if k != "recipes" and v is not None:
                base_config[k] = v

    try:
        session = SessionLocal()
        try:
            job = job_crud.create_job(
                session,
                config=base_config,
                name=base_config.get("name", "Chat Job"),
                user_id=user_id,
            )
            session.commit()
            return {
                "job_id": str(job.id),
                "name": job.name,
                "recipe_type": recipe_type,
                "message": f"Job created. Download when complete from Job History.",
            }
        finally:
            session.close()
    except Exception as e:
        logger.warning_structured(
            "create_job tool failed",
            extra_fields={"recipe_type": recipe_type, "error": str(e)},
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
            "description": "Create a dataset generation job. Use when the user wants to generate a dataset with a specific recipe (task_topics, concept_topics, glossary_pack, etc.).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "recipe_type": {
                        "type": "string",
                        "description": "Recipe type: task_topics, concept_topics, reference_topics, glossary_pack, bookmap_structure, conditional_content, relationship_table, conref_pack, keyscope_demo, keyword_metadata, media_rich_content, maps_topicgroup_basic, maps_topicgroup_nested, maps_topicref_basic, maps_nested_topicrefs, maps_mapref_basic, maps_topichead_basic, maps_reltable_basic, maps_topicset_basic, maps_navref_basic",
                    },
                    "config": {
                        "type": "object",
                        "description": "Optional config overrides (e.g. topic_count)",
                    },
                },
                "required": ["recipe_type"],
            },
        },
    ]


async def run_tool(
    name: str,
    params: dict,
    user_id: str = "chat-user",
    session_id: str | None = None,
    run_id: str | None = None,
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
    else:
        result = {"error": f"Unknown tool: {name}"}
    return _sanitize_tool_result(result)
