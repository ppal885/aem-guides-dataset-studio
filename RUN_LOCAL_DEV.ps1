# One-command local launcher for AEM Guides Dataset Studio on Windows.
# Starts:
#   - Backend:  http://127.0.0.1:8001
#   - Frontend: http://127.0.0.1:5173
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\RUN_LOCAL_DEV.ps1
#   powershell -ExecutionPolicy Bypass -File .\RUN_LOCAL_DEV.ps1 -Stop

param(
    [switch]$Stop,
    [int]$BackendPort = 8001,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$LogDir = Join-Path $Root "logs"
$RunDir = Join-Path $Root ".run-local"
$BackendPidFile = Join-Path $RunDir "backend.pid"
$FrontendPidFile = Join-Path $RunDir "frontend.pid"
$BackendOut = Join-Path $LogDir "local-backend.out.log"
$BackendErr = Join-Path $LogDir "local-backend.err.log"
$FrontendOut = Join-Path $LogDir "local-frontend.out.log"
$FrontendErr = Join-Path $LogDir "local-frontend.err.log"

New-Item -ItemType Directory -Force -Path $LogDir, $RunDir | Out-Null

function Write-Step($Message) {
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Ok($Message) {
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warn($Message) {
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Stop-ByPidFile($Path, $Label) {
    if (Test-Path $Path) {
        $pidValue = Get-Content $Path -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($pidValue) {
            $proc = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Step "Stopping $Label pid $pidValue"
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            }
        }
        Remove-Item $Path -Force -ErrorAction SilentlyContinue
    }
}

function Stop-ByPort($Port) {
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    foreach ($connection in $connections) {
        if ($connection.OwningProcess) {
            Write-Step "Stopping process $($connection.OwningProcess) on port $Port"
            Stop-Process -Id $connection.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}

function Resolve-Python {
    $candidates = @(
        (Join-Path $BackendDir ".venv312\Scripts\python.exe"),
        (Join-Path $BackendDir ".venv\Scripts\python.exe"),
        (Join-Path $Root "venv\Scripts\python.exe"),
        "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
        "python"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -ne "python" -and -not (Test-Path $candidate)) {
            continue
        }
        try {
            & $candidate --version *> $null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        } catch {
        }
    }
    return $null
}

function Wait-Http($Url, $Seconds) {
    for ($i = 1; $i -le $Seconds; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        } catch {
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Wait-Port($Port, $Seconds) {
    for ($i = 1; $i -le $Seconds; $i++) {
        try {
            $client = [System.Net.Sockets.TcpClient]::new()
            $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
            if ($async.AsyncWaitHandle.WaitOne(1000, $false)) {
                $client.EndConnect($async)
                $client.Close()
                return $true
            }
            $client.Close()
        } catch {
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Start-CmdBackground($Command, $WorkingDirectory, $PidFile) {
    $name = [System.IO.Path]::GetFileNameWithoutExtension($PidFile)
    $runner = Join-Path $RunDir "run-$name.cmd"
    @(
        "@echo off",
        "cd /d `"$WorkingDirectory`"",
        $Command
    ) | Set-Content -Path $runner -Encoding ASCII

    & cmd.exe /c "start `"`" /MIN `"$runner`""
    "0" | Set-Content -Path $PidFile
    return 0
}

if ($Stop) {
    Stop-ByPidFile $FrontendPidFile "frontend"
    Stop-ByPidFile $BackendPidFile "backend"
    Stop-ByPort $FrontendPort
    Stop-ByPort $BackendPort
    Write-Ok "Stopped local frontend/backend."
    exit 0
}

if (-not (Test-Path $BackendDir)) {
    throw "Backend directory not found: $BackendDir"
}
if (-not (Test-Path $FrontendDir)) {
    throw "Frontend directory not found: $FrontendDir"
}

Write-Step "Cleaning ports $BackendPort and $FrontendPort"
Stop-ByPidFile $FrontendPidFile "frontend"
Stop-ByPidFile $BackendPidFile "backend"
Stop-ByPort $FrontendPort
Stop-ByPort $BackendPort
Start-Sleep -Seconds 2

$python = Resolve-Python
if (-not $python) {
    throw "No Python found. Install Python 3.11/3.12 or create backend virtual environment."
}

Write-Step "Using Python: $python"
try {
    & $python -c "import fastapi, uvicorn, dotenv" *> $null
} catch {
    Write-Warn "Backend dependencies are missing for $python"
    Write-Warn "Run: $python -m pip install -r backend\requirements.txt"
    throw
}

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Step "Installing frontend dependencies"
    cmd /c "cd /d `"$FrontendDir`" && npm install"
}

$backendCommand = "set LEARNED_QA_AUTO_SYNC_ON_STARTUP=false&& set JIRA_INDEXING_BOOTSTRAP_ON_STARTUP=false&& set JIRA_QA_RAG_BOOTSTRAP_ON_STARTUP=false&& set DITA_SPEC_INDEX_ON_STARTUP=false&& set AEM_DOCS_CRAWL_ENABLED=false&& set DITA_PDF_INDEX_ENABLED=false&& `"$python`" -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort > `"$BackendOut`" 2> `"$BackendErr`""
Write-Step "Starting backend on http://127.0.0.1:$BackendPort"
Start-CmdBackground $backendCommand $BackendDir $BackendPidFile | Out-Null

if (-not (Wait-Port $BackendPort 60)) {
    Write-Warn "Backend did not become healthy. Logs:"
    Get-Content $BackendErr -Tail 80 -ErrorAction SilentlyContinue
    Get-Content $BackendOut -Tail 80 -ErrorAction SilentlyContinue
    throw "Backend startup failed."
}
Write-Ok "Backend healthy"

$frontendCommand = "set VITE_PROXY_TARGET=http://127.0.0.1:$BackendPort&& set VITE_DEV_HOST=127.0.0.1&& set VITE_DEV_PORT=$FrontendPort&& node start-vite-native.mjs > `"$FrontendOut`" 2> `"$FrontendErr`""
Write-Step "Starting frontend on http://127.0.0.1:$FrontendPort"
Start-CmdBackground $frontendCommand $FrontendDir $FrontendPidFile | Out-Null

if (-not (Wait-Http "http://127.0.0.1:$FrontendPort/" 30)) {
    Write-Warn "Frontend did not become reachable. Logs:"
    Get-Content $FrontendErr -Tail 80 -ErrorAction SilentlyContinue
    Get-Content $FrontendOut -Tail 80 -ErrorAction SilentlyContinue
    throw "Frontend startup failed."
}
Write-Ok "Frontend reachable"

Write-Host ""
Write-Host "AEM Guides Dataset Studio is running:" -ForegroundColor Green
Write-Host "  Frontend : http://127.0.0.1:$FrontendPort"
Write-Host "  Backend  : http://127.0.0.1:$BackendPort/health"
Write-Host "  Logs     : $LogDir"
Write-Host ""
Write-Host "Stop:"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\RUN_LOCAL_DEV.ps1 -Stop"
