# Execution outcome feedback loop (UACLOOP-01)

Use this optional record after a QE plan has been executed. It supplies governed
feedback about ACs that found real defects and defects that escaped the plan. It
does not change the acceptance contract, author ACs, or approve learning patterns.

## Record contract

Store the record under `execution_outcome` in the evidence manifest:

```json
{
  "execution_outcome": {
    "plan_key": "plan-2026-09-01-001",
    "acs": [
      {
        "ac_id": "AC-01",
        "execution": "FAIL",
        "found_defect": true,
        "defect_ref": "DEFECT-REF-001"
      }
    ],
    "escapes": [
      {
        "defect_ref": "DEFECT-REF-002",
        "summary": "A material behavior shipped without matching AC coverage.",
        "should_have_been_covered_by": "FAILURE_RECOVERY",
        "first_missed_stage": "DISCOVERY"
      }
    ],
    "source": "HUMAN",
    "recorded_at": "2026-09-01T12:00:00+05:30"
  }
}
```

`execution` is `PASS`, `FAIL`, or `NOT_RUN`. `source` is `HUMAN` or a trusted
`CI` signal. `MODEL`, `AI`, AI review, and provider synthesis cannot create an
execution outcome or an escape. A defect-finding AC must include `defect_ref`.

Each escape must name both:

- `should_have_been_covered_by`: the generic coverage axis or dimension that
  should have exposed the defect; and
- `first_missed_stage`: one value from the canonical `PIPELINE_STAGES` vocabulary
  in `human_feedback_delta.py`.

This attribution ensures the lesson targets the first failed pipeline stage.
Do not use a Jira key, customer name, or feature name as a production dimension.

## Governed hand-off

`execution_outcome.to_candidate_miss_probes()` converts a valid Human-confirmed
escape into a deterministic UACDISCOVER miss-probe input with:

- `source=HUMAN`;
- `promotion_state=CANDIDATE`;
- `auto_promote=false`; and
- `auto_author_ac=false`.

The candidate must pass the existing `CANDIDATE -> VALIDATING -> APPROVED`
governance. A CI record is valid supervisory evidence when the CI source is
trusted, but phase 1 does not convert CI escapes into Human candidate probes.

`dimension_priority_signals()` may emit `priority_action=RAISE` only after at
least two distinct defects were found by ACs mapped to the same generic coverage
dimension. The AC-to-dimension mapping must come from the plan/coverage model;
the converter does not guess it. A priority signal never writes an AC.

## Gate behavior

`run_gates.py` validates an explicitly present outcome as a REVIEW step. A
malformed record creates a `REVIEW execution-outcome: ...` note and keeps an
otherwise-clean plan exit code unchanged. The note still blocks automatic
posting under the existing review policy. An absent `execution_outcome` block is
a clean, backward-compatible pass.

Automatic collection of Jira/CI defect links is outside this phase.
