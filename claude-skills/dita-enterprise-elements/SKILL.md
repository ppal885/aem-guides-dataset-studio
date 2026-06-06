---
name: dita-enterprise-elements
description: >
  Generate DITA datasets that demonstrate or exercise specific enterprise DITA
  elements and patterns. Use this skill whenever a user mentions specific DITA
  XML elements or authoring constructs in their prompt: "xref", "cross-reference",
  "conref", "keyref", "keys", "duplicate keys", "external keys", "keys pointing
  to external resources", "codeph", "codeblock", "filepath", "varname", "cmdname",
  "uicontrol", "menucascade", "wintitle", "userinput", "systemoutput", "msgph",
  "note types", "hazardstatement", "draft-comment", "required-cleanup",
  "index-see", "indexterm", "table", "simpletable", "choicetable", "properties",
  "stepsection", "substeps", "stepxmp", "tutorialinfo", or any other named DITA
  element. Also triggers on "enterprise DITA patterns", "complex DITA examples",
  "realistic DITA markup", "DITA with real code examples", "software documentation
  DITA", "technical writing DITA patterns".
---

# DITA Enterprise Elements Dataset Generator

This skill generates datasets rich in specific enterprise DITA elements — cross-references,
keys, code elements, reuse patterns, and domain-specific inline markup. It maps element
names from the user's prompt to the right recipes and prompt-text patterns.

---

## 1. Element → Recipe Quick Map

| User says | Elements involved | Best recipe |
|---|---|---|
| xref, cross-reference, xrefs | `<xref>` with `@href`/`@keyref` | `task_topics` or `reference_topics` + rich prompt_text |
| conref, content reuse, conref push | `@conref`, `@conrefend`, conref push | `conref_pack` or `dita_conref_keyref_dataset_recipe` |
| keys, keyref, key definitions | `<keydef>`, `@keyref`, `@keys` | `dita_conref_keyref_dataset_recipe` or `keyscope_demo` |
| duplicate keys, key overrides | Competing keydefs, keyscopes | `keyscope_demo` or `keyref_nested_keydef_chain_map_to_map_to_topic` |
| external keys, external resources | `<keydef>` with `@scope="external"` | `dita_conref_keyref_dataset_recipe` |
| codeph, codeblock, code examples | `<codeph>`, `<codeblock>`, `<pre>` | `task_topics` with `prompt_text` requiring code |
| filepath, cmdname, varname | Inline tech elements | `task_topics` or `reference_topics` |
| uicontrol, menucascade, wintitle | UI navigation elements | `task_topics` (UI procedures) |
| userinput, systemoutput, msgph | Software I/O elements | `task_topics` (command-line procedures) |
| note types, hazardstatement | `<note>`, `<hazardstatement>` | `concept_topics` or `conref_pack` |
| simpletable, properties table | `<simpletable>`, `<properties>` | `properties_table_reference` or `reference_topics` |
| choicetable, choices | `<choicetable>` | `choicetable_tasks` or `choicetable_references` |
| indexterm, index-see | `<indexterm>`, `<index-see>` | `keyword_metadata` |
| bookmap, front matter | `<bookmap>`, `<frontmatter>` | `bookmap_structure` |

---

## 2. Element Groups and How to Request Them

### Code elements (`codeph`, `codeblock`, `filepath`, `cmdname`, `varname`)

These appear naturally in task topics and reference topics when `prompt_text` requests them explicitly.

**subject:**
```
"[domain] command-line procedures and configuration reference"
```

**prompt_text pattern:**
```
"All steps that show commands must use <codeblock> for multi-line code and <codeph>
for inline commands. File paths use <filepath>. Variable names use <varname>.
Command names use <cmdname>. Include realistic code examples with actual syntax
(e.g., 'kubectl apply -f deployment.yaml', 'docker run -d --name app -p 8080:80 nginx')."
```

### Cross-references (`xref`, related-links)

**prompt_text pattern:**
```
"Each topic must include at least one <xref> to a related topic using @keyref
(not @href) where the key is defined in the keydef map. Reference topics link
to task topics that describe how to use them. Task topics link to concept topics
that explain the background."
```

### Keys and keyrefs (internal + external)

**prompt_text pattern:**
```
"Keydef map must define:
- Product name keys (e.g., keys='product-name', keys='product-version') with <keyword> text
- Internal topic keys (keys='install-guide') pointing to a topic in the bundle
- External resource keys (keys='vendor-docs', @scope='external', @format='html') pointing to URLs
Topics must reference these keys via @keyref on <keyword>, <xref>, and <ph>."
```

### Duplicate keys / key overrides

**prompt_text pattern:**
```
"Demonstrate key override behavior: a root keydef map defines keys='config-path'
pointing to a default value. A product-specific submap redefines the same key
with a product-specific value. Show how the submap's definition overrides the
root for that scope. Use keyscopes 'community' and 'enterprise' to isolate variants."
```

### UI elements (`uicontrol`, `menucascade`, `wintitle`)

**prompt_text pattern:**
```
"All UI element names must use <uicontrol>. Navigation paths use <menucascade>
with nested <uicontrol> elements. Window/dialog titles use <wintitle>.
Example: 'Click <menucascade><uicontrol>File</uicontrol><uicontrol>Save As</uicontrol></menucascade>
in the <wintitle>Export Settings</wintitle> dialog.'"
```

### Software I/O elements (`userinput`, `systemoutput`, `msgph`)

**prompt_text pattern:**
```
"Command-line procedures: user-typed input uses <userinput>, system responses use
<systemoutput>, inline message text uses <msgph>. Steps show realistic terminal
sessions where the user types a command and sees a response."
```

---

## 3. Full create_job Pattern for Element-Rich Data

```
create_job(
  recipe_type = "[see §1]",
  subject     = "[domain] + [element focus]",
  prompt_text = "[element requirements from §2] + [domain vocabulary]",
  config      = { "topic_count": 25–40 }
)
```

---

## 4. Enterprise DITA Examples

**"Generate DITA with xrefs, codeph, codeblock for Kubernetes CLI procedures"**
```
create_job(
  recipe_type = "task_topics",
  subject     = "Kubernetes CLI procedures: kubectl commands, manifest files, resource management",
  prompt_text = "Task topics for kubectl operations. Requirements: (1) Every multi-line command uses <codeblock outputclass='language-bash'>. (2) Inline commands use <codeph>. (3) File paths use <filepath>. (4) Each topic has <related-links> with <xref keyref='concept-pods'/> linking to the concept. (5) Variable placeholders use <varname> (e.g., <varname>namespace</varname>, <varname>deployment-name</varname>). Use realistic kubectl commands.",
  config      = {"topic_count": 30}
)
```

**"Create dataset with keys, duplicate keys, and external resource keys"**
```
create_job(
  recipe_type = "dita_conref_keyref_dataset_recipe",
  subject     = "DITA key management patterns: internal keys, external resource keys, keyscope overrides",
  prompt_text = "Demonstrate all key types: (1) Internal topic keys with @keyref on <xref>. (2) Product variable keys with <keyword keyref='product-name'/>. (3) External URL keys with <keydef keys='vendor-api' href='https://api.example.com' scope='external' format='html'/> referenced via <xref keyref='vendor-api'>. (4) Duplicate key override with keyscopes 'v1' and 'v2'. Domain: software product documentation."
)
```

**"Generate DITA with uicontrol, menucascade, wintitle for GUI software"**
```
create_job(
  recipe_type = "task_topics",
  subject     = "GUI application procedures: AEM Guides XML editor, panels, dialogs, toolbar actions",
  prompt_text = "Task topics for AEM Guides UI navigation. All UI element names use <uicontrol>. Navigation paths use <menucascade>. Window titles use <wintitle>. Example step: 'In the <wintitle>Output Presets</wintitle> dialog, click <menucascade><uicontrol>Advanced</uicontrol><uicontrol>DITAVAL</uicontrol></menucascade>'. Include keyboard shortcuts with <shortcut>.",
  config      = {"topic_count": 20}
)
```

**"Generate dataset with all note types and hazardstatement"**
```
create_job(
  recipe_type = "concept_topics",
  subject     = "safety and informational notes in technical documentation: note, tip, important, warning, danger, hazardstatement",
  prompt_text = "Concept topics about different admonition types. Each topic must demonstrate correct usage of: <note type='note'>, <note type='tip'>, <note type='important'>, <note type='warning'>, <note type='danger'>, <note type='restriction'>, and <hazardstatement type='danger'> with <typeofhazard>, <consequence>, <howtoavoid> children. Domain: industrial equipment and enterprise software.",
  config      = {"topic_count": 15}
)
```

**"Produce enterprise DITA with userinput, systemoutput for CLI docs"**
```
create_job(
  recipe_type = "task_topics",
  subject     = "command-line interface documentation: terminal sessions, input/output patterns, error handling",
  prompt_text = "Task topics showing realistic CLI sessions. User-typed text uses <userinput>. System responses use <systemoutput>. Error messages use <msgph>. Structure: show a command prompt, user input, and the system's response as a 3-part exchange. Include error scenarios where the system outputs a warning. Domain: Docker container operations.",
  config      = {"topic_count": 25}
)
```

---

## 5. Multi-element Combination (Freeform)

For datasets requiring several element types simultaneously:

```
create_job(
  recipe_type = "freeform",
  subject     = "enterprise software documentation with all key inline elements",
  prompt_text = "Generate DITA task and reference topics for enterprise software. Requirements:
- Code: <codeblock outputclass='language-bash'> for multi-line, <codeph> for inline
- Paths: <filepath> for file/directory paths
- Variables: <varname> for placeholders
- Commands: <cmdname> for executable names
- UI: <uicontrol> for buttons, <menucascade> for paths, <wintitle> for dialogs
- Terminal: <userinput> for typed input, <systemoutput> for responses
- Notes: at least one <note type='important'> and one <note type='warning'> per 3 topics
- Keys: @keyref on at least one <xref> per topic
- Cross-refs: each task topic has a <related-links> section with links to concept topics
Domain: Kubernetes cluster administration."
)
```
