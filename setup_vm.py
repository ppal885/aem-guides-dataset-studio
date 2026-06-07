#!/usr/bin/env python3
"""
AEM Guides Dataset Studio — Linux VM Setup Script
Run as root: python3 setup_vm.py

This script:
1. Writes the nginx config for the app
2. Creates a systemd service for the backend
3. Builds the frontend and copies to /var/www
4. Starts everything
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def run(cmd, check=True, cwd=None):
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd or ROOT, check=check)
    return result.returncode == 0


def write_file(path, content, sudo=False):
    print(f"  Writing {path}")
    if sudo:
        tmp = "/tmp/_setup_tmp"
        with open(tmp, "w") as f:
            f.write(content)
        run(f"cp {tmp} {path}")
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)


# ── 1. nginx config ───────────────────────────────────────────────────────────
print("\n[1/5] Writing nginx config...")

NGINX_CONF = r"""server {
    listen 80;
    server_name _;
    root /var/www/aem-studio;
    index index.html;

    # SSE endpoints — no buffering, long timeout
    location ~ ^/api/v1/(chat|ai) {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_request_buffering off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_connect_timeout 75s;
        gzip off;
        chunked_transfer_encoding on;
    }

    # All other API calls
    location /api {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        proxy_read_timeout 300s;
        gzip off;
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
        add_header Cache-Control "no-cache";
    }

    # Static assets cache
    location ~* \.(js|css|png|jpg|ico|svg|woff2?)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }
}
"""

write_file("/tmp/aem-studio.nginx", NGINX_CONF)
run("cp /tmp/aem-studio.nginx /etc/nginx/sites-available/aem-studio")
run("ln -sf /etc/nginx/sites-available/aem-studio /etc/nginx/sites-enabled/default")
run("rm -f /etc/nginx/sites-enabled/aem-studio 2>/dev/null", check=False)

# Remove IPv6 from nginx default config (not supported on all VMs)
run("sed -i '/\\[::\\]/d' /etc/nginx/nginx.conf")
run("nginx -t")
run("systemctl reload nginx")
print("  nginx config OK")


# ── 2. systemd backend service ────────────────────────────────────────────────
print("\n[2/5] Creating backend systemd service...")

BACKEND_DIR = os.path.join(ROOT, "backend")
ENV_FILE = os.path.join(ROOT, ".env.docker")
VENV = os.path.join(BACKEND_DIR, "venv")
UVICORN = os.path.join(VENV, "bin", "uvicorn")

SERVICE = f"""[Unit]
Description=AEM Guides Dataset Studio Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={BACKEND_DIR}
EnvironmentFile={ENV_FILE}
Environment=PORT=8001
ExecStart={UVICORN} app.main:app --host 0.0.0.0 --port 8001 --workers 1
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""

write_file("/tmp/aem-backend.service", SERVICE)
run("cp /tmp/aem-backend.service /etc/systemd/system/aem-backend.service")
run("systemctl daemon-reload")
print("  systemd service created")


# ── 3. Install backend Python deps (if not done) ──────────────────────────────
print("\n[3/5] Checking backend Python dependencies...")

if not os.path.exists(UVICORN):
    print("  venv not found — installing (this may take 5-10 min)...")
    run(f"python3.11 -m venv {VENV} || python3 -m venv {VENV}")
    pip = os.path.join(VENV, "bin", "pip")
    os.environ["TMPDIR"] = "/var/tmp"
    run(f"{pip} install --upgrade pip")
    run(f"TMPDIR=/var/tmp {pip} install --timeout 300 -r {BACKEND_DIR}/requirements.txt")
else:
    print("  venv already exists, skipping install")


# ── 4. Start backend ──────────────────────────────────────────────────────────
print("\n[4/5] Starting backend service...")
run("systemctl enable aem-backend")
run("systemctl restart aem-backend")

import time
print("  Waiting 8s for backend to start...")
time.sleep(8)

ret = subprocess.run(
    "curl -sf http://localhost:8001/health",
    shell=True, capture_output=True, text=True
)
if ret.returncode == 0:
    print(f"  Backend healthy: {ret.stdout[:100]}")
else:
    print("  Backend not yet healthy — check: journalctl -u aem-backend -n 30")


# ── 5. Build and deploy frontend ──────────────────────────────────────────────
print("\n[5/5] Building frontend...")
FRONTEND_DIR = os.path.join(ROOT, "frontend")
DIST = os.path.join(FRONTEND_DIR, "dist")

if not os.path.exists(os.path.join(FRONTEND_DIR, "node_modules")):
    run("npm install", cwd=FRONTEND_DIR)

run("npm run build", cwd=FRONTEND_DIR)
run("mkdir -p /var/www/aem-studio")
run(f"cp -r {DIST}/. /var/www/aem-studio/")
run("systemctl reload nginx")

# ── Done ──────────────────────────────────────────────────────────────────────
import socket
try:
    ip = socket.gethostbyname(socket.gethostname())
except Exception:
    ip = "your-vm-ip"

print(f"""
============================================================
  AEM Guides Dataset Studio is running!

  Open in browser:  http://{ip}/
  Backend health:   http://{ip}:8001/health

  Logs:   journalctl -u aem-backend -f
  Restart: systemctl restart aem-backend
============================================================
""")
