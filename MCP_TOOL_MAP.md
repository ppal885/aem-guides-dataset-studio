# MCP tool to REST endpoint map

This document describes the **HTTP MCP adapter** (`mcp_api_adapter`): each tool only forwards to the existing FastAPI service under `/api/v1`. No business logic is duplicated in the MCP layer.

For setup (Cursor, Claude Code, Codex), see [Client configuration samples](#client-configuration-samples) below.

## Tool reference

| MCP tool | HTTP | Path | Notes |
|----------|------|------|--------|
| `list_presets` | GET | `/api/v1/presets` | |
| `create_job` | POST | `/api/v1/jobs` | JSON body `{ "config": { ... } }` |
| `get_job` | GET | `/api/v1/jobs/{job_id}` | `job_id` must be a UUID |
| `schedule_job` | POST | `/api/v1/jobs/schedule` | `scheduled_at` ISO-8601, `timezone` default `UTC` |
| `search_dataset_files` | GET | `/api/v1/datasets/{job_id}/search` | Query params `query`, optional `file_type` |
| `save_recipe` | POST | `/api/v1/recipes/save` | |
| `preview_conref_recipe` | POST | `/api/v1/aem-recipes/conref/preview` | |
| `preview_glossary_recipe` | POST | `/api/v1/specialized/glossary/preview` | |
| `get_rag_status` | GET | `/api/v1/ai/rag-status` | Query `tenant_id` (default `default`) |
| `generate_from_text` | POST | `/api/v1/ai/generate-from-text` | Query `async`, `skip_rag_check` |
| `create_chat_session` | POST | `/api/v1/chat/sessions` | |
| `send_chat_message` | POST | `/api/v1/chat/sessions/{session_id}/messages` | SSE aggregated to JSON |
| `regenerate_chat_response` | POST | `/api/v1/chat/sessions/{session_id}/regenerate` | SSE aggregated to JSON |

Admin routes and other `/api/v1` routers are **not** exposed as MCP tools.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATASET_STUDIO_API_BASE_URL` | `http://127.0.0.1:8000` | FastAPI base URL (no trailing slash) |
| `DATASET_STUDIO_API_BEARER_TOKEN` | (empty) | `Authorization: Bearer …` if set; else falls back to `API_BEARER_TOKEN` |
| `DATASET_STUDIO_API_TIMEOUT_SECONDS` | `120` | httpx timeout (generation can be slow) |
| `DATASET_STUDIO_API_EXTRA_HEADERS_JSON` | (empty) | JSON object of extra headers (e.g. tenant), merged on every request |
| `DATASET_STUDIO_API_SSE_MAX_CHARS` | `120000` | Max length of concatenated `assistant_text` from chat SSE |

Dotenv: if installed, `mcp_api_adapter` loads `.env` from the repo root and `backend/.env` (non-overriding).

## Client configuration samples

Replace paths with your machine’s paths. Start the API first (for example `uvicorn` on port 8000).

### Cursor

Project file [`.cursor/mcp.json`](https://docs.cursor.com/context/mcp) or user `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "dataset-studio-api": {
      "command": "C:\\path\\to\\aem-guides-dataset-studio\\venv\\Scripts\\python.exe",
      "args": ["-m", "mcp_api_adapter"],
      "cwd": "C:\\path\\to\\aem-guides-dataset-studio",
      "env": {
        "DATASET_STUDIO_API_BASE_URL": "http://127.0.0.1:8000",
        "DATASET_STUDIO_API_BEARER_TOKEN": "your-bearer-token-if-required"
      }
    }
  }
}
```

macOS / Linux: use `venv/bin/python` and Unix paths for `cwd`.

### Claude Code

Claude Code reads MCP server definitions from its MCP config (commonly user-level or project-level JSON). Use the same `command` / `args` / `cwd` / env pattern as Cursor: run `python -m mcp_api_adapter` with `cwd` set to the repo root so `mcp_api_adapter` resolves on `PYTHONPATH`.

Example (structure only; exact file location depends on your Claude Code version):

```json
{
  "mcpServers": {
    "dataset-studio-api": {
      "type": "stdio",
      "command": "/path/to/aem-guides-dataset-studio/venv/bin/python",
      "args": ["-m", "mcp_api_adapter"],
      "cwd": "/path/to/aem-guides-dataset-studio",
      "env": {
        "DATASET_STUDIO_API_BASE_URL": "http://127.0.0.1:8000",
        "DATASET_STUDIO_API_BEARER_TOKEN": ""
      }
    }
  }
}
```

See also internal notes under [`backend/app/knowledge/claude_code_setup/`](backend/app/knowledge/claude_code_setup/) for Adobe Claude Code environment setup (Bedrock, etc.); those are separate from this MCP process.

### OpenAI Codex (CLI)

Project example: [`.codex/config.toml`](.codex/config.toml). Point `command` at the same venv Python and use `-m mcp_api_adapter`:

```toml
[mcp_servers.dataset_studio_api]
command = "C:\\path\\to\\aem-guides-dataset-studio\\venv\\Scripts\\python.exe"
args = ["-m", "mcp_api_adapter"]
cwd = "C:\\path\\to\\aem-guides-dataset-studio"
env_vars = ["DATASET_STUDIO_API_BEARER_TOKEN"]

[mcp_servers.dataset_studio_api.env]
PYTHONUTF8 = "1"
DATASET_STUDIO_API_BASE_URL = "http://127.0.0.1:8000"
```

Set `DATASET_STUDIO_API_BEARER_TOKEN` in your shell or user environment when the API requires Bearer auth (production or when dev bypass is disabled).

## Install (adapter only)

```bash
pip install -r requirements-mcp.txt
python -m mcp_api_adapter
```

The last line starts the stdio MCP server (used by IDE integrations; not typically run manually).

## Relation to `mcp_server.py`

| | `mcp_server.py` (repo root) | `mcp_api_adapter` |
|--|----------------------------|-------------------|
| Integration | Imports `backend.app` services directly | HTTP only to `/api/v1` |
| Backend required | DB, Jira, Chroma as per tool | FastAPI server must be running |
| Use case | Rich local tools (RAG, Jira, files) | Agent-safe API parity, remote API possible |
