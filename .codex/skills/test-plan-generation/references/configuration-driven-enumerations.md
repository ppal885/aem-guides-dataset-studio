# Configuration-Driven Enumeration UAC

Read this reference when product behavior enumerates attributes, elements, labels, actions, formats, providers, metadata fields, or other UI choices from configuration. Relevant sources include repository/profile files and services such as CSV, XML, JSON, OSGi, or UI configuration. `/libs/fmdita/config/condAttrList.csv` is one example, not a special-case rule.

## Evidence Boundary

- A screenshot or repository view proves only the values and path observed in that environment. It does not establish the authoritative source, overlay precedence, deployment scope, cache/reload lifecycle, schema applicability, or a closed list of all supported values.
- Inspect the effective configuration source and every consumer. Compare configured entries with hardcoded arrays, enums, switch branches, label maps, validation lists, caches, and automation fixtures. A configured value missing from a consumer is a concrete extensibility risk.
- Keep configuration-derived behavior `[Proposed]` unless accepted Jira/UAC confirms it. Code or UI evidence may ground current behavior and regression risk, but it does not upgrade derived scope to `[Confirmed]`.
- Distinguish membership from presentation. One mechanism may decide that an entry exists, another whether it is valid for the active schema/profile/element, and another which friendly or fallback label is displayed.

## Minimum Coverage Matrix

- Existing entry with a configured friendly/display name: it remains discoverable and every in-scope surface renders the mapped label without changing the stored key or value.
- Newly added valid entry with a configured friendly/display name: after the supported configuration activation or reload boundary, it becomes discoverable in every applicable consumer without a product-code change.
- Newly added valid entry without a mapping: it uses the approved fallback. Preserve an exact built-in default label when one exists; otherwise use the exact raw identifier. Never emit a blank, malformed, title-cased guess, or stale label.
- Mapping add, edit, and removal: every already-rendered and newly opened in-scope surface converges at the supported refresh boundary, and removal returns to the approved fallback.
- Applicability boundary: an entry present in the global/effective list but disallowed by the active DTD/schema, element, profile, permission, or deployment scope is not incorrectly offered or applied. Do not misclassify this absence as failed configuration discovery.
- Preservation: adding, editing, removing, or reordering one configured entry does not remove, rename, duplicate, reorder, or change the stored semantics of unrelated existing entries unless the accepted contract explicitly says it should.
- Invalid input: cover blank, malformed, unsupported, duplicate, case-variant, and conflicting-overlay entries using the product's accepted reject/ignore/error contract. If that contract is unknown, keep the outcome in `Open Questions` with QA impact rather than inventing it.
- Lifecycle: test the documented activation boundary, such as profile reselect, panel reopen, editor reopen, cache refresh, service restart, or deployment. Do not promise hot reload from a static screenshot or config file alone.
- Upgrade and rollback when relevant: retain supported custom entries across upgrade, preserve new defaults, and restore the previous effective list and labels when the customization is removed.

## Acceptance-Criteria Rules

- Write separate observable outcomes for dynamic membership, mapped display, unmapped fallback, and applicability when they can fail independently.
- Name the exact configuration key/path only when evidence establishes it for the target deployment. Otherwise name the effective configuration source and keep path/precedence as an Open Question.
- Do not enumerate only today's built-in values as though they were exhaustive. Use one representative built-in matrix plus at least one additional valid configured entry.
- State the surfaces supported by evidence, such as an attribute dropdown, applied-attribute row, Full Tags view, or Condition Attributes panel. Do not claim parity for an uninspected consumer.
- Express the product outcome as configuration-driven discoverability. Put removal of a hardcoded allowlist, cache implementation, listener choice, or data structure under `Code Touched`, `Regression Areas`, or `Open Questions` unless accepted UAC explicitly requires that implementation contract.

## Evidence And Automation Probes

- Search by the exact config path/key, configured values, label/friendly-name API, parsing/loading symbol, cache or change event, schema/DTD applicability check, and every rendering consumer.
- Prepare a temporary, valid custom entry whose identifier is absent from defaults, plus mapped and unmapped variants. Use an applicable schema/profile fixture and a deliberately non-applicable fixture.
- Assert both presentation and identity: visible label, selector/list presence, applied-row label, stored raw attribute/key/value, and save/reopen behavior when persistence is in scope.
- Make automation restore the original configuration in cleanup, refresh through the supported lifecycle, and assert unrelated entries remain intact. Never mutate a shared production configuration for a repeatable test.

## Required Open Questions When Evidence Is Missing

- What is the authoritative configuration source, overlay/precedence order, and deployment/profile scope? QA impact: this determines where the fixture must be installed and which value should win in conflicts.
- What activation or cache-refresh boundary is supported? QA impact: this determines whether live-update, panel-reopen, editor-reopen, restart, or deployment scenarios are valid.
- What makes an added entry valid, and which DTD/schema/element/profile restrictions apply? QA impact: this separates discovery failures from expected non-applicability.
- What are the exact fallback, ordering, duplicate, case-sensitivity, malformed-input, removal, upgrade, and rollback contracts? QA impact: each answer changes pass/fail oracles and the required negative matrix.
