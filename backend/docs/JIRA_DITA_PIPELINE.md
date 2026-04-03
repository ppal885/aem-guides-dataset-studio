# Jira → DITA generation pipeline

This document describes how a Jira issue becomes a DITA dataset in this repository. It is aimed at contributors who work on prompts, recipes, or validation—not end users.

## End-to-end flow

1. **Evidence** — The API or pipeline loads a Jira **evidence pack** (summary, description, optional Representative Sample XML, similar issues).

2. **Scenario expansion** — `expand_scenarios` in `app/services/ai_planner_service.py` may produce multiple scenarios; the deterministic **recipe pipeline** typically uses a single `S1_MIN_REPRO` scenario.

3. **Mechanism and pattern classification** — `run_recipe_pipeline` in `app/services/recipe_pipeline_service.py` runs:
   - `classify_mechanism` → high-level feature (e.g. `keyref`, `table_content`, `inline_formatting`).
   - `classify_pattern` → specific pattern within that feature (keyword/LLM-assisted).

4. **Recipe routing** — `route_recipe` in `app/services/recipe_router.py` maps `(feature, pattern)` to a **recipe id** using `ROUTE_TABLE` in `app/services/recipe_scoring_service.py`. Feedback overrides (keywords, similar past evidence) can change the route.

5. **Content from evidence** — `generate_content_from_evidence` loads `content_from_evidence.txt`, merges **RAG** (`retrieve_dita_knowledge`, optional graph/AEM docs), and combines LLM extraction with **Representative Sample** XML from `app/utils/evidence_extractor.py`. Output fields (e.g. `representative_xml`, `content_steps`) are passed as **recipe params**.

6. **Planner (agentic path)** — When the agentic stack is used, `plan_for_scenario` in `ai_planner_service.py` reads `generator_invocation_planner.txt` (plus optional `jira_to_recipe_selection_rules.txt`). The planner receives **candidate recipes** from `retrieve_recipe_candidates` in `app/services/recipe_retriever.py`, which scores specs from `discover_recipe_specs()` in `app/generator/recipe_manifest.py`. It returns a `GeneratorInvocationPlan` (one or more `SelectedRecipe` entries with params).

7. **Execution** — `execute_plan` in `app/services/ai_executor_service.py` resolves each `recipe_id` to a `RecipeSpec`, imports `module.function`, and passes sanitized params. Generated files are written under the job output directory with `safe_join` path checks.

## LLM fallback: `llm_generated_dita`

When no catalog recipe fits, or `evidence_mentions_novel_construct` forces it, the pipeline selects **`llm_generated_dita`** (`app/generator/llm_dita_generator.py`). That path:

- Loads **`llm_dita_generator.txt`** (global rules: JSON-only output, DITA roots, minimal file count).
- Appends **pattern-specific hint modules** composed by `app/services/jira_dita_pattern_hints.py` from `app/templates/prompts/pattern_modules/*.txt` when the issue text matches registered patterns (keeps the base prompt small).
- Pulls **RAG** (DITA spec chunks, optional DITA graph, optional AEM Guides docs when trigger terms match).
- Optionally runs **post-generation pattern validators** (`app/services/llm_dita_pattern_validators.py`) and a **single repair retry** when enabled via environment variables (see that module and `llm_dita_generator.py`).
- Optionally logs **term overlap** warnings when `LLM_DITA_CONTENT_FIDELITY_ENABLED` is set.

## Recipes vs LLM-only

| Approach | When to use | Where it lives |
|----------|-------------|----------------|
| **Deterministic recipe** | Repeated structure (tables, keyref chains, RTE nesting) with stable output | `app/generator/*.py` + `RECIPE_SPECS`, `ROUTE_TABLE` |
| **Planner-selected recipe** | Heterogeneous Jira text; LLM chooses from retrieved candidates | `generator_invocation_planner.txt`, `recipe_retriever.py` |
| **LLM DITA generator** | Novel constructs (`topicset`, `navref`, `bookmap`, …) or no match | `llm_dita_generator.py` + pattern modules |

**Guideline:** Prefer promoting a recurring pattern to a **recipe** and a **routing rule** over adding more bullets to `llm_dita_generator.txt`. Use **pattern modules** for fallback-only nuance and **validators** to catch systematic misses.

**Example:** `table_semantics_reference` (`app/generator/table_semantics_recipe.py`) is routed from `(table_content, table_alignment_reference)` in `ROUTE_TABLE` for alignment-focused issues, while width/layout-heavy issues still use `heavy_topics_tables_codeblocks`.

## Related files

- Pipeline orchestration: `recipe_pipeline_service.py`, `ai_planner_service.py`
- Recipe catalog: `recipe_manifest.py`, `discover_recipe_specs()`
- Feedback and overrides: `feedback_aggregation_service.py` (`load_prompt_overrides`, routing keywords)
- Prompts: `backend/app/templates/prompts/`
