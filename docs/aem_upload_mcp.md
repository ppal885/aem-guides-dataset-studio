# AEM Upload MCP Tool

Use `upload_dataset_to_aem` from Claude/Cursor/Codex MCP to upload a generated
DITA dataset directory or ZIP into AEM Assets.

## Environment

Preferred auth is environment-based so credentials are not pasted into chat:

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

## Claude MCP Usage

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

`source_path` must be inside the project, `output`, `incoming_archives`, or
`tmp`. ZIP files are extracted under `tmp/aem_upload_extract` before upload.

`target_path` must start with `/content/dam/`.
