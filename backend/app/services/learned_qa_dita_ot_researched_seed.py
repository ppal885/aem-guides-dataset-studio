"""Researched DITA-OT documentation prompt corpus for learned-QA retrieval."""

from __future__ import annotations

from typing import Any


_TOPICS: list[dict[str, Any]] = [
    {
        "id": "args_filter_precedence",
        "title": "args.filter precedence and multiple DITAVAL files",
        "terms": ["args.filter", "DITAVAL", "filter precedence", "include", "exclude", "flag"],
        "summary": "DITA-OT can apply one or more DITAVAL files through `args.filter`; when several filters are supplied, order and matching rules decide which condition wins.",
        "command": 'dita --input=book.ditamap --format=html5 --args.filter="admin.ditaval;common.ditaval" --clean.temp=no',
        "checks": ["Record the exact filter-file order passed to DITA-OT.", "Inspect whether the value is separated with the correct OS path separator.", "Compare global filtering with branch `ditavalref` behavior before assuming source XML is wrong."],
    },
    {
        "id": "draft_required_cleanup",
        "title": "args.draft with draft-comment and required-cleanup",
        "terms": ["args.draft", "draft-comment", "required-cleanup", "release output", "titlealts", "PDF"],
        "summary": "`args.draft` controls whether draft-only elements such as `draft-comment` and `required-cleanup` appear in output, with PDF-specific effects that should be tested separately.",
        "command": "dita --input=book.ditamap --format=pdf --args.draft=no --clean.temp=no",
        "checks": ["Verify the transform parameter in the actual command or wrapper scenario.", "Inspect the temporary topic after preprocessing.", "Confirm whether the symptom is HTML/PDF rendering or draft inclusion policy."],
    },
    {
        "id": "temp_debug_attributes",
        "title": "temporary directory and generated debug attributes",
        "terms": ["clean.temp", "dita.temp.dir", "generate-debug-attributes", "xtrf", "xtrc", "debug"],
        "summary": "Keeping the DITA-OT temp directory and generated debug attributes gives source traceability for failures that disappear by the final output stage.",
        "command": "dita --input=book.ditamap --format=html5 --temp=tmp/debug --clean.temp=no -v",
        "checks": ["Set `clean.temp=no` and use a stable temp directory.", "Check `xtrf`/`xtrc` source pointers in intermediate files.", "Do not disable debug attributes while investigating source-location problems."],
    },
    {
        "id": "processing_mode_policy",
        "title": "processing-mode strict, lax, and skip",
        "terms": ["processing-mode", "strict", "lax", "skip", "error recovery"],
        "summary": "`processing-mode` is a DITA-OT error-handling policy: strict fails fast, lax attempts recovery, and skip continues without recovery for some errors.",
        "command": "dita --input=book.ditamap --format=html5 --processing-mode=strict",
        "checks": ["Reproduce in strict mode to reveal hidden broken references.", "Compare strict/lax results before declaring a processor bug.", "Use skip only when the expected data loss is acceptable and documented."],
    },
    {
        "id": "grammar_cache_entities",
        "title": "grammar cache and entity-resolution failures",
        "terms": ["args.grammar.cache", "entities", "parser", "catalog", "grammar"],
        "summary": "`args.grammar.cache` can improve parsing performance, but parser/entity-resolution failures should be isolated by disabling grammar caching and checking catalogs.",
        "command": "dita --input=book.ditamap --format=html5 --args.grammar.cache=no",
        "checks": ["Compare the failure with grammar caching on and off.", "Inspect catalog resolution for DTD/RNG shells and entities.", "Avoid treating a parser cache issue as a DITA semantic issue."],
    },
    {
        "id": "args_resources_root_context",
        "title": "args.resources for key and relationship-table context",
        "terms": ["args.resources", "key definitions", "relationship tables", "single topic", "context"],
        "summary": "`args.resources` can supply additional maps for keys or relationship tables when processing a partial documentation set or a single topic.",
        "command": "dita --input=topic.dita --format=html5 --args.resources=keys.ditamap",
        "checks": ["Confirm whether the build is a full root-map build or partial build.", "Add the map that contains required keys/reltables as resources.", "Do not confuse resource context with normal navigation inclusion."],
    },
    {
        "id": "outer_control_content",
        "title": "outer.control and content outside the map directory",
        "terms": ["outer.control", "generate.copy.outer", "outside map directory", "relative paths", "shared content", "outer content"],
        "summary": "DITA-OT can warn or fail when content is outside the input map directory, so external shared-content structures need explicit path policy.",
        "command": "dita --input=maps/book.ditamap --format=html5 --outer.control=fail",
        "checks": ["Find references that climb outside the root-map directory.", "Choose warn/fail behavior intentionally.", "Use a repository layout that keeps shared content predictable for CI and AEM/Oxygen wrappers."],
    },
    {
        "id": "onlytopic_link_crawl",
        "title": "onlytopic.in.map and link-crawl behavior",
        "terms": ["onlytopic.in.map", "link-crawl", "xref", "conref", "output generation"],
        "summary": "`onlytopic.in.map` and `link-crawl` influence whether linked or reused topics outside direct map references are crawled or generated.",
        "command": "dita --input=book.ditamap --format=html5 --onlytopic.in.map=true --link-crawl=map",
        "checks": ["Separate link discovery from output file generation.", "Check whether a topic is referenced by map, xref, conref, or key.", "Inspect generated job files before changing source references."],
    },
    {
        "id": "force_unique_copy_to",
        "title": "force-unique and copy-to output identity",
        "terms": ["force-unique", "copy-to", "duplicate topics", "output identity", "links"],
        "summary": "`force-unique` can generate `copy-to` values to create unique output files for repeated references to the same topic, but link behavior must be verified.",
        "command": "dita --input=book.ditamap --format=html5 --force-unique=true",
        "checks": ["List every repeated source topic reference.", "Inspect generated output names and rewritten links.", "Avoid using forced uniqueness to hide ambiguous information architecture."],
    },
    {
        "id": "root_chunk_override",
        "title": "root-chunk-override and chunked output",
        "terms": ["root-chunk-override", "chunk", "to-content", "by-topic", "output files"],
        "summary": "`root-chunk-override` can override map-level chunk behavior, so output file boundaries may differ from authored `chunk` attributes.",
        "command": "dita --input=book.ditamap --format=html5 --root-chunk-override=to-content",
        "checks": ["Inspect effective chunk values after preprocessing.", "Compare generated output boundaries before and after override.", "Verify xrefs, search indexing, and context-help IDs after chunk changes."],
    },
    {
        "id": "html_css_parameters",
        "title": "HTML5 CSS parameters and copied assets",
        "terms": ["html5", "args.css", "args.copycss", "args.csspath", "CSS", "assets"],
        "summary": "DITA-OT HTML5 CSS behavior depends on the CSS file parameter, whether CSS is copied, and the path used in generated output.",
        "command": "dita --input=book.ditamap --format=html5 --args.css=site.css --args.copycss=yes --args.csspath=assets/css",
        "checks": ["Inspect the generated HTML link element.", "Verify the CSS file is copied to the expected output path.", "Separate missing CSS from missing `outputclass` or preprocessing content."],
    },
    {
        "id": "html_rellinks",
        "title": "related-link generation in HTML output",
        "terms": ["args.rellinks", "related links", "relationship table", "reltable", "nofamily", "all", "HTML5", "PDF"],
        "summary": "`args.rellinks` controls which related-link roles appear, so HTML and PDF may differ even when the source relationship table is valid.",
        "command": "dita --input=book.ditamap --format=html5 --args.rellinks=all",
        "checks": ["Check reltable membership and link roles.", "Compare transformation defaults for HTML and PDF.", "Verify `linking` attributes before blaming reltable syntax."],
    },
    {
        "id": "pdf_formatter_fonts",
        "title": "PDF formatter and font differences",
        "terms": ["pdf", "pdf.formatter", "FOP", "fonts", "XSL-FO", "formatter"],
        "summary": "PDF failures often depend on the formatter and available fonts, not only on DITA source validity.",
        "command": "dita --input=book.ditamap --format=pdf --pdf.formatter=fop --clean.temp=no",
        "checks": ["Capture formatter warnings and FO-stage errors.", "Verify fonts installed in local, CI, and server environments.", "Compare PDF output after confirming the preprocessed DITA is correct."],
    },
    {
        "id": "pdf_customization_dir",
        "title": "PDF customization directory and plug-in strategy",
        "terms": ["customization.dir", "PDF", "PDF2", "XSLT", "plug-in", "page masters"],
        "summary": "PDF customization should be isolated and versioned; prefer a plug-in strategy for durable PDF2 changes rather than editing toolkit core files.",
        "command": "dita --input=book.ditamap --format=pdf --customization.dir=cfg/pdf",
        "checks": ["Confirm the customization directory is being loaded.", "Keep XSLT, attribute sets, images, and font config versioned together.", "Test the same customization in command line, Oxygen, AEM Guides, and CI."],
    },
    {
        "id": "plugin_install_integration",
        "title": "plug-in install and integrator behavior",
        "terms": ["dita install", "plug-in", "integrator", "pluginsdir", "registry"],
        "summary": "DITA-OT plug-ins must be installed or integrated before their extension points, transtypes, catalogs, or resources are available to builds.",
        "command": "dita install path/to/plugin.zip",
        "checks": ["Confirm the plug-in ID appears after installation/integration.", "Check custom `pluginsdir` or toolkit locations used by wrappers.", "Restart or re-run integration when a wrapper caches the toolkit."],
    },
    {
        "id": "plugin_xml_extension_points",
        "title": "plugin.xml extension points and custom transtypes",
        "terms": ["plugin.xml", "extension point", "transtype", "feature", "depends"],
        "summary": "`plugin.xml` is the contract that declares plug-in features, dependencies, and extension-point contributions for DITA-OT.",
        "command": "dita --input=book.ditamap --format=my-html",
        "checks": ["Validate plug-in ID, dependencies, extension-point names, and feature values.", "Check whether the custom transtype extends the expected base transformation.", "Inspect integration output before troubleshooting XSLT."],
    },
    {
        "id": "store_type_memory",
        "title": "store-type memory versus file temp storage",
        "terms": ["store-type", "memory", "file", "temp directory", "custom plug-ins"],
        "summary": "`store-type=memory` can help I/O-bound builds, but custom plug-ins that expect files in the temp directory may fail.",
        "command": "dita --input=book.ditamap --format=html5 --store-type=memory",
        "checks": ["Test with `store-type=file` and `store-type=memory`.", "Audit custom plug-ins for direct temp-file assumptions.", "Use file mode when debugging intermediate artifacts."],
    },
    {
        "id": "parallel_memory_performance",
        "title": "parallel, conserve-memory, and large build performance",
        "terms": ["parallel", "conserve-memory", "performance", "large map", "memory"],
        "summary": "DITA-OT performance tuning must separate CPU parallelism, memory pressure, validation cost, PDF formatter cost, and temp I/O.",
        "command": "dita --input=book.ditamap --format=html5 --parallel=true --conserve-memory=false",
        "checks": ["Measure preprocessing and final-transform time separately.", "Record Java heap, CPU, temp disk, and formatter behavior.", "Do not tune global flags until a representative large-map repro exists."],
    },
    {
        "id": "validation_wrapper_mismatch",
        "title": "validation differences between DITA-OT and wrapper tools",
        "terms": ["validate", "Oxygen", "AEM Guides", "CI", "grammar", "Schematron"],
        "summary": "Validation results can differ when Oxygen, AEM Guides, CI, and command-line DITA-OT use different catalogs, validators, root maps, or parameters.",
        "command": "dita --input=book.ditamap --format=html5 --validate=true",
        "checks": ["Identify which validator produced the finding.", "Align catalogs, root map, DITAVAL, and plug-ins.", "Separate grammar validity from cross-file completeness and business-rule validation."],
    },
    {
        "id": "release_upgrade_regression",
        "title": "release upgrade regression triage",
        "terms": ["upgrade", "release notes", "deprecated", "regression", "DITA-OT version"],
        "summary": "DITA-OT upgrades can change defaults, warnings, plug-in compatibility, dependencies, and output details; treat upgrade issues as controlled regressions.",
        "command": "dita --input=book.ditamap --format=html5 --clean.temp=no",
        "checks": ["Run old and new DITA-OT versions with identical inputs and parameters.", "Compare logs before comparing final output.", "Check release notes, deprecated parameters, plug-ins, Java support, and customizations."],
    },
]


_PROMPT_TEMPLATES = [
    "How should I troubleshoot {title} in DITA-OT?",
    "What senior checks should a DITA-OT chatbot give for {title}?",
    "Why can {title} behave differently between command-line DITA-OT, Oxygen, AEM Guides, and CI?",
    "Create a minimal repro plan for {title}.",
    "What answer should a senior DITA-OT expert give for {title}?",
]


def _answer(topic: dict[str, Any]) -> str:
    checks = "\n".join(f"- {check}" for check in topic["checks"])
    terms = ", ".join(f"`{term}`" for term in topic["terms"])
    return (
        "## Short answer\n"
        f"{topic['summary']}\n\n"
        "## Scope\n"
        "- Behavior scope: DITA-OT implementation, with source-DITA semantics and wrapper-tool differences called out explicitly.\n"
        f"- Research basis: official DITA-OT documentation area for {topic['title']}.\n"
        f"- Key terms: {terms}\n\n"
        "## Example command context\n"
        "```bash\n"
        f"{topic['command']}\n"
        "```\n\n"
        "## Senior reasoning\n"
        "First reproduce the issue with an explicit DITA-OT command outside the wrapper tool. Then preserve the temporary directory, inspect the first failing processing phase, and compare authored source with effective intermediate files. "
        "If Oxygen, AEM Guides, CI, and command-line DITA-OT differ, align the root map, parameters, DITAVAL files, catalogs, installed plug-ins, Java version, fonts, locale, paths, and DITA-OT version before changing content.\n\n"
        "## Deterministic checks\n"
        f"{checks}\n\n"
        "## Common mistakes\n"
        "- Treating a wrapper-tool scenario as proof of generic DITA-OT behavior.\n"
        "- Editing final CSS, XSLT, or PDF layout before checking the preprocessed effective content.\n"
        "- Hiding warnings with lax settings instead of identifying the exact failing resource and phase.\n\n"
        "## Chatbot answer guardrails\n"
        "- Do not claim the DITA specification mandates a DITA-OT parameter behavior.\n"
        "- Do not cite Oxygen or AEM Guides behavior as universal unless the wrapper context is named.\n"
        "- Always tell the user which command, temp files, logs, and parameters to inspect."
    )


def get_dita_ot_researched_seed_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for topic in _TOPICS:
        for template in _PROMPT_TEMPLATES:
            items.append(
                {
                    "prompt": template.format(title=topic["title"]),
                    "final_answer": _answer(topic),
                    "tags": ["dita-ot", "researched", topic["id"], *topic["terms"]],
                    "topic": "dita_ot_researched",
                    "source_type": "dita_ot_docs_researched",
                    "answer_style": "senior_technical_docs",
                    "status": "approved",
                }
            )
    return items
