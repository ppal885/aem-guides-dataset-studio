[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [Alias("Url")]
    [string]$BackendUrl = $env:AEM_STUDIO_URL,

    [Parameter(Position = 1)]
    [string]$Token = $(if ($env:AEM_STUDIO_TOKEN) { $env:AEM_STUDIO_TOKEN } else { "dev-bypass" }),

    [switch]$SkipSmoke
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$ClientDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ClientDir

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Text
    )
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText((Join-Path $ClientDir $Path), $Text, $encoding)
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$Step = "Command"
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

function Resolve-PythonCommand {
    $candidates = @(
        @{ Exe = "py"; Args = @("-3.12") },
        @{ Exe = "py"; Args = @("-3.11") },
        @{ Exe = "py"; Args = @("-3.10") },
        @{ Exe = "py"; Args = @("-3") },
        @{ Exe = "python"; Args = @() },
        @{ Exe = "python3"; Args = @() }
    )

    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) {
            continue
        }
        $versionText = ""
        try {
            $versionText = & $candidate.Exe @($candidate.Args) -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        } catch {
            continue
        }
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($versionText)) {
            continue
        }
        if ([version]$versionText.Trim() -ge [version]"3.10") {
            return $candidate
        }
    }
    throw "Python 3.10+ not found. Install Python and ensure `python` or `py` is available."
}

function Resolve-NpmCommand {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        throw "Node.js 18+ not found. Install Node.js, then rerun setup. Local AEM upload needs Node.js."
    }

    $nodeVersion = (& node -p "process.versions.node").Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($nodeVersion)) {
        throw "Could not read Node.js version. Reinstall Node.js, then rerun setup."
    }
    if ([version]$nodeVersion -lt [version]"18.0.0") {
        throw "Node.js 18+ is required for local AEM upload. Found Node.js $nodeVersion."
    }

    foreach ($candidate in @("npm.cmd", "npm")) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }
    throw "npm not found. Install Node.js with npm, then rerun setup."
}

if ([string]::IsNullOrWhiteSpace($BackendUrl)) {
    Write-Host "Usage:"
    Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -BackendUrl http://<VM-IP-or-host>:4502 [-Token dev-bypass]"
    Write-Host ""
    Write-Host "Example:"
    Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -BackendUrl http://10.42.46.78:4502 -Token dev-bypass"
    exit 2
}

$BackendUrl = $BackendUrl.Trim()
if ($BackendUrl -notmatch "^https?://") {
    $BackendUrl = "http://$BackendUrl"
}
$BackendUrl = $BackendUrl.TrimEnd("/")

$python = Resolve-PythonCommand
Write-Host "Using Python launcher: $($python.Exe) $($python.Args -join ' ')"

Invoke-Checked -FilePath $python.Exe -Arguments (@($python.Args) + @("-m", "venv", ".venv")) -Step "Create virtual environment"

$VenvPython = Join-Path $ClientDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Virtual environment Python not found at $VenvPython"
}

Invoke-Checked -FilePath $VenvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip") -Step "Upgrade pip"
Invoke-Checked -FilePath $VenvPython -Arguments @("-m", "pip", "install", "-r", "requirements.txt") -Step "Install Python requirements"

$NpmPath = Resolve-NpmCommand
Write-Host "Using npm: $NpmPath"
Invoke-Checked -FilePath $NpmPath -Arguments @("install", "--omit=dev") -Step "Install local AEM upload dependency"

$envText = @"
AEM_STUDIO_URL=$BackendUrl
AEM_STUDIO_TOKEN=$Token
AEM_STUDIO_TIMEOUT_SECONDS=300
PYTHONUTF8=1
"@
Write-Utf8NoBom -Path ".env" -Text ($envText.TrimEnd() + "`n")

$serverPath = Join-Path $ClientDir "server.py"
$mcpServer = [ordered]@{
    command = $VenvPython
    args = @($serverPath)
    cwd = $ClientDir
    env = [ordered]@{
        AEM_STUDIO_URL = $BackendUrl
        AEM_STUDIO_TOKEN = $Token
        AEM_STUDIO_TIMEOUT_SECONDS = "300"
        PYTHONUTF8 = "1"
    }
}
$mcpRoot = [ordered]@{
    mcpServers = [ordered]@{
        "aem-guides-dataset-studio" = $mcpServer
    }
}

Write-Utf8NoBom -Path "claude-mcp-server.json" -Text (($mcpServer | ConvertTo-Json -Depth 10) + "`n")
Write-Utf8NoBom -Path ".mcp.json" -Text (($mcpRoot | ConvertTo-Json -Depth 10) + "`n")

Write-Host ""
Write-Host "Installed AEM Guides MCP client."
Write-Host "Client dir: $ClientDir"
Write-Host "VM backend: $BackendUrl"
Write-Host ""
if ($SkipSmoke) {
    Write-Host "Skipping smoke test because -SkipSmoke was provided."
} else {
    Write-Host "Running smoke test..."
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ClientDir "smoke_test.ps1")
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Smoke test passed."
    } else {
        Write-Warning "Smoke test failed. Check VPN, backend URL, token, and VM service."
    }
}

Write-Host ""
Write-Host "Next:"
Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File .\install_claude_assets.ps1"
Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File .\register_claude.ps1 -Scope user"
Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File .\doctor_claude.ps1"
Write-Host ""
Write-Host "If your Claude Code version does not support add-json, run Claude from this folder so .mcp.json is picked up:"
Write-Host "  cd `"$ClientDir`"; claude"
Write-Host ""
Write-Host "For local uploads, create config\aem-upload.properties and pass a local source_path to upload_dataset_to_aem."
