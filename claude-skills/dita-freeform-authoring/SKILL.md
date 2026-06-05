---
name: dita-freeform-authoring
description: >
  Generate real, domain-accurate DITA XML content using LLM-authored free-form output — no
  recipe templates, no structural skeletons. Use this skill whenever the user wants high-quality
  DITA written from scratch with full creative fidelity: "write a DITA topic about X",
  "author DITA content for Y", "create a concept topic explaining Z", "generate DITA from
  this text", "write realistic DITA for my domain", "make a task topic that walks through X
  step by step", or any request where the content itself (titles, body, steps, examples)
  matters more than the structural breadth. Also triggers when the user pastes prose, a
  spec excerpt, or a feature description and says "turn this into DITA". Use this skill
  instead of dita-dataset-generator when the request is about CONTENT QUALITY over QUANTITY.
---

# DITA Freeform Authoring

This skill drives `generate_dita` — the LLM-native generation path that writes real DITA XML
from a natural language prompt without recipe scaffolding. Every title, shortdesc, step, and
body paragraph is authored by the LLM based on your description.

---

## 1. When to Use This vs. `create_job`

| Situation | Use |
|---|---|
| User wants N topics on a domain, structured tree or flat set | `create_job` (recipe) |
| User wants one or a few topics written with real content depth | `generate_dita` (this skill) |
| User pastes prose / spec / feature description to convert | `generate_dita` (this skill) |
| User says "write", "author", "draft", "turn this into DITA" | `generate_dita` (this skill) |
| User says "generate a dataset", "bulk topics", "training data" | `create_job` (recipe) |

---

## 2. Extract What to Generate

From the user's prompt, capture:

| Signal | Examples |
|---|---|
| **Topic type** | concept, task, reference, glossary entry |
| **Domain / subject** | "Kubernetes pod scheduling", "Adobe PDF output preset" |
| **Specific content** | steps, properties, attributes, examples the user mentions |
| **Source text** | any prose, spec excerpt, or description to convert |
| **Constraints** | "keep steps under 10", "include a codeblock", "use choicetable" |

If the user pastes source text (prose, feature notes, user story), include it verbatim in the
`text` parameter — this is the primary signal for content quality.

---

## 3. Build the `generate_dita` Call

```
generate_dita(
  text         = "<full user description OR pasted source text>",
  instructions = "<specific authoring constraints, e.g. 'task topic, 5-8 steps, include result element'>",
)
```

**`text`** — the primary content driver. Be generous: include everything the user said, plus
any domain keywords or structure hints. Richer text → richer output.

**`instructions`** — shape the output:
- Topic type: `"Write as a DITA concept topic."`
- Structure: `"Include shortdesc, one section per feature area, close with a note element."`
- Elements: `"Use codeblock for all code examples. Use uicontrol for UI labels."`
- Constraints: `"Steps should be atomic (one action each). Include a prereq."`

---

## 4. Pre-flight (Required Before Approval)

`generate_dita` requires user approval. Before the prompt appears, say:

```
I'll author a DITA **[concept | task | reference]** topic about **[subject]**.

What the LLM will write:
- [shortdesc describing the topic in one sentence]
- [2-3 bullet points about the sections/steps/properties it will cover]
- Validated DITA 1.3 XML, auto-repaired if needed

[If source text was pasted]: Starting from the text you provided.
```

---

## 5. After Generation

1. Show the **download URL** so the user can get the bundle.
2. Show a **short summary** of what was produced: topic type, element count, any repairs.
3. **Offer to refine**: *"Want me to add more steps, swap to a reference table format, or
   include a codeblock example?"*

---

## 6. Handling Advanced Constructs

If the user mentions conref, keyref, reltable, or multi-topic maps, `generate_dita`
auto-detects these and routes to `create_job(recipe_type="freeform")` internally —
you do not need to change the call. Just make sure the `text` mentions the constructs
clearly so the auto-detection fires.

---

## 7. Examples

**Convert prose to DITA:**
> "Take this feature description and turn it into a DITA concept topic:
> AEM Guides supports DITAVAL-based conditional publishing. Authors apply @audience,
> @platform, and @product attributes to elements, then reference a DITAVAL filter file
> in the output preset to include or exclude content at build time."

```
generate_dita(
  text         = "AEM Guides supports DITAVAL-based conditional publishing. Authors apply @audience, @platform, and @product attributes to elements, then reference a DITAVAL filter file in the output preset to include or exclude content at build time.",
  instructions = "Write as a DITA concept topic. Include shortdesc, a section on applying attributes, a section on DITAVAL filter files, and a note about precedence rules."
)
```

**Author a task topic:**
> "Write a DITA task for adding a keydef to a map in AEM Guides."

```
generate_dita(
  text         = "Write a DITA task topic: how to add a keydef element to a DITA map in AEM Guides XML editor. Cover opening the map, inserting a keydef with keys and href attributes, and saving.",
  instructions = "Task topic. 5-8 steps. Include a prereq (map must be open in XML editor). Add a result element. Use uicontrol for UI labels and filepath for file paths."
)
```

**Reference table:**
> "Create a reference topic listing all DITA @outputclass values for note elements."

```
generate_dita(
  text         = "DITA reference topic: @outputclass values supported on note elements in AEM Guides. Values: note, tip, important, warning, danger, trouble, restriction, attention, fastpath, remember, other.",
  instructions = "Reference topic. Use a properties table with columns: outputclass value, rendered style, when to use. Include shortdesc."
)
```
