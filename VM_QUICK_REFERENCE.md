# VM quick reference

## Update and deploy

```bash
cd ~/aem-guides-dataset-studio
git status --short
git pull --ff-only origin main
sudo python3 setup_vm.py
```

Refresh only the dashboard and Nginx configuration:

```bash
sudo python3 setup_vm.py --dashboard-only
```

## URLs

- Dashboard: `http://<VM-IP>:4502/`
- Health: `http://<VM-IP>:4502/health`
- API: `http://<VM-IP>:4502/api/`
- MCP: `http://<VM-IP>:4502/mcp`

`/eval-dashboard/` redirects to `/`. There is no React/Vite application or frontend container.

## Service commands

```bash
sudo systemctl status aem-backend.service --no-pager -l
sudo systemctl restart aem-backend.service
journalctl -u aem-backend.service -n 100 --no-pager
journalctl -u aem-backend.service -f
sudo nginx -t
sudo systemctl reload nginx
```

## Checks

```bash
curl -fsS http://127.0.0.1:8001/health
curl -fsS http://127.0.0.1:4502/health
curl -fsSI http://127.0.0.1:4502/
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:4502/mcp/health
```

For `/mcp/health`, accept `200`, or unauthenticated `401/403` as proof that the protected boundary is reachable. Reject every other status, including `404/502`. See [VM_DEV_RUNBOOK.md](VM_DEV_RUNBOOK.md) for the secret-safe authenticated check.

If port `4502` returns `502`, diagnose the backend on port `8001` first. Do not delete Docker volumes, corpora, or backend storage as a recovery shortcut.

## UAC generation

Use the installed `test-plan-generation` skill, the `guides_test_plan_generator` MCP tool, the REST pipeline, or:

```bash
python3 scripts/run_test_plan_pipeline.py GUIDES-12345 --http --base-url http://127.0.0.1:8001
```
