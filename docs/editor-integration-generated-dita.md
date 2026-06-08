# Editor integration: screenshot-generated DITA

This repo’s **main** web app (`frontend/`) does not embed Oxygen-style XML editing elsewhere; the integration point is the **DITA workspace** page plus the existing **chat authoring** pipeline.

## User flow

1. **AI Chat** (`/chat`): attach screenshot, optional reference `.dita`, prompt, send (existing `ChatInput` + `sendMessage` authoring route).
2. **Result card** (`AttachmentAuthoringResultPanel` in `ChatMessage.tsx`): XML preview, validation list, download, open artifact URL (unchanged).
3. **Open in workspace**: loads full XML from `artifact_url` (GET `/api/v1/chat/assets/{id}` with cookies), stores a one-shot payload in `sessionStorage`, navigates to `/authoring`.
4. **Replace workspace**: same fetch/storage with `mode: replace_draft` (same editor behavior; metadata records the mode).
5. **Regenerate**: when this assistant message is the last in the thread, **Regenerate** calls the same chat **Regenerate** control (re-runs the last turn with persisted attachments).

## Validation before insert

If validation failed, there are structural/validator **errors**, or any **warnings** (including flattened `review_issues`), a **Radix dialog** lists them. Import is blocked until the user checks **“I understand…”** when errors are present or `valid` is false.

## Backend change

`chat_dita_authoring_service.py` now saves a **text asset whenever `final_xml` is non-empty**, not only when validation passes. Invalid topics still get an `artifact_url` so the workspace can load the full document for manual repair. AEM save still runs only when `validation_result.valid` and `save_path` is set.

## Undo / reload

- The workspace uses a native `<textarea>`: browser **Ctrl+Z / Ctrl+Y** applies to the buffer.
- Pending import is **consumed on first mount** of `/authoring` so a full page reload does not re-apply the same import from `sessionStorage`.

## Tests

- `frontend/src/lib/ditaWorkspaceBridge.test.ts` — sessionStorage queue semantics (Vitest + jsdom).
- Backend: existing `tests/test_chat_dita_authoring_integration.py` and `tests/test_chat_attachment_authoring.py` still pass.

## Extending to an external editor

`window` event `dita-studio:workspace-pending` fires when a topic is enqueued; another bundle could subscribe and call a host API. The canonical contract is `PendingWorkspaceTopic` in `frontend/src/lib/ditaWorkspaceBridge.ts`.
