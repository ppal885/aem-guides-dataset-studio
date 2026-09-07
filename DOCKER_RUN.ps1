# Run the UAC backend in Docker and the read-only dashboard with Python.

[CmdletBinding()]
param(
    [switch]$Dev,
    [switch]$Build,
    [ValidateRange(1, 65535)]
    [int]$DashboardPort = 8765
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$dashboardDir = Join-Path $projectRoot "scripts\uac_eval"
$aggregator = Join-Path $dashboardDir "aggregate_runs.py"
$dashboardPage = Join-Path $dashboardDir "dashboard.html"
$logDir = Join-Path $projectRoot "logs"
$dashboardOut = Join-Path $logDir "docker-dashboard.out.log"
$dashboardErr = Join-Path $logDir "docker-dashboard.err.log"

function Resolve-Python {
    $candidates = @(
        (Join-Path $projectRoot "backend\.venv312\Scripts\python.exe"),
        (Join-Path $projectRoot "backend\.venv\Scripts\python.exe"),
        (Join-Path $projectRoot "backend\venv\Scripts\python.exe"),
        (Join-Path $projectRoot "venv\Scripts\python.exe"),
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

function Test-IsolatedDashboardPath([string]$Path) {
    if (-not $Path) {
        return $false
    }
    $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\', '/')
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $requiredPrefix = $tempRoot + [System.IO.Path]::DirectorySeparatorChar + "aem-guides-dashboard-site-"
    return $fullPath.StartsWith($requiredPrefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Remove-IsolatedDashboardSite([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    if (-not (Test-IsolatedDashboardPath $Path)) {
        throw "Refusing to remove untrusted dashboard staging path: $Path"
    }
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        throw "Refusing to remove reparse-point dashboard staging path: $Path"
    }
    Remove-Item -LiteralPath $Path -Recurse -Force
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
        Copy-PreservedFile $aggregator $isolatedAggregator
        foreach ($source in Get-ChildItem -LiteralPath $dashboardDir -Filter "judge_pipeline*.json" -File) {
            Copy-PreservedFile $source.FullName (Join-Path $buildDir $source.Name)
        }

        $aggregationOutput = & $Python $isolatedAggregator 2>&1
        $aggregationCode = $LASTEXITCODE
        $aggregationOutput | ForEach-Object { Write-Host $_ }
        if ($aggregationCode -ne 0 -or -not (Test-Path -LiteralPath $generatedData)) {
            throw "Isolated dashboard aggregation failed with exit code $aggregationCode."
        }

        $generatedIds = @(Get-DashboardRunIds $generatedData "Generated")
        $snapshotPath = Join-Path $dashboardDir "dashboard_data.json"
        if (Test-Path -LiteralPath $snapshotPath) {
            $snapshotIds = @(Get-DashboardRunIds $snapshotPath "Checked-in")
            $missingIds = @($snapshotIds | Where-Object { $generatedIds -notcontains $_ })
            $newIds = @($generatedIds | Where-Object { $snapshotIds -notcontains $_ })
            if ($missingIds.Count -gt 0 -and $newIds.Count -eq 0) {
                Write-Warning "Eligible run inputs are a strict subset of checked-in dashboard history; retaining $($snapshotIds.Count) runs instead of $($generatedIds.Count)."
                Copy-PreservedFile $snapshotPath $generatedData
            } elseif ($missingIds.Count -gt 0) {
                throw "Isolated aggregation would drop checked-in run IDs: $($missingIds -join ', ')."
            }
        }

        Copy-PreservedFile $dashboardPage (Join-Path $siteDir "index.html")
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

try {
    docker info | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "docker info failed"
    }
} catch {
    Write-Host "ERROR: Docker is not running. Start Docker Desktop and try again." -ForegroundColor Red
    exit 1
}

foreach ($requiredPath in @($aggregator, $dashboardPage)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        Write-Host "ERROR: Required dashboard file not found: $requiredPath" -ForegroundColor Red
        exit 1
    }
}

$python = Resolve-Python
if (-not $python) {
    Write-Host "ERROR: Python 3.11+ is required to aggregate and serve the dashboard." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Location $projectRoot

if ($Build) {
    Write-Host "Building the backend image..." -ForegroundColor Yellow
    docker compose build
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$existingDashboard = Get-NetTCPConnection -LocalPort $DashboardPort -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($existingDashboard) {
    Write-Host "ERROR: Dashboard port $DashboardPort is already owned by PID $($existingDashboard.OwningProcess)." -ForegroundColor Red
    exit 1
}

$dashboardSiteDir = $null
$dashboardProcess = $null
$composeExitCode = 1
try {
    Write-Host "Preparing dashboard data in an isolated staging directory..." -ForegroundColor Cyan
    $dashboardSiteDir = New-IsolatedDashboardSite $python
    $dashboardProcess = Start-Process `
        -FilePath $python `
        -ArgumentList @("-m", "http.server", "$DashboardPort", "--bind", "127.0.0.1") `
        -WorkingDirectory $dashboardSiteDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput $dashboardOut `
        -RedirectStandardError $dashboardErr `
        -PassThru

    Write-Host "AEM Guides UAC runtime" -ForegroundColor Green
    Write-Host "  Dashboard: http://127.0.0.1:$DashboardPort/"
    Write-Host "  Backend:   http://127.0.0.1:8001"
    Write-Host "  API docs:  http://127.0.0.1:8001/docs"
    Write-Host "  Press Ctrl+C to stop Docker Compose; the dashboard helper stops with this script."
    Write-Host ""

    if ($Dev) {
        docker compose -f docker-compose.yml -f docker-compose.dev.yml up
    } else {
        docker compose up
    }
    $composeExitCode = $LASTEXITCODE
} finally {
    if ($dashboardProcess) {
        Stop-Process -Id $dashboardProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($dashboardSiteDir) {
        Remove-IsolatedDashboardSite $dashboardSiteDir
    }
}
exit $composeExitCode
