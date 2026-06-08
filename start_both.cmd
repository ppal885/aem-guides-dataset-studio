@echo off
setlocal

rem Start backend + frontend together (no PowerShell execution policy needed).
set "ROOT=%~dp0"

echo AEM Guides Dataset Studio - Starting Backend + Frontend
echo.

rem Use `cmd /k` so the windows stay open if something errors early.
start "Dataset Studio Backend" cmd /k "%ROOT%start_backend.cmd"
start "Dataset Studio Frontend" cmd /k "%ROOT%start_frontend.cmd"

echo Launched.
echo - Backend:  http://localhost:8001  (health: /health, docs: /docs)
echo - Frontend: http://localhost:5173
