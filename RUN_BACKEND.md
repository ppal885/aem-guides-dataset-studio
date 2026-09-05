# Run the UAC backend

The backend hosts the canonical UAC generation API and MCP bridge. It does not require a browser UI.

## Recommended Windows launcher

From the repository root:

```powershell
.\RUN_LOCAL_DEV.cmd
```

This starts the backend on port `8001` and the read-only dashboard on port `8765`. Use `.\RUN_LOCAL_DEV.cmd -Stop` to stop only the processes owned by that launcher.

## Backend only

Create and populate a project virtual environment once:

```powershell
Copy-Item backend\.env.example backend\.env
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Then start the service:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

The compatibility scripts `START_BACKEND_SIMPLE.ps1`, `start_backend.ps1`, `start_backend_direct.ps1`, and `start_backend.cmd` remain backend-only alternatives.

## Verify

```powershell
Invoke-WebRequest http://127.0.0.1:8001/health -UseBasicParsing
python scripts\run_test_plan_pipeline.py GUIDES-12345 --http --base-url http://127.0.0.1:8001
```

- Health: `http://127.0.0.1:8001/health`
- API docs: `http://127.0.0.1:8001/docs`
- Canonical API: `POST http://127.0.0.1:8001/api/v1/test-plans/pipeline`
- MCP bridge: `POST http://127.0.0.1:8001/api/v1/mcp/guides-test-plan-generator`

## Troubleshooting

- If the port is already in use, stop the known launcher with `.\RUN_LOCAL_DEV.cmd -Stop`. Use `.\KILL_PORTS.ps1` only when you intentionally want to terminate every listener on the documented local ports.
- If imports fail, confirm that the same Python executable received `backend\requirements.txt`.
- Keep secrets in `backend\.env` or the approved deployment secret store; never add them to tracked scripts.
- Review local logs under `logs\`. On the VM, use `journalctl -u aem-backend -n 100 --no-pager`.
