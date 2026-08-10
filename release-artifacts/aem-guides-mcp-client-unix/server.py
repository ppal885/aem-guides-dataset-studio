#!/usr/bin/env python3
"""Minimal Claude MCP client for VM RAG and local-machine AEM upload.

This client intentionally contains no dataset-studio repo, corpus, ChromaDB,
or backend app code. It exposes the team-approved evidence surface through the
VM `/mcp` gateway plus local-machine AEM upload.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server


CLIENT_ROOT = Path(__file__).resolve().parent
UPLOAD_SCRIPT = CLIENT_ROOT / "scripts" / "aem_upload.js"
UPLOAD_NODE_MODULE = CLIENT_ROOT / "node_modules" / "@adobe" / "aem-upload"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(CLIENT_ROOT / ".env")
_load_env_file(CLIENT_ROOT / "client.env")

BACKEND_URL = os.environ.get("AEM_STUDIO_URL", "http://10.42.46.78:4502").rstrip("/")
AUTH_TOKEN = os.environ.get("AEM_STUDIO_TOKEN", "dev-bypass")
TIMEOUT_SECONDS = float(os.environ.get("AEM_STUDIO_TIMEOUT_SECONDS", "300"))

UPLOAD_PROPERTY_KEYS = {
    "aem.base.url": "aem_base_url",
    "aem.base_url": "aem_base_url",
    "aem.url": "aem_base_url",
    "aem.username": "username",
    "aem.password": "password",
    "aem.access.token": "access_token",
    "aem.access_token": "access_token",
}

server = Server("aem-guides-dataset-studio")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json",
    }


def _resolve_client_path(path_value: str) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    return CLIENT_ROOT / path


def _resolve_local_upload_path(path_value: str) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def _parse_properties(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        mapped = UPLOAD_PROPERTY_KEYS.get(key.strip().lower())
        value = value.strip().strip('"').strip("'")
        if mapped and value:
            values[mapped] = value
    return values


@lru_cache(maxsize=1)
def _load_upload_config() -> dict[str, str]:
    override = (os.environ.get("AEM_UPLOAD_CONFIG") or "").strip()
    path = _resolve_client_path(override) if override else CLIENT_ROOT / "config" / "aem-upload.properties"
    return _parse_properties(path)


async def _post(path: str, body: dict[str, Any]) -> Any:
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        response = await client.post(f"{BACKEND_URL}{path}", headers=_headers(), json=body)
        response.raise_for_status()
        return response.json()


async def _safe_post(path: str, body: dict[str, Any]) -> Any:
    try:
        return await _post(path, body)
    except Exception as exc:
        return {"error": str(exc), "query": body}


async def _remote_mcp_tool(name: str, arguments: dict[str, Any]) -> Any:
    payload = {
        "jsonrpc": "2.0",
        "id": f"team-wrapper-{name}",
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    response = await _post("/mcp", payload)
    if response.get("error"):
        error = response["error"]
        raise RuntimeError(str(error.get("message") if isinstance(error, dict) else error))
    result = response.get("result") or {}
    content = result.get("content") if isinstance(result, dict) else None
    if isinstance(content, list) and content:
        text = str(content[0].get("text") or "") if isinstance(content[0], dict) else str(content[0])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return result


def _fmt(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, ensure_ascii=False, default=str)


def _text_tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> types.Tool:
    return types.Tool(
        name=name,
        description=description,
        inputSchema={
            "type": "object",
            "properties": properties,
            "required": required or [],
        },
    )


def _detect_content_dam_upload_root(source_path: Path) -> Path:
    if not source_path.is_dir():
        return source_path

    dam_dir = source_path / "content" / "dam"
    if not dam_dir.is_dir():
        return source_path

    subfolders = sorted(item for item in dam_dir.iterdir() if item.is_dir())
    if not subfolders:
        return source_path

    return subfolders[0].resolve()


def _coerce_int(value: Any, default: int, name: str) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < 1:
        raise ValueError(f"{name} must be greater than 0")
    return parsed


def _extract_json_output(stdout: str, stderr: str) -> dict[str, Any]:
    candidates = [line.strip() for line in stdout.splitlines() if line.strip()]
    candidates.append(stdout.strip())
    for candidate in reversed(candidates):
        if not candidate.startswith("{"):
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return {
        "success": False,
        "error": (stdout or stderr or "Upload script returned no JSON output")[:2000],
        "message": "Upload failed",
    }


def _run_local_aem_upload(args: dict[str, Any]) -> dict[str, Any]:
    source_path_value = str(args.get("source_path") or "").strip()
    target_path = str(args.get("target_path") or "").strip()
    if not source_path_value:
        raise ValueError("source_path is required and must be a local file/folder path on this machine")
    if not target_path.startswith("/content/dam/"):
        raise ValueError("target_path must start with /content/dam/")

    source_path = _resolve_local_upload_path(source_path_value)
    if not source_path.exists():
        raise FileNotFoundError(f"Local source_path does not exist on this machine: {source_path}")

    upload_config = _load_upload_config()
    aem_base_url = str(args.get("aem_base_url") or upload_config.get("aem_base_url", "")).strip().rstrip("/")
    username = str(args.get("username") or upload_config.get("username", "")).strip()
    password = str(args.get("password") or upload_config.get("password", "")).strip()
    access_token = str(args.get("access_token") or upload_config.get("access_token", "")).strip()

    if not aem_base_url:
        raise ValueError(
            "AEM base URL is required. Add config/aem-upload.properties or pass aem_base_url to the tool."
        )
    if not ((username and password) or access_token):
        raise ValueError(
            "AEM auth is required. Add username/password or access_token in config/aem-upload.properties."
        )
    if shutil.which("node") is None:
        raise RuntimeError("Node.js is required for local AEM upload. Install Node.js 18+ and rerun setup.")
    if not UPLOAD_SCRIPT.is_file():
        raise FileNotFoundError(f"Upload helper script missing: {UPLOAD_SCRIPT}")
    if not UPLOAD_NODE_MODULE.exists():
        raise RuntimeError("AEM upload dependency missing. Run setup/install again so npm installs @adobe/aem-upload.")

    upload_path = _detect_content_dam_upload_root(source_path)
    max_concurrent = _coerce_int(args.get("max_concurrent"), 20, "max_concurrent")
    max_upload_files = _coerce_int(args.get("max_upload_files"), 70000, "max_upload_files")

    node_config = {
        "sourcePath": str(upload_path),
        "aemBaseUrl": aem_base_url,
        "targetPath": target_path.lstrip("/"),
        "username": username,
        "password": password,
        "accessToken": access_token,
        "maxConcurrent": max_concurrent,
        "maxUploadFiles": max_upload_files,
    }

    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            prefix="aem-upload-",
            dir=str(CLIENT_ROOT),
            delete=False,
        ) as config_file:
            json.dump(node_config, config_file)
            temp_path = config_file.name
        try:
            os.chmod(temp_path, 0o600)
        except OSError:
            pass

        completed = subprocess.run(
            ["node", str(UPLOAD_SCRIPT), "--config-file", temp_path],
            cwd=str(CLIENT_ROOT),
            capture_output=True,
            text=True,
            timeout=3600,
            check=False,
        )
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    result = _extract_json_output(completed.stdout or "", completed.stderr or "")
    result.update(
        {
            "tool": "upload_dataset_to_aem",
            "upload_mode": "local_machine",
            "source_path": str(source_path),
            "upload_path": str(upload_path),
            "optimized_content_dam_root": upload_path != source_path,
            "target_path": target_path,
            "aem_base_url": aem_base_url,
        }
    )
    if completed.returncode != 0 and result.get("success") is not False:
        result["success"] = False
    if completed.stderr:
        result["stderr_tail"] = completed.stderr[-2000:]
    return result


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        _text_tool(
            "ask_dita_expert",
            (
                "Ground a DITA, DITA-OT, or AEM Guides behavior question using VM RAG evidence. "
                "Use this as the only Claude MCP knowledge/RAG tool."
            ),
            {
                "question": {
                    "type": "string",
                    "description": "Question about DITA, DITA-OT, AEM Guides, publishing, UI behavior, or workflow rules.",
                },
                "tenant_id": {
                    "type": "string",
                    "description": "Tenant id for context labeling; default is default.",
                    "default": "default",
                },
            },
            ["question"],
        ),
        _text_tool(
            "search_jira_history",
            "Search indexed Jira history directly for same-customer and cross-customer defect evidence.",
            {
                "query": {"type": "string"},
                "component": {
                    "type": "string",
                    "enum": ["", "Editor", "Authoring", "Publishing", "Platform", "Schematron", "Integration"],
                    "default": "",
                },
                "customer": {"type": "string", "default": ""},
                "exclude_jira_key": {"type": "string", "default": ""},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 30, "default": 10},
            },
            ["query"],
        ),
        _text_tool(
            "query_test_evidence_graph",
            "Connect direct evidence through the audited graph; path IDs are traceability only and leaf citations are evidence.",
            {
                "query": {"type": "string"},
                "jira_key": {"type": "string", "default": ""},
                "customer": {"type": "string", "default": ""},
                "component": {
                    "type": "string",
                    "enum": ["", "Editor", "Authoring", "Publishing", "Platform", "Schematron", "Integration"],
                    "default": "",
                },
                "outputs": {"type": "array", "items": {"type": "string"}, "default": []},
                "dita_entities": {"type": "array", "items": {"type": "string"}, "default": []},
                "include_cross_customer": {"type": "boolean", "default": True},
                "max_depth": {"type": "integer", "minimum": 1, "maximum": 2, "default": 2},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 25, "default": 10},
                "max_paths": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
                "tenant_id": {"type": "string", "default": "kone"},
            },
            ["query"],
        ),
        _text_tool(
            "check_rag_status",
            "Return graph-aware VM RAG readiness and indexed corpus counts through `/mcp`.",
            {"tenant_id": {"type": "string", "default": "kone"}},
        ),
        _text_tool(
            "upload_dataset_to_aem",
            (
                "Upload a local file or folder from this teammate machine directly to AEM Assets. "
                "The files do not need to be copied to the VM."
            ),
            {
                "source_path": {
                    "type": "string",
                    "description": "Local file/folder path on this Windows/Mac/Linux machine; absolute paths are recommended.",
                },
                "target_path": {
                    "type": "string",
                    "description": "AEM DAM target path, for example /content/dam/guides-qa/GUIDES-12345.",
                },
                "aem_base_url": {
                    "type": "string",
                    "description": "Optional AEM base URL override; otherwise local config/aem-upload.properties is used.",
                    "default": "",
                },
                "username": {"type": "string", "description": "Optional AEM username override.", "default": ""},
                "password": {"type": "string", "description": "Optional AEM password override.", "default": ""},
                "access_token": {"type": "string", "description": "Optional AEM access token override.", "default": ""},
                "max_concurrent": {"type": "integer", "description": "Max concurrent uploads; default 20.", "default": 20},
                "max_upload_files": {"type": "integer", "description": "Upload safety cap; default 70000.", "default": 70000},
            },
            ["source_path", "target_path"],
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    try:
        result = await _dispatch(name, arguments or {})
        return [types.TextContent(type="text", text=_fmt(result))]
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:2000] if exc.response is not None else ""
        status = exc.response.status_code if exc.response is not None else "unknown"
        return [types.TextContent(type="text", text=f"HTTP {status}: {body}")]
    except Exception as exc:
        return [types.TextContent(type="text", text=f"ERROR: {exc}")]


async def _dispatch(name: str, args: dict[str, Any]) -> Any:
    if name in {"search_jira_history", "query_test_evidence_graph", "check_rag_status"}:
        return await _remote_mcp_tool(name, args)

    if name == "ask_dita_expert":
        question = str(args.get("question") or "").strip()
        if not question:
            raise ValueError("question is required")

        tenant_id = str(args.get("tenant_id") or "default").strip() or "default"
        element_names = sorted({m.group(1) for m in re.finditer(r"<\s*([A-Za-z_][\w.-]*)", question)})
        attribute_names = sorted({m.group(1) for m in re.finditer(r"@([A-Za-z_][\w.-]*)", question)})

        attribute_evidence = []
        for attribute_name in attribute_names[:3]:
            attribute_evidence.append(
                await _safe_post("/api/v1/mcp/lookup-dita-attribute", {"attribute_name": attribute_name})
            )

        return {
            "tool": "ask_dita_expert",
            "tenant_id": tenant_id,
            "question": question,
            "detected_elements": element_names[:5],
            "detected_attributes": attribute_names[:5],
            "answering_instruction": (
                "Answer directly from the evidence below. Cite source titles/URLs when present. "
                "Mark claims as unverified when evidence is missing or generic. For exact DITA element questions, "
                "do not treat an attribute-only chunk as proof for an element."
            ),
            "aem_guides_evidence": await _safe_post("/api/v1/mcp/lookup-aem-guides", {"query": question}),
            "dita_spec_evidence": await _safe_post("/api/v1/mcp/lookup-dita-spec", {"query": question}),
            "attribute_evidence": attribute_evidence,
        }

    if name == "upload_dataset_to_aem":
        return await asyncio.to_thread(_run_local_aem_upload, args)

    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
