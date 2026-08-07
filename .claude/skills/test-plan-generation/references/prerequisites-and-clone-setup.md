# Prerequisites & Clone Setup (OS-aware)

Run this check BEFORE gathering evidence, and show the user what is configured vs
missing. A QA machine frequently does NOT have the backend/product clones — that is
expected. GitHub MCP remote inspection substitutes for any missing clone.

## 1. MCP prerequisites — surface these to the user

| MCP / tool | Role | Required? | If missing |
|---|---|---|---|
| Jira MCP | Issue facts, comments, attachments, historical JQL | **Required** | Use pasted issue text; state the source |
| GitHub MCP | Remote code/PR/commit/blame inspection; **substitute for any missing local clone** | **Required** | No clone + no GitHub MCP = code evidence cannot be gathered (blocker for impl/post-fix; labelled gap pre-dev) |
| `search_jira_history` (Dataset Studio) | Cross-customer `jira_qa` past-similar mining | Recommended | Fall back to live Jira JQL; mark the gap |
| `ask_dita_expert` (Dataset Studio) | Product-doc / DITA-spec behaviour RAG | Recommended | Ground behaviour from Jira + code; mark the RAG gap |
| Figma MCP | UI/design-flow evidence | Optional | Only a gap if the ticket is design-dependent |

Report example to the user: "Prerequisites: Jira MCP ✅, GitHub MCP ✅, RAG (ask_dita_expert/search_jira_history) ✅, Figma ⚠️ not configured (only needed for UI-flow tickets). You're set up to run."

Do not silently proceed as if a missing prerequisite were present.

## 2. Detect OS, then check the platform-correct clone paths

Detect Windows vs macOS vs Linux first — never assume one OS's paths on another.

**Windows** candidate roots (drive-letter):
- Backend/product: `C:\starling`, `C:\xmleditor\xmleditor`, `C:\ui_framework\new_editor`
- Automation: `C:\ui_framework\guides-ui-tests`, `C:\UI TEST\guides-ui-tests`, `C:\api automation\dxml-it-tests`, `C:\editor-e2e\guides-editor-e2e`

**macOS / Linux** candidate roots (`$HOME`-relative — the drive-letter paths above will NOT exist):
- Backend/product: `~/starling`, `~/xmleditor`, `~/new_editor`, `~/src/starling`, `~/src/xmleditor`, `~/workspace/*`
- Automation: `~/guides-ui-tests`, `~/dxml-it-tests`, `~/guides-editor-e2e`
- Also honor `$GQS_GUIDES_REPO_ROOT` and any user-provided workspace root.

Detection command per OS:
- Windows (Git Bash/PowerShell): test each candidate with `test -d <path>` / `Test-Path <path>`.
- macOS/Linux: `for d in ~/starling ~/xmleditor ~/src/* ; do [ -d "$d/.git" ] && echo "$d"; done`.

## 3. If a needed clone is ABSENT — two supported paths

**Path A (default) — GitHub MCP remote inspection (no clone needed):**
Use GitHub MCP against the repo on the corporate GitHub, e.g. `search_code repo:<owner>/<name> "<symbol/label>"`, `get_file_contents`, `list_commits`, and the PR/branch APIs. This gives exact current implementation, file paths, and blame without any local clone. Cite the repo + inspected ref. Known repos: `AdobeStarling/*` (backend), `BlueJay/jui-app` (XML Editor / Native PDF editor UI — the real home of editor UI that `xmleditor` only thin-wraps), `AdobeStarling/guides-ui-tests`.

**Path B (only if the user wants a local copy) — offer the OS-correct clone command:**
- Windows (PowerShell/Git Bash):
  - `git clone https://git.corp.adobe.com/AdobeStarling/starling.git C:/starling`
  - `git clone https://git.corp.adobe.com/BlueJay/jui-app.git C:/jui-app`
- macOS / Linux:
  - `git clone https://git.corp.adobe.com/AdobeStarling/starling.git ~/starling`
  - `git clone https://git.corp.adobe.com/BlueJay/jui-app.git ~/jui-app`
Do NOT clone large product repos unprompted; only run/suggest on the user's request, and note these need corporate GitHub access.

## 4. Record the choice
In `Scope From Git`, state for each area whether it was inspected via a local clone (with its sync/SHA state) or via GitHub MCP (with the repo + ref). Never write "clone unavailable / no backend evidence" without having tried GitHub MCP for that repo first.
