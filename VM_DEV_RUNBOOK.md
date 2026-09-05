# Linux VM runbook

The supported shared VM runs the UAC backend under systemd and serves the read-only evaluation dashboard through Nginx on port `4502`. The retired React/Vite development server is not used.

## Pull and deploy

```bash
cd ~/aem-guides-dataset-studio
git status --short
git pull --ff-only origin main
sudo python3 setup_vm.py
```

For a dashboard-only refresh after new evaluation JSON is added:

```bash
cd ~/aem-guides-dataset-studio
sudo python3 setup_vm.py --dashboard-only
```

## Verify shared routes

```bash
sudo nginx -t
sudo systemctl status aem-backend.service --no-pager -l
curl -fsS http://127.0.0.1:8001/health
curl -fsSI http://127.0.0.1:4502/
curl -fsS http://127.0.0.1:4502/health
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:4502/mcp/health
```

For `/mcp/health`, HTTP `200` passes. When production authentication is enabled, `401` or `403` without a token also proves that the protected MCP boundary is reachable. Treat every other status, including `404` or `502`, as a routing failure.

For an authenticated `200` check, read the token without echo and pass the header through curl configuration input so the secret is not placed in the command line:

```bash
read -rsp 'MCP bearer token: ' MCP_BEARER_TOKEN; printf '\n'
curl -fsS --config - http://127.0.0.1:4502/mcp/health <<< "header = \"Authorization: Bearer ${MCP_BEARER_TOKEN}\""
unset MCP_BEARER_TOKEN
```

Do not enable shell tracing or record the expanded configuration input.

Open `http://<VM-IP>:4502/`. `/eval-dashboard/` redirects to `/`; unsupported former application routes return `404`.

## Logs and restart

```bash
journalctl -u aem-backend.service -n 100 --no-pager
journalctl -u aem-backend.service -f
sudo systemctl restart aem-backend.service
sudo systemctl reload nginx
```

If Nginx reports `502`, check `http://127.0.0.1:8001/health` and the backend journal before changing the proxy.

## Temporary developer server

For isolated debugging without changing the shared Nginx deployment:

```bash
cd ~/aem-guides-dataset-studio
bash start-vm-dev.sh
```

Defaults are backend port `8010`, dashboard port `8765`, and loopback-only binding. With SSH port forwarding, open `http://127.0.0.1:8765/`. Use `--host 0.0.0.0` only when team access to the temporary ports is intentional and approved.

Stop launcher-owned processes with:

```bash
bash start-vm-dev.sh --stop
```

The development dashboard is static and does not proxy API or MCP requests.

## Generate through the development backend

```bash
cd ~/aem-guides-dataset-studio
python3 scripts/run_test_plan_pipeline.py GUIDES-12345 --http --base-url http://127.0.0.1:8010
```

Use the environment’s configured authentication and credentials. Never add real secrets to this runbook or shell scripts.
