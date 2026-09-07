# AEM Guides UAC MCP setup

This repo ships a local stdio MCP server (`mcp_server.py`) so Claude Code, Claude
Desktop, Cursor, and other MCP-enabled clients can use the UAC, DITA, and Jira
tooling directly — no browser UI is required for
most tools (a few, like Jira search, still call out to live services and need
the same credentials the backend uses).

## Install

```bash
cd backend
.venv/Scripts/python.exe -m pip install -r ../requirements-mcp.txt
```

Use the **same virtualenv** the backend already runs on (`backend/.venv`), not a
separate one — the MCP server imports directly from `backend/app/services/*`,
so it needs the exact same dependencies (LLM SDKs, ChromaDB, lxml, etc.) already
installed there.

## Configure your MCP client

Copy `.mcp.json.example` to `.mcp.json` and fill in your actual paths:

```json
{
  "mcpServers": {
    "aem-dataset-studio": {
      "command": "C:\\path\\to\\aem-guides-dataset-studio\\backend\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\aem-guides-dataset-studio\\mcp_server.py"]
    }
  }
}
```

- **Claude Code**: put `.mcp.json` at the repo root (already the convention this
  project uses for other MCP servers) — it's picked up automatically per-project.
- **Claude Desktop**: add the same `mcpServers` entry to Claude Desktop's own
  `claude_desktop_config.json` instead (Settings → Developer → Edit Config).
- **Cursor**: same shape, under Cursor's MCP settings.

The server reads `.env` at both the project root and `backend/.env` on startup
(same config the backend uses — LLM keys, Jira credentials, tenant settings),
so as long as your local backend already works, the MCP server will too.

## What's available

**DITA Expert (grounded Q&A, construct lookup, bug search)** — new, added
alongside today's chatbot Processing-Behavior work:

| Tool | What it does |
|---|---|
| `ask_dita_expert(question, tenant_id="kone")` | Full grounded Q&A — same pipeline as the DITA Expert web chat. For element/attribute questions, automatically includes a "Processing behavior" section (preprocessing-resolved vs. cosmetic, content-filtering, Native PDF vs. DITA-OT parity). |
| `lookup_dita_construct(tag)` | Raw grounded facts for a DITA element/attribute (description, parents/children, attributes, common mistakes) from the spec registry — no LLM call, fast, for grounding a test-scenario document or your own answer. Honestly reports when a tag isn't recognized rather than inventing facts. |
| `find_dita_ot_and_jira_issues(tag, tenant_id="kone")` | Searches DITA-OT GitHub issues + AEM Guides Jira for a specific construct. Reports real, cited issues or an explicit "none found" — never fabricates a plausible-sounding bug. |

**Jira tools** — `get_jira_issue`, `get_jira_issue_with_comments`,
`search_jira_issues`, `find_similar_jira_issues`, `index_jira_issues`,
`run_jira_dita_analysis_pipeline`, `generate_dita_from_jira`,
`batch_generate_dita_from_jira`, `mark_issue_generated`,
`check_issue_generated`, `list_generation_history`.

**RAG / knowledge base** — `check_rag_status`, `crawl_experience_league`,
`index_dita_spec_pdfs`, `query_experience_league`, `query_dita_spec`,
`query_dita_graph`, `query_combined_context`.

**DITA file generation & validation** — `generate_dita`, `save_dita_file`,
`save_dita_files`, `enrich_dita_output`, `list_dita_files`, `read_dita_file`,
`validate_dita_file`, `validate_and_fix_dita`, `score_dita_quality`,
`bundle_dita_package`.

**DITA example corpus** — `clone_dita_example_repos`,
`index_dita_example_repos`, `query_dita_examples`, `list_dita_example_repos`.

**Images** — `get_jira_issue_images`, `save_dita_with_images`,
`list_issue_images`, `generate_fig_elements`.

**Prompt templates** — `list_prompt_templates`, `read_prompt_template`,
`save_prompt_template`.

Run any client's tool-listing command (or just ask Claude "what MCP tools do
you have from aem-dataset-studio?") to see the full live list — this table may
drift as tools are added.


## Generate a UAC

Ask the client to use the installed `test-plan-generation` skill for the Jira key. The skill may call the MCP `guides_test_plan_generator(jira_key, tenant_id="kone", evidence_k=8)` tool for its evidence packet, then applies the canonical reasoning and quality gates. No browser UI is required.

The MCP tool is read-only: it builds a Jira + Experience League RAG + DITA/spec + QA Studio preview evidence packet and does not crawl, reindex, delete, or mutate production vector indexes.

## Notes

- **Read-mostly, opt-in writes**: most tools are read/query only. File-writing
  tools (`save_dita_file(s)`, `bundle_dita_package`, `mark_issue_generated`,
  `save_prompt_template`) write under `backend/storage/` or
  `backend/app/templates/prompts/` — review before running them against shared
  data.
- **`ask_dita_expert` and `find_dita_ot_and_jira_issues` call live services**
  (the configured LLM provider, and — for Jira — your tenant's Jira instance),
  so they need the same credentials the backend already uses in `.env`. If
  those aren't configured, the tool returns an explicit error rather than a
  fabricated answer.
- **`lookup_dita_construct` has no LLM/network dependency** — it only reads
  this project's local DITA spec registry, so it works even without any
  external credentials configured.
