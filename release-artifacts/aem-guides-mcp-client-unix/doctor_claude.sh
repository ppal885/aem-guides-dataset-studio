#!/usr/bin/env bash
set -euo pipefail

CLIENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$CLIENT_DIR"

load_env() {
  local env_file="$1"
  [[ -f "$env_file" ]] || return 0
  while IFS= read -r raw || [[ -n "$raw" ]]; do
    raw="${raw#"${raw%%[![:space:]]*}"}"
    raw="${raw%"${raw##*[![:space:]]}"}"
    [[ -z "$raw" || "$raw" == \#* || "$raw" != *=* ]] && continue
    local key="${raw%%=*}"
    local value="${raw#*=}"
    if [[ -z "${!key:-}" ]]; then
      export "$key=$value"
    fi
  done < "$env_file"
}

check() {
  local name="$1"
  local ok="$2"
  local detail="${3:-}"
  if [[ "$ok" == "true" ]]; then
    printf '[OK] %s%s\n' "$name" "${detail:+ - $detail}"
  else
    printf '[FAIL] %s%s\n' "$name" "${detail:+ - $detail}"
  fi
}

load_env ".env"

BACKEND_URL="${AEM_STUDIO_URL:-http://10.42.46.78:4502}"
BACKEND_URL="${BACKEND_URL%/}"
TOKEN="${AEM_STUDIO_TOKEN:-dev-bypass}"

echo "AEM Guides MCP Client Doctor"
echo "Client dir: $CLIENT_DIR"
echo "Backend:    $BACKEND_URL"
echo

[[ -x ".venv/bin/python" ]] && check "Python venv" true "$CLIENT_DIR/.venv/bin/python" || check "Python venv" false "$CLIENT_DIR/.venv/bin/python"
[[ -f "server.py" ]] && check "server.py" true "$CLIENT_DIR/server.py" || check "server.py" false "$CLIENT_DIR/server.py"
[[ -f ".mcp.json" ]] && check ".mcp.json" true "$CLIENT_DIR/.mcp.json" || check ".mcp.json" false "$CLIENT_DIR/.mcp.json"
[[ -f "claude-mcp-server.json" ]] && check "claude-mcp-server.json" true "$CLIENT_DIR/claude-mcp-server.json" || check "claude-mcp-server.json" false "$CLIENT_DIR/claude-mcp-server.json"
[[ -f "config/aem-upload.properties" ]] && check "local AEM upload config" true "$CLIENT_DIR/config/aem-upload.properties" || check "local AEM upload config" false "$CLIENT_DIR/config/aem-upload.properties (or pass credentials as tool args)"
GRAPH_CONTRACT=".claude/skills/test-plan-generation/references/evidence-graph-contract.md"
if [[ -f "$GRAPH_CONTRACT" ]] && grep -q 'shadow' "$GRAPH_CONTRACT" && grep -q 'augment' "$GRAPH_CONTRACT" && grep -q 'used_for_plan' "$GRAPH_CONTRACT"; then
  check "Phase B skill contract" true "$CLIENT_DIR/$GRAPH_CONTRACT"
else
  check "Phase B skill contract" false "missing shadow/augment/used_for_plan contract markers"
fi
SKILL_ROOT=".claude/skills/test-plan-generation"
SKILL_FILE="$SKILL_ROOT/SKILL.md"
AC_CONTRACT="$SKILL_ROOT/scripts/ac_contract.py"
AC_EXTRACTOR="$SKILL_ROOT/scripts/extract_acs.py"
PERFORMANCE_CONTRACT="$SKILL_ROOT/scripts/performance_contract.py"
PERFORMANCE_REFERENCE="$SKILL_ROOT/references/performance-assessment-contract.md"
GOLDEN_BENCHMARK_REFERENCE="$SKILL_ROOT/references/golden-benchmark.md"
COMPACT_RENDERER="$SKILL_ROOT/scripts/render_compact_view.py"
if [[ -f "$SKILL_FILE" && -f "$AC_CONTRACT" && -f "$AC_EXTRACTOR" && -f "$PERFORMANCE_CONTRACT" && -f "$PERFORMANCE_REFERENCE" && -f "$GOLDEN_BENCHMARK_REFERENCE" && -f "$COMPACT_RENDERER" ]] \
    && grep -q 'aem-guides-ac-v1' "$SKILL_FILE" \
    && grep -q 'aem-guides-performance-assessment-v1' "$SKILL_FILE" \
    && grep -q 'Performance Analysis' "$SKILL_FILE" \
    && grep -q 'Acceptance Criteria' "$SKILL_FILE" \
    && grep -q 'Regression Areas' "$SKILL_FILE" \
    && grep -q 'Past Jiras' "$SKILL_FILE" \
    && grep -q 'Open Questions' "$SKILL_FILE" \
    && grep -q 'golden-benchmark.md' "$SKILL_FILE"; then
  check "Canonical AC and compact UI contract" true "$CLIENT_DIR/$SKILL_ROOT"
else
  check "Canonical AC and compact UI contract" false "missing AC/performance scripts or four-section UI markers"
fi

if command -v node >/dev/null 2>&1; then
  NODE_VERSION="$(node -p "process.versions.node")"
  NODE_MAJOR="$(node -p "process.versions.node.split('.')[0]")"
  if [[ "$NODE_MAJOR" -ge 18 ]]; then
    check "Node.js 18+ for local upload" true "version=$NODE_VERSION"
  else
    check "Node.js 18+ for local upload" false "version=$NODE_VERSION"
  fi
else
  check "Node.js 18+ for local upload" false "Install Node.js and rerun setup."
fi
command -v npm >/dev/null 2>&1 && check "npm on PATH" true "required for setup/install" || check "npm on PATH" false "required for setup/install"
[[ -d "node_modules/@adobe/aem-upload" ]] && check "@adobe/aem-upload dependency" true "$CLIENT_DIR/node_modules/@adobe/aem-upload" || check "@adobe/aem-upload dependency" false "Run setup/install to install npm dependencies."

if command -v curl >/dev/null 2>&1; then
  if curl -fsS -H "Authorization: Bearer $TOKEN" "$BACKEND_URL/mcp/health" >/tmp/aem-guides-mcp-health.json; then
    check "VM /mcp/health" true "$(cat /tmp/aem-guides-mcp-health.json)"
  else
    check "VM /mcp/health" false "check VPN, backend URL, token, and VM service"
  fi
  if curl -fsS -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
      "$BACKEND_URL/mcp" >/tmp/aem-guides-mcp-tools.json && python3 - <<'PY'
import json
from pathlib import Path

payload = json.loads(Path("/tmp/aem-guides-mcp-tools.json").read_text(encoding="utf-8"))
names = {item.get("name") for item in (payload.get("result") or {}).get("tools", [])}
required = {"ask_dita_expert", "search_jira_history", "query_test_evidence_graph", "check_rag_status"}
missing = sorted(required - names)
print("remote_tools:", ", ".join(sorted(names)))
raise SystemExit(1 if missing else 0)
PY
  then
    check "VM evidence MCP tools" true "direct RAG, Jira history, graph query, and graph status exposed"
  else
    check "VM evidence MCP tools" false "one or more required /mcp tools are missing"
  fi
else
  check "curl on PATH" false "install curl or verify VM manually"
fi

if command -v claude >/dev/null 2>&1; then
  echo
  echo "claude mcp list:"
  claude mcp list
else
  check "Claude Code CLI on PATH" false "register after Claude Code is available"
fi

if [[ -x ".venv/bin/python" ]]; then
  echo
  echo "Local wrapper tool check:"
  ".venv/bin/python" - <<'PY'
import asyncio
import importlib.util
from pathlib import Path

module_path = Path("server.py").resolve()
spec = importlib.util.spec_from_file_location("aem_guides_mcp_client_server", module_path)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

async def main():
    tools = await mod.list_tools()
    names = [tool.name for tool in tools]
    expected = [
        "ask_dita_expert",
        "search_jira_history",
        "query_test_evidence_graph",
        "check_rag_status",
        "upload_dataset_to_aem",
    ]
    removed = [
        "health_check",
        "lookup_aem_guides",
        "lookup_dita_spec",
        "lookup_dita_attribute",
        "search_jira_issues",
        "guides_test_plan_generator",
        "test_plan_pipeline",
        "generate_dita",
        "generate_from_text",
        "generate_dita_ot_output",
        "upload_mcp_generated_data_to_aem",
        "review_dita_xml",
        "fix_dita_xml",
        "list_jobs",
        "get_job_status",
    ]
    print("tool_count:", len(names))
    print("exact_minimal_surface:", names == expected)
    for required in expected:
        print(f"{required}:", required in names)
    print("removed_tools_exposed:", [name for name in removed if name in names])

asyncio.run(main())
PY
else
  echo
  echo "Local wrapper tool check skipped because .venv is missing. Run ./install.sh first."
fi
