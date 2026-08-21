# Coverage Hypotheses & Explorers — Procedure

Read and apply this after building the Phase-2 BehaviorModel, whenever the model
surfaces a dimension that may need investigation. Its job is to turn technical
signals into **investigation candidates**, never directly into test cases.

## Iron rule

```
technical evidence  ->  potential missing dimension  ->  INVESTIGATION_CANDIDATE
```

NOT `AI thinks it may matter -> add a test`. A candidate must be explored and
verified (Prompt 4 HypothesisVerifier) before it can influence an AC. Do **not**
create an Acceptance Criterion in this stage.

## CoverageHypothesis record (manifest `coverage_hypotheses` list)

```json
{
  "hypothesis_id": "H-01",
  "dimension": "CONSUMER",
  "candidate": "the report view also reads the same TOC model",
  "reason": "same model is produced once and read by more than one surface",
  "technical_basis": ["behavior_model.consumers lists two surfaces", "shared service X"],
  "current_evidence": ["E3"],
  "activated_patterns": ["shared-consumer/state"],
  "status": "INVESTIGATION_CANDIDATE",
  "requires_more_evidence": true,
  "confidence": 0.4,
  "equivalence_key": ""
}
```

`run_gates.py` validates the block when present (backward-compatible): every
hypothesis needs a `dimension` from the vocabulary, a `candidate`, a `reason`, and
a non-empty `technical_basis` (no speculation), and the set must already be
collapsed (no equivalent duplicates — `equivalence_key` marks a family that one
representative covers).

## Dimensions (activate only those the BehaviorModel supports)

`CONTRACT_BOUNDARY`, `CONSUMER`, `CONSUMER_POLICY`, `STATE_PARTITION`,
`TYPE_ABSTRACTION`, `REFERENCE_ARTIFACT`, `DITA_SEMANTIC_DEPENDENCY`, `LIFECYCLE`,
`CONFIGURATION`, `PUBLISHING_MODE`, `NFR_RISK`, `BACKWARD_COMPATIBILITY`,
`DOWNSTREAM_REGRESSION`. Do **not** run every dimension for every Jira; each
activation must be justified from a behavior fact / code path / config branch /
consumer / spec relationship / scale signal.

## Explorers (generic reasoning — discover, do not hardcode)

- **A. Contract Boundary** — classify each major Jira entity as `CONTRACT_BOUNDARY`,
  `REPRODUCTION_EXAMPLE`, `SPECIAL_CASE`, `IMPLEMENTATION_DETAIL`, or `UNKNOWN`. Ask:
  *is the thing shown in Jira the real behavior domain, or just the reproduction
  example?* Search implementation for the enum/interface/superclass/generic
  model/shared service the example belongs to. Do not hardcode any specific type.
- **B. Consumer Surface** — when behavior is produced once but consumed by several
  workflows/surfaces (same API / model / utility / persisted state / service /
  transformed output), each discovered consumer is a candidate, not proof; verify
  it actually uses the affected path.
- **C. Consumer-Specific Policy** — do not assume same entity = same behavior
  everywhere. Model per-consumer policy (`INCLUDE`/`EXCLUDE`/`PROCESS`/`SKIP`/
  `HIDE`/`SHOW_OPTIONALLY`/`UNCHANGED`/`UNKNOWN`). Do not hardcode specific consumers.
- **D. State / Partition** — investigate meaningful state alternatives
  (bound/unbound, configured/unconfigured, enabled/disabled, new/existing,
  resolved/unresolved, explicit/fallback, direct/indirect, local/inherited,
  present/absent) **only** when evidence suggests the state changes a code path,
  semantics, output, data shape, persistence, fallback, or regression behavior. Do
  not auto-create every inverse.
- **E. Type / Reference / Artifact** — for generic/polymorphic handling, identify
  the abstraction, its concrete supported members, which members reach the affected
  path, and distinct vs equivalent paths; collapse equivalent paths (do not emit one
  test per enum member). Discover reference/artifact types dynamically from
  implementation/spec, never a hardcoded list.
- **F. Lifecycle** — where applicable investigate CREATE/READ/UPDATE/SAVE/REOPEN/
  COPY/MOVE/RENAME/DELETE/RESTORE/PUBLISH, guided by the BehaviorModel's state
  paths — not every operation blindly.
- **G. NFR Risk** — do not require the word "performance". Look for technical
  signals: large hierarchy, many references, large collection, bulk operation,
  recursive traversal, per-reference processing, large payload, repeated repository
  lookups, browser rendering, async backlog, historical scale defect,
  customer-scale content. When justified, emit a `NFR_RISK` candidate to verify with
  representative large content. Never invent an SLA/threshold.
- **H. Generic DITA Semantic Relationship** — the exemplar; follow
  `references/dita-semantic-relationship-explorer.md`. Dynamically discover
  controlling/dependent/inheritance/fallback/precedence/reference/structural/
  processing relationships from indexed DITA 1.2/1.3, DITA-OT, AEM Guides docs, and
  current implementation. Each relation needs evidence; preserve which DITA version
  supports each conclusion; never hardcode attribute pairs (`if navtitle:
  add_locktitle()` is banned and enforced by `scripts/anti_hardcoding_audit.py`).

## Output of this stage

Every explorer produces `INVESTIGATION_CANDIDATE`s (or references existing verified
evidence). Record them in `coverage_hypotheses`. Do **not** generate final UAC here.
Collapse behaviorally equivalent candidates. Irrelevant dimensions simply do not
activate — an empty/absent set is valid when the BehaviorModel supports no candidate.
