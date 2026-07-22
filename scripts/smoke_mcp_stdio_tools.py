#!/usr/bin/env python3
"""Real stdio MCP smoke tests for the Dataset Studio server.

This script launches ``mcp_server.py`` as an MCP stdio server, performs the
MCP initialize/list_tools flow, and invokes a small set of tools over the same
protocol Cursor/Claude use. It is intentionally not a unit test.

Usage:
  python scripts/smoke_mcp_stdio_tools.py
  python scripts/smoke_mcp_stdio_tools.py --call generate-router
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PYTHON = ROOT / "backend" / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
SERVER = ROOT / "mcp_server.py"


def _text_content(result: Any) -> str:
    chunks: list[str] = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            chunks.append(text)
    return "\n".join(chunks)


async def _call_tool(
    session: ClientSession,
    name: str,
    arguments: dict[str, Any],
    *,
    timeout_seconds: int,
) -> tuple[bool, str]:
    try:
        result = await asyncio.wait_for(session.call_tool(name, arguments), timeout=timeout_seconds)
    except TimeoutError:
        return False, f"TIMEOUT: MCP tool `{name}` did not return within {timeout_seconds}s"
    text = _text_content(result)
    is_error = bool(getattr(result, "isError", False))
    return (not is_error, text)


async def run(args: argparse.Namespace) -> int:
    python = Path(args.python).resolve()
    if not python.exists():
        print(f"FAIL: Python not found: {python}")
        return 2
    if not SERVER.exists():
        print(f"FAIL: MCP server not found: {SERVER}")
        return 2

    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("AEM_STUDIO_URL", "http://127.0.0.1:8001")
    env.setdefault("AEM_STUDIO_TOKEN", "dev-bypass")

    server_params = StdioServerParameters(
        command=str(python),
        args=[str(SERVER)],
        cwd=str(ROOT),
        env=env,
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = sorted(tool.name for tool in tools.tools)
            print(f"Connected MCP server. tools={len(tool_names)}")
            required = {
                "ask_dita_expert",
                "lookup_dita_construct",
                "generate_dita",
                "generate_dita_ot_output",
                "guides_test_plan_generator",
                "upload_mcp_generated_data_to_aem",
            }
            missing = sorted(required - set(tool_names))
            if missing:
                print("FAIL missing tools:", ", ".join(missing))
                return 1
            print("Required tools present:", ", ".join(sorted(required)))

            if args.call in {"ask", "all"}:
                ok, text = await _call_tool(
                    session,
                    "ask_dita_expert",
                    {"question": "What is searchtitle in DITA?"},
                    timeout_seconds=args.tool_timeout,
                )
                print("\n--- ask_dita_expert(searchtitle) ---")
                print(text[:3000])
                if not ok or "search" not in text.lower():
                    print("FAIL ask_dita_expert smoke did not return expected content")
                    return 1

            if args.call in {"lookup", "all"}:
                ok, text = await _call_tool(
                    session,
                    "lookup_dita_construct",
                    {"tag": "searchtitle"},
                    timeout_seconds=args.tool_timeout,
                )
                print("\n--- lookup_dita_construct(searchtitle) ---")
                print(text[:2000])
                if not ok or "search" not in text.lower():
                    print("FAIL lookup smoke did not return expected content")
                    return 1

            if args.call in {"generate-router", "all"}:
                ok, text = await _call_tool(
                    session,
                    "generate_dita",
                    {
                        "text": "Generate DITA-OT HTML5 for searchtitle publishing behavior",
                        "prior_context": "What is searchtitle and how is it used in DITA publishing?",
                    },
                    timeout_seconds=args.tool_timeout,
                )
                print("\n--- generate_dita router smoke ---")
                print(text[:4000])
                if not ok:
                    print("FAIL generate_dita returned MCP error")
                    return 1
                expected_markers = ("routed to DITA-OT", "DITA-OT", "Status:")
                if not any(marker.lower() in text.lower() for marker in expected_markers):
                    print("FAIL generate_dita did not appear to route through DITA-OT path")
                    return 1

            if args.call in {"dita-ot", "all"}:
                ok, text = await _call_tool(
                    session,
                    "generate_dita_ot_output",
                    {
                        "prompt": "Generate DITA-OT HTML5 for metadata cascading publishing behavior",
                        "output_format": "html5",
                        "package_name": "mcp-smoke-metadata-cascade",
                        "timeout_seconds": min(args.tool_timeout, 45),
                    },
                    timeout_seconds=args.tool_timeout + 10,
                )
                print("\n--- generate_dita_ot_output(html5) ---")
                print(text[:4000])
                if not ok or "success" not in text.lower():
                    print("FAIL DITA-OT output smoke did not report success")
                    return 1

    print("\nMCP stdio smoke passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=str(DEFAULT_PYTHON), help="Python executable used by Cursor MCP config")
    parser.add_argument(
        "--call",
        choices=("ask", "lookup", "generate-router", "dita-ot", "all", "none"),
        default="all",
        help="Which real tool call to execute after list_tools",
    )
    parser.add_argument("--tool-timeout", type=int, default=75, help="Per-tool MCP call timeout in seconds")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
