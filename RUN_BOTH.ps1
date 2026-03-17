# Run Backend + Frontend together
# Backend must be running for API calls to work (frontend proxies /api to backend:8000)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot

Write-Host "AEM Guides Dataset Studio - Starting Backend + Frontend" -ForegroundColor Green
Write-Host ""

# Stop existing processes on ports (retry loop for reliability)
Write-Host "Clearing ports 8000 and 5173..." -ForegroundColor Yellow
for ($i = 1; $i -le 5; $i++) {
    $pids8000 = @()
    $pids5173 = @()
    try {
        Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object { $pids8000 += $_.OwningProcess }
        Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue | ForEach-Object { $pids5173 += $_.OwningProcess }
    } catch { }
    $pids8000 | Select-Object -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    $pids5173 | Select-Object -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 3
    $still8000 = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
    $still5173 = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue
    if (-not $still8000 -and -not $still5173) { break }
}
Start-Sleep -Seconds 2

# Start backend
$backendDir = Join-Path $projectRoot "backend"
$venvPython = Join-Path $backendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "ERROR: Backend venv not found. Run: cd backend; python -m venv .venv; .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

Write-Host "Starting Backend on http://localhost:8000 ..." -ForegroundColor Cyan
Start-Process -FilePath $venvPython -ArgumentList "run_local.py" -WorkingDirectory $backendDir -WindowStyle Normal

# Wait up to 30 seconds for backend health check (backend may load embeddings, DB on first run)
$healthOk = $false
for ($i = 1; $i -le 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        Write-Host "Backend OK (health: $($r.StatusCode))" -ForegroundColor Green
        $healthOk = $true
        break
    } catch {
        if ($i -lt 30) {
            Write-Host "  Waiting for backend... ($i/30)" -ForegroundColor Gray
        }
    }
}
if (-not $healthOk) {
    Write-Host ""
    Write-Host "ERROR: Backend did not respond after 30 seconds." -ForegroundColor Red
    Write-Host "  - Port 8000 may be in use. Run: .\KILL_PORTS.ps1" -ForegroundColor Yellow
    Write-Host "  - Check the backend window for errors (look for 'address already in use')." -ForegroundColor Yellow
    Write-Host "  - Or start backend manually: .\START_BACKEND_SIMPLE.ps1" -ForegroundColor Yellow
    Write-Host ""
    $yn = Read-Host "Continue with frontend anyway? (y/N)"
    if ($yn -ne 'y' -and $yn -ne 'Y') { exit 1 }
}

# Start frontend
$frontendDir = Join-Path $projectRoot "frontend"
$npmPaths = @(
    "C:\Program Files\nodejs\npm.cmd",
    "${env:ProgramFiles}\nodejs\npm.cmd"
)
$npmExe = $null
foreach ($p in $npmPaths) {
    if (Test-Path $p) { $npmExe = $p; break }
}
if (-not $npmExe) {
    Write-Host "ERROR: npm not found. Install Node.js from https://nodejs.org" -ForegroundColor Red
    exit 1
}

Write-Host "Starting Frontend on http://localhost:5173 ..." -ForegroundColor Cyan
Write-Host ""
Write-Host "  Backend:  http://localhost:8000" -ForegroundColor White
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor White
Write-Host "  API docs: http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to stop both." -ForegroundColor Gray
Write-Host ""

Set-Location $frontendDir
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing frontend dependencies (first run)..." -ForegroundColor Yellow
    & $npmExe install
}
& $npmExe run dev
