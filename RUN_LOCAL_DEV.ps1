# One-command local launcher for the UAC generator and its read-only dashboard.
# Starts:
#   - Backend API: http://127.0.0.1:8001
#   - Dashboard:   http://127.0.0.1:8765
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\RUN_LOCAL_DEV.ps1
#   powershell -ExecutionPolicy Bypass -File .\RUN_LOCAL_DEV.ps1 -Open
#   powershell -ExecutionPolicy Bypass -File .\RUN_LOCAL_DEV.ps1 -Stop

[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$Open,
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8001,
    [ValidateRange(1, 65535)]
    [int]$DashboardPort = 8765
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$DashboardDir = Join-Path $Root "scripts\uac_eval"
$Aggregator = Join-Path $DashboardDir "aggregate_runs.py"
$DashboardPage = Join-Path $DashboardDir "dashboard.html"
$LogDir = Join-Path $Root "logs"
$RunDir = Join-Path $Root ".run-local"
$BackendPidFile = Join-Path $RunDir "backend.pid"
$DashboardPidFile = Join-Path $RunDir "dashboard.pid"
$DashboardSitePathFile = Join-Path $RunDir "dashboard-site.path"
$BackendOut = Join-Path $LogDir "local-backend.out.log"
$BackendErr = Join-Path $LogDir "local-backend.err.log"
$DashboardOut = Join-Path $LogDir "local-dashboard.out.log"
$DashboardErr = Join-Path $LogDir "local-dashboard.err.log"

New-Item -ItemType Directory -Force -Path $LogDir, $RunDir | Out-Null

function Write-Step([string]$Message) {
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warn([string]$Message) {
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Stop-ByPidFile([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    $pidValue = Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pidValue -and $pidValue -match '^\d+$') {
        $process = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
        if ($process) {
            Write-Step "Stopping $Label (PID $pidValue)"
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
}

function Test-IsolatedDashboardPath([string]$Path) {
    if (-not $Path) {
        return $false
    }
    $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\', '/')
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $requiredPrefix = $tempRoot + [System.IO.Path]::DirectorySeparatorChar + "aem-guides-dashboard-site-"
    return $fullPath.StartsWith($requiredPrefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Remove-IsolatedDashboardSite {
    if (-not (Test-Path -LiteralPath $DashboardSitePathFile)) {
        return
    }
    $sitePath = Get-Content -LiteralPath $DashboardSitePathFile -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($sitePath -and (Test-IsolatedDashboardPath $sitePath)) {
        $item = Get-Item -LiteralPath $sitePath -Force -ErrorAction SilentlyContinue
        if ($item -and -not ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            Remove-Item -LiteralPath $sitePath -Recurse -Force -ErrorAction SilentlyContinue
        } elseif ($item) {
            Write-Warn "Refusing to remove reparse-point dashboard staging path: $sitePath"
        }
    } elseif ($sitePath) {
        Write-Warn "Refusing to remove untrusted dashboard staging path: $sitePath"
    }
    Remove-Item -LiteralPath $DashboardSitePathFile -Force -ErrorAction SilentlyContinue
}

function Copy-PreservedFile([string]$Source, [string]$Destination) {
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
    (Get-Item -LiteralPath $Destination).LastWriteTimeUtc =
        (Get-Item -LiteralPath $Source).LastWriteTimeUtc
}

function Get-DashboardRunIds([string]$Path, [string]$Label) {
    $payload = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $payload.runs) {
        throw "$Label dashboard data must contain a runs list."
    }
    $ids = @()
    foreach ($row in @($payload.runs)) {
        if (-not $row -or -not ($row.run_id -is [string]) -or [string]::IsNullOrWhiteSpace($row.run_id)) {
            throw "$Label dashboard data has an invalid run_id."
        }
        $ids += $row.run_id
    }
    if (@($ids | Select-Object -Unique).Count -ne $ids.Count) {
        throw "$Label dashboard data contains duplicate run IDs."
    }
    return $ids
}

function New-IsolatedDashboardSite([string]$Python) {
    $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $buildDir = Join-Path $tempRoot ("aem-guides-dashboard-build-" + [guid]::NewGuid().ToString("N"))
    $siteDir = Join-Path $tempRoot ("aem-guides-dashboard-site-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $buildDir, $siteDir | Out-Null
    try {
        $isolatedAggregator = Join-Path $buildDir "aggregate_runs.py"
        $generatedData = Join-Path $buildDir "dashboard_data.json"
        Copy-PreservedFile $Aggregator $isolatedAggregator
        foreach ($source in Get-ChildItem -LiteralPath $DashboardDir -Filter "judge_pipeline*.json" -File) {
            Copy-PreservedFile $source.FullName (Join-Path $buildDir $source.Name)
        }

        $aggregationOutput = & $Python $isolatedAggregator 2>&1
        $aggregationCode = $LASTEXITCODE
        $aggregationOutput | ForEach-Object { Write-Host $_ }
        if ($aggregationCode -ne 0 -or -not (Test-Path -LiteralPath $generatedData)) {
            throw "Isolated dashboard aggregation failed with exit code $aggregationCode."
        }

        $generatedIds = @(Get-DashboardRunIds $generatedData "Generated")
        $snapshotPath = Join-Path $DashboardDir "dashboard_data.json"
        if (Test-Path -LiteralPath $snapshotPath) {
            $snapshotIds = @(Get-DashboardRunIds $snapshotPath "Checked-in")
            $missingIds = @($snapshotIds | Where-Object { $generatedIds -notcontains $_ })
            $newIds = @($generatedIds | Where-Object { $snapshotIds -notcontains $_ })
            if ($missingIds.Count -gt 0 -and $newIds.Count -eq 0) {
                Write-Warn "Eligible run inputs are a strict subset of checked-in dashboard history; retaining $($snapshotIds.Count) runs instead of $($generatedIds.Count)."
                Copy-PreservedFile $snapshotPath $generatedData
            } elseif ($missingIds.Count -gt 0) {
                throw "Isolated aggregation would drop checked-in run IDs: $($missingIds -join ', ')."
            }
        }

        Copy-PreservedFile $DashboardPage (Join-Path $siteDir "index.html")
        Copy-PreservedFile $generatedData (Join-Path $siteDir "dashboard_data.json")
        $siteFiles = @(Get-ChildItem -LiteralPath $siteDir | Select-Object -ExpandProperty Name | Sort-Object)
        if (($siteFiles -join ',') -ne "dashboard_data.json,index.html") {
            throw "Dashboard staging directory contains unexpected files."
        }
        return $siteDir
    } catch {
        if (Test-IsolatedDashboardPath $siteDir) {
            Remove-Item -LiteralPath $siteDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        throw
    } finally {
        $buildFull = [System.IO.Path]::GetFullPath($buildDir)
        $tempPrefix = [System.IO.Path]::GetFullPath($tempRoot).TrimEnd('\', '/') +
            [System.IO.Path]::DirectorySeparatorChar + "aem-guides-dashboard-build-"
        if ($buildFull.StartsWith($tempPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $buildFull -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

function Get-PortOwner([int]$Port) {
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($connection) {
        return $connection.OwningProcess
    }
    return $null
}

function Wait-Http([string]$Url, [int]$Seconds) {
    for ($attempt = 1; $attempt -le $Seconds; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                return $true
            }
        } catch {
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Resolve-Python {
    $candidates = @(
        (Join-Path $BackendDir ".venv312\Scripts\python.exe"),
        (Join-Path $BackendDir ".venv\Scripts\python.exe"),
        (Join-Path $BackendDir "venv\Scripts\python.exe"),
        (Join-Path $Root "venv\Scripts\python.exe"),
        "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
        "python"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -ne "python" -and -not (Test-Path -LiteralPath $candidate)) {
            continue
        }
        try {
            & $candidate -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" *> $null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        } catch {
        }
    }
    return $null
}

function Stop-OwnedProcesses {
    Stop-ByPidFile $DashboardPidFile "dashboard"
    Stop-ByPidFile $BackendPidFile "backend"
    Remove-IsolatedDashboardSite
}

if ($Stop) {
    Stop-OwnedProcesses
    foreach ($port in @($DashboardPort, $BackendPort)) {
        $owner = Get-PortOwner $port
        if ($owner) {
            Write-Warn "Port $port is still owned by PID $owner; it was not started by this launcher and was left running."
        }
    }
    Write-Ok "Stopped launcher-owned dashboard and backend processes."
    exit 0
}

foreach ($requiredPath in @($BackendDir, $DashboardDir, $Aggregator, $DashboardPage)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required path not found: $requiredPath"
    }
}

Stop-OwnedProcesses
foreach ($port in @($BackendPort, $DashboardPort)) {
    $owner = Get-PortOwner $port
    if ($owner) {
        throw "Port $port is already in use by PID $owner. Stop it explicitly or choose another port."
    }
}

$python = Resolve-Python
if (-not $python) {
    throw "No working Python interpreter found. Create backend\.venv or install Python 3.11+."
}

Write-Step "Using Python: $python"
& $python -c "import fastapi, uvicorn, dotenv" *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Backend dependencies are missing for $python"
    Write-Warn "Run: $python -m pip install -r backend\requirements.txt"
    throw "Backend dependency check failed."
}

Write-Step "Preparing dashboard data in an isolated staging directory"
$DashboardSiteDir = New-IsolatedDashboardSite $python
$DashboardSiteDir | Set-Content -LiteralPath $DashboardSitePathFile -Encoding UTF8

# These opt-out switches keep local startup deterministic and avoid background ingestion.
$env:LEARNED_QA_AUTO_SYNC_ON_STARTUP = "false"
$env:JIRA_INDEXING_BOOTSTRAP_ON_STARTUP = "false"
$env:JIRA_QA_RAG_BOOTSTRAP_ON_STARTUP = "false"
$env:DITA_SPEC_INDEX_ON_STARTUP = "false"
$env:AEM_DOCS_CRAWL_ENABLED = "false"
$env:DITA_PDF_INDEX_ENABLED = "false"

try {
    Write-Step "Starting backend on http://127.0.0.1:$BackendPort"
    $backendProcess = Start-Process `
        -FilePath $python `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$BackendPort") `
        -WorkingDirectory $BackendDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput $BackendOut `
        -RedirectStandardError $BackendErr `
        -PassThru
    $backendProcess.Id | Set-Content -LiteralPath $BackendPidFile -Encoding ASCII

    if (-not (Wait-Http "http://127.0.0.1:$BackendPort/health" 60)) {
        throw "Backend did not become healthy. Review $BackendErr and $BackendOut."
    }
    Write-Ok "Backend is healthy"

    Write-Step "Starting static dashboard on http://127.0.0.1:$DashboardPort"
    $dashboardProcess = Start-Process `
        -FilePath $python `
        -ArgumentList @("-m", "http.server", "$DashboardPort", "--bind", "127.0.0.1") `
        -WorkingDirectory $DashboardSiteDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput $DashboardOut `
        -RedirectStandardError $DashboardErr `
        -PassThru
    $dashboardProcess.Id | Set-Content -LiteralPath $DashboardPidFile -Encoding ASCII

    if (-not (Wait-Http "http://127.0.0.1:$DashboardPort/" 30)) {
        throw "Dashboard did not become reachable. Review $DashboardErr and $DashboardOut."
    }
    Write-Ok "Dashboard is reachable"
} catch {
    Stop-OwnedProcesses
    throw
}

$dashboardUrl = "http://127.0.0.1:$DashboardPort/"
Write-Host ""
Write-Host "AEM Guides UAC runtime is running:" -ForegroundColor Green
Write-Host "  Dashboard      : $dashboardUrl"
Write-Host "  Backend health : http://127.0.0.1:$BackendPort/health"
Write-Host "  API docs       : http://127.0.0.1:$BackendPort/docs"
Write-Host "  Logs           : $LogDir"
Write-Host ""
Write-Host "Generate a UAC with the HTTP runtime:"
Write-Host "  python scripts\run_test_plan_pipeline.py GUIDES-12345 --http --base-url http://127.0.0.1:$BackendPort"
Write-Host ""
Write-Host "Stop:"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\RUN_LOCAL_DEV.ps1 -Stop"

if ($Open) {
    Start-Process $dashboardUrl
}
