# Compatibility wrapper for the retired UI launcher.
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
Write-Warning "This legacy command now starts the dashboard-only UAC runtime. Use RUN_LOCAL_DEV.ps1 for new workflows."
& (Join-Path $PSScriptRoot "RUN_LOCAL_DEV.ps1") @PSBoundParameters
exit $LASTEXITCODE
