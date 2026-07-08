"""Complex DITA-OT prompt corpus for learned-QA retrieval."""

from __future__ import annotations

from typing import Any


_TOPICS: list[dict[str, Any]] = [
    {
        "id": "dita_command_params",
        "title": "DITA command parameters",
        "terms": ["dita", "command", "args.input", "args.format", "transtype", "output.dir"],
        "summary": "DITA-OT command behavior depends on the resolved input map/topic, transformation type, output directory, temp directory, plug-ins, and parameters passed by CLI, Ant, Oxygen, AEM Guides, or CI.",
        "checks": ["Run the same build from command line with explicit input, format, output, temp, and filter parameters.", "Compare wrapper-tool parameters against the final DITA-OT invocation.", "Capture the full command, DITA-OT version, Java version, plug-ins, and log."],
    },
    {
        "id": "draft_cleanup_filtering",
        "title": "Draft and cleanup content",
        "terms": ["args.draft", "draft-comment", "required-cleanup", "filtering", "DITAVAL"],
        "summary": "Draft and cleanup content is controlled by DITA-OT parameters and filtering rules; source validity alone does not mean draft-only content should appear in published output.",
        "checks": ["Verify the `args.draft` or equivalent transform parameter.", "Check whether DITAVAL excludes draft-related content.", "Compare preprocessing output before final HTML/PDF rendering."],
    },
    {
        "id": "ditaval_branch_filtering",
        "title": "DITAVAL and branch filtering",
        "terms": ["DITAVAL", "ditavalref", "branch filtering", "resourceprefix", "resourcesuffix", "keyscopeprefix", "keyscopesuffix", "filtered branch", "generated file names", "duplicate filenames", "conkeyref"],
        "summary": "DITA-OT filtering can be global or branch-specific; branch filtering can create different effective copies, names, keys, links, and resource identities.",
        "checks": ["List every active DITAVAL source and branch `ditavalref`.", "Inspect generated resource names and key scopes.", "Check for collisions after prefix/suffix rules are applied."],
    },
    {
        "id": "preprocessing_pipeline",
        "title": "DITA-OT preprocessing pipeline",
        "terms": ["preprocess", "temp", "job.xml", "keyref", "conref", "conrefend", "range reuse", "mapref", "submap"],
        "summary": "Many DITA-OT failures are visible in preprocessing before the final transform; debug effective content, keys, conrefs, filters, and generated files before changing output CSS or XSLT.",
        "checks": ["Keep the temporary directory for inspection.", "Compare source XML with preprocessed/intermediate files.", "Find the first preprocessing stage where the expected content disappears."],
    },
    {
        "id": "keyref_resolution",
        "title": "Key reference resolution",
        "terms": ["keyref", "keydef", "keyscope", "root map", "submap", "publishing submap", "preprocess"],
        "summary": "DITA-OT key resolution is map-context dependent; publishing a submap or topic independently can produce different key availability than publishing the intended root map.",
        "checks": ["Confirm the root map passed to DITA-OT.", "Inspect effective key definitions after filtering.", "Check key scopes and branch-filtering prefixes/suffixes."],
    },
    {
        "id": "conref_conkeyref_resolution",
        "title": "Conref and conkeyref resolution",
        "terms": ["conref", "conkeyref", "conrefend", "range reuse", "reuse", "preprocess", "filtered branch"],
        "summary": "DITA-OT content reuse depends on target addressability, element compatibility, filtering, key resolution, and preprocessing order.",
        "checks": ["Validate target URI/key, topic ID, element ID, and range end.", "Confirm target survives filtering.", "Compare editor preview with DITA-OT preprocessed output."],
    },
    {
        "id": "chunk_copyto_links",
        "title": "Chunking, copy-to, and link rewriting",
        "terms": ["chunk", "copy-to", "href", "xref", "xref rewriting", "link rewriting", "generated output"],
        "summary": "Chunking and copy-to change output identity and file boundaries; link rewriting must be validated against generated output, not source paths alone.",
        "checks": ["Inspect generated filenames and output URI map.", "Test xrefs, related links, search, and context help.", "Avoid combining chunk/copy-to changes without a minimal repro."],
    },
    {
        "id": "resource_only_navigation",
        "title": "Resource-only processing",
        "terms": ["processing-role", "resource-only", "toc", "keydef", "navigation"],
        "summary": "Resource-only map references can remain available for keys or reuse while being excluded from normal navigation/reading-order output.",
        "checks": ["Separate navigation inclusion from key/conref availability.", "Check `processing-role`, `toc`, and `linking` independently.", "Verify whether the same resource is referenced normally elsewhere."],
    },
    {
        "id": "html5_webhelp_output",
        "title": "HTML5/WebHelp output",
        "terms": ["html5", "webhelp", "CSS", "search", "outputclass"],
        "summary": "DITA-OT HTML output issues often come from preprocessing, generated file paths, CSS selectors, copied resources, or deployment rather than DITA source validity.",
        "checks": ["Inspect generated HTML and copied assets.", "Check CSS specificity and outputclass propagation.", "Use browser developer tools for missing resources and search failures."],
    },
    {
        "id": "pdf2_native_pdf_output",
        "title": "PDF/PDF2 output",
        "terms": ["pdf", "pdf2", "XSL-FO", "FOP", "Native PDF", "formatter"],
        "summary": "PDF failures must separate DITA-OT preprocessing from PDF transform, XSL-FO, formatter, font, image, and page-layout behavior.",
        "checks": ["Compare preprocessed content before PDF generation.", "Inspect FO/intermediate output when available.", "Check fonts, images, table grids, page masters, and formatter warnings."],
    },
    {
        "id": "tables_in_pdf",
        "title": "CALS tables in DITA-OT PDF",
        "terms": ["CALS", "morerows", "row spans", "filtered rows", "namest", "nameend", "colspec", "PDF", "table rows"],
        "summary": "DITA-OT table failures often come from invalid CALS grids after filtering, unsupported spans, column width behavior, or formatter limits.",
        "checks": ["Validate colspec names, spans, row/column counts, and filtered cells.", "Use a minimal table-only repro.", "Compare HTML table output with PDF/FO rendering."],
    },
    {
        "id": "media_images_svg",
        "title": "Images, SVG, and media",
        "terms": ["image", "svg", "scale", "scalefit", "width", "height", "alt", "PDF image"],
        "summary": "DITA-OT media rendering depends on source references, copied resources, image format support, sizing attributes, accessibility text, and output formatter behavior.",
        "checks": ["Verify image paths and copied resources.", "Compare intrinsic size with `scale`, `width`, `height`, and `scalefit`.", "Check SVG/PDF formatter support and fallback strategy."],
    },
    {
        "id": "plugin_extension_points",
        "title": "DITA-OT plug-ins and extension points",
        "terms": ["plugin", "extension point", "integrator", "transtype", "XSLT"],
        "summary": "DITA-OT customization should use plug-ins and documented extension points instead of modifying toolkit core files.",
        "checks": ["Install and run the integrator after plug-in changes.", "Check extension point IDs and transtype dependencies.", "Keep custom XSLT/CSS/resources packaged with the plug-in."],
    },
    {
        "id": "catalog_grammar_resolution",
        "title": "Catalog and grammar resolution",
        "terms": ["catalog", "DTD", "Relax NG", "grammar", "specialization"],
        "summary": "Grammar and specialization issues depend on XML catalog resolution, plug-in order, shell declarations, and whether Oxygen/DITA-OT use the same catalogs.",
        "checks": ["Inspect effective catalogs after plug-in integration.", "Compare Oxygen catalog resolution with command-line DITA-OT.", "Check public/system IDs, URI rewrites, and specialization dependencies."],
    },
    {
        "id": "logging_diagnostics",
        "title": "Logs and diagnostics",
        "terms": ["log", "verbose", "debug", "warning", "error", "stack trace"],
        "summary": "DITA-OT troubleshooting should start from the first meaningful warning/error in the log and the processing phase where it occurs.",
        "checks": ["Run verbose/debug logging when reproducing.", "Classify messages as validation, preprocessing, transform, formatter, or plug-in failures.", "Preserve the full log and minimal input bundle."],
    },
    {
        "id": "ci_reproducibility",
        "title": "CI and reproducible publishing",
        "terms": ["CI", "Jenkins", "pipeline", "Docker", "reproducible", "baseline"],
        "summary": "A DITA-OT build that works locally but fails in CI usually differs by Java, DITA-OT version, plug-ins, catalogs, paths, fonts, locale, permissions, or filesystem case sensitivity.",
        "checks": ["Record exact toolchain versions and environment variables.", "Clone submodules/shared content before publishing.", "Run the same command locally and in CI with identical parameters."],
    },
    {
        "id": "performance_memory",
        "title": "Performance and memory",
        "terms": ["performance", "memory", "large map", "incremental", "cache", "temp"],
        "summary": "Large DITA-OT builds can be slowed by map size, key/conref graphs, validation, image processing, PDF formatting, and repeated clean temp builds.",
        "checks": ["Measure preprocessing vs final transform time.", "Check Java memory and temp directory behavior.", "Reduce to a representative large-map repro before optimizing."],
    },
    {
        "id": "uri_paths_platforms",
        "title": "URI, paths, and platform differences",
        "terms": ["URI", "path", "path issues", "filenames", "spaces", "non-ASCII", "case-sensitive", "Windows", "Linux"],
        "summary": "DITA-OT path failures often come from URI escaping, Windows backslashes, case sensitivity, non-ASCII filenames, spaces, or different working directories.",
        "checks": ["Use URI syntax, not OS-specific path assumptions.", "Test on the target filesystem case sensitivity.", "Check base paths, XML catalogs, and copied resource paths."],
    },
    {
        "id": "validation_strictness",
        "title": "Validation and strictness",
        "terms": ["validate", "grammar", "Schematron", "strict", "completeness"],
        "summary": "DITA-OT validation, editor validation, and CMS completeness checks may not enforce the same rules, so failures must identify which validator produced which finding.",
        "checks": ["Separate XML grammar validation from cross-file completeness checks.", "Compare editor and command-line validation contexts.", "Do not suppress warnings globally until the failing rule is understood."],
    },
    {
        "id": "migration_deprecation",
        "title": "Version upgrades and migration",
        "terms": ["upgrade", "deprecated", "migration", "breaking change", "DITA-OT version"],
        "summary": "DITA-OT upgrades can change warnings, defaults, dependencies, plug-in compatibility, or output behavior; compare the old and new toolchain before editing content.",
        "checks": ["Record old/new DITA-OT versions and plug-ins.", "Run a golden-output comparison.", "Check release notes, deprecated parameters, and custom plug-in compatibility."],
    },
]


_PROMPT_TEMPLATES = [
    "How should a senior DITA-OT expert troubleshoot {title}?",
    "What deterministic checks should I run for {title} in DITA-OT?",
    "Why can {title} behave differently in Oxygen, AEM Guides, CI, and command-line DITA-OT?",
    "What should a DITA chatbot answer when a user asks about {title}?",
    "Create a minimal repro strategy for a complex DITA-OT issue involving {title}.",
]


def _xml_example(topic_id: str) -> str:
    if topic_id == "draft_cleanup_filtering":
        return '<topic id="draft"><title>Draft</title><body><draft-comment>Internal note</draft-comment><required-cleanup>Fix before release</required-cleanup></body></topic>'
    if topic_id == "ditaval_branch_filtering":
        return '<topicref href="install.dita"><ditavalref href="filters/admin.ditaval" keyscopeprefix="admin-" resourcesuffix="-admin"/></topicref>'
    if topic_id == "keyref_resolution":
        return '<map><keydef keys="product-name"><topicmeta><keywords><keyword>Acme Pro</keyword></keywords></topicmeta></keydef><topicref href="install.dita"/></map>'
    if topic_id == "conref_conkeyref_resolution":
        return '<p conkeyref="reuse/install-note">Fallback note</p>'
    if topic_id == "chunk_copyto_links":
        return '<topicref href="shared/install.dita" copy-to="product-a-install.dita" chunk="to-content"/>'
    if topic_id == "resource_only_navigation":
        return '<keydef keys="product-name" href="reuse/product.dita" processing-role="resource-only"/>'
    if topic_id == "tables_in_pdf":
        return '<entry namest="col1" nameend="col2" morerows="1">Spanned cell</entry>'
    if topic_id == "media_images_svg":
        return '<image href="diagram.svg" scale="75" scalefit="yes"><alt>Architecture diagram</alt></image>'
    return '<map><topicref href="guide.dita"/></map>'


def _answer(topic: dict[str, Any]) -> str:
    checks = "\n".join(f"- {check}" for check in topic["checks"])
    terms = ", ".join(f"`{term}`" for term in topic["terms"])
    return (
        "## Short answer\n"
        f"{topic['summary']}\n\n"
        "## Scope\n"
        f"- DITA-OT doc area: {topic['title']}\n"
        f"- Key terms: {terms}\n"
        "- Behavior scope: DITA-OT implementation plus DITA source semantics and wrapper-tool configuration.\n\n"
        "## Minimal XML / command context\n"
        "```xml\n"
        f"{_xml_example(topic['id'])}\n"
        "```\n\n"
        "## Senior DITA-OT reasoning\n"
        "Start by identifying whether the symptom appears in source validation, DITA-OT preprocessing, final transform, formatter/rendering, plug-in customization, or wrapper-tool configuration. "
        "Then compare authored source XML with effective intermediate output and final artifacts. If Oxygen, AEM Guides, CI, and command-line DITA-OT differ, align the same root map, parameters, DITAVAL files, catalogs, plug-ins, Java version, fonts, locale, paths, and processor version before drawing conclusions.\n\n"
        "## Deterministic checks\n"
        f"{checks}\n\n"
        "## Common mistakes\n"
        "- Treating editor preview or CMS output as proof of core DITA-OT behavior without reproducing the DITA-OT command.\n"
        "- Debugging final CSS/PDF layout before inspecting preprocessed effective content.\n"
        "- Suppressing warnings globally instead of identifying the processing phase and exact failing resource.\n\n"
        "## Must include in a chatbot answer\n"
        "- Direct answer first.\n"
        "- Processing phase involved.\n"
        "- Files/parameters/logs to inspect.\n"
        "- Clear distinction between DITA semantics, DITA-OT behavior, and Oxygen/AEM/CI wrapper behavior."
    )


def get_dita_ot_complex_seed_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for topic in _TOPICS:
        for index, template in enumerate(_PROMPT_TEMPLATES, 1):
            prompt = template.format(title=topic["title"])
            items.append(
                {
                    "prompt": prompt,
                    "final_answer": _answer(topic),
                    "tags": ["dita-ot", "complex", topic["id"], *topic["terms"]],
                    "topic": "dita_ot_complex",
                    "source_type": "dita_ot_docs_complex",
                    "answer_style": "senior_technical_docs",
                    "status": "approved",
                }
            )
    return items
