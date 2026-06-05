---
name: qa-studio-planner
description: >
  Generate AEM Guides QA automation test plans and Behave/Page Object code from
  JIRA tickets. Use this skill whenever a user wants to create test automation for
  AEM Guides features: "generate a test plan for AG-1234", "create automation
  scenarios for this Jira ticket", "write Behave feature files for X", "generate
  page object for the DITA editor", "automate testing for this bug fix",
  "create QA plan from this ticket", "generate step definitions for AG-5678",
  "build automation coverage for this feature", or any time someone describes
  an AEM Guides feature, bug, or workflow and wants automated tests for it.
  Always use this skill before attempting to write test code manually.
---

# QA Studio Planner

This skill drives the QA Studio pipeline: **Plan → Review → Generate**.
It turns a JIRA ticket (or a plain description) into a Behave-style automation plan,
then generates feature files, step definitions, and Page Object stubs.

---

## 1. Collect Inputs

You need at least ONE of these to start:

| Input | How user provides it | Required? |
|---|---|---|
| **JIRA key** | e.g. `AG-1234` | Preferred — enables full enrichment |
| **Summary** | Title of the feature/bug | Required if no JIRA key |
| **Description** | What the feature does | Strongly recommended |
| **Acceptance Criteria** | What must be true to pass | Best source for scenario titles |
| **Repro steps** | For bug tickets | Optional but improves scenario quality |
| **Target area** | e.g. "DITA Editor", "Output Presets", "Map Editor" | Optional |

If the user gives a JIRA key, call `search_jira_issues` first to retrieve the ticket
details. Extract summary, description, and acceptance criteria from the result.

If critical inputs are missing (no summary, no description, no ACs), ask one targeted
question: *"Can you share the acceptance criteria or a brief description of what
should be tested?"*

---

## 2. Call the Plan Endpoint

**Endpoint:** `POST /api/v1/qa-studio/plan`

```json
{
  "jira_key": "AG-1234",
  "jira_summary": "<ticket title>",
  "jira_description": "<full description text>",
  "acceptance_criteria": "<ACs from ticket>",
  "repro_steps": "<steps to reproduce, for bugs>",
  "expected_behavior": "<what should happen>",
  "target_area": "DITA Editor"
}
```

The endpoint returns one of two shapes:

**Blocked** (missing critical info):
```json
{ "blocked": true, "blocking_questions": ["What UI panel is involved?", ...] }
```
→ Show the questions to the user and ask them to answer before proceeding.

**Plan ready**:
```json
{
  "blocked": false,
  "plan_draft": {
    "feature": "...",
    "scenarios": [
      { "title": "...", "given": [...], "when": [...], "then": [...] }
    ],
    "page_objects": ["DitaEditorPage", ...],
    "assertions": [...]
  }
}
```

---

## 3. Present the Plan

Show the plan clearly before generating code:

```
## Test Plan: [feature name]

**Scenarios ([N] total):**
1. [scenario title] — [one-line description]
2. ...

**Page Objects needed:** [DitaEditorPage, MapEditorPage, ...]
**Assertions:** [N] verifiable assertions traced to ACs

Does this look right? If yes, I'll generate the full Behave feature files,
step definitions, and page object stubs.
```

Give the user a chance to:
- Remove scenarios they don't need
- Add missing coverage ("also test the error state")
- Change the target area or page objects

---

## 4. Generate the Code

**Endpoint:** `POST /api/v1/qa-studio/generate`

Pass the approved plan back:
```json
{
  "plan": { /* the plan_draft object from step 2 */ },
  "jira_key": "AG-1234",
  "jira_summary": "<same as plan step>",
  "acceptance_criteria": "<same as plan step>"
}
```

The response contains:
- `feature_file` — Behave `.feature` file with Given/When/Then scenarios
- `step_definitions` — Python step def file
- `page_objects` — Page Object class stubs
- `validation_report` — assertion traceability, locator quality checks

---

## 5. Present the Output

Show each artifact in a fenced code block with the file type:

````
**`features/ag_1234_dita_editor.feature`**
```gherkin
Feature: [feature title]
  ...
```

**`steps/ag_1234_steps.py`**
```python
from behave import given, when, then
...
```

**`pages/dita_editor_page.py`**
```python
class DitaEditorPage:
    ...
```
````

Then show the validation report:
- Assertion traceability: N/N ACs covered
- Locator quality: any warnings about brittle selectors

---

## 6. QA Studio Modes

| Env flag | Behavior |
|---|---|
| `QA_STUDIO_LLM_AUTHORING=false` (default) | Returns a **stub plan** only — use as a template |
| `QA_STUDIO_LLM_AUTHORING=true` | Full LLM-authored plan + code generation |

If the user gets stub output, tell them:
*"LLM authoring isn't enabled — this is a template to fill in. Ask your admin
to set `QA_STUDIO_LLM_AUTHORING=true` in the backend `.env` for full generation."*

---

## 7. Example Flows

**From JIRA key:**
> "Generate a test plan for AG-2091 — conref on note elements."

1. `search_jira_issues("AG-2091")` → retrieves ticket
2. `POST /api/v1/qa-studio/plan` with extracted fields
3. Present plan (e.g. 3 scenarios: basic conref, conref with type override, invalid conref)
4. User approves → `POST /api/v1/qa-studio/generate`
5. Show feature file + step defs + page object

**From description only:**
> "I need automation for the DITA map editor — opening a map, adding topicrefs, saving."

1. No JIRA key → use description directly
2. `POST /api/v1/qa-studio/plan` with `jira_summary="DITA map editor: open, add topicrefs, save"`, `target_area="Map Editor"`
3. Continue as above
