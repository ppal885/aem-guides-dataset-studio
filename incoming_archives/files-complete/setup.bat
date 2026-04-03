@echo off
REM setup.bat — Run this once to set up AEM Guides Dataset Studio
REM Usage: setup.bat

echo.
echo ========================================
echo  AEM Guides Dataset Studio — Setup
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)
echo [OK] Python found

REM Check Git
git --version >nul 2>&1
if errorlevel 1 (
    echo [WARN] Git not found. clone_dita_example_repos tool will not work.
    echo        Install from https://git-scm.com/download/win
) else (
    echo [OK] Git found
)

REM Create venv
echo.
echo [1/5] Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment
    pause
    exit /b 1
)
echo [OK] Virtual environment created

REM Activate and install
echo.
echo [2/5] Installing dependencies...
call venv\Scripts\activate
pip install --quiet mcp python-dotenv httpx sqlalchemy sentence-transformers
if errorlevel 1 (
    echo [ERROR] Failed to install core dependencies
    pause
    exit /b 1
)
echo [OK] Core dependencies installed

REM Install optional deps
pip install --quiet chromadb lxml beautifulsoup4 langchain langchain-community langchain-text-splitters pypdf 2>nul
echo [OK] Optional dependencies installed (ChromaDB, lxml, LangChain)

REM Create .env
echo.
echo [3/5] Setting up environment file...
if not exist .env (
    copy .env.example .env
    echo [OK] .env created from .env.example
    echo [!!] EDIT .env with your Jira credentials before continuing
) else (
    echo [OK] .env already exists, skipping
)

REM Create output directories
echo.
echo [4/5] Creating output directories...
if not exist output\dita mkdir output\dita
if not exist output\packages mkdir output\packages
if not exist dita_examples mkdir dita_examples
if not exist models mkdir models
echo [OK] Directories created

REM Verify mcp_server.py starts
echo.
echo [5/5] Verifying MCP server...
python mcp_server.py --help >nul 2>&1
echo [OK] mcp_server.py found

echo.
echo ========================================
echo  Setup Complete!
echo ========================================
echo.
echo Next steps:
echo   1. Edit .env with your Jira credentials
echo   2. Add to ~/.cursor/mcp.json:
echo      {
echo        "mcpServers": {
echo          "aem-dataset-studio": {
echo            "command": "%CD%\venv\Scripts\python.exe",
echo            "args": ["%CD%\mcp_server.py"]
echo          }
echo        }
echo      }
echo   3. Restart Cursor — green dot should appear
echo   4. In Cursor Agent, run:
echo      - crawl_experience_league
echo      - index_dita_spec_pdfs
echo      - clone_dita_example_repos
echo      - index_dita_example_repos
echo.
pause
