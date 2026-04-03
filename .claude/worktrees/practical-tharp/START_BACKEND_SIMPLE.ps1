# Simple Backend Starter
Write-Host "Starting Backend Server..." -ForegroundColor Green

$backendDir = Join-Path $PSScriptRoot "backend"
$venvPython = Join-Path $backendDir ".venv\Scripts\python.exe"
$fallbackPython = "C:\Users\prashantp\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe"

# Prefer venv Python (has httpx, anthropic, etc.)
$pythonExe = if (Test-Path $venvPython) { $venvPython } elseif (Test-Path $fallbackPython) { $fallbackPython } else { "python" }

if (-not (Test-Path $backendDir)) {
    Write-Host "ERROR: Backend directory not found: $backendDir" -ForegroundColor Red
    exit 1
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
