---
name: vm-deployment
description: >
  Deploy the AEM Guides Dataset Studio to a Linux VM (Ubuntu, CentOS, etc.) without Docker.
  Use this skill whenever someone asks about deploying the app to a server, VM, or production
  host: "how do I deploy to a Linux VM", "deploy to Ubuntu server", "run on a production VM",
  "set up on a cloud VM", "deploy without Docker", "host on Linux", "production deployment",
  "set up systemd service", "configure nginx for the app", or any time someone is trying to
  get the app running on a remote Linux server. Also use when Docker fails on constrained VMs.
---

# VM Deployment (Linux — No Docker)

Deploy AEM Guides Dataset Studio directly on Linux using Python venv + systemd + nginx.
This is more reliable than Docker on VMs with small tmpfs, old Docker versions, or restricted environments.

---

## 1. Quick Start — One Command

```bash
git clone https://github.com/ppal885/aem-guides-dataset-studio.git
cd aem-guides-dataset-studio
cp .env.docker.example .env.docker
nano .env.docker          # fill in Azure/LLM keys
python3 setup_vm.py
```

`setup_vm.py` handles everything: nginx, systemd, pip install, frontend build.

---

## 2. Prerequisites

```bash
# Ubuntu 22.04
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip nginx nodejs npm

# Verify
python3.11 --version && node --version && nginx -v
```

---

## 3. Known Issues & Fixes

### /tmp is a 512MB tmpfs — pip install fails on large packages
```bash
# Fix: increase /tmp or use /var/tmp
sudo mount -o remount,size=4G /tmp

# Or use /var/tmp in pip commands:
TMPDIR=/var/tmp pip install --no-cache-dir -r requirements.txt
```
Large packages: anthropic (~530MB), sentence-transformers (~300MB) exceed the default tmpfs.

### Docker apt install fails with "No space left on device"
```bash
# The package list cache got corrupted — clean and retry
sudo rm -rf /var/lib/apt/lists/*
sudo apt-get clean
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io
```

### nginx fails to start: "socket() [::]:80 failed (97)"
IPv6 not supported on this VM. Remove all IPv6 listen directives:
```bash
sudo grep -rl "\[::\]" /etc/nginx/ | xargs sudo sed -i '/\[::\]/d'
sudo nginx -t && sudo systemctl restart nginx
```

### 401 Unauthorized on all API calls
`ALLOW_DEV_AUTH_BYPASS=true` is ignored when `ENVIRONMENT=production`.
```bash
sed -i 's/ENVIRONMENT=production/ENVIRONMENT=development/' .env.docker
systemctl restart aem-backend
```

### Tenant '10' not found (or Tenant 'X' not found with IP as tenant)
The app extracts tenant from the Host header. IP addresses like `10.42.46.78` produce `10` as tenant.
This bug was fixed in the codebase (`.isdigit()` check in tenant_service.py).
If it occurs on an older version: add `X-Tenant-ID: kone` header in nginx:
```nginx
proxy_set_header X-Tenant-ID "kone";
```

### SQLite "no such table: jobs"
Database migrations haven't run. Initialize the schema:
```bash
cd backend && source venv/bin/activate
python -c "
from app.db.base import Base
from app.db.session import engine
import app.db.chat_models, app.db.jira_models
Base.metadata.create_all(bind=engine)
print('Done')
"
systemctl restart aem-backend
```

### Azure OpenAI / LLM calls silently fail — answers are "local indexed knowledge"
The openai SDK must be >= 1.47.0 for `max_completion_tokens` support (required by gpt-5.2 and newer models).
```bash
TMPDIR=/var/tmp /path/to/venv/bin/pip install --no-cache-dir "openai>=1.47.0"
/path/to/venv/bin/python -c "import openai; print(openai.__version__)"
systemctl restart aem-backend
```

### nginx 403 Forbidden after deploying frontend
```bash
chmod -R 755 /var/www/aem-studio
chown -R www-data:www-data /var/www/aem-studio
systemctl reload nginx
```

---

## 4. Key Environment Variables (.env.docker)

```bash
# Required
LLM_PROVIDER=azure_openai
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_OPENAI_API_VERSION=2025-04-01-preview
AZURE_OPENAI_MODEL=gpt-5.2

# MUST be development (not production) for dev auth bypass
ENVIRONMENT=development
ALLOW_DEV_AUTH_BYPASS=true
PORT=8001
```

---

## 5. Management Commands

```bash
# Status
systemctl status aem-backend nginx

# Logs (live)
journalctl -u aem-backend -f

# Update app
cd ~/aem-guides-dataset-studio && git pull && python3 setup_vm.py

# Restart
systemctl restart aem-backend && systemctl reload nginx

# Health check
curl http://localhost:8001/health
```

---

## 6. Port Configuration

The app is designed to run nginx on port 80, but security groups may require a different port.
To change: edit `/etc/nginx/sites-available/aem-studio` and update `listen 80;` to `listen 4502;`.

Two places to open ports:
1. **OS firewall**: `ufw allow 4502/tcp`
2. **Cloud security group**: add inbound rule for port 4502 in AWS/Azure/GCP/ATS Corp console

---

## 7. Architecture on VM

```
Browser → nginx:4502 → /api/* → uvicorn:8001 (FastAPI)
                      → /*    → /var/www/aem-studio (React static)

systemd: aem-backend.service (Restart=always, EnvironmentFile=.env.docker)
Storage: backend/storage/ (SQLite DB, ChromaDB, ZIP bundles)
```
