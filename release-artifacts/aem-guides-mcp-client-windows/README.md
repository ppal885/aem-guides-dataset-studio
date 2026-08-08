# AEM Guides Minimal MCP Client for Claude Code on Windows

Lightweight Windows client for team members who use Claude Code with the central VM-hosted AEM Guides RAG backend.

This package does **not** contain the full dataset-studio repo, RAG corpus, ChromaDB, JSON chunks, or backend code. Live RAG stays on the VM.

## What This Package Installs

- MCP tool `ask_dita_expert` for VM-backed RAG knowledge.
- MCP tool `search_jira_history` for indexed same-customer and cross-customer Jira learning.
- MCP tool `query_test_evidence_graph` for audited same-mechanism evidence connections with leaf citations.
- MCP tool `check_rag_status` for graph-aware corpus readiness through Nginx `/mcp`.
- MCP tool `upload_dataset_to_aem` for direct local-machine upload to AEM Assets.
- Claude skill `test-plan-generation` for plain-English QA test-plan writing guidance.
- No slash commands are installed.

No other MCP tools or slash commands are intentionally exposed.

## Requirements

- Windows 10/11.
- PowerShell 5+ or PowerShell 7+.
- Python 3.10+ on PATH, or Python Launcher (`py`) installed.
- Node.js 18+ with npm on PATH.
- Claude Code installed.
- VPN/network access to the VM RAG backend.
- VM backend URL, normally `http://10.42.46.78:4502`.

## Clean Install

The zip contains one top-level folder: `aem-guides-mcp-client`.

```powershell
cd C:\Users\<your-user>
Remove-Item .\aem-guides-mcp-client -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive .\aem-guides-mcp-client-windows.zip -DestinationPath . -Force
cd .\aem-guides-mcp-client
.\setup.cmd http://10.42.46.78:4502 dev-bypass
```

This installs Python dependencies, installs the local AEM upload npm dependency, copies the test-plan skill, runs smoke checks, and registers the MCP server in Claude Code.

## Local AEM Upload Config

Every teammate keeps their own private config on their laptop:

```powershell
cd C:\Users\<your-user>\aem-guides-mcp-client
Copy-Item .\config\aem-upload.properties.example .\config\aem-upload.properties
notepad .\config\aem-upload.properties
```

Fill basic auth:

```properties
aem.base.url=http://<aem-author-host>:4502
aem.username=<your-aem-username>
aem.password=<your-aem-password>
```

Or token auth:

```properties
aem.base.url=http://<aem-author-host>:4502
aem.access.token=<your-access-token>
```

Credential precedence is: explicit Claude tool args > local `config\aem-upload.properties`.

## Use Local Upload

The source path is on the user's own Windows machine. Nothing needs to be copied to the VM.

Ask Claude:

```text
Use MCP tool upload_dataset_to_aem with source_path=C:\Users\<your-user>\Downloads\aem-seed-data and target_path=/content/dam/guides-qa/GUIDES-12345.
```

Rules:

- `source_path` must exist on the local laptop where Claude Code is running.
- `source_path` can be a local file or folder; absolute paths are safest.
- `target_path` must start with `/content/dam/`.
- If the folder contains `content\dam\<folder>`, the uploader automatically uploads from that nested DAM folder root.

## Verify

```powershell
.\doctor_claude.cmd
claude mcp list
```

Expected:

- `aem-guides-dataset-studio` appears in `claude mcp list`.
- `doctor_claude.cmd` shows `exact_minimal_surface: True`.
- `doctor_claude.cmd` shows `ask_dita_expert: True`.
- `doctor_claude.cmd` shows `search_jira_history`, `query_test_evidence_graph`, and `check_rag_status` in the exact local surface.
- `doctor_claude.cmd` shows `upload_dataset_to_aem: True`.
- `doctor_claude.cmd` shows `removed_tools_exposed: []`.
- `doctor_claude.cmd` shows Node.js and `@adobe/aem-upload` as available.

Restart Claude Code after setup.

## Test Plan Skill

The package installs the Claude skill `test-plan-generation`, but there is no `/aem-guides-test-plan` command and no test-plan MCP tool.

Ask Claude naturally:

```text
Use $test-plan-generation to create a test plan for GUIDES-12345. Jira details are: ...
```

The skill uses `ask_dita_expert` for product behavior, `search_jira_history` for indexed historical tickets, and `query_test_evidence_graph` only after those direct calls. Graph influence defaults to shadow, so graph output is recorded but cannot alter the test plan unless the deployment explicitly enables augment. Mutable Jira facts and GitHub evidence still require live Jira/GitHub connectors or supplied evidence.

## Important Rules

- Do not clone the full dataset-studio repo on teammate laptops.
- Do not copy RAG JSON, ChromaDB, or DITA corpus to teammate laptops.
- Do not copy generated upload folders to the VM.
- Keep upload source files/folders on the local machine and use `upload_dataset_to_aem`.
- Reindex and maintain RAG only on the VM.
- If RAG is stale, fix the VM backend/index; all clients then get updated evidence.
- Old AEM slash commands and deprecated AEM skills are removed during `install_claude_assets.ps1`.

## Troubleshooting

### Expand-Archive says files already exist

Use clean reinstall with `-Force`:

```powershell
cd C:\Users\<your-user>
Remove-Item .\aem-guides-mcp-client -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive .\aem-guides-mcp-client-windows.zip -DestinationPath . -Force
```

### Cannot reach VM RAG backend

```powershell
Invoke-RestMethod http://10.42.46.78:4502/mcp/health
$payload = @{jsonrpc='2.0'; id=1; method='tools/call'; params=@{name='check_rag_status'; arguments=@{tenant_id='kone'}}} | ConvertTo-Json -Depth 6
Invoke-RestMethod -Method Post -Uri http://10.42.46.78:4502/mcp -ContentType application/json -Body $payload
```

### Local upload dependency missing

```powershell
node --version
npm --version
npm install --omit=dev
.\doctor_claude.cmd
```

### Claude does not show MCP tools

```powershell
claude mcp list
.\register_claude.cmd
.\doctor_claude.cmd
claude mcp list
```

Existing Claude Code sessions need a full restart to reload MCP registration.
