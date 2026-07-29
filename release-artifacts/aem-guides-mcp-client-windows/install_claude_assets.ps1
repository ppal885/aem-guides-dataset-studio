[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$ClientDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ClientDir

$ClaudeDir = Join-Path $HOME ".claude"
$CommandsDir = Join-Path $ClaudeDir "commands"
$SkillsDir = Join-Path $ClaudeDir "skills"

New-Item -ItemType Directory -Force -Path $CommandsDir | Out-Null
New-Item -ItemType Directory -Force -Path $SkillsDir | Out-Null

$DeprecatedCommands = @(
    "ask-dita-expert.md",
    "generate-dita-ot-output.md",
    "guides-test-plan-generator.md",
    "aem-ask-dita-expert.md",
    "aem-data-upload-workflow.md",
    "aem-generate-dita.md",
    "aem-generate-dita-ot-output.md",
    "aem-guides-test-plan.md",
    "aem-guides-test-scenario-generator.md",
    "aem-rag-status.md",
    "aem-upload-generated-to-aem.md"
)
foreach ($command in $DeprecatedCommands) {
    Remove-Item -LiteralPath (Join-Path $CommandsDir $command) -Force -ErrorAction SilentlyContinue
}

$SkillDestination = Join-Path $SkillsDir "test-plan-generation"
$DeprecatedSkills = @(
    "aem-data-upload-workflow",
    "aem-guides-dita-qa-pipeline",
    "aem-guides-test-scenario-generator"
)
Remove-Item -LiteralPath $SkillDestination -Recurse -Force -ErrorAction SilentlyContinue
foreach ($skill in $DeprecatedSkills) {
    Remove-Item -LiteralPath (Join-Path $SkillsDir $skill) -Recurse -Force -ErrorAction SilentlyContinue
}

Copy-Item -LiteralPath (Join-Path $ClientDir ".claude\skills\test-plan-generation") -Destination $SkillsDir -Recurse -Force

Write-Host "Installed Claude skill to:    $SkillDestination"
Write-Host "Removed old AEM slash commands and deprecated AEM skills."
Write-Host ""
Write-Host "Recommended MCP registration:"
Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File `"$ClientDir\register_claude.ps1`""
Write-Host ""
Write-Host "No AEM upload slash command is installed. Use MCP tool: upload_dataset_to_aem"
