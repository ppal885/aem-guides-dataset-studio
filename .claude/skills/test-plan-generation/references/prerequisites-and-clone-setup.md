# Prerequisites and Clone Setup

Run evidence preflight before generating a plan and state which sources are available.

## Evidence Sources

- Jira MCP supplies current issue facts, comments, attachments, and mutable status when accessible. Pasted Jira or incident text is a valid degraded fallback and must be labelled.
- `search_jira_history` supplies indexed same-customer and cross-customer historical evidence. A live Jira 403 does not erase indexed history, but freshness and mutable fields remain degraded.
- `ask_dita_expert` supplies product-documentation and DITA-spec evidence.
- GitHub MCP or a synchronized local product clone supplies current implementation/PR evidence. Do not claim a clone is unavailable before trying the configured remote source.
- Figma is required only when a design-dependent claim cannot be established from accepted Jira/UAC or inspected implementation.

## OS-Aware Clone Discovery

- On Windows, check user-provided roots and common locations such as `C:\starling`, `C:\xmleditor`, `C:\ui_framework\new_editor`, `C:\ui_framework\guides-ui-tests`, and `C:\api automation\dxml-it-tests`.
- On macOS/Linux, check user-provided roots, `$GQS_GUIDES_REPO_ROOT`, and common locations under `$HOME`, such as `~/starling`, `~/xmleditor`, `~/new_editor`, `~/guides-ui-tests`, and `~/dxml-it-tests`.
- Never clone a large product repository without the user's request. Prefer GitHub MCP remote inspection when it provides the required exact file/ref evidence.
- For every local clone used, record absolute path, branch, pre/post SHA, upstream/ahead/behind state, dirty state, fetch/pull result, inspected ref, and any retained stash plus restore command.
