# Component-Scoped Reference Routing

Use this file before loading detailed UAC examples. The goal is to load only the evidence rules needed for the Jira's actual component and mechanism.

## Deterministic Order

1. Use a canonical Jira component when the issue supplies one: `Editor`, `Authoring`, `Publishing`, `Platform`, `Schematron`, or `Integration`.
2. If the component is missing, infer it from the accepted UAC first, then the summary, then the description. Record the inference source.
3. Run `scripts/component_reference_router.py` and load only the reference files returned in its `references` list.
4. Treat component, customer, and domain as retrieval/ranking hints. They never prove same-mechanism similarity or expected behaviour.
5. Fall back to `uac-reference-examples.md` only when no focused component pack covers the mechanism or an exact gold/caution reference is required.

## Scope Authority

- The current Jira's latest accepted UAC is the sign-off authority. If it conflicts with an older description, do not merge both scopes.
- Preserve the stale request as context or an Open Question only when it affects QA sign-off.
- A Closed/Duplicate Jira without accepted UAC is candidate history. It may seed Proposed ACs and regression questions, never Confirmed ACs or a verified historical behaviour claim.
- A generic phrase such as `selection should work fine` does not authorize multi-selection, cross-folder selection, or a selection-count contract.
- Area-only overlap is insufficient. Retain a historical Jira only when the mechanism, state transition, API/config key, output transform, DITA entity, or strong failure signature matches.
- Authoring mechanisms currently routed to the focused pack include asset-browser thumbnails, image-picker multi-selection, map-Xref display labels, Map View parent-to-descendant hierarchy selection counts, and Web Editor Explorer filename/title sorting.
- Integration asset CRUD requests route to the focused Integration pack only when API operations are paired with asset/topic payload, metadata, GUID, external-import, or UPSERT evidence. The generic word `API` alone remains insufficient.
- Platform bulk-overwrite/session requests route to the focused Platform pack only when same-name overwrite or re-upload evidence is paired with a batch/asset context and a terminal-state, login redirect, CSRF, loader, or `/bin/fmdita/import` failure signature.

## Token Budget

- Load this routing file plus one focused component pack: `component-authoring.md`, `component-integration.md`, or `component-platform.md` when returned by the router.
- Load an additional pack only when current Jira evidence names a real cross-component dependency.
- Do not load all component packs or the full historical example catalog pre-emptively.
