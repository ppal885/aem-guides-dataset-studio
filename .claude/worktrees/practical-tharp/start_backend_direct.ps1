# Start Backend Server - Direct Python execution
# This bypasses Windows Store Python permission issues by using Start-Process

Write-Host "Starting Backend Server..." -ForegroundColor Cyan
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPath = Join-Path $scriptPath "backend"

# Try Windows Store Python path directly
$pythonPath = "C:\Users\prashantp\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe"

if (Test-Path $pythonPath) {
    Write-Host "Using Python at: $pythonPath" -ForegroundColor Green
    Write-Host "Starting Backend Server in new window..." -ForegroundColor Cyan
    
    $scriptBlock = @"
cd '$backendPath'
Write-Host 'Starting Backend Server...' -ForegroundColor Green
& '$pythonPath' run_local.py
"@
    
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $scriptBlock
    
    Write-Host "`nBackend server starting in new window..." -ForegroundColor Green
    Write-Host "Server will be available at http://localhost:8000" -ForegroundColor Cyan
    Write-Host "API docs: http://localhost:8000/docs" -ForegroundColor Cyan
    Write-Host "`nIf you see permission errors, please install Python from:" -ForegroundColor Yellow
    Write-Host "https://www.python.org/downloads/" -ForegroundColor Yellow
} else {
    Write-Host "ERROR: Python not found at expected location!" -ForegroundColor Red
    Write-Host "Please install Python from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "Make sure to check 'Add Python to PATH' during installation" -ForegroundColor Yellow
    exit 1
}
