---
name: aem-output-presets
description: >
  Configure and troubleshoot AEM Guides output presets — Native PDF, HTML5, AEM Sites,
  Knowledge Base, and ePub. Use this skill whenever someone asks about publishing
  configuration in AEM Guides: "how do I configure native PDF output", "set up HTML5
  output preset", "native PDF isn't rendering my table of contents", "how do I add
  a cover page to PDF", "configure page size for PDF", "how do I apply a DITAVAL
  filter in my output preset", "PDF template customization in AEM Guides", "AEM Sites
  output configuration", "publish to Knowledge Base", "why is my PDF missing images",
  "how do I set up conditional publishing", "output preset settings explained",
  "difference between PDF2 and native PDF in AEM Guides", or any question about
  getting DITA content published to a deliverable format through AEM Guides.
---

# AEM Guides Output Presets

This skill answers output preset questions using `lookup_output_preset` and
`generate_native_pdf_config` — grounded in AEM Guides Experience League documentation.

---

## 1. Identify the Output Type

| User asks about | Output type | Tool to use |
|---|---|---|
| Native PDF, cover page, page size, PDF template | `native_pdf` | `generate_native_pdf_config` + `lookup_output_preset` |
| HTML5 web output, responsive layout | `html5` | `lookup_output_preset(output_type="html5")` |
| AEM Sites, page hierarchy, component mapping | `aem_sites` | `lookup_output_preset(output_type="aem_sites")` |
| Salesforce / ServiceNow articles | `knowledge_base` | `lookup_output_preset(output_type="knowledge_base")` |
| DITAVAL conditions in publishing | any | `lookup_output_preset` + DITAVAL guidance |
| General / unclear | — | `lookup_output_preset(query=<question>)` |

Always call the relevant tool before answering — don't guess at config values.

---

## 2. Output Type Quick Reference

### Native PDF
AEM Guides' CSS-based PDF engine (not DITA-OT PDF2).

**Where configured:** Map console → Output Presets → PDF type → select template

**Key settings:**
| Setting | What it does |
|---|---|
| PDF Template | Controls page layout, fonts, cover, TOC style |
| Condition Preset | DITAVAL file to apply conditional filtering |
| Cross-reference style | How `<xref>` links appear in PDF |
| Baseline | Publish a specific topic version snapshot |
| Generate PDF for changed files only | Incremental publish |

**Customisation:** Tools → PDF Templates → Edit template → download ZIP → edit `content/*.css` → re-upload

**vs DITA-OT PDF2:**
| | Native PDF | PDF2 (DITA-OT) |
|---|---|---|
| Engine | CSS Paged Media | XSL-FO (Apache FOP) |
| Customise | CSS + template editor | XSLT stylesheets |
| Configured in | AEM Guides UI | CLI / Ant properties |
| Skill needed | CSS | XSLT |

### HTML5
DITA-OT `html5` transform wrapped in AEM Guides preset UI.

**Key settings:** base path, context path, condition preset, responsive layout, search

### AEM Sites
Publishes DITA structure as AEM page tree.

**Key settings:** site path, component mapping, paragraph styles, image handling

### Knowledge Base
Generates article-per-topic output for Salesforce or ServiceNow.

**Key settings:** target platform, article type mapping, category/subcategory

---

## 3. Generate a Native PDF Config

Use `generate_native_pdf_config` when the user needs a configuration snippet or
template settings for a specific PDF requirement:

```
generate_native_pdf_config(
  query        = "<what the user wants, e.g. 'A4 page size, TOC with 3 levels, cover page with logo'>",
  output_type  = "native_pdf",
)
```

This returns a configuration guide with:
- Template settings to adjust
- CSS properties to set
- Variables to define in `variables/en.xml`
- Step-by-step instructions for the AEM Guides template editor

---

## 4. Troubleshooting Common Problems

| Problem | Cause | Fix |
|---|---|---|
| TOC missing entries | `@toc="no"` on topicref | Remove the attribute or set `@toc="yes"` |
| Images missing in PDF | Image path not relative to map | Use relative paths; check image is in the topic's folder |
| Blank PDF pages | Empty `<section>` or `<topic>` | Add `<p>` or draft-comment placeholder |
| Conditional content not filtered | DITAVAL not set in preset | Add DITAVAL file under Condition Preset in output settings |
| Cover page not showing | Template has no cover page layout | Enable cover page in PDF Template → Page Layouts |
| Cross-references broken | `@href` uses absolute path | Switch to `@keyref` with keydef map, or fix to relative path |
| Wrong font in PDF | Font not embedded in template | Add font to template CSS + upload font file |
| Large PDF file size | Images not compressed | Convert images to JPEG/WebP before adding to DITA |

---

## 5. Answer Format

**"How do I configure X"** → numbered steps with UI path (e.g. *Map Console → Output Presets → New → PDF*)

**"Why isn't X working"** → Cause first, then specific fix, then prevention

**"Difference between X and Y"** → table comparing the two options, then recommendation

**"What settings does X support"** → table of settings with purpose and values

Always call `lookup_output_preset` or `generate_native_pdf_config` and ground your
answer in the retrieved AEM Guides documentation. Never invent config values.

---

## 6. Examples

**Configuring page size:**
> "How do I change the page size to A4 in my Native PDF output?"

→ `generate_native_pdf_config(query="A4 page size", output_type="native_pdf")`
→ Answer: navigate to PDF Template → Page Layouts → set width/height CSS variables

**Filtering conditions:**
> "How do I apply a DITAVAL filter when publishing to HTML5?"

→ `lookup_output_preset(query="DITAVAL condition preset HTML5", output_type="html5")`
→ Answer: in the HTML5 preset, under Condition Preset, select or upload the DITAVAL file

**Troubleshooting:**
> "My table of contents is missing some chapters in the native PDF."

→ `lookup_output_preset(query="TOC missing entries native PDF")`
→ Answer: check `@toc` attribute on topicrefs; check TOC depth in PDF template settings
