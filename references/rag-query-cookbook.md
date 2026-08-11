# RAG Query Cookbook

Use this file before calling or judging `ask_dita_expert`.

## Query Set

Run focused queries from normalized behaviour:

- **Exact failure**: `<Jira key or exact error/user symptom> in AEM Guides <area/workflow>`
- **Exact API/config/UI/construct**: `<api path/config key/UI label/DITA construct> <expected verb> <boundary term>`
- **Expected workflow**: `How should <workflow> behave in AEM Guides when <condition/config/version> applies?`
- **Boundary/config**: `What are the rules for <configuration/permission/version/data-shape> in <workflow>?`
- **Regression**: `Which nearby AEM Guides workflows can be affected by <changed area/API/component>?`

Always run at least three probes for behaviour-sensitive tickets:

- Exact probe with the precise API route, config key, UI label, DITA element/attribute, error text, or release version.
- Workflow probe with the user action and expected product surface.
- Boundary probe with platform, role, version, config, data-shape, or output/preset constraints.

If the first probe is noisy, tighten the query with exact tokens instead of broad prose. For example, prefer `ignored.post.processing.paths enabled.post.processing.paths rules child successors same folder ignored wins` over a long generic question about folder postprocessing.

For DITA element / output-preset discrepancy questions:

Follow the three-source protocol in `references/dita-spec-evidence.md`. The three query intents are separate — mix them and you get noisy, unusable chunks:

- **Spec probe** (DITA 1.3 normative): `DITA 1.3 spec <element-name> normative shall must included processing`
  - Accept chunks that contain "shall", "must", content model, or usage constraints.
  - Reject chunks that only describe element syntax or valid parent/child without processing requirements.
- **DITA-OT benchmark probe**: `DITA-OT <element-name> <output-type> processing included unconditional`
  - DITA-OT PDF is the primary assertion oracle for output correctness.
  - Accept chunks describing DITA-OT transformation behavior for that element.
  - Reject generic DITA-OT install or plugin docs.
- **AEM Guides product probe**: `AEM Guides <element-name> <output-preset> behavior expected`
  - AEM Guides presets in scope: AEM Sites (new), AEM Sites (legacy), HTML5, Native AEM Site, Native PDF, DITA-OT PDF.
  - Accept chunks describing how AEM Guides handles the element in the named preset.
  - Reject chunks that describe the same element in a different preset and claim cross-preset equivalence.

Do not accept an attribute chunk as proof for an element, or generic DITA docs as proof for AEM Guides UI behaviour.
Do not accept AEM Guides documentation for one output preset as proof of behavior for a different output preset — the pipelines differ.

## Accept Evidence When

- It names the same workflow, element, attribute, configuration, release note, API, UI area, or product feature.
- It explains expected behaviour, constraints, side effects, permissions, or version boundaries.
- It directly changes a scenario, expected result, regression area, or AC interpretation.
- It has a credible source title/URL or clear corpus origin from the VM RAG response.
- It appears in top results with exact feature/API/config/source overlap, not just broad semantic similarity.
- For release behaviour, it is the latest matching current doc unless the Jira is explicitly about an older release, upgrade, or regression history.

## Reject Evidence When

- It only matches broad words such as `topic`, `map`, `assets`, `metadata`, `cloud`, `workflow`, `translation`, `baseline`, or `report`.
- It describes a different product surface than the Jira/PR.
- It is generic DITA/DITA-OT guidance but the claim is about AEM Guides UI/AEM Sites behaviour.
- It is release-note text that does not mention the affected behaviour or nearby component.
- It conflicts with Jira facts or inspected PR diff.
- It is an older release note that only matches generic product terms while newer/current docs cover the same area more directly.
- It names a related feature area but not the exact API/config/UI/DITA behaviour being claimed.

## How To Use RAG In The Plan

- Convert accepted RAG into short behaviour facts, not citations dumps.
- Put supported facts under `Expected Behaviour` or coverage impact under `Regression Areas`.
- If RAG does not support the claim, write `Unknown from current evidence` or `Draft blocker: RAG did not confirm expected behaviour`.
- Never phrase unsupported RAG as certainty.
- If RAG returns mixed useful and noisy chunks, keep only the exact-matching chunks and say unrelated chunks were rejected internally.
- If all top chunks are generic release-note or validation-oracle text, mark RAG as noisy and do not use it as behaviour proof.

## Good vs Noisy Examples

Good:

- Jira is about postprocessing path enable/ignore rules, and RAG returns exact rules for `ignored.post.processing.paths` and `enabled.post.processing.paths`.
- Jira is about AEM Guides release behaviour, and RAG returns a matching release note or upgrade instruction.
- Jira is about a DITA element, and RAG returns the exact element reference and valid parent/child rules.

Noisy:

- Jira is about metadata schema editing, and RAG returns a generic assets metadata overview without edit behaviour.
- Jira is about AEM Sites title rendering, and RAG returns only DITA `<title>` or `<searchtitle>` syntax with no AEM Sites mapping.
- Jira is about an API regression, and RAG returns only UI workflow documentation.
