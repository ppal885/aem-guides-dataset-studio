#!/usr/bin/env bash
# One-time setup: run ChromaDB as a shared server on the VM (localhost only) and
# expose it through the EXISTING Nginx port as a /chroma/ sub-path, so teammates
# can store/query RAG chunks against one shared DB.
#
# Safe to re-run (idempotent): it skips steps already done and backs up nginx conf.
#
# Usage (on the VM, as root):
#   sudo bash scripts/setup_shared_chroma.sh
#
# Optional overrides (env vars):
#   CHROMA_DB_PATH=/abs/path/to/backend/storage/chroma_db
#   CHROMA_PORT=8000      NGINX_PORT=4502      ALLOW_SUBNET=10.42.0.0/16
set -euo pipefail

# ---- config -----------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CHROMA_DB_PATH="${CHROMA_DB_PATH:-$REPO_ROOT/backend/storage/chroma_db}"
CHROMA_HOST="127.0.0.1"
CHROMA_PORT="${CHROMA_PORT:-8000}"
NGINX_PORT="${NGINX_PORT:-4502}"
ALLOW_SUBNET="${ALLOW_SUBNET:-}"     # e.g. 10.42.0.0/16 ; empty = no IP allowlist
SERVICE="chroma"

echo "== Shared Chroma setup =="
echo "  repo root     : $REPO_ROOT"
echo "  chroma db path: $CHROMA_DB_PATH"
echo "  chroma        : ${CHROMA_HOST}:${CHROMA_PORT} (localhost only)"
echo "  nginx port    : ${NGINX_PORT}  ->  /chroma/ sub-path"
echo "  allow subnet  : ${ALLOW_SUBNET:-<none>}"
echo

if [[ "$(id -u)" != "0" ]]; then
  echo "ERROR: run as root (sudo bash $0)"; exit 1
fi
mkdir -p "$CHROMA_DB_PATH"

# ---- 1. install chromadb ----------------------------------------------------
if ! command -v chroma >/dev/null 2>&1; then
  echo "[1/5] installing chromadb ..."
  (pip3 install --quiet chromadb || pip install --quiet chromadb)
else
  echo "[1/5] chromadb already installed ($(command -v chroma))"
fi
CHROMA_BIN="$(command -v chroma)"

# ---- 2. chroma as a systemd service (survives reboot) -----------------------
if command -v systemctl >/dev/null 2>&1; then
  echo "[2/5] writing systemd service ($SERVICE) ..."
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
  echo "[2/5] no systemd; starting chroma with nohup ..."
  pkill -f "chroma run .*--port ${CHROMA_PORT}" 2>/dev/null || true
  nohup "${CHROMA_BIN}" run --host "${CHROMA_HOST}" --port "${CHROMA_PORT}" --path "${CHROMA_DB_PATH}" \
    > /var/log/chroma.log 2>&1 &
fi

# ---- 3. wait for chroma heartbeat ------------------------------------------
echo "[3/5] waiting for chroma heartbeat ..."
ok=""
for i in $(seq 1 20); do
  if curl -sf "http://${CHROMA_HOST}:${CHROMA_PORT}/api/v2/heartbeat" >/dev/null; then ok=1; break; fi
  sleep 1
done
if [[ -z "$ok" ]]; then echo "ERROR: chroma did not come up on ${CHROMA_PORT} (check: journalctl -u ${SERVICE} or /var/log/chroma.log)"; exit 1; fi
echo "      chroma up: $(curl -s http://${CHROMA_HOST}:${CHROMA_PORT}/api/v2/heartbeat)"

# ---- 4. add /chroma/ location to the nginx block on NGINX_PORT --------------
echo "[4/5] wiring nginx /chroma/ -> ${CHROMA_HOST}:${CHROMA_PORT} ..."
NGINX_CONF="$(grep -rl "listen ${NGINX_PORT}" /etc/nginx/ 2>/dev/null | head -1 || true)"
if [[ -z "$NGINX_CONF" ]]; then echo "ERROR: no nginx conf found with 'listen ${NGINX_PORT}'"; exit 1; fi
echo "      conf: $NGINX_CONF"
cp "$NGINX_CONF" "${NGINX_CONF}.bak.$(date +%s)"

ALLOW_SUBNET="$ALLOW_SUBNET" CHROMA_PORT="$CHROMA_PORT" NGINX_PORT="$NGINX_PORT" \
python3 - "$NGINX_CONF" <<'PY'
import os, sys
p = sys.argv[1]
lines = open(p).read().splitlines(keepends=True)
if any("location /chroma/" in l for l in lines):
    print("      /chroma/ location already present - skipping")
    sys.exit(0)
allow = os.environ.get("ALLOW_SUBNET", "").strip()
cport = os.environ.get("CHROMA_PORT", "8000")
nport = os.environ.get("NGINX_PORT", "4502")
acl = (f"        allow {allow};\n        deny all;\n" if allow else "")
block = (
    "    location /chroma/ {\n"
    f"{acl}"
    f"        proxy_pass http://127.0.0.1:{cport}/;\n"
    "        proxy_set_header Host $host;\n"
    "        proxy_read_timeout 300s;\n"
    "        client_max_body_size 50m;\n"
    "    }\n"
)
for i, l in enumerate(lines):
    if f"listen {nport}" in l:
        lines.insert(i + 1, block)
        break
else:
    print("ERROR: could not find 'listen %s' line to insert after" % nport); sys.exit(1)
open(p, "w").write("".join(lines))
print("      inserted /chroma/ location")
PY

nginx -t
nginx -s reload
echo "      nginx reloaded"

# ---- 5. verify through the proxy -------------------------------------------
echo "[5/5] verifying proxy ..."
if curl -sf "http://127.0.0.1:${NGINX_PORT}/chroma/api/v2/heartbeat" >/dev/null; then
  echo "      OK: http://<vm>:${NGINX_PORT}/chroma/api/v2/heartbeat -> $(curl -s http://127.0.0.1:${NGINX_PORT}/chroma/api/v2/heartbeat)"
else
  echo "      WARN: proxy heartbeat failed - check the ${NGINX_PORT} server block / SELinux (httpd_can_network_connect)"
fi

VMIP="$(hostname -I 2>/dev/null | awk '{print $1}')"
cat <<EOF

== DONE ==
Teammates connect (no repo needed) with:

  import chromadb
  from chromadb.config import Settings
  client = chromadb.HttpClient(host="${VMIP:-<vm-ip>}", port=${NGINX_PORT}, ssl=False,
      settings=Settings(chroma_server_api_default_path="/chroma/api/v2"))
  coll = client.get_or_create_collection("automation_features", metadata={"hnsw:space":"cosine"})

Rules: same embedding model all-MiniLM-L6-v2, same collection name, content-hash ids.
Manage chroma: systemctl status|restart ${SERVICE}   (logs: journalctl -u ${SERVICE} -f)
EOF
