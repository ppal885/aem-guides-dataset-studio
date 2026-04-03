# Run AEM Guides Dataset Studio with Docker
# Prerequisites: Docker Desktop installed and running

param(
    [switch]$Dev,
    [switch]$Build
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot

Write-Host "AEM Guides Dataset Studio - Docker" -ForegroundColor Green
Write-Host ""

# Check Docker
try {
    docker info | Out-Null
} catch {
    Write-Host "ERROR: Docker is not running. Start Docker Desktop and try again." -ForegroundColor Red
    exit 1
}

Set-Location $projectRoot

if ($Build) {
    Write-Host "Building images..." -ForegroundColor Yellow
    docker compose build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($Dev) {
    Write-Host "Starting in DEVELOPMENT mode (hot-reload)..." -ForegroundColor Cyan
    Write-Host "  Backend: http://localhost:8000" -ForegroundColor White
    Write-Host "  Frontend: http://localhost:5173" -ForegroundColor White
    Write-Host ""
    docker compose -f docker-compose.yml -f docker-compose.dev.yml up
} else {
    Write-Host "Starting in PRODUCTION mode..." -ForegroundColor Cyan
    Write-Host "  Frontend: http://localhost (port 80)" -ForegroundColor White
    Write-Host "  Backend API: proxied at /api" -ForegroundColor White
    Write-Host ""
    docker compose up
}
