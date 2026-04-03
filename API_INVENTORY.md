# API inventory — AEM Guides Dataset Studio

Generated from static analysis of the repository (FastAPI backend + Vite/React frontend). **Framework:** [FastAPI](https://fastapi.tiangolo.com/) on Starlette; app entry `backend/app/main.py`. **Global API prefix:** `/api/v1` (see `app.include_router(v1_router, prefix="/api/v1")` in `backend/app/main.py`).

---

## Routers registered on `api_router`

Defined in `backend/app/api/v1/router.py` — each `include_router` merges the sub-router’s `prefix` under `/api/v1`:

| Sub-router module | `APIRouter` prefix | Tags (OpenAPI) |
|-------------------|-------------------|----------------|
| `presets` | `/presets` | presets |
| `schedule` | `/jobs` | jobs |
| `dataset_explorer` | `/datasets` | datasets |
| `performance` | `/performance` | performance |
| `recipes` | `/recipes` | recipes |
| `bulk` | `/bulk` | bulk |
| `aem_recipes` | `/aem-recipes` | aem-recipes |
| `specialized` | `/specialized` | specialized |
| `scale_testing` | `/scale-testing` | scale-testing |
| `limits` | `/limits` | limits |
| `admin` | `/admin` | admin |
| `ai_dataset` | `/ai` | AI |
| `chat` | `/chat` | Chat |

**Not registered:** `backend/app/api/v1/routes/storage.py` defines `/storage` routes but is **not** imported in `router.py` (same situation as `doc_pdf`, `tenants`, `smart_suggestions`, `ai_flow`).

**Additional route on `api_router` itself (no extra prefix):** `GET /rag-status` — implemented in `router.py` (duplicate conceptually with `GET /ai/rag-status`; see “Overlaps”).

---

## Middleware and exception handling (`backend/app/main.py`)

| Layer | Purpose |
|-------|---------|
| `CORSMiddleware` | `allow_origins=["*"]`, credentials/methods/headers `*` |
| `request_context_middleware` | `X-Request-ID`, structured logging context |
| `deduplicate_requests` | Short-TTL response cache for identical POST/PUT/PATCH (DELETE excluded) |
| `validation_exception_handler` | 422 with structured Pydantic errors |
| `global_exception_handler` | 500 JSON; passes through `HTTPException` |

---

## Authentication (Bearer + dev bypass)

Implementation: `backend/app/core/auth.py`

- **`HTTPBearer(auto_error=False)`** — optional `Authorization: Bearer <token>`.
- **Token map:** `AUTH_TOKENS_JSON`, `ADMIN_BEARER_TOKEN`, `API_BEARER_TOKEN` (+ related env vars for user id/roles/tenants).
- **Dev/test bypass:** If `ENVIRONMENT` is `development` or `test` and `ALLOW_DEV_AUTH_BYPASS` is true (default), unauthenticated requests resolve to a default dev user with `admin` role.
- **Production:** Missing/unknown token → `401` with `WWW-Authenticate: Bearer`.

**Per-route:** Only routes that declare `user: UserIdentity = CurrentUser` or `AdminUser` run this logic. Routes **without** those dependencies do **not** invoke `get_current_user` and are therefore **not Bearer-protected** at the handler level (still subject to dev bypass behavior for *other* code paths that read `request.state.user` indirectly — most listed “none” routes have no user checks).

---

## Shared validation / schemas (selected)

| Area | Location / notes |
|------|-------------------|
| Job scheduling body | `ScheduleJobRequest` in `backend/app/api/v1/routes/schedule.py` |
| Chat | `SendMessageRequest`, `PatchMessageRequest`, `PatchSessionRequest`, `RegenerateRequest`, etc. in `backend/app/api/v1/routes/chat.py` |
| AI generate-from-text | `GenerateFromTextRequest` in `backend/app/api/v1/routes/ai_dataset.py` |
| Crawl / PDF index bodies | `CrawlRequest`, `IndexDitaPdfRequest`, `IndexGithubDitaRequest` in `ai_dataset.py` |
| Feedback submit | `FeedbackSubmitRequest` in `ai_dataset.py` |
| Bulk jobs | `BulkJobRequest`, `FlexibleJobRequest`, `BulkJobResponse` in `backend/app/api/v1/routes/bulk.py` |
| Saved recipes | `SavedRecipeCreate`, `SavedRecipeUpdate` in `backend/app/api/v1/routes/recipes.py` |
| Admin cleanup | `CleanupRequest` in `backend/app/api/v1/routes/admin.py` |
| AEM upload | `AemUploadRequest` in `backend/app/api/v1/routes/dataset_explorer.py` |
| Dataset job config (internal) | `DatasetConfig` in `backend/app/jobs/schemas.py` (used by scale-testing profile endpoint) |
| AI planner types | `app.core.schemas_ai` (imported by `ai_dataset.py` for pipeline logic, not always as response models) |

---

## Endpoint table — mounted (reachable via `main.py`)

Full path = `/api/v1` + router prefix + route path. Root app paths have no `/api/v1`.

| Method | Full path | Handler | File | Auth | Request summary | Response summary |
|--------|-----------|---------|------|------|-----------------|------------------|
| GET | `/` | `root` | `backend/app/main.py` | None | — | `message`, `version` |
| GET | `/health` | `health` | `backend/app/main.py` | None | — | DB/storage/resources/jobs/RAG/LLM status object |
| GET | `/api/v1/rag-status` | `get_rag_status_v1` | `backend/app/api/v1/router.py` | None | — | RAG snapshot via `_get_rag_status()` (AEM guides + DITA spec collections) |
| GET | `/api/v1/presets` | `list_recipe_presets` | `backend/app/api/v1/routes/presets.py` | None | — | `{ presets: [...] }` |
| GET | `/api/v1/presets/{preset_id}` | `get_recipe_preset` | `presets.py` | None | path `preset_id` | Preset object or 404 |
| POST | `/api/v1/presets/{preset_id}/apply` | `apply_recipe_preset` | `presets.py` | None | path + optional `base_config` (see FastAPI binding note below) | `{ config }` |
| GET | `/api/v1/jobs` | `list_jobs` | `backend/app/api/v1/routes/schedule.py` | **CurrentUser** | query: `status`, `limit`, `offset` | User’s jobs list (+ total) |
| GET | `/api/v1/jobs/{job_id}` | `get_job` | `schedule.py` | **CurrentUser** | path `job_id` | Job detail JSON |
| POST | `/api/v1/jobs` | `create_job` | `schedule.py` | **CurrentUser** | JSON body: `{ config: dict, ... }` (parsed manually) | Job summary JSON |
| POST | `/api/v1/jobs/schedule` | `schedule_job` | `schedule.py` | **CurrentUser** | body `ScheduleJobRequest` | Scheduled job metadata |
| GET | `/api/v1/datasets/{job_id}/download` | `download_dataset` | `backend/app/api/v1/routes/dataset_explorer.py` | **CurrentUser** | path | ZIP stream |
| GET | `/api/v1/datasets/{job_id}/structure` | `get_dataset_structure` | `dataset_explorer.py` | **CurrentUser** | path | `job_id`, `structure`, `manifest` |
| GET | `/api/v1/datasets/{job_id}/file` | `get_dataset_file` | `dataset_explorer.py` | **CurrentUser** | path + query `file_path` | File stream |
| GET | `/api/v1/datasets/{job_id}/search` | `search_dataset` | `dataset_explorer.py` | **CurrentUser** | path + query `query`, optional `file_type` | Search hits JSON |
| POST | `/api/v1/datasets/{job_id}/upload-to-aem` | `upload_dataset_to_aem` | `dataset_explorer.py` | **CurrentUser** | body `AemUploadRequest` | Upload result JSON |
| GET | `/api/v1/performance/metrics` | `get_performance_metrics` | `backend/app/api/v1/routes/performance.py` | **CurrentUser** | query `days` (default 7) | Metrics object |
| GET | `/api/v1/performance/timeline` | `get_performance_timeline` | `performance.py` | **CurrentUser** | query `days` (default 30) | `{ timeline, days }` |
| GET | `/api/v1/performance/job/{job_id}/profile` | `get_job_profile` | `performance.py` | **CurrentUser** | path | Job profile JSON |
| POST | `/api/v1/recipes/save` | `save_recipe` | `backend/app/api/v1/routes/recipes.py` | **CurrentUser** | body `SavedRecipeCreate` | `{ id, name, message }` |
| GET | `/api/v1/recipes` | `list_recipes` | `recipes.py` | **CurrentUser** | query `include_public`, `tags`, `search` | `{ recipes: [...] }` |
| GET | `/api/v1/recipes/{recipe_id}` | `get_recipe` | `recipes.py` | **CurrentUser** | path | Recipe detail |
| PUT | `/api/v1/recipes/{recipe_id}` | `update_recipe` | `recipes.py` | **CurrentUser** | path + body `SavedRecipeUpdate` | Update confirmation |
| DELETE | `/api/v1/recipes/{recipe_id}` | `delete_recipe` | `recipes.py` | **CurrentUser** | path | `{ message }` |
| POST | `/api/v1/recipes/{recipe_id}/use` | `use_recipe` | `recipes.py` | **CurrentUser** | path | Config + usage |
| POST | `/api/v1/bulk/jobs` | `create_bulk_jobs` | `backend/app/api/v1/routes/bulk.py` | **CurrentUser** | body `BulkJobRequest` | `BulkJobResponse` |
| POST | `/api/v1/bulk/jobs/from-template` | `create_bulk_jobs_from_template` | `bulk.py` | **CurrentUser** | OpenAPI: query `template_id`, body `variations` (FastAPI composite) | `BulkJobResponse` |
| POST | `/api/v1/bulk/jobs/from-csv` | `create_bulk_jobs_from_csv` | `bulk.py` | **CurrentUser** | OpenAPI treats simple types as **query** (`csv_data`, `name_prefix`) unless client sends JSON matching dependency injection — verify in `/docs` | Delegates to `create_bulk_jobs` |
| POST | `/api/v1/aem-recipes/relationship-table/preview` | `preview_relationship_table` | `backend/app/api/v1/routes/aem_recipes.py` | **CurrentUser** | body `RelationshipTableRecipeRequest` | Estimate + structure |
| POST | `/api/v1/aem-recipes/conref/preview` | `preview_conref_pack` | `aem_recipes.py` | **CurrentUser** | body `ConrefPackRecipeRequest` | Estimate + structure |
| POST | `/api/v1/aem-recipes/conditional/preview` | `preview_conditional_content` | `aem_recipes.py` | **CurrentUser** | body `ConditionalContentRecipeRequest` | Estimate + structure |
| POST | `/api/v1/aem-recipes/localized/preview` | `preview_localized_content` | `aem_recipes.py` | **CurrentUser** | body `LocalizedContentRecipeRequest` | Estimate + structure |
| POST | `/api/v1/specialized/task-topics/preview` | `preview_task_topics` | `backend/app/api/v1/routes/specialized.py` | **CurrentUser** | body `TaskTopicsRecipeRequest` | Estimate + structure |
| POST | `/api/v1/specialized/concept-topics/preview` | `preview_concept_topics` | `specialized.py` | **CurrentUser** | body `ConceptTopicsRecipeRequest` | … |
| POST | `/api/v1/specialized/reference-topics/preview` | `preview_reference_topics` | `specialized.py` | **CurrentUser** | body `ReferenceTopicsRecipeRequest` | … |
| POST | `/api/v1/specialized/glossary/preview` | `preview_glossary` | `specialized.py` | **CurrentUser** | body `GlossaryPackRecipeRequest` | … |
| POST | `/api/v1/specialized/bookmap/preview` | `preview_bookmap` | `specialized.py` | **CurrentUser** | body `BookmapStructureRecipeRequest` | … |
| POST | `/api/v1/specialized/media-rich/preview` | `preview_media_rich` | `specialized.py` | **CurrentUser** | body `MediaRichContentRecipeRequest` | … |
| POST | `/api/v1/specialized/workflow-enabled/preview` | `preview_workflow_enabled` | `specialized.py` | **CurrentUser** | body `WorkflowEnabledContentRecipeRequest` | … |
| POST | `/api/v1/specialized/output-optimized/preview` | `preview_output_optimized` | `specialized.py` | **CurrentUser** | body `OutputOptimizedRecipeRequest` | … |
| POST | `/api/v1/scale-testing/large-scale/preview` | `preview_large_scale` | `backend/app/api/v1/routes/scale_testing.py` | **CurrentUser** | body `LargeScaleTestRequest` | Estimate + warnings |
| POST | `/api/v1/scale-testing/deep-hierarchy/preview` | `preview_deep_hierarchy` | `scale_testing.py` | **CurrentUser** | body `DeepHierarchyTestRequest` | … |
| POST | `/api/v1/scale-testing/wide-branching/preview` | `preview_wide_branching` | `scale_testing.py` | **CurrentUser** | body `WideBranchingTestRequest` | … |
| POST | `/api/v1/scale-testing/performance-profile` | `get_performance_profile` | `scale_testing.py` | **CurrentUser** | body `DatasetConfig` + `test_type` + `test_params` (composite; confirm in OpenAPI) | Metrics sample JSON |
| GET | `/api/v1/limits` | `get_limits` | `backend/app/api/v1/routes/limits.py` | None | — | Static limits object |
| POST | `/api/v1/admin/cleanup` | `trigger_cleanup` | `backend/app/api/v1/routes/admin.py` | **AdminUser** | body `CleanupRequest` (optional fields) | Cleanup stats |
| GET | `/api/v1/ai/datasets/search` | `search_datasets` | `backend/app/api/v1/routes/ai_dataset.py` | None | query filters + pagination | Paginated `DatasetRun` summary |
| GET | `/api/v1/ai/bundle/{jira_id}/{run_id}/download` | `download_ai_bundle` | `ai_dataset.py` | None | path | ZIP file |
| GET | `/api/v1/ai/prompt-versions` | `get_prompt_versions` | `ai_dataset.py` | None | — | Prompt versions JSON |
| GET | `/api/v1/ai/pipeline-metrics` | `get_pipeline_metrics` | `ai_dataset.py` | None | query `limit` | Aggregated metrics |
| GET | `/api/v1/ai/agentic-config` | `get_agentic_config` | `ai_dataset.py` | None | — | Config + overrides |
| PATCH | `/api/v1/ai/agentic-config` | `patch_agentic_config` | `ai_dataset.py` | None | JSON body `dict` of numeric overrides | `{ overrides }` |
| POST | `/api/v1/ai/crawl-aem-guides` | `crawl_aem_guides` | `ai_dataset.py` | None | optional body `CrawlRequest` | Crawl stats |
| GET | `/api/v1/ai/crawl-status` | `get_crawl_status` | `ai_dataset.py` | None | — | Playwright / file diagnostics |
| GET | `/api/v1/ai/rag-status` | `get_rag_status` | `ai_dataset.py` | None | query `tenant_id` (default `default`) | Extended RAG status (+ tavily, github_dita) |
| POST | `/api/v1/ai/index-dita-pdf` | `index_dita_pdf` | `ai_dataset.py` | None | optional body `IndexDitaPdfRequest` | Index stats |
| POST | `/api/v1/ai/index-github-dita-examples` | `index_github_dita_examples_route` | `ai_dataset.py` | None | optional body `IndexGithubDitaRequest` | Index results |
| GET | `/api/v1/ai/feedback` | `list_feedback` | `ai_dataset.py` | None | query filters | Feedback list |
| GET | `/api/v1/ai/feedback/insights` | `get_feedback_insights` | `ai_dataset.py` | None | query | Aggregated insights |
| POST | `/api/v1/ai/feedback/apply-overrides` | `apply_feedback_overrides` | `ai_dataset.py` | None | query | Override application summary |
| POST | `/api/v1/ai/feedback/export-pairs` | `export_feedback_pairs` | `ai_dataset.py` | None | query | `{ path, count }` |
| POST | `/api/v1/ai/feedback/submit` | `submit_feedback` | `ai_dataset.py` | None | body `FeedbackSubmitRequest` | `{ status: ok }` |
| GET | `/api/v1/ai/feedback/for-run/{run_id}` | `get_feedback_for_run` | `ai_dataset.py` | None | path | Feedback items |
| GET | `/api/v1/ai/feedback/{feedback_id}` | `get_feedback` | `ai_dataset.py` | None | path | Single feedback (care: static paths like `insights` registered before this route in code — `feedback_id` catches non-reserved ids) |
| POST | `/api/v1/ai/run-eval` | `run_eval` | `ai_dataset.py` | None | query `run_execution` | Eval report |
| GET | `/api/v1/ai/generate-status/{run_id}` | `get_generate_status` | `ai_dataset.py` | None | path | In-memory progress dict |
| GET | `/api/v1/ai/generate-stream/{run_id}` | `get_generate_stream` | `ai_dataset.py` | None | path | SSE progress |
| POST | `/api/v1/ai/generate-from-text` | `generate_from_text` | `ai_dataset.py` | None | body `GenerateFromTextRequest`; query `async`, `skip_rag_check` | Result JSON or async `{ run_id, ... }` |
| DELETE | `/api/v1/chat/all-sessions` | `delete_all_chat_sessions_endpoint` | `backend/app/api/v1/routes/chat.py` | None | — | `DeleteAllSessionsResponse` |
| POST | `/api/v1/chat/sessions` | `post_create_session` | `chat.py` | None | — | `{ session_id }` |
| GET | `/api/v1/chat/sessions` | `get_list_sessions` | `chat.py` | None | query `limit`, `offset` | `{ sessions }` |
| DELETE | `/api/v1/chat/sessions/purge-all` | `delete_all_sessions` | `chat.py` | None | — | `DeleteAllSessionsResponse` |
| GET | `/api/v1/chat/sessions/{session_id}` | `get_session_by_id` | `chat.py` | None | path | Session + messages |
| DELETE | `/api/v1/chat/sessions/{session_id}` | `delete_session_by_id` | `chat.py` | None | path | `ok` or bulk delete if id aliases `purge-all` |
| PATCH | `/api/v1/chat/sessions/{session_id}` | `patch_session` | `chat.py` | None | body `PatchSessionRequest` | Updated session |
| PATCH | `/api/v1/chat/sessions/{session_id}/messages/{message_id}` | `patch_user_message` | `chat.py` | None | body `PatchMessageRequest` | `{ messages }` |
| POST | `/api/v1/chat/sessions/{session_id}/regenerate` | `post_regenerate` | `chat.py` | None | optional body `RegenerateRequest` | SSE stream |
| GET | `/api/v1/chat/sessions/{session_id}/messages` | `get_session_messages` | `chat.py` | None | path + query `limit` | `{ messages }` |
| POST | `/api/v1/chat/sessions/{session_id}/messages` | `post_send_message` | `chat.py` | None | body `SendMessageRequest` | SSE stream |

---

## Routers defined but **not** mounted in `backend/app/api/v1/router.py`

These modules define `APIRouter` and handlers but **`api_router.include_router(...)` is never called** for them in the active router file. They are **not** reachable through `main.py` unless another entrypoint mounts them (none found in this repo’s active app).

| Module | Intended prefix (from `incoming_archives` samples only — **not active**) | Notes |
|--------|--------------------------------------------------------------------------|-------|
| `backend/app/api/v1/routes/doc_pdf.py` | Archive suggests `/docs` | Routes: `POST /index-pdf`, `GET /indexed`, `DELETE /indexed/{file_hash}`, `POST /index-directory` |
| `backend/app/api/v1/routes/smart_suggestions.py` | Archive suggests `/smart` | Routes under empty prefix in module: `/analyse`, `/apply-fix`, `/refine-completions`, `/section-suggestions`, `/fix-all` |
| `backend/app/api/v1/routes/tenants.py` | Archive suggests `/admin/tenants` | CRUD + KB update; all use `AdminUser` |
| `backend/app/api/v1/routes/ai_flow.py` | Would be `/ai/flow-intelligence` if mounted at root of v1 (module path is `/ai/flow-intelligence`) | Uses `CurrentUser` + tenant resolution |
| `backend/app/api/v1/routes/storage.py` | Would be `/storage/*` if `include_router(storage.router)` were added | `GET /disk-usage`, `GET /storage-stats`, `POST /check-space`, `POST /estimate-size`; all use **CurrentUser** |

**Evidence:** `grep include_router` under `backend/` only matches `main.py` and `router.py`; `router.py` imports omit these modules (see file).

---

## Frontend HTTP usage vs backend

Mapped from `frontend/src/**/*.tsx` and `frontend/src/**/*.ts` (fetch to `/api/v1/...`).

| Frontend path | Backend |
|---------------|---------|
| `/api/v1/chat/*`, `/api/v1/ai/generate-status/*` | **Mounted** — `chat.py`, `ai_dataset.py` |
| `/api/v1/ai/rag-status`, `index-dita-pdf`, `crawl-aem-guides`, `index-github-dita-examples` | **Mounted** — `ai_dataset.py` |
| `/api/v1/limits` | **Mounted** — `limits.py` |
| `/api/v1/jobs`, `/api/v1/jobs/schedule`, `/api/v1/jobs/{id}` | **Mounted** — `schedule.py` |
| `/api/v1/datasets/{id}/*` | **Mounted** — `dataset_explorer.py` |
| `/api/v1/performance/metrics`, `timeline` | **Mounted** — `performance.py` |
| `/api/v1/recipes/*` | **Mounted** — `recipes.py` |
| `/api/v1/bulk/jobs` | **Mounted** — `bulk.py` |
| `/api/v1/presets` | **Mounted** — `presets.py` |

**No frontend references found** (in `frontend/src`) to: `/api/v1/storage/*` (also **not mounted** in `router.py`), `/api/v1/admin/*`, most `/api/v1/ai/*` (except those above), `/api/v1/bulk/jobs/from-template`, `/api/v1/bulk/jobs/from-csv`, `/api/v1/aem-recipes/*`, `/api/v1/specialized/*`, `/api/v1/scale-testing/*`, `/api/v1/rag-status` (top-level alias), `/api/v1/ai/datasets/search`, bundle download, feedback APIs, `run-eval`, `generate-stream`, etc. Those backends exist but appear **unused by the current frontend** (may be used by tests, scripts, or external clients).

---

## Findings: quality / overlap / gaps

### Possibly incomplete or problematic implementations

1. **`dataset_explorer.py` — debug logging to a fixed local path**  
   `download_dataset` opens `c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\.cursor\debug.log` (lines 39–40 and nearby). That path is environment-specific and likely fails or is dead on other machines — should be removed or gated.

2. **`POST /api/v1/bulk/jobs/from-csv`**  
   Parameters `csv_data: str` and `name_prefix` are simple types; in FastAPI they are typically **query** parameters, which is impractical for large CSV payloads. Confirm at `/docs` and consider a Pydantic body model.

3. **`POST /api/v1/presets/{preset_id}/apply`**  
   `base_config: dict = None` is ambiguous for clients (body vs query). Confirm OpenAPI.

4. **`POST /api/v1/scale-testing/performance-profile`**  
   Composite signature (`DatasetConfig` + `test_type` + `test_params`) — verify OpenAPI for exact client shape.

5. **Global exception handler** may return `str(exc)` in 500 responses (`main.py`) — risk of leaking internal details (security/style issue, not an “incomplete endpoint”).

### Duplicate / overlapping endpoints

- **`GET /api/v1/rag-status`** (`router.py`) vs **`GET /api/v1/ai/rag-status`** (`ai_dataset.py`): different implementations; the latter includes Tavily/GitHub DITA summary and `tenant_id`. Frontend uses **`/api/v1/ai/rag-status`** (`SettingsPage.tsx`).

- **Chat session purge:** `DELETE /api/v1/chat/all-sessions`, `DELETE /api/v1/chat/sessions/purge-all`, and `DELETE /api/v1/chat/sessions/{session_id}` with `purge-all` alias — overlapping ways to clear sessions (by design per comments in `chat.py`).

### Frontend calls with no matching mounted backend

- **None identified** for paths listed in the frontend grep — all referenced `/api/v1/...` paths match mounted routers.

### Dead / unused HTTP routers (in active app)

- `doc_pdf.py`, `smart_suggestions.py`, `tenants.py`, `ai_flow.py`, **`storage.py`** — **not included** in `router.py`. Services are still tested or used internally, but **HTTP routes are inactive**.

### Auth gaps (informational)

- **Chat**, **limits**, and most **`/api/v1/ai/*`** routes do not use `CurrentUser`. In production with `ALLOW_DEV_AUTH_BYPASS=false`, they remain **unauthenticated** at the FastAPI dependency layer (anyone can call them unless another layer blocks). Routes using **`CurrentUser`** / **`AdminUser`** enforce Bearer (or dev user when bypass is on).

---

## Non-HTTP “API”

- **`mcp_server.py`**: FastMCP tool server (Jira, etc.), **not** part of the FastAPI route tree.

---

## Evidence references

```270:275:backend/app/main.py
app.include_router(v1_router, prefix="/api/v1")
```

```44:62:backend/app/api/v1/router.py
@api_router.get("/rag-status")
def get_rag_status_v1():
    """RAG source status (alias at /api/v1/rag-status). Also at /api/v1/ai/rag-status."""
    return _get_rag_status()


api_router.include_router(presets.router)
api_router.include_router(schedule.router)
api_router.include_router(dataset_explorer.router)
api_router.include_router(performance.router)
api_router.include_router(recipes.router)
api_router.include_router(bulk.router)
api_router.include_router(aem_recipes.router)
api_router.include_router(specialized.router)
api_router.include_router(scale_testing.router)
api_router.include_router(limits.router)
api_router.include_router(admin.router)
api_router.include_router(ai_dataset.router)
api_router.include_router(chat.router)
```

```43:46:backend/app/api/v1/routes/ai_dataset.py
router = APIRouter(prefix="/ai", tags=["AI"])
```

```23:24:backend/app/api/v1/routes/chat.py
router = APIRouter(prefix="/chat", tags=["Chat"])
```

```7:7:backend/app/api/v1/routes/ai_flow.py
router = APIRouter()
```

```12:12:backend/app/api/v1/routes/doc_pdf.py
router = APIRouter()
```

*(No `include_router` for `ai_flow`, `doc_pdf`, `smart_suggestions`, or `tenants` in `router.py` — see full file listing above.)*

---

*End of inventory.*
