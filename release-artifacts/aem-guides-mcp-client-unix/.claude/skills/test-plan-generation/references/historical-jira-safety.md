# Historical Jira Evidence Safety

Historical Jira is useful evidence — known behavior, terminology, previous
regression paths, relevant configurations, likely documentation/code
locations — but **similarity to an old ticket never automatically makes that
ticket an authority for the current ticket**. Enforced by
`scripts/historical_jira_safety.py` over the manifest
`historical_jira_assessment` block; extends (never competes with) the
existing historical-evidence path: `temporal_evidence.py`,
`evidence_authority_resolver.py`, the Q1 resolver's non-establishing
`HISTORICAL_JIRA` authority, and `data/authority_policy.json`. Retrieval rank
is discovery metadata, not authority; full retrieval evaluation is a separate
phase and is not implemented here.

Every historical Jira item considered for a material Question is assessed per
Question — never admitted globally to the ticket — with: `history_id`,
`question_id`, `jira_key_or_source_id`, `relationship`, the match dimensions
(`feature_match`, `surface_match`, `version_match`, `configuration_match`,
`failure_mode_match`, `expected_behavior_match`, each
`SAME`/`SIMILAR`/`DIFFERENT`/`UNKNOWN`), `currentness`, `superseded_status`,
`human_accepted_ac_available`, `applicability`, `authority_role`,
`allowed_use`, `reason`, `limitations[]`, and optional `evidence_kind` /
`authority_basis`. Classification never rests on vector similarity or lexical
overlap alone.

## Relationships (`relationship`)

- `AUTHORITATIVE_HISTORY` — very narrow: only when an **existing**
  source-authority rule explicitly permits that historical source to
  establish the claim for the current Question. Requires `authority_basis`
  naming that rule and exact applicability (surface, version, configuration,
  and expected behavior all `SAME`). A historical Human Accepted AC is **not**
  automatically authoritative for a different current ticket. No new
  authority hierarchy is created.
- `SUPPORTING_PRECEDENT` — materially same behavior, applicable surface,
  established version/configuration applicability, no conflict with current
  higher-authority evidence. May contribute; S1 still evaluates the complete
  evidence, and precedent alone never makes a Question SUFFICIENT nor
  overrides current Jira requirements.
- `DISCOVERY_ONLY` — helps locate terminology, sources, configurations,
  regression dimensions, documentation/code paths, or prior investigations.
  Cannot directly establish an Acceptance answer, may trigger further
  authorized research, and never enters final Source lines as acceptance
  authority.
- `NOT_APPLICABLE` — material applicability differs (wrong surface, wrong
  version, Cloud vs 6.5, New vs Old Editor, Native PDF vs DITA-OT, different
  configuration/workflow, customer-specific behavior). Any `DIFFERENT` on
  `surface_match`/`version_match`/`configuration_match` forces
  NOT_APPLICABLE; high semantic similarity must not override it.
- `CONFLICTING_HISTORY` — materially conflicts with current evidence. The
  disagreement is preserved; current higher-authority evidence retains its
  authority; the bound Question routes through existing Q1/S1 conflict/TBD
  behavior (stays CONFLICTED/ACCEPTANCE_TBD/PARTIALLY_ANSWERED, or ANSWERED
  only with the contradictions retained per the Q1 rule).

`allowed_use` must be compatible: `ESTABLISH_ANSWER` (AUTHORITATIVE_HISTORY),
`SUPPORT_ANSWER` (SUPPORTING_PRECEDENT), `DISCOVERY` (DISCOVERY_ONLY),
`NONE` (NOT_APPLICABLE), `CONFLICT_SIGNAL` (CONFLICTING_HISTORY).

## Observation vs requirement

Historical Actual Result stays an observation; historical reproduction steps
stay reproduction evidence; historical suspected root cause stays
investigation. `evidence_kind` of `ACTUAL_RESULT` / `REPRODUCTION` /
`SUSPECTED_ROOT_CAUSE` allows only `DISCOVERY`/`NONE` use and never becomes
`AUTHORITATIVE_HISTORY` — a historical bug's actual result does not establish
that the observed behavior is desired today. Historical Human UAC is never
copied into the current UAC merely because the ticket is similar: each
historical AC binds to a current Question, is assessed for applicability and
allowed use, and keeps its historical source identity.

## Integration

- **S1** — a SUFFICIENT question never rests on DISCOVERY_ONLY /
  NOT_APPLICABLE / CONFLICTING_HISTORY evidence; SUPPORTING_PRECEDENT may
  contribute but never alone establishes.
- **C1** — historical evidence never directly creates a Coverage Decision; it
  reaches coverage only through its bound Question and only as
  AUTHORITATIVE_HISTORY / SUPPORTING_PRECEDENT lineage. A historical
  regression pattern may suggest P1 dimensions, but C1 still decides.
- **E1** — current and historical outcomes are never merged merely for
  similar wording; E1 operates on admitted current Coverage Decisions.
- **L1** — historical evidence reaches AC lineage (and final Source lines)
  only when legitimately admitted; DISCOVERY_ONLY remains auditable outside
  AC lineage, and unused historical Jira never contaminates a Source line.

## Backward compatibility

Absent `historical_jira_assessment` block: clean pass.
