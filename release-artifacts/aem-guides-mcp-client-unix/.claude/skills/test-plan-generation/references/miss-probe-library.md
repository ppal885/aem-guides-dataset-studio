# Miss-Probe Library (UACDISCOVER-02)

The compounding ceiling-raiser. Every human-caught miss becomes a **reusable discovery
probe**, so the skill improves per correction instead of needing a new bespoke gate each
time. The library feeds the dimension synthesizer (UACDISCOVER-01), which emits matching
probes as `LEARNED_PROBE` `INVESTIGATION_CANDIDATE`s.

## Where it lives

`data/miss_probes.json` (checked in, part of the enforced byte-match set so a learned
probe can never be missing from the executing copy). `scripts/miss_probe_library.py`
loads, governs, and matches it.

## Probe schema

```
{
  "probe_id": "MP-001",
  "pattern_class": "DISCOVERY_PATTERN",
  "signal_pattern": {"evidence_kind": "CODE|RAG|HISTORY|CONTRACT",
                     "match": ["generic keyword/token over evidence text/paths"],
                     "component_scope": ""},
  "implied_dimension": {"axis": "<one of the coverage axes>",
                        "candidate_template": "generic phrasing of the dimension to test"},
  "provenance": {"source": "HUMAN", "delta_ids": ["..."],
                 "promotion_state": "APPROVED|VALIDATING", "independent_case_count": N},
  "abstraction_note": "why this generalizes beyond the originating ticket",
  "normative_invariant": true,          // optional: justifies ACTIVE below the case floor
  "counterexamples_checked": true,
  "equivalence_key": "dedup family",
  "status": "ACTIVE|SHADOW|RETIRED"
}
```

## Governance (mirrors human_feedback_delta.py — human feedback is the only learning truth)

`effective_status()` enforces these defensively, even if the stored `status` over-claims:

- **HUMAN-only + APPROVED => ACTIVE.** A `VALIDATING` probe runs in **SHADOW**
  (non-authoritative). `AI_REVIEW` / `FLUFFYJAWS` / `MODEL` can never be ACTIVE.
- **Generalized required.** `signal_pattern.match` and `candidate_template` must be generic
  vocabulary; a token that looks like a Jira key, a `Class::member`, a camelCase symbol, or
  a path is rejected (RETIRED).
- **Counterexample-mined.** `counterexamples_checked` must be true before ACTIVE.
- **Language != discovery.** `RENDERING_LANGUAGE_PATTERN` / `TESTABILITY_PATTERN` never
  become discovery probes.
- **Anti-overfit.** Below `REQUIRED_INDEPENDENT_CASES` (2) without `normative_invariant`
  stays SHADOW. RETIRED probes never emit. Collapse by `equivalence_key`.

## Synthesizer integration

`candidates_for(evidence_pairs)` returns `LEARNED_PROBE` candidates for ACTIVE/SHADOW
probes whose `signal_pattern.match` hits the evidence; each cites the matching evidence
label, the `probe_id`, and the originating `delta` id(s). SHADOW candidates are tagged
`non_authoritative`. The synthesizer includes these in its output; `run_gates` surfaces
any unrepresented dimension as a `REVIEW DISCOVERY:` note. Candidates never author an AC.

## Manifest activity block (optional)

`miss_probe_activity.dispositions[]` (`{probe_id, disposition}`) lets a plan record how it
disposed each learned candidate; `validate()` flags an unknown `probe_id` or invalid
disposition as a non-blocking `REVIEW miss-probe:` note. Absent block = clean pass.

## Adding a probe

Only from a HUMAN, APPROVED, counterexample-checked delta whose lesson generalizes. Never
encode a single concrete symbol, path, customer, or Jira key — that fails both the
generalization rule and the anti-hardcoding audit.
