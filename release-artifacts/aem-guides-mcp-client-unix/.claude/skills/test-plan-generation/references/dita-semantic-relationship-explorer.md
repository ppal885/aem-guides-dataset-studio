# DITA Semantic Dependency Explorer — Procedure

Read and apply this file whenever the normalized behaviour model shows that the
expected behaviour is **governed by DITA semantics** — not only when a ticket
names a DITA element. Its single objective:

> Given any affected DITA construct, reconstruct the semantic neighbourhood from
> authoritative evidence and investigate only the relationships that materially
> affect the reported behaviour — **before** declaring test coverage complete.

This is the fix for a specific, recurring failure: the plan recognises the
construct a Jira names (say `navtitle`) but never investigates the *other*
constructs that control, inherit into, resolve, filter, or override its
processing (say `@locktitle`, the title-resolution precedence chain, or `@href`
presence). Coverage then silently misses the branch that actually breaks.

## Hard anti-hardcoding rule (read first)

The explorer is a **discovery procedure driven by evidence**, never a table of
construct pairs. The following are PROHIBITED in production prompts or code:

```python
if navtitle: test_locktitle()      # ticket-specific hardcoding — banned
if keyref:   test_keyscope()       # banned
RULES = {"conref": "conkeyref"}    # a construct->construct truth table — banned
```

Every controlling/dependent construct must be **discovered from spec / product /
code evidence at run time**. The `navtitle -> locktitle` relationship may appear
only as an illustrative example (like below) or inside a regression test —
never as a live production mapping. `scripts/anti_hardcoding_audit.py` enforces
this and runs inside `run_gates.py`. A relation derived dynamically from an
indexed spec/semantic index is acceptable **only** if its provenance (authority
layer + evidence quote/probe + DITA version) is preserved on the record.

## 1. Activation

Activate when the behaviour model indicates DITA-semantic governance. Triggers
include: DITA element or attribute behaviour, reference resolution, key
resolution, conref resolution, title resolution, filtering / conditional
processing, metadata processing, `processing-role`, map/topic hierarchy, or
publishing behaviour derived from DITA structure.

Do **not** activate for UI-only or backend-only tickets with no DITA-semantic
contract (a login dialog bug, a REST pagination bug, a JCR lock timeout).

When active, set `dita_semantics.active: true` in the evidence manifest and
populate the block described in §7 so the Semantic Coverage Gate can run.

## 2. Identify the primary construct(s)

Extract the primary DITA constructs the Jira is actually about. A construct may be
an ELEMENT, ATTRIBUTE, REFERENCE, RELATIONSHIP, STRUCTURAL_ROLE, or
PROCESSING_SEMANTIC. Do **not** assume the Jira-named construct is the complete
semantic contract — it is the entry point, not the boundary.

## 3. Build the semantic neighbourhood (model)

For each primary construct, retrieve governing semantics from, in order:
DITA spec (the version that applies), DITA-OT docs when processing behaviour is
relevant, AEM Guides product docs, current product implementation, historical
Jira, and existing automation. Then assemble a neighbourhood record:

```json
{
  "primary_construct": "navtitle",
  "construct_type": "ATTRIBUTE",
  "controlling_constructs": [], "dependent_constructs": [],
  "parent_dependencies": [], "child_dependencies": [],
  "reference_dependencies": [], "resolution_dependencies": [],
  "inheritance_dependencies": [], "fallback_dependencies": [],
  "precedence_dependencies": [], "processing_dependencies": [],
  "structural_dependencies": [], "filtering_dependencies": [],
  "validity_constraints": [], "related_product_behavior": [],
  "evidence": []
}
```

Rule: **do not populate a relation because two constructs sit near each other in
the spec.** Each dependency needs its own semantic evidence. `scripts/
semantic_relationship_explorer.py` builds this record from relation inputs and
rejects any material relation lacking evidence, an authority layer, or a version.

## 4. Relation vocabulary

Use the smallest correct vocabulary (implemented in `RELATION_TYPES`):
`CONTROLS`, `CHANGES_PROCESSING_OF`, `OVERRIDES`, `FALLS_BACK_TO`,
`INHERITS_FROM`, `RESOLVES_FROM`, `REQUIRES`, `OPTIONALLY_USES`, `EXCLUDES`,
`FILTERED_BY`, `SCOPED_BY`, `TARGETS`, `REFERENCES`, `CONTAINS`, `SPECIALIZES`,
`DERIVES_FROM`, `AFFECTS_OUTPUT_OF`. Read each edge as
`<source> <RELATION> <target>`. Do not create an edge just because two constructs
share a spec section — verify the relationship holds.

## 5. Controlling-attribute & fallback/precedence discovery

For every primary construct, ask (and only keep answers backed by evidence):
- Which attributes change how this value is interpreted or whether it is
  authoritative? (`CONTROLS`, `OVERRIDES`)
- Which parent attributes affect it through inheritance? (`INHERITS_FROM`)
- Which child/sibling elements provide an alternate source? (`FALLS_BACK_TO`,
  `RESOLVES_FROM`)
- Does `@href` / `@keyref` / `@conref` presence change processing?
  (`CHANGES_PROCESSING_OF`, `REQUIRES`)
- Which attributes decide whether it is processed at all? (`FILTERED_BY`,
  `processing-role`)

**Fallback/precedence is mandatory** whenever output depends on ordered sources.
Model it explicitly and generate coverage for each *distinct* precedence branch:

```json
{
  "behavior": "navigation title resolution",
  "candidate_sources": ["map-provided navtitle", "referenced topic title", "fallback"],
  "precedence_order": [], "conditions": [], "evidence": [], "unknowns": []
}
```

## 6. Value-state partitions (semantic states)

For every verified dependency, determine the value-states that create *distinct*
behaviour. Beyond the generic partitions the plan already uses
(present/absent, configured/unconfigured, enabled/disabled), add DITA-controlled
semantic states such as: `locked / unlocked`, `explicit / inherited`,
`local / referenced`, `resolved / fallback`, `direct / indirect`,
`processing enabled / resource-only`. A state is a coverage candidate **only**
when it changes the processing path, effective value, resolution, resulting
structure, generated output, persistence, or a known regression. Do not test all
values by default.

## 7. Dependency-chain reasoning (worked example — illustrative only)

Continue past the first related attribute until the effective behavioural branch
is understood or becomes unresolved; bound exploration to materially relevant
hops. Example reasoning trace for the New AEM Sites navigation-title issue
(this is an **example**, not a production rule):

```
topicref  ->  navtitle participates in navigation-title resolution
          ->  DITA semantics indicate a control affects title usage
          ->  @locktitle discovered (CONTROLS)
          ->  distinct title-resolution paths exist
          ->  @href present vs absent changes the source (CHANGES_PROCESSING_OF)
```

Then ask, and retrieve answers for: how does New AEM Sites render a locked
map-provided navigation title? an unlocked href-based title? a navtitle-only
topicref with no href? If the no-href + `locktitle=no/absent` behaviour cannot be
proven from spec/product/code, it is **UNRESOLVED -> Open Question** — never
invent the expected result.

Meaningful states here are a small set, not the Cartesian product:
`href present/absent` × `navtitle present/absent` × `locktitle yes/no/absent`
collapses to the few branches DITA/product/code evidence proves distinct.

## 8. Coverage hypotheses, not tests

Do **not** convert a discovered relationship directly into an AC. Emit a
hypothesis and run it through the existing workflow —
`Hypothesis -> Exploration -> Reasoning-directed retrieval -> Verification`:

```json
{
  "dimension": "DITA_SEMANTIC_DEPENDENCY",
  "primary_construct": "navtitle", "dependent_construct": "locktitle",
  "relationship": "CONTROLS", "behavioral_branch": "locked vs unlocked title source",
  "reason": "", "evidence": [], "status": "INVESTIGATION_CANDIDATE"
}
```

Allowed terminal statuses: `CONFIRMED`, `INFERRED_HIGH_CONFIDENCE`, `REJECTED`,
`UNRESOLVED`. Reasoning-directed retrieval should target the DITA 1.2/1.3 spec,
DITA-OT docs where applicable, Experience League, the current repository,
existing automation, and historical Jira — with the exact construct/attribute
names in the probe, per `references/dita-spec-evidence.md`.

## 9. Cartesian-explosion protection

A construct may have several related attributes. Do **not** produce
`A × B × C × D`. Before splitting into separate coverage, ask: does the state
alter processing? exercise a distinct implementation path? have a distinct spec
behaviour? show historical regression risk? or can one representative scenario
stand in? Collapse equivalent paths (implemented in
`collapse_equivalent_paths`; set `equivalence_key` on relations that a single
representative can cover).

## 10. Spec vs product authority

Never assume `DITA spec semantics == AEM Guides implementation`. Use the spec to
establish the semantic contract, then verify how AEM Guides implements it in the
affected output preset (inspect the rendering layer per SKILL Gap-13). Track the
authority for every conclusion: `DITA_SPEC`, `DITA_OT`, `AEM_GUIDES_DOC`,
`AEM_GUIDES_IMPLEMENTATION`, `HISTORICAL_BEHAVIOR`. If AEM Guides intentionally
differs, preserve both authorities. Preserve the DITA version (1.2 / 1.3 / both)
on every conclusion; if a construct changed between versions, probe both and
record where they differ. If the product/version mapping is unknown, it is an
Open Question, not a guess.

## 11. Existing-automation semantic-path coverage

Do not decide coverage by matching the primary keyword. A test that exercises
`href + navtitle` does **not** cover `navtitle + no href` with `locktitle`.
Classify by semantic path:

```json
{
  "primary_construct": "navtitle",
  "covered_dependency_states": ["href present + navtitle"],
  "missing_dependency_states": ["no href + locktitle=no", "no href + locktitle absent"],
  "equivalent_paths": [], "automation_status": "Partially covered"
}
```

Report the missing semantic paths as the automation gap in
`Automation Coverage & Gaps`.

## 12. Semantic Coverage Gate (machine-enforced)

When `dita_semantics.active` is true, `run_gates.py` runs
`evaluate_semantic_gate`. Every applicable dimension must end `COVERED`,
`INVESTIGATED_AND_REJECTED`, or `UNRESOLVED_AND_EXPOSED`; if a governing semantic
dependency exists but was never investigated (a material relation left as a bare
`INVESTIGATION_CANDIDATE`, or lacking evidence), the gate is `NEEDS_REVIEW` and
the plan is not deliverable. Dimensions (the gate names are a superset that
covers both the CONTROL_ATTRIBUTES / FALLBACK_PRECEDENCE / SEMANTIC_STATES
vocabulary and the neighbourhood vocabulary):

- `PRIMARY_CONSTRUCT_IDENTIFIED`
- `GOVERNING_SPEC_RETRIEVED`
- `SEMANTIC_NEIGHBORHOOD_EXPLORED`
- `CONTROLLING_DEPENDENCIES_EXPLORED`
- `INHERITANCE_EXPLORED_WHEN_APPLICABLE`
- `FALLBACK_PRECEDENCE_EXPLORED_WHEN_APPLICABLE`
- `REFERENCE_RESOLUTION_EXPLORED_WHEN_APPLICABLE`
- `MEANINGFUL_STATE_PARTITIONS_EXPLORED`
- `DITA_VERSION_AUTHORITY_RESOLVED`
- `PRODUCT_IMPLEMENTATION_CHECKED`
- `AUTOMATION_SEMANTIC_PATHS_CHECKED`
- `UNRESOLVED_SEMANTICS_EXPOSED`

## 13. Pre-UAC output split

Do not dump the whole neighbourhood into UAC. Separate discovered semantics into:
- **Confirmed Acceptance Behavior** — semantics directly required by the reported
  feature/fix (these become `[Confirmed]`/`[Proposed]` ACs).
- **Regression Coverage** — related semantic branches that must not regress
  (these go to `Regression Areas`).
- **Investigation Candidates / Findings** — verified-relevant interactions that
  are not part of the acceptance contract (scenarios or notes).
- **Open Questions** — semantics the spec/product cannot establish safely.

## 14. Reasoning-pattern library entry

This procedure implements the reusable pattern
**`SEMANTIC_CONTROL_ATTRIBUTE_DEPENDENCY`**:

> When the behaviour of a DITA construct is controlled, overridden, resolved,
> inherited, filtered, or otherwise modified by another DITA construct or
> attribute, investigate the controlling semantic dimension before declaring
> coverage complete.

Generalized child patterns (reuse, do not duplicate): `FALLBACK_PRECEDENCE`,
`SEMANTIC_STATE_PARTITION`, `CONTROL_ATTRIBUTE_DEPENDENCY`,
`REFERENCE_RESOLUTION_DEPENDENCY`.

## 15. Generalization & success criterion

The explorer must work for any construct A whose processing is influenced by a
construct/attribute B — B must be discovered from evidence, never keyed off a
keyword. Given any DITA-focused Jira, the plan should be able to answer: the
primary construct; which other constructs materially control/modify it; which
value-states create distinct behaviour; which relationships are irrelevant; what
fallback/precedence exists; what inheritance matters; which DITA version governs;
how AEM Guides implements it; which semantic paths are already automated; and what
remains an Open Question — discovered automatically, without a hand-coded pair
list. The `navtitle` Jira, run **without** a `locktitle` hint, must independently
surface `locktitle` as a semantic-dependency hypothesis, investigate its
meaningful branches and the no-`href` case, leave unprovable branches as Open
Questions, and check existing automation for semantic-path coverage — while
staying broader than "test navtitle" without becoming a Cartesian explosion.

## 16. Optional: derived semantic-relation index

If repeatedly probing the DITA PDFs is slow, a derived relation index may be
cached (`{source_construct, target_construct, relation, dita_version,
evidence_chunk, confidence}`) from the already-indexed DITA 1.2/1.3 sources —
reusing Chroma or the existing JSON store, no new database. It is a retrieval
optimization only: every record must trace to authoritative indexed evidence and
carry its provenance; it must never become an unverified hand-authored truth
table (the anti-hardcoding audit still applies to it).
