# Scope Applicability (UACFIX-03)

Reasoning may investigate broadly. The **final UAC scope must stay evidence-based
and minimal.** A related surface does not enter scope just because it shares a name.

## Scope states (per candidate)

- `DIRECT_SCOPE` — current Jira, Human requirement, direct affected surface, or verified fix applicability.
- `SHARED_PATH_REGRESSION` — another surface shares the affected implementation/semantic path AND regression is material, but is not the primary customer contract. Keep it distinct from the core contract.
- `REFERENCE_ONLY` — another output/path helps establish correctness but is not being changed. Never auto-promote to an AC.
- `OPTIONAL_REGRESSION` — nice-to-have regression, not part of the accepted contract.
- `OUT_OF_SCOPE` — investigated and excluded (kept in the internal ledger, not necessarily rendered).
- `UNRESOLVED_SCOPE` — shared-path applicability is material but unresolved → becomes an Open Question.

## Per-candidate fields

`candidate_ref`, `scope_status`, `scope_basis`, `scope_evidence_ids`,
`shared_path_evidence`, `customer_contract_relation` (`PRIMARY` / `SECONDARY_SHARED` / `NOT_CONTRACT`),
optional `open_question_ref`, `promotes_ac`.

## The scope-expansion rule (enforced by `scripts/scope_applicability.py`)

Never expand scope based **solely** on: same feature name, same product family,
same metadata name, same DITA element, same output category, a FluffyJaws
neighbouring doc, or a historical Jira analogy. These `scope_basis` values
(`SAME_FEATURE_NAME`, `SAME_PRODUCT_FAMILY`, `SAME_METADATA_NAME`,
`SAME_DITA_ELEMENT`, `SAME_OUTPUT_CATEGORY`, `FLUFFYJAWS_NEIGHBOR_DOC`,
`HISTORICAL_JIRA_ANALOGY`) cannot place a candidate in scope.

An in-scope candidate (`DIRECT_SCOPE` / `SHARED_PATH_REGRESSION`) must use an
applicability basis (`CURRENT_JIRA_AFFECTED_SURFACE`, `HUMAN_REQUIREMENT`,
`VERIFIED_FIX_APPLICABILITY`, `SEMANTIC_APPLICABILITY`, `IMPLEMENTATION_APPLICABILITY`,
`SHARED_IMPLEMENTATION_PATH`, `SHARED_SEMANTIC_PATH`) **and** non-empty
`scope_evidence_ids`.

Other enforced rules:
- **Target surface first.** Final scope must begin from a `DIRECT_SCOPE` candidate
  tied to the `PRIMARY` customer outcome / current Jira affected surface.
- `SHARED_PATH_REGRESSION` requires `shared_path_evidence` and must not be `PRIMARY`
  (keep internal coverage distinct from the core contract).
- `REFERENCE_ONLY` / `OPTIONAL_REGRESSION` must not `promotes_ac`.
- `UNRESOLVED_SCOPE` must carry `open_question_ref` — never silently added to scope.

## Out of Scope language

Keep final OOS concise — render only boundaries that prevent realistic
misunderstanding. The internal ledger retains all rejected/OOS candidates; do not
dump every investigated surface into the plan.

## Backward compatibility

Absent `scope_applicability` is a clean pass. See also
`references/evidence-conflict-resolution.md` and `references/fluffyjaws-evidence.md`.
