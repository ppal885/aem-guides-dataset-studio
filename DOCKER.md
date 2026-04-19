# Running with Docker

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

## Quick Start

### Production (PostgreSQL, Redis, Nginx)

```powershell
# From project root
.\DOCKER_RUN.ps1
```

- Frontend: http://localhost (port 80)
- Backend API: proxied at http://localhost/api
- API docs: http://localhost/api/docs

### Development (hot-reload)

```powershell
.\DOCKER_RUN.ps1 -Dev
```

- Backend: http://localhost:8001
- Frontend: http://localhost:5173

### Build images first

```powershell
.\DOCKER_RUN.ps1 -Build -Dev
```

## Environment Variables

Create a `.env` file in the project root (copy from `.env.example`). Docker Compose loads it automatically.

For Jira (AI pipeline - Index, Plan, Generate):

```
JIRA_URL=https://jira.corp.adobe.com
JIRA_USERNAME=your_username
JIRA_PASSWORD=your_password
JIRA_PROJECT_KEY=DXML
JIRA_ISSUE_TYPE=Bug
JIRA_API_VERSION=2
```

## Manual Commands

```powershell
# Start in background
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down

# Rebuild after code changes
docker compose build --no-cache
docker compose up
```

## Services

| Service   | Port | Description                    |
|-----------|------|--------------------------------|
| frontend  | 80   | Nginx + React (production)     |
| frontend  | 5173 | Vite dev server (dev mode)     |
| backend   | 8001 | FastAPI API (host; container listens on 8000) |
| postgres  | 5432 | PostgreSQL database           |
| redis     | 6379 | Redis (for future Celery)     |
