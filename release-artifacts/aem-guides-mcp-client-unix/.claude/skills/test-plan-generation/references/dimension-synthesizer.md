# Evidence-Driven Dimension Synthesizer (UACDISCOVER-01)

Raises **discovery**, not enforcement. The forcing gates match *known* signals; this
step proposes candidate test dimensions from the manifest's own evidence — including
ones the ticket never named — as `INVESTIGATION_CANDIDATE`s that flow into the existing
`coverage_hypotheses -> verifications` pipeline and `clarification_gate.dimension_space`.
It never authors an AC and never hard-fails.

## Activation

Runs when the manifest carries a `behavior_model` or an `evidence_catalog`. A manifest
with neither (e.g. a legacy v2 plan) is a clean no-op, so `run_gates` exit and postability
are unchanged.

## Generators

Each candidate is tagged with the generating evidence label and generator:

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
collapsed by dimension.

## Output in run_gates

For every synthesized candidate whose `dimension` is **not** already represented in
`coverage_hypotheses[].dimension` or `clarification.dimension_space[].axis`, `run_gates`
emits a non-blocking `REVIEW DISCOVERY:` note so the author must consciously dispose or
reject it. Exit stays 0; the receipt becomes non-postable until the author resolves the
candidate (the standard REVIEW contract).

## Constraints

Generic and standard-library only. No product symbol, class, config key, or Jira id is
hardcoded — the signal map is generic vocabulary. Non-activated or degraded input yields
an empty candidate set with a recorded reason, never an invented candidate.

Read `offline-authoring-rag.md` for the offline provider, query-expansion, provenance,
Human-UAC exclusion, and live-history honesty contracts.
