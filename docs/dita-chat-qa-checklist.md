# DITA Chat QA Checklist

Use this checklist when validating DITA/AEM Guides chat answer quality after prompt, retrieval, or grounding changes.

## Goals

- Answer the user’s actual DITA question directly in the first 1–2 lines.
- Prefer construct-specific explanations over generic retrieval summaries.
- Include short XML only when it materially improves understanding.
- When XML is shown, prefer a full enclosing example (`<map>`, `<topic>`, `<table>`) over an isolated fragment when that extra context clarifies usage.
- Distinguish DITA spec behavior from DITA-OT runtime behavior.
- Keep answers useful even when live AI is unavailable.

## Must-pass checks

- The answer starts with the actual explanation, not with phrases such as `Retrieved...` or `Best available guidance...`.
- Element and attribute names are explicit, for example `` `<entry>` `` or `` `@morerows` ``.
- Comparison questions include a clear contrast, ideally in table form.
- How-to questions include steps or a concrete configuration example.
- Output/publishing questions distinguish:
  - DITA conditional processing / DITAVAL
  - AEM Guides output preset behavior
  - DITA-OT arguments such as `args.draft`
- If the answer uses XML, the snippet is structurally plausible and scoped to the user’s question.
- If the user asked for an example, the snippet is complete enough to copy and understand without guessing the missing parent structure.
- Offline/local fallback still returns a useful answer, not only a retrieval dump.

## Reject if

- The answer labels a concept incorrectly, for example calling `@morerows` a `simpletable` feature.
- The answer routes a DITAVAL filtering question into generic DITA-OT CLI advice.
- The answer gives only sources or bullet fragments without a direct explanation.
- The answer invents unsupported nesting or invalid DITA markup.
- The answer mixes authoring guidance and runtime transform guidance without stating the difference.

## Golden prompts

### Prompt 1
`What did morerows attribute do in table?`

Expected answer must mention:

- `@morerows` spans a CALS table `<entry>` vertically
- current row + additional rows
- not `<simpletable>`
- full table context, not only bare `<row>` fragments

### Prompt 2
`How do I exclude draft-only content at publish time?`

Expected answer must mention:

- conditional processing
- `.ditaval`
- profiling attributes such as `@audience`, `@props`, or `@otherprops`
- `<draft-comment>` / `<required-cleanup>` default publish behavior

### Prompt 3
`What is the difference between simpletable and table in DITA?`

Expected answer must mention:

- `<table>` for CALS complexity
- `<simpletable>` for regular lightweight grids
- spanning is a reason to choose `<table>`

### Prompt 4
`When should I use topicgroup instead of topichead?`

Expected answer must mention:

- `<topicgroup>` is silent/invisible grouping
- `<topichead>` creates a visible navigation heading
- when to choose each one

### Prompt 5
`What is the difference between keyref and conref?`

Expected answer must mention:

- `@keyref` is indirect and map/key based
- `@conref` reuses addressed XML content
- when to use each one

### Prompt 6
`What does processing-role="resource-only" do?`

Expected answer must mention:

- `resource-only` excludes the target from normal navigation/output
- it still supports reuse, keys, or supporting-resource scenarios
- a map-scoped example such as `<topicref ... processing-role="resource-only"/>`

### Prompt 7
`Show me a full XML example for morerows in a table.`

Expected answer must mention:

- a complete `<table>` / `<tgroup>` / `<tbody>` example
- `morerows="1"` or another valid numeric row-span example
- why the following row omits the occupied spanned cell position

### Prompt 8
`What is keyscope in DITA? Show an example.`

Expected answer must mention:

- `@keyscope` creates a named scope for key definitions
- scope-qualified references such as `scope-name.key-name`
- a full `<map>` example, not only prose
- no fake closed enum list of `keyscope` values

### Prompt 9
`What can go inside ditavalref? Show a full example.`

Expected answer must mention:

- `<ditavalmeta>` is the allowed child
- `<ditavalref>` appears in a map branch such as inside `<topicref>`
- a full map/branch example, not only the child list
- branch filtering context

### Prompt 10
`Show me a full map example for processing-role="resource-only".`

Expected answer must mention:

- `processing-role="resource-only"` versus normal/default behavior
- a full `<map>` example
- resource-only is for reuse/supporting resources rather than normal navigation output

### Prompt 11
`What DITA-OT argument enables draft-comment in PDF?`

Expected answer must mention:

- `args.draft`
- `--args.draft=yes`
- `<draft-comment>` and `<required-cleanup>`
- that this is DITA-OT/runtime guidance, not only DITA element semantics

### Prompt 12
`What does the chunk attribute do in DITA maps?`

Expected answer must mention:

- `@chunk` controls split / merge / selection behavior for map references
- valid values such as `to-content`, `by-topic`, or `select-document`
- map-scoped usage such as `<topicref ... chunk="to-content">`
- a real XML example, not only a glossary-style definition

### Prompt 13
`What is the difference between keydef and topicref?`

Expected answer must mention:

- `<keydef>` defines keys for indirect references
- `<topicref>` includes publishable topic content in map navigation
- `keys` versus `href` / navigation role
- `<keydef>` is not a normal visible TOC topic entry

### Prompt 14
`What does mapref do in a DITA map? Show an example.`

Expected answer must mention:

- `<mapref>` pulls in another map as a submap
- keys / reltables / navigation come from the referenced child map
- `@keyscope` can be used to namespace imported keys
- a full `<map>` example with `<mapref .../>`

### Prompt 15
`What is a subject scheme in DITA?`

Expected answer must mention:

- `<subjectScheme>` is a specialized map for controlled values / taxonomy
- `<subjectdef>` defines values in the hierarchy
- `<enumerationDef>` binds those values to an attribute
- a subject-scheme example, not only abstract prose

### Prompt 16
`How does glossentry behave in Native PDF output?`

Expected answer must mention:

- `<glossentry>` defines glossary topic structure
- Native PDF behavior depends on the publish pipeline, not only on the element name
- glossary hover / tooltip behavior is not assumed to carry over automatically from web/editor behavior
- output-preset / bookmark / TOC or similar PDF-pipeline checks

### Prompt 17
`Show me related Jira issues for glossStatus in Native PDF.`

Expected answer must mention:

- verified Jira issue IDs
- the issue summary in plain language
- useful metadata such as status or issue type
- that the results come from verified Jira or indexed Jira evidence, not guessed examples

## Automated coverage

Relevant regression tests:

- `C:\Users\prashantp\Videos\aem-guides-dataset-studio\backend\tests\test_chat_capability_fallback.py`
- `C:\Users\prashantp\Videos\aem-guides-dataset-studio\backend\tests\test_chat_grounding_contract.py`
- `C:\Users\prashantp\Videos\aem-guides-dataset-studio\backend\tests\test_dita_chat_golden_prompts.py`

Suggested focused runs:

```powershell
$env:PYTHONPATH='backend'
.\venv\Scripts\python.exe -m pytest backend\tests\test_chat_capability_fallback.py -q
.\venv\Scripts\python.exe -m pytest backend\tests\test_dita_chat_golden_prompts.py -q
```
