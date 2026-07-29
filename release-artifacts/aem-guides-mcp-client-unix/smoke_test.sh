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

with httpx.Client(timeout=60) as client:
    health = client.get(f"{url}/health", headers=headers)
    health.raise_for_status()
    health_payload = health.json()
    print("health.status:", health_payload.get("status"))
    print("health.rag_ready:", health_payload.get("rag_ready"))

    rag = client.get(f"{url}/api/v1/ai/rag-status", headers=headers, params={"tenant_id": "default"})
    rag.raise_for_status()
    rag_payload = rag.json()
    print("rag.chroma_available:", rag_payload.get("chroma_available"))
    print("rag.aem_guides.chunk_count:", (rag_payload.get("aem_guides") or {}).get("chunk_count"))
    print("rag.dita_spec.chunk_count:", (rag_payload.get("dita_spec") or {}).get("chunk_count"))
    print("rag.jira_qa.chunk_count:", (rag_payload.get("jira_qa") or {}).get("chunk_count"))

    lookup = client.post(
        f"{url}/api/v1/mcp/lookup-aem-guides",
        headers=headers,
        json={"query": "AEM Guides postprocessing ignored paths enabled paths rules"},
    )
    lookup.raise_for_status()
    lookup_payload = lookup.json()
    print("lookup.count:", lookup_payload.get("count"))
    if lookup_payload.get("results"):
        first = lookup_payload["results"][0]
        print("lookup.first_source:", first.get("source"))

module_path = Path("server.py").resolve()
spec = importlib.util.spec_from_file_location("aem_guides_mcp_client_server", module_path)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

async def check_tools():
    names = [tool.name for tool in await mod.list_tools()]
    expected = ["ask_dita_expert", "upload_dataset_to_aem"]
    print("wrapper.tools:", names)
    if names != expected:
        raise SystemExit(f"Unexpected MCP tools exposed: {names}")

asyncio.run(check_tools())
print("ok")
PY
