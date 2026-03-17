# Kill processes using ports 8000 (backend) and 5173 (frontend)
# Run this if RUN_BOTH.ps1 fails with "Backend did not respond" or port-in-use errors

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

Write-Host "Clearing ports 8000 and 5173..." -ForegroundColor Cyan
Kill-Port 8000
Kill-Port 5173
Start-Sleep -Seconds 2
Write-Host "Done. Run .\RUN_BOTH.ps1 to start." -ForegroundColor Green
