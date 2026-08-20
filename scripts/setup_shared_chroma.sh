#!/usr/bin/env bash
# One-time setup: run ChromaDB as a shared server on the VM (localhost only) and
# expose it through the EXISTING Nginx port by routing the real /api/v2 path to it,
# restricted to the team subnet. Teammates then connect with just host+port (no
# custom client settings), because the Chroma client validates its API path as an
# enum (/api/v1 | /api/v2) and rejects any custom sub-path prefix.
#
# Safe to re-run (idempotent). Run as root on the VM:
#   sudo bash scripts/setup_shared_chroma.sh
#
# Optional overrides (env vars):
#   CHROMA_DB_PATH=/abs/path/to/backend/storage/chroma_db
#   CHROMA_PORT=8000   NGINX_PORT=4502   ALLOW_SUBNET=10.0.0.0/8
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CHROMA_DB_PATH="${CHROMA_DB_PATH:-$REPO_ROOT/backend/storage/chroma_db}"
CHROMA_HOST="127.0.0.1"
CHROMA_PORT="${CHROMA_PORT:-8000}"
NGINX_PORT="${NGINX_PORT:-4502}"
ALLOW_SUBNET="${ALLOW_SUBNET:-10.0.0.0/8}"   # team/corp private range; blocks public. Narrow if you like.
SERVICE="chroma"

echo "== Shared Chroma setup =="
echo "  chroma db path: $CHROMA_DB_PATH"
echo "  chroma        : ${CHROMA_HOST}:${CHROMA_PORT} (localhost only)"
echo "  nginx port    : ${NGINX_PORT}  ->  /api/v2/ (team-only: ${ALLOW_SUBNET})"
echo
[[ "$(id -u)" == "0" ]] || { echo "ERROR: run as root (sudo bash $0)"; exit 1; }
mkdir -p "$CHROMA_DB_PATH"

# ---- 1. install chromadb ----
command -v chroma >/dev/null 2>&1 || { echo "[1/5] installing chromadb ..."; (pip3 install --quiet chromadb || pip install --quiet chromadb); }
CHROMA_BIN="$(command -v chroma)"
echo "[1/5] chroma: $CHROMA_BIN"

# ---- 2. chroma as a systemd service (survives reboot); ensure single instance ----
echo "[2/5] systemd service ($SERVICE) ..."
pkill -f "chroma run .*--port ${CHROMA_PORT}" 2>/dev/null || true   # kill any stray nohup instance
sleep 1
if command -v systemctl >/dev/null 2>&1; then
  cat > "/etc/systemd/system/${SERVICE}.service" <<UNIT
[Unit]
Description=ChromaDB shared vector store (localhost)
After=network.target
[Service]
Type=simple
ExecStart=${CHROMA_BIN} run --host ${CHROMA_HOST} --port ${CHROMA_PORT} --path ${CHROMA_DB_PATH}
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable "${SERVICE}" >/dev/null 2>&1 || true
  systemctl restart "${SERVICE}"
else
  nohup "${CHROMA_BIN}" run --host "${CHROMA_HOST}" --port "${CHROMA_PORT}" --path "${CHROMA_DB_PATH}" > /var/log/chroma.log 2>&1 &
fi

# ---- 3. wait for heartbeat ----
echo "[3/5] waiting for chroma ..."
ok=""; for i in $(seq 1 20); do curl -sf "http://${CHROMA_HOST}:${CHROMA_PORT}/api/v2/heartbeat" >/dev/null && { ok=1; break; }; sleep 1; done
[[ -n "$ok" ]] || { echo "ERROR: chroma not up (journalctl -u ${SERVICE} / /var/log/chroma.log)"; exit 1; }
echo "      up: $(curl -s http://${CHROMA_HOST}:${CHROMA_PORT}/api/v2/heartbeat)"

# ---- 4. route /api/v2/ -> chroma in the LIVE nginx conf (never a .bak) ----
echo "[4/5] wiring nginx /api/v2/ -> chroma ..."
NGINX_CONF="$(grep -rlE "listen[[:space:]]+${NGINX_PORT}\b" /etc/nginx/ 2>/dev/null | grep -vE '\.bak|/backup|~$' | head -1 || true)"
[[ -n "$NGINX_CONF" ]] || { echo "ERROR: no live nginx conf with 'listen ${NGINX_PORT}'"; exit 1; }
echo "      conf: $NGINX_CONF"
cp "$NGINX_CONF" "${NGINX_CONF}.chromabak.$(date +%s)"

ALLOW_SUBNET="$ALLOW_SUBNET" CHROMA_PORT="$CHROMA_PORT" NGINX_PORT="$NGINX_PORT" \
python3 - "$NGINX_CONF" <<'PY'
import os, re, sys
p = sys.argv[1]; s = open(p).read()
# remove any earlier /chroma/ attempt (that path can't work with the client)
s = re.sub(r"\n[ \t]*location /chroma/ \{.*?\n[ \t]*\}\n", "\n", s, flags=re.S)
if "location /api/v2/" in s:
    open(p, "w").write(s); print("      /api/v2/ already present (cleaned old /chroma/)"); sys.exit(0)
cport = os.environ["CHROMA_PORT"]; nport = os.environ["NGINX_PORT"]; subnet = os.environ["ALLOW_SUBNET"].strip()
acl = "        allow 127.0.0.1;\n" + (f"        allow {subnet};\n        deny all;\n" if subnet else "")
block = ("    location /api/v2/ {\n" + acl +
         f"        proxy_pass http://127.0.0.1:{cport};\n"   # no trailing slash: keep the /api/v2 URI
         "        proxy_set_header Host $host;\n"
         "        proxy_read_timeout 300s;\n"
         "        client_max_body_size 50m;\n"
         "    }\n")
lines = s.splitlines(keepends=True)
for i, l in enumerate(lines):
    if re.search(r"listen\s+%s\b" % nport, l):
        lines.insert(i + 1, block); break
else:
    print("ERROR: could not find listen line"); sys.exit(1)
open(p, "w").write("".join(lines)); print("      inserted /api/v2/ (team-only) after listen %s" % nport)
PY

nginx -t && nginx -s reload && echo "      nginx reloaded"

# ---- 5. verify through the proxy ----
echo "[5/5] verifying ..."
curl -sf "http://127.0.0.1:${NGINX_PORT}/api/v2/heartbeat" >/dev/null \
  && echo "      OK: :${NGINX_PORT}/api/v2/heartbeat -> $(curl -s http://127.0.0.1:${NGINX_PORT}/api/v2/heartbeat)" \
  || echo "      WARN: proxy heartbeat failed - check the ${NGINX_PORT} block / SELinux (httpd_can_network_connect)"

VMIP="$(hostname -I 2>/dev/null | awk '{print $1}')"
cat <<EOF

== DONE ==
Teammates connect (no repo, no custom settings):

  import chromadb
  client = chromadb.HttpClient(host="${VMIP:-<vm-ip>}", port=${NGINX_PORT}, ssl=False)
  coll = client.get_or_create_collection("automation_features", metadata={"hnsw:space":"cosine"})

Rules: same embedding model all-MiniLM-L6-v2, same collection name, content-hash ids.
Manage: systemctl status|restart ${SERVICE}   (logs: journalctl -u ${SERVICE} -f)
Access is restricted to ${ALLOW_SUBNET} (+127.0.0.1).
EOF
