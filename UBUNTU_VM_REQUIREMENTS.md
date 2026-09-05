# Ubuntu VM requirements

The supported non-Docker VM deployment runs the UAC backend with systemd and serves the static evaluation dashboard with system Nginx.

## Required

- Ubuntu 20.04 LTS or newer
- Python 3.11+ with `venv` and `pip`
- Nginx and systemd
- Git and curl
- enough disk for the backend environment, evidence stores, and saved evaluation runs

Node.js, npm, Vite, PostgreSQL, Redis, and a frontend container are not required for the dashboard-only deployment.

Install the base packages on Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip nginx git curl
```

If the default Python is older than 3.11, install the approved Python 3.11 package for the VM image before running setup.

## Optional Docker backend

Docker Engine with Compose v2 is needed only when choosing the backend-container workflow in `DOCKER.md`. The dashboard remains a static Nginx/Python surface.

## Network

- `22/tcp` — SSH, restricted by the VM/network policy
- `4502/tcp` — team-facing dashboard and API/MCP gateway
- `8001/tcp` — backend loopback/internal service; do not expose it publicly when Nginx is the gateway

Open only the ports approved for the environment. Prefer network allowlists or the corporate access layer for port `4502`.

## Configuration

- Store deployment settings in the ignored `.env.docker` file or approved secret injection.
- Disable development authentication bypass in production.
- Never commit credentials, bearer tokens, private keys, or production URLs containing credentials.

## Setup and verification

```bash
cd ~/aem-guides-dataset-studio
test -f .env.docker || cp .env.docker.example .env.docker
chmod 600 .env.docker
sudo python3 setup_vm.py
sudo nginx -t
curl -fsS http://127.0.0.1:8001/health
curl -fsS http://127.0.0.1:4502/health
```

See `QUICK_START_FRESH_VM.md` for the full operator flow.
