# Test-Plan Quality Golden Benchmark

This offline harness qualifies changes to the AEM Guides test-plan skill and its evidence pipeline. It does not run in the API process and does not change normal single-ticket generation.

## Coverage

- 18 real Jira cases.
- Three cases each for Editor, Authoring, Publishing, Platform, Schematron, and Integration.
- Historical-match goldens based on explicit Jira Duplicate or Cloners relationships, plus cases where no strong relationship exists.
- Principal-QE performance decisions spanning `required`, `conditional`, and `not_required`.
- Seeded goldens are intentionally not production-release eligible.

## Commands

Run from the repository root:

```text
python scripts/run_test_plan_quality_benchmark.py validate --json
python scripts/run_test_plan_quality_benchmark.py prepare --run-root <absolute-empty-directory> --skill-variant codex
python scripts/run_test_plan_quality_benchmark.py score --run-root <absolute-directory> --json-out <report.json> --markdown-out <report.md>
```

Use `--skill-variant claude` for a Claude candidate. Add `--baseline <baseline.json>` only when comparing with an approved baseline. Scoring exits nonzero on incomplete artifacts, integrity failures, threshold failures, baseline regression, seeded goldens, or failed skill self-tests.

## Blind Candidate Boundary

`prepare` writes only public inputs and schemas. The candidate receives no expected Jira key, performance decision, source rationale, or prior score. The scorer verifies the run fingerprint, immutable case inputs and helper, candidate revision, exact evidence/plan artifact fingerprints, and absence of expected Jira keys in candidate-facing files.

Each case must produce:

- `full-plan.md`
- `combined-plan.md`
- `evidence-manifest.json`
- `retrieval.json`
- `evidence-catalog.json`
- `fingerprints.json`, generated last with `python ../compute-fingerprints.py .`

The generated `candidate-contract.md`, `artifact-schemas.json`, and immutable `compute-fingerprints.py` define the machine-readable artifact contract. Retrieval schema v2 requires every returned Jira to be same-mechanism qualified, records `same_release`, `different_release`, or `unknown`, and forbids hard release/version filtering.

## Metrics

- `case_pass_rate`: complete case-level contract and integrity checks.
- `gate_pass_rate`: the selected skill's mandatory gate exits cleanly.
- `ac_contract_rate`: every AC follows the immutable grammar and sequence.
- `history_precision_at_5`: selected Past Jiras that match explicit goldens, divided by selected Past Jiras.
- `history_recall_at_5`: explicit golden Jira relationships found in the selected top five.
- `retrieval_recall_at_10`: explicit golden Jira relationships present within rank 10 of either recorded same-customer or cross-customer query.
- `citation_accuracy`: AC citations resolve to evaluator-verified catalog entries, not merely candidate-declared IDs.
- `performance_decision_accuracy`: manifest decision equals the reviewed principal-QE golden.
- `history_version_accuracy`: expected historical Jiras carry the reviewed release/version applicability classification; version remains a ranking signal, never a hard filter.
- `fingerprint_integrity_rate`: scorer-recomputed evidence snapshot and plan fingerprints exactly match the submitted immutable artifact.
- `hallucination_free_rate`: no invented Jira key, unverified AC source, graph-path-only source, invented local source, or Past Jira absent from recorded retrieval.

No-match history cases score precision and recall as 1 only when the plan selects no Past Jira. Retrieval may return candidates; the plan must reject area-only or weak-mechanism matches.

## Golden Governance

- Every case stores at least two rationales: historical-match basis and performance-decision basis.
- Approval is per case. Each case requires reviewer identity and timestamp before the manifest can become `approved`.
- The manifest also requires an accountable suite approver and timestamp.
- A baseline can be written only from a passing run against an approved manifest.
- Baseline schema, benchmark ID, and manifest fingerprint must match before comparison.
- Never edit a baseline to hide a regression. Review the candidate or deliberately version and reapprove the goldens.

## Module Layout

- `models.py`: strict schemas and golden governance.
- `scoring.py`: deterministic artifact, retrieval, citation, AC, performance, and hallucination scoring.
- `runner.py`: blinded preparation, run-integrity audit, aggregation, baseline comparison, and reports.
- `cli.py`: `validate`, `prepare`, and `score` commands.
- `dataset/manifest.yaml`: seeded 18-case golden set.
