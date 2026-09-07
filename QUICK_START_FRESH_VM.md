# Fresh VM quick start

The VM exposes one browser surface: the read-only UAC evaluation dashboard. Nginx listens on port `4502` and proxies API and MCP traffic to the backend on `127.0.0.1:8001`.

## 1. Prepare the checkout

```bash
cd ~/aem-guides-dataset-studio
git status --short
git pull --ff-only origin main
test -f .env.docker || cp .env.docker.example .env.docker
chmod 600 .env.docker
```

Add real credentials to `.env.docker` through the approved secret process. Do not paste tokens into scripts, shell history, or Git-tracked files. Production must not enable the development authentication bypass.

## 2. Install or refresh the service

```bash
cd ~/aem-guides-dataset-studio
sudo python3 setup_vm.py
```

The setup script:

1. validates and installs the dashboard-only Nginx configuration;
2. creates or refreshes `aem-backend.service`;
3. installs backend dependencies when needed;
4. starts the backend;
5. aggregates saved evaluation runs and atomically deploys only `index.html` and `dashboard_data.json`.

For a dashboard-only refresh that does not change systemd:

```bash
sudo python3 setup_vm.py --dashboard-only
```

## 3. Verify

```bash
sudo systemctl status aem-backend.service --no-pager -l
sudo nginx -t
curl -fsS http://127.0.0.1:8001/health
curl -fsS http://127.0.0.1:4502/health
curl -fsSI http://127.0.0.1:4502/
curl -fsSI http://127.0.0.1:4502/eval-dashboard/
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:4502/mcp/health
```

For `/mcp/health`, `200` passes. Without a token, `401` or `403` also passes because it confirms the protected MCP boundary is reachable. Any other status, including `404` or `502`, fails. See [VM_DEV_RUNBOOK.md](VM_DEV_RUNBOOK.md) for the secret-safe authenticated check.

Expected team URLs:

- Dashboard: `http://<VM-IP>:4502/`
- API: `http://<VM-IP>:4502/api/`
- MCP: `http://<VM-IP>:4502/mcp`
- Health: `http://<VM-IP>:4502/health`

`/eval-dashboard` and `/eval-dashboard/` permanently redirect to `/`. Retired application paths such as `/builder`, `/chat`, `/settings`, and `/dataset-explorer` return `404`.

## Generate a UAC

Use the `test-plan-generation` skill, the `guides_test_plan_generator` MCP tool, the canonical REST endpoint `POST /api/v1/test-plans/pipeline`, or the CLI:

```bash
python3 scripts/run_test_plan_pipeline.py GUIDES-12345 --http --base-url http://127.0.0.1:8001
```

Use the authentication configured for the environment. The dashboard itself is read-only and does not generate UACs.

## Operations

```bash
journalctl -u aem-backend.service -n 100 --no-pager
journalctl -u aem-backend.service -f
systemctl restart aem-backend.service
systemctl reload nginx
```

If Nginx returns `502`, verify the backend health on port `8001` and inspect the service log before reloading Nginx.
