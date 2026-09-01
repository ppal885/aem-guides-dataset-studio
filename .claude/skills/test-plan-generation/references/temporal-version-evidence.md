# Temporal / Version-Aware Evidence (UACFIX-01)

Every material evidence claim must be **version-aware**. Do not mix old
documentation, old implementation, old UI behaviour, historical Jira expectations,
and current product behaviour as if equally applicable. **Authority and recency are
separate dimensions.**

## Record the version context (where available)

On any material evidence record, capture what you know (all optional):
`product`, `product_version`, `build_version`, `deployment`, `cloud_or_onprem`,
`repository`, `branch`, `commit`, `pr`, `document_version`,
`document_publish_date`, `dita_version`, `dita_ot_version`, `valid_from`,
`valid_to`, `customer_version`, `current_jira_version`, `observed_at`.

## Classify temporal applicability (required to opt in)

Set `temporal_applicability` to one of:

- `CURRENTLY_APPLICABLE` — verified against current product/branch.
- `LIKELY_APPLICABLE` — plausibly current, not verified.
- `HISTORICAL_REFERENCE` — old behaviour/doc kept for reasoning, not current proof.
- `VERSION_MISMATCH` — refers to a different version than the one under test.
- `SUPERSEDED` — replaced by newer behaviour (must name `superseded_by`).
- `FUTURE_BEHAVIOR` — planned/unreleased.
- `UNKNOWN_VERSION` — version unknown. **Never silently treated as current.**

## Rules the gate enforces (`scripts/temporal_evidence.py`)

- A material claim with `supports_ac: true` on a **non-current** state
  (`HISTORICAL_REFERENCE`, `VERSION_MISMATCH`, `SUPERSEDED`, `FUTURE_BEHAVIOR`,
  `UNKNOWN_VERSION`) must be dispositioned `OPEN_QUESTION` or
  `NEEDS_CURRENT_VERIFICATION` — it cannot silently become an AC.
- `SUPERSEDED` / `VERSION_MISMATCH` must record `superseded_by` / `conflict_with`
  (preserve BOTH records; never overwrite old evidence).
- A record with `authority_is_normative: true` (e.g. DITA 1.3 spec) must **not** be
  marked `SUPERSEDED` by recency alone — old-but-normative stays authoritative.
- Version conflicts go in `temporal_evidence.version_conflicts[]`, each listing
  `between` (≥2 evidence_ids) and an `applicability`/`disposition` — routed to the
  conflict resolver, not resolved by overwrite.

## Separations to keep

- `PRODUCT_CAPABILITY` vs `CURRENT_UI_REPRESENTATION` — don't discard a behaviour
  because a UI moved (old screenshot / action location != current entry point).
- Publishing: engine/template/renderer/DITA-OT/preset/Cloud-release changes make
  evidence from another version **reference-only** until current applicability is
  verified.
- GitHub: prefer the **current fix branch/PR** for implementation applicability;
  historical implementation must not override current `develop`/fix code. Persist
  `repo`, `branch`, `commit`, `pr`, changed file/symbol.

## Backward compatibility

Absent temporal metadata is a clean pass. Add fields incrementally; the gate only
enforces on records that carry `temporal_applicability` (or an explicit
`temporal_evidence` block).
