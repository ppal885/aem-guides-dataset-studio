# Claude Code Skills

These skills extend Claude Code's behavior for DITA authoring, dataset generation, and AEM Guides publishing questions.

## Installation

Copy skills into your Claude Code skills directory:

**Windows:**
```powershell
$dest = "$env:USERPROFILE\.claude\plugins\cache\claude-plugins-official\skill-creator\unknown\skills"
Get-ChildItem -Directory . | ForEach-Object { Copy-Item $_.FullName $dest -Recurse -Force }
```

**macOS / Linux:**
```bash
dest="$HOME/.claude/plugins/cache/claude-plugins-official/skill-creator/unknown/skills"
for skill in */; do cp -r "$skill" "$dest/"; done
```

## Skills

| Skill | Triggers on | Uses |
|---|---|---|
| `dita-dataset-generator` | "generate a dataset", JIRA key, bulk topics | `create_job` (named recipes) |
| `dita-freeform-authoring` | "write a topic about X", "author DITA for Y", paste prose | `generate_dita` |
| `dita-batch-planner` | "full content set for X", 200+ topics, mixed types | chained `create_job` calls |
| `dita-xml-repair` | "fix this DITA", paste broken XML, validation failed | `review_dita_xml` → `fix_dita_xml` |
| `dita-element-qa` | "what is `<shortdesc>`", "how does `@conref` work" | `lookup_dita_spec` |
| `dita-ot-publishing` | "DITA-OT transforms", "PDF not rendering", "how to publish" | `lookup_aem_guides` |
| `dita-authoring-advisor` | "concept vs task", "how do I reuse content", best practices | `lookup_dita_spec` + `lookup_aem_guides` |

## Chat UI integration

The element, OT, and authoring guidance is also baked into the backend system prompt via:
- `backend/app/templates/prompts/chat_dita_element_guidance.txt`
- `backend/app/templates/prompts/chat_dita_ot_guidance.txt`
- `backend/app/templates/prompts/chat_dita_authoring_guidance.txt`

These are auto-selected based on the user's question type in `chat_service.py::_select_skill_guidance`.
