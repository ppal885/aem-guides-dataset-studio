---
name: dita-ot-publishing
description: >
  Answer DITA-OT and publishing questions accurately. Use this skill for ANY question
  about DITA Open Toolkit processing, output generation, or publishing from AEM Guides:
  "how does DITA-OT work", "what transforms does DITA-OT support", "PDF2 vs PDF transform",
  "how to publish to HTML5", "DITA-OT plugin development", "how to add a custom plugin",
  "what Ant properties control PDF output", "dita command line usage", "DITA-OT error
  messages", "why is my PDF output wrong", "how to configure native PDF in AEM Guides",
  "DITAVAL in publishing", "what is a transtype", "how does the PDF2 transform work",
  "difference between DITA-OT PDF and AEM Guides native PDF", "how to set page size",
  "why is my table of contents wrong", "DITA-OT version differences", "how to override
  XSL for PDF", "publishing pipeline in AEM Guides", "output presets", or any question
  about getting content OUT of DITA into a deliverable format.
---

# DITA-OT & Publishing Guide

This skill answers DITA-OT and publishing questions with accurate, specific guidance —
covering transforms, plugins, command-line usage, AEM Guides output, and troubleshooting.

---

## 1. Identify the Question Domain

| Question type | Answer approach |
|---|---|
| Transform / output type | §2 — Transform reference |
| Command-line usage | §3 — DITA-OT CLI |
| Plugin development | §4 — Plugin guide |
| AEM Guides publishing | §5 — AEM Guides specifics |
| Error diagnosis | §6 — Troubleshooting |

Call `lookup_aem_guides` for AEM Guides-specific behavior before answering publishing
questions. Use `lookup_dita_spec` for DITA structure questions that affect output.

---

## 2. Transform Reference

### Built-in DITA-OT transforms (transtypes)

| Transtype | Output | Notes |
|---|---|---|
| `pdf2` | PDF via XSL-FO (Apache FOP or Antenna House) | Legacy PDF; customizable via XSL override |
| `html5` | Standalone HTML5 pages | Default web output; CSS-themeable |
| `htmlhelp` | Windows HTML Help (.chm) | Legacy; Windows only |
| `eclipsehelp` | Eclipse plugin help | For Eclipse IDE integration |
| `xhtml` | XHTML 1.0 pages | Older web output |
| `eclipsehelp` | Eclipse-compatible help | |
| `troff` | Unix man pages | Niche |
| `markdown` | Markdown files | Requires DITA-OT 3.x+ with markdown plugin |
| `tocjs` | JS-driven TOC + HTML | |
| `dita` | Resolved DITA (preprocessing only) | Useful for debugging |

**AEM Guides additionally supports:**
- **Native PDF** — CSS-based PDF (not XSL-FO); configured via PDF profiles in Guides
- **AEM Sites** — publishes to AEM page tree
- **Knowledge Base** — Salesforce/ServiceNow article output
- **ePub** — EPUB3 output

### Key difference: PDF2 vs AEM Guides Native PDF

| | PDF2 (DITA-OT) | Native PDF (AEM Guides) |
|---|---|---|
| Engine | XSL-FO (FOP / AH) | CSS Paged Media (Prince/Antenna House CSS) |
| Customization | XSL stylesheets | CSS + PDF profile JSON |
| Where configured | plugin / Ant properties | Output preset in Guides UI |
| Skill needed | XSLT | CSS |

---

## 3. DITA-OT Command Line

### Basic syntax
```bash
dita --input=<map.ditamap> --format=<transtype> --output=<dir>
```

### Common options
```bash
# PDF output
dita --input=mymap.ditamap --format=pdf2 --output=out/

# HTML5 with custom args
dita --input=mymap.ditamap --format=html5 --output=out/ \
     --args.css=custom.css --args.csspath=css

# With DITAVAL filtering
dita --input=mymap.ditamap --format=html5 --output=out/ \
     --filter=filter.ditaval

# Verbose / debug
dita --input=mymap.ditamap --format=pdf2 --output=out/ -v
dita --input=mymap.ditamap --format=pdf2 --output=out/ --debug
```

### Key Ant properties for PDF2

| Property | Effect | Example |
|---|---|---|
| `args.fo.userconfig` | Custom FOP config | `--args.fo.userconfig=fop.xml` |
| `args.xsl.pdf` | Override XSL stylesheet | `--args.xsl.pdf=custom.xsl` |
| `customization.dir` | Plugin customization dir | `--customization.dir=custom/` |
| `args.draft` | Show draft comments | `--args.draft=yes` |
| `args.figurelink.style` | Figure numbering style | `NUMBER` / `TITLE` |
| `args.tablelink.style` | Table numbering | `NUMBER` / `TITLE` |
| `pdf2.i18n.locale` | Locale for i18n | `--pdf2.i18n.locale=ja_JP` |

---

## 4. Plugin Development

### Plugin structure
```
com.example.myplugin/
├── plugin.xml          ← required — declares plugin ID, version, dependencies
├── build.xml           ← optional Ant targets
├── xsl/
│   └── custom.xsl      ← XSL overrides for PDF2
├── cfg/
│   └── fo/
│       └── attrs/      ← attribute set overrides
└── Customization/
    └── xsl/            ← alternate override location
```

### Minimal `plugin.xml`
```xml
<?xml version="1.0" encoding="UTF-8"?>
<plugin id="com.example.myplugin" version="1.0">
  <require plugin="org.dita.pdf2"/>
  <feature extension="dita.xsl.xslfo" value="xsl/custom.xsl" type="file"/>
</plugin>
```

### Install a plugin
```bash
dita install com.example.myplugin/
# or from a zip
dita install com.example.myplugin.zip
# or from a URL
dita install https://example.com/plugin.zip
```

### Common extension points
| Extension point | Purpose |
|---|---|
| `dita.xsl.xslfo` | Add XSL for PDF2 output |
| `dita.xsl.html5` | Add XSL for HTML5 output |
| `dita.conductor.steps` | Add Ant steps to the pipeline |
| `dita.transtype.print` | Register a print transtype |
| `dita.xsl.strings` | Override string variables |

---

## 5. AEM Guides Publishing

### Output presets

In AEM Guides, publishing is configured via **Output Presets** on a DITAMAP:
- **PDF (Native)** — CSS-based PDF; configure page size, fonts, cover page in the preset
- **AEM Site** — maps DITA structure to AEM page hierarchy
- **HTML5** — delegates to DITA-OT html5 transform
- **Knowledge Base** — Salesforce/ServiceNow article format

Use `lookup_output_preset` or `lookup_aem_guides` to get details on a specific preset type.

### DITAVAL / conditional content in AEM Guides
- Define conditions in **Condition Attributes** panel (Tools > Guides > Condition Attributes)
- Apply filter via DITAVAL file referenced in the output preset's **Condition Presets**
- Preview filtered output in the editor with **Preview with Condition**

### Native PDF customization
- Use **PDF Templates** (Output > PDF Templates)
- Set page layout, fonts, cover page, TOC style via the template editor
- For advanced CSS: download template ZIP, edit `content/` CSS files, re-upload
- Custom variables: define in `variables/en.xml`, reference in XSL/CSS as `<var-name>`

### Common AEM Guides publishing errors
| Error | Cause | Fix |
|---|---|---|
| `Topic not found` | Broken topicref path | Check href is relative and correct |
| `Key not resolved` | Keydef map not in scope | Add keydef map to bookmap or rootmap |
| `Conref target missing` | Source file not in map | Include source file or use `processing-role="resource-only"` |
| Blank PDF pages | Empty section/topic | Add `<p>` placeholder or `draft-comment` |
| Missing images in PDF | Image path incorrect | Use relative paths from map file location |
| TOC missing entries | `@toc="no"` on topicref | Remove the attribute or set `@toc="yes"` |

---

## 6. Troubleshooting DITA-OT Errors

### Diagnostic approach
1. **Run with `-v` (verbose)** — surfaces which file/element caused the error
2. **Run with `--debug`** — dumps full Ant log; look for `[fop]` or `[xslt]` sections
3. **Check the temp dir** — `dita --input=... --output=out/ --keep-temp` preserves intermediate files
4. **Validate the map first** — `dita --input=mymap.ditamap --format=dita --output=validated/`

### Common errors

| Error message | Meaning | Fix |
|---|---|---|
| `[DOTJ013F] File not found` | Missing topic or image | Fix the path in topicref/image href |
| `[DOTX008E] Keyref could not be resolved` | Key not defined | Add keydef or check key name spelling |
| `[DOTJ015F] Cannot read map` | Corrupt or invalid XML | Fix XML syntax in the map |
| `[FOP] Error: page-sequence too many` | XSL-FO rendering issue | Simplify table or column widths |
| `javax.xml.transform.TransformerException` | XSL error | Check custom XSL for errors |
| `[WARN][DOTJ053W] i18n file not found` | Missing locale file | Add locale or use `en` as fallback |
| `OutOfMemoryError` | Large map, low heap | Increase JVM: `JAVA_TOOL_OPTIONS=-Xmx2g dita ...` |

### DITA-OT version-specific notes
- **DITA-OT 3.x** — introduced LwDITA, HTML5 default, `dita` command
- **DITA-OT 4.x** — improved PDF CSS support, Java 17+ required, deprecated legacy HTML
- AEM Guides bundles a specific DITA-OT version — check **Tools > DITA-OT Profile** to see which

---

## 7. Answer Format for Publishing Questions

**How-to questions** → numbered steps with code blocks for commands/config
**Error questions** → cause first, then fix, then prevention
**Comparison questions** → table with key dimensions, then recommendation
**Concept questions** → definition, how it fits in the pipeline, example

Always be specific about:
- Which DITA-OT version the behavior applies to
- Whether the answer is DITA-OT native or AEM Guides-specific
- Whether a property/feature requires a plugin

---

## 8. Routing & Response Quality Notes (learned from production testing)

### Questions that route correctly
- "DOTX020 error when building" → DITA-OT error path → GitHub issues as evidence
- "PDF2 fails with NullPointerException" → DITA-OT error path
- "how to configure HTML5 output preset" → AEM Guides grounding
- "native PDF vs PDF2 difference" → OT comparison path (comparison table returned)

### Questions that previously routed wrong (now fixed)
- "unresolved keyref when building DITA-OT" — `keyref` has trailing `\w*` match
- "DOTJ013F file not found" — DOT[XJAF]`\w+` pattern (not `\d{3,}`)
- "how does keyscope work" — now routes to authoring guidance, not generation

### GitHub Issues RAG
2988 DITA-OT GitHub issues are indexed. They surface automatically for error code queries.
Always mention the GitHub issue URL when it appears in the evidence block.

### Humanized response style
Write like a senior colleague, not a manual page:
- "This one trips people up..." for common errors
- Give the most likely cause FIRST, not theory first
- "You're not alone — this came up in [issue title]" when GitHub evidence found
