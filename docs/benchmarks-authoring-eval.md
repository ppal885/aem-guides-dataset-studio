# Screenshot + reference DITA — evaluation harness

This document describes the **offline benchmark** for screenshot-guided DITA generation with an optional reference topic. Implementation lives under `backend/app/benchmarks/authoring_eval/`.

## Goals

- Track **XML validity**, **structural correctness**, **topic type**, **style vs reference**, **reference leak risk**, **unresolved xref/conref**, **pipeline repair** (auto-fix pressure), and **mocked insertion success**.
- **Regeneration** and **edit-after-generation** are defined below; they require **product telemetry**, not the generator alone.

## Dataset layout

| Path | Purpose |
|------|---------|
| `app/benchmarks/authoring_eval/dataset/manifest.yaml` | Case definitions (prompt, expected type, vision stub, reference path, AEM expectations) |
| `app/benchmarks/authoring_eval/dataset/references/*.dita` | Reference topics (include distinctive `@id` values to detect over-copying) |
| `app/benchmarks/authoring_eval/dataset/screenshots/*.png` | Optional real PNGs; if omitted, a minimal 1×1 PNG is used |

Manifest fields are modeled by `BenchmarkCase` in `models.py` (Pydantic).

## Scoring dimensions

| Dimension | Meaning | Source |
|-----------|---------|--------|
| **xml_validity_rate** | Share of cases where `validate_dita_folder` reports no errors on the generated file | `scoring.score_xml_valid_folder` |
| **structural_correctness_rate** | Share with no structural **errors** from `validate_dita_topic_structure_categorized` | `dita_authoring_structure` |
| **topic_type_correctness_rate** | Share where `result.dita_type` matches `expected_dita_type` (skipped if expectation omitted) | Compare to manifest |
| **style_adherence_mean** | Mean of 0–1 score: reference vs generated profiles from `analyze_reference_dita` (habits, child order, root alignment) | `scoring.style_adherence_score` |
| **mean_over_copying_risk** | Mean binary risk: `1` if any reference `@id`, `xref/@href`, or `@conref` string reappears verbatim in output | `fingerprints.over_copying_score` |
| **mean_unresolved_xref_conref_rate** | Unresolved same-document xref/conref error count ÷ max(1, xref+conref element count) | `scoring.unresolved_xref_conref_rate` |
| **pipeline_repair_rate** | Share of runs where `debug.pipeline_trace` contains `repair_optional` with `repaired` | `scoring.pipeline_repair_used` |
| **insertion_success_rate** | Among cases with `expect_saved_to_aem: true`, share with `status == "saved"` (AEM mocked in harness) | `ChatDitaAuthoringResult.status` |
| **regeneration_rate** | User clicked regenerate / new attempt — **not** measured offline | Telemetry (see below) |
| **edit_after_generation_rate** | User edited artifact after generation — **not** measured offline | Telemetry |

## Running

From `backend/`:

```bash
python -m app.benchmarks.authoring_eval.cli
python -m app.benchmarks.authoring_eval.cli --json-out authoring_benchmark_report.json
```

Pytest (CI-friendly, same stubs):

```bash
pytest tests/benchmarks/test_authoring_eval.py -q
```

## Recommended baseline metrics (starting point)

Use the bundled manifest as a **smoke baseline** after any change to prompts, models, or serializers:

| Metric | Target (smoke suite) |
|--------|----------------------|
| `xml_validity_rate` | 1.0 |
| `structural_correctness_rate` | 1.0 |
| `topic_type_correctness_rate` | 1.0 (where expected type set) |
| `mean_over_copying_risk` | 0.0 |
| `mean_unresolved_xref_conref_rate` | 0.0 |
| `pipeline_repair_rate` | 0.0 (ideal; increases warrant investigation) |
| `style_adherence_mean` | informational (reference/output type mismatch lowers score by design) |

Treat **style_adherence_mean** as a **regression signal**, not a hard gate, unless you add paired reference/output types per case.

## Comparing prompt/model changes safely

1. **Freeze the dataset** — commit manifest + references + optional PNGs; bump `manifest.version` when semantics change.
2. **Run twice** — `cli --json-out before.json` on baseline commit, `after.json` on candidate branch.
3. **Diff aggregates** — especially `structural_correctness_rate`, `mean_over_copying_risk`, `mean_unresolved_xref_conref_rate`, `pipeline_repair_rate`.
4. **Inspect failures** — each case includes `assertion_failures` and `over_copying_reasons` in `extra` when leaks occur.
5. **Live eval** — set `is_llm_available()` truthfully and remove/disable vision stub only in a **manual** job with secrets; do not put API keys in CI. Keep CI on the deterministic stub path for stability.
6. **Telemetry** — for regeneration and post-edit quality, emit events with `pipeline_run_id` from `ChatDitaAuthoringResult.debug` and join in your warehouse; see `telemetry_merge.py`.

## Security notes

- Benchmark files are trusted **local** fixtures. Do not point the manifest at arbitrary user uploads without scanning and size limits (**path traversal / SSRF not applicable** to committed paths; validate any future UI-driven manifest).

## Automated assertions (gates)

`apply_case_assertions` fails a case when:

- XML invalid or structurally errored
- Topic type mismatch (if expected)
- `expect_saved_to_aem` but not `saved`
- Any reference id/href/conref leak
- Any unresolved xref/conref (same-document)

Adjust assertions in `scoring.py` if you add cases that intentionally include external `href` targets (would require extending the temp folder validator setup).
