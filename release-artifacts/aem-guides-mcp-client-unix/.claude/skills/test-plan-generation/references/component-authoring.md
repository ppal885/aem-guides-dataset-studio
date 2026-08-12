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

- Given a DITA map has a map title that differs from its file name | When the map is shown as an Xref reference in the affected authoring surface | Then the visible label uses the resolved map title instead of the file name.
- Given two map references have identical or similar file names but different titles | When both are shown together | Then each reference remains distinguishable by its own resolved title and still opens the intended map.
- Given an existing topic is shown as an Xref | When the map-title change is enabled | Then the topic continues to display its title with no regression to topic-reference selection or rendering.
- Given only the Xref display label changes | When the reference is saved and inspected | Then its destination and source semantics—including `href`, `format`, `scope`, and `type` when present—remain unchanged.

### Required Open Questions

- Which exact surfaces are in scope: picker/search result, inserted Author rendering, Properties, Preview, or all of them? QA impact: each surface can use a different title resolver.
- What is the fallback when the map title is empty, unavailable, duplicated, conditional, or unresolved? QA impact: filename/path fallback must be deterministic before automation can assert it.
- Does `MAP` include standard DITA maps only or also bookmaps and specialized map types? QA impact: title extraction differs by map type.
- Which Jira is the duplicate target and what accepted contract did it implement? QA impact: without it, the historical record cannot justify Confirmed ACs or a fixed-version claim.

### Same-Mechanism Retrieval

- Strong matches share map-Xref label resolution, map-title extraction, or a display-label-versus-destination split.
- Reject generic Xref, filename, map, search, or title tickets that do not touch the same display-label mechanism.
