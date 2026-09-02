# Behavioral v3 authoring

Use the existing `aem-guides-evidence-manifest-v3` record. A legacy v2 fixture is
input for migration, not a template for a new plan. Do not fabricate facts, queries,
Human approvals, or verification results to make a gate pass.

Claude Desktop remains the reasoning author for the target runtime. Python
enumerates candidates and validates the record. This procedure supplies the
canonical runtime; it does not add an alternate planner, LLM, or final renderer.

## 1. Model inspected behavior before writing ACs

Populate `behavior_model.trigger`, `operations`, `inputs`, `outputs`,
`affected_state`, `consumers`, `processors`, `write_paths`, and `read_paths` as lists.
Empty lists are allowed where genuinely inapplicable; explain unavailable paths
in `unknowns`. Never replace missing implementation evidence with a guessed path.

Record at least one `facts` item with `fact`, `evidence_ids`, `authority`, and
numeric `confidence` in [0,1]. Use the source authority, not the model's opinion.
Bind IDs to inspected sources in `evidence_catalog`; local code must carry its
actual source path and SHA-256. Unknown behavior belongs in `unknowns`, not facts.
Record extra model relationships only when supported: configuration branches,
fallbacks, capabilities, artifact shapes, shared processors, execution/publishing
modes, versioned models, side effects, and state-update/remove paths.

## 2. Execute discovery, do not hand-enumerate dimensions afterward

Run the installed copy's `scripts/dimension_synthesizer.py --manifest <path> --json`.
Its `explorers` trace records all twelve family checks: CONTRACT_BOUNDARY,
CONSUMER, STATE_PARTITION, TYPE_ABSTRACTION, REFERENCE_ARTIFACT,
DITA_SEMANTIC_DEPENDENCY, LIFECYCLE, CONFIGURATION, PUBLISHING_MODE, NFR_RISK,
BACKWARD_COMPATIBILITY, and DOWNSTREAM_REGRESSION. No grounded signal means no
candidate. It also runs code/RAG/history neighborhoods, `miss_probe_library`, and
`feature_map`; source unavailability remains a recorded gap.

Carry returned candidates into `coverage_hypotheses`, retaining their stable ID,
canonical `dimension`, `implied_dimension_axis` when present, `generator`,
`equivalence_key`, `technical_basis`, evidence, and probe/feature/source tags.
Investigate each independent relationship named by the technical basis. Split
distinct consumers where applicability differs; collapse only proven equivalents
and preserve the representative's original generator key. Do not delete candidates
to clear DISCOVERY notes: retain their rejection or unresolved outcome.

Discovery is SUPPORTING only. A matched feature, historical analogy, RAG snippet,
or generated candidate does not establish current applicability or acceptance.
Never paste candidate wording straight into an AC.

## 3. Investigate missing evidence

For each material or blocking gap, author a contextual `missing_questions` record:
`question_id`, `hypothesis_id`, `question`, `why_it_matters`, `preferred_sources`,
`search_concepts`, `blocking`, `material`, `source_ref`, `subject`, and the visible
`open_question_ref`. Follow `missing-question-quality-contract.md` for the
separate hash-bound Claude submission; do not relabel Python candidates as Claude
questions.

Execute a genuinely new query for **each** blocking question. Record actual
`evidence_lifecycle` items with `evidence_id`, `source`, `query`, `pass`, `status`,
`question_id`, `hypothesis_id`, `subject`, and `authority`. A query answered for
another question is not this question's second pass. Do not invent a retrieval
when a provider is absent. Empty/unavailable retrieval leaves the candidate
unresolved, not disproved. If no question remains, an explicit empty
`missing_questions` list is valid; the material-gap validators still run.

## 4. Verify, disposition, then promote

Every candidate needs exactly one `verifications` entry, even when rejected:
CONFIRMED, INFERRED_HIGH_CONFIDENCE, REJECTED, or UNRESOLVED. Use
`hypothesis_verifier.py`'s existing fields and subject-specific authority rules.
Supporting/disproving evidence must be USED evidence bound to that hypothesis.
UNRESOLVED requires a real Open Question; no result does not justify REJECTED.

Populate `dispositions` with the candidate's `source_refs` and destination.
Only product-contract-backed acceptance findings receive `acceptance_promotions`
records. Keep the candidate, subject, authority, disposition, AC ID, and visible
status aligned. Confirmed implementation evidence alone is not acceptance truth.
Retain the existing `contract_facts`, `issue_domains`, `behavior_graph`,
`semantic_closure`, and their exactly-once completeness checks.

Run `run_gates.py` on the complete record before canonical delegation. Hypotheses
count toward probe coverage using `dimension` and `implied_dimension_axis`; do not
duplicate them in clarification solely to satisfy the probe gate. Clarification
still records actual blocking Human decisions and answers when applicable.

## Migration and reviewed exceptions

Ordinary waivers of the three core behavioral blocks hard-fail, including in v2.
Other legacy structural waivers retain their transition behavior. Any reasoning
waiver makes the receipt REVIEW/non-postable. In v3 every reasoning waiver requires
an actual reviewed escape. See `manifest-completeness.md` for the recorded-review
shape. Never self-author a review or downgrade the schema to regain postability.
