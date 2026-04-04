# AI Chat — user guide (technical writers / DITA)

## What you can ask

- **DITA authoring:** glossary (`glossentry`, `glossref`), reuse (`conref`, `keyref`), maps (`topicref`, `navtitle`), accessibility (`alt`, `desc`), short descriptions.
- **AEM Guides:** product behavior, UI paths, and version-specific details — accuracy improves when **RAG** is populated (see Settings).
- **Jira → DITA (ZIP in chat):** Paste **Issue Summary + Description** (and steps) for the richest output. If the backend has **Jira configured** (`JIRA_BASE_URL` plus `JIRA_USERNAME`/`JIRA_PASSWORD` or `JIRA_EMAIL`/`JIRA_API_TOKEN`), you can send **only** an issue key (`GUIDES-19555`) or a **browse URL** (`…/browse/GUIDES-19555`); the server fetches the issue and the ZIP is named `GUIDES-19555_bundle.zip` instead of `TEXT-…`. If Jira is not configured or fetch fails, paste the full issue text—or fix `.env` and retry.
- **Dataset jobs:** Natural language requests for specific recipes may use **create_job**.

## Settings (RAG, Tavily, GitHub DITA)

Open **Settings** in the app (`/settings`) to:

- See **Chroma** / index status for AEM Guides and DITA spec content.
- Configure **Tavily** web search (when enabled) for supplemental context.
- Trigger or review **GitHub DITA** example indexing (when configured).

Example prompts are shown on the chat empty state; use them to prefill the composer.

## Refinement (“change the last generation”)

After **generate_dita**, follow-up messages like “add a concept topic” use the **last generation context** for that chat session. This context is **stored in the database** with the session so it **survives backend restarts** (unlike a pure in-memory cache).

If refinement ever seems ignored, send a short reminder or paste the relevant excerpt again.

## Reloading the page and tool results

Assistant messages persist **tool results** (e.g. `generate_dita` bundle links). After refresh or returning to a session, **Download** actions for verified bundles should still work when the message was saved with tool metadata.

## Further reading for prompt authors

See [PROMPT_BUILDING_GUIDE.md](./PROMPT_BUILDING_GUIDE.md) for RAG setup, prompt files, and versioning.
