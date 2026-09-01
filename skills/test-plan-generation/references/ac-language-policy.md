# UAC Language & Readability Policy (UACFIX-LANGUAGE-01)

Target: **deep internal QE reasoning + simple external QE language.** Simplification
must never reduce coverage. This is a rendering/synthesis concern (the UAC Linter /
AcceptanceContractSynthesizer), not a discovery concern — see
`references/plain-language-ac-writing.md` for the writing style and `ac_readability.py`
for soft first-read clarity notes. This gate adds the hard-edged, machine-checkable
rules, including the merge-safety invariant.

## Language profile (how to write the final AC)

- Simple daily QE language; preserve exact AEM Guides / DITA terms where necessary.
- One AC = one clearly testable customer behavior. Prefer observable product behavior.
- Clear **must / must-not** statements. Do not force Given/When/Then.
- Keep negative behavior next to the positive behavior it protects.
- No vague phrases: "works correctly", "should work", "verify that", "behaves as expected".
- Keep implementation names out of the AC unless the technical artifact **is** the
  acceptance contract (e.g. a required `metadata.xml`) — then set
  `technical_artifact_is_requirement: true` on that AC.
- Merge overlapping ACs when the customer-visible contract is identical; **never**
  merge if it hides a distinct material configuration / lifecycle / identity /
  consumer / ordering / failure / negative boundary.

## FluffyJaws boundary

FluffyJaws provides **content evidence**, not writing style. Never copy FluffyJaws
prose into an AC: normalize → applicability → candidate → disposition → synthesize a
concise QE contract. (Enforced upstream by `fluffyjaws_evidence.py`.)

## The `ac_synthesis` block (opt-in; enables machine checks)

```json
"ac_synthesis": {
  "source_candidate_ids": ["CF-02", "CF-03", "CF-04"],
  "final_acs": [
    {"ac_ref": "AC-01",
     "title": "Deleted-preset data is removed on cleanup",
     "body": "When cleanup completes, deleted-preset data must be absent and valid data must remain.",
     "candidate_ids": ["CF-09"],
     "merged_candidate_ids": ["CF-09"],
     "distinct_material_dimensions": [],
     "distinct_contract_count": 1}
  ]
}
```

## Enforced lints (`scripts/ac_language_policy.py`)

- **MATERIAL_CANDIDATE_LOSS = 0** — every `source_candidate_ids` entry must survive
  into some final AC's `candidate_ids`/`merged_candidate_ids`. If equivalence can't
  be shown, do not merge.
- **HIDDEN_MATERIAL_SCENARIO** — a merge that declares a distinct material dimension
  is rejected.
- **VAGUE_EXPECTATION**, **UNCLEAR_AC_TITLE**, **IMPLEMENTATION_DETAIL_LEAK**
  (class.method(), CSS selector, source-file symbol — unless
  `technical_artifact_is_requirement`), **MULTIPLE_UNRELATED_CONTRACTS**
  (`distinct_contract_count > 1`), **REDUNDANT_AC** (duplicate bodies).

## Language vs discovery (do not confuse them)

- "AC wording is confusing" / "already there but I couldn't understand it" →
  RENDERING/LANGUAGE fix (title, grouping, visibility). Do **not** change reasoning
  families or reduce coverage.
- "Scenario missing" → a discovery/applicability/disposition question (debug the
  pipeline), not a language change.

Titles should tell QE what behavior the AC protects
("Deleted-preset data is removed on cleanup"), not "Correct behavior".

## Backward compatibility

Absent `ac_synthesis` is a clean pass.
