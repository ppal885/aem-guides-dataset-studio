"""Senior DITA relationship-table prompt corpus for learned-QA retrieval."""

from __future__ import annotations

from typing import Any


_RELTABLE_TOPICS: list[dict[str, Any]] = [
    {
        "id": "reltable_overview",
        "prompt": "What is a reltable in DITA and when should I use it?",
        "short": "`<reltable>` is a map-level relationship table used to declare non-hierarchical relationships among topics so processors can generate related links.",
        "details": [
            "Use it when related links are part of the publication structure rather than inline source-topic content.",
            "A reltable belongs in a DITA map, not inside a topic body.",
            "It does not physically insert `<xref>` elements into source topics; generated links are processor output.",
        ],
        "xml": """<map>
  <title>Installation guide</title>
  <topicref href="install.dita"/>
  <topicref href="configure.dita"/>
  <topicref href="troubleshoot.dita"/>
  <reltable>
    <relrow>
      <relcell><topicref href="install.dita"/></relcell>
      <relcell><topicref href="configure.dita"/></relcell>
      <relcell><topicref href="troubleshoot.dita"/></relcell>
    </relrow>
  </reltable>
</map>""",
        "tags": ["reltable", "relationship table", "related links", "map", "topicref"],
    },
    {
        "id": "relrow_semantics",
        "prompt": "What does relrow do inside a DITA relationship table?",
        "short": "`<relrow>` defines one relationship set inside a `<reltable>`; topics referenced in the same row are candidates for generated related links.",
        "details": [
            "Think of a row as one semantic relationship group.",
            "Each row contains one or more `<relcell>` elements, usually aligned with the reltable column semantics.",
            "Filtering, linking attributes, collection type, and processor behavior decide the final generated links.",
        ],
        "xml": """<reltable>
  <relrow>
    <relcell><topicref href="concept-overview.dita"/></relcell>
    <relcell><topicref href="task-install.dita"/></relcell>
    <relcell><topicref href="reference-options.dita"/></relcell>
  </relrow>
</reltable>""",
        "tags": ["relrow", "reltable", "relcell", "related links", "relationship set"],
    },
    {
        "id": "relcell_semantics",
        "prompt": "What does relcell mean in a DITA reltable?",
        "short": "`<relcell>` is a cell in a relationship-table row; it groups one or more topic references that share the same relationship role for that row.",
        "details": [
            "A cell can contain topic references such as `<topicref href=\"...\"/>` or key-based topic references.",
            "Multiple topicrefs in the same cell are usually peers in that column's role, not separate columns.",
            "An empty `<relcell/>` can be valid when the row has no member for that column, but the table structure should still match the intended column model.",
        ],
        "xml": """<reltable>
  <relrow>
    <relcell>
      <topicref href="install-windows.dita"/>
      <topicref href="install-linux.dita"/>
    </relcell>
    <relcell><topicref href="install-troubleshooting.dita"/></relcell>
  </relrow>
</reltable>""",
        "tags": ["relcell", "reltable", "relrow", "topicref", "same cell"],
    },
    {
        "id": "relheader_relcolspec",
        "prompt": "How do relheader and relcolspec work in DITA reltables?",
        "short": "`<relheader>` holds relationship-column metadata, and `<relcolspec>` describes the semantics or behavior of a relationship-table column.",
        "details": [
            "Use column metadata to distinguish concept, task, reference, troubleshooting, or other relationship roles.",
            "Column semantics can guide tools, validation, and generated link behavior, but final rendering is processor-specific.",
            "`relheader` is structural map metadata, not reader-visible topic body content.",
        ],
        "xml": """<reltable>
  <relheader>
    <relcolspec type="concept"/>
    <relcolspec type="task"/>
    <relcolspec type="reference"/>
  </relheader>
  <relrow>
    <relcell><topicref href="overview.dita"/></relcell>
    <relcell><topicref href="install.dita"/></relcell>
    <relcell><topicref href="cli-options.dita"/></relcell>
  </relrow>
</reltable>""",
        "tags": ["relheader", "relcolspec", "reltable", "column metadata", "type"],
    },
    {
        "id": "linking_attribute_reltable",
        "prompt": "How does the linking attribute affect reltable generated links?",
        "short": "`@linking` controls generated-link participation: `normal`, `sourceonly`, `targetonly`, and `none` affect whether a topic acts as a source, target, both, or neither.",
        "details": [
            '`linking="sourceonly"` means the topic can be a source of generated links, but should not receive generated incoming links where honored.',
            '`linking="targetonly"` means the topic can receive generated links, but should not be the source of outgoing generated related links where honored.',
            "`linking` does not mean the topic is unpublished; it is different from `toc` and `processing-role`.",
            "Evaluate the effective `linking` value on the topicrefs in the active map context.",
            "HTML, PDF, Oxygen, AEM Guides, or custom DITA-OT transforms can render or suppress related links differently.",
        ],
        "xml": """<reltable>
  <relrow>
    <relcell><topicref href="release-notes.dita" linking="sourceonly"/></relcell>
    <relcell><topicref href="upgrade-guide.dita" linking="targetonly"/></relcell>
    <relcell><topicref href="deprecated-options.dita" linking="none"/></relcell>
  </relrow>
</reltable>""",
        "tags": ["linking", "sourceonly", "targetonly", "none", "reltable", "related links"],
    },
    {
        "id": "collection_type_reltable",
        "prompt": "How does collection-type affect relationship-table links?",
        "short": "`@collection-type` describes the relationship among topics, such as `sequence`, `choice`, `family`, or `unordered`; processors may use it when generating related links.",
        "details": [
            "`sequence` suggests ordered previous/next style relationships.",
            "`choice` suggests alternatives; `family` groups related members; `unordered` indicates no sequence.",
            "Do not assume all transforms render every collection type identically.",
        ],
        "xml": """<reltable collection-type="family">
  <relrow>
    <relcell><topicref href="setup-overview.dita"/></relcell>
    <relcell><topicref href="setup-windows.dita"/></relcell>
    <relcell><topicref href="setup-linux.dita"/></relcell>
  </relrow>
</reltable>""",
        "tags": ["collection-type", "sequence", "choice", "family", "unordered", "reltable"],
    },
    {
        "id": "reltable_keys",
        "prompt": "Can reltable topicrefs use keyref instead of href?",
        "short": "Yes. A relationship-table `<topicref>` can use `keyref` where the active map and key scope provide a valid key definition.",
        "details": [
            "This is indirect addressing: the reltable points to a key, and the effective root map resolves that key.",
            "A broken keyref is a key-resolution problem, not proof that reltables cannot use keys.",
            "Scoped keys must be resolved in the reltable's effective map context.",
        ],
        "xml": """<map>
  <keydef keys="install" href="install.dita"/>
  <keydef keys="troubleshoot" href="troubleshoot.dita"/>
  <reltable>
    <relrow>
      <relcell><topicref keyref="install"/></relcell>
      <relcell><topicref keyref="troubleshoot"/></relcell>
    </relrow>
  </reltable>
</map>""",
        "tags": ["reltable", "keyref", "keys", "keyscope", "indirect addressing"],
    },
    {
        "id": "reltable_scope_format",
        "prompt": "Can a DITA reltable link to external HTML or PDF resources?",
        "short": "Yes, relationship-table topicrefs can point to external resources when `href`, `scope`, and `format` are set appropriately and the processor supports rendering those links.",
        "details": [
            "Use `scope=\"external\"` for resources outside the local DITA deliverable.",
            "Use `format=\"html\"`, `format=\"pdf\"`, or another appropriate format value for non-DITA targets.",
            "External reltable links are generated-link metadata; processors may validate and render them differently.",
        ],
        "xml": """<reltable>
  <relrow>
    <relcell><topicref href="install.dita"/></relcell>
    <relcell>
      <topicref href="https://example.com/support" scope="external" format="html"/>
    </relcell>
    <relcell>
      <topicref href="release-notes.pdf" scope="peer" format="pdf"/>
    </relcell>
  </relrow>
</reltable>""",
        "tags": ["reltable", "scope", "format", "external", "html", "pdf", "href"],
    },
    {
        "id": "toc_processing_role_reltable",
        "prompt": "What is the difference between toc, linking, and processing-role in reltables?",
        "short": "`@toc` affects navigation visibility, `@linking` affects generated-link participation, and `@processing-role` affects whether a reference is normal content or a processing resource.",
        "details": [
            "`toc=\"no\"` does not automatically mean the topic is not generated.",
            "`linking=\"none\"` does not automatically mean the topic is omitted from output.",
            "`processing-role=\"resource-only\"` can make a target available for processing without normal navigation/output participation unless referenced normally elsewhere.",
        ],
        "xml": """<map>
  <topicref href="api-reference.dita" toc="no"/>
  <topicref href="keys.ditamap" format="ditamap" processing-role="resource-only"/>
  <reltable>
    <relrow>
      <relcell><topicref href="api-reference.dita" linking="targetonly"/></relcell>
      <relcell><topicref href="overview.dita"/></relcell>
    </relrow>
  </reltable>
</map>""",
        "tags": ["toc", "linking", "processing-role", "resource-only", "reltable"],
    },
    {
        "id": "duplicate_reltable_links",
        "prompt": "Can relationship tables create duplicate related links?",
        "short": "Yes. Duplicate related links, or duplicates, can occur when the same relationship is declared in more than one reltable row, appears through hierarchy-generated links, or is also authored as an inline link.",
        "details": [
            "A senior implementation should normalize effective targets before duplicate suppression.",
            "Normalization must account for direct `href`, `keyref`, `copy-to`, branch filtering, and scoped output identity.",
            "Do not blindly collapse links that point to the same source file if they represent different effective output instances.",
        ],
        "xml": """<map>
  <topicref href="install.dita"/>
  <topicref href="troubleshoot.dita"/>
  <reltable>
    <relrow>
      <relcell><topicref href="install.dita"/></relcell>
      <relcell><topicref href="troubleshoot.dita"/></relcell>
    </relrow>
    <relrow>
      <relcell><topicref href="install.dita"/></relcell>
      <relcell><topicref href="troubleshoot.dita"/></relcell>
    </relrow>
  </reltable>
</map>""",
        "tags": ["duplicate links", "duplicates", "related links", "reltable", "copy-to", "keyref"],
    },
    {
        "id": "troubleshoot_missing_reltable_links",
        "prompt": "How do I troubleshoot reltable related links that do not appear in output?",
        "short": "Troubleshoot missing reltable links by checking the effective map, row/cell structure, target availability, `linking`, filtering, and transform-specific related-link settings.",
        "details": [
            "First verify the reltable is in the root map processing context used by the output preset.",
            "Confirm topicrefs resolve after filtering, key resolution, branch filtering, and copy-to processing.",
            "Compare temporary/intermediate files with final HTML/PDF output before changing source XML.",
        ],
        "xml": """<reltable>
  <relrow>
    <relcell><topicref href="a.dita" linking="normal"/></relcell>
    <relcell><topicref href="b.dita" linking="normal"/></relcell>
  </relrow>
</reltable>""",
        "tags": ["troubleshooting", "missing related links", "reltable", "linking", "filtering", "DITA-OT"],
    },
    {
        "id": "copy_to_branch_reltable",
        "prompt": "How do copy-to and branch filtering affect reltable links?",
        "short": "`copy-to` and branch filtering can change the effective output identity of relationship targets, so reltable links must be evaluated after preprocessing, not only from source hrefs.",
        "details": [
            "The same source topic can produce multiple output instances.",
            "Branch filtering can include, exclude, rename, or scope different branches differently.",
            "Duplicate suppression must compare effective output identities, not just source filenames.",
        ],
        "xml": """<map>
  <topicref href="shared/install.dita" copy-to="product-a/install.dita"/>
  <topicref href="shared/install.dita" copy-to="product-b/install.dita"/>
  <reltable>
    <relrow>
      <relcell><topicref href="shared/install.dita"/></relcell>
      <relcell><topicref href="troubleshoot-install.dita"/></relcell>
    </relrow>
  </reltable>
</map>""",
        "tags": ["copy-to", "branch filtering", "reltable", "related links", "output identity"],
    },
]


_ALIASES: list[tuple[str, str]] = [
    ("Explain reltable relrow relcell with XML example.", "reltable_overview"),
    ("What attributes should I check for relationship table link generation?", "toc_processing_role_reltable"),
    ("Which attributes control reltable links?", "toc_processing_role_reltable"),
    ("Why are my reltable links one-way instead of two-way?", "linking_attribute_reltable"),
    ("How does linking sourceonly affect reltable generated links?", "linking_attribute_reltable"),
    ("Can relcell contain multiple topicrefs?", "relcell_semantics"),
    ("Can I use scoped keys inside relcell topicrefs?", "reltable_keys"),
    ("What does relcolspec type mean in a relationship table?", "relheader_relcolspec"),
    ("Why does a related link appear in HTML but not PDF?", "troubleshoot_missing_reltable_links"),
    ("How should duplicate reltable links be handled?", "duplicate_reltable_links"),
]


def _answer(topic: dict[str, Any]) -> str:
    detail_lines = "\n".join(f"- {detail}" for detail in topic["details"])
    return (
        "## Short answer\n"
        f"{topic['short']}\n\n"
        "## Scope note\n"
        "This is DITA map relationship-table behavior. The DITA source declares relationships; DITA-OT, AEM Guides, Oxygen, or custom transforms decide the final rendered related-link placement and duplicate suppression.\n\n"
        "## XML example\n"
        "```xml\n"
        f"{topic['xml']}\n"
        "```\n\n"
        "## Senior explanation\n"
        f"{detail_lines}\n\n"
        "## Common mistakes\n"
        "- Putting `<reltable>`, `<relrow>`, or `<relcell>` inside a topic body instead of a map.\n"
        "- Assuming reltables edit source topics by inserting `<xref>` elements.\n"
        "- Confusing `toc`, `linking`, and `processing-role`; they control different behaviors.\n\n"
        "## Verification checks\n"
        "- Confirm the active root map includes the reltable.\n"
        "- Check effective targets after filtering, key resolution, branch filtering, and copy-to.\n"
        "- Compare generated/intermediate relationship data with final HTML/PDF output."
    )


def get_reltable_seed_items() -> list[dict[str, Any]]:
    by_id = {topic["id"]: topic for topic in _RELTABLE_TOPICS}
    prompts: list[tuple[str, dict[str, Any]]] = [(topic["prompt"], topic) for topic in _RELTABLE_TOPICS]
    prompts.extend((prompt, by_id[topic_id]) for prompt, topic_id in _ALIASES)

    return [
        {
            "prompt": prompt,
            "final_answer": _answer(topic),
            "tags": ["dita", "map", "senior", "reltable", *topic["tags"]],
            "topic": "dita_reltable",
            "source_type": "dita_reltable_senior_seed",
            "answer_style": "senior_technical_docs",
            "status": "approved",
        }
        for prompt, topic in prompts
    ]
