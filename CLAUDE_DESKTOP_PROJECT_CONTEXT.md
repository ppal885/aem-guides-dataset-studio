# AEM Guides Dataset Studio — Project Context for Claude Desktop

Use this document to give Claude Desktop (or any AI assistant) full context about the project so it can help you effectively.

---

## Project Overview

**AEM Guides Dataset Studio** is a full-stack AI-powered application that generates DITA XML datasets from Jira evidence and natural language. It combines:

- **Backend**: Python FastAPI with LLM integration (Claude/Groq), RAG (ChromaDB, LangChain), multi-stage classification pipeline
- **Frontend**: React + Vite + TypeScript
- **Chat**: ChatGPT-style conversational interface with tool-calling, streaming, and RAG grounding

---

## Core Architecture

```
User (Chat UI)
    → POST /api/v1/chat/sessions/{id}/messages (SSE stream)
    → chat_service.chat_turn()
    → LLM (Claude/Groq) with tools: generate_dita, create_job
    → RAG: AEM Guides docs, DITA spec, Claude Code setup
    → Tool execution: generate_dita → _run_generate_from_text → LLM DITA generator
    → Progress: _generate_progress[run_id] updated at each stage
    → Frontend polls GET /api/v1/ai/generate-status/{run_id}
```

---

## Conversational Data Generation Flow (ChatGPT-Style)

### 1. First Generation

- User pastes Jira text or says "Create a task topic about X"
- LLM calls `generate_dita` tool with `text` and optional `instructions`
- Backend:
  - Creates `run_id`, sets `_generate_progress[run_id]` for polling
  - Yields `tool_start` event with `run_id` (frontend shows progress card)
  - Runs `_run_generate_from_text()`: planning → generating → enriching → validating → bundling
  - Updates `_generate_progress` at each stage
  - Stores last generation in `_session_last_generation[session_id]` for refinement
- Frontend: `GenerationProgressCard` polls `/api/v1/ai/generate-status/{run_id}` until completed
- Result: download link in chat, refinement hint shown

### 2. Conversational Refinement (Multi-Turn)

- User says "Add a concept topic" or "Make steps more detailed"
- `_build_context_block()` injects `LAST GENERATION IN THIS SESSION` with previous text
- LLM calls `generate_dita` with `text=<previous text>` and `instructions=<refinement request>`
- Same pipeline runs; new bundle generated

### 3. Key Data Structures

- **`_generate_progress`** (ai_dataset.py): `{run_id: {status, stage, message, jira_id, result, ...}}`
- **`_session_last_generation`** (chat_service.py): `{session_id: {text, instructions, jira_id, run_id, download_url}}`

---

## Key Files and Responsibilities

| File | Purpose |
|------|---------|
| `backend/app/services/chat_service.py` | Chat sessions, messages, RAG context, `chat_turn()` orchestrator, session generation context |
| `backend/app/services/chat_tools.py` | `generate_dita`, `create_job` tools; `run_tool()`; tool definitions for LLM |
| `backend/app/api/v1/routes/ai_dataset.py` | `_run_generate_from_text()`, `_update_generate_progress()`, generate-status, bundle download |
| `backend/app/api/v1/routes/chat.py` | Chat API routes; SSE streaming for messages |
| `backend/app/generator/llm_dita_generator.py` | LLM DITA generation (RAG-augmented), retry, content fidelity check |
| `backend/app/services/recipe_pipeline_service.py` | Mechanism → pattern → recipe routing (when GENERATE_FROM_TEXT_USE_PIPELINE=true) |
| `frontend/src/pages/ChatPage.tsx` | Chat UI, `generationRunId` state, `onToolStart` handler |
| `frontend/src/components/Chat/GenerationProgressCard.tsx` | Polls generate-status, shows stage progress, download button when done |
| `frontend/src/components/Chat/ChatMessage.tsx` | Renders messages, tool results (download card for generate_dita) |
| `frontend/src/api/chat.ts` | `sendMessage()` SSE client, `tool_start` event, `getGenerateStatus()` |

---

## API Endpoints

- `POST /api/v1/chat/sessions` — Create session
- `GET /api/v1/chat/sessions` — List sessions
- `GET /api/v1/chat/sessions/{id}` — Get session + messages
- `POST /api/v1/chat/sessions/{id}/messages` — Send message, SSE stream (chunk, tool_start, tool, done, error)
- `GET /api/v1/ai/generate-status/{run_id}` — Poll generation progress
- `GET /api/v1/ai/bundle/{jira_id}/{run_id}/download` — Download DITA ZIP
- `POST /api/v1/ai/generate-from-text` — Direct generate (body: `{text, instructions}`)

---

## SSE Event Types (Chat)

- `chunk` — Streaming text content
- `tool_start` — Tool started (for generate_dita: includes `run_id`)
- `tool` — Tool completed (includes `name`, `result`)
- `done` — Turn complete
- `error` — Error message

---

## Environment Variables (Relevant)

- `ANTHROPIC_API_KEY` / `GROQ_API_KEY` — LLM
- `GENERATE_FROM_TEXT_USE_PIPELINE` — Use recipe pipeline instead of direct LLM (default: false)
- `CHAT_CONTEXT_MAX_TOKENS` — Token budget for chat history
- `LLM_DITA_MAX_RETRIES` — Retries for LLM DITA generator
- `LLM_DITA_CONTENT_FIDELITY_ENABLED` — Optional content fidelity check

---

## DITA Generation Pipeline Stages

1. **planning** — Build evidence pack, optionally run recipe pipeline
2. **generating** — `execute_plan()` runs LLM DITA generator
3. **enriching** — `enrich_dita_folder`, `auto_fix_dita_folder`
4. **validating** — `validate_dita_folder`
5. **bundling** — `build_bundle`, `package_bundle`

---

## Prompt for Claude Desktop

Copy the following into a Claude Desktop project prompt or system instruction:

---

**You are helping with AEM Guides Dataset Studio — an AI-powered DITA dataset generator.**

**Project structure:**
- Backend: Python FastAPI in `backend/` (app/services/, app/api/, app/generator/)
- Frontend: React + Vite in `frontend/` (src/pages/, src/components/Chat/)
- Chat uses SSE streaming with events: chunk, tool_start, tool, done, error

**Conversational flow:**
- User pastes Jira or says "create DITA" → `generate_dita` tool runs
- Backend yields `tool_start` with `run_id` before execution; frontend polls `GET /api/v1/ai/generate-status/{run_id}`
- Progress stages: planning → generating → enriching → validating → bundling
- Last generation stored per session for refinement; user can say "add a concept topic" and LLM uses previous text + instructions

**Key services:**
- `chat_service.py`: chat_turn, session context, RAG, tool execution loop
- `chat_tools.py`: execute_generate_dita, run_tool, get_tool_definitions
- `ai_dataset.py`: _run_generate_from_text, _update_generate_progress, generate-status endpoint

**When debugging:** Check _generate_progress for run_id, _session_last_generation for session_id. RAG uses ChromaDB (AEM Guides, DITA spec). LLM DITA generator is in llm_dita_generator.py with retry and content fidelity options.

---
