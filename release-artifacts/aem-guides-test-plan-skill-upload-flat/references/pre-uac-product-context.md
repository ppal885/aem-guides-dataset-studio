# Pre-UAC product context (read before sign-off checks)

**Pre-UAC** explains the **AEM Guides product area** (Baseline, Asset Status API, Publishing, Web Editor, etc.) **before** PM/QA write or validate acceptance criteria. It is **not** a substitute for Jira Expected Result — it gives shared vocabulary and documented behavior so UAC discussions are grounded.

## When this runs

| Mode | Pre-UAC source |
| --- | --- |
| **Unified pipeline** (preferred) | Auto — stage `pre_uac_product_brief` after RAG + ticket intake |
| **Manual skill workflow** | Agent must read `{KEY}-pipeline-result.json` → `pre_uac_product_brief`, or `{KEY}-test-plan-pipeline-draft.md` section **0**, or run pipeline first |

**CLI:**

```powershell
python C:/Users/prashantp/Videos/aem-guides-dataset-studio/scripts/run_test_plan_pipeline.py GUIDES-52248 --write-starling --skip-uac-label-gate
```

**MCP / HTTP:** `test_plan_pipeline(jira_key, write_starling_artifacts=true, skip_uac_label_gate=true)` — prefer CLI/HTTP for full RAG (stdio may timeout).

## Three layers (how behavior is decided)

| Layer | IDs in draft | Source | Use in refined plan |
| --- | --- | --- | --- |
| **Curated product facts** | **KB-*** | Topic catalog in `pre_uac_product_brief_service.py` | Distill into **EB-*** bullets (section 2 supplementary) |
| **Ranked RAG evidence** | **DB-*** | Experience League + learned Swagger chunks, topic-focused query + scoring | Cite in **Where we got the facts**; prefer EL over raw OpenAPI JSON |
| **Ticket + PM questions** | **PU-*** | Jira current/expected + rule-based clarifications | **Blocking sign-off today** or PM questions until answered |

### Topic detection

Jira text (summary, description, labels, components) is keyword-scored against a catalog:

- `baseline`, `baseline table`, `version comment` → **AEM Guides Baseline**
- `/assets/status`, `asset status` → **Asset Status API**
- `publish`, `output preset` → **Publishing**
- `web editor`, `ui_config` → **Web Editor**

Primary topic drives curated **KB-*** bullets and supplemental RAG query terms.

### RAG ranking rules (baseline example)

**Promote:** Experience League “Work with Baseline”, filter/CSV/column/table UI text.

**Demote:** raw `{ "type": "object" }` Swagger DTO dumps, **Reports / Translation API** when primary topic is baseline (unless explicitly baseline-related), CSS `vertical-align:baseline` false positives.

**Display:** raw scrape chunks are cleaned — whitespace collapsed, OpenAPI JSON summarized to one line (e.g. "OpenAPI schema for BaselineExportRequestDto — use for export contract checks").

## Pipeline draft vs compact test plan

| Artifact | Pre-UAC | Length |
| --- | --- | --- |
| `{KEY}-test-plan-pipeline-draft.md` | Full **section 0** (KB + DB + PU) | Long — machine draft |
| `{KEY}-test-plan.md` (QE deliverable) | **No separate section 0** — fold KB into EB-*; PU into blocking items | ≤195 lines |

**Agent rule:** After pipeline draft, **refine** into compact `{KEY}-test-plan.md`. Do not paste all of section 0 into the final plan — testers need action items first (section 1).

## Order relative to UAC label gate

1. **Pre-UAC** — product context (always in pipeline when not blocked)
2. **UAC intelligence** — acceptance analysis, PM/QA questions
3. **Sign-off checks (AC-*)** — only when Jira has **`UAC_Done`** or agreed Expected Result

**`UAC_Check` gate:** still required for production full RAG via `guides_test_plan_generator`. Pipeline dev override: `--skip-uac-label-gate` or `skip_uac_label_gate=true` (local/tests only).

## What agents must do

1. Run pipeline (or read existing `{KEY}-pipeline-result.json`).
2. Read **section 0** / `pre_uac_product_brief` before writing AC or EB bullets.
3. For feature requests with empty Expected Result, treat **PU-*** as mandatory PM alignment — plan stays **Draft**.
4. Convert **KB-1…KB-n** into plain-English **EB-*** expected behaviour (5–7 bullets max).
5. Use **DB-*** URLs as traceability in “Where we got the facts” — not as Jira facts.

## Example (GUIDES-52248 — Baseline)

**KB (curated):** Version comment is OOTB topic metadata; Baseline table columns are fixed today; filter + CSV export exist.

**DB (RAG):** Experience League “Work with Baseline”, baseline v2 data model pages.

**PU (clarify before UAC):** Web Editor v2 vs legacy dashboard scope; column vs export-only; filter/sort/CSV must include new column?
