# UAC label gate for full RAG test plans

Do **not** manually read Jira `acceptance_criteria` custom fields or UAC comment threads for gate decisions. Use **Jira labels** only.

## Labels

| Label | Meaning | Generator behavior |
| --- | --- | --- |
| **`UAC_Check`** | QA requested full test-plan / RAG generation | **Required** to run `guides_test_plan_generator` full RAG packet |
| **`UAC_Done`** | PM/QA marked UAC complete on the ticket | Sign-off checks (AC-*) may be written from Jira **Expected Result** + description |

## Workflow

1. **Pre-UAC product context** (pipeline) — explain the Guides feature area before acceptance work. See `references/pre-uac-product-context.md`. Runs automatically in `test_plan_pipeline` after RAG intake.
2. PM/QA finishes UAC discussion on Jira → apply **`UAC_Done`** when acceptance is agreed.
3. When QA wants the **full RAG packet** + compact test plan → apply **`UAC_Check`**.
4. Run unified pipeline (`test_plan_pipeline` / `run_test_plan_pipeline.py`) **or** MCP `guides_test_plan_generator` with **full backend mode** (`mcp_fast_mode=false`).
5. If **`UAC_Check` missing** → MCP returns `generation_mode: blocked`. Add label and re-run, **or** pipeline dev override `--skip-uac-label-gate` (local/tests only).
6. If **`UAC_Check` present** (or pipeline skip) → save `{KEY}-full-rag-packet.md`, read Pre-UAC from draft/JSON, write compact `{KEY}-test-plan.md`.
7. **Sign-off checks (AC):** plain-English bullets from Jira Expected/Actual when **`UAC_Done`** is present; otherwise keep AC provisional and plan **Draft**.

## Deliverables

| File | When |
| --- | --- |
| `{KEY}-full-rag-packet.md` | After successful full RAG run (`UAC_Check` present or pipeline skip gate) |
| `{KEY}-test-plan-pipeline-draft.md` | Pipeline machine draft — includes **Pre-UAC section 0** |
| `{KEY}-pipeline-result.json` | Full pipeline JSON — `pre_uac_product_brief`, score, QE handoff |
| `{KEY}-test-plan.md` | Compact QE plan from packet + skill (≤195 lines); KB distilled into EB-* |

## Dev override (local/tests only)

```bash
GUIDES_TEST_PLAN_SKIP_UAC_LABEL_GATE=1
```

Never use in production QA workflow.
