# Simple Backend Starter
Write-Host "Starting Backend Server..." -ForegroundColor Green

$backendDir = Join-Path $PSScriptRoot "backend"
$repoVenvPython = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
$backendVenvPython = Join-Path $backendDir ".venv\Scripts\python.exe"
$fallbackPython = "C:\Users\prashantp\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe"

function Resolve-PythonExe {
    param([string[]]$Candidates)

    foreach ($candidate in $Candidates) {
        if ($candidate -ne "python" -and -not (Test-Path $candidate)) { continue }
        & $candidate --version *> $null
        if ($LASTEXITCODE -eq 0) { return $candidate }
    }
    return $null
}

# Prefer project-local venvs first; fall back to system python if needed.
$pythonExe = Resolve-PythonExe @($repoVenvPython, $backendVenvPython, $fallbackPython, "python")

if (-not (Test-Path $backendDir)) {
    Write-Host "ERROR: Backend directory not found: $backendDir" -ForegroundColor Red
    exit 1
}

if (-not $pythonExe) {
    Write-Host "ERROR: Could not find a working Python executable." -ForegroundColor Red
    Write-Host "Try installing Python from https://www.python.org/downloads/ (check 'Add Python to PATH')." -ForegroundColor Yellow
    exit 1
}

if ($pythonExe -eq $backendVenvPython) {
    $cfg = Join-Path $backendDir ".venv\pyvenv.cfg"
    if (Test-Path $cfg) {
        $homeLine = (Get-Content $cfg -ErrorAction SilentlyContinue | Where-Object { $_ -match '^home\s*=\s*' } | Select-Object -First 1)
        if ($homeLine) {
            $home = ($homeLine -replace '^home\s*=\s*', '').Trim()
            if ($home -and -not (Test-Path $home)) {
                Write-Host "WARNING: backend/.venv was created with a Python that is no longer installed ($home)." -ForegroundColor Yellow
                Write-Host "         Consider recreating it: cd backend; python -m venv .venv; .venv\\Scripts\\pip install -r requirements.txt" -ForegroundColor Yellow
            }
        }
    }
}

if ($pythonExe -eq "python") {
    Write-Host "WARNING: Using system python. Run 'pip install -r requirements.txt' in backend if modules are missing." -ForegroundColor Yellow
}

Write-Host "Python: $pythonExe" -ForegroundColor Cyan
Write-Host "Backend Directory: $backendDir" -ForegroundColor Cyan
Write-Host ""

Set-Location $backendDir

Write-Host "Running: $pythonExe run_local.py" -ForegroundColor Yellow
Write-Host ""

# Try to run Python
try {
    & $pythonExe run_local.py
} catch {
    Write-Host "ERROR: Failed to start backend" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Try running manually:" -ForegroundColor Yellow
    Write-Host "  cd backend" -ForegroundColor White
    Write-Host "  $pythonExe run_local.py" -ForegroundColor White
    exit 1
}
