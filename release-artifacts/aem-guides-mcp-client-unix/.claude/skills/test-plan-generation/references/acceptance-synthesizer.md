# Acceptance-Contract Synthesizer (UACFIX-06)

Turn the finalized Candidate Ledger into a concise, QE-readable acceptance contract
WITHOUT losing distinct material coverage. Internal completeness stays detailed; the
external UAC wording stays simple. Do not reason from scratch in the renderer - consume
only finalized/disposition-ready candidates from the Candidate Ledger, Scope Gate,
Authority/Conflict Resolver, and Oracle Resolver.

## Group by customer-observable contract

Group candidates by CUSTOMER-OBSERVABLE contract, not by tag, file, implementation
symbol, or shared words. `synthesis_group` on each final AC is one of:
CORE_CUSTOMER_CONTRACT, DIRECT_FIX_BEHAVIOR, SHARED_REGRESSION, NEGATIVE_BOUNDARY,
CONFIGURATION_BRANCH, ORDERING_OR_ASSOCIATION, LIFECYCLE, FAILURE_RECOVERY.

## Merge rule

Merge ACs only when they describe the same customer-observable contract. Never merge
when it would hide a distinct state, configuration, consumer, negative boundary,
identity, ordering, or failure behaviour. (Merge-safety and MATERIAL_CANDIDATE_LOSS=0
are enforced by `ac_language_policy.py`; language lints live there too.)

## Internal -> external trace (enforced by `scripts/acceptance_synthesizer.py`)

Every synthesized AC (any final AC that declares a `synthesis_group`) must retain:
`candidate_ids`, `evidence_ids`, `scope_basis`, `oracle`, and `merged_candidate_ids`
(each merged candidate must appear in `candidate_ids`). This keeps simplification from
destroying traceability. Language stays natural - do NOT force Given/When/Then, and
keep internal terms (semantic closure, candidate, resolver graph, family activation)
out of the customer-facing AC.

## Structure

Prefer an AC title plus 2-4 concise sentences, with a short example only when it
materially clarifies behaviour. Render concise Scope from DIRECT_SCOPE plus explicitly
selected material shared-path coverage; render only material, evidence-unresolved Open
Questions; keep OOS/Rejected to useful boundaries, not laundry lists.

## Backward compatibility

Absent `ac_synthesis`, or an `ac_synthesis` block with no `synthesis_group`, is a
clean pass.
