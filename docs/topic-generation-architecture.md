# Topic generation from screenshot + reference DITA — repository map

> The React/Vite client named below has been retired. Frontend paths are retained only as historical implementation context; the backend pipeline remains available to API, MCP, CLI, and skill consumers.

## 1. Where uploads work

- **API**: `backend/app/api/v1/routes/chat.py` — `POST .../messages/authoring` accepts multipart `image_attachment`, optional `reference_dita`, plus generation options and optional `jira_context`.
- **Storage & validation**: `backend/app/services/chat_asset_service.py` — `save_upload_asset()` writes under `chat_assets/`, size limits, optional raster magic-byte checks for images.
- **Retired frontend snapshot**: the removed `frontend/src/api/chat.ts` and `frontend/src/components/Chat/ChatInput.tsx` previously supplied browser attachment controls. They are not active runtime dependencies.

## 2. Where chat orchestration lives

- **Streaming turn / attachment branch**: `backend/app/services/chat_service.py` — `_stream_attachment_authoring_reply` → `ChatDitaAuthoringService.generate_topic_from_request`.
- **Authoring service**: `backend/app/services/chat_dita_authoring_service.py` — intent classification, attachment collection, calls the screenshot-guided pipeline, saves artifacts, optional AEM upload.
- **Pipeline coordinator (stages + telemetry)**: `backend/app/services/dita_authoring_pipeline.py` — `run_screenshot_guided_pipeline` (now delegates to `TopicGenerationOrchestrator`).

## 3. Where DITA parsing / serialization lives

- **Reference parsing & safe style profile** (no ids/hrefs/conrefs in profile): `backend/app/services/reference_dita_analyzer.py` — `analyze_reference_dita`, `build_reference_summary`.
- **Screenshot → structured IR** (vision JSON, not OCR-only): `backend/app/services/screenshot_understanding_service.py` — `extract_screenshot_context`.
- **Semantic plan → internal draft**: `backend/app/services/dita_topic_draft.py` — `build_topic_draft`, `merge_structured_into_plan`, `infer_topic_type`.
- **Draft → XML**: `backend/app/services/dita_topic_serializer.py`, `structured_topic_draft.py` — programmatic serialization; LLM XML path only when style strictness is `low` (`chat_dita_authoring_service._render_dita_xml_with_mode`).

## 4. Where validation plugs in

- **Structural**: `backend/app/services/dita_authoring_structure.py` — `validate_dita_topic_structure_categorized`.
- **Folder / DTD**: `backend/app/utils/dita_validator.py` — `validate_dita_folder` (temp file).
- **Review / AEM-style signals**: `backend/app/services/smart_suggestions_service.py` — `build_review_snapshot`, `fix_all_safe` for repair.
- **Link guidance (post-gen)**: `backend/app/services/dita_link_recommendations.py`.

## Cisco-style enterprise task mode

- **Options**: `ChatDitaGenerationOptions.authoring_pattern` = `default` | `cisco_task` | `auto` (infer from reference structure).
- **Detection**: `app/services/cisco_task_authoring.py` scores task XML + `ReferenceStyleProfile` habits (prereq, step `info`, prolog, `uicontrol`/`codeph`, etc.).
- **Pipeline**: `TopicGenerationOrchestrator` adds stage `resolve_authoring_pattern`; forces `dita_type=task` when resolved to `cisco_task` and type unset.
- **Serialization**: `dita_topic_serializer.py` — `_serialize_cisco_enterprise_task_body` (ordering, `cmd`/`info`, `codeph` from draft snippets, optional reference DOCTYPE via `replace_first_doctype_line`).
- **Examples**: `examples/cisco-task-authoring.md`, fixture `backend/tests/fixtures/cisco_style_reference_task.dita`.

## 5. Files changed / added for modular services

| Area | Files |
|------|--------|
| New package | `backend/app/services/topic_generation/*.py` — orchestrator + named services |
| Pipeline entry | `backend/app/services/dita_authoring_pipeline.py` — delegates to orchestrator |
| Dedup | `backend/app/services/chat_dita_authoring_service.py` — `_summarize_reference_dita` uses `ReferenceDitaAnalyzer` |
| Tests | `backend/tests/test_topic_generation_services.py` |
| This doc | `docs/topic-generation-architecture.md` |

## Technical rationale

The product already enforced **structured IR → semantic plan (JSON) → topic draft → programmatic XML** for medium/high strictness, with **sanitized reference profiles** and **no copying of link/id attributes** into generated topics. The new package **names and isolates** each concern for tests, dependency injection, and future swaps (e.g. different vision providers or validators) without changing HTTP contracts or the `ScreenshotGuidedPipelineExecutor` protocol used for LLM-bound steps.
