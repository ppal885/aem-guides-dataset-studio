give # Cisco-style enterprise task authoring (screenshot + reference)

This mode shapes **new** DITA `<task>` topics to match common enterprise patterns (prereq → context → steps with optional `<info>` → result → example → postreq), **without** copying business text, IDs, or links from the reference file.

## How to use

1. In **Chat** → DITA from screenshot, attach a **screenshot** and a **reference** `.dita` task.
2. Under **Options**:
   - **Authoring pattern**: choose **Auto-detect** (recommended with a Cisco-like reference), **Cisco-style enterprise task**, or **Default task layout**.
   - Optionally enable **Preserve reference DOCTYPE line** to keep the catalog declaration from the sample (Cisco mode also preserves when a task `DOCTYPE` is present).
3. Use **medium** or **high** style strictness so output is built via the **structured draft → serializer** path (not raw LLM XML).

## Reference sample

See `backend/tests/fixtures/cisco_style_reference_task.dita` for a **fictitious** shell that exercises:

- `<task>` root, prolog/metadata, terse copy
- `taskbody` ordering: `prereq`, `context`, `steps` with `cmd` + `info`, `substeps`, `result`, `example`, `postreq`
- Inline `uicontrol` and `codeph`

That file is for **tests and pattern detection only** — do not treat it as real product content.

## Semantic plan hints (LLM)

With **Cisco-style** or **auto-detected** Cisco mode, the planner receives extra rules:

- Sections named `prereq`, `context`, `steps`, `result`, and optional `acceptance criteria`
- Step details may use ` || ` to split **command** vs **info** paragraph
- No `xref` / `conref` / `href` in plan fields

## Generated output guarantees

- **New** root and step `@id` values (slugged from the generated title).
- Reference **root `id`**, **href**, **conref**, and **keyref** values are **not** copied into the style profile or output.
- Serializer does not emit cross-reference elements in the programmatic path.

## Validation

Output is validated like any other chat-generated topic (structural checks, folder/DITA checks, review snapshot). Failing validation still produces an artifact you can open in the **DITA workspace** for manual fix-up.
