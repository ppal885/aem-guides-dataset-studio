---
name: dita-screenshot-to-topic
description: >
  Generate a DITA XML topic from a UI screenshot or image. Use this skill whenever
  a user uploads or references a screenshot and wants DITA content from it: "turn
  this screenshot into a DITA topic", "generate DITA from this UI image", "convert
  this mockup to DITA", "create a task topic from this screenshot", "write DITA
  for this dialog box", "document this UI screen as DITA", "generate a reference
  topic from this settings page", "create a concept from this architecture diagram",
  or any time an image is provided alongside a request to author DITA content.
  Use this skill instead of generate_dita when there is an actual image/screenshot
  involved — it runs a vision-analysis pipeline specifically designed for UI content.
---

# DITA Screenshot-to-Topic

This skill drives `generate_dita_from_screenshot` — a 9-stage vision pipeline that:
1. Analyses the screenshot (UI type, content areas, element layout)
2. Infers the best DITA topic type (concept / task / reference)
3. Builds a structured content plan
4. Authors a full DITA topic with correct element markup
5. Validates against DTD and auto-repairs if needed

---

## 1. What You Need From the User

| Input | Purpose |
|---|---|
| **Screenshot / image** | The UI to document (required) |
| **Topic type hint** | "make it a task" / "concept" / "reference table" (optional — inferred if omitted) |
| **Domain context** | "this is the AEM Guides XML editor" / "this is an output preset dialog" (improves titles) |
| **Reference DITA** | An existing topic to match style/structure (optional) |

If the user hasn't provided an image, ask: *"Please attach or describe the screenshot
you'd like documented."*

---

## 2. Infer the Right Topic Type

Use context clues to suggest a topic type before calling the tool:

| Screenshot content | Best topic type |
|---|---|
| Step-by-step workflow, wizard, dialog with actions | **task** — numbered steps, cmd elements |
| Settings panel, properties dialog, attribute table | **reference** — properties table or simpletable |
| Architecture diagram, concept overview, dashboard | **concept** — explanation with sections |
| Mixed / unclear | Let the pipeline auto-detect |

Tell the user: *"This looks like a [task/reference/concept] topic. I'll structure it
accordingly — let me know if you'd prefer a different type."*

---

## 3. Call the Tool

```
generate_dita_from_screenshot(
  image         = <attached image or image URL>,
  topic_type    = "task" | "concept" | "reference" | None,
  context       = "<domain hint, e.g. 'AEM Guides XML editor toolbar'>",
  instructions  = "<specific authoring constraints>",
)
```

**`context`** — crucial for quality. "AEM Guides XML editor" is far better than nothing.
Include: product name, screen name, workflow being documented.

**`instructions`** — shape the output:
- `"Task topic. Steps should be atomic. Use uicontrol for button names."`
- `"Reference table listing each setting, its type, default value, and description."`
- `"Concept topic. Include a shortdesc under 50 words. Add a note about prerequisites."`

`generate_dita_from_screenshot` requires **user approval** before running.

---

## 4. Pre-flight (Required Before Approval)

Before the approval prompt appears:

```
I'll generate a DITA **[concept | task | reference]** topic from your screenshot.

What the pipeline will do:
- Analyse the UI layout and identify content areas
- [For task] Extract the steps/actions visible in the screenshot
- [For reference] Build a properties table from the settings/fields shown
- [For concept] Summarise the concept illustrated and add supporting sections
- Validate the output against DITA 1.3 DTD; auto-repair if needed

[If context provided]: Treating this as: [screen/feature name]
```

---

## 5. After Generation

1. Show the generated DITA in a fenced `xml` code block
2. Call out what the pipeline inferred: topic type, main title, key elements used
3. Point out anything the user may want to review:
   - Steps that were inferred (user should verify order)
   - Text extracted from the image (OCR may have errors)
   - Elements that used a fallback (e.g., `<p>` instead of `<cmd>`)
4. Offer to refine: *"Want me to add a shortdesc, switch to a different topic type,
   or expand a section?"*

---

## 6. Examples

**Task from dialog screenshot:**
> "Here's a screenshot of the Condition Presets dialog in AEM Guides. Generate a task topic."

```
generate_dita_from_screenshot(
  image        = <attached screenshot>,
  topic_type   = "task",
  context      = "AEM Guides Condition Presets dialog — creating a new condition preset",
  instructions = "Task topic. Steps for creating a condition preset. Use uicontrol for button/field names. Include a prereq: DITAVAL file must exist."
)
```

**Reference from settings page:**
> "Turn this output preset settings page into a DITA reference topic."

```
generate_dita_from_screenshot(
  image        = <attached screenshot>,
  topic_type   = "reference",
  context      = "AEM Guides Native PDF output preset configuration page",
  instructions = "Reference topic. Properties table with columns: Setting, Type, Default, Description."
)
```

**Concept from architecture diagram:**
> "Generate a concept topic from this DITA publishing architecture diagram."

```
generate_dita_from_screenshot(
  image        = <attached screenshot>,
  topic_type   = "concept",
  context      = "DITA publishing pipeline: from DITAMAP to PDF/HTML5 via DITA-OT",
  instructions = "Concept topic. Overview section explains the pipeline stages. Add a note about where AEM Guides fits."
)
```

---

## 7. Common Pitfalls to Flag

- **UI labels may be clipped** — if the screenshot cuts off text, mention it and ask
  the user to confirm the full label
- **Steps inferred from visual order** — the pipeline reads left-to-right, top-to-bottom;
  if the actual task order differs, the user should re-order
- **Icons without labels** — if the screenshot has icon-only buttons, the pipeline
  may describe them by position; ask user to confirm the button names
