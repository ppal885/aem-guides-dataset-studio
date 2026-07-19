# Claude Code Skills

These skills extend Claude Code's behavior for DITA authoring, dataset generation, and AEM Guides publishing questions.

## Installation

Claude only auto-discovers skills from a Claude skills directory. A skill can live anywhere for
source control, but team members must copy or install it into one of these locations before Claude
can reliably use it:

| Scope | Windows | macOS / Linux |
|---|---|---|
| User-wide skill | `%USERPROFILE%\.claude\skills\<skill-name>\SKILL.md` | `~/.claude/skills/<skill-name>/SKILL.md` |
| User-wide slash command | `%USERPROFILE%\.claude\commands\<command>.md` | `~/.claude/commands/<command>.md` |
| Repo source copy | `claude-skills\<skill-name>\SKILL.md` | `claude-skills/<skill-name>/SKILL.md` |

Do not install skills into Claude plugin cache paths; those paths are implementation details and can
change. Keep this repository's `claude-skills/` directory as the source copy, then install to the
user-wide Claude directory.

Install only the AEM Guides test-plan workflow:

**Windows PowerShell:**
```powershell
python scripts\install_claude_test_plan_generator.py
```

**macOS / Linux:**
```bash
python3 scripts/install_claude_test_plan_generator.py
```

Then restart Claude Code and run:

```text
/guides-test-plan-generator GUIDES-12345
```

If a user keeps the skill in a custom local folder, install with explicit destinations:

```bash
python3 scripts/install_claude_test_plan_generator.py \
  --dest-skill-dir "$HOME/.claude/skills" \
  --dest-command-dir "$HOME/.claude/commands"
```

The slash command still requires the MCP gateway/tool `guides_test_plan_generator` to be registered
in that user's Claude Code environment.

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
| `aem-guides-test-scenario-generator` | `/guides-test-plan-generator GUIDES-12345`, AEM Guides test plans, bug discovery, regression prevention | `guides_test_plan_generator` MCP + RAG/Jira/code evidence |

## Chat UI integration

The element, OT, and authoring guidance is also baked into the backend system prompt via:
- `backend/app/templates/prompts/chat_dita_element_guidance.txt`
- `backend/app/templates/prompts/chat_dita_ot_guidance.txt`
- `backend/app/templates/prompts/chat_dita_authoring_guidance.txt`

These are auto-selected based on the user's question type in `chat_service.py::_select_skill_guidance`.
