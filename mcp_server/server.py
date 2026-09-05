"""
AEM Guides Studio — MCP Server

Exposes DITA spec lookup, dataset generation, AEM Guides documentation search,
Jira search, and job management as MCP tools so Claude Desktop, Cursor, and
other MCP-capable editors can use them.

Prerequisites:
  1. Backend running:  cd backend && python run_local.py   (default port 8001)
  2. backend/.env has:  ALLOW_DEV_AUTH_BYPASS=true

Run (stdio — local use, Claude Desktop / Cursor / Claude Code on same machine):
  python mcp_server/server.py

Run (SSE/HTTP — shared team access, exposes on a network port):
  python mcp_server/server.py --sse
  MCP_SSE_PORT=4502 python mcp_server/server.py --sse   # custom port

Team members then add to their claude_desktop_config.json:
  { "mcpServers": { "aem-guides-dataset-studio": { "url": "http://<vm-ip>:4502/sse" } } }

Environment variables:
  AEM_STUDIO_URL    Backend base URL  (default: http://127.0.0.1:8001)
  AEM_STUDIO_TOKEN  Bearer token      (default: dev-bypass — works with ALLOW_DEV_AUTH_BYPASS=true)
  MCP_SSE_PORT      Port for SSE mode (default: 4502)
  MCP_SSE_HOST      Bind host for SSE (default: 0.0.0.0)
"""

import asyncio
import json
import os
import re
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

BACKEND_URL = os.environ.get("AEM_STUDIO_URL", "http://127.0.0.1:8001").rstrip("/")
AUTH_TOKEN = os.environ.get("AEM_STUDIO_TOKEN", "dev-bypass")

FEEDBACK_DELTA_TYPES = [
    "UNCLASSIFIED", "COVERAGE_ADDED", "COVERAGE_REMOVED", "SCOPE_NARROWED",
    "SCOPE_EXPANDED", "DISPOSITION_CHANGED", "OPEN_QUESTION_ADDED",
    "OPEN_QUESTION_REMOVED", "LANGUAGE_SIMPLIFIED", "AC_MERGED", "AC_SPLIT",
    "ORACLE_CHANGED", "PRIORITY_CHANGED", "IMPLEMENTATION_DETAIL_REMOVED",
]
FEEDBACK_SOURCE_KINDS = ["HUMAN_CORRECTION", "AI_PROPOSAL", "UNCONFIRMED"]
FEEDBACK_DECISIONS = ["APPROVE", "REJECT", "REVOKE", "SUPERSEDE"]
FEEDBACK_TOOL_NAMES = frozenset({
    "capture_uac_feedback",
    "list_uac_feedback",
    "get_uac_feedback_status",
    "review_uac_feedback",
})
_SAFE_FEEDBACK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
SHARED_SSE_TRANSPORT = False

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


def _pattern_error_payload(*, invalid_request: bool) -> dict[str, Any]:
    return {
        "schema_version": "aem-guides-qe-pattern-mcp-v1",
        "provider_name": "TRAIN_V2_PATTERN_ADAPTER",
        "provider_status": "INVALID_REQUEST" if invalid_request else "UNAVAILABLE",
        "pattern_library_version": "NOT_LOADED",
        "pattern_library_sha256": None,
        "pattern_count": 0,
        "validated_production_pattern_count": 0,
        "matched_patterns": [],
        "suppressed_patterns": [],
        "excluded_pattern_counts": {},
        "warnings": [
            "Pattern request rejected; no pattern influenced reasoning."
            if invalid_request
            else "Pattern provider unavailable; no pattern influenced reasoning."
        ],
        "error_code": (
            "QE_PATTERN_REQUEST_VALIDATION_FAILED"
            if invalid_request
            else "QE_PATTERN_PROVIDER_UNAVAILABLE"
        ),
    }


def _require_personal_feedback_identity() -> None:
    token = AUTH_TOKEN.strip()
    if SHARED_SSE_TRANSPORT:
        raise ValueError(
            "Shared UAC feedback is disabled on the legacy shared SSE transport; "
            "use a local stdio client so each Human supplies a personal credential."
        )
    if (
        not token
        or token == "dev-bypass"
        or token.casefold().startswith("replace")
        or any(character in token for character in "\r\n")
    ):
        raise ValueError(
            "Shared UAC feedback requires AEM_STUDIO_TOKEN to be a personal token; "
            "dev-bypass cannot establish a named Human author or reviewer."
        )


def _feedback_id(value: object) -> str:
    identifier = str(value or "").strip()
    if not _SAFE_FEEDBACK_ID.fullmatch(identifier):
        raise ValueError("feedback_id is required and contains unsupported characters")
    return identifier


def _feedback_tools() -> list[types.Tool]:
    client_context = {
        "type": "object",
        "properties": {
            "client": {
                "type": "string",
                "enum": ["claude_desktop", "codex", "api", "unknown"],
                "default": "unknown",
            },
            "session_id": {"type": "string", "maxLength": 160, "default": ""},
            "message_id": {"type": "string", "maxLength": 160, "default": ""},
        },
        "additionalProperties": False,
        "default": {},
    }
    draft = {
        "type": "object",
        "description": (
            "Optional exact generated draft for atomic registration. Do not put an entire "
            "chat transcript here; criteria must be exact substrings of draft_markdown."
        ),
        "properties": {
            "draft_markdown": {"type": "string", "minLength": 1, "maxLength": 100000},
            "criteria": {
                "type": "object",
                "additionalProperties": {"type": "string", "minLength": 1, "maxLength": 12000},
                "default": {},
            },
            "evidence_bundle_id": {"type": "string", "maxLength": 180, "default": ""},
            "run_id": {"type": "string", "maxLength": 160, "default": ""},
            "client_context": client_context,
        },
        "required": ["draft_markdown"],
        "additionalProperties": False,
    }
    return [
        types.Tool(
            name="capture_uac_feedback",
            description=(
                "Any authenticated tenant teammate may persist a selected Human UAC correction as pending feedback. "
                "This never approves or indexes the correction. Use HUMAN_CORRECTION only "
                "when a Human directly supplied it; never upload the whole conversation."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "contract_version": {
                        "type": "string", "enum": ["shared-uac-feedback-v1"],
                        "default": "shared-uac-feedback-v1",
                    },
                    "tenant_id": {"type": "string", "maxLength": 120, "default": "kone"},
                    "jira_key": {"type": "string", "minLength": 3, "maxLength": 64},
                    "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 240},
                    "raw_feedback": {"type": "string", "minLength": 1, "maxLength": 12000},
                    "source_kind": {
                        "type": "string", "enum": FEEDBACK_SOURCE_KINDS,
                        "default": "UNCONFIRMED",
                    },
                    "proposed_correction": {"type": "string", "maxLength": 12000, "default": ""},
                    "delta_type": {
                        "type": "string", "enum": FEEDBACK_DELTA_TYPES,
                        "default": "UNCLASSIFIED",
                    },
                    "ai_classification": {
                        "type": "object",
                        "description": "Advisory model metadata only; never Human authority.",
                        "additionalProperties": True,
                        "default": {},
                    },
                    "draft_id": {"type": "string", "maxLength": 36, "default": ""},
                    "plan_fingerprint": {
                        "type": "string", "pattern": "^$|^[a-f0-9]{64}$", "default": "",
                    },
                    "evidence_bundle_id": {"type": "string", "maxLength": 180, "default": ""},
                    "run_id": {"type": "string", "maxLength": 160, "default": ""},
                    "ac_id": {"type": "string", "maxLength": 120, "default": ""},
                    "draft": draft,
                    "client_context": client_context,
                },
                "required": ["jira_key", "idempotency_key", "raw_feedback"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="list_uac_feedback",
            description=(
                "List shared UAC feedback visible to the authenticated tenant teammate. Pending and "
                "candidate records are not reusable learning."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "tenant_id": {"type": "string", "maxLength": 120, "default": "kone"},
                    "jira_key": {"type": "string", "maxLength": 64, "default": ""},
                    "plan_fingerprint": {
                        "type": "string", "pattern": "^$|^[a-f0-9]{64}$", "default": "",
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 100},
                },
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="get_uac_feedback_status",
            description=(
                "Read the server-authoritative binding, review, publication, and index "
                "status for one feedback record, including reuse_eligible and publication_review_status. "
                "An earlier APPROVED state alone does not establish current reuse eligibility."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "feedback_id": {"type": "string", "minLength": 1, "maxLength": 80},
                    "tenant_id": {"type": "string", "maxLength": 120, "default": "kone"},
                },
                "required": ["feedback_id"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="review_uac_feedback",
            description=(
                "Submit one deliberate review using the current revision. Only the ticket's "
                "current live Jira QE Assignee, using a personal named Human identity, may review. "
                "Admin status, roles, draft ownership, ordinary Assignee and prose names grant no review right. "
                "The server verifies Jira identity and QE assignment; unavailable verification denies review. "
                "Review operations are never queued or automatically retried."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "feedback_id": {"type": "string", "minLength": 1, "maxLength": 80},
                    "tenant_id": {"type": "string", "maxLength": 120, "default": "kone"},
                    "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 240},
                    "expected_revision": {"type": "integer", "minimum": 1},
                    "decision": {"type": "string", "enum": FEEDBACK_DECISIONS},
                    "note": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "lesson": {
                        "type": "object",
                        "description": "Server-validated lesson definition; required for approval/supersession.",
                        "additionalProperties": True,
                    },
                    "origin_confirmed": {"type": "boolean", "default": False},
                    "applicability_confirmed": {"type": "boolean", "default": False},
                    "counterexamples_checked": {"type": "boolean", "default": False},
                },
                "required": [
                    "feedback_id", "idempotency_key", "expected_revision", "decision", "note"
                ],
                "additionalProperties": False,
            },
        ),
    ]


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
        types.Tool(
            name="guides_test_plan_generator",
            description=(
                "Build the evidence packet for the Claude Code slash command "
                "`/guides-test-plan-generator GUIDES-12345`. Retrieves Jira, "
                "Experience League RAG, DITA/spec evidence, and QA Studio preview "
                "without mutating indexes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "jira_key": {
                        "type": "string",
                        "description": "AEM Guides Jira key, e.g. GUIDES-12345",
                    },
                    "tenant_id": {
                        "type": "string",
                        "description": "Jira tenant id; defaults to kone",
                        "default": "kone",
                    },
                    "evidence_k": {
                        "type": "integer",
                        "description": "Number of AEM Guides evidence chunks to retrieve",
                        "default": 8,
                    },
                },
                "required": ["jira_key"],
            },
        ),
        types.Tool(
            name="search_jira_history",
            description=(
                "Semantic search over the INDEXED jira_qa corpus — past validated AEM "
                "Guides UACs / test plans the team has indexed. This is historical QA "
                "learning, distinct from `search_jira_issues` (which hits live Jira). "
                "Use it to retrieve prior plans for the same component/behaviour."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language query or Jira key (e.g. 'native AEM site navtitle crash', 'duplicate id save warning')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 10)",
                        "default": 10,
                    },
                    "customer": {
                        "type": "string",
                        "description": "Optional customer/tenant to rank same-customer plans first",
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="resolve_qe_patterns",
            description=(
                "Resolve Human-backed QE question families and relationships to investigate. "
                "This discovery-only tool never generates or approves final acceptance criteria."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
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
                    "publishing_mode": {"type": ["string", "null"], "default": None},
                    "configuration_state": {
                        "type": ["string", "null"],
                        "default": None,
                    },
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
                "required": ["domain"],
                "additionalProperties": False,
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
        types.Tool(
            name="index_test_plan",
            description=(
                "Persist a validated test-plan markdown to the backend's shared store and "
                "index it into the jira_qa corpus, so the whole team can retrieve it via "
                "`search_jira_history`. Push your own already-made plan to the team backend "
                "(the VM behind AEM_STUDIO_URL) from Claude Desktop or the CLI. Idempotent."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "AEM Guides Jira key the plan is for, e.g. GUIDES-12345",
                    },
                    "markdown": {
                        "type": "string",
                        "description": "The full validated test-plan markdown to index",
                    },
                },
                "required": ["key", "markdown"],
            },
        ),
    ] + ([] if SHARED_SSE_TRANSPORT else _feedback_tools())


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        result = await _dispatch(name, arguments)
        return [types.TextContent(type="text", text=_fmt(result))]
    except httpx.HTTPStatusError as exc:
        if name in FEEDBACK_TOOL_NAMES:
            return [
                types.TextContent(
                    type="text",
                    text=(
                        "Shared feedback request failed. Verify access and read server status "
                        "before retrying; no review decision was retried."
                    ),
                )
            ]
        detail = exc.response.text[:500]
        return [
            types.TextContent(
                type="text", text=f"Backend error {exc.response.status_code}: {detail}"
            )
        ]
    except httpx.ConnectError:
        return [
            types.TextContent(
                type="text",
                text=f"Cannot reach backend at {BACKEND_URL}. Make sure 'python backend/run_local.py' is running.",
            )
        ]
    except Exception as exc:
        if name in FEEDBACK_TOOL_NAMES:
            return [
                types.TextContent(
                    type="text",
                    text=(
                        "Shared feedback operation failed local validation or transport. "
                        "No review decision was retried."
                    ),
                )
            ]
        return [
            types.TextContent(type="text", text=f"Error ({type(exc).__name__}): {exc}")
        ]


async def _dispatch(name: str, args: dict) -> Any:
    if name == "find_recipes":
        return await _post("/api/v1/mcp/find-recipes", {"query": args["query"]})

    if name == "lookup_dita_spec":
        return await _post("/api/v1/mcp/lookup-dita-spec", {"query": args["query"]})

    if name == "lookup_aem_guides":
        return await _post("/api/v1/mcp/lookup-aem-guides", {"query": args["query"]})

    if name == "lookup_dita_attribute":
        return await _post(
            "/api/v1/mcp/lookup-dita-attribute",
            {"attribute_name": args["attribute_name"]},
        )

    if name == "review_dita_xml":
        return await _post(
            "/api/v1/mcp/review-dita-xml",
            {
                "xml": args["xml"],
                "filename": args.get("filename", "topic.dita"),
            },
        )

    if name == "fix_dita_xml":
        return await _post(
            "/api/v1/mcp/fix-dita-xml",
            {
                "xml": args["xml"],
                "filename": args.get("filename", "topic.dita"),
            },
        )

    if name == "generate_dita":
        return await _post(
            "/api/v1/ai/generate-from-text",
            {
                "text": args["text"],
                "instructions": args.get("instructions"),
            },
        )

    if name == "list_jobs":
        return await _get("/api/v1/jobs", {"limit": args.get("limit", 10)})

    if name == "get_job_status":
        return await _get(f"/api/v1/jobs/{args['job_id']}")

    if name == "search_jira_issues":
        return await _post(
            "/api/v1/mcp/search-jira",
            {
                "query": args["query"],
                "limit": args.get("limit", 5),
            },
        )

    if name == "guides_test_plan_generator":
        return await _post(
            "/api/v1/mcp/guides-test-plan-generator",
            {
                "jira_key": args["jira_key"],
                "tenant_id": args.get("tenant_id", "kone"),
                "evidence_k": args.get("evidence_k", 8),
            },
        )

    if name == "search_jira_history":
        return await _post(
            "/api/v1/mcp/search-jira-history",
            {
                "query": args["query"],
                "limit": args.get("limit", 10),
                "customer": args.get("customer"),
            },
        )

    if name == "resolve_qe_patterns":
        try:
            return await _post(
                "/api/v1/mcp/resolve-qe-patterns",
                {
                    "domain": args["domain"],
                    "change_surfaces": args.get("change_surfaces", []),
                    "abstract_signals": args.get("abstract_signals", []),
                    "publishing_mode": args.get("publishing_mode"),
                    "configuration_state": args.get("configuration_state"),
                    "scope_constraints": args.get("scope_constraints", {}),
                    "include_analysis_candidates": args.get(
                        "include_analysis_candidates", False
                    ),
                    "max_results": args.get("max_results", 10),
                },
            )
        except httpx.HTTPStatusError as exc:
            return _pattern_error_payload(
                invalid_request=exc.response.status_code == 422
            )
        except (httpx.ConnectError, httpx.TimeoutException):
            return _pattern_error_payload(invalid_request=False)

    if name == "index_test_plan":
        return await _post(
            "/api/v1/mcp/index-test-plan",
            {
                "key": args["key"],
                "markdown": args["markdown"],
            },
        )

    if name == "capture_uac_feedback":
        _require_personal_feedback_identity()
        body = {
            "contract_version": args.get("contract_version", "shared-uac-feedback-v1"),
            "tenant_id": args.get("tenant_id", "kone"),
            "jira_key": args["jira_key"],
            "idempotency_key": args["idempotency_key"],
            "raw_feedback": args["raw_feedback"],
            "source_kind": args.get("source_kind", "UNCONFIRMED"),
            "proposed_correction": args.get("proposed_correction", ""),
            "delta_type": args.get("delta_type", "UNCLASSIFIED"),
            "ai_classification": args.get("ai_classification", {}),
            "draft_id": args.get("draft_id", ""),
            "plan_fingerprint": args.get("plan_fingerprint", ""),
            "evidence_bundle_id": args.get("evidence_bundle_id", ""),
            "run_id": args.get("run_id", ""),
            "ac_id": args.get("ac_id", ""),
            "client_context": args.get("client_context", {}),
        }
        if "draft" in args:
            body["draft"] = args["draft"]
        return await _post("/api/v1/test-plan-learning/feedback", body)

    if name == "list_uac_feedback":
        _require_personal_feedback_identity()
        return await _get(
            "/api/v1/test-plan-learning/feedback",
            {
                "tenant_id": args.get("tenant_id", "kone"),
                "jira_key": args.get("jira_key", ""),
                "plan_fingerprint": args.get("plan_fingerprint", ""),
                "limit": args.get("limit", 100),
            },
        )

    if name == "get_uac_feedback_status":
        _require_personal_feedback_identity()
        identifier = _feedback_id(args.get("feedback_id"))
        return await _get(
            f"/api/v1/test-plan-learning/feedback/{identifier}",
            {"tenant_id": args.get("tenant_id", "kone")},
        )

    if name == "review_uac_feedback":
        _require_personal_feedback_identity()
        identifier = _feedback_id(args.get("feedback_id"))
        body = {
            "tenant_id": args.get("tenant_id", "kone"),
            "idempotency_key": args["idempotency_key"],
            "expected_revision": args["expected_revision"],
            "decision": args["decision"],
            "note": args["note"],
            "lesson": args.get("lesson"),
            "origin_confirmed": args.get("origin_confirmed", False),
            "applicability_confirmed": args.get("applicability_confirmed", False),
            "counterexamples_checked": args.get("counterexamples_checked", False),
        }
        return await _post(
            f"/api/v1/test-plan-learning/feedback/{identifier}/review", body
        )

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


def run_sse() -> None:
    """Run as an HTTP/SSE server so the whole team can connect without a local clone."""
    global SHARED_SSE_TRANSPORT
    SHARED_SSE_TRANSPORT = True
    try:
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route
        import uvicorn
    except ImportError:
        raise SystemExit("SSE dependencies missing. Run: pip install starlette uvicorn")

    host = os.environ.get("MCP_SSE_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_SSE_PORT", "4502"))

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as (
            read_stream,
            write_stream,
        ):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ]
    )
    print(f"AEM Guides MCP server (SSE) starting on http://{host}:{port}")
    print(f"  Backend: {BACKEND_URL}")
    print(
        f"  Team config: add url=http://<this-vm-ip>:{port}/sse to claude_desktop_config.json"
    )
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import sys

    if "--sse" in sys.argv:
        run_sse()
    else:
        asyncio.run(main())
