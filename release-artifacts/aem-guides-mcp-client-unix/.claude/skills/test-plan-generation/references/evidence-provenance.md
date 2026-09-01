# Evidence Provenance Gate (UACFIX-12)

Gates validate the manifest artifact, not that reasoning actually happened. A
hand-crafted manifest whose evidence ids do not resolve to real files or probes can
otherwise pass. This gate (an extension of `verify_evidence.py`, run by `run_gates.py`)
makes cited evidence real.

## Activation

Runs only when the manifest declares an `evidence_catalog` (backward-compatible: a plan
without one is a clean pass). The documented opt-out `behaviour_matters: false` also
skips it, same as the RAG escape.

## Evidence catalog

```
"evidence_catalog": [
  {"id": "E1", "source_type": "code", "source_ref": "C:/starling/.../Handler.java",
   "source_hash": "sha256:<64 lowercase hex>"},
  {"id": "E2", "source_type": "rag", "probe": "<exact question recorded in rag_probes>"}
]
```

An entry may instead live under `evidence_catalog.sources` / `.entries`. `id` may be
`source_id`; `source_type` may be `kind`.

## Hard failures (prefix `PROVENANCE GATE:`)

- A **dangling id**: any evidence id cited in the plan or in `behavior_model.facts[].evidence_ids`
  that is not a catalog entry. A dangling id is never allowed, even in degraded mode.
- A **code entry** whose `source_ref` does not exist on disk (forward slashes), or whose
  `source_hash` is not `sha256:<64 hex>`, or whose hash does not match the file.
- A **rag entry** whose `probe`/`source_ref` does not correspond to a recorded
  `rag_probes` question.

## Degraded escape

A catalog entry explicitly marked unavailable (`availability`/`status` =
`unavailable`/`degraded`/…) is exempt from the **disk/hash** check only when the manifest
carries an `evidence_preflight.claim_restrictions` entry. The id must still resolve — an
unavailable source justifies a missing file, never a dangling reference.

## Coordination

Complements `verify_evidence.verify` (cited file paths/line numbers exist),
`verify_attachments` (attachments fetched + attested), and `verify_config_keys`
(reporter config keys grep-verified in the clone). This one closes the id→source loop.
