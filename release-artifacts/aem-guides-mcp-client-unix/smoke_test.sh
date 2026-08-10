#!/usr/bin/env bash
set -euo pipefail

CLIENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$CLIENT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Missing .venv. Run ./install.sh first."
  exit 1
fi

".venv/bin/python" - <<'PY'
import json
import os
import asyncio
import importlib.util
import shutil
import sys
from pathlib import Path

import httpx

for raw in Path(".env").read_text(encoding="utf-8").splitlines():
    raw = raw.strip()
    if raw and not raw.startswith("#") and "=" in raw:
        key, value = raw.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

url = os.environ.get("AEM_STUDIO_URL", "").rstrip("/")
token = os.environ.get("AEM_STUDIO_TOKEN", "dev-bypass")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

if not url:
    raise SystemExit("AEM_STUDIO_URL missing in .env")

node_path = shutil.which("node")
print("node.available:", bool(node_path))
if not node_path:
    raise SystemExit("Node.js missing; local AEM upload cannot run")
print("aem_upload.node_module:", Path("node_modules/@adobe/aem-upload").exists())
if not Path("node_modules/@adobe/aem-upload").exists():
    raise SystemExit("@adobe/aem-upload missing; rerun setup/install")

skill_root = Path(".claude/skills/test-plan-generation")
required_skill_files = [
    skill_root / "SKILL.md",
    skill_root / "scripts/ac_contract.py",
    skill_root / "scripts/extract_acs.py",
    skill_root / "scripts/performance_contract.py",
    skill_root / "scripts/render_compact_view.py",
    skill_root / "references/performance-assessment-contract.md",
    skill_root / "references/golden-benchmark.md",
]
missing_skill_files = [str(path) for path in required_skill_files if not path.is_file()]
if missing_skill_files:
    raise SystemExit(f"Missing test-plan skill contract files: {missing_skill_files}")
skill_text = required_skill_files[0].read_text(encoding="utf-8")
required_markers = (
    "aem-guides-ac-v1",
    "aem-guides-performance-assessment-v1",
    "Performance Analysis",
    "Acceptance Criteria",
    "Regression Areas",
    "Past Jiras",
    "Open Questions",
    "golden-benchmark.md",
)
missing_markers = [marker for marker in required_markers if marker not in skill_text]
if missing_markers:
    raise SystemExit(f"Missing test-plan skill contract markers: {missing_markers}")
sys.path.insert(0, str((skill_root / "scripts").resolve()))
from ac_contract import AC_SCHEMA_VERSION
from performance_contract import PERFORMANCE_SCHEMA_VERSION
from render_compact_view import SOURCE_SECTIONS

if AC_SCHEMA_VERSION != "aem-guides-ac-v1":
    raise SystemExit(f"Unexpected AC schema: {AC_SCHEMA_VERSION}")
if PERFORMANCE_SCHEMA_VERSION != "aem-guides-performance-assessment-v1":
    raise SystemExit(f"Unexpected performance schema: {PERFORMANCE_SCHEMA_VERSION}")
if SOURCE_SECTIONS != (
    "Acceptance Criteria",
    "Regression Areas",
    "Known Jira Bugs / Past Similar Tickets",
    "Open Questions",
):
    raise SystemExit(f"Unexpected compact UI source sections: {SOURCE_SECTIONS}")
print("test_plan_skill.contract:", AC_SCHEMA_VERSION)
print("test_plan_skill.performance_contract:", PERFORMANCE_SCHEMA_VERSION)

def rpc(client, method, params):
    response = client.post(
        f"{url}/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": method, "method": method, "params": params},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise SystemExit(f"MCP error: {payload['error']}")
    return payload.get("result") or {}


def tool_result(client, name, arguments):
    result = rpc(client, "tools/call", {"name": name, "arguments": arguments})
    content = result.get("content") or []
    text = content[0].get("text", "{}") if content else "{}"
    return json.loads(text)


with httpx.Client(timeout=60) as client:
    listed = rpc(client, "tools/list", {})
    remote_names = {item.get("name") for item in listed.get("tools", [])}
    required_remote = {"ask_dita_expert", "search_jira_history", "query_test_evidence_graph", "check_rag_status"}
    missing = sorted(required_remote - remote_names)
    print("remote_mcp.tools:", sorted(remote_names))
    if missing:
        raise SystemExit(f"Missing remote MCP tools: {missing}")

    rag_payload = tool_result(client, "check_rag_status", {"tenant_id": "kone"})
    print("rag.chroma_available:", rag_payload.get("chroma_available"))
    print("rag.collections:", rag_payload.get("collections"))
    print("graph.status:", (rag_payload.get("evidence_graph") or {}).get("status"))

    graph_payload = tool_result(
        client,
        "query_test_evidence_graph",
        {"query": "documented AEM Guides image map hotspot behaviour", "tenant_id": "kone"},
    )
    if "status" not in graph_payload or "evidence_paths" not in graph_payload or "query_runtime" not in graph_payload:
        raise SystemExit(f"Invalid graph query contract: {graph_payload}")
    print("graph.query.status:", graph_payload.get("status"))

module_path = Path("server.py").resolve()
spec = importlib.util.spec_from_file_location("aem_guides_mcp_client_server", module_path)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

async def check_tools():
    names = [tool.name for tool in await mod.list_tools()]
    expected = [
        "ask_dita_expert",
        "search_jira_history",
        "query_test_evidence_graph",
        "check_rag_status",
        "upload_dataset_to_aem",
    ]
    print("wrapper.tools:", names)
    if names != expected:
        raise SystemExit(f"Unexpected MCP tools exposed: {names}")

asyncio.run(check_tools())
print("ok")
PY
