# Evidence-Driven Dimension Synthesizer (UACDISCOVER-01)

Raises **discovery**, not enforcement. The forcing gates match *known* signals; this
step proposes candidate test dimensions from the manifest's own evidence — including
ones the ticket never named — as `INVESTIGATION_CANDIDATE`s that flow into the existing
`coverage_hypotheses -> verifications` pipeline and `clarification_gate.dimension_space`.
It never authors an AC and never hard-fails.

## Activation

Runs when the manifest carries a `behavior_model`, `evidence_catalog`, or recorded
`construct_relationships`. A manifest with none contributes no candidates. This does not bypass the separate v3
reasoning requirements: a behavioral legacy record without its required blocks
still fails `run_gates`.

## Generators

Each candidate is tagged with the generating evidence label and generator:

- **Behavior-model explorers** — execute `coverage_hypotheses.generate_from_model`
  for all twelve families in `EXPLORATION_FIELDS`; emit only when inspected model
  facts and relationships provide a non-empty technical basis. The `explorers`
  trace distinguishes activation from `NO_GROUNDED_SIGNAL`. These are investigation
  candidates, not contextual Claude Missing Questions or acceptance criteria.

- **CODE_NEIGHBORHOOD** — generic vocabulary signals in cited code text/paths
  (evidence-catalog `source_ref`/`note`, `behavior_model.facts`, read/write paths). Example:
  a metadata / `jcr:content` read path proposes a `VALUE_SET_CHANNEL` candidate for
  repository-node value provenance — *discovered*, not remembered.
  It also emits a separate candidate for each recorded sibling/configuration/caller
  finding in `construct_relationships` (including its exact source). Two neighbors
  on the same axis do not collapse into one check. This consumes recorded inspection;
  it does not perform an AST search or claim to find every unrecorded neighbor.
- **RAG_NEIGHBORHOOD** — the same signal map over recorded `rag_probes`, plus
  fail-open local product-documentation neighbors when recorded probes or current
  behavior text can form a query. Offline results are explicitly supporting discovery;
  when the local collection is unavailable the original no-probe gap remains visible.
- **HISTORY_NEIGHBORHOOD** — recurring same-component defect classes from a recorded
  `search_jira_history` run, or from the local `jira_qa` collection when no live run is
  recorded. Offline results never set `indexed_history_run=true`; when neither source
  is available the generator records a gap and fabricates nothing.

Candidates use the `coverage_hypotheses` item shape (`hypothesis_id`, `dimension`,
`candidate`, `reason`, non-empty `technical_basis`, `current_evidence`,
`status=INVESTIGATION_CANDIDATE`, `equivalence_key`) plus a `generator` tag, and are
collapsed only by exact dimension/equivalence key. Discovery axes normalize to
the v3 family in `dimension`; the original `implied_dimension_axis` survives so
probe coverage does not mistake a broad family for a specific axis. Generator IDs
are stable across repeat runs. Retained duplicates merge evidence and technical basis.

## Output in run_gates

Every synthesized candidate needs an evidence-backed terminal decision. A matching
axis, copied feature name, equivalence key, or candidate row alone does not clear
`REVIEW DISCOVERY:`. `discovery_disposition.py` checks the exact discovery identity,
retained source/basis, one terminal verification and one linked disposition using
the existing canonical contracts. This applies to all generators, not one product.

Missing or invalid chains retain REVIEW and a non-postable receipt. This check adds
no hard failures to the legacy exit-code contract. A justified rejection clears
the discovery note without creating an AC. An unresolved candidate needs its real
Open Question and remains subject to existing question/readiness gates. Verified
implementation evidence may justify regression, never automatic acceptance.

Follow `discovery-disposition.md` and `v3-reasoning-authoring.md`. Do not mark evidence
USED or invent a rejection simply to remove a warning.

## Constraints

Generic and standard-library only. No product symbol, class, config key, or Jira id is
hardcoded — the signal map is generic vocabulary. Non-activated or degraded input yields
an empty candidate set with a recorded reason, never an invented candidate.

Read `offline-authoring-rag.md` for the offline provider, query-expansion, provenance,
Human-UAC exclusion, and live-history honesty contracts.

## Bounded retrieval without silent starvation

Feature queries group features that share the same surface and exact documentation
URLs, then rotate across matched surfaces. A large broad checklist cannot consume
all slots before a smaller matched surface gets a query. The existing six-query,
per-query result and total-candidate limits remain unchanged. The first two explicit
RAG probes and current behavior remain in the bounded plan. Query groups outside
the budget are recorded as deferred gaps, not reported as retrieved. Provider failure
or a result-budget early stop also records unexecuted queries while retaining any
real earlier results. Authors must investigate material deferred candidates through
the normal directed retrieval process.
