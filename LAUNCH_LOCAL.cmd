@echo off
setlocal

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "FRONTEND_DIR=%ROOT%frontend"
set "RUN_DIR=%ROOT%.run-local"
set "LOG_DIR=%ROOT%logs"
set "PYTHON_EXE=%BACKEND_DIR%\.venv312\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  set "PYTHON_EXE=python"
)

if not exist "%RUN_DIR%" mkdir "%RUN_DIR%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo Starting AEM Guides Dataset Studio locally...
echo.
echo Backend:  http://127.0.0.1:8001
echo Frontend: http://127.0.0.1:5173
echo.

call "%ROOT%STOP_LOCAL.cmd" >nul 2>nul

(
  echo @echo off
  echo cd /d "%BACKEND_DIR%"
  echo set LEARNED_QA_AUTO_SYNC_ON_STARTUP=false
  echo set JIRA_INDEXING_BOOTSTRAP_ON_STARTUP=false
  echo set JIRA_QA_RAG_BOOTSTRAP_ON_STARTUP=false
  echo set DITA_SPEC_INDEX_ON_STARTUP=false
  echo set AEM_DOCS_CRAWL_ENABLED=false
  echo set DITA_PDF_INDEX_ENABLED=false
  echo "%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port 8001
) > "%RUN_DIR%\backend-local.cmd"

(
  echo @echo off
  echo cd /d "%FRONTEND_DIR%"
  echo set VITE_PROXY_TARGET=http://127.0.0.1:8001
  echo set VITE_DEV_HOST=127.0.0.1
  echo set VITE_DEV_PORT=5173
  echo node start-vite-native.mjs
) > "%RUN_DIR%\frontend-local.cmd"

start "AEM Guides Backend" cmd /k "%RUN_DIR%\backend-local.cmd"
start "AEM Guides Frontend" cmd /k "%RUN_DIR%\frontend-local.cmd"

echo.
echo Waiting for backend health...
set "BACKEND_READY=0"
for /L %%i in (1,1,30) do (
  curl -s -m 2 http://127.0.0.1:8001/health >nul 2>nul
  if not errorlevel 1 (
    set "BACKEND_READY=1"
    goto backend_ready
  )
  ping -n 2 127.0.0.1 >nul
)

:backend_ready
if "%BACKEND_READY%"=="1" (
  echo [OK] Backend is healthy.
) else (
  echo [WARN] Backend did not respond yet.
  echo        Check the "AEM Guides Backend" terminal window for errors.
)

echo Waiting for frontend...
set "FRONTEND_READY=0"
for /L %%i in (1,1,20) do (
  curl -s -m 2 http://127.0.0.1:5173/ >nul 2>nul
  if not errorlevel 1 (
    set "FRONTEND_READY=1"
    goto frontend_ready
  )
  ping -n 2 127.0.0.1 >nul
)

:frontend_ready
if "%FRONTEND_READY%"=="1" (
  echo [OK] Frontend is reachable.
) else (
  echo [WARN] Frontend did not respond yet.
  echo        Check the "AEM Guides Frontend" terminal window for errors.
)

start http://127.0.0.1:5173/

echo Launched. Keep both terminal windows open while testing.
echo To stop: double-click STOP_LOCAL.cmd
