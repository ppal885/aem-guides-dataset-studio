[CmdletBinding()]
param(
    [ValidateSet("user", "local", "project")]
    [string]$Scope = "user",

    [switch]$SkipList,

    [switch]$NoGlobalConfigFallback
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$ClientDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ClientDir

$ConfigPath = Join-Path $ClientDir "claude-mcp-server.json"
if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "Missing claude-mcp-server.json. Run install.ps1 or setup.ps1 first."
}

function Write-Utf8NoBomFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Text
    )
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $encoding)
}

function Read-JsonObject {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return [pscustomobject]@{}
    }
    $raw = Get-Content -LiteralPath $Path -Raw
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return [pscustomobject]@{}
    }
    return $raw | ConvertFrom-Json
}

function Test-GlobalClaudeRegistration {
    $claudeJsonPath = Join-Path $HOME ".claude.json"
    if (-not (Test-Path -LiteralPath $claudeJsonPath)) {
        return $false
    }
    try {
        $config = Read-JsonObject -Path $claudeJsonPath
        return [bool](
            $config.PSObject.Properties["mcpServers"] -and
            $config.mcpServers.PSObject.Properties["aem-guides-dataset-studio"]
        )
    } catch {
        return $false
    }
}

function Set-GlobalClaudeRegistration {
    param([Parameter(Mandatory = $true)]$ServerConfig)

    $claudeJsonPath = Join-Path $HOME ".claude.json"
    $config = Read-JsonObject -Path $claudeJsonPath

    if (-not $config.PSObject.Properties["mcpServers"]) {
        $config | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([pscustomobject]@{})
    }

    $config.mcpServers | Add-Member `
        -Force `
        -NotePropertyName "aem-guides-dataset-studio" `
        -NotePropertyValue $ServerConfig

    Write-Utf8NoBomFile -Path $claudeJsonPath -Text (($config | ConvertTo-Json -Depth 20) + "`n")
    return $claudeJsonPath
}

$json = Get-Content -LiteralPath $ConfigPath -Raw
$serverConfig = $json | ConvertFrom-Json

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Warning "Claude Code CLI not found on PATH."
    if (-not $NoGlobalConfigFallback) {
        $globalPath = Set-GlobalClaudeRegistration -ServerConfig $serverConfig
        Write-Host "Wrote MCP registration directly to: $globalPath"
    }
    Write-Host "Fallback: start Claude Code from this folder so project .mcp.json is also picked up:"
    Write-Host "  cd `"$ClientDir`""
    Write-Host "  claude"
    exit 0
}

$registeredByCli = $false

& claude mcp add-json --scope $Scope aem-guides-dataset-studio $json
if ($LASTEXITCODE -eq 0) {
    $registeredByCli = $true
} else {
    Write-Warning "Claude MCP registration with --scope $Scope failed with exit code $LASTEXITCODE. Trying legacy syntax."
    & claude mcp add-json aem-guides-dataset-studio $json
    if ($LASTEXITCODE -eq 0) {
        $registeredByCli = $true
    }
}

if (-not $registeredByCli) {
    Write-Warning "Claude CLI registration did not succeed."
}

if ($Scope -eq "user" -and -not $NoGlobalConfigFallback) {
    $globalPath = Set-GlobalClaudeRegistration -ServerConfig $serverConfig
    if (-not (Test-GlobalClaudeRegistration)) {
        throw "MCP registration was not found in $globalPath after repair."
    }
    Write-Host "Verified MCP registration in: $globalPath"
}

Write-Host "Registered MCP server: aem-guides-dataset-studio (scope: $Scope)"
Write-Host "Restart Claude Code after registration."

if (-not $SkipList) {
    & claude mcp list
}
