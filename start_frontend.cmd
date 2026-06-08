@echo off
setlocal

rem Start the frontend proxy server so the app and /api proxy stay on port 5173.
set "ROOT=%~dp0"
set "PY=%ROOT%venv\Scripts\python.exe"
set "FRONTEND_PROXY=%ROOT%tmp\frontend_proxy.py"

if not exist "%PY%" (
  echo ERROR: Repo venv python not found: "%PY%"
  echo Run setup first - see README.md - or recreate venv under "%ROOT%venv".
  exit /b 1
)

if not exist "%FRONTEND_PROXY%" (
  echo ERROR: Frontend proxy script not found: "%FRONTEND_PROXY%"
  exit /b 1
)

echo Starting frontend on http://localhost:5173 ...
echo (Static frontend with /api proxy to the backend.)
echo.
call "%PY%" "%FRONTEND_PROXY%"
if errorlevel 1 (
  echo.
  echo Frontend exited with error code %errorlevel%.
  pause
)
