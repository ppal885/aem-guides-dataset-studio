#!/usr/bin/env bash
set -euo pipefail

MCP_URL="${MCP_URL:-http://10.42.46.78:4502/mcp}"
AUTH_TOKEN="${AUTH_TOKEN:-dev-bypass}"
SMOKE_JIRA_KEY="${GRAPH_SMOKE_JIRA_KEY:-}"
SMOKE_CUSTOMER="${GRAPH_SMOKE_CUSTOMER:-}"
DOCUMENT_QUERY="${GRAPH_SMOKE_DOCUMENT_QUERY:-What is the documented AEM Guides image map hotspot behaviour?}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

if [[ -z "$SMOKE_JIRA_KEY" || -z "$SMOKE_CUSTOMER" ]]; then
  echo "ERROR: set GRAPH_SMOKE_JIRA_KEY and GRAPH_SMOKE_CUSTOMER to a Jira with known same- and cross-customer mechanism history." >&2
  exit 2
fi

call_mcp() {
  local body="$1"
  local output="$2"
  curl -fsS \
    -H "Authorization: Bearer $AUTH_TOKEN" \
    -H "Content-Type: application/json" \
    --data "$body" \
    "$MCP_URL" >"$output"
}

call_mcp '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' "$TMP_DIR/tools.json"
python3 - "$TMP_DIR/tools.json" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
names = {item["name"] for item in payload["result"]["tools"]}
required = {"query_test_evidence_graph", "check_rag_status", "search_jira_history", "ask_dita_expert"}
missing = sorted(required - names)
if missing:
    raise SystemExit(f"missing MCP tools: {missing}")
print("tools/list: ok")
PY

call_mcp '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"check_rag_status","arguments":{"tenant_id":"kone"}}}' "$TMP_DIR/status.json"
python3 - "$TMP_DIR/status.json" <<'PY'
import json, os, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
result = json.loads(payload["result"]["content"][0]["text"])
graph = result.get("evidence_graph") or {}
if not graph.get("active_generation_id") or graph.get("status") not in {"ready", "degraded"}:
    raise SystemExit(f"evidence graph not query-ready: {graph}")
integrity = graph.get("integrity") or {}
if not integrity.get("sha256"):
    raise SystemExit(f"active generation has no integrity manifest: {graph}")
if os.getenv("REQUIRE_GRAPH_HMAC_SEAL", "true").lower() in {"1", "true", "yes", "on"} and not integrity.get("sealed"):
    raise SystemExit(f"active generation is not HMAC-sealed: {graph}")
if not isinstance(graph.get("query_health"), dict):
    raise SystemExit(f"query telemetry is unavailable: {graph}")
print(f"graph status: {graph['status']} generation={graph['active_generation_id']}")
PY

DOCUMENT_BODY="$(python3 - "$DOCUMENT_QUERY" <<'PY'
import json, sys
print(json.dumps({
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
        "name": "query_test_evidence_graph",
        "arguments": {
            "query": sys.argv[1],
            "max_depth": 2,
            "top_k": 10,
            "max_paths": 20,
            "tenant_id": "kone",
        },
    },
}))
PY
)"
call_mcp "$DOCUMENT_BODY" "$TMP_DIR/documented.json"
python3 - "$TMP_DIR/documented.json" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
result = json.loads(payload["result"]["content"][0]["text"])
required = {"documented_behaviors", "same_mechanism_jira_history", "dita_constraints", "evidence_paths"}
if not result.get("available") or not required.issubset(result):
    raise SystemExit(f"documented-behaviour query failed: {result}")
if not result["documented_behaviors"]:
    raise SystemExit(f"documented-behaviour query returned no behavior: {result}")
if any(not item.get("leaf_citations") for item in result["documented_behaviors"]):
    raise SystemExit(f"documented behavior is missing leaf citations: {result}")
runtime = result.get("query_runtime") or {}
if not isinstance(runtime.get("duration_ms"), int) or not isinstance(runtime.get("cache_hit"), bool):
    raise SystemExit(f"query runtime/cache metadata is missing: {result}")
print(f"documented query: ok paths={len(result['evidence_paths'])}")
PY

BODY="$(python3 - "$SMOKE_JIRA_KEY" "$SMOKE_CUSTOMER" "false" <<'PY'
import json, sys
print(json.dumps({
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
        "name": "query_test_evidence_graph",
        "arguments": {
            "query": f"Find same-mechanism regressions for {sys.argv[1]}",
            "jira_key": sys.argv[1],
            "customer": sys.argv[2],
            "include_cross_customer": sys.argv[3].lower() == "true",
            "max_depth": 2,
            "top_k": 10,
            "max_paths": 20,
            "tenant_id": "kone",
        },
    },
}))
PY
)"
call_mcp "$BODY" "$TMP_DIR/jira-same.json"
python3 - "$TMP_DIR/jira-same.json" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
result = json.loads(payload["result"]["content"][0]["text"])
matches = result.get("same_mechanism_jira_history") or []
if not result.get("available") or not matches or any(item.get("cross_customer") for item in matches):
    raise SystemExit(f"same-customer same-mechanism query failed: {result}")
print(f"same-customer query: ok matches={len(matches)}")
PY

BODY="$(python3 - "$SMOKE_JIRA_KEY" "$SMOKE_CUSTOMER" "true" <<'PY'
import json, sys
print(json.dumps({
    "jsonrpc": "2.0",
    "id": 5,
    "method": "tools/call",
    "params": {
        "name": "query_test_evidence_graph",
        "arguments": {
            "query": f"Find same-mechanism regressions for {sys.argv[1]}",
            "jira_key": sys.argv[1],
            "customer": sys.argv[2],
            "include_cross_customer": sys.argv[3].lower() == "true",
            "max_depth": 2,
            "top_k": 10,
            "max_paths": 20,
            "tenant_id": "kone",
        },
    },
}))
PY
)"
call_mcp "$BODY" "$TMP_DIR/jira-cross.json"
python3 - "$TMP_DIR/jira-cross.json" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
result = json.loads(payload["result"]["content"][0]["text"])
matches = result.get("same_mechanism_jira_history") or []
aggregate = result.get("cross_customer_aggregate") or {}
has_cross = any(item.get("cross_customer") for item in matches) or aggregate.get("same_mechanism_ticket_count", 0) > 0
if not result.get("available") or not has_cross:
    raise SystemExit(f"cross-customer same-mechanism query failed: {result}")
print("cross-customer query: ok")
PY

echo "Evidence graph MCP smoke tests passed via $MCP_URL"
