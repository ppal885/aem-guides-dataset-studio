# Close each discovery with evidence

Use this process for a new behavioral UAC and whenever a revision adds/removes
coverage, changes an expected result, or a reviewer names a missed feature.
A wording-only revision is not a fresh completeness check. Do not claim that it
reran discovery, RAG, code inspection, or gates unless those steps actually ran.

## Discover before reducing the AC list

1. Read the current Jira scope and inspect the affected implementation and UI.
   Record the real sibling options/configuration keys, callers and same-path
   processors in `construct_relationships.discovery.code_neighborhood_sweep`.
   Record searches with no findings honestly; an empty search is not proof that
   no related feature exists.
2. Run `dimension_synthesizer.py --manifest <path> --json`. It combines grounded
   model families, recorded code neighbors, curated feature-map entries, learned
   probes and available retrieval. The affected surface can discover a related
   feature even when the ticket does not name that feature.
3. Query product RAG for each material discovered concept. Inspect the relevant
   configuration/UI/caller in code when applicability is unclear. Web evidence,
   if used as a fallback, must be labelled as such, never as a RAG result. Unavailable
   retrieval stays a gap or Open Question, not proof of no impact.

## Retain the exact candidate

Carry the emitted candidate into `coverage_hypotheses`. Keep `generator`,
`equivalence_key`, `technical_basis`, `current_evidence` and its source tags.
An axis such as CONSUMER or CONFIGURATION is not a substitute for an independently
discovered neighbor. A decision about one sibling does not settle another.

Ground its sources in `evidence_catalog` and record actual inspection in
`evidence_lifecycle`. Local source files need their real path and SHA-256; file
hashing alone does not prove inspection. Keep discovery provenance even when later
evidence rejects applicability. Historical or curated advice is supporting only.

An activating label such as `behavior_model.trigger` is not a retrieved source ID.
For these generic leads, keep the label and bind the newly inspected catalog entry
with `discovery_refs: ["<exact candidate equivalence_key>"]`. Retain its real
`source_ref` and, for code, `source_hash`; record the actual query and use. Exact
feature-map reference URLs may also link the retrieved underlying documentation.
Neither linkage upgrades the checklist or a RAG summary into acceptance authority.
A concrete recorded code/source URL cannot be swapped for an unrelated alias.

Then link the existing records:

- `verifications[].hypothesis_id` identifies the exact hypothesis. Use one terminal
  verdict and the existing subject/authority rules. Supporting/disproving evidence
  must be USED and bound to that hypothesis after real inspection.
- `dispositions[].source_refs` includes that hypothesis ID. `finding_id` is the
  disposition's own ID, not the hypothesis ID. Record one destination.
- Rejected: preserve inspected contrary/scope evidence and a specific reason.
- Unresolved: link a real declared `open_question_ref` in the verification and
  question disposition. Missing/unavailable sources can remain honestly unresolved;
  do not invent a source hash or USED evidence to expose the question. The existing
  missing-question gates still enforce genuine retrieval attempts/second passes.
  No result does not justify a rejection.
- Confirmed implementation: use regression coverage when appropriate. Only a
  current acceptance contract can justify promotion to an AC through the existing
  acceptance promotion gate.

`run_gates.py` leaves a `REVIEW DISCOVERY:` note when this chain is absent or invalid.
The existing REVIEW contract keeps the receipt non-postable even if the compatibility
exit code is zero. Do not add waivers, copied verdicts or blanket out-of-scope rows.
This safeguard checks recorded evidence and decisions; it cannot prove exhaustive
search or replace Human review of semantic relevance.

## Keep the final wording simple

Discovery can be broad without making the AC list repetitive. Merge only checks
with the same pass/fail outcome while retaining all candidate mappings. Distinct
settings, entry points or regression risks still need an explicit decision. Use
the exact AEM Guides feature names and the plain-language policy; never turn an
internal candidate template into QE-facing AC wording unchanged.
