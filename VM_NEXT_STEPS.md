# VM setup — next steps

SSH login ho gaya hai to ab dashboard-only UAC runtime deploy karein. React/Vite frontend ki zaroorat nahi hai.

## 1. Repository update

```bash
cd ~/aem-guides-dataset-studio
git status --short
git pull --ff-only origin main
```

Unexpected local changes dikhein to pull/cleanup force mat karein; pehle unka backup ya merge decide karein.

## 2. Environment configure

```bash
test -f .env.docker || cp .env.docker.example .env.docker
chmod 600 .env.docker
```

Real Jira/LLM/auth values approved secret process se add karein. Secrets ko Git ya shell scripts mein mat daalein.

## 3. Setup run

```bash
sudo python3 setup_vm.py
```

## 4. Verify

```bash
sudo systemctl status aem-backend.service --no-pager -l
sudo nginx -t
curl -fsS http://127.0.0.1:8001/health
curl -fsS http://127.0.0.1:4502/health
curl -fsSI http://127.0.0.1:4502/
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:4502/mcp/health
```

`/mcp/health` ke liye `200` pass hai. Token ke bina `401` ya `403` bhi pass hai, kyunki protected MCP boundary reachable hai. `404`, `502`, ya koi aur status failure hai. Secret-safe authenticated check ke liye [VM_DEV_RUNBOOK.md](VM_DEV_RUNBOOK.md) dekhein.

Team browser URL: `http://<VM-IP>:4502/`

Yahi read-only evaluation dashboard hai. UAC generate karne ke liye `test-plan-generation` skill, `guides_test_plan_generator` MCP tool, REST pipeline, ya CLI use karein:

```bash
python3 scripts/run_test_plan_pipeline.py GUIDES-12345 --http --base-url http://127.0.0.1:8001
```

Nginx `502` de to pehle port `8001` health aur `journalctl -u aem-backend.service` check karein.
