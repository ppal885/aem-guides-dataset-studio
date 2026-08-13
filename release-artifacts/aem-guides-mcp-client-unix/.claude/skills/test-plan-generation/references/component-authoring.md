# Authoring Component UAC Pack

Use this focused pack for Authoring Jiras involving topic/map references, asset selection, repository/search surfaces, or author-facing labels. Current Jira/UAC evidence always overrides these historical patterns.

## Asset-Browser Thumbnail Contract — GUIDES-34915

### Evidence Boundary

- The accepted Jira field changed the ticket scope to thumbnail rendering even though the stale description still requested image multi-selection.
- Confirmed scope is limited to valid-image thumbnails in Home Repository content view, Search panel, and Bottom search panel; PNG, JPG, and SVG; latest-image-version freshness; safe placeholder behavior for invalid/unsupported images; and smooth lazy loading without layout jank.
- `Selection of image files should work fine` means existing selection remains functional. It does not prove multi-selection, same-folder-only selection, cross-folder behavior, or a selection limit.
- Post-fix notes about original-image fallback and default multimedia icons are supporting regression evidence unless the current Jira/UAC explicitly adopts them.

### Normalized Acceptance Pattern

- Given a valid PNG, JPG, or SVG asset is visible in a named thumbnail surface | When its result card is rendered | Then the card shows the correct thumbnail and selecting the asset continues to work.
- Given an image has multiple versions | When its thumbnail is fetched after the latest version is available | Then the displayed thumbnail represents that latest version rather than a stale rendition.
- Given an unsupported or invalid image cannot produce a thumbnail | When the result is rendered | Then a stable default placeholder is shown without a broken-image control or broken layout.
- Given enough results require deferred loading | When the user scrolls through the repository/search results | Then thumbnails load lazily without shifting the surrounding result layout.

### Required Boundaries

- Keep Home Repository, Search panel, and Bottom search panel as separate surfaces.
- Keep PNG, JPG, and SVG explicit; do not add formats from memory.
- Do not invent milliseconds, request counts, cache behavior, or a layout-shift threshold from the word `smoothly`.
- Ask whether the original multi-selection request was dropped, deferred, or moved to another Jira only when that answer affects the current plan.

## Map-Xref Display Label Contract — GUIDES-34580

### Trust Boundary

- The Jira is Closed as Duplicate and the supplied record has no accepted UAC. This is a candidate usability pattern, not a verified historical fix.
- Every criterion derived from this record remains `[Proposed]` until the duplicate target or current Jira supplies accepted UAC.

### Proposed Acceptance Pattern

- Given a repository-local DITA map has a map title that differs from its file name | When the map is shown as an Xref reference in the affected authoring surface | Then the visible label uses the resolved map title instead of the file name.
- Given two map references have identical or similar file names but different titles | When both are shown together | Then each reference remains distinguishable by its own resolved title and still opens the intended map.
- Given an existing topic is shown as an Xref | When the map-title change is enabled | Then the topic continues to display its title with no regression to topic-reference selection or rendering.
- Given only the Xref display label changes | When the reference is saved and inspected | Then its destination and source semantics—including `href`, `format`, `scope`, and `type` when present—remain unchanged.
- Given an Xref has `scope="external"` or targets an external URI | When the Xref is displayed, saved, reopened, or activated | Then no repository map-title lookup is applied and the external URI, explicit link text, `scope`, `format`, and open behavior remain unchanged.

### Required Open Questions

- Which exact surfaces are in scope: picker/search result, inserted Author rendering, Properties, Preview, or all of them? QA impact: each surface can use a different title resolver.
- What is the fallback when the map title is empty, unavailable, duplicated, conditional, or unresolved? QA impact: filename/path fallback must be deterministic before automation can assert it.
- Does `MAP` include standard DITA maps only or also bookmaps and specialized map types? QA impact: title extraction differs by map type.
- Which Jira is the duplicate target and what accepted contract did it implement? QA impact: without it, the historical record cannot justify Confirmed ACs or a fixed-version claim.

### Same-Mechanism Retrieval

- Strong matches share map-Xref label resolution, map-title extraction, or a display-label-versus-destination split.
- Reject generic Xref, filename, map, search, or title tickets that do not touch the same display-label mechanism.
- Treat external-link-only URI or navigation defects as boundary evidence, not same-mechanism history, unless they also exercise repository map-title lookup.

## Map View Hierarchy Selection-Count Contract

### Evidence Boundary

- The Hyundai Guides 4.6 reproduction is a cold-state count defect. In an expanded hierarchy whose selected set contains exactly seven tree nodes, selecting `map2` initially shows `1 selected`; clearing/reselecting later shows the correct count. The first selection must immediately show `7 selected`.
- The seven-node total includes the selected map node itself and every descendant node selected by that action. Do not reinterpret the fixture as one parent plus seven children.
- The explicit content matrix is DITA, Markdown, and DITAVAL entries inside the map hierarchy. Preserve those file types as fixtures instead of replacing them with a generic `all assets` claim.
- The issue explicitly establishes an expanded nested-map state, an initial undercount, and subsequent self-recovery. It does not establish the implementation root cause, whether repeated nodes count as visible node occurrences or unique asset identity, or how collapsed/unloaded descendants and partial selection behave.
- This is not the Review-task map-hierarchy contract, asset-picker multi-selection, or a generic checkbox issue. Keep those mechanisms separate unless current Jira evidence connects them.

### Normalized Acceptance Pattern

- Given a fresh Map View session contains the expanded `map2` hierarchy with exactly seven selectable tree nodes including `map2` | When the user selects `map2` for the first time | Then the footer immediately displays `7 selected` and all seven expected nodes are checked without a second selection.
- Given the first-selection result is correct | When the user clears and repeats the same selection | Then every subsequent selection also displays `7 selected`; later self-recovery does not compensate for an incorrect first result.
- Given a supported child entry is DITA, Markdown, or DITAVAL | When it is selected through the parent-map action | Then its file type does not cause the entry to be omitted from or added twice to the selected total.

### Required Boundaries

- Recreate the reported hierarchy with at least three maps and nested map references, then enumerate an expanded `map2` selected set of exactly seven tree nodes including `map2`.
- Reset to a fresh Map View state before the primary assertion; a warm second selection cannot validate this defect.
- Record the expected selected nodes before execution and compare them with both visible checkbox state and the footer count. A number alone is not a sufficient oracle.
- Do not add deselection, indeterminate state, disabled nodes, cycles, lazy loading, pagination, persistence after reopen, or a performance SLA unless the current Jira/UAC names them.
- Treat content volume only as a fixture unless current evidence provides an approved performance contract.

### Required Open Questions

- Are repeated references counted by visible tree occurrence or deduplicated by repository asset identity? QA impact: nested maps can display the same map or topic more than once and produce different valid totals.
- Must collapsed or not-yet-loaded descendants be included on initial selection? QA impact: the expected total depends on whether selection operates on the complete hierarchy model or only rendered nodes.

## SubjectScheme Title Resolution And Enumdefs Performance

Activate only when Jira, code, or API evidence names `subjectdef`, Subject Scheme title/navtitle resolution, `enumerationdef`, `SubjectSchemeDocumentHelper`, or `/bin/aem/guides/xmleditor/subjectscheme/enumdefs`.

### Functional Boundaries

- Resolve `<topicmeta>/<navtitle>` before deprecated `@navtitle`, then preserve the accepted no-title fallback for both `@keys` and `@keyref` paths.
- Verify the Subject Scheme panel and an `enumerationdef`-bound attribute dropdown consume the same resolved title; UI similarity alone does not prove a shared backend path.

### Principal Performance Boundary

- Query and validate `GUIDES-37915` whenever inspected current code or the current API path overlaps SubjectScheme enumdefs/title resolution. That Jira records same-dataset before/after measurement, average/min/max/p90/p95/p99 response metrics, a claimed `2x` gain, and an agreed workload of approximately `200 concurrent users`.
- If current-code/API evidence proves the same mechanism or shared execution path, retain `GUIDES-37915` under `performance_assessment.historical_contracts`, set performance to `required`, and add a Proposed Performance AC plus a mapped benchmark scenario. Do not reduce it to a P2 regression bullet.
- Use the Jira-backed workload and oracle: `200 concurrent users` and at least `2x` p95 response-time improvement versus the recorded before-fix same-dataset baseline. Record p50/p90/p95/p99, throughput, error/timeout rate, CPU, memory, and GC during execution; only the Jira-backed 2x target is the product pass/fail oracle unless another approved threshold is supplied.
- If the current change does not touch the enumdefs request or an inspected shared execution path, classify `GUIDES-37915` as area-only and do not emit its Performance AC.
- Does `DITA` mean topics only, or also DITA maps, bookmaps, and specialized maps? QA impact: the fixture and expected count differ by supported node types.
- Should the UI label remain generic `N selected` for mixed file types, or name maps/items? QA impact: automation needs the accepted accessible label and noun.

### Same-Mechanism Retrieval

- Strong matches share Map View tree-selection aggregation, parent-to-descendant selection expansion, or stale/off-by-one selected counters on the first interaction.
- Give highest weight to first-selection undercount followed by correct subsequent selection in an expanded nested-map hierarchy.
- Reject Review-task hierarchy, generic list selection, asset picker, map preview scroll, or map tree rendering tickets without the same selection-count state transition.

## Explorer Filename/Title Sorting Contract — GUIDES-41093

### Evidence Boundary

- The supplied Red Hat record describes a pre-development enhancement. Engineering confirmed the current behavior is working as designed: `User Preferences → Display → File/Folder listing` changes the visible label, while Explorer order continues to use the folder-level AEM Assets sort configuration.
- The supplied Explorer mockup resolves the UI direction to a dedicated sort affordance in the Explorer header, positioned to the right of Search and Add and separated from them by a divider. Treat sorting as independent from the display-label preference; do not retain implicit display-preference coupling as the selected design.
- The static mockup does not show the opened control, available sort keys, direction choices, selected/default state, persistence, or runtime behavior. Those details remain unresolved and every derived behavioral criterion remains Proposed until accepted UAC or inspected interactive design evidence confirms them.
- Feature-flag coverage must include OFF, ON, and first-render default state. The supplied evidence does not provide the flag key, its configured default value, the OFF-state presentation, or the button's initial key/direction, so do not invent any of them.
- Treat display label, sort key, sort direction, folder default, and per-user override as separate state. A label change alone does not prove an order change.
- `Home → Repository` is the documented workaround and comparison surface. It does not prove that Explorer must inherit every Repository-table control or sorting rule.

### Mockup-Backed Proposed Pattern

- Given Explorer is displayed | When the header actions render | Then a dedicated sort action is available beside Search and Add without replacing either action or the row-level overflow menu.
- Given a folder whose file-name order differs from its title order | When the user chooses an approved key and direction through the dedicated sort action | Then visible items are ordered by that key/direction and continue to display the configured label without changing asset identity or open behavior.
- Given the display preference changes between `File name` and `Title` | When Explorer rerenders | Then the visible label follows that preference while the active sort state changes only through the dedicated sort contract.
- Given the folder-level Assets sort differs from an active user override | When Explorer reloads within the accepted persistence boundary | Then precedence follows the approved folder-default-versus-user-override contract.

### Feature-Flag and Default-State Matrix

- `[Proposed]` Given the feature flag is OFF | When Explorer renders | Then legacy Explorer label and ordering behavior remain unchanged and the new sorting behavior cannot be invoked; whether the sort button is hidden, omitted, or disabled requires accepted evidence.
- `[Proposed]` Given the feature flag is ON | When Explorer renders for the first time | Then the dedicated sort action is available beside Search and Add, and its visible/enabled/selected state plus the actual item order agree with the approved default sort key and direction.
- `[Proposed]` Given the feature flag is ON and the user has not selected a sort option | When the control is inspected by mouse, keyboard, and assistive technology | Then icon, tooltip, accessible name, state announcement, and item order describe one consistent default; an upward arrow in a static mockup is not proof of ascending order.
- `[Proposed]` Given the feature flag value changes | When the documented cache, session, or service-reload boundary completes | Then Explorer shows one coherent OFF or ON behavior without a stale control paired with legacy ordering, or a hidden control paired with an active override.
- Keep the feature flag's configured default value separate from the sort button's first-render default state. Both require explicit verification.

### Required Open Questions

- What is the exact feature-flag key, its default value, rollout scope, and activation boundary? QA impact: OFF/ON setup and backward-compatibility expectations cannot otherwise be reproduced.
- With the flag OFF, is the sort button hidden, omitted, or visible-but-disabled? QA impact: visual, keyboard, and automation expectations differ for each contract.
- With the flag ON, what exact key/direction is selected by default, and what visible and accessible state represents it? QA impact: the first-render order and button-state oracle remain undefined.
- Does the header action open a menu, cycle through states, or use another interaction? QA impact: the activation and automation contract cannot be inferred from a static icon.
- Which keys are available: file name, title, or additional fields? QA impact: each key requires a dataset whose orders differ.
- Does the upward arrow show the current ascending state, the next action, or a non-stateful icon; how is descending selected and announced? QA impact: direction and accessibility assertions otherwise remain ambiguous.
- Is the folder-level Assets configuration only the initial default, and when exactly does a user override win? QA impact: the expected order cannot be asserted without precedence.
- What is the override lifetime: current folder, navigation within Explorer, editor reload, browser session, or future login? QA impact: each boundary needs a different persistence scenario.
- What are the collation rules for case, locale, numbers, duplicate labels, folders-first behavior, and tie-breaking? QA impact: ambiguous datasets can otherwise produce multiple valid orders.
- Is scope limited to Web Editor Explorer, or also Collections, Home Repository, search results, and asset pickers? QA impact: generic repository/file-browser similarity is insufficient.
- What are the action's accessible name, tooltip, focus order, keyboard activation, and selected-state announcement? QA impact: the icon alone does not define an accessible interaction.

### Same-Mechanism Retrieval

- Strong matches share Explorer tree/list sort-key selection, display-label-versus-sort decoupling, or folder-level default versus per-user override precedence.
- Reject generic repository ordering, Collections sorting, search relevance, map-tree selection, Xref display labels, or filename/title tickets without the same Explorer sorting mechanism.


## Folder Deletion Release-Evolution Contract - GUIDES-19345

### Evidence Boundary

- `GUIDES-19345` is an open historical feature request, not accepted UAC and not proof of an implemented Guides folder-delete workflow.
- Jira comments from August 2024 through April 2025 state that folder and bulk-file deletion were not available in Guides Editor; users were directed to AEM Assets UI. A proposed custom extension that opens Assets UI or calls an API is a workaround, not product behavior.
- The customer's broader request also mentioned multiple-file deletion, a dependency popup, and restore/trash behavior. Keep each as an independent scope item. Folder deletion evidence does not imply bulk deletion or restore.
- The current official `Manage files and folders` page, updated July 28, 2026, documents governed **file deletion** from the AEM repository. It identifies administrator permissions, checked-out files, and incoming/outgoing references as deletion controls. It does not, by itself, prove that Guides Editor now supports deleting a selected folder.
- Always verify the target product version, hosting model, and surface: Guides Home Repository, Web Editor Explorer, or AEM Assets UI. Current documentation can supersede historical availability, but only for the behavior and surface it explicitly documents.
- Never turn the Jira request into Confirmed acceptance criteria unless current Jira/UAC, inspected implementation, or exact official documentation proves the selected folder-delete behavior.

### Proposed Acceptance Pattern

Use only after implementation scope confirms folder deletion in the named Guides surface.

- Given an authorized user selects an empty folder | When the user invokes the approved delete action and confirms it | Then the folder is removed once, the parent listing refreshes, and no unrelated asset changes.
- Given a selected folder contains files or nested folders | When deletion is requested | Then the UI reports the complete deletion scope before mutation and follows the accepted all-or-nothing or partial-failure contract without silently orphaning content.
- Given content inside the folder is checked out or has incoming/outgoing references | When deletion is requested | Then configured permission and reference guards are enforced, and the result identifies blocked content or an explicitly authorized force-delete path.
- Given the user lacks delete privileges | When the folder is selected | Then deletion cannot be completed and the UI returns an actionable authorization result without removing content.
- Given deletion succeeds or fails | When the operation reaches a terminal state | Then the affected surface refreshes once and reports a deterministic outcome; repeated clicks must not create duplicate delete requests.
- Given file deletion remains supported through Assets UI | When a Guides folder-delete change is enabled | Then the existing Assets UI path and documented file-level restrictions remain unchanged.

### Scope Guards

- Test empty and non-empty folders, nested folders, mixed DITA/non-DITA contents, checked-out descendants, incoming references, outgoing references, permission groups, cancellation, and server failure only when the accepted implementation exposes those paths.
- Do not infer restore, trash, soft delete, retention period, undo, dependency visualization, multi-folder deletion, or bulk-file deletion from this Jira. Each requires explicit accepted evidence.
- Do not use the current file-deletion documentation as proof of folder deletion or of a Guides-specific delete button.
- Do not claim data loss, reference cleanup, asynchronous processing, or a performance SLA without current evidence.
- If the release/surface cannot be verified, keep the plan in degraded mode and label all folder-delete criteria `[Proposed]`.

### Same-Mechanism Retrieval

- Strong matches share folder deletion in the same Guides surface plus permission, checkout, reference-integrity, or nested-content handling.
- Treat Assets UI file deletion as boundary/comparison evidence, not same-mechanism proof of Guides folder deletion.
- Reject create-folder, folder sorting, move/copy, generic file deletion, repository search, and trash/restore tickets unless they exercise the same folder-delete transaction.
- Historical `GUIDES-19345` may appear under Past Jiras as product-evolution context; it must not be presented as a fixed bug or current support statement.
