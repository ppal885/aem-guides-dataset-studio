---
name: dita-construct-coverage
description: >
  Generate DITA datasets that specifically exercise or demonstrate particular DITA
  constructs, elements, or authoring patterns. Use this skill when a user asks for
  data targeting specific DITA features: "generate datasets with conref examples",
  "create DITA with keyref patterns", "generate choicetable examples", "dataset
  with conditional content and DITAVAL", "generate topics using reltables",
  "create conref push examples", "dataset demonstrating keyscopes", "generate
  DITA with complex tables", "create examples of all note types", "generate
  datasets with MathML", "produce DITA with nested maps", "generate reuse
  patterns for training", or any request where specific DITA XML constructs,
  elements, or authoring techniques must appear in the output data.
---

# DITA Construct Coverage Generator

This skill generates datasets where specific DITA constructs are the primary focus —
for testing, training data, documentation examples, or QA coverage.

---

## 1. Construct → Recipe Mapping

| Requested construct | Best recipe | Key config |
|---|---|---|
| `@conref`, conref push, conref range | `conref_pack` or `dita_conref_keyref_dataset_recipe` | `conref_density: 0.5` |
| `@keyref`, `<keydef>`, keyscopes | `dita_conref_keyref_dataset_recipe` or `keyscope_demo` | — |
| `<choicetable>`, `<choices>` | `choicetable_tasks` or `choicetable_references` | — |
| `<reltable>`, relationship tables | `relationship_table` or `maps_reltable_basic` | — |
| DITAVAL, conditional content (`@audience`, `@platform`) | `conditional_content` | — |
| `<simpletable>`, `<properties>` table | `properties_table_reference` | — |
| Subject scheme maps | `dita_subject_scheme_dataset_recipe` | — |
| Glossary abbreviations | `dita_glossary_abbrev_dataset_recipe` | — |
| Nested keydefs / key chains | `keyref_nested_keydef_chain_map_to_map_to_topic` | — |
| `<bookmap>` structure | `bookmap_structure` | — |
| `<mapref>`, nested maps | `maps_mapref_basic` or `maps_nested_topicrefs` | — |
| `<foreign>` / MathML / SVG | `topic_svg_mathml_foreign` | — |
| Inline formatting, nested elements | `inline_formatting_nested` | — |
| Media-rich (images, figures, video) | `media_rich_content` | — |
| Large-scale mixed constructs | `freeform` | — |

---

## 2. Build the subject Around the Construct

The `subject` must name both the construct AND a domain so the LLM generates realistic content (not lorem ipsum):

**Pattern:** `"[DITA construct] patterns in [domain context]"`

**Examples:**
- `"@conref patterns for DITA note, warning, hazardstatement elements in safety documentation"`
- `"@keyref and keyscope patterns in multi-variant software documentation"`
- `"choicetable patterns for configuration procedures in cloud infrastructure"`
- `"conditional content with DITAVAL for audience-based filtering in enterprise software docs"`
- `"reltable cross-references between task, concept, and reference topics for Kubernetes"`

---

## 3. prompt_text for Construct Accuracy

`prompt_text` should spell out the exact construct requirements — what the LLM authoring step uses to generate compliant DITA:

**For conref:**
```
"Source/library topics must define reusable elements with @id attributes.
Consuming topics must pull those elements via @conref using full
'path/file.dita#topicid/elementid' syntax. Cover: basic conref pull,
conref range with @conrefend, and at least one conref push (push-replace).
Elements to target: <note>, <warning>, <hazardstatement>."
```

**For keyref:**
```
"Keydef maps must define keys with @keys and @href. Topics must reference
those keys via @keyref on <keyword>, <xref>, and <image>. Cover: simple
key substitution, key-only references, keyscope isolation for variants.
Use keyscope 'platform-a' and 'platform-b' for variant demonstration."
```

**For choicetable:**
```
"Task topics must include <choicetable> elements with <chhead>, <chrow>,
<choption>, and <chdesc>. Each choicetable should have 3-5 rows.
The choices should represent real decision points (e.g. deployment options,
configuration modes, authentication methods)."
```

---

## 4. Full create_job Call

```
create_job(
  recipe_type = "[construct-specific recipe from §1]",
  subject     = "[construct] patterns in [domain]",
  prompt_text = "[construct requirements + domain context]",
  config      = { "conref_density": 0.5 }  # for conref recipes
)
```

---

## 5. Combining Constructs

When the user wants multiple constructs in one dataset, use `freeform` recipe with explicit instructions:

```
create_job(
  recipe_type = "freeform",
  subject     = "advanced DITA constructs: conref, keyref, choicetable, reltable",
  prompt_text = "Generate DITA topics demonstrating: (1) @conref pull on note elements, (2) @keyref variable substitution for product names, (3) <choicetable> in at least 3 task topics, (4) a <reltable> in the map linking related topics. Domain: enterprise software configuration."
)
```

---

## 6. Common Construct Coverage Examples

**"Generate conref examples for note elements"**
```
create_job(
  recipe_type = "conref_pack",
  subject     = "@conref patterns: note, warning, hazardstatement elements in safety documentation",
  prompt_text = "Conref source library with <note type='warning'>, <note type='danger'>, <hazardstatement type='danger'> elements as targets. Consuming topics pull via @conref. Include conref range and conref push variants.",
  config      = {"topic_count": 20, "conref_density": 0.5}
)
```

**"Create DITA with choicetables for cloud configuration"**
```
create_job(
  recipe_type = "choicetable_tasks",
  subject     = "choicetable patterns in cloud infrastructure configuration procedures",
  prompt_text = "Task topics where each step presents a <choicetable> of configuration options: storage class choices, network topology choices, authentication method choices. 3-5 rows per table with <choption> and <chdesc>."
)
```

**"Generate keyref dataset for multi-product docs"**
```
create_job(
  recipe_type = "dita_conref_keyref_dataset_recipe",
  subject     = "@keyref patterns for product variant documentation with keyscopes",
  prompt_text = "Keydef map with keyscopes 'product-a' and 'product-b' each defining keys for product-name, version, install-path. Topics use @keyref on <keyword> and <xref>. Demonstrate how same topic renders differently per keyscope."
)
```
