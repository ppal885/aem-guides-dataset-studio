# Evidence-Driven Dimension Synthesizer (UACDISCOVER-01)

Raises **discovery**, not enforcement. The forcing gates match *known* signals; this
step proposes candidate test dimensions from the manifest's own evidence — including
ones the ticket never named — as `INVESTIGATION_CANDIDATE`s that flow into the existing
`coverage_hypotheses -> verifications` pipeline and `clarification_gate.dimension_space`.
It never authors an AC and never hard-fails.

## Activation

Runs when the manifest carries a `behavior_model` or an `evidence_catalog`. A manifest
with neither contributes no candidates. This does not bypass the separate v3
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

For every synthesized candidate whose `dimension` is **not** already represented in
`coverage_hypotheses[].dimension` or `clarification.dimension_space[].axis`, `run_gates`
emits a non-blocking `REVIEW DISCOVERY:` note so the author must consciously dispose or
reject it. Exit stays 0; the receipt becomes non-postable until the author resolves the
candidate (the standard REVIEW contract).

Model-explorer candidates and feature-map entries require their exact generator
equivalence key; a single broad-family hypothesis cannot hide these candidates.
Follow `v3-reasoning-authoring.md` to carry the output into terminal verification.

## Constraints

Generic and standard-library only. No product symbol, class, config key, or Jira id is
hardcoded — the signal map is generic vocabulary. Non-activated or degraded input yields
an empty candidate set with a recorded reason, never an invented candidate.

Read `offline-authoring-rag.md` for the offline provider, query-expansion, provenance,
Human-UAC exclusion, and live-history honesty contracts.
