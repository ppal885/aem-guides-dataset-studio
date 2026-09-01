# Authoring State and Structural UAC Contract

Use this generic relationship reference only after current Jira/UAC evidence activates one of the routes below. It supplies investigation dimensions, not pre-approved AC text or historical fixture values.

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
- Enumerate only the preview state named by current scope, such as selected topic, relative scroll location, panel state, or applied filtering. Preserve each named state across only the transitions authorized by current evidence.
- Include topic refresh, full-map refresh, tab switching, or Edit-return only when current scope names the transition or verified code proves the same state owner/consumer path.
- Cover standard maps, bookmaps, and subject schemes only when current UAC names that matrix; references such as topic, DITAVAL, Markdown, and non-DITA assets are likewise evidence-gated.
- Do not inherit Author-canvas caret or reference-picker focus requirements.

## Route 3 - CALS Multi-Column Deletion

- Derive the starting row/column count and selected-column set from current evidence; use unique cell labels so the expected retained structure is explicit.
- Deleting selected columns must preserve the original row count and reduce the visible column count by exactly the number of distinct columns deleted.
- No blank ghost column may remain in Author view.
- Source structure must preserve retained cell order/content and contain no orphan `colspec`, `namest`, `nameend`, or other span metadata targeting removed columns.
- Include adjacent/crossing span fixtures only when current evidence or inspected branch behavior makes span handling applicable. Do not add `simpletable` or `reltable` parity unless current Jira/UAC names it.

## Route 4 - Configuration-Driven Large-File Safeguard

- Classify the behavior as configuration-driven working as designed when evidence identifies `largeFileTagCount`.
- Record the effective configuration and test immediately below and at/above its parsed DITA tag-count threshold.
- Verify dirty-state and undo/redo behavior changes at the configured parsed-tag boundary.
- Do not treat an observed table-cell, UI-item, or file count as a hard-coded product threshold or defect; those counts are not equivalent to parsed tag count.
- Do not derive a performance SLA from the customer-observed cell count.

## Historical Similarity Boundary

- Map Preview and Authoring viewport issues are different mechanisms by default.
- Shared words such as `scroll`, `editor`, `large`, or `topic` are area-only similarity.
- A cross-surface Jira may qualify only when evidence shows a shared state-restoration mechanism, editor-scroll controller, active-element anchor, or equivalent implementation/root-cause link.

## Exact-UAC Provenance

- Exact historical UAC indexing requires a live Jira source or Jira CSV source with a verified SHA-256 source hash.
- Screenshot-only and pasted examples can teach generic candidate patterns but cannot create an exact Jira/UAC record.
- Re-importing the same hashed CSV must not duplicate learned records.
