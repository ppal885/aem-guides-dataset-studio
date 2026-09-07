# Docker: UAC backend with static dashboard

Docker Compose runs the canonical Python backend only. The evaluation dashboard is static and is served locally by Python or, on the VM, by system Nginx. No Node, npm, Vite, or frontend container is required.

## Windows quick start

Prerequisites: Docker Desktop and Python 3.11+.

```powershell
Copy-Item .env.docker.example .env.docker
.\DOCKER_RUN.ps1 -Build
```

While the script is running:

- Dashboard: `http://127.0.0.1:8765/`
- Backend: `http://127.0.0.1:8001`
- API docs: `http://127.0.0.1:8001/docs`

`DOCKER_RUN.ps1` builds the dashboard in an isolated staging directory and does not rewrite the checked-in `dashboard_data.json`. If eligible local run files are an incomplete subset, the staged bundle retains the checked-in history snapshot.

Use `-Dev` for backend source mounting and Uvicorn reload:

```powershell
.\DOCKER_RUN.ps1 -Dev
```

The dashboard helper stops when `DOCKER_RUN.ps1` exits. To stop the backend container after a detached or interrupted run:

```powershell
docker compose down
```

## Manual backend commands

```powershell
docker compose build
docker compose up -d
docker compose logs -f backend
docker compose down
```

To intentionally rewrite the tracked dashboard snapshot and serve it in a separate terminal:

```powershell
python scripts\uac_eval\aggregate_runs.py
python -m http.server 8765 --bind 127.0.0.1 --directory scripts\uac_eval
```

## VM deployment

The supported team-facing deployment uses Nginx on port `4502`:

```bash
sudo ./deploy.sh --build
```

`deploy.sh` starts the backend container, verifies health, and calls `setup_vm.py --dashboard-only` to atomically refresh the Nginx site. The resulting routes are:

- `http://<VM-IP>:4502/` — dashboard
- `http://<VM-IP>:4502/api/` — API proxy
- `http://<VM-IP>:4502/mcp` — MCP proxy
- `http://<VM-IP>:4502/health` — health proxy

## Configuration

Create `.env.docker` from `.env.docker.example`, keep real values out of Git, and configure the approved Jira, LLM, repository, and authentication settings. Production must disable development-auth bypass and use explicit credentials.

The optional `DITA_CONTENT_HOST_PATH` mount remains read-only so the UAC runtime can inspect the team’s AEM Guides content without modifying it.

## Service inventory

| Service | Host port | Purpose |
|---|---:|---|
| `backend` | 8001 | Canonical FastAPI UAC runtime and MCP bridge |
| local dashboard helper | 8765 | Read-only development dashboard |
| system Nginx on VM | 4502 | Team dashboard plus API/MCP reverse proxy |
