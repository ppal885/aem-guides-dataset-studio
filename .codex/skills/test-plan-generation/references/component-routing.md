# Component-Scoped Reference Routing

Use this file before loading a generic component contract. The goal is to load only the evidence rules needed for the current issue's actual component and mechanism.

## Deterministic Order

1. Use a canonical Jira component when the issue supplies one: `Editor`, `Authoring`, `Publishing`, `Platform`, `Schematron`, or `Integration`.
2. If the component is missing, infer it from the accepted UAC first, then the summary, then the description. Record the inference source.
3. Run `scripts/component_reference_router.py` and load only the generic reference files returned in its `references` list.
4. Treat component, customer, and domain as retrieval/ranking hints. They never prove same-mechanism similarity or expected behaviour.
5. When no focused pack covers the mechanism, continue with the canonical domain/graph pipeline and record the missing focused pack. Do not load a historical-example catalog as a production fallback.

## Scope Authority

- The current Jira's latest accepted UAC is the sign-off authority. If it conflicts with an older description, do not merge both scopes.
- Preserve the stale request as context or an Open Question only when it affects QA sign-off.
- A Closed/Duplicate Jira without accepted UAC is candidate retrieval evidence. It may seed a hypothesis or regression question only after same-mechanism verification; it never directly seeds an AC or verified historical behaviour claim.
- A generic phrase such as `selection should work fine` does not authorize multi-selection, cross-folder selection, or a selection-count contract.
- Area-only overlap is insufficient. Retain a historical Jira only when the mechanism, state transition, API/config key, output transform, DITA entity, or strong failure signature matches.
- Historical issue keys, customer names, observed counts, and old release values are not routing predicates. A retained historical fact can affect a plan only after subject-specific authority, current applicability, and exact source provenance are verified.
- Authoring mechanisms currently routed to the focused pack include asset-browser thumbnails, image-picker multi-selection, map-Xref display labels, Map View parent-to-descendant hierarchy selection counts, and Web Editor Explorer filename/title sorting.
- Integration asset CRUD requests route to the focused Integration pack only when API operations are paired with asset/topic payload, metadata, GUID, external-import, or UPSERT evidence. The generic word `API` alone remains insufficient.
- Platform bulk-overwrite/session requests route to the focused Platform pack only when same-name overwrite or re-upload evidence is paired with a batch/asset context and a terminal-state, login redirect, CSRF, loader, or `/bin/fmdita/import` failure signature.

## Token Budget

- Load this routing file plus one focused component pack: `component-authoring.md`, `component-integration.md`, or `component-platform.md` when returned by the router.
- Load an additional pack only when current Jira evidence names a real cross-component dependency.
- Do not load all component packs or any historical example catalog during production plan generation. Historical catalogs are regression/evaluation fixtures only.
