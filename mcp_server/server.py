"""
AEM Guides Studio — MCP Server

Exposes DITA spec lookup, dataset generation, AEM Guides documentation search,
Jira search, and job management as MCP tools so Claude Desktop, Cursor, and
other MCP-capable editors can use them.

Prerequisites:
  1. Backend running:  cd backend && python run_local.py   (default port 8001)
  2. backend/.env has:  ALLOW_DEV_AUTH_BYPASS=true

Run (stdio transport — used by Claude Desktop / Cursor / Claude Code):
  python mcp_server/server.py

Environment variables:
  AEM_STUDIO_URL    Backend base URL  (default: http://127.0.0.1:8001)
  AEM_STUDIO_TOKEN  Bearer token      (default: dev-bypass — works with ALLOW_DEV_AUTH_BYPASS=true)
"""

import asyncio
import json
import os
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

BACKEND_URL = os.environ.get("AEM_STUDIO_URL", "http://127.0.0.1:8001").rstrip("/")
AUTH_TOKEN = os.environ.get("AEM_STUDIO_TOKEN", "dev-bypass")

server = Server("aem-guides-dataset-studio")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _headers() -> dict:
    return {"Authorization": f"Bearer {AUTH_TOKEN}", "Content-Type": "application/json"}


async def _get(path: str, params: dict | None = None) -> Any:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{BACKEND_URL}{path}", headers=_headers(), params=params)
        r.raise_for_status()
        return r.json()


async def _post(path: str, body: dict) -> Any:
    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post(f"{BACKEND_URL}{path}", headers=_headers(), json=body)
        r.raise_for_status()
        return r.json()


def _fmt(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="find_recipes",
            description=(
                "Search available DITA dataset recipe types by keyword. "
                "Returns matching recipes with title, description, tags, and parameter schema. "
                "Use this to discover what kinds of DITA datasets can be generated."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term (e.g. 'conref', 'task topics', 'keyref', 'bookmap', 'glossary')",
                    }
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="lookup_dita_spec",
            description=(
                "Look up DITA 1.3 specification information for an element or concept. "
                "Returns allowed children, allowed parents, supported attributes, "
                "usage contexts, common mistakes, and correct examples. "
                "Also returns relevant spec chunks from the indexed DITA PDF corpus."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Element name or question (e.g. '<step>', 'keyref', 'how to use conref', 'topicref attributes')",
                    }
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="lookup_aem_guides",
            description=(
                "Search Adobe Experience Manager Guides product documentation "
                "(Experience League crawl corpus). Use for AEM Guides feature questions, "
                "UI guidance, output presets, translation workflows, baselines, etc."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Question or topic (e.g. 'how to create a baseline', 'native PDF output preset', 'conditional content filtering')",
                    }
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="lookup_dita_attribute",
            description=(
                "Look up details about a specific DITA attribute: allowed values, "
                "which elements it applies to, combination rules, usage contexts, "
                "common mistakes, and correct usage examples."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "attribute_name": {
                        "type": "string",
                        "description": "DITA attribute name (e.g. 'props', 'conref', 'keyref', 'outputclass', 'format', 'scope')",
                    }
                },
                "required": ["attribute_name"],
            },
        ),
        types.Tool(
            name="review_dita_xml",
            description=(
                "Validate a DITA XML string. Checks for ID uniqueness, broken hrefs/conrefs, "
                "malformed keyref syntax, and other structural issues. "
                "Returns a list of errors and warnings."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "xml": {
                        "type": "string",
                        "description": "DITA XML content to validate (topic, map, or bookmap)",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Optional filename hint to improve diagnostics (e.g. 'install.dita')",
                    },
                },
                "required": ["xml"],
            },
        ),
        types.Tool(
            name="fix_dita_xml",
            description=(
                "Automatically repair common DITA XML issues: malformed structure, "
                "missing required elements, bad attribute values. "
                "Returns the repaired XML string."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "xml": {
                        "type": "string",
                        "description": "DITA XML content to repair",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Optional filename hint (e.g. 'my-topic.dita')",
                    },
                },
                "required": ["xml"],
            },
        ),
        types.Tool(
            name="generate_dita",
            description=(
                "Generate a DITA dataset bundle from a text description. "
                "Accepts Jira issue text, feature descriptions, or freeform instructions. "
                "The LLM selects the best recipe(s), generates DITA XML files, validates them, "
                "and packages a downloadable ZIP. Returns a run_id to track progress."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Description of content to generate (Jira issue body, feature spec, or freeform)",
                    },
                    "instructions": {
                        "type": "string",
                        "description": "Optional extra generation instructions (e.g. 'use task topic type', 'include reltable')",
                    },
                },
                "required": ["text"],
            },
        ),
        types.Tool(
            name="list_jobs",
            description="List recent DITA dataset generation jobs with status, recipe used, and download link.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max number of jobs to return (default 10)",
                        "default": 10,
                    }
                },
            },
        ),
        types.Tool(
            name="get_job_status",
            description="Get the current status and details of a dataset generation job by its ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "Job ID returned by generate_dita or list_jobs",
                    }
                },
                "required": ["job_id"],
            },
        ),
        types.Tool(
            name="search_jira_issues",
            description=(
                "Search Jira issues related to AEM Guides. "
                "Accepts an issue key (e.g. GUIDES-1234) or natural language query. "
                "Returns issue summaries, descriptions, status, and metadata."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Jira issue key or search query (e.g. 'GUIDES-1234', 'keyref resolution bug', 'native PDF table of contents')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        result = await _dispatch(name, arguments)
        return [types.TextContent(type="text", text=_fmt(result))]
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500]
        return [types.TextContent(type="text", text=f"Backend error {exc.response.status_code}: {detail}")]
    except httpx.ConnectError:
        return [types.TextContent(
            type="text",
            text=f"Cannot reach backend at {BACKEND_URL}. Make sure 'python backend/run_local.py' is running.",
        )]
    except Exception as exc:
        return [types.TextContent(type="text", text=f"Error ({type(exc).__name__}): {exc}")]


async def _dispatch(name: str, args: dict) -> Any:
    if name == "find_recipes":
        return await _post("/api/v1/mcp/find-recipes", {"query": args["query"]})

    if name == "lookup_dita_spec":
        return await _post("/api/v1/mcp/lookup-dita-spec", {"query": args["query"]})

    if name == "lookup_aem_guides":
        return await _post("/api/v1/mcp/lookup-aem-guides", {"query": args["query"]})

    if name == "lookup_dita_attribute":
        return await _post("/api/v1/mcp/lookup-dita-attribute", {"attribute_name": args["attribute_name"]})

    if name == "review_dita_xml":
        return await _post("/api/v1/mcp/review-dita-xml", {
            "xml": args["xml"],
            "filename": args.get("filename", "topic.dita"),
        })

    if name == "fix_dita_xml":
        return await _post("/api/v1/mcp/fix-dita-xml", {
            "xml": args["xml"],
            "filename": args.get("filename", "topic.dita"),
        })

    if name == "generate_dita":
        return await _post("/api/v1/ai/generate-from-text", {
            "text": args["text"],
            "instructions": args.get("instructions"),
        })

    if name == "list_jobs":
        return await _get("/api/v1/jobs", {"limit": args.get("limit", 10)})

    if name == "get_job_status":
        return await _get(f"/api/v1/jobs/{args['job_id']}")

    if name == "search_jira_issues":
        return await _post("/api/v1/mcp/search-jira", {
            "query": args["query"],
            "limit": args.get("limit", 5),
        })

    raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
