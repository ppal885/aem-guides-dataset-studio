# Simple Frontend Starter - uses full path to npm (works when PATH not refreshed)
Write-Host "Starting Frontend Dev Server..." -ForegroundColor Green

$npmPaths = @(
    "C:\Program Files\nodejs\npm.cmd",
    "${env:ProgramFiles}\nodejs\npm.cmd",
    "${env:ProgramFiles(x86)}\nodejs\npm.cmd"
)

$npmExe = $null
foreach ($p in $npmPaths) {
    if (Test-Path $p) {
        $npmExe = $p
        break
    }
}

if (-not $npmExe) {
    Write-Host "ERROR: npm not found. Install Node.js from https://nodejs.org" -ForegroundColor Red
    exit 1
}

$frontendDir = Join-Path $PSScriptRoot "frontend"
if (-not (Test-Path $frontendDir)) {
    Write-Host "ERROR: Frontend directory not found: $frontendDir" -ForegroundColor Red
    exit 1
}

Write-Host "npm: $npmExe" -ForegroundColor Cyan
Write-Host "Frontend: $frontendDir" -ForegroundColor Cyan
Write-Host ""

Set-Location $frontendDir

# Ensure dependencies are installed
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing dependencies (first run)..." -ForegroundColor Yellow
    & $npmExe install
}

Write-Host "Running: npm run dev" -ForegroundColor Yellow
& $npmExe run dev
