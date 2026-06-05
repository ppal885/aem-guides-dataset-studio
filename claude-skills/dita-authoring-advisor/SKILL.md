---
name: dita-authoring-advisor
description: >
  Answer DITA authoring best-practice questions and help users write better DITA. Use
  this skill for questions about HOW to author DITA correctly: "when should I use a
  concept vs task vs reference", "how do I reuse content in DITA", "what is conref and
  how does it work", "how do I use keyrefs", "how to structure a DITA map", "best practice
  for shortdesc", "how to use DITAVAL for conditions", "how do I create a glossary",
  "what is a bookmap", "how to set up topic reuse", "how do I create a keydef map",
  "how do I write a good task topic", "what is the difference between conref and keyref",
  "how to use reltables", "how do I version my DITA content", "how to handle translation
  in DITA", "how do I use scoped keys", "what is chunk attribute", "how do I organize
  my DITA files", or any question about authoring strategy, content reuse, map structure,
  or DITA best practices. Uses lookup_dita_spec and lookup_aem_guides to ground answers.
---

# DITA Authoring Advisor

This skill provides best-practice guidance for DITA authoring — topic types, content reuse,
map structure, conditions, and AEM Guides-specific workflows — grounded in spec lookups.

---

## 1. Topic Type Decision Guide

Answer "which topic type should I use?" with this table:

| Content type | Use | Key elements |
|---|---|---|
| **Concept** | Explanatory content, background, "what is X" | `<conbody>`, `<section>`, `<p>`, `<example>` |
| **Task** | Step-by-step procedures, "how to do X" | `<taskbody>`, `<steps>`, `<step>`, `<cmd>` |
| **Reference** | Look-up tables, parameters, API docs, specifications | `<refbody>`, `<properties>`, `<table>`, `<simpletable>` |
| **Glossary entry** | Term definitions | `<glossentry>`, `<glossterm>`, `<glossdef>` |
| **Troubleshooting** | Problem/cause/remedy | `<troublebody>`, `<condition>`, `<cause>`, `<remedy>` |

**Decision rule:** If the user is *doing* something → task. If they're *learning about* something → concept. If they'll *look up* a value → reference.

**One topic, one type.** Never mix step-by-step instructions and background explanation in the same topic. Split them.

---

## 2. Content Reuse — Choosing the Right Mechanism

| Need | Use | How |
|---|---|---|
| Reuse a single element (warning, note, step) | `@conref` | `<note conref="shared.dita#reuse/safety-note"/>` |
| Reuse a whole topic in multiple maps | `<topicref>` pointing to same file | No copy needed — maps reference the same topic |
| Reuse a phrase or product name | `@keyref` on `<keyword>` | Define key in keydef map, reference as `<keyword keyref="product-name"/>` |
| Reuse a link target | `@keyref` on `<xref>` | `<xref keyref="install-guide"/>` — key resolves to href + text |
| Exclude/include content per audience | DITAVAL + conditional attributes | Add `@audience="admin"` to elements, filter with `.ditaval` |
| Reuse a block range | `@conref` + `@conrefend` | Pulls contiguous elements between start and end IDs |
| Push content into a topic without editing it | conref push | `@conaction="pushreplace"` in a separate map |

### Conref rules
```xml
<!-- In the source (library) topic — give element an @id -->
<note id="safety-note" type="warning">
  Do not operate without protective equipment.
</note>

<!-- In the consuming topic -->
<note conref="shared/notes.dita#shared-notes/safety-note"/>
<!-- Format: filename.dita#topicid/elementid -->
```

The `@conref` value MUST use the format `path/to/file.dita#topic-id/element-id`.
Both the topic ID and element ID are required. The consuming element must be the SAME
element type as the source.

### Keyref rules
```xml
<!-- In the keydef map (resource-only map) -->
<map>
  <keydef keys="product-name" href="topics/product.dita">
    <topicmeta>
      <keywords><keyword>AEM Guides</keyword></keywords>
    </topicmeta>
  </keydef>
  <keydef keys="install-url" href="https://example.com/install" format="html" scope="external"/>
</map>

<!-- In any topic -->
<p>Welcome to <keyword keyref="product-name"/>.</p>
<p>See <xref keyref="install-url">the installation guide</xref>.</p>
```

---

## 3. Map Structure Best Practices

### Basic DITAMAP structure
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">
<map title="Product Guide">
  <!-- Always include your keydef map first, resource-only -->
  <mapref href="keys/product-keys.ditamap" processing-role="resource-only"/>

  <!-- Main content structure -->
  <topicref href="topics/overview.dita">
    <topicref href="topics/install.dita"/>
    <topicref href="topics/configure.dita"/>
  </topicref>

  <!-- Relationship table for related links -->
  <reltable>
    <relrow>
      <relcell><topicref href="topics/install.dita"/></relcell>
      <relcell><topicref href="topics/requirements.dita"/></relcell>
    </relrow>
  </reltable>
</map>
```

### Map authoring rules
- Use `processing-role="resource-only"` for keydef maps and conref libraries — they won't appear in the TOC
- Set `@toc="no"` on topicrefs that should not appear in navigation
- Use `<mapref>` to include submaps — keeps large maps manageable
- Set `@collection-type="sequence"` when topics have a reading order (enables prev/next links)
- Set `@collection-type="family"` to generate related-links between siblings

---

## 4. Conditions and DITAVAL

### Mark elements with condition attributes
```xml
<!-- Single-condition -->
<step audience="admin"><cmd>Open the admin console.</cmd></step>
<step audience="user"><cmd>Log in with your credentials.</cmd></step>

<!-- Multi-value (space-separated) -->
<note platform="windows linux">Applies to Windows and Linux.</note>

<!-- Multiple attributes -->
<p audience="admin" platform="linux">Linux admin note.</p>
```

Standard condition attributes: `@audience`, `@platform`, `@product`, `@props`, `@otherprops`

### DITAVAL file
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE val PUBLIC "-//OASIS//DTD DITA DITAVAL//EN" "ditaval.dtd">
<val>
  <prop att="audience" val="admin" action="include"/>
  <prop att="audience" val="user" action="exclude"/>
  <prop att="platform" val="windows" action="include"/>
  <prop att="platform" val="linux" action="exclude"/>
</val>
```

Actions: `include` (show), `exclude` (hide), `flag` (highlight in output), `passthrough`

### AEM Guides condition workflow
1. Define attribute values in **Tools > Guides > Condition Attributes**
2. Apply to elements in the XML editor
3. Create a **Condition Preset** referencing a DITAVAL file
4. Assign the preset to an Output Preset before publishing

---

## 5. Shortdesc Best Practices

`<shortdesc>` is the single most impactful element for content quality:

**Rules:**
- Maximum 50 words (ideally 1-2 sentences)
- Must stand alone — it appears in search results, tooltips, and related-links previews
- State the PURPOSE of the topic, not what the topic IS
- Avoid starting with "This topic..." or "This section..."

```xml
<!-- Bad -->
<shortdesc>This topic describes how to install the product.</shortdesc>

<!-- Good -->
<shortdesc>Install the product on Windows, macOS, or Linux using the command-line installer.</shortdesc>
```

---

## 6. Common Authoring Mistakes

| Mistake | Why it's wrong | Fix |
|---|---|---|
| Putting steps inside `<conbody>` | Steps belong in `<taskbody>` | Use a task topic for procedures |
| Using `<p>` inside `<step>` directly | `<step>` requires `<cmd>` first | Wrap the action in `<cmd>`, put explanation in `<info>` |
| Putting multiple actions in one `<cmd>` | Each step should have ONE action | Split into multiple `<step>` elements |
| Using `<b>` for product/UI names | Semantic markup is better | Use `<uicontrol>`, `<cmdname>`, `<varname>` |
| Hard-coding product names in text | Breaks reuse | Use `<keyword keyref="product-name"/>` |
| Deep folder nesting for DITA files | Breaks portability | Keep maps and topics in 2-level hierarchy max |
| Duplicate content in multiple topics | Maintenance burden | Use conref or keyref instead |
| Long `<shortdesc>` | Truncated in search results | Keep under 50 words |
| Missing `@id` on topic root | Required for conref targeting | Always set `id` on `<concept>`, `<task>`, etc. |

---

## 7. Answer Format

**"When should I use X"** → decision table (§1, §2 patterns) + recommendation
**"How do I set up X"** → numbered steps + XML snippet
**"What is X"** → definition + example + when to use
**"Difference between X and Y"** → comparison table + deciding factor

Call `lookup_dita_spec` for elements mentioned and `lookup_aem_guides` for AEM Guides
workflow questions before answering. Ground every structural claim in spec evidence.
