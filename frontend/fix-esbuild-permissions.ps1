# Fix esbuild Permission Issues on Windows
# This script helps resolve EPERM errors when starting Vite

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Fix esbuild Permission Issues" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Continue"

# Navigate to frontend directory
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

Write-Host "Step 1: Finding esbuild executables..." -ForegroundColor Yellow

# Find all esbuild.exe files
$esbuildPaths = @()
$esbuildPaths += Get-ChildItem -Path "node_modules" -Recurse -Filter "esbuild.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
$esbuildPaths += Get-ChildItem -Path "node_modules\vite\node_modules" -Recurse -Filter "esbuild.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName

if ($esbuildPaths.Count -eq 0) {
    Write-Host "No esbuild.exe files found. Installing dependencies..." -ForegroundColor Yellow
    npm install
    $esbuildPaths = Get-ChildItem -Path "node_modules" -Recurse -Filter "esbuild.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
}

if ($esbuildPaths.Count -eq 0) {
    Write-Host "ERROR: Still cannot find esbuild.exe. Please run 'npm install' manually." -ForegroundColor Red
    exit 1
}

Write-Host "Found $($esbuildPaths.Count) esbuild.exe file(s):" -ForegroundColor Green
foreach ($path in $esbuildPaths) {
    Write-Host "  - $path" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Step 2: Checking file permissions..." -ForegroundColor Yellow

# Check if running as administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host ""
    Write-Host "WARNING: Not running as Administrator!" -ForegroundColor Red
    Write-Host "Some fixes require administrator privileges." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To fix this issue:" -ForegroundColor Yellow
    Write-Host "1. Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Cyan
    Write-Host "2. Navigate to: $scriptPath" -ForegroundColor Cyan
    Write-Host "3. Run this script again: .\fix-esbuild-permissions.ps1" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "OR manually exclude from Windows Defender:" -ForegroundColor Yellow
    Write-Host "1. Open Windows Security" -ForegroundColor Cyan
    Write-Host "2. Virus & threat protection > Manage settings" -ForegroundColor Cyan
    Write-Host "3. Exclusions > Add or remove exclusions" -ForegroundColor Cyan
    Write-Host "4. Add folder: $scriptPath\node_modules" -ForegroundColor Cyan
    Write-Host ""
    
    # Try to unblock files anyway (might work without admin)
    Write-Host "Attempting to unblock files (may not work without admin)..." -ForegroundColor Yellow
    foreach ($path in $esbuildPaths) {
        try {
            Unblock-File -Path $path -ErrorAction SilentlyContinue
            Write-Host "  Unblocked: $path" -ForegroundColor Green
        } catch {
            Write-Host "  Failed to unblock: $path" -ForegroundColor Red
        }
    }
    
    Write-Host ""
    Write-Host "Trying to start dev server anyway..." -ForegroundColor Yellow
    Write-Host "If it fails, please use Administrator PowerShell." -ForegroundColor Yellow
    Write-Host ""
    
    exit 0
}

Write-Host "Running as Administrator - applying fixes..." -ForegroundColor Green
Write-Host ""

# Unblock all esbuild files
Write-Host "Step 3: Unblocking esbuild files..." -ForegroundColor Yellow
foreach ($path in $esbuildPaths) {
    try {
        Unblock-File -Path $path -ErrorAction Stop
        Write-Host "  ✓ Unblocked: $path" -ForegroundColor Green
    } catch {
        Write-Host "  ✗ Failed to unblock: $path" -ForegroundColor Red
        Write-Host "    Error: $_" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Step 4: Setting file permissions..." -ForegroundColor Yellow

# Set permissions to allow execution
foreach ($path in $esbuildPaths) {
    try {
        $acl = Get-Acl $path
        $permission = "BUILTIN\Users", "ReadAndExecute", "Allow"
        $accessRule = New-Object System.Security.AccessControl.FileSystemAccessRule $permission
        $acl.SetAccessRule($accessRule)
        Set-Acl $path $acl
        Write-Host "  ✓ Set permissions: $path" -ForegroundColor Green
    } catch {
        Write-Host "  ✗ Failed to set permissions: $path" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Fix Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. If Windows Defender still blocks, add exclusion (see instructions above)" -ForegroundColor Cyan
Write-Host "2. Try starting the dev server:" -ForegroundColor Cyan
Write-Host "   npm run dev" -ForegroundColor White
Write-Host ""
Write-Host "If issues persist, exclude this folder from Windows Defender:" -ForegroundColor Yellow
Write-Host "  $scriptPath\node_modules" -ForegroundColor White
Write-Host ""
