---
name: aem-guides-test-scenario-generator
description: >
  Generate bug-discovery-first Adobe AEM Guides QA test plans and DITA construct test scenarios using
  JIRA evidence, VM RAG/documentation/spec evidence, repository evidence, DITA registries, DITA-OT
  GitHub RAG, and AEM Guides Jira index. Use this skill when the user asks for a test plan, QA
  scenarios, bug discovery, regression prevention, test coverage, test matrix, blast-radius/risk analysis, automation strategy, or known
  bugs for AEM Guides work or any DITA element/attribute/tag such as <indexterm>, conref, @keyref,
  @collection-type, required-cleanup, topicref, @keyscope, or choicetable. The skill requires
  mandatory blast-radius, bug-hypothesis, kill-the-fix, oracle, historical-regression, and residual-risk analysis before scenario generation for every JIRA/bug/enhancement/
  regression/refactor/configuration/infrastructure change; do not use it for generic testing
  requests unrelated to DITA/AEM Guides.
---

# AEM Guides Test Scenario Generator

This skill's primary objective is bug discovery and regression prevention. Test cases are the output format, not the goal. For JIRA-driven work, preserve the evidence ledger, JIRA MCP workflow, central VM RAG retrieval, scraped Experience League DITA learned-behavior evidence, repository analysis, blast-radius analysis, regression rings, automation mapping, and Markdown validation. For standalone DITA construct requests, remain grounded in this project's real spec registries and RAG indexes, not invented memory.

Everything here runs as short Python snippets against the backend's own services (the same
mechanism used throughout this project's development), from `backend/`:

```bash
cd C:/Users/prashantp/Videos/aem-guides-dataset-studio/backend
./.venv/Scripts/python.exe - <<'PY'
from dotenv import load_dotenv
load_dotenv(".env")
# ... snippet body from the sections below ...
PY
```

(On a non-Windows checkout, use `.venv/bin/python` instead of `.venv/Scripts/python.exe`.)

---


## Mandatory workflow for JIRA-driven plans

For every JIRA, do not move directly from issue analysis to test-case generation. Use this blocking
sequence:

1. JIRA intake from Adobe JIRA MCP.
2. Evidence collection from the central VM MCP/RAG and repository tools.
3. RAG retrieval for AEM Guides docs, scraped Experience League DITA learned-behavior chunks, DITA 1.2/1.3, DITA-OT, and explicitly allowlisted corpora.
4. Implementation, diff, and automation repository inspection.
5. **Blast-radius analysis gate**.
6. **Bug Hypothesis Register** from `references/bug-discovery-heuristics.md`.
7. **Kill the Fix** analysis when a diff exists.
8. Historical regression analysis from `references/historical-regression-analysis.md`.
9. Interaction matrix, failure injection, and multi-layer oracles from `references/test-oracles-and-fault-injection.md`.
10. Scenario design, automation-strength classification, regression pack split, exploratory charters, residual risk, and validation.

Before risk/scenario selection for any bug, enhancement, regression, behavior change, refactor, dependency update, configuration change, or infrastructure JIRA, read `references/blast-radius-analysis.md`, `references/bug-discovery-heuristics.md`, `references/historical-regression-analysis.md`, `references/test-oracles-and-fault-injection.md`, and `references/output-template.md`. Produce `## 4. Blast radius and risk analysis` first, then the Bug Hypothesis Register and related sections using the exact table structures in `references/output-template.md`.

If blast-radius, bug-hypothesis, kill-the-fix applicability, historical-regression search, multi-layer oracle, automation-strength, or residual-risk analysis is missing or incomplete, keep the plan in **Draft** and do not call it review-ready.

### Scraped Experience League DITA behavior evidence

When the MCP packet contains `learned_behavior_evidence`, treat it as the product-behavior bridge between documentation and QA design:

- Use it to write the Requirement and behavior summary before selecting scenarios.
- Extract documented feature behavior, detected DITA constructs/attributes, publishing/output contexts, generation requirements, QA checklist items, PDF review areas, HTML5 review areas, negative/risk cases, and validation oracles.
- Cite `source_url` or `canonical_url` from each chunk in the Evidence map.
- Convert behavior chunks into test-data and oracle requirements; do not merely list them as sources.
- If scraped behavior evidence is unavailable, weak, or unrelated, mark the plan **Draft** and list the missing evidence under Residual Risk.
- Do not treat scraped docs as Jira facts or implementation diffs; use them as expected behavior/product documentation evidence only.

When the MCP packet contains `planning_seeds`, it is not optional guidance. Use the four seed lists as mandatory inputs:

- `blast_radius_seed` → populate `## 4. Blast radius and risk analysis` before scenario design.
- `bug_hypothesis_seed` → populate `## 5. Bug hypothesis register` and negative/failure-injection scenarios.
- `test_area_seed` → drive `## 9. Prioritized scenarios` and `## 10. Detailed test scenarios`.
- `regression_risk_seed` → drive regression ring/pack split and residual risk.

Every P0/P1 seed must map to a scenario ID or an evidence-backed exclusion. If a seed cannot be used because repository/Jira/RAG evidence is missing, keep the plan **Draft** and list the exact missing evidence.

For DITA construct-only requests without a JIRA, still use the original tag workflow below; if the
user also asks for a test plan tied to product/code change, apply the blast-radius gate.

---

## 1. Resolve the tag — never invent facts

Before writing a single scenario, pull real, grounded facts about the tag. A tag may be an
element, an attribute, or (rarely) both — check both registries:

```python
from app.services.dita_spec_registry_service import get_element_spec, list_element_names
from app.services.dita_attribute_catalog import get_attribute_spec, list_attribute_names, build_test_scenarios

tag = "indexterm"  # strip any leading @ or <> the user typed

element_spec = get_element_spec(tag)
attr_spec = get_attribute_spec(tag)

print("element known:", element_spec is not None)
print("attribute known:", attr_spec is not None)
```

- If `element_spec` is found: use its `description`, `parent_element`, `allowed_children`,
  `allowed_parents`, `supported_attributes`, `attribute_usage`, `usage_contexts`,
  `common_mistakes`, `correct_examples` as the seed facts for every section below.
- If `attr_spec` is found: use its `text_content`/description, `all_valid_values`,
  `supported_elements`, `combination_attributes`, `default_scenarios`, `common_mistakes`, and
  call `build_test_scenarios(tag, elements=attr_spec.supported_elements[:4], mentioned_values=attr_spec.all_valid_values)`
  for an initial, code-generated scenario seed list — expand these into the full
  ID/title/test-data/preconditions/steps/expected-result shape, don't just paste the raw strings.
- **If neither resolves:** say so plainly — "`<tag>` isn't in the current DITA spec registry
  (checked `list_element_names()`/`list_attribute_names()`)." Then either ask the user to
  confirm the exact tag name, or (only if they insist) produce a scenario document explicitly
  labeled as based on general DITA-spec knowledge rather than this project's grounded registry,
  and flag every claim in it for verification. **Never present an unregistered/made-up tag as
  if it were a confirmed, spec-grounded DITA construct.**

If the fact set feels thin (e.g. a real element with almost no `usage_contexts`/`common_mistakes`
populated), say so in the output rather than padding it with invented detail.

---

## 2. Build the scenario document

**Always read `references/category-taxonomy.md` in full before writing scenarios** — it is not
optional background reading, it is the actual checklist (functional, XML persistence,
multiplicity/duplicates, nesting, attribute coverage, negative, boundary, special characters,
Unicode/localization, whitespace, profiling/filtering, reuse, map-level, publishing, performance/scale,
concurrency, editor regression, error handling, automation feasibility). Work through it category by
category, using the grounded facts from Step 1 as the actual content — e.g. only write nesting
scenarios if `allowed_children`/`parent_element` show the element can actually self-nest; only write
attribute-coverage scenarios for attributes the tag really supports.

**Publishing (Native PDF / DITA-OT PDF) is gated, not automatic:** include it whenever the tag —
element, attribute, metadata field, reference/reuse mechanism, or filtering behavior — can plausibly
affect published output (true for most DITA constructs). Skip it entirely when the feature is
strictly UI/editor-only with no publishing-side effect. State explicitly which case applies and
why (see `references/category-taxonomy.md` §N for the full rule).

**Every attribute needs a Processing Instruction note, not just value coverage:** for each attribute
in the Attribute Coverage section, explain *how the processor actually handles it at publish time* —
resolved at preprocessing (like `@conref`/`@keyref`) vs. carried through literally to output (like
`@outputclass`), whether it affects content inclusion/exclusion, navigation, or is purely cosmetic,
and whether Native PDF and DITA-OT are known to process it identically (see
`references/category-taxonomy.md` §E for the full rule — don't assume parity, flag unverified
processing behavior rather than guessing).

**Output structure** (mirrors the validated `<indexterm>` reference document):

```
# Complete Testing Scenarios: <tag>

## 1. Feature Understanding
## 2. Test Coverage Summary   (compact matrix table)
## 3. Detailed Test Scenarios (grouped by category, each with Scenario ID / title / test data
                                / preconditions / steps / expected result / validation layers)
## Critical Scenarios
## Regression Candidates
## Product-Specific Validation  (explicitly flag anything needing live product verification)
## Recommended Dataset          (proposed folder structure of topics/maps/ditaval exercising
                                  the scenarios — see Step 4 for actually generating it)
```

Use meaningful Scenario IDs (a short uppercase prefix derived from the tag + a number, e.g.
`IDX-001`, `KEYREF-001`, `CONREF-001`).

For anything that depends on the actual product/processor implementation rather than the DITA
spec itself (Native PDF vs. DITA-OT formatting differences, exact nesting depth limits, cache
invalidation behavior, etc.), explicitly write: *"Validate actual product behavior against the
applicable DITA specification and supported AEM Guides implementation."* Do not guess at
implementation-specific behavior and present it as fact.

---

## 3. Find related bugs (DITA-OT GitHub + Jira)

The DITA-OT GitHub RAG gates on a "is this about DITA-OT" heuristic that a bare tag name alone
won't reliably pass — synthesize a short sentence around the tag instead:

```python
from app.services.dita_ot_github_rag_service import retrieve_dita_ot_github_for_query
from app.services.jira_chat_search_service import search_related_jira_issues

github_issues = retrieve_dita_ot_github_for_query(f"DITA-OT known issues with {tag}", k=5)
jira_result = search_related_jira_issues(f"known issue with {tag}", tenant_id="kone", max_results=5)
```

- `github_issues` is a list of `{url, title, issue_number, snippet, source}` — `source` is
  `"dita_ot_github_reference"` for curated issues or `"dita_ot_github"` for indexed/live ones.
- `jira_result["issues"]` is the matched list; `jira_result["source"]` tells you whether it came
  from live Jira, the indexed cache, or is `"unavailable"`. Check `jira_result["message"]` too —
  it explicitly says when nothing matched.
- Use `tenant_id="kone"` by default (the project convention throughout this codebase); ask the
  user for a different tenant only if they mention one.
- **Report honestly.** If either search returns nothing, write "No known DITA-OT GitHub issues
  found for `<tag>`" / "No matching Jira issues found" — do not fabricate a plausible-sounding
  bug. This project has repeatedly hit and fixed bugs where a search silently surfaced
  unrelated results instead of admitting "no match" — don't reintroduce that failure mode by
  overclaiming here.

Add a `## Related Known Issues` section to the scenario document with two subsections:
**DITA-OT GitHub** and **AEM Guides Jira**, each listing real hits with their URLs/keys, or an
honest "none found" line.

---


---

## 3A. JIRA test-plan output requirements

For JIRA-driven plans, use `references/output-template.md` as the governing structure. The plan must
include the exact heading:

```markdown
## 4. Blast radius and risk analysis
```

The blast-radius section must come before scenario selection/generation. Every Direct, Shared-path,
Downstream, Compatibility, or Observability/Recovery risk that is critical/high priority must map to
a scenario or an explicit evidence-backed exclusion.

Final quality gates must fail or mark the plan Draft when:

- blast-radius section is absent;
- Bug Hypothesis Register is absent;
- direct or shared-path impact is not covered or excluded;
- changed/shared path was not investigated;
- critical downstream consumers are missing;
- existing unchanged behavior has no R0 control test;
- bug plans lack reproduction, negative, or recovery coverage;
- critical/high impact has no scenario or exclusion;
- scenarios do not trace back to risk, hypothesis, interaction, or evidence IDs;
- Kill the Fix coverage is missing when a diff was inspected;
- scenario oracles are vague (`no error`, `works correctly`) or single-layer where multi-layer evidence is needed;
- automation strength is not classified;
- exclusions have no reason/evidence;
- historical Jira search is missing or treated as specification;
- residual risk and release confidence are absent;
- suspected impact is presented as confirmed;
- unavailable code/RAG/JIRA evidence is silently replaced with assumptions or Review-ready status.

Run `scripts/validate_test_plan.py <plan.md>` before calling a JIRA-driven plan review-ready.

## 4. Optional: generate an actual downloadable test-data bundle

Only do this when the user explicitly asks for real sample files (not just the scenario
document) — e.g. "...and give me a sample dataset" / "...with test data I can publish". Reuse
the project's existing bundle pipeline rather than inventing a new one:

- `backend/app/services/bundle_builder_service.py::build_bundle()` — assembles a bundle
  directory with a manifest.
- `backend/app/services/dataset_packager_service.py::package_bundle()` — zips it for download.

Pick a small, representative subset of the scenarios from Step 3 (e.g. one basic positive case,
one negative case, one boundary case, one filtering case) to turn into real `.ditamap`/`.dita`/
`.ditaval` files — don't try to materialize every single scenario as a file; the scenario
document itself is the complete deliverable, the bundle is a representative sample.

---

## 5. Rules

**DO:**
- Ground every claim in `get_element_spec`/`get_attribute_spec`/`build_test_scenarios` output.
- Explicitly flag processor-dependent behavior for product verification.
- Report "none found" honestly for the bug-lookup section when that's the truth.
- Skip categories that are genuinely inapplicable to the tag, and say why.

**DO NOT:**
- Invent a content model, attribute, or DITA-OT/Jira bug that didn't come from the actual lookup.
- Treat an unregistered tag name as a confirmed DITA construct without flagging it.
- Pad thin grounded facts with generic filler text to look more complete.
- Materialize every scenario as a file when the user only asked for the document (Step 4 is
  opt-in, not automatic).
