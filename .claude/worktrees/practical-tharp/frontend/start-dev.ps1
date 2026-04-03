# Frontend Dev Server Startup Script
# This script handles Windows permission issues with esbuild

Write-Host "Starting Frontend Dev Server..." -ForegroundColor Green

$ErrorActionPreference = "Stop"

# Navigate to frontend directory
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

# Clear Vite cache
Write-Host "Clearing Vite cache..." -ForegroundColor Yellow
if (Test-Path ".vite") {
    Remove-Item -Recurse -Force ".vite" -ErrorAction SilentlyContinue
}

# Try multiple approaches to start the server
Write-Host "Attempting to start Vite dev server..." -ForegroundColor Yellow

# Approach 1: Try with --force flag
try {
    Write-Host "Trying with --force flag..." -ForegroundColor Cyan
    npm run dev -- --force
    exit 0
} catch {
    Write-Host "Failed with --force flag, trying alternative..." -ForegroundColor Yellow
}

# Approach 2: Try using vite directly
try {
    Write-Host "Trying direct vite command..." -ForegroundColor Cyan
    npx vite --force
    exit 0
} catch {
    Write-Host "Failed with direct vite, trying node_modules path..." -ForegroundColor Yellow
}

# Approach 3: Try using node_modules/.bin/vite directly
try {
    Write-Host "Trying node_modules/.bin/vite..." -ForegroundColor Cyan
    & ".\node_modules\.bin\vite.cmd" --force
    exit 0
} catch {
    Write-Host "All startup methods failed. Please check Windows Defender exclusions." -ForegroundColor Red
    Write-Host "See frontend/FIX_FRONTEND_STARTUP.md for detailed instructions." -ForegroundColor Yellow
    exit 1
}
