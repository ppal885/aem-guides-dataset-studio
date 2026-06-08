@echo off
setlocal

rem Start backend using the repo virtualenv (no PowerShell execution policy needed).
set "ROOT=%~dp0"
set "PY=%ROOT%venv\Scripts\python.exe"

if not exist "%PY%" (
  echo ERROR: Repo venv python not found: "%PY%"
  echo Run setup first - see README.md - or recreate venv under "%ROOT%venv".
  exit /b 1
)

cd /d "%ROOT%backend" || exit /b 1
echo Starting backend on http://localhost:8001 ...
echo (Keep this window open.)
echo.
call "%PY%" run_local.py
if errorlevel 1 (
  echo.
  echo Backend exited with error code %errorlevel%.
  pause
)
