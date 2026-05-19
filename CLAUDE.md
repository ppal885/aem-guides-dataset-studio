# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

AEM Guides Studio — a full-stack tool for generating, validating, and managing DITA XML datasets for Adobe Experience Manager Guides. It has two major modes:

1. **Dataset Generator** — a "recipe"-based system that produces deterministic or LLM-generated DITA XML bundles (topics, maps, keydefs, conrefs, reltables, etc.) for use as training data or test fixtures.
2. **Chat/Authoring Assistant** — an agentic AI chat interface that lets users query DITA specs, search Jira, and author DITA topics from screenshots or text using a multi-stage pipeline.

---

## MCP Server

`mcp_server/server.py` exposes the studio's capabilities as MCP tools for Claude Desktop, Cursor, and Claude Code.

**Exposed tools:** `find_recipes`, `lookup_dita_spec`, `lookup_aem_guides`, `lookup_dita_attribute`, `review_dita_xml`, `fix_dita_xml`, `generate_dita`, `generate_dita_from_screenshot`, `list_jobs`, `get_job_status`, `search_jira_issues`.

The MCP server calls the backend REST API. A new bridge route (`backend/app/api/v1/routes/mcp_bridge.py`, registered at `/api/v1/mcp/*`) provides direct service-level endpoints for tools that have no standalone REST endpoint.

### Setup

```bash
# Install MCP server dependencies (separate from backend)
pip install -r mcp_server/requirements.txt

# Backend must be running first
cd backend && python run_local.py
```

### Claude Desktop

Merge `mcp_server/claude_desktop_config.json` into:
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

### Cursor

Copy `mcp_server/cursor_mcp.json` to `.cursor/mcp.json` in this repo (or `~/.cursor/mcp.json` for global).

### Claude Code

```bash
claude mcp add aem-guides-dataset-studio -- python mcp_server/server.py
```

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `AEM_STUDIO_URL` | `http://127.0.0.1:8001` | Backend base URL |
| `AEM_STUDIO_TOKEN` | `dev-bypass` | Bearer token (works when `ALLOW_DEV_AUTH_BYPASS=true`) |

---

## Commands

### Backend (Python / FastAPI)

```bash
cd backend

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt   # dev/test extras

# Run the dev server (port 8001 by default)
python run_local.py

# Run all backend tests
pytest

# Run a single test file
pytest tests/test_dita_authoring_pipeline.py

# Run a single test by name
pytest tests/test_dita_authoring_pipeline.py::test_function_name -v

# Run quick generator smoke tests (no pytest)
python test_all_generators.py
python test_all_recipe_types.py
```

The backend reads `backend/.env` (copy from `backend/.env.example`). At minimum set `ANTHROPIC_API_KEY` and `ALLOW_DEV_AUTH_BYPASS=true` for local dev.

### Frontend (React / Vite)

```bash
cd frontend

# Install dependencies
npm install

# Dev server — http://localhost:5173 (see frontend/vite.config.ts; strictPort avoids silent fallback to another port)
npm run dev

# Run frontend tests
npm test

# Run a single test file
npx vitest run src/components/Chat/toolResultUtils.test.ts

# Type-check + build
npm run build:check

# Lint
npm run lint
```

---

## Architecture

### Backend Layout

```
backend/
  app/
    main.py              # FastAPI app, middleware (CORS, dedup, logging), APScheduler
    api/v1/routes/       # Route handlers: chat, ai_dataset, bulk, recipes, presets, schedule, tenants, admin, qa_studio, ...
    core/                # Schemas (Pydantic), auth, logging, observability, runtime_safety
    generator/           # Deterministic DITA XML generators — one module per recipe family
    services/            # Business logic: chat, LLM, authoring pipeline, Jira, RAG, upload, ...
    jobs/                # Job CRUD, SQLAlchemy models
    db/                  # SQLAlchemy session, migrations, models
    storage/             # Local filesystem storage abstraction
    training/            # Contrastive / feedback pair generation for fine-tuning
    utils/               # XML escaping, validation, rate limiting, disk monitoring
```

### Recipe System

Each DITA generator is a Python module under `app/generator/`. Generators declare themselves via a `RecipeSpec` dataclass (see `app/generator/recipe_manifest.py`). `discover_recipe_specs()` auto-discovers all specs by scanning the package. The executor (`app/services/ai_executor_service.py`) takes an LLM-produced `GeneratorInvocationPlan`, resolves the recipe, coerces params, and calls the generator function. Param caps (`PARAM_CAPS`) prevent oversized runs on AI-generated plans.

### Chat / Agentic System

`POST /api/v1/chat/{session_id}/messages` streams SSE. The core loop is in `app/services/chat_service.py`, which calls the LLM with a tool catalog (`app/services/chat_tools.py`). Tools include:

- `find_recipes` — semantic search over recipe specs
- `create_job` — launches a dataset generation job (requires approval in the UI)
- `fix_dita_xml` — auto-repair DITA XML
- `search_jira_issues` — Jira integration
- `lookup_dita_spec` / `lookup_dita_attribute` — RAG over DITA 1.3 spec
- `lookup_aem_guides` — RAG over Experience League crawl
- `browse_dataset`, `get_job_status`, `list_jobs` — dataset lifecycle
- `generate_native_pdf_config`, `lookup_output_preset` — AEM Guides output presets

`APPROVAL_REQUIRED_TOOLS` (`create_job`, `fix_dita_xml`) require explicit user confirmation before execution.

**Live LLM instructions (answer quality):** Normal chat (tool mode and grounded RAG replies) uses the **compact** system prompt built by `_build_compact_chat_system_prompt` in `app/services/chat_service.py` — not the large `app/templates/prompts/chat_system.json` spec (that JSON is loaded by `_get_chat_prompt_builder` but is unused in the main reply path today). Tool-mode and grounded paths append `TOOL RESULT SAFETY RULES` where applicable. **Precision mode** (**`human_prompts`**, **`chat_human_precision.txt`** under `PRECISION MODE`) is **on by default** when the client omits the flag or sends `null`; set **`human_prompts: false`** on the send/regenerate JSON body (or form field) for longer, more conversational replies. Set **`CHAT_SUGGEST_FOLLOWUPS=true`** (or `1` / `yes` / `on`) to allow an optional **`## Next questions`** section in compact-prompt replies. Grounded user prompts instruct the model to cite evidence IDs inline (**`[E1]`**, **`[E2]`**, …) when the evidence block includes those labels, and to treat prior assistant prose as **unverified** (only the Evidence block is authoritative). **Follow-up utterances** use `_fetch_last_messages_for_session` + `_expand_follow_up_retrieval_query` so the transcript and corrective-RAG / grounded-tool queries include the **latest** turns and, when appropriate, the prior user question—reducing off-topic retrieval and hallucination on short replies like “what about conref?”. Multi-step **agent research** final synthesis uses `_synthesize_agent_answer`, which prescribes `## Summary`, `## Details`, `## Limits of evidence`, optional **`## Recommended next step`**, and `## Sources`.

### Prompt patterns for `create_job` (dataset generation)

When chat calls `create_job`, subject-aware LLM authoring runs if the primary recipe is a hierarchy/scale or flat-content type **and** either `subject` or `prompt_text` is set (sanitized caps: subject ≤ 200 chars, `prompt_text` ≤ 4000). Implementation: `execute_create_job` in `app/services/chat_tools.py`; authoring helpers in `app/services/subject_aware_hierarchy_service.py`.

| Enrichment path | `recipe_type` values | LLM-authored slice |
|---|---|---|
| `generate_subject_content` | `deep_hierarchy`, `wide_branching`, `flat_hierarchical_dita`, `large_scale` | Up to **60** titles + short bodies; remainder uses subject-templated fallback in generators |
| `generate_flat_content` | `task_topics`, `concept_topics`, `reference_topics`, `glossary_pack` | Up to **120** items |

If the assistant omits `subject`, a rich **`prompt_text`** (verbatim user excerpt) still triggers enrichment and supplies hints.

**Effective user prompts (examples)**

1. Name the domain explicitly so the model fills `subject`: e.g. *“Generate a deep hierarchy DITA dataset about **Kubernetes networking** — Services, Ingress, NetworkPolicies.”*
2. Pair structure + subject + optional `config`: e.g. *“**flat_hierarchical_dita** with `topic_count` ~500 for **OpenAPI 3.1** IA.”*
3. Use `prompt_text` for constraints: short `subject` (**Kubernetes**) plus *“Emphasize scheduling and resource quotas; keep titles under 80 chars.”*
4. Flat recipes: *“**reference_topics** for **Terraform** — state backend, modules, workspaces.”* or *“**task_topics** for **Kubernetes** — kubectl install, namespaces, applying manifests.”*
5. Glossary: *“**glossary_pack** for **cloud networking** — VPC, subnet, NAT gateway, route table, peering.”*

**Avoid**

- Vague scale-only asks (*“make a huge tree”*) without a domain — weak titles/bodies.
- Recipe mismatch — have the assistant call `find_recipes` first so `recipe_type` matches intent (e.g. Terraform reference vs unrelated structural-only recipes).

| Goal | Typical `recipe_type` | What to include in chat |
|---|---|---|
| Deep tree + domain | `deep_hierarchy` | Domain + depth/branch hints; optional `config` (`depth`, `children_per_level`) |
| Wide fan-out | `wide_branching` | Domain + counts (`root_topics`, `children_per_root`) |
| Large flat set | `large_scale` or `flat_hierarchical_dita` | Domain + `topic_count` |
| Reference-style topics | `reference_topics` | Domain + areas (e.g. Terraform AWS resources) |
| Procedures | `task_topics` | Named workflows |
| Terminology | `glossary_pack` | Subject area for terms |

### Screenshot-Guided DITA Authoring Pipeline

`app/services/dita_authoring_pipeline.py` runs a 9-stage pipeline:

1. `analyze_screenshot` — vision LLM classifies UI screenshot
2. `analyze_reference_topic` — parses user-supplied reference DITA
3. `infer_topic_type` — determines concept/task/reference
4. `build_semantic_plan` — LLM produces a structured plan
5. `merge_screenshot_ir` — merges plan with screenshot IR
6. `build_structured_draft` — constructs a `TopicDraft` (typed sections, tables, notes)
7. `serialize_xml` — programmatic or LLM serialization to DITA XML
8. `validate` — DTD/schema + semantic validation
9. `repair_optional` — LLM repair loop on validation failure

Entry point is `app/services/chat_dita_authoring_service.py`, which is invoked from the chat tool `generate_dita_from_screenshot`.

### AEM Guides MathML in DITA

For **prefixed MathML** (`m:math`), **equation-block** / **mathml** wrappers, DTD errors such as `Element type "math" must be declared`, and authoring rules for AEM Guides, see the Cursor rule [`.cursor/rules/aem-guides-dita-mathml.mdc`](.cursor/rules/aem-guides-dita-mathml.mdc). Chat’s compact system prompt also carries a short reminder so replies default to Guides-safe equation markup.

### LLM Service

`app/services/llm_service.py` supports multiple providers selected by `LLM_PROVIDER`:
- `anthropic` (default, claude-3-5-sonnet-20241022)
- `bedrock` (AWS — for Adobe internal use via Project Turnkey / CAMP)
- `groq`
- `openai`
- `azure_openai`

Screenshot/vision calls can use a separate `SCREENSHOT_VISION_PROVIDER`. The service has a circuit breaker (env-gated), rate limiter, and optional LangSmith tracing.

### Generate-from-Text Pipeline

`app/services/generate_from_text_service.py` is the shared entry point for both the REST API (`/api/v1/ai-dataset/generate-from-text`) and the chat `create_job` tool. Flow:

1. Resolve Jira context if a Jira key is supplied
2. LLM produces a `GeneratorInvocationPlan` (recipe selection + params)
3. `execute_plan` runs the chosen generator(s)
4. Bundle is built, validated (DTD + semantic contract), optionally auto-fixed
5. Packaged as a ZIP artifact in `backend/storage/`

### QA Studio (UI automation planning & generation)

Optional **AEM Guides QA Studio** surface for Jira-grounded automation **plans** (Behave + Page Object style) and, when enabled, **LLM-authored** feature/step/PO proposals with validation gates.

- **API** (prefix `/api/v1/qa-studio`): `POST /plan` (planning gate + stub or LLM plan), `POST /generate` (LLM codegen from an inline `plan` JSON), plus validators, bundled playbooks, locator checks, dashboard `GET /status`.
- **Orchestration:** `app/services/qa_studio_llm_authoring.py` — `run_llm_planning` / `run_llm_generation`, plan judge (`_judge_plan`), `validate_automation_artifacts` wrapper, self-correction via `generate_json`. Prompts in `backend/prompts/qa_studio_authoring.py`. Retrieval digest + optional Jira QA Chroma context in `app/services/qa_studio_retrieve_for_plan.py`. Existing gates/validators: `qa_studio_plan_gate.py`, `qa_studio_automation_validator.py`, `qa_studio_assertion_traceability.py`, `qa_studio_rag_evidence.py`, bundled JSON under `app/data/qa_studio/`.
- **Enable LLM path:** set `QA_STUDIO_LLM_AUTHORING=true` and configure the same LLM provider as the rest of the app (see `backend/.env.example` for `QA_STUDIO_*` / `GQS_*` retry and lite-plan knobs). When the flag is off or the LLM is unavailable, `POST /plan` returns the **stub** plan only.

### Frontend Layout

```
frontend/src/
  App.tsx              # Routes: /, /builder, /job-history, /dataset-explorer, /chat, /upload, /settings, /qa-studio/*
  pages/               # Builder, ChatPage, JobHistoryPage, DatasetExplorerPage, AemUploadPage, SettingsPage, QaStudioPage
  components/
    Chat/              # Chat UI: ChatMessage, ChatInput, ChatSidebar, streaming, tool result rendering
    Authoring/         # DITA authoring review UI (split-screen, regenerate options)
    *Config.tsx        # One component per recipe type (rendered in Builder)
  api/chat.ts          # Chat API client (SSE streaming)
  api/qaStudio.ts      # QA Studio API client (plan, generate, validators)
  utils/api.ts         # fetchWithRetry, fetchJson — all HTTP calls go through here
  lib/                 # ditaWorkspaceBridge, authoringGenerationDefaults
```

The frontend always calls the backend at `http://127.0.0.1:8001` in dev (inferred from `window.location`). Override with `VITE_API_BASE_URL`.

### Auth

`ALLOW_DEV_AUTH_BYPASS=true` skips token validation. In production, set `AUTH_TOKENS_JSON` (map of token→UserIdentity) or `API_BEARER_TOKEN`. Multi-tenant: each user has `allowed_tenants`; tenant context is forwarded through all API calls.

### Storage

All generated bundles are stored under `backend/storage/` as flat directories (`TEXT-<id>_bundle/`) and ZIPs (`backend/storage/zips/`). The storage abstraction is `app/storage/local_storage.py`. ChromaDB vector stores for RAG live under `backend/storage/chroma_db/`.

---

## Key Environment Variables

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Required for LLM generation and chat |
| `LLM_PROVIDER` | `anthropic` \| `bedrock` \| `groq` \| `openai` |
| `ALLOW_DEV_AUTH_BYPASS` | Set `true` for local dev (skips bearer token check) |
| `PORT` | Backend port (default `8001`) |
| `JIRA_URL`, `JIRA_USERNAME`, `JIRA_PASSWORD` | Jira integration |
| `JIRA_API_VERSION` | `2` for on-prem/corp Jira, `3` for Jira Cloud |
| `TAVILY_API_KEY` | Web search augmentation for chat |
| `GENERATE_FROM_TEXT_USE_INTENT_PIPELINE` | Enable intent-driven recipe selection |
| `DITA_PIPELINE_MAX_REPAIRS` | Max LLM repair rounds on validation failure |
| `QA_STUDIO_LLM_AUTHORING` | Set `true` to use LLM for `POST /qa-studio/plan` and `POST /qa-studio/generate` (stub plans when off or LLM unavailable) |
| `QA_STUDIO_DEEP_REASONING`, `GQS_DEEP_REASONING` | Optional senior-QA reasoning block before planning |
| `QA_STUDIO_PLAN_MAX_RETRIES`, `GQS_PLAN_MAX_RETRIES` | Max plan judge retry rounds after LLM (default 2) |
| `QA_STUDIO_GEN_MAX_RETRIES`, `GQS_GEN_MAX_RETRIES` | Max generation validation retry rounds (default 2) |
| `QA_STUDIO_PLAN_LITE`, `GQS_PLAN_LITE` | Shorter / lighter plans when set truthy |

Full reference: `backend/.env.example`.
