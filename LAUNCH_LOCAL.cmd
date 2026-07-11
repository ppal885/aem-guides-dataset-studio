@echo off
setlocal

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "FRONTEND_DIR=%ROOT%frontend"
set "PYTHON_EXE=%BACKEND_DIR%\.venv312\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  set "PYTHON_EXE=python"
)

echo Starting AEM Guides Dataset Studio locally...
echo.
echo Backend:  http://127.0.0.1:8001
echo Frontend: http://127.0.0.1:5173
echo.

call "%ROOT%STOP_LOCAL.cmd" >nul 2>nul

start "AEM Guides Backend" cmd /k "cd /d "%BACKEND_DIR%" && set LEARNED_QA_AUTO_SYNC_ON_STARTUP=false&& set JIRA_INDEXING_BOOTSTRAP_ON_STARTUP=false&& set JIRA_QA_RAG_BOOTSTRAP_ON_STARTUP=false&& set DITA_SPEC_INDEX_ON_STARTUP=false&& set AEM_DOCS_CRAWL_ENABLED=false&& set DITA_PDF_INDEX_ENABLED=false&& "%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port 8001"

start "AEM Guides Frontend" cmd /k "cd /d "%FRONTEND_DIR%" && set VITE_PROXY_TARGET=http://127.0.0.1:8001&& set VITE_DEV_HOST=127.0.0.1&& set VITE_DEV_PORT=5173&& node start-vite-native.mjs"

timeout /t 6 /nobreak >nul
start http://127.0.0.1:5173/

echo Launched. Keep both terminal windows open while testing.
echo To stop: double-click STOP_LOCAL.cmd
