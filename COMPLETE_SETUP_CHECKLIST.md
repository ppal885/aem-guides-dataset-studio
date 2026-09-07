# Complete dashboard-only VM setup checklist

Use this checklist for a fresh Linux VM deployment of the AEM Guides UAC generator. The React/Vite application and frontend container are retired.

## Before deployment

- [ ] Clone or update `aem-guides-dataset-studio`.
- [ ] Confirm `git status --short` contains no unexpected local changes.
- [ ] Install Python 3.11+, Nginx, and systemd support.
- [ ] Copy `.env.docker.example` to the ignored `.env.docker` file if it does not exist.
- [ ] Inject Jira, LLM, authentication, and repository settings through the approved secret process.
- [ ] Set production authentication explicitly; do not enable development bypass.

## Install

```bash
cd ~/aem-guides-dataset-studio
git pull --ff-only origin main
test -f .env.docker || cp .env.docker.example .env.docker
chmod 600 .env.docker
sudo python3 setup_vm.py
```

The setup must deploy only these web files under `/var/www/aem-studio`:

- `index.html`
- `dashboard_data.json`

It must not leave old JavaScript bundles or other retired UI assets in the webroot.

## Service checks

```bash
sudo nginx -t
sudo systemctl is-enabled aem-backend.service
sudo systemctl is-active aem-backend.service
curl -fsS http://127.0.0.1:8001/health
```

## Public-route checks on port 4502

```bash
curl -fsSI http://127.0.0.1:4502/
curl -fsS http://127.0.0.1:4502/health
curl -fsSI http://127.0.0.1:4502/eval-dashboard/
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:4502/mcp/health
```

For `/mcp/health`, HTTP `200` passes. With production development-bypass disabled, an unauthenticated `401` or `403` also confirms that Nginx reached the protected MCP boundary. Any other status, including `404` or `502`, fails the route check.

Optionally verify an authenticated `200` without echoing the bearer token or placing it in the curl command line:

```bash
read -rsp 'MCP bearer token: ' MCP_BEARER_TOKEN; printf '\n'
curl -fsS --config - http://127.0.0.1:4502/mcp/health <<< "header = \"Authorization: Bearer ${MCP_BEARER_TOKEN}\""
unset MCP_BEARER_TOKEN
```

Do not run the token check with shell tracing enabled, and do not save its expanded input in logs.

- [ ] `/` returns the dashboard.
- [ ] `/eval-dashboard` and `/eval-dashboard/` redirect permanently to `/`.
- [ ] `/dashboard_data.json` returns JSON with no-cache headers.
- [ ] `/api/`, `/mcp`, `/mcp/`, and `/health` reach the backend; an unauthenticated `401/403` is valid MCP reachability.
- [ ] `/builder`, `/chat`, `/settings`, and `/dataset-explorer` return `404`.

## UAC smoke checks

```bash
python3 scripts/uac_eval/aggregate_runs.py --self-test
python3 scripts/uac_eval/aggregate_runs.py
python3 scripts/run_test_plan_pipeline.py GUIDES-12345
python3 scripts/run_test_plan_pipeline.py GUIDES-12345 --http --base-url http://127.0.0.1:8001
```

- [ ] Skill-based generation works.
- [ ] `guides_test_plan_generator` works through MCP.
- [ ] In-process and HTTP CLI outputs remain equivalent after normalization.
- [ ] Dashboard values match `dashboard_data.json` exactly.

Use an accessible, non-sensitive Jira key for the smoke run. Do not post generated content during deployment verification.

## Operations

```bash
journalctl -u aem-backend.service -n 100 --no-pager
journalctl -u aem-backend.service -f
sudo systemctl restart aem-backend.service
sudo python3 setup_vm.py --dashboard-only
```

If port `4502` returns `502`, verify the backend on `127.0.0.1:8001` and inspect the journal before changing Nginx.
