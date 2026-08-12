# Authoring State and Structural UAC Contract

Use this reference only after current Jira/UAC evidence activates one of the routes below. Current Jira/UAC always overrides this learned candidate contract.

## Route 1 - Authoring Viewport Stability

- Activation requires Author view/editing canvas plus an active caret, selection, element, reference insertion, viewport jump, scroll-to-top, or lost editing-location symptom.
- For a long topic with the active caret or selected element deep in the document, typing or pasting must keep the active element visible; the viewport must not jump to the document top or an unrelated section.
- After cross-reference/reference insertion or update, closing the picker must return focus to the intended insertion location and keep it visible.
- Cancelling the picker must restore focus without inserting a reference or mutating surrounding content.
- When layout reflow changes content height, restore relative to the active element rather than an exact pixel offset.
- Repeated typing, paste, insert, update, and cancel operations must retain the intended caret/selection, one correct inserted reference, and unchanged surrounding content.
- Do not automatically add map-tree/outline state, save/reopen, version restore, old/new editor parity, or a performance SLA. Content size is a fixture unless an approved performance oracle exists.
- Evidence of workflow disruption supports repeated-navigation and wrong-location risk. Do not claim data loss unless current evidence establishes mutation or loss.

## Route 2 - Map Preview State Restoration

- Activation requires Map Preview or map-preview-specific state.
- Preserve selected topic, relative scroll location, right-panel/condition state, and applied filtering when switching tabs or returning from Edit during an active session.
- Topic refresh and full-map toolbar refresh must fetch latest content without resetting the selected topic, relative scroll location, or condition state.
- Cover standard maps, bookmaps, and subject schemes only when current UAC names that matrix; references such as topic, DITAVAL, Markdown, and non-DITA assets are likewise evidence-gated.
- Do not inherit Author-canvas caret or reference-picker focus requirements.

## Route 3 - CALS Multi-Column Deletion

- Prepare a 6-row by 5-column CALS table with unique row-column labels.
- Deleting the two selected rightmost columns must leave exactly 6 rows and 3 visible columns.
- No blank ghost column may remain in Author view.
- Source structure must preserve retained cell order/content and contain no orphan `colspec`, `namest`, `nameend`, or other span metadata targeting removed columns.
- Include a valid adjacent span fixture. Do not add `simpletable` or `reltable` parity unless current Jira/UAC names it.

## Route 4 - GUIDES-35437 Large-File Safeguard

- Classify the behavior as configuration-driven working as designed when evidence identifies `largeFileTagCount`.
- Record the effective configuration and test immediately below and at/above its parsed DITA tag-count threshold.
- Verify dirty-state and undo/redo behavior changes at the configured parsed-tag boundary.
- Do not treat 411 table cells as a hard-coded product threshold or defect; cell count is not equivalent to parsed tag count.
- Do not derive a performance SLA from the customer-observed cell count.

## Historical Similarity Boundary

- Map Preview and Authoring viewport issues are different mechanisms by default.
- Shared words such as `scroll`, `editor`, `large`, or `topic` are area-only similarity.
- A cross-surface Jira may qualify only when evidence shows a shared state-restoration mechanism, editor-scroll controller, active-element anchor, or equivalent implementation/root-cause link.

## Exact-UAC Provenance

- Exact historical UAC indexing requires a live Jira source or Jira CSV source with a verified SHA-256 source hash.
- Screenshot-only and pasted examples can teach generic candidate patterns but cannot create an exact Jira/UAC record.
- Re-importing the same hashed CSV must not duplicate learned records.
