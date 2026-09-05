# AEM Guides UAC Generator

This repository provides the evidence-backed AEM Guides test-plan and User Acceptance Criteria (UAC) runtime. Its only browser interface is a read-only evaluation dashboard. UAC generation is available through the installed skill, MCP, the backend API, or the command line.

## Supported surfaces

- **Test-plan skill:** `.codex/skills/test-plan-generation` is the source of truth for guided Jira analysis and plain-English UAC authoring.
- **Canonical runtime:** the Python backend performs Jira intake, evidence retrieval, reasoning, validation, and rendering.
- **MCP and API:** callers can use the canonical runtime without a browser UI.
- **Evaluation:** `scripts/uac_eval` stores benchmark runs and renders their reported metrics in a standalone dashboard.

There is no browser form for generating or editing a UAC. The retired React/Vite Dataset Studio application is not part of the supported product surface.

## Architecture

```text
Jira or supplied evidence
        |
        v
test-plan-generation skill / CLI / MCP / API
        |
        v
canonical Python reasoning runtime
        |
        +--> evidence, verification, gates, and rendered UAC
        |
        +--> saved evaluation run JSON
                  |
                  v
          read-only HTML dashboard
```

Important paths:

- `backend/` — FastAPI service and canonical UAC runtime
- `.codex/skills/test-plan-generation/` — skill source of truth
- `mcp_server/` and `mcp_server.py` — remote and in-process MCP entry points
- `scripts/run_test_plan_pipeline.py` — canonical CLI entry point
- `scripts/uac_eval/` — evaluator, aggregator, dashboard, and saved run data

## Local start on Windows

Prerequisites: Python 3.11+ and the backend dependencies installed in a project virtual environment.

```powershell
Copy-Item backend\.env.example backend\.env
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\RUN_LOCAL_DEV.cmd
```

The launcher builds an isolated dashboard bundle and starts:

- dashboard: `http://127.0.0.1:8765/`
- backend health: `http://127.0.0.1:8001/health`
- API documentation: `http://127.0.0.1:8001/docs`

Automatic launch does not rewrite the checked-in `scripts/uac_eval/dashboard_data.json` snapshot. When the available run files are an incomplete subset of that snapshot, the isolated bundle retains the checked-in history instead of silently dropping runs.

Stop only the processes owned by the launcher:

```powershell
.\RUN_LOCAL_DEV.cmd -Stop
```

`LAUNCH_LOCAL.cmd`, `RUN_BOTH.ps1`, and `start_both.cmd` remain compatibility wrappers around this launcher. They no longer start a Node/Vite development server.

## Generate a UAC

### Installed skill

In Claude Desktop, Codex, or another supported client, ask it to use the `test-plan-generation` skill for the Jira key. The skill gathers evidence and runs the required quality gates before presenting or posting a plan.

### Command line, in process

```powershell
python scripts\run_test_plan_pipeline.py GUIDES-12345
```

Add `--json` for the complete result object. A review-required result intentionally exits with code `2`.

### Command line, through the local API

Start the backend first, then run:

```powershell
python scripts\run_test_plan_pipeline.py GUIDES-12345 --http --base-url http://127.0.0.1:8001
```

The canonical REST endpoint is `POST /api/v1/test-plans/pipeline`. Use the authentication configured for the target environment; never place a real token in source control or command examples.

### MCP

The canonical generation tool is `guides_test_plan_generator`. For local stdio setup, see [MCP_SETUP.md](MCP_SETUP.md). For the VM gateway, connect the client to:

```text
http://<VM-IP>:4502/mcp
```

The corresponding REST bridge is `POST /api/v1/mcp/guides-test-plan-generator`.

## Evaluation dashboard

To intentionally refresh the tracked dashboard snapshot before reviewing or committing it, run:

```powershell
python scripts\uac_eval\aggregate_runs.py --self-test
python scripts\uac_eval\aggregate_runs.py
python -m http.server 8765 --bind 127.0.0.1 --directory scripts\uac_eval
```

This manual aggregation rewrites `scripts/uac_eval/dashboard_data.json`. Then open `http://127.0.0.1:8765/dashboard.html`. The dashboard only displays numbers already present in that file; it does not generate or alter UACs.

## VM deployment

On the Linux VM, the supported deployment is systemd plus Nginx:

```bash
git pull --ff-only origin main
sudo python3 setup_vm.py
```

The team-facing routes on the single public port are:

- `http://<VM-IP>:4502/` — evaluation dashboard
- `http://<VM-IP>:4502/eval-dashboard/` — permanent redirect to `/`
- `http://<VM-IP>:4502/health` — backend health through Nginx
- `http://<VM-IP>:4502/api/` — API gateway
- `http://<VM-IP>:4502/mcp` — MCP gateway

Old application routes such as `/builder`, `/chat`, `/settings`, and `/dataset-explorer` return `404`.

See [QUICK_START_FRESH_VM.md](QUICK_START_FRESH_VM.md) for verification and rollback-safe operator commands. Docker users should follow [DOCKER.md](DOCKER.md).

## Configuration and security

- Copy example environment files and inject real secrets through local environment files or the approved secrets mechanism.
- Never commit Jira credentials, LLM keys, bearer tokens, or AEM credentials.
- Local static serving binds to `127.0.0.1` by default. Team access is provided by the controlled Nginx listener on port `4502`.
- Keep production development-auth bypass disabled and configure explicit allowed origins when a browser client calls the API directly.

## Validation

```powershell
python scripts\uac_eval\aggregate_runs.py --self-test
python scripts\uac_eval\aggregate_runs.py
python .codex\skills\test-plan-generation\scripts\test_skill_scripts.py
python .codex\skills\test-plan-generation\scripts\audit_production_hardcoding.py
```

Backend tests can be run from `backend/` with the project virtual environment:

```powershell
python -m pytest tests -q
```

## Team onboarding

- [ONBOARDING.md](ONBOARDING.md) — install and verify the test-plan skill
- [MCP_SETUP.md](MCP_SETUP.md) — configure a local MCP client
- [MCP_TOOL_MAP.md](MCP_TOOL_MAP.md) — MCP-to-API mappings
- [RUN_BACKEND.md](RUN_BACKEND.md) — backend-only startup and diagnostics
