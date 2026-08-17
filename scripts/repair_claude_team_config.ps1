param(
    [string]$SourceProjectPath = "C:\UI TEST\guides-ui-tests",
    [string]$TargetProjectPath = "C:\ui_framework\guides-ui-tests"
)

$ErrorActionPreference = "Stop"
$ClaudeHome = Join-Path $env:USERPROFILE ".claude"
$UserConfigPath = Join-Path $env:USERPROFILE ".claude.json"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ServerName = "aem-guides-dataset-studio"

if (-not (Test-Path -LiteralPath $UserConfigPath -PathType Leaf)) {
    throw "Claude user configuration is missing: $UserConfigPath"
}

$UserBackup = "$UserConfigPath.backup-$Timestamp"
Copy-Item -LiteralPath $UserConfigPath -Destination $UserBackup
$UserConfig = Get-Content -LiteralPath $UserConfigPath -Raw | ConvertFrom-Json
if ($UserConfig.mcpServers -and $UserConfig.mcpServers.PSObject.Properties[$ServerName]) {
    $UserConfig.mcpServers.PSObject.Properties.Remove($ServerName)
    $UserConfig | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $UserConfigPath -Encoding UTF8
}

$SourceConfigPath = Join-Path ([System.IO.Path]::GetFullPath($SourceProjectPath)) ".mcp.json"
$TargetConfigPath = Join-Path ([System.IO.Path]::GetFullPath($TargetProjectPath)) ".mcp.json"
if (-not (Test-Path -LiteralPath $SourceConfigPath -PathType Leaf)) {
    throw "Configured source project MCP file is missing: $SourceConfigPath"
}
if (-not (Test-Path -LiteralPath $TargetProjectPath -PathType Container)) {
    throw "Target Claude Code project is missing: $TargetProjectPath"
}

$SourceConfig = Get-Content -LiteralPath $SourceConfigPath -Raw | ConvertFrom-Json
$RemoteServer = $SourceConfig.mcpServers.$ServerName
if (-not $RemoteServer -or $RemoteServer.type -ne "http" -or -not $RemoteServer.url) {
    throw "Source project does not contain the configured HTTP Dataset Studio MCP"
}

if (Test-Path -LiteralPath $TargetConfigPath) {
    Copy-Item -LiteralPath $TargetConfigPath -Destination "$TargetConfigPath.backup-$Timestamp"
    $TargetConfig = Get-Content -LiteralPath $TargetConfigPath -Raw | ConvertFrom-Json
} else {
    $TargetConfig = [pscustomobject]@{}
}
if (-not $TargetConfig.PSObject.Properties["mcpServers"]) {
    $TargetConfig | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([pscustomobject]@{})
}
if ($TargetConfig.mcpServers.PSObject.Properties[$ServerName]) {
    $TargetConfig.mcpServers.$ServerName = $RemoteServer
} else {
    $TargetConfig.mcpServers | Add-Member -NotePropertyName $ServerName -NotePropertyValue $RemoteServer
}
$TargetConfig | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $TargetConfigPath -Encoding UTF8

$OldSkill = Join-Path $ClaudeHome "skills\aem-guides-test-scenario-generator.backup"
$SkillBackupRoot = Join-Path $ClaudeHome "skill-backups"
if (Test-Path -LiteralPath $OldSkill -PathType Container) {
    New-Item -ItemType Directory -Force -Path $SkillBackupRoot | Out-Null
    $OldSkillTarget = Join-Path $SkillBackupRoot "aem-guides-test-scenario-generator-$Timestamp"
    Move-Item -LiteralPath $OldSkill -Destination $OldSkillTarget
}

Write-Host "Removed conflicting global Dataset Studio MCP; backup: $UserBackup"
Write-Host "Configured full HTTP Dataset Studio MCP in: $TargetConfigPath"
Write-Host "Moved the old skill outside the active skills directory."
Write-Host "Fully exit Claude Desktop, end remaining claude.exe processes, reopen $TargetProjectPath, and start a new task."
