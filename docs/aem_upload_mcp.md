# AEM Upload MCP Tool

Use `upload_dataset_to_aem` from Claude/Cursor/Codex MCP to upload a generated
DITA dataset directory or ZIP into AEM Assets.

## One-time setup

Install the Node upload dependency from the backend folder:

```bash
cd /path/to/aem-guides-dataset-studio/backend
npm ci
```

If `npm ci` is not available for your environment, use:

```bash
npm install
```

## Config file (recommended)

Fill this simple properties file — no need to edit `.env`:

`config/aem-upload.properties`

```properties
aem.base.url=https://author-p12345-e67890.adobeaemcloud.com
aem.username=your-username
aem.password=your-password

# Optional: use token instead of username/password on AEM Cloud
aem.access.token=
```

Template: `config/aem-upload.properties.example`

After saving, restart the `aem-guides-dataset-studio` MCP server so it reloads the file.

Priority order: tool arguments > `config/aem-upload.properties` > environment variables.

## Environment (optional fallback)

You can still use environment variables if you prefer:

Linux/macOS:

```bash
export AEM_BASE_URL="https://author.example.com"
export AEM_USERNAME="admin"
export AEM_PASSWORD="admin"
```

Windows PowerShell:

```powershell
$env:AEM_BASE_URL = "https://author.example.com"
$env:AEM_USERNAME = "admin"
$env:AEM_PASSWORD = "admin"
```

For AEM Cloud Service, use a bearer token instead:

```powershell
$env:AEM_BASE_URL = "https://author-p12345-e67890.adobeaemcloud.com"
$env:AEM_ACCESS_TOKEN = "TOKEN"
```

Chat-provided credentials are also supported when the user explicitly provides
them for a one-off upload. Claude should pass them as tool arguments and must not
repeat or summarize the password/token in the answer:

```text
upload_dataset_to_aem(
  source_path="output/manual-review/copy-to-chunk.zip",
  target_path="/content/dam/aem-guides-test-data/copy-to-chunk",
  aem_base_url="https://author.example.com",
  username="admin",
  password="<provided-in-chat>"
)
```

The Python service writes credentials to a temporary private config file before
invoking the Node upload helper, so passwords are not exposed as command-line
process arguments. The temporary file is deleted after the upload attempt.

## Claude MCP Usage

Claude users should first generate or select a dataset, then explicitly ask for
upload. Prefer MCP environment variables for credentials. If a user provides
server URL, username, and password in chat, use those values only for that tool
call and do not echo them back.

Upload-only is supported. If the user already has a ZIP or folder and only asks
Claude to upload it, Claude should skip generation and call `upload_dataset_to_aem`
with the explicit `source_path`.

```text
upload_dataset_to_aem(
  source_path="output/aem-guides-1000-topics-broken-links.zip",
  target_path="/content/dam/aem-guides-test-data/broken-links"
)
```

For data generated from MCP, use the convenience wrapper:

```text
upload_mcp_generated_data_to_aem(
  latest=true,
  target_path="/content/dam/aem-guides-test-data/latest"
)
```

Or upload by job/source:

```text
upload_mcp_generated_data_to_aem(
  job_id="GUIDES-12345",
  target_path="/content/dam/aem-guides-test-data/GUIDES-12345"
)
```

Natural-language Claude prompt:

```text
Upload the latest MCP-generated DITA-OT dataset to
/content/dam/aem-guides-test-data/xml-lang-chunk-smoke.
Use the configured AEM environment variables.
```

Upload-only natural-language Claude prompt:

```text
Upload output/manual-review/copy-to-chunk.zip to
/content/dam/aem-guides-test-data/copy-to-chunk.
Do not generate new data.
```

Expected Claude tool call:

```text
upload_mcp_generated_data_to_aem(
  latest=true,
  target_path="/content/dam/aem-guides-test-data/xml-lang-chunk-smoke"
)
```

Expected upload-only tool call:

```text
upload_dataset_to_aem(
  source_path="output/manual-review/copy-to-chunk.zip",
  target_path="/content/dam/aem-guides-test-data/copy-to-chunk"
)
```

`source_path` must be inside the project, `output`, `incoming_archives`, or
`tmp`. ZIP files are extracted under `tmp/aem_upload_extract` before upload.

`target_path` must start with `/content/dam/`.

## What the tool verifies

- Refuses uploads outside `/content/dam/`.
- Refuses missing or non-project-local source paths.
- Extracts ZIPs safely and rejects unsafe ZIP entries.
- Uses `AEM_ACCESS_TOKEN` first when present; otherwise uses
  `AEM_USERNAME`/`AEM_PASSWORD`.
- Accepts one-off `aem_base_url`, `username`, `password`, or `access_token`
  tool arguments when explicitly provided by the user.
- Returns JSON with `success`, `message`, `duration` or `error`; secrets are not
  returned in the MCP response.

## Claude Desktop or Claude Code configuration

Use the in-process MCP server when the user needs generated artifacts, DITA-OT
publishing, RAG, Jira evidence, and AEM upload in one workflow:

```json
{
  "mcpServers": {
    "aem-guides-dataset-studio": {
      "command": "python",
      "args": ["/path/to/aem-guides-dataset-studio/mcp_server.py"],
      "cwd": "/path/to/aem-guides-dataset-studio",
      "env": {
        "AEM_BASE_URL": "https://author.example.com",
        "AEM_USERNAME": "admin",
        "AEM_PASSWORD": "admin"
      }
    }
  }
}
```

For AEM Cloud Service, replace username/password with `AEM_ACCESS_TOKEN`.
