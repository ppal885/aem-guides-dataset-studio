# Building Better Prompts for AI Chat (Jira + DITA)

Use the **AI Chat** page for Jira paste, issue summary, and dataset generation. One page handles everything.

**End-user guide:** See [CHAT_USER_GUIDE.md](./CHAT_USER_GUIDE.md) for RAG/Settings, refinement behavior, and reload behavior for bundle links.

## Quick Tips

| Principle | Do | Don't |
|-----------|-----|-------|
| **Be specific** | "Create a task topic about installing the HP LaserJet printer with 5 steps" | "Make DITA" |
| **Include context** | Paste full Jira text (Summary + Description + Steps) | Paste only a one-line summary |
| **State intent** | "Generate DITA from this Jira issue" | Vague "help me with this" |
| **Refine iteratively** | "Add prerequisite section" or "Make steps more detailed" | Expect perfect output on first try |

## Jira Paste Flow

1. **Paste** the full Jira content (Issue Summary, Description, Steps to Reproduce, etc.).
2. The AI detects Jira-style text and **calls generate_dita immediately**—no extra step.
3. You get a download link for the DITA bundle.
4. **Refine** in follow-up messages: "Add a concept topic for the glossary terms" or "Include expected result in each step."

**Refinement context** for `generate_dita` is stored **per chat session in the database** (`chat_sessions.last_generation_json`) so it survives **backend restarts**. Tool outputs such as bundle links are stored on assistant messages (`tool_results`) so they survive **page reload**.

## Natural Language Examples

- "Create a task topic about configuring SSO in AEM"
- "Generate a concept topic explaining DITA maps"
- "Make a task with 8 steps for upgrading the content model"
- "From this Jira issue, create DITA and add a troubleshooting section"

## Prompt as Interface

Prompts are treated as structured specs, not just raw text. See `app/core/prompt_interface.py`:

- **PromptSpec**: id, version, sections (dict), section_order
- **PromptBuilder**: composes spec + dynamic blocks (user_context, rag_context)
- **load_prompt_spec**: loads from JSON (preferred) or .txt fallback

Chat uses `chat_system.json` with sections: role_and_tone, capabilities, **dita_writer** (glossary, reuse, maps, accessibility, RAG vs general DITA), tool_rules, jira_rule, grounding, **accuracy**, examples, formatting.

## Prompt Structure (for customization)

The system prompt is loaded from `app/templates/prompts/chat_system.json` (or `chat_system.txt` fallback) and uses:

1. **Role + tone** – Friendly, conversational, adaptive
2. **Capabilities** – DITA, recipes, AEM Guides, Claude Code
3. **Tool rules** – When to call `generate_dita` vs `create_job`
4. **Jira rule** – Call `generate_dita` immediately when Jira content is pasted
5. **Grounding** – Use RAG for AEM Guides product facts; for generic DITA element semantics, standard DITA knowledge is allowed and irrelevant RAG hits should be ignored (see `chat_system.json` + `chat_human_precision.txt`)
6. **Accuracy** – Prefer narrow, correct answers; don’t invent URLs/versions; separate facts from suggestions (`chat_system.json` section `accuracy`)
7. **Examples** – Few-shot examples for Jira paste and natural language

**Chat temperature:** lower values reduce randomness (`CHAT_TEMPERATURE` in `.env`, default ~0.15 in `llm_service.py`).

## RAG Setup

To populate RAG sources for better DITA accuracy:

1. **AEM Guides docs**: `POST /api/v1/ai/crawl-aem-guides` (optional body: `{ "urls": ["https://..."] }`)
2. **DITA spec PDFs**: `POST /api/v1/ai/index-dita-pdf` — indexes DITA 1.2 and 1.3 Part 1 Base by default. Optional body: `{ "urls": ["https://..."] }` for custom URLs.
3. **GitHub DITA (e.g. Oxygen userguide)**: `POST /api/v1/ai/index-github-dita-examples` — downloads a repo subtree via GitHub’s zip API (not the HTML crawl). Body example: `{ "tenant_id": "default", "index_all": true }` indexes the configured primary tree plus defaults such as `DITA/dev_guide`, and merges chunks into the same **`aem_guides`** Chroma collection used by chat when `GITHUB_DITA_ALSO_MERGE_TO_AEM_RAG=true` (default). Single subtree: `{ "source_url": "https://github.com/oxygenxml/userguide/tree/master/DITA/dev_guide" }` (blob URLs are accepted and normalized).

**Crawl URL list:** `config/aem_guides_crawl_urls.json` (or the same filename under storage, which overrides the bundled file). It includes Experience League paths plus **full URLs** for third-party docs. The repo includes [Oxygen XML DITA Style Guide](https://www.oxygenxml.com/dita/styleguide/) topics (e.g. choice tables, `keycol`/`refcols`, row headers, nested tables, `cmdname`/`apiname`, parameters/variables, UI messages) so chat RAG can retrieve authoring best practices—not only Adobe AEM Guides pages.

Check status with `GET /api/v1/ai/rag-status`.

To improve prompts:

- **Edit the spec** – `app/templates/prompts/chat_system.json` (sections) or `chat_system.txt` (legacy)
- **Add versioned variants** – `chat_system_v2.json` or `chat_system_v2.txt` for A/B testing
- **Tighten tool descriptions** in `chat_tools.py` so the LLM knows when to act
- **Use USER CONTEXT** – Pass `source_page`, `issue_key`, `issue_summary` from the frontend for better responses

## Versioning

Chat prompts are versioned in `app/templates/prompts/versions.json`:

```json
{ "chat_system": "v1", ... }
```

- **Rollback**: Set `"chat_system": "v0"` and add `chat_system_v0.txt`
- **A/B test**: Set `CHAT_PROMPT_VERSION=v2` in `.env` to override versions.json
- **Versioned files**: `chat_system_v1.json` or `chat_system.json`; falls back to `chat_system.txt`

Current versions are exposed at `GET /api/v1/ai/prompt-versions`.

## Context Window

| Env var | Default | Purpose |
|---------|---------|---------|
| `CHAT_CONTEXT_MAX_TOKENS` | 120000 | Total input token budget (Claude 3.5 ~200k; reserves system+RAG, trims messages) |
| `CHAT_CONTEXT_WINDOW_MESSAGES` | 20 | Fallback: max messages when token budget not set |
| `CHAT_USE_TIKTOKEN` | false | When true, use tiktoken (cl100k_base) for accurate token counts; else ~4 chars/token |
| `CHAT_ENABLE_HUMAN_PROMPTS` | false | When true, append **human precision** rules (`chat_human_precision.txt`): shorter, direct answers; no filler (“Best available guidance”), no unsolicited “Good next prompts,” lighter RAG citation noise. Per-message: JSON body `human_prompts: true|false` overrides this when set. |

Truncation: system prompt + RAG context are reserved; conversation messages are trimmed from the oldest until within budget.

### Human precision (less noisy chat)

- **Template**: [`app/templates/prompts/chat_human_precision.txt`](../app/templates/prompts/chat_human_precision.txt) — edit to tighten tone (bullets, anti-disclaimer, no follow-up lists).
- **API**: `POST /api/v1/chat/sessions/{id}/messages` with `{ "content": "...", "human_prompts": true }` (optional). Omit `human_prompts` to use `CHAT_ENABLE_HUMAN_PROMPTS` only.
- **UI**: AI Chat page — **Precise answers** toggle (stored in `localStorage` as `chatHumanPrompts`, default on).

## Pipeline and LLM DITA Environment Variables

### Confidence and Pipeline

| Env var | Default | Purpose |
|---------|---------|---------|
| `AI_MIN_CONFIDENCE_THRESHOLD` | 0.0 | When > 0, log warning if avg (mechanism + pattern) confidence is below this. Set 0.35–0.4 to trigger LLM DITA fallback for low-confidence keyref routing. |
| `GENERATE_FROM_TEXT_USE_PIPELINE` | false | When true, paste/generate-from-text uses the deterministic recipe pipeline (mechanism → pattern → route) instead of always using `llm_generated_dita`. |

### LLM DITA Generator (fallback for novel constructs)

| Env var | Default | Purpose |
|---------|---------|---------|
| `LLM_DITA_MAX_TOKENS` | 4000 | Max tokens for LLM DITA generation when no recipe exists (topicset, navref, foreign, bookmap, etc.). |
| `LLM_DITA_MAX_RETRIES` | 1 | Number of retries on transient LLM failure before raising. |
| `LLM_DITA_RAG_DITA_K` | 4 | Number of DITA spec chunks to retrieve for RAG context. |
| `LLM_DITA_RAG_DITA_GRAPH_ENABLED` | true | When true, inject DITA structure (nesting and attributes) into the LLM prompt to reduce hallucination. |
| `LLM_DITA_RAG_AEM_DOCS_ENABLED` | true | When true, retrieve AEM Guides documentation when evidence mentions product-specific terms (keyref, conref, etc.). |
| `LLM_DITA_CONTENT_FIDELITY_ENABLED` | false | When true, run optional check: warn if too few evidence terms appear in generated DITA. |
| `LLM_DITA_CONTENT_FIDELITY_MIN_RATIO` | 0.2 | When fidelity check enabled: minimum ratio of evidence terms (5+ chars) that must appear in output. Below this triggers a warning log. |

## Where to Edit

| File | What to change |
|------|----------------|
| `app/templates/prompts/chat_system.json` | Structured prompt spec (sections) |
| `app/templates/prompts/chat_human_precision.txt` | Extra rules when human precision is on (env or request) |
| `app/templates/prompts/chat_system.txt` | Legacy fallback (single block) |
| `app/core/prompt_interface.py` | PromptSpec, PromptBuilder, load_prompt_spec |
| `app/templates/prompts/versions.json` | Prompt version (e.g. `chat_system`: `v1`) |
| `app/services/chat_service.py` | `_build_context_block`, `_build_chat_system_prompt` |
| `app/services/chat_tools.py` | `get_tool_definitions()` – tool names, descriptions, parameters |
| Frontend `ChatPage` | `context` and `humanPrompts` passed to `sendMessage` |
