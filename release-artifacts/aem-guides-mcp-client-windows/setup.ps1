[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [Alias("Url")]
    [string]$BackendUrl = $(if ($env:AEM_STUDIO_URL) { $env:AEM_STUDIO_URL } else { "http://10.42.46.78:4502" }),

    [Parameter(Position = 1)]
    [string]$Token = $(if ($env:AEM_STUDIO_TOKEN) { $env:AEM_STUDIO_TOKEN } else { "dev-bypass" }),

    [switch]$SkipSmoke,
    [switch]$SkipClaudeRegister
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$ClientDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ClientDir

$installArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $ClientDir "install.ps1"), "-BackendUrl", $BackendUrl, "-Token", $Token)
if ($SkipSmoke) {
    $installArgs += "-SkipSmoke"
}

& powershell @installArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ClientDir "install_claude_assets.ps1")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($SkipClaudeRegister) {
    Write-Host "Skipping Claude MCP registration because -SkipClaudeRegister was provided."
} else {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ClientDir "register_claude.ps1") -Scope user
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "Validate registration:"
Write-Host "  .\doctor_claude.cmd"
Write-Host "  claude mcp list"
Write-Host ""
Write-Host "Restart Claude Code, then try:"
Write-Host "  Ask Claude: use MCP tool upload_dataset_to_aem with source_path=C:\Users\<you>\Downloads\aem-seed-data and target_path=/content/dam/guides-qa/GUIDES-12345"
