# Golden Test-Plan Benchmark

## Purpose

- Use this benchmark only to qualify a test-plan skill, RAG, Jira retrieval, evidence-graph, ranking, or AC-contract release. Do not run all 18 cases for an ordinary test-plan request.
- The suite contains 18 Jira cases: three each for Editor, Authoring, Publishing, Platform, Schematron, and Integration. It covers `required`, `conditional`, and `not_required` performance decisions.
- Seeded goldens are development evidence only. They cannot establish or update a production baseline until an accountable QE reviewer verifies every case's Jira relationship and performance decision, records that case's reviewer and review time, and changes manifest `golden_status` to `approved` in a reviewed change.

## Blind Evaluation

- The evaluator owns the golden manifest. The candidate sees only `run.json`, `candidate-contract.md`, `artifact-schemas.json`, and each case's `case-input.json` and `task.md`.
- Never inspect or disclose expected Jira keys, expected performance decisions, prior reports, baselines, or another candidate's artifacts while producing a candidate run.
- Never fabricate a successful `search_jira_history` call when retrieval is degraded. A failed or incomplete case must remain failed.

## Workflow

- Validate the suite: `python scripts/run_test_plan_quality_benchmark.py validate --json`.
- Prepare a new empty blinded run: `python scripts/run_test_plan_quality_benchmark.py prepare --run-root <absolute-run-directory> --skill-variant codex|claude`.
- Generate each case with the selected skill and write the five required artifacts named in its `task.md`.
- Score the completed run: `python scripts/run_test_plan_quality_benchmark.py score --run-root <absolute-run-directory> --json-out <report.json> --markdown-out <report.md>`.
- Compare a candidate with an approved baseline by adding `--baseline <baseline.json>`.
- Write a new baseline only from a passing run against approved goldens by adding `--write-baseline <baseline.json>`. Never auto-update a baseline to make a regression pass.

## Required Candidate Artifacts

- `full-plan.md`: validated eleven-section record.
- `combined-plan.md`: full record plus any automation-evidence appendix.
- `evidence-manifest.json`: the normal mandatory skill manifest, including performance assessment and evidence-graph status.
- `retrieval.json`: exactly one successful same-customer and one successful cross-customer `search_jira_history` query with ranked results.
- `evidence-catalog.json`: only directly retrieved or inspected sources. Local code, attachment, and log entries require a matching SHA-256 hash.

## Release Gates

- Enforce complete artifacts, skill-gate success, immutable AC grammar, historical precision@5, historical recall@5, retrieval recall@10, citation accuracy, performance-decision accuracy, hallucination-free output, and no regression from the approved baseline.
- A catalog entry does not prove itself. Jira citations must resolve to the target or retrieved Jira set; local sources must exist and match their hash; web/DITA/Figma citations must use an approved direct or retrieval method.
- Graph path IDs never count as underlying evidence. Unknown Jira keys, unverified sources, invented paths, and selected history absent from recorded retrieval fail the run.
- Run both Codex and Claude skill self-tests and parity checks before release. Benchmark unavailability does not alter normal plan generation; it blocks only release qualification.
