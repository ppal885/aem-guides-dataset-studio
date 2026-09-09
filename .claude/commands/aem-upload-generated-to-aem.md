---
description: Upload VM-generated DITA/DITA-OT artifacts to AEM Assets through Dataset Studio MCP.
argument-hint: latest=true target_path=/content/dam/guides-qa/GUIDES-12345
---

You are running the AEM Guides generated-artifact upload command.

Request:

```text
$ARGUMENTS
```

Rules:

1. Upload only when this command or the user's message explicitly requests an upload.
2. Use `mcp__aem-guides-dataset-studio__upload_mcp_generated_data_to_aem`.
3. Require `target_path` under `/content/dam/` and one artifact selector: `latest=true`, `job_id`, or a VM-side `source_path` returned by `generate_dita_ot_output`.
4. Never treat a laptop path such as `C:\Users\...` as a VM-side source path. Ask the user to generate through `/generate-dita-ot-output` first when no VM artifact exists.
5. Prefer credentials configured securely on the VM. Pass credential overrides only when the user explicitly supplies them, and never echo secrets.
6. After upload, report the selected artifact, DAM target, uploaded/skipped/failed counts, and sanitized errors.

Call shape:

- `latest`, `job_id`, or `source_path`: VM artifact selector from `$ARGUMENTS`
- `target_path`: DAM target path from `$ARGUMENTS`
- optional overrides only if explicitly provided: `aem_base_url`, `username`, `password`, `access_token`, `max_concurrent`, `max_upload_files`
