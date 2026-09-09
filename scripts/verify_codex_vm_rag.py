"""Read-only fresh-stdio proof of the configured Codex VM RAG connection.

Does not invoke the chat/planner, import backend modules, ingest, or restart services.
An exit-zero routing proof is NOT a corpus completeness or authenticated-team proof.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
READ_TOOLS = {"ask_dita_expert", "check_rag_status", "search_jira_history", "query_test_evidence_graph"}
VARIABLES_URL = "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/output-gen-config/config-native-pdf-publish/native-pdf-variables"
LANGUAGE_URL = VARIABLES_URL.replace("native-pdf-variables", "native-pdf-language-variables")


def require(condition, code):
    if not condition:
        raise ValueError(code)


def load_profile():
    config = tomllib.loads((ROOT / ".codex/config.toml").read_text(encoding="utf-8"))
    profile = config["mcp_servers"]["aem_dataset_studio"]
    require(set(profile.get("enabled_tools", [])) == READ_TOOLS, "READ_ONLY_TOOL_FILTER_REQUIRED")
    require(profile.get("env", {}).get("AEM_STUDIO_READ_ONLY") == "true", "READ_ONLY_PROFILE_REQUIRED")
    expected = ROOT / "release-artifacts/aem-guides-mcp-client-windows/server.py"
    args = profile.get("args", [])
    require(len(args) == 1 and Path(args[0]).resolve() == expected.resolve(), "UNEXPECTED_STDIO_SERVER")
    require(Path(profile["command"]).is_file(), "CONFIGURED_PYTHON_MISSING")
    pin = profile["env"].get("AEM_STUDIO_EXPECTED_INDEX_FINGERPRINT", "")
    require(re.fullmatch(r"[a-f0-9]{64}", pin) is not None, "EXPECTED_INDEX_PIN_REQUIRED")
    return profile


def local_profile():
    config = tomllib.loads((ROOT / ".codex/config.toml").read_text(encoding="utf-8"))
    profile = config["mcp_servers"]["aem_local_dita_tools"]
    require(len(profile.get("args", [])) == 1 and Path(profile["args"][0]).resolve()
            == (ROOT / "mcp_server.py").resolve(), "LOCAL_TOOLS_SERVER_CHANGED")
    require(READ_TOOLS.issubset(set(profile.get("disabled_tools", []))), "LOCAL_SHARED_RAG_NOT_DISABLED")
    return profile


def forwarded_environment(profile):
    env = {key: os.environ[key] for key in profile.get("env_vars", []) if key in os.environ}
    env.update(profile.get("env", {}))
    env["PYTHONUTF8"] = "1"
    return env


def unpack(result):
    require(not getattr(result, "isError", False), "MCP_TOOL_ERROR")
    content = [item.text for item in result.content if getattr(item, "type", None) == "text"]
    require(len(content) == 1, "INVALID_TOOL_CONTENT")
    value = json.loads(content[0])
    require(isinstance(value, dict) and not value.get("error"), "INVALID_TOOL_PAYLOAD")
    return value


def identity(status, pin):
    item = status.get("index_identity", {})
    require(item.get("status") == "OK" and item.get("mode") == "REMOTE"
            and item.get("target_fingerprint") == pin, "VM_IDENTITY_MISMATCH")
    require(status.get("chroma_available") is True and status.get("embedding_available") is True,
            "VM_RAG_NOT_READY")
    collections = item.get("collections", {})
    for name in ("aem_guides", "dita_spec", "jira_qa"):
        row = collections.get(name, {})
        require(row.get("status") == "OK" and isinstance(row.get("id"), str)
                and type(row.get("count")) is int and row["count"] > 0, "INVALID_COLLECTION_IDENTITY")
    return item


def evidence_summary(packet, exact_url):
    evidence = packet.get("aem_guides_evidence", {})
    require(isinstance(evidence, dict) and not evidence.get("error"), "PRODUCT_LOOKUP_FAILED")
    rows = evidence.get("results")
    require(isinstance(rows, list), "INVALID_PRODUCT_LOOKUP")
    sources = sorted({row["source"].split("#", 1)[0].rstrip("/") for row in rows
                      if isinstance(row, dict) and isinstance(row.get("source"), str)})
    return {"result_count": len(rows), "exact_source_returned": exact_url in sources,
            "sources": sources, "payload_sha256": hashlib.sha256(
                json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}


async def verify(profile):
    # These are the installed MCP SDK contracts, shared with smoke_mcp_stdio_tools.py.
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    import httpx

    env = forwarded_environment(profile)
    pin = env["AEM_STUDIO_EXPECTED_INDEX_FINGERPRINT"]
    report = {"schema_version": "codex-vm-rag-stdio-proof-v1", "status": "STOP",
              "observed_at": datetime.now(timezone.utc).isoformat(),
              "fresh_stdio_process": True, "current_chat_reloaded": False,
              "corpus_write_requested": False, "service_restart_requested": False,
              "team_credentials_verified": False, "backend_loopback_verified": False,
              "full_uac_run_performed": False, "full_corpus_parity_proven": False}
    params = StdioServerParameters(command=profile["command"], args=profile["args"],
                                   cwd=profile.get("cwd"), env=env)
    with open(os.devnull, "w") as errlog:
        async with stdio_client(params, errlog=errlog) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                names = sorted(tool.name for tool in (await session.list_tools()).tools)
                require(set(names) == READ_TOOLS, "UNEXPECTED_EXPOSED_TOOLS")
                report["exposed_tools"] = names
                before = identity(unpack(await session.call_tool("check_rag_status", {})), pin)
                report["identity_before"] = before
                for label, question, source in (
                    ("language_variables_control", "Native PDF Language Variables output language UI language fallback", LANGUAGE_URL),
                    ("variables", "Native PDF Variables Variable Sets page layouts output preset", VARIABLES_URL),
                ):
                    packet = unpack(await session.call_tool("ask_dita_expert", {"question": question}))
                    report[label] = evidence_summary(packet, source)
                history = unpack(await session.call_tool("search_jira_history", {
                    "query": "table header editing", "top_k": 3}))
                require(history.get("searched_jira_qa") is True, "HISTORY_SEARCH_NOT_EXECUTED")
                report["history"] = {key: history.get(key) for key in (
                    "searched_jira_qa", "indexed_chunks", "match_count", "rejected_candidate_count")}
                after = identity(unpack(await session.call_tool("check_rag_status", {})), pin)
                require(before == after, "INDEX_CHANGED_DURING_PROBE")
                report["identity_stable"] = True
                # Direct HTTP is only the SAME read-only status contract, not a Chroma write.
                from urllib.parse import urlsplit
                origin = env["AEM_STUDIO_URL"].rstrip("/")
                parsed = urlsplit(origin)
                require(parsed.scheme in {"http", "https"} and parsed.hostname
                        and not parsed.username and not parsed.password and not parsed.query
                        and not parsed.fragment and parsed.path in {"", "/"}, "INVALID_ORIGIN")
                headers = {"Accept": "application/json"}
                token = env.get("AEM_STUDIO_TOKEN", "").strip()
                require(not token or parsed.scheme == "https", "TOKEN_REQUIRES_HTTPS")
                if token:
                    headers["Authorization"] = "Bearer " + token
                async with httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False) as client:
                    response = await client.post(origin + "/mcp", headers=headers, json={
                        "jsonrpc": "2.0", "id": "stdio-parity", "method": "tools/call",
                        "params": {"name": "check_rag_status", "arguments": {}}})
                    response.raise_for_status()
                    payload = response.json()
                    require(payload.get("id") == "stdio-parity" and not payload.get("error")
                            and not payload.get("result", {}).get("isError"), "DIRECT_STATUS_FAILED")
                    direct = identity(json.loads(payload["result"]["content"][0]["text"]), pin)
                    require(after == direct, "STDIO_HTTP_PARITY_MISMATCH")
                report["stdio_matches_gateway"] = True
                report["status"] = "PASS_FRESH_STDIO_VM_ROUTING_ONLY"
                report["variables_source_gap"] = not report["variables"]["exact_source_returned"]
        # Listing local tools never invokes a generator, indexer or file writer.
        local = local_profile()
        local_params = StdioServerParameters(command=local["command"], args=local["args"],
                                            cwd=local.get("cwd"), env=forwarded_environment(local))
        async with stdio_client(local_params, errlog=errlog) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                available = {tool.name for tool in (await session.list_tools()).tools}
                effective = available - set(local.get("disabled_tools", []))
                retained = {"generate_dita", "generate_dita_ot_output", "validate_dita_file",
                            "save_dita_file", "lookup_dita_construct"}
                require(retained.issubset(effective), "LOCAL_DITA_TOOLS_MISSING")
                require(not READ_TOOLS.intersection(effective), "DUPLICATE_SHARED_RAG_TOOLS")
                report["local_dita_tools_retained"] = sorted(retained)
                report["local_tools_invoked"] = []
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New report file only; never overwrite")
    parser.add_argument("--require-variables", action="store_true",
                        help="After VM ingestion, fail unless the exact Variables source is retrieved")
    args = parser.parse_args()
    try:
        report = asyncio.run(asyncio.wait_for(verify(load_profile()), timeout=180))
        if args.require_variables and report.get("variables_source_gap", True):
            report.update(status="STOP", reason="VARIABLES_SOURCE_NOT_RETRIEVED")
    except Exception as exc:
        report = {"schema_version": "codex-vm-rag-stdio-proof-v1", "status": "STOP",
                  "reason": "READ_ONLY_STDIO_PROBE_FAILED", "corpus_write_requested": False}
        # Only our fixed diagnostic codes are safe to print, never HTTP exceptions.
        if type(exc) is ValueError and re.fullmatch(r"[A-Z_]{3,80}", str(exc)):
            report["reason"] = str(exc)
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(rendered)
    print(rendered)
    return 0 if report["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
