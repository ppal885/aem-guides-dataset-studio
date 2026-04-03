# Start Backend Server in new window
Write-Host "Starting Backend Server in new window..." -ForegroundColor Cyan
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPath = Join-Path $scriptPath "backend"

# Try to use Python directly with full path to avoid Windows Store permission issues
$pythonPath = "C:\Users\prashantp\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe"

if (Test-Path $pythonPath) {
    Write-Host "Using Python at: $pythonPath" -ForegroundColor Green
    $command = "cd '$backendPath'; Write-Host 'Starting Backend Server...' -ForegroundColor Green; & '$pythonPath' run_local.py"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $command
} else {
    Write-Host "Python not found at expected path. Trying 'python' command..." -ForegroundColor Yellow
    Write-Host "If this fails, see RUN_BACKEND.md for solutions" -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$backendPath'; Write-Host 'Starting Backend Server...' -ForegroundColor Green; python run_local.py"
}

Write-Host "Backend server starting in new window..." -ForegroundColor Green
Write-Host "Server will be available at http://localhost:8000" -ForegroundColor Cyan
Write-Host "API docs: http://localhost:8000/docs" -ForegroundColor Cyan
