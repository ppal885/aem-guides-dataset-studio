# Explicitly stop listeners on the local backend and dashboard ports.
# Prefer RUN_LOCAL_DEV.ps1 -Stop; use this only for stale or externally started processes.

$ErrorActionPreference = "SilentlyContinue"

function Kill-Port {
    param([int]$Port)
    $pids = @()
    try {
        Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | ForEach-Object { $pids += $_.OwningProcess }
    } catch {
        # Fallback: netstat
        $line = netstat -ano | Select-String ":\s*$Port\s+.*LISTENING"
        if ($line) {
            $parts = $line -split '\s+'
            $pid = $parts[-1]
            if ($pid -match '^\d+$') { $pids += [int]$pid }
        }
    }
    $pids | Select-Object -Unique | ForEach-Object {
        Write-Host "Killing PID $_ on port $Port" -ForegroundColor Yellow
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Clearing ports 8001 and 8765..." -ForegroundColor Cyan
Kill-Port 8001
Kill-Port 8765
Start-Sleep -Seconds 2
Write-Host "Done. Run .\RUN_LOCAL_DEV.cmd to start." -ForegroundColor Green
