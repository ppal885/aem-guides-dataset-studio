# AEM Guides Minimal MCP Client for Claude Code on macOS/Linux

Lightweight macOS/Linux client for team members who use Claude Code with the central VM-hosted AEM Guides RAG backend.

This package does **not** contain the full dataset-studio repo, RAG corpus, ChromaDB, JSON chunks, or backend code. Live RAG stays on the VM.

## What This Package Installs

- MCP tool `ask_dita_expert` for VM-backed RAG knowledge.
- MCP tool `upload_dataset_to_aem` for direct local-machine upload to AEM Assets.
- Claude skill `test-plan-generation` for plain-English QA test-plan writing guidance.
- No slash commands are installed.

No other MCP tools or slash commands are intentionally exposed.

## Requirements

- macOS or Linux.
- Python 3.10+.
- Node.js 18+ with npm on PATH.
- Claude Code installed.
- VPN/network access to the VM RAG backend.
- VM backend URL, normally `http://10.42.46.78:4502`.

## Install

```bash
unzip -o aem-guides-mcp-client-unix.zip
cd aem-guides-mcp-client
chmod +x install.sh smoke_test.sh install_claude_assets.sh doctor_claude.sh
./install.sh http://10.42.46.78:4502 dev-bypass
./install_claude_assets.sh
```

This installs Python dependencies, installs the local AEM upload npm dependency, copies the test-plan skill, and runs smoke checks.

## Register MCP in Claude Code

```bash
claude mcp add-json aem-guides-dataset-studio "$(cat claude-mcp-server.json)"
claude mcp list
```

Fallback:

```bash
cd /path/to/aem-guides-mcp-client
claude
```

The package writes a project-local `.mcp.json`, so running Claude Code from this folder can load the MCP server even without editing global config.

## Local AEM Upload Config

Every teammate keeps their own private config on their laptop:

```bash
cd ~/aem-guides-mcp-client
cp config/aem-upload.properties.example config/aem-upload.properties
chmod 600 config/aem-upload.properties
${EDITOR:-vi} config/aem-upload.properties
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

Credential precedence is: explicit Claude tool args > local `config/aem-upload.properties`.

## Use Local Upload

The source path is on the user's own Mac/Linux machine. Nothing needs to be copied to the VM.

Ask Claude:

```text
Use MCP tool upload_dataset_to_aem with source_path=/Users/<your-user>/Downloads/aem-seed-data and target_path=/content/dam/guides-qa/GUIDES-12345.
```

Rules:

- `source_path` must exist on the local machine where Claude Code is running.
- `source_path` can be a local file or folder; absolute paths are safest.
- `target_path` must start with `/content/dam/`.
- If the folder contains `content/dam/<folder>`, the uploader automatically uploads from that nested DAM folder root.

## Verify

```bash
./doctor_claude.sh
claude mcp list
```

Expected:

- `aem-guides-dataset-studio` appears in `claude mcp list`.
- `doctor_claude.sh` shows `exact_minimal_surface: True`.
- `doctor_claude.sh` shows `ask_dita_expert: True`.
- `doctor_claude.sh` shows `upload_dataset_to_aem: True`.
- `doctor_claude.sh` shows `removed_tools_exposed: []`.
- `doctor_claude.sh` shows Node.js and `@adobe/aem-upload` as available.

Restart Claude Code after setup.

## Test Plan Skill

The package installs the Claude skill `test-plan-generation`, but there is no `/aem-guides-test-plan` command and no test-plan MCP tool.

Ask Claude naturally:

```text
Use $test-plan-generation to create a test plan for GUIDES-12345. Jira details are: ...
```

The skill can use `ask_dita_expert` for RAG-backed product behavior facts. Jira/GitHub evidence must come from user-provided context or separately connected Jira/GitHub MCPs.

## Important Rules

- Do not clone the full dataset-studio repo on teammate laptops.
- Do not copy RAG JSON, ChromaDB, or DITA corpus to teammate laptops.
- Do not copy generated upload folders to the VM.
- Keep upload source files/folders on the local machine and use `upload_dataset_to_aem`.
- Reindex and maintain RAG only on the VM.
- If RAG is stale, fix the VM backend/index; all clients then get updated evidence.
- Old AEM slash commands and deprecated AEM skills are removed during `install_claude_assets.sh`.

## Troubleshooting

### Cannot reach VM RAG backend

Check VPN, URL, firewall, and VM service:

```bash
curl http://10.42.46.78:4502/mcp/health
```

On the VM:

```bash
systemctl status aem-backend
curl http://localhost:8001/health
```

### Local upload dependency missing

```bash
node --version
npm --version
npm install --omit=dev
./doctor_claude.sh
```

### Claude does not show MCP tools

```bash
claude mcp list
claude mcp add-json aem-guides-dataset-studio "$(cat claude-mcp-server.json)"
./doctor_claude.sh
```

Existing Claude Code sessions need a full restart to reload MCP registration.

### Python venv fails on Ubuntu

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip
./install.sh http://10.42.46.78:4502 dev-bypass
```
