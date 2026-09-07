#!/usr/bin/env bash
# Verify the dashboard-only VM deployment and preserved UAC backend gateways.
# Usage: bash vm-verify-setup.sh

set -Eeuo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_ROOT="/var/www/aem-studio"
BASE_URL="http://127.0.0.1:4502"
VM_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
FAILURES=0

pass() { printf '%b✓%b %s\n' "$GREEN" "$NC" "$*"; }
warn() { printf '%b⚠%b %s\n' "$YELLOW" "$NC" "$*"; }
fail() { printf '%b✗%b %s\n' "$RED" "$NC" "$*"; FAILURES=$((FAILURES + 1)); }

http_code() {
  curl -sS -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || true
}

redirect_location() {
  curl -sS -o /dev/null -D - "$1" 2>/dev/null \
    | awk 'BEGIN { IGNORECASE=1 } /^Location:/ { sub(/\r$/, "", $2); print $2; exit }' \
    || true
}

echo ""
printf '%b========================================%b\n' "$BLUE" "$NC"
printf '%bUAC dashboard VM verification%b\n' "$BLUE" "$NC"
printf '%b========================================%b\n' "$BLUE" "$NC"
echo ""

for command_name in curl nginx systemctl python3; do
  if command -v "$command_name" >/dev/null 2>&1; then
    pass "$command_name is installed"
  else
    fail "$command_name is not installed"
  fi
done

if [[ -f "$PROJECT_DIR/docker-compose.yml" ]]; then
  pass "docker-compose.yml is present"
else
  fail "docker-compose.yml is missing"
fi

if nginx -t >/dev/null 2>&1; then
  pass "Nginx configuration is valid"
else
  fail "Nginx configuration is invalid"
fi

if systemctl is-active --quiet nginx; then
  pass "system Nginx is running"
else
  fail "system Nginx is not running"
fi

if systemctl is-active --quiet aem-backend.service; then
  pass "systemd backend is running"
elif command -v docker >/dev/null 2>&1 \
  && docker inspect --format='{{.State.Health.Status}}' aem-studio-backend 2>/dev/null | grep -qx healthy; then
  pass "Docker backend is healthy"
else
  fail "no healthy systemd or Docker backend was found"
fi

if [[ -d "$WEB_ROOT" ]]; then
  pass "dashboard webroot exists"
else
  fail "dashboard webroot is missing: $WEB_ROOT"
fi

for filename in index.html dashboard_data.json; do
  if [[ -f "$WEB_ROOT/$filename" ]]; then
    pass "$filename is deployed"
  else
    fail "$filename is missing from the webroot"
  fi
done

if [[ -f "$WEB_ROOT/dashboard_data.json" ]] \
  && python3 -c 'import json,sys; value=json.load(open(sys.argv[1], encoding="utf-8")); assert isinstance(value, dict) and isinstance(value.get("runs"), list)' "$WEB_ROOT/dashboard_data.json"; then
  pass "dashboard_data.json has the expected runs contract"
else
  fail "dashboard_data.json is not valid dashboard data"
fi

if [[ -d "$WEB_ROOT" ]]; then
  UNEXPECTED="$(find "$WEB_ROOT" -mindepth 1 -maxdepth 1 \
    ! -name index.html ! -name dashboard_data.json -print -quit)"
  if [[ -z "$UNEXPECTED" ]]; then
    pass "webroot contains only dashboard artifacts"
  else
    fail "webroot contains stale or unexpected content: $UNEXPECTED"
  fi
fi

if curl -fsS "$BASE_URL/" 2>/dev/null | grep -q "UAC Eval Observability"; then
  pass "dashboard is served at the root URL"
else
  fail "dashboard root is not reachable or has unexpected content"
fi

if [[ "$(http_code "$BASE_URL/dashboard_data.json")" == "200" ]]; then
  pass "dashboard data is served"
else
  fail "dashboard data is not served with HTTP 200"
fi

for redirect_path in /eval-dashboard /eval-dashboard/; do
  CODE="$(http_code "$BASE_URL$redirect_path")"
  LOCATION="$(redirect_location "$BASE_URL$redirect_path")"
  if [[ "$CODE" == "308" && "$LOCATION" == "/" ]]; then
    pass "$redirect_path returns an exact 308 redirect to /"
  else
    fail "$redirect_path redirect mismatch (status=$CODE location=${LOCATION:-missing})"
  fi
done

for retired_path in /builder /chat /settings /dataset-explorer; do
  CODE="$(http_code "$BASE_URL$retired_path")"
  if [[ "$CODE" == "404" ]]; then
    pass "$retired_path returns 404"
  else
    fail "$retired_path should return 404 but returned $CODE"
  fi
done

if [[ "$(http_code http://127.0.0.1:8001/health)" == "200" ]]; then
  pass "backend health is reachable on localhost:8001"
else
  fail "backend health is not reachable on localhost:8001"
fi

if command -v ss >/dev/null 2>&1; then
  BACKEND_LISTENERS="$(ss -H -ltn 2>/dev/null | awk '$4 ~ /:8001$/ { print $4 }')"
  if grep -Eq '(^|\[)(0\.0\.0\.0|::|\*)[:\]]*8001$|^\*:8001$' <<<"$BACKEND_LISTENERS"; then
    fail "backend port 8001 is publicly bound: $BACKEND_LISTENERS"
  elif [[ -n "$BACKEND_LISTENERS" ]]; then
    pass "backend port 8001 is bound to loopback only"
  else
    fail "no listener was found on backend port 8001"
  fi
else
  warn "ss is unavailable; backend loopback binding could not be inspected"
fi

if [[ "$(http_code "$BASE_URL/health")" == "200" ]]; then
  pass "/health is proxied through Nginx"
else
  fail "/health proxy is not healthy"
fi

MCP_HEALTH_CODE="$(http_code "$BASE_URL/mcp/health")"
case "$MCP_HEALTH_CODE" in
  200)
    pass "/mcp/health is reachable and returned HTTP 200"
    ;;
  401|403)
    pass "/mcp/health reached the authenticated MCP boundary (HTTP $MCP_HEALTH_CODE without a token)"
    ;;
  *)
    fail "/mcp/health is not reachable through the expected MCP boundary (HTTP ${MCP_HEALTH_CODE:-000})"
    ;;
esac

ROOT_HEADERS="$(curl -sSI "$BASE_URL/" 2>/dev/null || true)"
JSON_HEADERS="$(curl -sSI "$BASE_URL/dashboard_data.json" 2>/dev/null || true)"
if grep -Eiq '^Cache-Control:.*no-store' <<<"$ROOT_HEADERS" \
  && grep -Eiq '^Cache-Control:.*no-store' <<<"$JSON_HEADERS"; then
  pass "HTML and JSON responses disable caching"
else
  fail "HTML and JSON must both include Cache-Control: no-store"
fi
if grep -Eiq '^Content-Security-Policy:' <<<"$ROOT_HEADERS" \
  && grep -Eiq '^X-Content-Type-Options:[[:space:]]*nosniff' <<<"$ROOT_HEADERS"; then
  pass "dashboard security headers are present"
else
  fail "dashboard security headers are missing"
fi

echo ""
printf '%bAccess URLs%b\n' "$BLUE" "$NC"
echo "  Dashboard: http://${VM_IP:-localhost}:4502/"
echo "  Health   : http://${VM_IP:-localhost}:4502/health"
echo "  API      : http://${VM_IP:-localhost}:4502/api/"
echo "  MCP      : http://${VM_IP:-localhost}:4502/mcp"
echo ""

if [[ "$FAILURES" -gt 0 ]]; then
  printf '%bVerification failed: %s check(s) failed.%b\n' "$RED" "$FAILURES" "$NC"
  exit 1
fi

printf '%bAll dashboard-only deployment checks passed.%b\n' "$GREEN" "$NC"
