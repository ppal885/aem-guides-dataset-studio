# Start Backend Server in new window
Write-Host "Starting Backend Server in new window..." -ForegroundColor Cyan
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPath = Join-Path $scriptPath "backend"
$repoVenvPython = Join-Path $scriptPath "venv\Scripts\python.exe"
$backendVenvPython = Join-Path $backendPath ".venv\Scripts\python.exe"

# Prefer project-local virtualenvs first for correct dependencies and .env behavior
$pythonPath = $null
if (Test-Path $repoVenvPython) {
    $pythonPath = $repoVenvPython
} elseif (Test-Path $backendVenvPython) {
    $pythonPath = $backendVenvPython
}

# Fall back to Windows Store path only if no project venv exists
if (-not $pythonPath) {
    $pythonPath = "C:\Users\prashantp\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe"
}

if (Test-Path $pythonPath) {
    Write-Host "Using Python at: $pythonPath" -ForegroundColor Green
    $command = "cd '$backendPath'; Write-Host 'Starting Backend Server...' -ForegroundColor Green; & '$pythonPath' '$backendPath\\run_local.py'"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $command
} else {
    Write-Host "Python not found at expected path. Trying 'python' command..." -ForegroundColor Yellow
    Write-Host "If this fails, see RUN_BACKEND.md for solutions" -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$backendPath'; Write-Host 'Starting Backend Server...' -ForegroundColor Green; python run_local.py"
}

Write-Host "Backend server starting in new window..." -ForegroundColor Green
Write-Host "Server will be available at http://localhost:8001" -ForegroundColor Cyan
Write-Host "API docs: http://localhost:8001/docs" -ForegroundColor Cyan
