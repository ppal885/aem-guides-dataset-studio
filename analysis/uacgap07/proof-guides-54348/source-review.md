# Source review for the generator demonstration

New run on existing GUIDES-54348, explicitly chosen by the user. This is not a blind benchmark or a fresh-ticket success claim. No Jira changes made.

Live issue description fetched via configured Jira MCP. The sole comment identifies itself as AI-generated and awaiting review; none of its 21 ACs establishes accepted Human truth.

## Inspected code

- XML Editor worktree: C:/xmleditor/xmleditor at 1f8e3996e40ea4c55cea2e11c52d7ddb6f58b09a. Tracked source files used below are unchanged; unrelated untracked user files retained.
- src/views/app_view.tsx lines 103-116 and 194-195 reads ditaAttributes.required into PAGE_REQUIRED_DITA_ATTRIBUTES.
- src/controllers/dialogs/insert_topicref_controller.ts lines 74-150 fetches per-path titles, checks the required-navtitle flag and DTD validity, and writes the attribute before conversion and insertion. Empty paths return before updateNavTitle.
- src/util/drag.ts lines 66-90 separately assembles topicref, glossref and mapref with title-cache values when required; keydef has a distinct construction path. This does not establish accepted scope or fallback policy for every type.
- Fetched branch origin/GUIDES-54348 at 999cd1e44311a0874e643f3d2d4827cb435b0821 differs from merge base with origin/develop (bce18629aadb6ef57550f3801cb6b87bbb894579) in three files, +13/-1. Read the complete diff: xml_markup_editor_controller.ts wires AUTHOR_REFRESH_NAV_TITLE to handleRefreshNavTitle, dispatching authorView.refreshNavTitle; xml_markup_author_controller.ts subscribes and calls editorContext.commands.refreshNavtitle(); the test adds one dispatch-table case.
- The branch does not change insertion functions. Whether that refresh-only change resolves the reported automatic-insertion failure remains an Open Question, not a confirmed fix. No GitHub MCP provider is exposed; local fetched refs are implementation evidence, not a fetched PR review.

## Clone boundaries and automation search

Guarded sync attempted on seven clones. No user work was stashed or overwritten. Existing tag conflicts prevented complete fetch on Starling, XML Editor, secondary UI tests and API tests; dirty clones were not pulled. Read-only fetched refs were used where available. Sync JSON files retain exact outcomes.

Exact search: required.*navtitle | navtitle.*required | refresh navigation title, plus navtitle under tests/editor_top_toolbar. Searched C:/UI TEST/guides-ui-tests origin/develop, C:/ui_framework/guides-ui-tests origin/main, C:/ui_framework/new_editor/guides-ui-tests origin/develop, C:/api automation/dxml-it-tests origin/develop, C:/editor-e2e/guides-editor-e2e HEAD. The new_editor container contains an automation clone, not a separate product clone.

UI automation explicitly sets required.navtitle in tests/editor_top_toolbar/environment.py:102. TC_03 in editor_top_toolbar.feature and steps/editor_top_toolbar.py:248-253 assert only refresh-button visibility, not saved automatic-insertion output. No match from the scoped API/E2E searches proves coverage; broader automation coverage remains unverified. Starling origin/develop was searched for ditaAttributes and PAGE_REQUIRED_DITA_ATTRIBUTES; this is not a claim that all backend behavior is absent.

## Evidence boundary

Three product-RAG probes timed out at the caller's 30-second limit. Indexed history succeeded after correcting component XML Editor to the supported Editor value; two focused queries returned no qualified matches, not proof no similar defects exist. Experience League directly confirms the core configuration behavior, not the unresolved specialization/fallback policies. Actual AEM execution, browser reproduction and Claude Desktop synthesis were not performed.

