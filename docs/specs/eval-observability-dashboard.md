# Eval & Skill Observability Dashboard — implementation plan

Status: Planned (for Codex implementation)
Goal: one screen that answers "is the UAC generator getting better or worse, and where
is it weak right now?" over BOTH axes: (1) the AI eval (coverage / precision / combined /
hallucination, per run and per ticket) and (2) the skill gates (which fail-closed gates
fire, on which tickets). Solo-operator tool, not a team service.

## What data already exists (do not invent sources)

- **Eval runs**: `scripts/uac_eval/*.json` (e.g. `judge_pipeline_*.json`). Each has
  `agg` (means per mode) and `per` (per-ticket coverage_pct, hallucinations, holistic,
  precision_pct, combined_pct, ac_count, over_decomposition, redundancy_pairs,
  ac_section_found, judge_precision, judge_redundant, pipeline_status). File mtime is the
  run timestamp; the filename is the run label. No time-series DB — each run is a file.
- **Gold quality**: `scripts/uac_eval/gold_quality.py` classifies excluded corpus rows.
- **Skill gates**: `.codex/skills/test-plan-generation/scripts/run_gates.py` returns an
  exit code today; it does NOT emit machine-readable per-gate results yet (see Phase 2).

## Phase 1 — MVP (static aggregator + one page). Ship this first.

### 1a. Aggregator — `scripts/uac_eval/aggregate_runs.py`
- Scan `scripts/uac_eval/*.json`, skip non-run files (score_report_*, train_priors).
- Normalize each into: `{run_id (filename), ts (mtime ISO), n, model, seed, vm,
  agg:{coverage,det_precision,combined,halluc,judge_precision,holistic,no_ac_section},
  per:[...] }`. Tolerate older files missing precision keys (null them).
- Write `scripts/uac_eval/dashboard_data.json` = `{runs:[...sorted by ts]}`.
- Stdlib only; add `--self-test` that builds from two tiny fixtures.

### 1b. Dashboard page (choose ONE; recommend the standalone HTML for speed)
Option A (fastest, no build): a single `scripts/uac_eval/dashboard.html` that `fetch`es
`dashboard_data.json` (served by `python -m http.server` from that dir) and renders with
a tiny charting lib (Chart.js via CDN) — trend lines + tables. Zero repo wiring.

Option B (integrated): a React page at `frontend/src/pages/EvalDashboardPage.tsx`, route
`/eval-dashboard` in `App.tsx`, data via a new backend route (Phase 2) or by importing the
JSON. Use the existing `utils/api.ts` fetch helpers and the project's chart conventions.

Panels (both options):
1. **Trend** (x = run ordered by ts): lines for combined, coverage, precision; a second
   axis or small multiple for mean hallucinations. This is THE headline — regression guard.
2. **Latest-run cards**: coverage, precision, combined (F1), hallucinations, holistic,
   and "N plans with no acceptance-contract section (excluded)".
3. **Per-ticket table** (latest run): key, component, coverage/precision/combined,
   ac_count, over_decomposition, redundancy_pairs, pipeline_status. Sort by combined asc;
   row highlight when precision < 50, over_decomposition > 0, or ac_section_found = false.
   This is the "where is it weak right now" drilldown.
4. **Precision distribution**: histogram of per-ticket precision_pct (0, 1-59, 60-89,
   90-100) so the over-decomposition tail is visible at a glance.

## Phase 2 — skill-gate observability (adds the second axis)

### 2a. Machine-readable gate output — `run_gates.py --json`
Add a `--json <path>` flag that writes `{ticket, exit_code, gates:[{name, status,
activated (bool), reasons:[...]}], self_tests:{passed,failed}}`. Keep the human output
unchanged. Each validator already returns pass/fail + reasons — serialize them.

### 2b. Gate panel on the dashboard
Read a directory of gate-result JSONs (one per authored ticket) and show: per-gate
fire-rate (how often each gate activates), pass/fail counts, and the last N tickets with
any gate failure. Answers "which recurring class is the skill catching, and is a gate
dead (never fires) or noisy (always fails)?"

## Phase 3 — persistence (optional, only if run volume grows)
Append each run's `agg` to `scripts/uac_eval/run_history.jsonl` at eval end (one line per
run) so the trend survives even if per-run JSONs are cleaned. Dashboard reads history if
present, else falls back to scanning `*.json`.

## Non-goals
- Not a live/hosted service, not multi-user, no auth. It reads local eval artifacts.
- No new metrics invented beyond what the harness already emits. If a metric is wanted
  (e.g. per-component precision), add it to `judge_pipeline.py` first so it is in the JSON,
  then surface it — never compute a different number in the dashboard than the eval reports.

## Validation
- `python scripts/uac_eval/aggregate_runs.py --self-test` passes.
- Open the dashboard against the existing `judge_pipeline_*.json` files and confirm the
  trend shows the runs we already have (baseline-vs-precision-signal-vs-G1-fix), and the
  per-ticket table highlights the over-decomposition tail (33605 etc.).
```

## Master Codex prompt (Phase 1 MVP)

```text
TASK: Build Phase 1 of the eval observability dashboard described in
docs/specs/eval-observability-dashboard.md (read it first). Deliver ONLY Phase 1
(aggregator + standalone HTML dashboard, Option A). Do not do Phase 2/3.

IMPLEMENT:
1. scripts/uac_eval/aggregate_runs.py
   - Scan scripts/uac_eval/*.json; include only judge_pipeline* run files (skip
     score_report*, train_priors, dashboard_data). Each run JSON has top-level "agg"
     (dict of mode -> metric -> value) and "per" (list of per-ticket dicts). Read the VM,
     seed, n, model from the file when present (some are only in the .md sibling header —
     if absent in JSON, leave null; do NOT parse markdown).
   - Emit scripts/uac_eval/dashboard_data.json = {"runs":[{run_id, ts, n, agg_pipeline,
     agg_baseline, per}]} sorted by ts ascending. Tolerate missing precision keys (null).
   - Stdlib only. Add run_self_tests() building from two in-memory fixture dicts written
     to a tmp dir, plus a --self-test CLI flag. Print a one-line summary of runs found.
2. scripts/uac_eval/dashboard.html
   - Standalone; fetch('dashboard_data.json'); Chart.js from CDN. No build step.
   - Render the 4 panels from the spec: Trend (combined/coverage/precision over runs),
     latest-run cards, per-ticket table (sortable, highlight precision<50 /
     over_decomposition>0 / ac_section_found==false), precision-distribution histogram.
   - Degrade gracefully if a run lacks precision fields (older runs): plot what exists.

VALIDATE (must pass before returning):
  - python scripts/uac_eval/aggregate_runs.py --self-test   -> PASS
  - python scripts/uac_eval/aggregate_runs.py               -> writes dashboard_data.json,
    prints the run count (should be >=3 given existing judge_pipeline_*.json files)
  - Serve and eyeball: cd scripts/uac_eval && python -m http.server 8765, open
    http://127.0.0.1:8765/dashboard.html — trend shows the existing runs; the per-ticket
    table highlights the over-decomposition tail (e.g. GUIDES-33605).

CONSTRAINTS:
  - Never compute a metric differently than the eval JSON reports it; the dashboard only
    reads and displays. If a field is missing, show "n/a", do not fabricate.
  - No changes to judge_pipeline.py / precision.py / the runtime in this task.
  - Keep it stdlib + a single CDN chart lib; no new pip/npm deps.
```
