"""Curated senior-style learned QA seeds for DITA/AEM Guides RAG."""

from __future__ import annotations

from typing import Any

ANSWER_STYLE = "senior_technical_docs"


def _entry(prompt: str, topic: str, tags: list[str], final_answer: str) -> dict[str, Any]:
    return {
        "prompt": prompt,
        "topic": topic,
        "tags": tags,
        "answer_style": ANSWER_STYLE,
        "final_answer": final_answer.strip(),
    }


def _xml_answer(
    *,
    direct: str,
    scope: str,
    example: str,
    expected: list[str],
    mistake: str,
    related: str = "",
) -> str:
    expected_lines = "\n".join(f"- {item}" for item in expected)
    related_block = f"\n\nRelated concept\n{related}" if related else ""
    return f"""{direct}

Scope note
{scope}

Example
```xml
{example.strip()}
```

Expected result
{expected_lines}
{related_block}

Common mistake
{mistake}"""


def _publishing_answer(
    *,
    direct: str,
    example: str,
    command: str,
    expected: list[str],
    mistake: str,
) -> str:
    expected_lines = "\n".join(f"- {item}" for item in expected)
    return f"""{direct}

Scope note
This is a publishing/runtime behavior question, so validate it in the target DITA-OT or AEM Guides output preset.

Source example
```xml
{example.strip()}
```

Command or preset setting
```bash
{command.strip()}
```

Expected result
{expected_lines}

Common mistake
{mistake}"""


def _troubleshooting_answer(title: str, first_check: str, second_check: str, third_check: str, mistake: str) -> str:
    return f"""{title}

Triage order
1. {first_check}
2. {second_check}
3. {third_check}

Evidence to collect
- Root map or output preset used for publishing.
- Exact warning or error text from DITA-OT or AEM Guides.
- Minimal topic/map snippet that reproduces the issue.

Expected senior response
State the likely cause first, then show the smallest XML or preset change that proves the fix.

Common mistake
{mistake}"""


def get_senior_prompt_seed_items() -> list[dict[str, Any]]:
    """Return approved prompt-answer pairs ordered from easy to difficult."""

    items: list[dict[str, Any]] = []

    items.extend(
        [
            _entry(
                "What is a DITA topic and when should I create a new one?",
                "dita_authoring",
                ["topic", "concept", "task", "reference", "authoring", "easy"],
                _xml_answer(
                    direct="A DITA topic is a self-contained unit of information. Create a new topic when the content can stand alone, be reused, or appear independently in a map.",
                    scope="This applies to base DITA authoring, including concept, task, reference, and generic topic structures.",
                    example="""<topic id="install_overview">
  <title>Installation overview</title>
  <body>
    <p>Install the product before configuring integrations.</p>
  </body>
</topic>""",
                    expected=["The topic has one clear subject.", "The topic can be referenced from a map.", "The title describes the topic without relying on surrounding context."],
                    related="Use a map to organize topics into reading order.",
                    mistake="Do not create one giant topic for an entire guide. That weakens reuse, linking, and review workflows.",
                ),
            ),
            _entry(
                "What is the difference between concept, task, and reference topics?",
                "dita_authoring",
                ["concept", "task", "reference", "topic", "easy"],
                _xml_answer(
                    direct="Use a concept for explanation, a task for step-by-step work, and a reference for lookup information.",
                    scope="This is an information typing decision, not a styling decision.",
                    example="""<concept id="why_keys">
  <title>Why keys are useful</title>
  <conbody>
    <p>Keys let maps control link targets and reusable text.</p>
  </conbody>
</concept>

<task id="create_key">
  <title>Create a key definition</title>
  <taskbody>
    <steps>
      <step><cmd>Add a keydef to the map.</cmd></step>
    </steps>
  </taskbody>
</task>

<reference id="key_tokens">
  <title>Key tokens</title>
  <refbody>
    <section><p>Use space-separated key names.</p></section>
  </refbody>
</reference>""",
                    expected=["Concept answers why or what.", "Task answers how.", "Reference answers exact values, syntax, or rules."],
                    mistake="Do not put long conceptual explanation inside task steps. Put the explanation in a concept and link to it.",
                ),
            ),
            _entry(
                "How should I write a clean shortdesc in DITA?",
                "dita_authoring",
                ["shortdesc", "topic", "authoring", "easy"],
                _xml_answer(
                    direct="A good `<shortdesc>` summarizes the topic purpose in one or two concise sentences and helps readers decide whether the topic is relevant.",
                    scope="Use it for reader orientation and search/result summaries, not as a duplicate of the title.",
                    example="""<task id="configure_proxy">
  <title>Configure the proxy server</title>
  <shortdesc>Configure proxy settings when users access repositories through an enterprise network.</shortdesc>
  <taskbody>
    <steps>
      <step><cmd>Open the network settings.</cmd></step>
    </steps>
  </taskbody>
</task>""",
                    expected=["The short description gives context beyond the title.", "It stays brief.", "It does not introduce unrelated prerequisites."],
                    mistake="Do not repeat the title word-for-word in `<shortdesc>`.",
                ),
            ),
            _entry(
                "When should I use section inside a topic?",
                "dita_authoring",
                ["section", "topic", "authoring", "easy"],
                _xml_answer(
                    direct="Use `<section>` to divide a topic body into meaningful subparts when each subpart supports the same topic purpose.",
                    scope="A section is not a replacement for a new topic when the content has an independent subject.",
                    example="""<concept id="publishing_options">
  <title>Publishing options</title>
  <conbody>
    <section>
      <title>HTML output</title>
      <p>Use HTML output for browser-based delivery.</p>
    </section>
    <section>
      <title>PDF output</title>
      <p>Use PDF output for fixed-layout review and distribution.</p>
    </section>
  </conbody>
</concept>""",
                    expected=["Sections organize one topic.", "Each section title supports the parent title.", "The content remains reusable as one unit."],
                    mistake="Do not hide multiple unrelated topics inside sections just to reduce file count.",
                ),
            ),
            _entry(
                "How do I create a basic ordered task in DITA?",
                "dita_authoring",
                ["task", "steps", "cmd", "easy"],
                _xml_answer(
                    direct="Create a task with `<taskbody>`, then put ordered procedural actions in `<steps>` and each user action in `<cmd>`.",
                    scope="This is for strict task authoring where the reader performs actions in sequence.",
                    example="""<task id="enable_feature">
  <title>Enable the feature</title>
  <taskbody>
    <steps>
      <step><cmd>Open the product settings.</cmd></step>
      <step><cmd>Select Enable feature.</cmd></step>
      <step><cmd>Save the configuration.</cmd></step>
    </steps>
  </taskbody>
</task>""",
                    expected=["The actions appear as ordered steps.", "Each `<cmd>` starts with an imperative verb.", "The task is easy to scan."],
                    mistake="Do not put multiple independent actions in one `<cmd>`. Split them into separate steps.",
                ),
            ),
            _entry(
                "What is the right way to add prerequisites to a DITA task?",
                "dita_authoring",
                ["task", "prereq", "steps", "authoring"],
                _xml_answer(
                    direct="Put prerequisites in `<prereq>` before the steps so the reader sees required conditions before starting the procedure.",
                    scope="Use prerequisites for conditions, access, setup, or knowledge required before performing the task.",
                    example="""<task id="publish_pdf">
  <title>Publish a PDF</title>
  <taskbody>
    <prereq>Ensure the map is valid and the Native PDF preset is configured.</prereq>
    <steps>
      <step><cmd>Open the output preset.</cmd></step>
      <step><cmd>Select Generate.</cmd></step>
    </steps>
  </taskbody>
</task>""",
                    expected=["Prerequisites appear before the procedure.", "Steps remain focused on actions.", "Readers can stop early if they are not ready."],
                    mistake="Do not bury prerequisites in step 1 if the user needs them before starting the task.",
                ),
            ),
            _entry(
                "How do I use note, warning, and important correctly in DITA?",
                "dita_authoring",
                ["note", "warning", "important", "authoring"],
                _xml_answer(
                    direct="Use `<note>` for supplemental information, `type='important'` for high-impact guidance, and `type='warning'` for hazards or serious negative outcomes.",
                    scope="The exact label and visual treatment are controlled by the publishing transform.",
                    example="""<note>Restart the service after changing the configuration.</note>
<note type="important">Back up the repository before migration.</note>
<note type="warning">Do not stop the migration process after it starts.</note>""",
                    expected=["The severity matches the consequence.", "Important information is visible without overusing warnings.", "Warnings are reserved for genuinely serious outcomes."],
                    mistake="Do not mark routine tips as warnings. Overuse makes real warnings easier to ignore.",
                ),
            ),
            _entry(
                "How should I mark UI labels and menu choices in DITA?",
                "dita_authoring",
                ["uicontrol", "menucascade", "authoring"],
                _xml_answer(
                    direct="Use `<uicontrol>` for a single UI label and `<menucascade>` for a path through menus or nested UI choices.",
                    scope="This improves semantic tagging and lets output styling treat UI text consistently.",
                    example="""<p>Select <uicontrol>Settings</uicontrol>.</p>
<p>Choose <menucascade>
  <uicontrol>File</uicontrol>
  <uicontrol>Export</uicontrol>
  <uicontrol>PDF</uicontrol>
</menucascade>.</p>""",
                    expected=["UI labels are tagged as UI controls.", "Menu paths are grouped.", "The sentence remains readable in source and output."],
                    mistake="Do not use bold formatting just to identify UI labels. Use semantic DITA elements.",
                ),
            ),
            _entry(
                "How do I represent code commands and filenames in DITA?",
                "dita_authoring",
                ["codeph", "filepath", "cmdname", "authoring"],
                _xml_answer(
                    direct="Use semantic inline elements such as `<codeph>`, `<filepath>`, and `<cmdname>` instead of generic formatting.",
                    scope="The goal is to preserve meaning across HTML, PDF, search, and translation workflows.",
                    example="""<p>Run <cmdname>dita</cmdname> from the project root.</p>
<p>Edit <filepath>config/publish.xml</filepath>.</p>
<p>Set <codeph>args.draft=no</codeph> for final output.</p>""",
                    expected=["Commands, paths, and code values are clearly typed.", "Output styling can distinguish each kind of technical text.", "Translation and review are easier."],
                    mistake="Do not tag every technical word as `<codeph>`. Choose the element that matches the meaning.",
                ),
            ),
            _entry(
                "What is a valid minimal DITA map?",
                "maps",
                ["map", "topicref", "easy"],
                _xml_answer(
                    direct="A minimal DITA map usually has a `<map>` root, a `<title>`, and one or more `<topicref>` elements that point to topics.",
                    scope="Specialized maps such as bookmaps add their own structures, but this is the basic map pattern.",
                    example="""<map>
  <title>Getting started guide</title>
  <topicref href="intro.dita"/>
  <topicref href="install.dita"/>
</map>""",
                    expected=["The map defines publication structure.", "Each topicref contributes a topic to the reading order.", "The title identifies the deliverable."],
                    mistake="Do not confuse a map with a topic. A map organizes topics; it is not authored as reader body content.",
                ),
            ),
        ]
    )

    element_specs = [
        ("What does topicref do in a DITA map?", "topicref", "href='install.dita'", "It adds a topic or resource to the map structure."),
        ("What does topichead do in a DITA map?", "topichead", "navtitle='Administration'", "It creates a visible navigation heading without linking to a topic."),
        ("What does topicgroup do in a DITA map?", "topicgroup", "", "It groups child topicrefs structurally without adding its own visible heading."),
        ("What does keydef do in a DITA map?", "keydef", "keys='product-name' href='reuse/product-name.dita'", "It defines a key without necessarily adding normal navigation content."),
        ("How do I use reltable for related links?", "reltable", "", "It defines topic relationships that processors can turn into related links."),
        ("How do I use xref for cross references?", "xref", "href='install.dita'", "It links from topic content to another target."),
        ("How do I use image correctly in DITA?", "image", "href='images/dialog.png' placement='break'", "It references an image resource with optional placement behavior."),
        ("What is fig used for in DITA?", "fig", "", "It groups a figure title, image, and related content."),
        ("What is dl used for in DITA?", "dl", "", "It represents a definition list or term-description structure."),
        ("When should I use simpletable?", "simpletable", "", "It represents a lightweight row-and-column table without CALS spanning features."),
        ("When should I use table instead of simpletable?", "table", "", "It provides the full CALS table model for column specs and spans."),
        ("What does entry mean in a CALS table?", "entry", "", "It represents a single cell inside a CALS table row."),
        ("What does stentry mean in simpletable?", "stentry", "", "It represents a single cell inside a simpletable row or header."),
        ("What is prolog used for in a DITA topic?", "prolog", "", "It stores metadata about the topic rather than reader body content."),
        ("How do I use metadata in a map?", "metadata", "", "It stores map-level metadata such as audience, keywords, or product context."),
    ]
    for prompt, element, attrs, direct in element_specs:
        attr_text = f" {attrs}" if attrs else ""
        items.append(
            _entry(
                prompt,
                "maps" if element in {"topicref", "topichead", "topicgroup", "keydef", "reltable", "metadata"} else "dita_authoring",
                [element, "xml", "dita"],
                _xml_answer(
                    direct=direct,
                    scope=f"`<{element}>` should be used for its semantic role, not just to force a visual style.",
                    example=f"""<map>
  <title>Example map</title>
  <{element}{attr_text}>
    <topicref href="child-topic.dita"/>
  </{element}>
</map>""" if element in {"topichead", "topicgroup"} else f"""<{element}{attr_text}>Example content</{element}>""",
                    expected=[f"The `{element}` structure is explicit in source.", "Processors can apply semantic output behavior.", "Reviewers can understand intent from markup."],
                    mistake=f"Do not use `<{element}>` when a more specific DITA element expresses the meaning better.",
                ),
            )
        )

    attribute_specs = [
        ("How does @audience filtering work in DITA?", "audience", "customer", "Use `@audience` to mark content for a target audience, then include or exclude it with DITAVAL."),
        ("How does @product filtering work in DITA?", "product", "cloud", "Use `@product` to identify product-specific content variants."),
        ("How does @platform filtering work in DITA?", "platform", "linux", "Use `@platform` to mark platform-specific content."),
        ("How does @props work for custom profiling?", "props", "beta", "Use `@props` for generalized profiling when a specialized profiling attribute is not available."),
        ("What does @otherprops do in DITA?", "otherprops", "internal", "Use `@otherprops` for additional conditional processing values when your environment supports them."),
        ("What does @rev mean in DITA?", "rev", "v2", "Use `@rev` to mark revision-related content for review or publishing workflows."),
        ("What does @status mean in DITA?", "status", "new", "Use `@status` to describe content lifecycle state such as new, changed, deleted, or unchanged."),
        ("What does @importance mean in DITA?", "importance", "high", "Use `@importance` to indicate relative importance where supported by processing."),
        ("What does @translate mean in DITA?", "translate", "no", "Use `@translate` to indicate whether content should be translated."),
        ("What does @xml:lang do in DITA?", "xml:lang", "en-US", "Use `@xml:lang` to identify the language of content."),
        ("What does @format do on xref or topicref?", "format", "html", "Use `@format` to identify the target format when it is not normal DITA topic content."),
        ("What does @scope external do on xref?", "scope", "external", "Use `scope='external'` when linking to resources outside the DITA content set."),
        ("What does @processing-role do on topicref?", "processing-role", "resource-only", "Use `@processing-role` to control whether a resource participates as normal content or supporting content."),
        ("What does @collection-type do in DITA maps?", "collection-type", "sequence", "Use `@collection-type` to describe relationships among child topicrefs."),
        ("What does @toc mean on topicref?", "toc", "no", "Use `@toc` to control whether a topicref appears in generated navigation."),
        ("What does @print mean on topicref?", "print", "no", "Use `@print` to control print-oriented inclusion where supported by the processor."),
        ("What does @search mean in DITA?", "search", "no", "Use `@search` to indicate whether content should participate in search indexing where supported."),
        ("What does @linking mean on topicref?", "linking", "none", "Use `@linking` to influence generated links for the topicref."),
        ("What does @locktitle do on topicref?", "locktitle", "yes", "Use `@locktitle='yes'` to force the map-provided navigation title."),
        ("What does @copy-to do in DITA maps?", "copy-to", "install-copy.dita", "Use `@copy-to` to create an alternate output copy of a referenced topic."),
    ]
    for prompt, attr, value, direct in attribute_specs:
        items.append(
            _entry(
                prompt,
                "publishing" if attr in {"audience", "product", "platform", "props", "otherprops", "toc", "print", "search"} else "reuse_and_maps",
                [attr, "attribute", "dita"],
                _xml_answer(
                    direct=direct,
                    scope=f"`@{attr}` behavior may depend on the active map, DITAVAL file, and publishing transform.",
                    example=f"""<topicref href="install.dita" {attr}="{value}"/>

<topic id="install">
  <title>Install the product</title>
  <body>
    <p {attr}="{value}">This paragraph is marked for the same condition.</p>
  </body>
</topic>""",
                    expected=[f"The `{value}` value is visible to processors.", "Filtering or output behavior can be controlled consistently.", "The source remains explicit for reviewers."],
                    mistake=f"Do not set `@{attr}` and assume it changes output by itself. Confirm the map, filter, or transform uses it.",
                ),
            )
        )

    reuse_specs = [
        ("How do I define and use a key for a product name?", "keydef", "keyref", "product-name", "<keyword keyref=\"product-name\"/>"),
        ("How do I use keyref for a reusable link target?", "topicref", "xref", "install-guide", "<xref keyref=\"install-guide\"/>"),
        ("How do I use conref for a reusable warning note?", "topic", "conref", "restart-warning", "<note conref=\"shared/warnings.dita#warnings/restart-warning\"/>"),
        ("How do I use conkeyref instead of hardcoded conref paths?", "keydef", "conkeyref", "restart-warning", "<note conkeyref=\"restart-warning\"/>"),
        ("How do I create a map-level variable with keywords?", "keydef", "keyword", "product-name", "<keyword keyref=\"product-name\"/>"),
        ("How do I organize a reusable key library map?", "mapref", "keydef", "key-library", "<mapref href=\"keys.ditamap\" processing-role=\"resource-only\"/>"),
        ("How do I reuse legal text safely with conref?", "topic", "conref", "legal-note", "<note conref=\"shared/legal.dita#legal/legal-note\"/>"),
        ("How do I make a link target change per product map?", "topicref", "keyref", "support-home", "<xref keyref=\"support-home\"/>"),
        ("How do I use keyscope for two product variants?", "topicref", "keyscope", "product-a", "<xref keyref=\"product-a.install\"/>"),
        ("How do I avoid duplicate key collisions in large maps?", "topicref", "keyscope", "admin", "<topicref keyscope=\"admin\">"),
        ("How do I reference keys from a peer map?", "topicref", "scope", "peer-guide", "<xref keyref=\"peer-guide.install\"/>"),
        ("How do I keep reuse-only topics out of the TOC?", "topicref", "processing-role", "reuse", "<topicref href=\"reuse.ditamap\" processing-role=\"resource-only\"/>"),
        ("How do I use ditavalref for branch filtering?", "topicref", "ditavalref", "linux", "<ditavalref href=\"linux.ditaval\"/>"),
        ("How do I use branch filtering for two outputs from one map?", "topicref", "ditavalref", "cloud", "<ditavalref href=\"cloud.ditaval\"/>"),
        ("How do I debug a conref that pulls the wrong element?", "topic", "conref", "shared-id", "<note conref=\"shared.dita#shared/note1\"/>"),
    ]
    for prompt, map_element, mechanism, key, consumer in reuse_specs:
        items.append(
            _entry(
                prompt,
                "reuse_and_maps",
                [mechanism, key, "reuse", "map"],
                _xml_answer(
                    direct=f"Use `{mechanism}` when the map should control or support reusable content and references.",
                    scope="Reuse behavior is map-context dependent when keys, key scopes, or branch filtering are involved.",
                    example=f"""<map>
  <title>Reuse example</title>
  <{map_element} keys="{key}" href="shared/{key}.dita"/>
</map>

<topic id="consumer">
  <title>Consumer topic</title>
  <body>
    <p>{consumer}</p>
  </body>
</topic>""",
                    expected=["The reusable target is defined in the map or shared topic.", "The consuming topic remains indirect or reusable.", "Changing the map can change resolution without editing every topic."],
                    mistake="Do not debug reuse only from the topic file. Always check the effective root map and active filters.",
                ),
            )
        )

    publishing_specs = [
        ("How do I exclude internal audience content from final output?", "audience=\"internal\"", "--filter=customer.ditaval", "Internal paragraphs are removed from customer output."),
        ("How do I publish review output with draft comments visible?", "draft-comment", "--args.draft=yes", "Draft comments appear in review output."),
        ("How do I publish final output without required-cleanup?", "required-cleanup", "--filter=release.ditaval", "Required-cleanup content is excluded."),
        ("How do I use DITAVAL to include only Linux content?", "platform=\"linux\"", "--filter=linux.ditaval", "Linux content remains and other platform variants can be excluded."),
        ("How do I use DITAVAL to exclude beta content?", "props=\"beta\"", "--filter=release.ditaval", "Beta-marked content is removed."),
        ("How do I explain args.draft in DITA-OT?", "draft-comment", "--args.draft=yes", "Draft elements are included for review-oriented transforms."),
        ("How do I control TOC visibility for a topic?", "toc=\"no\"", "dita -i root.ditamap -f html5", "The topic can publish without appearing in generated navigation."),
        ("How do I make a topic not print in PDF?", "print=\"no\"", "dita -i root.ditamap -f pdf", "Print-oriented transforms may skip that topic."),
        ("How do I set chunking for fewer HTML files?", "chunk=\"to-content\"", "dita -i root.ditamap -f html5", "Child topics can be combined into a larger output unit."),
        ("How do I keep each topic as its own HTML file?", "chunk=\"by-topic\"", "dita -i root.ditamap -f html5", "Topics are more likely to remain separate output units."),
        ("How do I troubleshoot Native PDF CSS not applying?", "outputclass=\"pdf-special\"", "dita -i root.ditamap -f pdf", "The marked element can be targeted by PDF styling."),
        ("How do I explain a DITA-OT transform type?", "format=\"html5\"", "dita -i root.ditamap -f html5", "The transform controls the output artifact type."),
        ("How do I publish a map with a DITAVAL file?", "audience=\"customer\"", "--filter=customer.ditaval", "Only allowed profile content appears."),
        ("How do I check whether filtering removed too much content?", "props=\"internal\"", "--filter=release.ditaval -v", "Verbose logs and output inspection show what changed."),
        ("How do I document a release-only publishing preset?", "rev=\"release\"", "dita -i root.ditamap -f pdf --filter=release.ditaval", "Release output follows the configured filter rules."),
    ]
    for prompt, marker, command, expected in publishing_specs:
        items.append(
            _entry(
                prompt,
                "publishing",
                ["publishing", "dita-ot", "ditaval", marker.split("=")[0].replace('"', "")],
                _publishing_answer(
                    direct="Use an explicit map, transform, and filter/preset setting so publishing behavior is repeatable.",
                    example=f"""<topic id="publishing_sample">
  <title>Publishing sample</title>
  <body>
    <p {marker}>Conditional publishing content.</p>
  </body>
</topic>""",
                    command=f"dita -i docs/root.ditamap -f html5 {command}",
                    expected=[expected, "The source markup stays unchanged.", "The output changes according to the selected preset or filter."],
                    mistake="Do not rely on authoring attributes alone. Publishing behavior requires the processor or output preset to use those attributes.",
                ),
            )
        )

    aem_specs = [
        ("How should I explain AEM Guides output presets to a writer?", "output preset", "A preset stores reusable publishing configuration for a map."),
        ("How do I troubleshoot AEM Guides map publishing failure?", "publishing failure", "Start from the map, preset, transform log, and any failed referenced topics."),
        ("How do I explain baseline publishing in AEM Guides?", "baseline", "A baseline freezes a reviewed set of topic/map versions for stable publishing."),
        ("How do I explain review workflow versus publishing workflow in AEM Guides?", "review workflow", "Review controls collaboration and approval; publishing creates deliverables."),
        ("How do I troubleshoot missing images in AEM Guides output?", "missing images", "Check DAM path, href, permissions, asset availability, and output logs."),
        ("How do I troubleshoot broken xrefs in AEM Guides?", "broken xref", "Check the href/keyref, map context, target availability, and output preset."),
        ("How do I explain map dashboard usage in AEM Guides?", "map dashboard", "Use it to manage map-level operations such as review, translation, baseline, and output."),
        ("How do I explain conditional profiling in AEM Guides?", "profiling", "Profiling marks source content and output presets choose which conditions publish."),
        ("How do I troubleshoot a topic that is visible in authoring but absent in output?", "absent output", "Check filtering, toc/print flags, resource-only branches, and branch exclusions."),
        ("How do I explain translation readiness for DITA content in AEM Guides?", "translation", "Use semantic markup, stable IDs, clean conrefs, and controlled conditional values."),
    ]
    for prompt, tag, direct in aem_specs:
        items.append(
            _entry(
                prompt,
                "aem_guides",
                ["aem guides", tag, "troubleshooting"],
                _troubleshooting_answer(
                    title=direct,
                    first_check="Confirm the root map and AEM Guides workflow or preset being used.",
                    second_check="Inspect referenced topics, keys, images, filters, and baseline/version selection.",
                    third_check="Use the generated logs or job details to identify the first concrete failure.",
                    mistake="Do not judge the issue from one topic preview alone. AEM Guides behavior is usually map, preset, and repository-context driven.",
                ),
            )
        )

    jira_specs = [
        ("How should I summarize a Jira bug into a senior technical repro?", "jira repro", "Extract environment, exact steps, actual result, expected result, and evidence."),
        ("How do I identify whether a Jira issue is DITA authoring or publishing?", "jira classification", "Classify by where the failure appears: source validation, map resolution, transform, or AEM workflow."),
        ("How do I turn a vague Jira issue into actionable troubleshooting?", "jira troubleshooting", "Ask for the root map, output preset, minimal XML, logs, and screenshots."),
        ("How do I analyze a Jira issue about broken keyrefs?", "jira keyref", "Check key definitions, keyscope, active map, filters, and duplicate key names."),
        ("How do I analyze a Jira issue about missing TOC entries?", "jira toc", "Check topicref presence, toc attributes, filtering, resource-only branches, and transform rules."),
        ("How do I analyze a Jira issue about draft content leaking into PDF?", "jira draft filtering", "Check draft settings, DITAVAL exclusion, preset configuration, and release pipeline command."),
        ("How do I analyze a Jira issue about conref content not appearing?", "jira conref", "Check conref path, target ID, valid element type, filters, and source map context."),
        ("How do I analyze a Jira issue about AEM Guides publishing timeout?", "jira timeout", "Separate content scale, transform error, asset resolution, and infrastructure timeout evidence."),
        ("How do I normalize Jira comments into one final answer?", "jira answer", "Prefer the latest confirmed facts, separate speculation, and preserve the accepted resolution."),
        ("How do I decide if a Jira issue belongs in learned QA?", "jira learned qa", "Only store the final accepted prompt-answer pair after review, not raw unverified issue chatter."),
    ]
    for prompt, tag, direct in jira_specs:
        items.append(
            _entry(
                prompt,
                "jira_understanding",
                ["jira", tag, "qa", "troubleshooting"],
                _troubleshooting_answer(
                    title=direct,
                    first_check="Rewrite the issue into one clear problem statement.",
                    second_check="Separate reproduction steps from observations, logs, and suspected cause.",
                    third_check="Map the issue to DITA, AEM Guides, DITA-OT, or repository/workflow responsibility.",
                    mistake="Do not convert every Jira issue directly into a dataset or learned answer. Only accepted, reviewed resolutions should enter trusted RAG.",
                ),
            )
        )

    advanced_specs = [
        ("How do I debug branch filtering with nested keyscopes?", "branch filtering keyscope", "Check whether the filter removes the branch that defines the scoped keys."),
        ("How do I explain cross-deliverable links with scope peer?", "scope peer", "Use peer for related DITA deliverables rather than normal local topics or external URLs."),
        ("How do I troubleshoot duplicate IDs after copy-to?", "copy-to duplicate id", "Check generated output paths and whether copy-to created multiple addressable copies."),
        ("How do I debug reltable links that do not appear?", "reltable links", "Check reltable placement, topicref targets, linking attributes, and transform support."),
        ("How do I explain map-to-map composition for a large documentation set?", "mapref composition", "Use maprefs to compose deliverables while preserving ownership of submaps."),
        ("How do I design a key library for multiple product versions?", "key library", "Use scoped key libraries and product-specific maps so references resolve by context."),
        ("How do I troubleshoot Native PDF styling that works in HTML but not PDF?", "native pdf css", "Check outputclass, PDF CSS selectors, template rules, and transform logs."),
        ("How do I explain why a topic preview differs from map publishing?", "map context", "Preview lacks full map context for keys, filters, variables, and relationship links."),
        ("How do I diagnose generated links pointing to the wrong product guide?", "wrong key target", "Check active keyscope, duplicate keys, peer map references, and branch order."),
        ("How do I decide between filtering and keyscopes for product variants?", "variants", "Use filtering for content inclusion and keyscopes for scoped target resolution."),
    ]
    for prompt, tag, direct in advanced_specs:
        items.append(
            _entry(
                prompt,
                "advanced_troubleshooting",
                ["advanced", tag, "dita-ot", "aem guides"],
                _troubleshooting_answer(
                    title=direct,
                    first_check="Identify the effective root map and active output preset or transform.",
                    second_check="Inspect the exact branch, key, filter, or stylesheet rule that changes behavior.",
                    third_check="Create a minimal map/topic reproduction before changing production content.",
                    mistake="Do not fix advanced publishing issues by editing random topic content first. Most of these failures are context-resolution problems.",
                ),
            )
        )

    senior_field_specs = [
        ("How do I explain AEM Guides file checkout/check-in problems to a writer?", "file checkout", "Check lock ownership, repository state, permissions, and whether another author has the file open."),
        ("How do I troubleshoot AEM Guides upload of existing DITA files?", "upload existing files", "Validate file names, folder target, duplicate assets, DTD references, and referenced images before upload."),
        ("How do I troubleshoot missing referenced images after uploading existing files?", "upload images", "Check relative href paths, DAM folder structure, file names, case sensitivity, and upload completeness."),
        ("How do I explain why uploaded DITA topics need stable IDs?", "stable ids", "Stable IDs keep xrefs, conrefs, translation memory, and review comments from breaking after import."),
        ("How do I review a ZIP import into AEM Guides before publishing?", "zip import", "Verify root map, folder structure, referenced assets, metadata, validation results, and output preset compatibility."),
        ("How do I triage duplicate filenames during AEM Guides file upload?", "duplicate filenames", "Decide whether to overwrite, rename, version, or import into a separate folder based on ownership and references."),
        ("How do I diagnose upload success but publishing failure?", "upload publish failure", "Separate repository import success from DITA validation, map resolution, filtering, and transform errors."),
        ("How do I explain why AEM Guides folder organization matters for DITA reuse?", "folder organization", "Folder structure affects relative links, reuse libraries, permissions, review ownership, and migration clarity."),
        ("How do I write a senior answer for a broken image href in DITA?", "image href", "Show the source image element, expected DAM path, output symptom, and smallest corrected href."),
        ("How do I write a senior answer for uploaded files with unresolved conrefs?", "upload conref", "Check target file import, target IDs, relative paths, element compatibility, and active map context."),
        ("How do I troubleshoot a DITA-OT preprocess failure?", "dita-ot preprocess", "Start with the first preprocessing error, root map, filters, key resolution, and input file validity."),
        ("How do I troubleshoot DITA-OT duplicate ID warnings?", "dita-ot duplicate id", "Find the duplicate topic or element IDs, then decide whether copy-to or reused source created repeated addresses."),
        ("How do I explain DITA-OT key resolution warnings?", "dita-ot key warnings", "Key warnings usually mean the effective map does not define the key, filtered it out, or defines it in another scope."),
        ("How do I debug DITA-OT failing only in PDF but not HTML?", "dita-ot pdf only", "Compare transform type, PDF plugin customization, image/font handling, and outputclass/CSS processing."),
        ("How do I debug DITA-OT failing only in HTML but not PDF?", "dita-ot html only", "Check HTML-specific chunking, resource copying, link generation, script/CSS assets, and transform parameters."),
        ("How do I explain DITA-OT args.input versus map context?", "args.input", "The input map controls key resolution, filtering, navigation, and relationship links for the transform."),
        ("How do I troubleshoot missing related links in DITA-OT output?", "related links", "Check reltable structure, linking attributes, collection-type, transform support, and whether targets are filtered."),
        ("How do I explain branch filtering to a senior writer?", "branch filtering", "Branch filtering applies DITAVAL conditions to a map branch so one map can publish different variants."),
        ("How do I troubleshoot branch filtering that removes shared keys?", "branch filtering keys", "Confirm the key-defining branch is not excluded before the consuming topic resolves keyrefs."),
        ("How do I decide between ditaval filtering and separate maps?", "ditaval separate maps", "Use filtering for small controlled variations and separate maps when structure, ownership, or deliverables diverge significantly."),
        ("How do I explain subject scheme validation failures?", "subject scheme validation", "Subject scheme failures mean an attribute value is outside the controlled value set active for the map."),
        ("How do I troubleshoot subject scheme values not appearing in AEM Guides?", "subject scheme aem", "Check scheme map reference, root map context, repository location, cache/state, and whether the attribute is controlled."),
        ("How do I explain controlled values to non-technical authors?", "controlled values", "Controlled values keep profiling metadata consistent so filters, search, and publishing presets behave predictably."),
        ("How do I troubleshoot inconsistent product profiling values?", "profiling consistency", "Normalize allowed values, check subject scheme configuration, and clean legacy free-text attribute values."),
        ("How do I debug a map that publishes topics in the wrong order?", "map order", "Check topicref order, maprefs, chunking, reltable expectations, and whether output preset uses a different root map."),
        ("How do I explain why topic preview cannot prove final publishing output?", "preview limitation", "Preview lacks the full map, filter, key, reltable, baseline, and output preset context."),
        ("How do I troubleshoot AEM Guides baseline publishing with stale content?", "baseline stale", "Confirm the baseline version selections and compare them with latest repository versions before republishing."),
        ("How do I write a Jira analysis for stale baseline output?", "jira baseline", "State the baseline used, affected topic versions, actual output, expected output, and verification method."),
        ("How do I write a Jira analysis for upload failures with existing files?", "jira upload", "Capture file package structure, failed file names, error messages, permissions, and smallest reproducing upload set."),
        ("How do I write a Jira analysis for Native PDF CSS regression?", "jira native pdf css", "Capture preset, template/CSS changes, affected selector, expected visual output, actual output, and sample DITA."),
        ("How do I write a Jira analysis for DITA-OT issue indexing?", "jira dita-ot", "Separate upstream DITA-OT behavior from AEM Guides integration and cite the exact transform/log evidence."),
        ("How do I decide whether a Jira issue needs docs, product fix, or data cleanup?", "jira disposition", "Classify the root cause as authoring guidance, product behavior, transform bug, repository data, or environment setup."),
        ("How do I produce a senior answer when evidence is weak?", "weak evidence", "Say what is verified, what is inferred, what evidence is missing, and the next minimal check."),
        ("How do I avoid hallucinated XML examples in answers?", "grounded examples", "Use only valid DITA structures, keep examples minimal, and label processor-dependent behavior clearly."),
        ("How do I answer a DITA question when the user mixes AEM Guides and DITA-OT?", "mixed scope", "Separate base DITA semantics, AEM Guides authoring behavior, and DITA-OT publishing behavior in the response."),
        ("How do I explain root map context in one paragraph?", "root map context", "The root map supplies key definitions, filters, navigation order, relationship tables, and output context for topics."),
        ("How do I troubleshoot a topic valid alone but invalid in a map?", "valid alone invalid map", "Check map-level keys, profiling, relationship tables, branch filters, and referenced resources."),
        ("How do I debug conkeyref in a scoped key library?", "scoped conkeyref", "Check the keyscope prefix, keydef target, target element ID, and whether the key library is in the effective map."),
        ("How do I explain when not to use conref?", "avoid conref", "Avoid conref for content that varies by deliverable, needs translation independence, or should resolve by map context."),
        ("How do I troubleshoot translation issues caused by reuse?", "translation reuse", "Check conrefs, keyrefs, variables, locked text, IDs, and whether reused content needs independent translation context."),
    ]
    for prompt, tag, direct in senior_field_specs:
        items.append(
            _entry(
                prompt,
                "senior_field_guidance",
                ["senior", tag, "dita", "aem guides", "dita-ot", "jira"],
                _troubleshooting_answer(
                    title=direct,
                    first_check="Identify the root map, repository location, output preset, and active filters or baseline.",
                    second_check="Collect the smallest topic/map/XML sample plus the exact warning, error, or observed output.",
                    third_check="Separate DITA semantics, AEM Guides workflow behavior, DITA-OT transform behavior, and Jira evidence.",
                    mistake="Do not answer from general LLM memory first. Ground the response in indexed source evidence, then use the LLM to explain it clearly.",
                ),
            )
        )

    senior_example_specs = [
        ("Show a full example of topichead with topicrefs and explain the TOC output.", "topichead full example", "Use topichead when you need a visible TOC heading that does not link to its own topic."),
        ("Show a full example of topicgroup and explain why it is invisible in the TOC.", "topicgroup full example", "Use topicgroup for structural grouping when the group itself should not create a navigation heading."),
        ("Show a full example of mapref with a reused submap.", "mapref full example", "Use mapref when a root map needs to include another map as part of the effective publication structure."),
        ("Show a full example of a key library map with resource-only.", "key library full example", "Use a resource-only key library when keys and reusable targets must resolve without publishing as normal chapters."),
        ("Show a full example of conkeyref for a reusable warning.", "conkeyref full example", "Use conkeyref when reusable content should be resolved through a map-defined key instead of a fixed file path."),
        ("Show a full example of branch filtering for cloud and on-prem outputs.", "branch filtering full example", "Use branch filtering when one map branch needs a specific DITAVAL condition for a variant output."),
        ("Show a full example of DITAVAL excluding internal-only paragraphs.", "ditaval exclude full example", "Use a DITAVAL exclude rule when internal content must stay in source but not appear in customer output."),
        ("Show a full example of subject scheme controlled values for audience.", "subject scheme full example", "Use subject scheme maps to constrain profiling values so authors pick consistent metadata."),
        ("Show a full example of reltable generated related links.", "reltable full example", "Use relationship tables to define links among topics without adding inline xrefs to every topic."),
        ("Show a full example of copy-to and explain when it is risky.", "copy-to full example", "Use copy-to sparingly when one source topic needs multiple output addresses or labels."),
        ("Show a full example of navtitle and locktitle.", "navtitle locktitle full example", "Use locktitle when the map navigation label must override the topic title."),
        ("Show a full example of chunk to-content versus by-topic.", "chunk full example", "Use chunking to influence output file grouping, not to change source topic ownership."),
        ("How should I answer a user asking why their uploaded map cannot find topics?", "uploaded map missing topics", "Check relative hrefs, folder placement, case-sensitive filenames, upload completeness, and root map selection."),
        ("How should I answer a user asking why AEM Guides upload accepted files but validation fails?", "upload validation", "Explain that repository import and DITA validation are separate checks, then inspect DTD/schema references and links."),
        ("How should I answer a user asking where to store shared reusable topics in AEM Guides?", "shared reuse folder", "Recommend a governed shared folder or reuse map with permissions, naming conventions, and resource-only references."),
        ("How should I answer a user asking how to rename DITA files safely?", "rename files", "Rename with reference updates, check maps, xrefs, conrefs, image hrefs, baselines, and publishing presets."),
        ("How should I answer a user asking how to move DITA topics between folders?", "move topics", "Move topics only after reviewing relative links, reuse references, images, map references, and translation state."),
        ("How should I answer a user asking why deleted files still appear in output?", "deleted files output", "Check baseline selection, cached output, old map references, generated artifacts, and whether the publishing job used latest content."),
        ("How should I answer a user asking why a new topic does not appear in AEM Guides output?", "new topic missing output", "Check whether the topic is referenced by the root map, filtered out, marked resource-only, or excluded by the preset."),
        ("How should I answer a user asking why a topic appears twice in output?", "duplicate topic output", "Check duplicate topicrefs, maprefs, copy-to, generated navigation, and nested submap inclusion."),
        ("How do I triage a Jira that says publishing is slow?", "jira publishing slow", "Separate content scale, image size, transform type, PDF template complexity, environment load, and external service calls."),
        ("How do I triage a Jira that says upload is slow?", "jira upload slow", "Separate package size, file count, asset validation, network latency, repository indexing, and virus/security scanning."),
        ("How do I triage a Jira that says search cannot find uploaded topics?", "jira search indexing", "Check repository indexing delay, metadata extraction, permissions, path, title/shortdesc content, and search scope."),
        ("How do I triage a Jira that says review comments disappeared?", "jira review comments", "Check version history, baseline, workflow state, file rename/move operations, permissions, and whether comments belong to another revision."),
        ("How do I triage a Jira that says conref works locally but not in AEM Guides?", "jira conref aem", "Compare local DITA-OT root map context with AEM Guides repository paths, keys, permissions, and validation pipeline."),
        ("How do I triage a Jira that says DITAVAL works in DITA-OT but not AEM Guides?", "jira ditaval aem", "Compare the command-line filter with the AEM Guides output preset and confirm the same DITAVAL is selected."),
        ("How do I triage a Jira that says Native PDF drops a table row?", "jira native pdf table", "Check CALS table validity, morerows spans, row/entry counts, conditional filtering, and PDF plugin table processing."),
        ("How do I triage a Jira that says keyscope links are wrong after mapref?", "jira keyscope mapref", "Check keyscope name, peer/local scope, submap key definitions, branch position, and duplicate keys."),
        ("How do I explain AEM Guides file management to a new technical writer?", "aem file management onboarding", "Explain that files are managed as repository assets with references, versions, locks, metadata, and publishing context."),
        ("How do I explain uploading existing files to a new AEM Guides user?", "aem upload onboarding", "Explain that upload should preserve folder structure and references, then validate maps, topics, images, and metadata."),
        ("How do I answer if RAG finds AEM docs but no DITA spec evidence?", "rag source split", "Say the AEM workflow is grounded in Experience League, while base DITA semantics should be verified against DITA spec sources."),
        ("How do I answer if RAG finds learned QA but no live source chunks?", "learned qa fallback", "Use learned QA as a reviewed pattern, but call out source limitations and avoid presenting unsupported product specifics as verified."),
        ("How do I answer when the user asks for exact command syntax but sources are weak?", "weak command source", "Give a cautious command pattern only if known, label it as a pattern, and ask for version/preset details for exact syntax."),
        ("How do I answer when the user asks for full XML but the element parent is uncertain?", "uncertain xml parent", "Provide a minimal safe snippet only when valid, otherwise explain the required parent/child context before showing XML."),
        ("How do I answer when the user asks for comparison of DITA table and HTML table?", "dita html table", "Explain DITA table semantics and publishing transformation, not browser HTML authoring as the primary source model."),
        ("How do I answer when the user asks simpletable row span support?", "simpletable row span", "State clearly that row/column span is a CALS table feature, not simpletable behavior."),
        ("How do I answer when the user asks about morerows in simpletable?", "morerows simpletable", "State that morerows applies to CALS table entry cells and does not apply to simpletable stentry cells."),
        ("How do I answer when the user asks about uploading Markdown into AEM Guides?", "upload markdown", "Explain whether Markdown is supported by the configured workflow, then distinguish source upload from DITA conversion."),
        ("How do I answer when the user asks whether AEM Guides changes source DITA during publishing?", "publishing source mutation", "Explain that publishing should generate output artifacts from source and presets, not silently rewrite source topics."),
        ("How do I answer when the user asks why output differs between two presets?", "preset diff", "Compare transform type, filter, baseline, template, parameters, root map, and publishing environment."),
    ]
    for prompt, tag, direct in senior_example_specs:
        items.append(
            _entry(
                prompt,
                "senior_examples_and_triage",
                ["senior", tag, "full example", "aem guides", "dita", "dita-ot", "jira"],
                _troubleshooting_answer(
                    title=direct,
                    first_check="Start with the exact user goal and classify it as authoring, repository management, publishing, or Jira triage.",
                    second_check="Retrieve indexed AEM Guides, DITA spec, DITA-OT, learned QA, or Jira evidence before drafting the final answer.",
                    third_check="Give a direct answer first, then include a minimal valid XML or workflow example when it helps.",
                    mistake="Do not give generic AI advice when the user needs product-specific AEM Guides, DITA, DITA-OT, or Jira troubleshooting guidance.",
                ),
            )
        )

    senior_operational_specs = [
        ("How do I answer when a map has circular maprefs?", "circular maprefs", "Explain that circular map references can create infinite or invalid effective map structures and must be broken at the map architecture level."),
        ("How do I troubleshoot circular conrefs in imported content?", "circular conrefs", "Find the conref chain, identify the loop, and replace one side with authored content or a non-cyclic reusable source."),
        ("How do I explain why a conref target must have a stable ID?", "conref target id", "A conref resolves to a specific element ID, so changing or omitting the target ID breaks reusable content."),
        ("How do I answer when a conref target has the wrong element type?", "conref type mismatch", "Explain that conref replacement must be compatible with the target element type and context."),
        ("How do I troubleshoot conrefend range reuse?", "conrefend range", "Verify the start and end elements are valid siblings, ordered correctly, and compatible with the consuming context."),
        ("How do I explain why xref to a topic ID differs from xref to an element ID?", "xref element id", "A topic-level xref targets the whole topic, while an element-level xref targets a specific element within that topic."),
        ("How do I answer when href points to a folder instead of a DITA file?", "href folder", "Explain that href should resolve to a valid resource, usually a topic/map/image file depending on context."),
        ("How do I troubleshoot spaces and special characters in uploaded DITA filenames?", "filename characters", "Check repository naming rules, URL encoding, transform behavior, and whether references use exact filenames."),
        ("How do I explain case sensitivity problems after migrating DITA files?", "case sensitivity", "Windows may hide case mismatches that Linux, AEM, or publishing pipelines treat as different paths."),
        ("How do I answer when image href works locally but fails after upload?", "image local upload", "Compare local folder layout with DAM/repository layout and update relative hrefs or uploaded asset paths."),
        ("How do I troubleshoot SVG images in Native PDF output?", "svg native pdf", "Check SVG support in the PDF pipeline, image dimensions, external resources, fonts, and PDF plugin limitations."),
        ("How do I troubleshoot MathML rendering in Native PDF output?", "mathml native pdf", "Check transform support, plugin configuration, namespace validity, fonts, and whether fallback images are required."),
        ("How do I answer when codeblock formatting changes in PDF?", "codeblock pdf", "Check outputclass, PDF CSS, whitespace preservation, font settings, and line-wrapping rules."),
        ("How do I explain outputclass without overusing it?", "outputclass guidance", "Use outputclass for output-specific styling hooks, not as a replacement for semantic DITA markup."),
        ("How do I troubleshoot a table that validates but looks wrong in PDF?", "table pdf layout", "Check column specs, widths, spans, filtering side effects, long text, and PDF table styling."),
        ("How do I explain colspec in CALS tables?", "colspec", "Use colspec to define column names, widths, alignment, and other column-level table behavior."),
        ("How do I answer when namest/nameend spans are broken?", "namest nameend", "Verify both column names exist in colspec and that the span does not collide with other cells."),
        ("How do I troubleshoot row spans after conditional filtering?", "filtered row span", "Filtering can remove cells or rows around spans, so validate the effective table after filtering."),
        ("How do I explain why simpletable is better for small lookup tables?", "simpletable small", "Simpletable is easier to author and maintain when no spans, column specs, or complex layout rules are needed."),
        ("How do I answer when a user asks to convert simpletable to CALS table?", "simpletable to cals", "Preserve rows and cells first, then add tgroup, row, entry, and optional colspec only when needed."),
        ("How do I troubleshoot glossary term reuse?", "glossary reuse", "Check glossary entries, key definitions, term references, map context, and whether the glossary map is included."),
        ("How do I explain abbrev and glossentry usage?", "glossentry abbrev", "Use glossentry for glossary definitions and abbreviation structures where terminology needs controlled reuse."),
        ("How do I answer when index terms do not appear in PDF?", "indexterm pdf", "Check indexterm placement, transform support, PDF index generation settings, and whether the preset includes an index."),
        ("How do I troubleshoot searchtitle not appearing in output?", "searchtitle", "Check whether the transform uses searchtitle for search metadata rather than visible navigation."),
        ("How do I explain titlealts to a writer?", "titlealts", "Title alternatives provide alternate titles for specific processing contexts without changing the main topic title."),
        ("How do I troubleshoot shortdesc missing from search results?", "shortdesc search", "Check search indexing settings, metadata extraction, output type, and whether shortdesc is present in the topic."),
        ("How do I answer when a map title and bookmap title conflict?", "bookmap title conflict", "Explain which title is used by the output preset and how map/bookmap metadata affects generated front matter."),
        ("How do I explain bookmap frontmatter and backmatter?", "bookmap frontmatter", "Bookmap frontmatter and backmatter organize publication-level material such as notices, prefaces, appendixes, and index content."),
        ("How do I troubleshoot appendixes not appearing in PDF?", "bookmap appendix", "Check bookmap structure, appendix topicrefs, filtering, output preset, and whether topics are resource-only."),
        ("How do I answer when chapter numbering is wrong?", "chapter numbering", "Check map/bookmap hierarchy, topicref nesting, output preset numbering settings, and filtered branches."),
        ("How do I troubleshoot cross-map links after splitting a guide?", "split guide links", "Check scope, format, keyscope, peer map configuration, and whether each deliverable has the needed keys."),
        ("How do I explain when to use peer scope for another guide?", "peer guide scope", "Use peer scope when the target is another DITA deliverable, not part of the same local output package."),
        ("How do I troubleshoot links opening as external instead of local?", "link scope mismatch", "Check scope, format, href type, output transform, and whether the target is included in the same deliverable."),
        ("How do I answer when generated HTML has broken CSS or assets?", "html assets", "Check resource copying, output directory structure, base paths, custom plugins, and browser network errors."),
        ("How do I troubleshoot AEM Guides publishing assets not copied?", "aem publish assets", "Check asset references, permissions, output preset asset handling, repository paths, and job logs."),
        ("How do I answer when a user asks about uploading non-DITA assets?", "upload non dita", "Explain supported asset types, where they are stored, how DITA references them, and what publishing outputs require."),
        ("How do I troubleshoot a map that opens but cannot be edited?", "map edit lock", "Check permissions, checkout/lock state, repository health, file type association, and workflow state."),
        ("How do I explain versioning versus baseline in AEM Guides?", "version baseline", "Versioning tracks asset revisions; a baseline selects specific revisions for stable review or publishing."),
        ("How do I answer when users confuse review status with publish readiness?", "review publish readiness", "Explain that approval helps governance but publish readiness also requires validation, map context, filters, and output preset checks."),
        ("How do I troubleshoot publishing from the wrong baseline?", "wrong baseline", "Confirm selected baseline, compare topic versions, regenerate output, and record the baseline in the troubleshooting notes."),
        ("How do I answer when a Jira has screenshots but no XML?", "jira screenshots no xml", "Use screenshots as symptoms, but request or infer minimally from map/topic/XML evidence before recommending source changes."),
        ("How do I answer when a Jira has logs but no reproduction steps?", "jira logs no repro", "Extract the first concrete error, map it to likely source/preset context, and ask for the smallest reproducible map/topic set."),
        ("How do I answer when Jira expected result is missing?", "jira missing expected", "State the observed behavior, identify missing acceptance criteria, and ask for expected output or product rule before closing analysis."),
        ("How do I answer when Jira actual result is vague?", "jira vague actual", "Ask for exact output, logs, affected file, root map, preset, and environment before choosing a root cause."),
        ("How do I decide whether a Jira should become learned QA?", "jira learned criteria", "Only learn from a Jira when the prompt, final answer, evidence, and accepted resolution are clear and reusable."),
        ("How do I answer when learned QA conflicts with current Experience League docs?", "learned conflict docs", "Prefer current trusted source evidence and treat learned QA as style/context, not authority over newer documentation."),
        ("How do I answer when DITA spec and AEM Guides behavior differ?", "spec product difference", "Separate normative DITA rules from AEM Guides product behavior and explain which layer controls the observed result."),
        ("How do I answer when DITA-OT behavior differs from AEM Guides output?", "ditaot aem difference", "Compare DITA-OT version, plugins, AEM output preset, Native PDF template, and any product-specific preprocessing."),
        ("How do I explain source confidence in final answers?", "source confidence", "Mention whether the answer is grounded in DITA spec, Experience League, DITA-OT issues, Jira QA, or learned QA examples."),
        ("How do I answer when no indexed source is relevant?", "no source relevant", "Say the indexed sources did not provide enough evidence, give a cautious general path, and recommend what to index or verify next."),
    ]
    for prompt, tag, direct in senior_operational_specs:
        items.append(
            _entry(
                prompt,
                "senior_operational_troubleshooting",
                ["senior", tag, "operations", "dita", "aem guides", "dita-ot", "jira"],
                _troubleshooting_answer(
                    title=direct,
                    first_check="Identify the effective source context: root map, topic, referenced asset, output preset, baseline, and environment.",
                    second_check="Confirm whether the problem is authoring markup, repository/file management, publishing transform, or Jira evidence quality.",
                    third_check="Give a minimal reproducible example or diagnostic checklist before recommending broad content changes.",
                    mistake="Do not collapse source authoring, AEM Guides repository behavior, and DITA-OT publishing behavior into one generic explanation.",
                ),
            )
        )

    return items
