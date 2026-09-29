"""Call the Dataset Studio backend's evidence tools over its JSON-RPC endpoint and record the result.

WHY THIS EXISTS
---------------
`ask_dita_expert` and `search_jira_history` are served by the Dataset Studio backend at
`<AEM_STUDIO_URL>/mcp`. When the MCP server is not registered in the current Claude, Codex or
Copilot session, the tools do not appear in the tool list, but the backend still answers. A tool
missing from the session is therefore NOT an unavailable source: call it through this script. A
source is unavailable only when this route also fails, and that failure is recorded.

WHAT IT WRITES
--------------
Results are appended to UAC_EVIDENCE.json (see uac_completeness_check.py):
  rag        -> "rag_probes":       {"question", "result": ok|empty|error, "summary"}
  history    -> "history_attempts": {"source", "query", "result": ok|empty|unavailable, "count"}
  preflight  -> "preflight.product_rag" and "preflight.jira_history" routes and status

Usage:
    python vm_evidence_call.py preflight --evidence UAC_EVIDENCE.json [--base-url URL]
    python vm_evidence_call.py rag --question "..." [--question "..."] --evidence UAC_EVIDENCE.json
    python vm_evidence_call.py history --query "..." [--component Publishing] --evidence UAC_EVIDENCE.json

The base URL comes from --base-url or AEM_STUDIO_URL; AEM_STUDIO_TOKEN is sent as a bearer token
when set. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable

EVIDENCE_FILE = "UAC_EVIDENCE.json"
SUMMARY_CHARS = 600
Transport = Callable[[str, dict], dict]


def endpoint(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("no backend URL: pass --base-url or set AEM_STUDIO_URL")
    return base if base.endswith("/mcp") else base + "/mcp"


def http_transport(url: str, payload: dict) -> dict:
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("AEM_STUDIO_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=240) as resp:
        return json.loads(resp.read())


def rpc(url: str, method: str, params: dict | None = None, transport: Transport = http_transport) -> Any:
    data = transport(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
    if "error" in data:
        raise RuntimeError(str(data["error"].get("message") or data["error"])[:200])
    return data.get("result")


def tool_text(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    return "\n".join(str(c.get("text") or "") for c in result.get("content") or [] if isinstance(c, dict))


def _summary(text: str) -> str:
    return " ".join(text.split())[:SUMMARY_CHARS]


def load_evidence(path: Path) -> dict:
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError(f"{path.name} must be a JSON object")
        return data
    return {}


def save_evidence(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def preflight(url: str, transport: Transport = http_transport) -> dict:
    """Record whether the backend route serves the RAG and history tools."""
    route = f"backend JSON-RPC {url}"
    try:
        names = {t.get("name") for t in (rpc(url, "tools/list", transport=transport) or {}).get("tools") or []}
    except Exception as exc:  # noqa: BLE001 - any failure is recorded, never hidden
        reason = f"{type(exc).__name__}: {str(exc)[:160]}"
        down = {"status": "unavailable", "attempted_routes": ["session MCP tool", route], "reason": reason}
        return {"product_rag": dict(down), "jira_history": dict(down)}

    def state(tool: str) -> dict:
        if tool in names:
            return {"status": "available", "route": route}
        return {"status": "unavailable", "attempted_routes": ["session MCP tool", route],
                "reason": f"{tool} is not served by {url}"}
    return {"product_rag": state("ask_dita_expert"), "jira_history": state("search_jira_history")}


def rag_probe(url: str, question: str, transport: Transport = http_transport) -> dict:
    try:
        text = tool_text(rpc(url, "tools/call", {"name": "ask_dita_expert", "arguments": {"question": question}},
                             transport=transport))
    except Exception as exc:  # noqa: BLE001
        return {"question": question, "result": "error", "summary": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return {"question": question, "result": "ok" if text.strip() else "empty", "summary": _summary(text)}


def history_attempt(url: str, query: str, component: str = "", transport: Transport = http_transport) -> dict:
    args = {"query": query, "component": component}
    try:
        text = tool_text(rpc(url, "tools/call", {"name": "search_jira_history", "arguments": args},
                             transport=transport))
    except Exception as exc:  # noqa: BLE001
        return {"source": "search_jira_history", "query": query, "component": component,
                "result": "unavailable", "count": 0, "summary": f"{type(exc).__name__}: {str(exc)[:200]}"}
    try:
        payload = json.loads(text)
    except ValueError:
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        # Structured result: only qualified matches count; rejected candidates are kept apart.
        keys = [str(r.get("jira_key") or "") for r in payload["results"] if isinstance(r, dict)]
        rejected = [str(r.get("jira_key") or "") for r in payload.get("rejected_candidates") or [] if isinstance(r, dict)]
    else:
        keys = sorted(set(re.findall(r"\b[A-Z][A-Z0-9]+-\d+\b", text)))
        rejected = []
    keys = [k for k in keys if k]
    return {"source": "search_jira_history", "query": query, "component": component,
            "result": "ok" if keys else "empty", "count": len(keys), "keys": keys[:30],
            "rejected_keys": [k for k in rejected if k][:30], "summary": _summary(text)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("preflight", "rag", "history"))
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--base-url", default=os.environ.get("AEM_STUDIO_URL", ""))
    parser.add_argument("--question", action="append", default=[])
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--component", default="")
    args = parser.parse_args(argv)
    url = endpoint(args.base_url)
    evidence = load_evidence(args.evidence)
    if args.command == "preflight":
        evidence.setdefault("preflight", {}).update(preflight(url))
        print(json.dumps(evidence["preflight"], indent=2))
    elif args.command == "rag":
        for question in args.question:
            probe = rag_probe(url, question)
            evidence.setdefault("rag_probes", []).append(probe)
            print(f"[{probe['result']}] {question}\n  {probe['summary'][:300]}")
    else:
        for query in args.query:
            attempt = history_attempt(url, query, args.component)
            evidence.setdefault("history_attempts", []).append(attempt)
            print(f"[{attempt['result']}] {query} -> {attempt['count']} key(s) {' '.join(attempt.get('keys', [])[:10])}")
    save_evidence(args.evidence, evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
