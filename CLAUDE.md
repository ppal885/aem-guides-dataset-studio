# Claude repository guidance

## Project focus

This repository’s supported product is the AEM Guides UAC/test-plan generator. The only browser surface is the read-only evaluation dashboard in `scripts/uac_eval/`. Do not recreate a general-purpose React/Vite UI or add browser-based UAC authoring unless the user explicitly requests a new product change.

## Canonical entry points

- Skill source of truth: `.codex/skills/test-plan-generation/`
- Python runtime: `backend/app/services/test_plan_pipeline_service.py`
- CLI: `scripts/run_test_plan_pipeline.py`
- REST: `POST /api/v1/test-plans/pipeline`
- MCP bridge: `POST /api/v1/mcp/guides-test-plan-generator`
- MCP tool: `guides_test_plan_generator`
- Evaluation dashboard: `scripts/uac_eval/dashboard.html`
- Dashboard data adapter: `scripts/uac_eval/aggregate_runs.py`

Preserve equivalent behavior across skill, CLI, REST, and MCP paths. The dashboard reads saved evaluation JSON and must never recalculate or invent metrics.

## Working rules

- For AEM Guides test plans or UACs, use the installed `test-plan-generation` skill.
- Fetch a supplied Jira key through the configured Jira MCP before drafting when access is available.
- Treat Human/product decisions as acceptance authority. AI synthesis and historical similarity are supporting discovery only.
- Keep Jira/customer-specific production rules out of the skill and runtime.
- Do not modify corpora, reingest data, post to Jira, or change production behavior unless the request explicitly includes it.
- Preserve user changes in dirty worktrees; use targeted staging and never `git add -A`.

Relevant product and automation clones can exist outside this checkout. Follow `AGENTS.md` before claiming code or automation evidence is unavailable.

## Local commands

Start backend plus static dashboard on Windows:

```powershell
.\RUN_LOCAL_DEV.cmd
```

- Dashboard: `http://127.0.0.1:8765/`
- Backend: `http://127.0.0.1:8001`

The launcher builds and serves an isolated dashboard bundle. It does not rewrite the checked-in `scripts/uac_eval/dashboard_data.json`; incomplete local run inputs retain the checked-in history snapshot.

Generate through the canonical runtime:

```powershell
python scripts\run_test_plan_pipeline.py GUIDES-12345
python scripts\run_test_plan_pipeline.py GUIDES-12345 --http --base-url http://127.0.0.1:8001
```

Refresh dashboard data:

```powershell
python scripts\uac_eval\aggregate_runs.py --self-test
python scripts\uac_eval\aggregate_runs.py
```

Run skill checks:

```powershell
python .codex\skills\test-plan-generation\scripts\test_skill_scripts.py
python .codex\skills\test-plan-generation\scripts\audit_production_hardcoding.py
```

## VM deployment

`setup_vm.py` deploys the backend service and the static dashboard. Nginx exposes the dashboard at `http://<VM-IP>:4502/` and proxies `/api`, `/mcp`, and `/health` to the backend on port `8001`. Former application routes must return `404`.

## Security

Keep real credentials in ignored environment files or approved secret injection. Never hardcode or log Jira credentials, LLM keys, bearer tokens, or AEM passwords. Development authentication bypass is local-only and must be disabled in production.
