"""Additional official DITA-OT documentation prompt corpus for learned-QA retrieval."""

from __future__ import annotations

from typing import Any


_TOPICS: list[dict[str, Any]] = [
    {
        "id": "figure_table_link_style",
        "title": "figure and table xref label style parameters",
        "terms": ["args.figurelink.style", "args.tablelink.style", "NUMBER", "TITLE", "NUMTITLE", "xref"],
        "doc_area": "Common parameters",
        "summary": "`args.figurelink.style` and `args.tablelink.style` control how generated cross-reference text points to figures and tables, such as number only, title only, or number plus title where supported.",
        "command": "dita --input=book.ditamap --format=pdf --args.figurelink.style=NUMTITLE --args.tablelink.style=NUMTITLE",
        "checks": ["Confirm the output type supports the requested style.", "Inspect generated link text, not only the source `<xref>`.", "For PDF, compare formatter output after preprocessing confirms the figure/table titles exist."],
    },
    {
        "id": "filter_file_paths",
        "title": "args.filter path resolution and multiple filter files",
        "terms": ["args.filter", "DITAVAL", "filter", "path separator", "include", "exclude", "flag"],
        "doc_area": "Common parameters",
        "summary": "`args.filter` identifies DITAVAL files used for include, exclude, and flag rules; multiple filters and relative paths must be handled explicitly in the command or wrapper.",
        "command": 'dita --input=book.ditamap --format=html5 --args.filter="filters/admin.ditaval;filters/common.ditaval"',
        "checks": ["Record the exact filter-file order passed to DITA-OT.", "Verify the resolved path for every DITAVAL file.", "Use the correct OS path separator or repeat the filter option when supported.", "Compare global filtering with branch `ditavalref` before assuming the source topic is wrong."],
    },
    {
        "id": "input_output_dirs",
        "title": "args.input.dir and output.dir path behavior",
        "terms": ["args.input.dir", "output.dir", "--input", "--output", "relative path", "current directory"],
        "doc_area": "DITA command arguments and Common parameters",
        "summary": "`args.input.dir` affects how relative input paths are interpreted, while `output.dir` or `--output` sets where generated output is written.",
        "command": "dita --input=maps/book.ditamap --format=html5 --output=out/html5",
        "checks": ["Print the exact command run by Oxygen, AEM Guides, CI, or the shell.", "Resolve relative paths from the actual working directory.", "Check whether a wrapper sets `args.input.dir` or changes the current directory."],
    },
    {
        "id": "remove_broken_links",
        "title": "remove-broken-links and broken related links",
        "terms": ["remove-broken-links", "related links", "broken links", "xref", "reltable"],
        "doc_area": "Common parameters",
        "summary": "`remove-broken-links` controls removal of broken related links; it is not a substitute for fixing missing targets, invalid keys, or incorrect map context.",
        "command": "dita --input=book.ditamap --format=html5 --remove-broken-links=true",
        "checks": ["Identify whether the broken link comes from reltable, hierarchy, keyref, or inline xref.", "Fix the missing target first when possible.", "Use the parameter deliberately only when broken-link suppression is acceptable for the deliverable."],
    },
    {
        "id": "rewrite_rules",
        "title": "result rewrite rules for generated filenames",
        "terms": ["result.rewrite-rule.class", "result.rewrite-rule.xsl", "RewriteRule", "generated filenames", "preprocess2"],
        "doc_area": "Common parameters and file-name rewrite rules",
        "summary": "`result.rewrite-rule.class` and `result.rewrite-rule.xsl` allow custom filename rewriting during map-first preprocessing, so output paths can differ from source hrefs.",
        "command": "dita --input=book.ditamap --format=html5 --result.rewrite-rule.xsl=cfg/rewrite-output.xsl",
        "checks": ["Confirm whether a custom rewrite rule is active.", "Compare source hrefs with effective generated filenames.", "Check links, search, copy-to, chunking, and context-help IDs after rewriting."],
    },
    {
        "id": "transtype_plugins",
        "title": "transtype selection and custom output formats",
        "terms": ["transtype", "--format", "html5", "pdf", "dita", "markdown", "plugin", "custom transtype"],
        "doc_area": "Common parameters",
        "summary": "`transtype` or `--format` selects the output format; installed plug-ins can add custom transformation types beyond the built-in formats.",
        "command": "dita --input=book.ditamap --format=html5",
        "checks": ["Run `dita transtypes` or `dita --help` to confirm available formats.", "Verify the custom plug-in is installed and integrated.", "Do not assume AEM Guides or Oxygen exposes every installed transtype automatically."],
    },
    {
        "id": "validate_mode",
        "title": "validate parameter and validation scope",
        "terms": ["validate", "grammar", "schema", "catalog", "strict", "cross-file completeness"],
        "doc_area": "Common parameters",
        "summary": "`validate` controls DITA-OT validation, but editor validation, Schematron checks, CMS validation, and cross-file completeness checks may still differ.",
        "command": "dita --input=book.ditamap --format=html5 --validate=true",
        "checks": ["Identify which validator produced the message.", "Align catalogs and plug-ins between command line, Oxygen, AEM Guides, and CI.", "Separate grammar validity from unresolved references, missing resources, and business rules."],
    },
    {
        "id": "html_css_bundle",
        "title": "HTML CSS file, source root, copy flag, and destination path",
        "terms": ["args.css", "args.cssroot", "args.copycss", "args.csspath", "HTML5", "CSS"],
        "doc_area": "HTML-based output parameters",
        "summary": "DITA-OT HTML CSS behavior depends on the CSS filename, source directory, whether DITA-OT copies it, and the destination path under the output directory.",
        "command": "dita --input=book.ditamap --format=html5 --args.css=site.css --args.cssroot=C:/docs/theme --args.copycss=yes --args.csspath=css",
        "checks": ["Use only the CSS filename in `args.css` and the absolute parent directory in `args.cssroot`.", "Set `args.copycss=yes` when DITA-OT should copy the file.", "Inspect generated HTML `<link>` paths and output folders."],
    },
    {
        "id": "html_header_footer_head",
        "title": "HTML header, footer, and head fragment parameters",
        "terms": ["args.hdr", "args.ftr", "args.hdf", "HTML5", "header", "footer", "head", "valid XML"],
        "doc_area": "HTML-based output parameters",
        "summary": "`args.hdr`, `args.ftr`, and `args.hdf` inject valid XML fragments into generated HTML page header, footer, or head areas.",
        "command": "dita --input=book.ditamap --format=html5 --args.hdr=C:/theme/header.xml --args.ftr=C:/theme/footer.xml --args.hdf=C:/theme/head.xml",
        "checks": ["Use absolute paths to valid XML fragments.", "Wrap multiple head elements in a single wrapper if needed.", "Distinguish HTML fragment injection from source DITA metadata or CSS styling."],
    },
    {
        "id": "html_classattr",
        "title": "HTML5 and XHTML class ancestry parameters",
        "terms": ["args.html5.classattr", "args.xhtml.classattr", "PRESERVE-DITA-CLASS", "class ancestry", "outputclass"],
        "doc_area": "HTML5 and HTML-based output parameters",
        "summary": "`args.html5.classattr` and `args.xhtml.classattr` control whether DITA class ancestry is preserved in generated HTML/XHTML class attributes.",
        "command": "dita --input=book.ditamap --format=html5 --args.html5.classattr=yes",
        "checks": ["Inspect the generated HTML element classes.", "Separate preserved DITA class ancestry from authored `outputclass`.", "If CSS selectors stop matching after an upgrade, compare this parameter and generated markup."],
    },
    {
        "id": "html_nav_toc",
        "title": "HTML5 navigation TOC generation",
        "terms": ["html5.toc.generate", "nav-toc", "none", "partial", "full", "HTML5", "TOC"],
        "doc_area": "HTML5 parameters",
        "summary": "`html5.toc.generate` controls TOC file generation, while `nav-toc` controls whether each HTML5 page gets a navigation TOC and how much of the map it includes.",
        "command": "dita --input=book.ditamap --format=html5 --html5.toc.generate=yes --nav-toc=partial",
        "checks": ["Decide whether the issue is missing standalone TOC file or missing per-page navigation.", "Check `nav-toc` values: `none`, `partial`, or `full`.", "Use CSS/devtools to distinguish hidden navigation from ungenerated navigation."],
    },
    {
        "id": "html_output_extension",
        "title": "args.outext for HTML output extensions",
        "terms": ["args.outext", "OUTEXT", "html", "xhtml", "file extension"],
        "doc_area": "HTML-based and HTML5 parameters",
        "summary": "`args.outext` changes the file extension used for generated HTML/XHTML output, which can affect links, hosting rules, and deployment expectations.",
        "command": "dita --input=book.ditamap --format=html5 --args.outext=.html",
        "checks": ["Confirm generated filenames and rewritten links use the expected extension.", "Check web server and CMS routing assumptions.", "Do not confuse output extension changes with source-topic filename changes."],
    },
    {
        "id": "html_indexshow_artlbl",
        "title": "HTML indexterm display and image labels",
        "terms": ["args.indexshow", "indexterm", "args.artlbl", "image label", "HTML5"],
        "doc_area": "HTML-based output parameters",
        "summary": "`args.indexshow` controls whether `<indexterm>` content is rendered, and `args.artlbl` controls whether generated image labels include image filenames.",
        "command": "dita --input=book.ditamap --format=html5 --args.indexshow=yes --args.artlbl=yes",
        "checks": ["Verify whether the requirement is search/index metadata or visible rendered text.", "Inspect source `<indexterm>` location and filtering.", "Confirm generated image labels are intentional before enabling `args.artlbl` broadly."],
    },
    {
        "id": "pdf_bookmap_chapter_bookmark",
        "title": "PDF bookmap order, chapter mini-TOC, and bookmark style",
        "terms": ["args.bookmap-order", "args.chapter.layout", "args.bookmark.style", "MINITOC", "BASIC", "EXPANDED", "COLLAPSE"],
        "doc_area": "PDF parameters",
        "summary": "PDF book structure can be affected by `args.bookmap-order`, chapter mini-TOC behavior by `args.chapter.layout`, and bookmark expansion by `args.bookmark.style`.",
        "command": "dita --input=book.ditamap --format=pdf --args.bookmap-order=retain --args.chapter.layout=BASIC --args.bookmark.style=COLLAPSE",
        "checks": ["Use a bookmap-specific repro when debugging frontmatter/backmatter order.", "Check whether mini-TOCs are controlled globally by `args.chapter.layout` or by PDF customization.", "Compare PDF bookmarks separately from rendered chapter pages."],
    },
    {
        "id": "pdf_fop_userconfig",
        "title": "PDF FOP user configuration and formatter options",
        "terms": ["args.fo.userconfig", "pdf.formatter", "fop", "ah", "xep", "Antenna House", "RenderX"],
        "doc_area": "PDF parameters",
        "summary": "`pdf.formatter` selects the FO formatter, while formatter-specific configuration parameters such as `args.fo.userconfig`, `axf.opt`, and `custom.xep.config` pass configuration to that engine.",
        "command": "dita --input=book.ditamap --format=pdf --pdf.formatter=fop --args.fo.userconfig=C:/fop/fop.xconf",
        "checks": ["Confirm which formatter is actually used.", "Pass the matching configuration file for that formatter.", "Check fonts, image support, and formatter warnings before blaming DITA source."],
    },
    {
        "id": "pdf_i18n_font_mapping",
        "title": "PDF2 internationalization font mapping",
        "terms": ["org.dita.pdf2.i18n.enabled", "font mapping", "I18N", "FOP", "font-selection-strategy", "PDF2"],
        "doc_area": "PDF parameters",
        "summary": "`org.dita.pdf2.i18n.enabled` controls PDF2 font-mapping behavior for per-character font selection, especially relevant when formatter support or custom fonts differ.",
        "command": "dita --input=book.ditamap --format=pdf --org.dita.pdf2.i18n.enabled=true",
        "checks": ["Check DITA-OT and FOP versions before changing font strategy.", "Verify language metadata and font mappings.", "Compare missing-glyph symptoms with formatter logs and generated FO."],
    },
    {
        "id": "pdf_chunk_enabled",
        "title": "PDF2 chunk attribute processing",
        "terms": ["org.dita.pdf2.chunk.enabled", "chunk", "PDF2", "page sequence", "topicref"],
        "doc_area": "PDF parameters",
        "summary": "`org.dita.pdf2.chunk.enabled` controls whether PDF2 honors chunk attribute processing; this can affect PDF structure differently from HTML output.",
        "command": "dita --input=book.ditamap --format=pdf --org.dita.pdf2.chunk.enabled=true",
        "checks": ["Compare HTML chunk behavior with PDF2 chunk settings.", "Inspect effective map and generated FO boundaries.", "Do not assume a `chunk` value affects PDF unless PDF2 chunk processing is enabled and supported."],
    },
    {
        "id": "pdf_theme_vs_customization",
        "title": "PDF theme file versus customization directory",
        "terms": ["theme", "customization.dir", "args.xsl.pdf", "PDF", "PDF2", "customization"],
        "doc_area": "PDF parameters and PDF customization",
        "summary": "PDF theming, `customization.dir`, and `args.xsl.pdf` are different levels of PDF customization; use the lightest mechanism that matches the requirement.",
        "command": "dita --input=book.ditamap --format=pdf --theme=cfg/theme.yaml",
        "checks": ["Use a theme for supported style-level changes.", "Use a PDF plug-in/customization when you need XSLT, attribute sets, page masters, or assets.", "Avoid editing core `org.dita.pdf2` files directly."],
    },
    {
        "id": "config_property_precedence",
        "title": "DITA-OT configuration property precedence",
        "terms": ["--property", "--propertyfile", ".ditaotrc", "local.properties", "plugin.properties", "configuration.properties", "first wins"],
        "doc_area": "Configuration properties",
        "summary": "DITA-OT resolves configuration properties from command-line properties, property files, `.ditaotrc`, `local.properties`, plug-in properties, and default configuration; the first value found wins.",
        "command": "dita --input=book.ditamap --format=html5 --propertyfile=publish.properties",
        "checks": ["List every property source in precedence order.", "Check `.ditaotrc` files in the current directory, ancestors, user home, and toolkit root.", "Remember configuration properties are not the same as runtime transform arguments."],
    },
    {
        "id": "ditaotrc_runtime_config",
        "title": ".ditaotrc runtime configuration layers",
        "terms": [".ditaotrc", "runtime configuration", "configuration properties", "local.properties", "propertyfile"],
        "doc_area": "Configuration properties",
        "summary": "`.ditaotrc` can provide layered runtime configuration from several locations, which can explain why local builds differ from CI, Oxygen, or AEM Guides.",
        "command": "dita --input=book.ditamap --format=html5",
        "checks": ["Search for `.ditaotrc` in the current directory, ancestor directories, the user home, and the DITA-OT root.", "Apply the configuration-property rule that the first value found wins.", "Compare CI and developer machines for hidden configuration files.", "Document which settings belong in project properties versus user-local runtime config."],
    },
]


_PROMPT_TEMPLATES = [
    "How should I use {title} in DITA-OT?",
    "What can go wrong with {title} in DITA-OT?",
    "Give a senior troubleshooting answer for {title}.",
    "Why can {title} behave differently in command-line DITA-OT, Oxygen, AEM Guides, and CI?",
]


def _answer(topic: dict[str, Any]) -> str:
    terms = ", ".join(f"`{term}`" for term in topic["terms"])
    checks = "\n".join(f"- {check}" for check in topic["checks"])
    return (
        "## Short answer\n"
        f"{topic['summary']}\n\n"
        "## Scope\n"
        f"- Source basis: official DITA-OT documentation, {topic['doc_area']}.\n"
        "- Behavior scope: DITA-OT implementation and wrapper-tool configuration, not a DITA specification rule.\n"
        f"- Key terms: {terms}\n\n"
        "## Example command\n"
        "```bash\n"
        f"{topic['command']}\n"
        "```\n\n"
        "## Senior explanation\n"
        "Treat this as a publishing-configuration question first. Confirm the exact DITA-OT command and parameter values used by the shell, Oxygen transformation scenario, AEM Guides output preset, or CI job. "
        "Then inspect the effective output artifact or temporary/intermediate files to verify what the processor actually did.\n\n"
        "## Deterministic checks\n"
        f"{checks}\n\n"
        "## Common mistakes\n"
        "- Presenting a DITA-OT parameter as if it were required by the DITA specification.\n"
        "- Assuming Oxygen, AEM Guides, and CI pass the same parameter values.\n"
        "- Debugging final output styling before confirming the parameter reached DITA-OT.\n\n"
        "## What the chatbot should not claim\n"
        "- Do not claim every output type supports the parameter identically.\n"
        "- Do not claim wrapper-tool behavior is universal DITA-OT behavior unless the wrapper context is named."
    )


def get_dita_ot_more_docs_seed_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for topic in _TOPICS:
        for template in _PROMPT_TEMPLATES:
            items.append(
                {
                    "prompt": template.format(title=topic["title"]),
                    "final_answer": _answer(topic),
                    "tags": ["dita-ot", "official-docs", topic["id"], topic["doc_area"], *topic["terms"]],
                    "topic": "dita_ot_more_docs",
                    "source_type": "dita_ot_docs_more",
                    "answer_style": "senior_technical_docs",
                    "status": "approved",
                }
            )
    return items
