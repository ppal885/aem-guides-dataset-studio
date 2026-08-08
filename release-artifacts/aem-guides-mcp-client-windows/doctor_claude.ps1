[CmdletBinding()]
param(
    [string]$BackendUrl = "",
    [string]$Token = ""
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$ClientDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ClientDir

function Read-ClientEnv {
    $envPath = Join-Path $ClientDir ".env"
    if (-not (Test-Path -LiteralPath $envPath)) {
        return
    }
    foreach ($raw in Get-Content -LiteralPath $envPath) {
        $line = $raw.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            continue
        }
        $parts = $line.Split("=", 2)
        if (-not [Environment]::GetEnvironmentVariable($parts[0])) {
            [Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
        }
    }
}

function Write-Check {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][bool]$Ok,
        [string]$Detail = ""
    )
    $status = if ($Ok) { "OK" } else { "FAIL" }
    Write-Host ("[{0}] {1}{2}" -f $status, $Name, $(if ($Detail) { " - $Detail" } else { "" }))
}

Read-ClientEnv

if ([string]::IsNullOrWhiteSpace($BackendUrl)) {
    $BackendUrl = $(if ($env:AEM_STUDIO_URL) { $env:AEM_STUDIO_URL } else { "http://10.42.46.78:4502" })
}
if ([string]::IsNullOrWhiteSpace($Token)) {
    $Token = $(if ($env:AEM_STUDIO_TOKEN) { $env:AEM_STUDIO_TOKEN } else { "dev-bypass" })
}
$BackendUrl = $BackendUrl.TrimEnd("/")

$VenvPython = Join-Path $ClientDir ".venv\Scripts\python.exe"
$ServerPath = Join-Path $ClientDir "server.py"
$McpJson = Join-Path $ClientDir ".mcp.json"
$ClaudeServerJson = Join-Path $ClientDir "claude-mcp-server.json"
$AemUploadConfig = Join-Path $ClientDir "config\aem-upload.properties"
$AemUploadNodeModule = Join-Path $ClientDir "node_modules\@adobe\aem-upload"
$ClaudeJson = Join-Path $HOME ".claude.json"

Write-Host "AEM Guides MCP Client Doctor"
Write-Host "Client dir: $ClientDir"
Write-Host "Backend:    $BackendUrl"
Write-Host ""

Write-Check "Python venv" (Test-Path -LiteralPath $VenvPython) $VenvPython
Write-Check "server.py" (Test-Path -LiteralPath $ServerPath) $ServerPath
Write-Check ".mcp.json" (Test-Path -LiteralPath $McpJson) $McpJson
Write-Check "claude-mcp-server.json" (Test-Path -LiteralPath $ClaudeServerJson) $ClaudeServerJson
Write-Check "local AEM upload config" (Test-Path -LiteralPath $AemUploadConfig) "$AemUploadConfig (or pass credentials as tool args)"
$GraphContract = Join-Path $ClientDir ".claude\skills\test-plan-generation\references\evidence-graph-contract.md"
$graphContractReady = $false
if (Test-Path -LiteralPath $GraphContract) {
    $graphContractText = Get-Content -LiteralPath $GraphContract -Raw
    $graphContractReady = $graphContractText.Contains("shadow") -and $graphContractText.Contains("augment") -and $graphContractText.Contains("used_for_plan")
}
Write-Check "Phase B skill contract" $graphContractReady $GraphContract

$nodeOk = $false
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeVersion = (& node -p "process.versions.node").Trim()
    $nodeOk = ($LASTEXITCODE -eq 0 -and [version]$nodeVersion -ge [version]"18.0.0")
    Write-Check "Node.js 18+ for local upload" $nodeOk "version=$nodeVersion"
} else {
    Write-Check "Node.js 18+ for local upload" $false "Install Node.js and rerun setup."
}
Write-Check "npm on PATH" ([bool](Get-Command npm.cmd -ErrorAction SilentlyContinue) -or [bool](Get-Command npm -ErrorAction SilentlyContinue)) "required for setup/install"
Write-Check "@adobe/aem-upload dependency" (Test-Path -LiteralPath $AemUploadNodeModule) $AemUploadNodeModule

$hasGlobalMcp = $false
if (Test-Path -LiteralPath $ClaudeJson) {
    try {
        $global = Get-Content -LiteralPath $ClaudeJson -Raw | ConvertFrom-Json
        $hasGlobalMcp = [bool](
            $global.PSObject.Properties["mcpServers"] -and
            $global.mcpServers.PSObject.Properties["aem-guides-dataset-studio"]
        )
    } catch {
        Write-Warning "Could not parse ${ClaudeJson}: $($_.Exception.Message)"
    }
}
Write-Check "global Claude MCP registration" $hasGlobalMcp $ClaudeJson

try {
    $headers = @{ Authorization = "Bearer $Token" }
    $health = Invoke-RestMethod -Uri "$BackendUrl/mcp/health" -Headers $headers -TimeoutSec 15
    Write-Check "VM /mcp/health" ($health.status -eq "alive") ("status=$($health.status), tools=$($health.tools)")
} catch {
    Write-Check "VM /mcp/health" $false $_.Exception.Message
}

try {
    $headers = @{ Authorization = "Bearer $Token"; "Content-Type" = "application/json" }
    $payload = @{ jsonrpc = "2.0"; id = 1; method = "tools/list"; params = @{} } | ConvertTo-Json -Depth 5
    $toolResponse = Invoke-RestMethod -Method Post -Uri "$BackendUrl/mcp" -Headers $headers -Body $payload -TimeoutSec 30
    $remoteNames = @($toolResponse.result.tools | ForEach-Object { $_.name })
    $requiredRemote = @("ask_dita_expert", "search_jira_history", "query_test_evidence_graph", "check_rag_status")
    $missingRemote = @($requiredRemote | Where-Object { $_ -notin $remoteNames })
    Write-Check "VM evidence MCP tools" ($missingRemote.Count -eq 0) $(if ($missingRemote.Count) { "missing=$($missingRemote -join ',')" } else { "all required tools exposed" })
} catch {
    Write-Check "VM evidence MCP tools" $false $_.Exception.Message
}

if (Get-Command claude -ErrorAction SilentlyContinue) {
    Write-Host ""
    Write-Host "claude mcp list:"
    & claude mcp list
} else {
    Write-Check "Claude Code CLI on PATH" $false "Run register_claude.cmd after Claude Code is available."
}

if (Test-Path -LiteralPath $VenvPython) {
    Write-Host ""
    Write-Host "Local wrapper tool check:"
    $code = @'
import asyncio
import importlib.util
from pathlib import Path

module_path = Path("server.py").resolve()
spec = importlib.util.spec_from_file_location("aem_guides_mcp_client_server", module_path)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

async def main():
    tools = await mod.list_tools()
    names = [tool.name for tool in tools]
    print("tool_count:", len(names))
    expected = [
        "ask_dita_expert",
        "search_jira_history",
        "query_test_evidence_graph",
        "check_rag_status",
        "upload_dataset_to_aem",
    ]
    print("exact_minimal_surface:", names == expected)
    for required in expected:
        print(f"{required}:", required in names)
    removed = [
        "health_check",
        "lookup_aem_guides",
        "lookup_dita_spec",
        "lookup_dita_attribute",
        "search_jira_issues",
        "guides_test_plan_generator",
        "test_plan_pipeline",
        "generate_dita",
        "generate_from_text",
        "generate_dita_ot_output",
        "upload_mcp_generated_data_to_aem",
        "review_dita_xml",
        "fix_dita_xml",
        "list_jobs",
        "get_job_status",
    ]
    leaked = [name for name in removed if name in names]
    print("removed_tools_exposed:", leaked)

asyncio.run(main())
'@
    $code | & $VenvPython -
} else {
    Write-Host ""
    Write-Host "Local wrapper tool check skipped because .venv is missing. Run setup.cmd first."
}
