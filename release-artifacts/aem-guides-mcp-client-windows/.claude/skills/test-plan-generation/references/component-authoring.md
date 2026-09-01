# Authoring Component UAC Pack

Use this generic pack for current Authoring issues involving topic/map references, asset selection, repository/search surfaces, configuration-driven attributes, or author-facing labels. Current accepted scope and subject-authorized evidence always control activation and exact values. Historical issue keys, customer names, counts, versions, screenshots, and old decisions are regression fixtures only.

## Configuration-Driven Conditional Attribute Discovery and Label Contract

Activate when current evidence names `condAttrList.csv`, a conditional-attribute configuration, dynamically configured attributes, or attribute friendly/display names in an identified surface. Also read [configuration-driven-enumerations.md](configuration-driven-enumerations.md).

- Verify the runtime configuration reader, active DTD/schema or specialization applicability filter, workspace/folder/global profile scope, friendly-name resolver, fallback resolver, and every current-issue rendering consumer as separate links. Do not freeze observed entries into an exhaustive product list.
- Use a canary conditional attribute that is valid for the active schema/profile and absent from inspected hardcoded allowlists. Cover it with and without a friendly-name mapping. A display-label change must not mutate the raw XML attribute name or value.
- Cover built-in and dynamic attributes with and without mappings, plus added, renamed, and removed entries. Preserve unrelated entries and prevent blank, malformed, stale, or duplicate labels.
- Test positive and negative applicability for the actual schema/DTD/specialization and profile gates found in current evidence. Do not invent universal cross-schema or cross-profile availability.
- Require live updates only when accepted evidence defines them. Otherwise expose the supported refresh/reopen/restart boundary as an Open Question.
- Treat a hardcoded product allowlist as a code-review and runtime-canary risk. Promote only the observable configuration-driven contract authorized by current accepted evidence.

## Asset-Browser Thumbnail Contract

Activate only when current accepted scope names thumbnail rendering or a verified current implementation/design shows that change surface.

- Preserve the exact surfaces and media formats named by current evidence. Similar repositories, pickers, search panels, or formats are separate consumers until verified.
- Separate thumbnail rendering, freshness, placeholder fallback, deferred loading, asset selection, and multi-selection. A statement that selection still works does not authorize new multi-selection behavior.
- For versioned assets, verify the approved freshness boundary and visible content identity. Do not infer cache invalidation timing.
- For unsupported or invalid assets, use only the accepted placeholder/error contract. Do not invent a format list or broken-image recovery behavior.
- Words such as `smoothly` or `without jank` establish a UX risk, not a numeric layout, request-count, cache, or latency threshold.
- When accepted scope conflicts with an older description, keep only accepted scope in ACs and disposition the stale request explicitly.

## Map-Xref Display Label Contract

Activate only when current evidence connects a map Xref/reference to display-label or title resolution.

- Keep visible label and destination semantics independent. A label-only change preserves `href`, `format`, `scope`, `type`, and target behavior unless accepted evidence says otherwise.
- Resolve repository-local titles only for the map types and surfaces proved in current evidence. An external URI or `scope="external"` does not inherit repository title lookup without explicit evidence.
- Verify duplicate or similar labels still resolve/open the intended target.
- Ask for the affected surfaces, supported map types, missing/duplicate/conditional-title fallback, and external-reference boundary when unresolved.
- Historical Xref/title similarity may guide retrieval, but a duplicate/closed issue without accepted UAC cannot seed an AC or exact fallback.

## Map View Hierarchy Selection-Count Contract

Activate only when current evidence identifies parent-to-descendant selection expansion or a selected-count state transition in Map View.

- Derive the expected selected-node set, total, node identity rule, supported child types, expanded/collapsed state, and first-interaction precondition from the current issue fixture. Do not import a count, map name, file-type list, or version from another issue.
- Verify the cold first selection and a repeat selection separately. Later self-recovery cannot compensate for an incorrect initial count or checkbox state.
- Compare the expected node set with both visible selection state and the displayed count. A number alone is insufficient.
- Keep Review-task hierarchy, asset-picker multi-selection, generic checkbox behavior, and Map Preview state separate unless current evidence proves a shared mechanism.
- Ask whether repeated references are counted by visible occurrence or asset identity, and whether collapsed or unloaded descendants are included, when those decisions affect the current fixture.
- Treat hierarchy size as test data unless an approved performance contract supplies a workload and oracle.

## SubjectScheme Title Resolution and Enumdefs Performance

Activate only when current evidence names `subjectdef`, Subject Scheme title/navtitle resolution, `enumerationdef`, `SubjectSchemeDocumentHelper`, or `/bin/aem/guides/xmleditor/subjectscheme/enumdefs`.

- Determine title precedence and no-title fallback from current accepted product/DITA evidence; do not copy a historical precedence rule without verification.
- Verify each identified consumer separately. UI similarity does not prove a shared backend execution path.
- Perform the normal performance-risk review. Retain a historical performance contract only when inspected code/API evidence proves the same mechanism or shared execution path and the historical workload/oracle remains applicable to the target environment.
- A retained contract keeps its exact source provenance, current-applicability result, workload, and oracle. Without all of those, performance is conditional and the missing workload/oracle becomes an Open Question; no numeric AC is emitted.
- Record metrics appropriate to the verified risk, but only approved workload and oracle values decide pass/fail.

## Explorer Filename/Title Sorting Contract

Activate only when current evidence identifies Explorer sorting or a display-label-versus-order problem.

- Treat display label, sort key, sort direction, folder default, per-user override, persistence, and feature-flag state as separate state variables.
- Use a dedicated sort action only when current accepted UAC or inspected design/runtime evidence shows it. A historical or static mockup cannot select the interaction for a new issue.
- If a feature flag applies, cover its approved OFF and ON behavior plus first-render state. Keep the flag's configured default separate from the control's default key/direction.
- A static image can prove visible placement and text/icon appearance only. It cannot prove the opened interaction, available keys, direction semantics, precedence, persistence, collation, keyboard behavior, or accessible state.
- Use a dataset whose filename order differs from title order only after current scope confirms those keys. Preserve asset identity and open behavior while labels/order change.
- Expose unresolved flag key/default, OFF-state presentation, activation boundary, key/direction set, control default, precedence, persistence, collation, scope, and accessibility as targeted Open Questions.
- Retain historical sorting evidence only when the same Explorer state transition or shared sorter/configuration path is verified.

## Folder Deletion Contract

Activate only when current evidence identifies folder deletion in a named Guides or Assets surface.

- Verify product version, deployment, surface, role, empty/non-empty state, nested content, checkout/reference guards, confirmation, and terminal result from current evidence.
- File deletion documentation does not prove folder deletion. Assets UI support does not prove a Guides-specific delete action.
- Keep folder deletion, bulk file deletion, multi-folder deletion, restore/trash, soft delete, retention, dependency visualization, and undo as independent scope items.
- Use implementation-backed patterns for permission denial, guarded content, partial/all-or-nothing semantics, refresh, cancellation, retry, and error handling only when the accepted implementation exposes them.
- A successful operation must identify the affected folder and leave unrelated assets unchanged. A failure must not silently remove or orphan content.
- Historical feature requests are product-evolution context only. They cannot prove current support, a fixed bug, or a current AC.
- If release, surface, transaction semantics, or recovery behavior is unresolved, expose it as an Open Question and keep unsupported candidate behavior out of acceptance scope.
