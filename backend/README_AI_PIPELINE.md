# AI Pipeline - Jira RAG + Scenario Generator + Bundle

## Quick Setup

Copy `.env.example` to `.env` and set your credentials:

```bash
cp .env.example .env
# Edit .env with your JIRA_PASSWORD and ANTHROPIC_API_KEY
```

## Environment Variables

### Jira
- `JIRA_URL` or `JIRA_BASE_URL` - Jira instance URL (e.g. https://jira.corp.adobe.com)
- `JIRA_USERNAME` - Username for Basic auth
- `JIRA_PASSWORD` - Password for Basic auth
- `JIRA_PROJECT_KEY` - Default project for JQL (e.g. DXML). Used when JQL is not provided.
- `JIRA_EMAIL` - Email for API auth (alternative to username/password)
- `JIRA_API_TOKEN` - API token for Jira REST API (alternative to username/password)

### Anthropic (LLM)
- `ANTHROPIC_API_KEY` - Required for plan-from-jira and generate-from-jira
- `ANTHROPIC_MODEL` - Default: claude-3-5-sonnet-20241022

### OpenAI (LLM)
- `OPENAI_API_KEY` - Required when `LLM_PROVIDER=openai`
- `OPENAI_MODEL` - Default: gpt-4o-mini

### Agentic Pipeline (configurable thresholds)
- `AI_VALIDATION_RETRIES` - Max validation retries per scenario (default: 2)
- `AI_EXECUTION_RETRIES` - Max execution retries per scenario (default: 1)
- `AI_MAX_SCENARIOS` - Max scenarios per run (default: 5)
- `AI_RECIPE_CANDIDATES_K` - Base recipe candidates per scenario (default: 6)
- `AI_RECIPE_CANDIDATES_K_PER_RETRY` - Extra candidates per validation retry (default: 2)
- `AI_CONSECUTIVE_FAILURES_STOP` - Stop after N consecutive validation failures (default: 2)
- `AI_SIMILAR_ISSUES_K` - Similar issues for evidence pack (default: 5)
- `AI_INDEX_MIN_ISSUES` - Min issues before index fallback (default: 200)
- `AI_INDEX_FALLBACK_LIMIT` - Index limit when fallback triggers (default: 500)
- `AI_LLM_TIMEOUT_SECONDS` - LLM API timeout (default: 120)
- `AI_MIN_CONFIDENCE_THRESHOLD` - When > 0, log warning if mechanism+pattern confidence below threshold. Set to 0.35–0.4 to trigger LLM DITA generator fallback for low-confidence generic keyref routing (default: 0).

### LLM DITA Generator (fallback for novel constructs)
- `LLM_DITA_MAX_TOKENS` - Max tokens for LLM DITA generation when no recipe exists (topicset, navref, foreign, bookmap, etc.). Default: 4000.
- `LLM_DITA_RAG_DITA_K` - Number of DITA spec chunks to retrieve for RAG (default: 4).
- `LLM_DITA_RAG_DITA_GRAPH_ENABLED` - When true (default), inject DITA structure (nesting and attributes) into the LLM prompt to reduce hallucination.
- `LLM_DITA_RAG_AEM_DOCS_ENABLED` - When true (default), retrieve AEM Guides documentation when evidence mentions product-specific terms (keyref, conref, etc.).

### Self-Learning and Feedback
- `AI_AUTO_APPLY_FEEDBACK` - When true (default), `POST /feedback/submit` automatically runs `compute_prompt_overrides_from_feedback()` and saves to `prompt_overrides.json` and `routing_overrides.json`. Set to false to apply overrides manually via `POST /feedback/apply-overrides`.
- `AI_PROMPT_OVERRIDES_ENABLED` - When true (default), planner uses `deprioritize_recipes`, `append_rules`, and `prefer_recipes` from `prompt_overrides.json`.
- Override files are stored under `{storage}/`: `routing_overrides.json` (jira_evidence_keywords, evidence_similarity_pairs) and `prompt_overrides.json` (deprioritize_recipes, append_rules, prefer_recipes). See `backend/docs/SELF_LEARNING_AND_REALIZATION.md` for design details.

### Jira Indexing
- `JIRA_INDEXING_ENABLED` - Default: false
- `JIRA_INDEXING_BOOTSTRAP_ON_STARTUP` - Default: false
- `JIRA_INDEXING_BOOTSTRAP_JQL` - Default: "project = {JIRA_PROJECT_KEY} AND updated >= -90d"
- `JIRA_INDEXING_BOOTSTRAP_LIMIT` - Default: 1000
- `JIRA_INDEXING_SCHEDULE_ENABLED` - Default: true
- `JIRA_INDEXING_SCHEDULE_CRON` - Default: "0 */6 * * *"
- `JIRA_INDEXING_SCHEDULE_JQL` - Default: "project = {JIRA_PROJECT_KEY} AND updated >= -7d"
- `JIRA_INDEXING_SCHEDULE_LIMIT` - Default: 300

### DITA 1.2 PDF RAG Index
- `DITA_PDF_INDEX_ENABLED` - Default: false. When true, weekly index of DITA 1.2 spec PDF.
- `DITA_PDF_INDEX_SCHEDULE` - Default: "0 4 * * 0" (cron: weekly Sunday 4am)
- `DITA_PDF_URL` - Custom OASIS PDF URL. Default: DITA 1.2 spec from docs.oasis-open.org. Override in config `dita_pdf.url` or env.

### Playwright Scraper (Experience League)
- `USE_PLAYWRIGHT_SCRAPER` - When true, crawl uses Playwright to extract structured content (p, li, codeph, codeblocks) for richer RAG and DITA conversion. Set `use_playwright: true` in `aem_guides_crawl_urls.json` instead.
- **First-time setup**: Run `playwright install chromium` after `pip install playwright`.

### Observability

#### LangSmith Tracing (LLM calls)
- `LANGSMITH_TRACING` - Set to `true` to enable LLM call tracing. When enabled, each LLM call (Anthropic, Bedrock, Groq) is traced to [smith.langchain.com](https://smith.langchain.com) with prompt tokens, completion tokens, latency, and retry count.
- `LANGSMITH_API_KEY` - Your LangSmith API key from smith.langchain.com (required when `LANGSMITH_TRACING=true`).
- `LANGCHAIN_TRACING_V2` - Set to `true` when using LangSmith. LangChain auto-instruments document loaders, chains, retrievers (RAG) when env is set.

#### Structured Logging
- `STRUCTURED_LOGGING` - Set to `true` for JSON-formatted logs (default: false). Logs include `dita_generation_started`, `dita_generation_completed`, `llm_dita_generation_started`, `llm_dita_generation_completed` with run_id, session_id, topic_count, duration_ms.

#### LLM Run Storage (DB)
LLM calls are stored in the `llm_runs` table (tokens_input, tokens_output, latency_ms, retry_count, model, step_name, error_type). Query directly or use `GET /api/v1/ai/llm-runs` if exposed.

## Indexing

### Index one issue
```bash
curl -X POST "http://localhost:8001/api/v1/ai/jira/index-one" \
  -H "Content-Type: application/json" \
  -d '{"issue_key": "DXML-123"}'
```

### Index recent issues
```bash
curl -X POST "http://localhost:8001/api/v1/ai/jira/index-recent" \
  -H "Content-Type: application/json" \
  -d '{"jql": "project = DXML AND updated >= -30d", "limit": 100}'
```

### Find similar issues
```bash
curl "http://localhost:8001/api/v1/ai/jira/similar?issue_key=DXML-123&k=5"
```

## Plan from Jira

Returns EvidencePack, ScenarioSet, per-scenario candidates, and domain classification.

```bash
curl -X POST "http://localhost:8001/api/v1/ai/plan-from-jira" \
  -H "Content-Type: application/json" \
  -d '{"jira_id": "DXML-123"}'
```

If the index has fewer than `AI_INDEX_MIN_ISSUES` (default 200), it will automatically index recent issues before planning.

## Generate from Jira

Full pipeline: evidence pack -> scenario expansion -> recipe retrieval -> planning -> execution -> validation -> bundle -> ZIP.

```bash
curl -X POST "http://localhost:8001/api/v1/ai/generate-from-jira" \
  -H "Content-Type: application/json" \
  -d '{"jira_id": "DXML-123"}'
```

Response includes `bundle.zip_path` and `bundle.bundle_dir`.

## Bundle ZIP Structure

```
{jira_id}_bundle.zip
  manifest.json
  S1_MIN_REPRO/
    (generated DITA files)
  S2_BOUNDARY/
    ...
  logs/
    planning.json
    validation.json
```

## Evaluation

Run the evaluation framework to measure domain accuracy, recipe selection, scenario diversity, and dataset validation rate:

```powershell
# From backend directory
py -m app.evaluation.run_eval

# Save report to file
py -m app.evaluation.run_eval -o eval_report.json

# Skip execution (planning only, faster)
py -m app.evaluation.run_eval --no-execution

# Write suggested prompt/recipe updates for iteration
py -m app.evaluation.run_eval -o report.json -f feedback.json
```

Or use the wrapper script:

```powershell
.\scripts\run_eval.ps1
# With options: .\scripts\run_eval.ps1 -Output report.json -Feedback feedback.json
```

Iterate on prompts in `app/templates/prompts/` and recipes based on results.

## Discovery and Debugging

Search dataset runs:

```bash
# Filter by Jira issue
curl "http://localhost:8001/api/v1/ai/datasets/search?jira_id=DXML-123"

# Filter by scenario type
curl "http://localhost:8001/api/v1/ai/datasets/search?scenario_type=MIN_REPRO"

# Filter by recipe used
curl "http://localhost:8001/api/v1/ai/datasets/search?recipe=conref_pack"

# Date range
curl "http://localhost:8001/api/v1/ai/datasets/search?date_from=2026-03-01&date_to=2026-03-04"

# Pagination
curl "http://localhost:8001/api/v1/ai/datasets/search?page=1&limit=20"
```

Response: `{items: [...], total, page, limit, pages}`.

## DITA Spec Coverage

The pipeline uses DITA spec knowledge (lexical + graph RAG) for valid scenario design:

- **Seed corpus**: `app/storage/dita_spec_seed.json` - 35+ elements with nesting and attributes
- **OASIS indexing**: `py scripts/index_dita_spec.py` (without `--seed-only`) fetches from OASIS DITA 1.3 spec
- **Seed-only (offline)**: `py scripts/index_dita_spec.py --seed-only` loads seed into DB
- **DITA 1.2 PDF RAG**: `POST /api/v1/ai/index-dita-pdf` downloads the OASIS DITA 1.2 spec PDF, loads with LangChain PyPDFLoader, splits, embeds, and stores in ChromaDB. When populated, ChromaDB is queried first; otherwise falls back to DB/seed.

To expand coverage, add elements to the seed or more URLs to `dita_spec_index_service.DEFAULT_URLS`.

## RAG Source Status

Check which LangChain sources are populated and used:

```bash
curl http://localhost:8001/api/v1/ai/rag-status
```

Returns `aem_guides` (Experience League) and `dita_spec` (DITA 1.2 PDF) chunk counts. When `chunk_count` is 0, run the populate endpoints. Logs show `source: chromadb` or `source: db_seed_fallback` when DITA/AEM docs are retrieved.
