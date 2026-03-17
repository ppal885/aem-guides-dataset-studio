# Self-Learning and Self-Realization Design

## Overview

**Self-learning**: The system improves from feedback (user corrections, validation failures) without manual retraining.

**Self-realization**: The system detects its own mistakes and adjusts behavior—e.g., "I routed wrong; for similar evidence I should route to X instead."

---

## Current State (What Exists Today)

### 1. Feedback Collection

| Source | What is stored |
|--------|----------------|
| **User feedback** | `thumbs_up`, `thumbs_down`, `wrong_recipe` + `expected_recipe_id` |
| **Validation failures** | `validation_errors`, `eval_metrics`, `suggested_updates` |
| **Auto-stored on generate** | `RunFeedback` for success and failure (jira_id, scenario_id, recipes_used, selected_feature, selected_pattern) |

### 2. Feedback Aggregation

- **`aggregate_feedback_insights()`**: Recipe failure counts, wrong-recipe corrections, recommendations
- **`compute_prompt_overrides_from_feedback()`**: Deprioritize failing recipes, prefer expected recipes, append rules
- **`_build_routing_overrides_from_corrections()`**: Build `jira_evidence_keywords` (keyword → recipe) from wrong-recipe corrections

### 3. Where Overrides Apply

| Component | Override type | Effect |
|-----------|---------------|--------|
| **mechanism_classifier** | `jira_evidence_keywords` → mechanism | When evidence matches keyword, use override mechanism |
| **recipe_router** | `jira_evidence_keywords` → recipe_id | When evidence matches, return override recipe |
| **signal_prior_service** | `jira_evidence_keywords` → mechanism boost | Boost mechanism score for override |
| **ai_planner** | `deprioritize_recipes`, `append_rules`, `prefer_recipes` | Planner avoids/prefers recipes |
| **feedback_loop_placeholder** | `suggested_updates` for same jira_id | Injects historical fixes into planner prompt |

### 4. Auto-Apply

- `AI_AUTO_APPLY_FEEDBACK=true` (default): On `POST /feedback/submit`, automatically runs `compute_prompt_overrides_from_feedback()` and saves to `prompt_overrides.json` and `routing_overrides.json`.

---

## How Self-Learning Should Work (End-to-End Flow)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. GENERATE                                                                  │
│    User runs generate-from-jira → pipeline selects recipe → executes        │
│    → validation passes/fails → RunFeedback stored (auto)                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. FEEDBACK                                                                  │
│    User: thumbs_down + expected_recipe_id="task_topics"                      │
│    OR: Validation failure → feedback_analysis suggests fixes                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. AGGREGATION (compute_prompt_overrides_from_feedback)                       │
│    - wrong_recipe_corrections: (recipe_used, expected) → infer keywords      │
│    - recipe_risk: failing recipes → deprioritize                              │
│    - recommendations → append_rules                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. PERSISTENCE                                                               │
│    - routing_overrides.json: jira_evidence_keywords, deprioritize_for_evidence│
│    - prompt_overrides.json: deprioritize_recipes, append_rules, prefer_recipes│
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. NEXT RUN (self-realization)                                               │
│    Same/similar Jira → mechanism_classifier/recipe_router load overrides      │
│    → evidence matches keyword → override recipe used                         │
│    → "I learned: for 'steps' + 'cmd' I should use task_topics"               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## How Self-Realization Should Work

**Self-realization** = the system "realizes" it made a mistake and corrects future behavior.

### A. Keyword-Based Realization (Current)

1. User says: "Wrong recipe. Expected: `task_topics`."
2. System has heuristic: `(keys.keydef_basic, task_topics)` → keywords `["steps", "cmd", "task"]`
3. Adds `"steps" → task_topics` to `jira_evidence_keywords`
4. Next run: Evidence contains "steps" → `_route_from_override()` returns `task_topics`

**Gap**: Heuristics are hardcoded in `_WRONG_RECIPE_KEYWORD_HINTS`. New (recipe_used, expected) pairs need manual hints.

### B. Evidence-Based Realization (Enhancement)

1. Store `evidence_text` (or hash) with each wrong-recipe correction
2. On routing: retrieve similar past evidence → if past correction exists, use expected_recipe
3. Uses embedding similarity or keyword overlap

### C. Validation Failure Realization (Partial)

1. Validation fails → `feedback_analysis_service` suggests fixes
2. `suggested_updates` stored in RunFeedback
3. Same jira_id re-run → `get_aggregated_feedback_for_prompt()` injects historical fixes into planner
4. Planner "realizes" past errors and avoids them

---

## Recommended Enhancements for Stronger Self-Learning

### 1. Extract Keywords from Evidence (Not Just Heuristics)

**Current**: `_WRONG_RECIPE_KEYWORD_HINTS` has fixed mappings.

**Enhancement**: Use LLM or simple NLP to extract discriminative keywords from evidence when user corrects:
- Input: evidence_text, recipe_used, expected_recipe_id
- Output: list of keywords that, when present, should route to expected_recipe
- Store in routing_overrides

### 2. Evidence Similarity for Override

**Enhancement**: When routing, check if current evidence is similar to past wrong-recipe evidence:
- Embed evidence (or use TF-IDF)
- Query: "past evidence where expected_recipe was X"
- If similar and user said expected=X, override to X

### 3. Automatic Feedback from Validation Failure

**Current**: RunFeedback is stored, but `expected_recipe_id` is only set by user.

**Enhancement**: When validation fails, use `feedback_analysis_service` to suggest a better recipe. Store as `suggested_recipe_id`. If user confirms (or after N similar failures), promote to routing override.

### 4. Confidence-Based Self-Correction

**Enhancement**: When mechanism/pattern confidence is low, query feedback: "Have we seen similar evidence with a correction?" If yes, use that recipe instead of generic fallback.

### 5. Periodic Retraining (Future)

**Current**: `recipe_feedback_pairs` exports (evidence, recipe_id, label) for eval.

**Enhancement**: Use pairs to fine-tune recipe retriever or mechanism classifier. Requires training pipeline and model versioning.

---

## Configuration

| Env var | Purpose |
|---------|---------|
| `AI_AUTO_APPLY_FEEDBACK` | When true, feedback submit auto-applies overrides (default: true) |
| `routing_overrides.json` | Path: `{storage}/routing_overrides.json` |
| `prompt_overrides.json` | Path: `{storage}/prompt_overrides.json` |

---

## API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /feedback/submit` | Submit thumbs up/down, expected_recipe_id |
| `GET /feedback/insights` | Aggregate insights (recipe risk, wrong corrections) |
| `POST /feedback/apply-overrides` | Manually run compute + save overrides |
| `POST /feedback/export-pairs` | Export (evidence, recipe, label) for training |
| `POST /generate-from-feedback` | Re-run with force_recipe_id from feedback |

---

## Summary

| Concept | Current behavior | Enhancement (Implemented) |
|---------|------------------|---------------------------|
| **Self-learning** | Feedback → overrides → next run uses overrides | Extract keywords from evidence (LLM + simple NLP); evidence similarity pairs |
| **Self-realization** | Override applies when keyword matches | Evidence similarity override (Jaccard); confidence-based correction (lower threshold when low confidence) |
| **Automatic** | Auto-apply on submit; auto-store RunFeedback on generate | Auto-suggest recipe from validation failure; promote when 2+ similar failures |

## Implemented Enhancements (Gaps Addressed)

1. **Keyword extraction from evidence**: `keyword_extraction_service.py` - LLM when available, else `_extract_keywords_simple()`. Used in `_build_routing_overrides_from_corrections` when evidence_text is present.

2. **Evidence similarity for override**: `feedback_evidence_service.py` - `find_similar_feedback_recipe()` using Jaccard similarity. `evidence_similarity_pairs` stored in `routing_overrides.json`. `recipe_router` checks similarity before keyword override.

3. **Automatic suggested_recipe from validation failure**: `RunFeedback.suggested_recipe_id` added. `feedback_analysis_service` maps recipe_hints to recipe IDs. Promoted to routing when 2+ failures for same jira_id + suggested_recipe_id.

4. **Confidence-based self-correction**: In `recipe_pipeline_service`, when low_confidence + keys.keydef_basic, checks `find_similar_feedback_recipe` with threshold=0.15 before overriding to llm_generated_dita.
