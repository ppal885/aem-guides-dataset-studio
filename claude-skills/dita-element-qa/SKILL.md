---
name: dita-element-qa
description: >
  Answer DITA element and attribute questions accurately using spec-grounded lookups.
  Use this skill for ANY question about a DITA element or attribute: "what is <shortdesc>",
  "how do I use <conref>", "what attributes does <topicref> support", "difference between
  <note> and <hazardstatement>", "what can go inside <taskbody>", "when should I use
  <codeblock> vs <codeph>", "what is the content model of <step>", "how does @collection-type
  work", "what does @scope do on <xref>", "explain <reltable>", "what is <keydef>",
  "difference between @href and @keyref", "what elements are allowed in <concept>",
  "how does @conref work", "what is @outputclass for", or any question that mentions a
  DITA element name (with or without angle brackets) or attribute name (with or without @).
  ALWAYS call lookup_dita_spec or lookup_dita_attribute before answering — never answer
  from memory alone.
---

# DITA Element & Attribute Q&A

This skill ensures every DITA element or attribute question is answered from spec-grounded
evidence, structured clearly, with correct examples — never from LLM memory alone.

---

## 1. Identify the Query Type

| User asks about | Call | Then |
|---|---|---|
| A single element (`<shortdesc>`, `<step>`) | `lookup_dita_spec(query=..., elements=["shortdesc"])` | Answer with element structure |
| An attribute (`@scope`, `@collection-type`) | `lookup_dita_attribute(attribute_name="scope")` | Answer with attribute details |
| Comparison (`<note> vs <hazardstatement>`) | `lookup_dita_spec(query=..., elements=["note","hazardstatement"])` | Use comparison format |
| Content model (`what can go in <taskbody>`) | `lookup_dita_spec(query=..., elements=["taskbody"])` | Focus on children |
| When to use (`when should I use <codeblock>`) | `lookup_dita_spec(query=...)` | Answer with use-case guidance |

**Never skip the lookup.** Even if you know the answer, call the tool — the response
includes structured guidance, correct examples, and source URLs that make the answer
authoritative.

---

## 2. Answer Structure

### For a single element:

```
## `<element-name>`

**What it is:** [One sentence — role in DITA, topic type context]

**Where it goes:** [Parent elements — e.g. "Inside `<step>`, after `<cmd>`"]

**What it contains:** [Key children — be specific, not "various elements"]

**Key attributes:** `@attr1`, `@attr2`, `@attr3`

**Example:**
\`\`\`xml
<element-name>
  [minimal but real example showing typical usage]
</element-name>
\`\`\`

**Common mistakes:**
- [Mistake 1: what people get wrong]
- [Mistake 2]
```

### For an attribute:

```
## `@attribute-name`

**What it does:** [One sentence]

**Valid values:** `value1` | `value2` | `value3`  (or: string, NMTOKEN, etc.)

**Supported on:** [elements it can appear on]

**Default:** [default value if any]

**Example:**
\`\`\`xml
<element @attribute-name="value">...</element>
\`\`\`

**When to use each value:** [table or bullets explaining each value's effect]
```

### For a comparison:

Use a markdown table:

```
| | `<element1>` | `<element2>` |
|---|---|---|
| **Purpose** | | |
| **Parent** | | |
| **Key children** | | |
| **When to use** | | |
```

Then add 1-2 sentences on the deciding factor.

---

## 3. Rules for Correct Answers

**DO:**
- Name specific parent elements (not "block-level containers")
- List actual required vs optional children
- Show a minimal working XML example for every element question
- Include the `type` attribute values when relevant (e.g. `<note type="tip|warning|danger">`)
- Mention AEM Guides-specific behavior if it differs from the DITA spec

**DO NOT:**
- Say "various attributes are available" — list the key ones
- Invent element nesting that isn't in the spec
- Say "check the documentation" without also answering
- Use vague language like "typically" or "usually" for spec-defined behavior
- Skip the XML example for element questions

---

## 4. Common DITA Elements — Quick Reference

Use these to sanity-check answers from the spec lookup:

**Concept topic structure:**
`<concept>` → `<title>` + optional `<shortdesc>` + `<conbody>` → `<p>`, `<section>`, `<example>`, `<table>`, `<ul>`, `<ol>`, `<dl>`, `<image>`, `<codeblock>`

**Task topic structure:**
`<task>` → `<title>` + optional `<shortdesc>` + `<taskbody>` → optional `<prereq>`, `<context>`, `<steps>` OR `<steps-unordered>`, optional `<result>`, optional `<postreq>`
`<steps>` → one or more `<step>` → required `<cmd>` + optional `<info>`, `<substeps>`, `<choices>`, `<choicetable>`, `<tutorialinfo>`, `<stepxmp>`, `<stepresult>`

**Reference topic structure:**
`<reference>` → `<title>` + optional `<shortdesc>` + `<refbody>` → `<section>`, `<table>`, `<simpletable>`, `<properties>`

**Key inline elements:**
`<b>`, `<i>`, `<u>` — formatting (use sparingly)
`<uicontrol>` — UI labels, buttons, menu items
`<cmdname>` — command names
`<filepath>` — file paths
`<varname>` — variable names
`<codeph>` — inline code
`<xref>` — cross-references (use `@href` or `@keyref`)

---

## 5. Attributes That Confuse People Most

| Attribute | Common confusion | Correct answer |
|---|---|---|
| `@href` vs `@keyref` | When to use which | `@href` = direct path; `@keyref` = indirect via keydef (prefer for reuse) |
| `@conref` | Fragment syntax | Must be `file.dita#topicid/elementid` — both topic ID and element ID required |
| `@scope` on xref | Values and effect | `local` (default, same deliverable) / `peer` (related deliverable) / `external` (outside) |
| `@format` | When needed | Required when referencing non-DITA files: `format="html"`, `format="pdf"` |
| `@collection-type` | What it controls | Controls relationship between topicrefs: `sequence`, `choice`, `family`, `unordered` |
| `@processing-role` | Resource-only | `resource-only` = keydef maps, conref libraries — not in TOC, not published alone |
| `@outputclass` | Rendering | Passes a CSS class to the output; behavior is transform-specific |
| `@props` | Filtering | Generic conditional attribute; use `@audience`, `@platform`, `@product` for common cases |

---

## 6. When the Spec Lookup Returns Thin Results

If `lookup_dita_spec` returns few or no results:

1. Try `lookup_dita_attribute` if the question is attribute-focused
2. Try `lookup_aem_guides` for AEM Guides-specific behavior
3. Use the quick reference in §4 above to give a correct structural answer
4. Be explicit: "The spec lookup didn't return detailed results for this element.
   Based on DITA 1.3: [answer]. I recommend verifying against the official spec at
   docs.oasis-open.org."

Never fabricate content models or attribute lists.
