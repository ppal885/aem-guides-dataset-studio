"""Senior DITA attribute prompt corpus for learned-QA retrieval."""

from __future__ import annotations

from typing import Any


_ATTRIBUTE_ROWS: list[tuple[str, str, str, str, str, str]] = [
    ("href", "Direct URI addressing", "points a reference directly to a target resource or fragment", "topicref, xref, link, image, object, mapref", "DITA specification + processor URI resolution", "href uri direct-addressing links"),
    ("keyref", "Indirect key-based addressing", "resolves a reference through the active map key space instead of a literal URI", "topicref, xref, link, keyword, ph and other key-aware elements", "DITA specification key resolution + map context", "keyref keys indirect-addressing keyspace"),
    ("keys", "Key definition", "declares one or more key names supplied by a map topic reference or key definition", "topicref, keydef, mapref and key-defining map constructs", "DITA specification key definition behavior", "keys keydef keyspace"),
    ("keyscope", "Scoped key spaces", "marks a map branch as a named key scope with separate key resolution context", "map, topicref, mapref, keydef", "DITA specification key-scope behavior", "keyscope scoped-keys map-context"),
    ("conref", "Direct content reference", "pulls reusable content directly from a target element addressed by URI and fragment", "most content elements where the target is compatible", "DITA specification content-reference behavior", "conref reuse direct-content"),
    ("conkeyref", "Indirect content reference", "pulls reusable content through a key-defined target rather than a literal URI", "content elements that allow conref-like reuse", "DITA specification + key resolution context", "conkeyref reuse keyref"),
    ("conrefend", "Content reference range end", "marks the ending element of a conref range", "elements that participate in valid conref ranges", "DITA specification content-reference behavior", "conrefend range-reuse"),
    ("processing-role", "Resource semantics", "states whether a map reference is normal reading-order content or resource-only supporting material", "topicref, mapref, topichead, topicgroup, keydef", "DITA map processing behavior + processor implementation", "processing-role resource-only navigation"),
    ("toc", "Navigation inclusion", "controls whether a map reference contributes to generated navigation such as TOC entries", "topicref, mapref, topichead, topicgroup", "DITA map semantics + output implementation", "toc navigation"),
    ("linking", "Link participation", "controls participation in generated links as source, target, both, or neither", "topicref and related linking contexts", "DITA linking semantics + processor implementation", "linking related-links"),
    ("scope", "Target relationship scope", "classifies a reference as local, peer, or external", "href/key-targeting references", "DITA linking semantics + processor validation", "scope local peer external"),
    ("format", "Target format hint", "identifies the format of the target resource such as dita, ditamap, html, or pdf", "href/key-targeting references", "DITA linking semantics + processor implementation", "format target-resource"),
    ("type", "Target type hint", "identifies the expected type of a referenced target", "xref, link, topicref and related references", "DITA linking semantics + processor implementation", "type target-type"),
    ("collection-type", "Relationship collection semantics", "controls generated relationships among child topic references", "topicref and map branches", "DITA map linking semantics", "collection-type family sequence choice unordered"),
    ("cascade", "Cascading behavior", "controls how eligible metadata and attributes cascade through map branches", "map and topicref contexts", "DITA map metadata semantics", "cascade metadata inheritance"),
    ("locktitle", "Navigation-title locking", "controls whether map-supplied navigation title overrides target title behavior", "topicref, mapref", "DITA map title resolution behavior", "locktitle navtitle titles"),
    ("lockmeta", "Metadata locking", "controls whether map metadata overrides or locks corresponding topic metadata behavior", "topicref and map metadata contexts", "DITA map metadata semantics", "lockmeta metadata"),
    ("navtitle", "Navigation title", "supplies title text intended for navigation labels", "topicmeta/navtitle or map reference contexts", "DITA map title behavior + output implementation", "navtitle navigation title"),
    ("copy-to", "Output identity copy", "creates an alternate output identity for a referenced topic", "topicref", "DITA processing/resource identity behavior", "copy-to output-identity"),
    ("chunk", "Chunking behavior", "requests combining, splitting, or selecting topic output chunks", "topicref and map branches", "DITA-OT/processor implementation guided by DITA map semantics", "chunk chunking output"),
    ("audience", "Profiling audience", "marks content applicability by intended audience", "many DITA elements", "DITA conditional processing + DITAVAL", "audience profiling filtering"),
    ("platform", "Profiling platform", "marks content applicability by platform", "many DITA elements", "DITA conditional processing + DITAVAL", "platform profiling filtering"),
    ("product", "Profiling product", "marks content applicability by product", "many DITA elements", "DITA conditional processing + DITAVAL", "product profiling filtering"),
    ("props", "Generic profiling", "provides generic conditional-processing values", "many DITA elements", "DITA conditional processing + DITAVAL", "props profiling filtering"),
    ("otherprops", "Additional generic profiling", "provides additional conditional-processing values", "many DITA elements", "DITA conditional processing + DITAVAL", "otherprops profiling filtering"),
    ("rev", "Revision marker", "marks revision-related applicability or change context", "many DITA elements", "DITA metadata/filtering semantics + processor implementation", "rev revision profiling"),
    ("status", "Content status", "indicates content status such as new, changed, or deleted depending on vocabulary/version", "many DITA elements", "DITA metadata semantics + processor implementation", "status revision"),
    ("importance", "Importance metadata", "indicates relative importance or priority of content", "many DITA elements", "DITA metadata semantics", "importance metadata"),
    ("translate", "Translation control", "indicates whether content should be translated", "many DITA elements", "DITA localization semantics", "translate localization"),
    ("xml:lang", "Language identification", "declares the natural language of an element and descendants", "XML/DITA elements", "XML + DITA localization/output behavior", "xml:lang localization language"),
    ("dir", "Text direction", "indicates text direction such as ltr or rtl", "many DITA elements", "DITA localization + output behavior", "dir rtl ltr localization"),
    ("outputclass", "Output styling hook", "provides an output-specific class or hint for styling/custom processing", "many DITA elements", "Processor/output implementation", "outputclass css styling"),
    ("class", "Specialization ancestry", "records DITA specialization ancestry for processors", "DITA elements", "DITA specialization architecture", "class specialization"),
    ("id", "Element identity", "identifies a topic or element for references and processing", "topics and many elements", "XML ID + DITA addressing semantics", "id fragment addressing"),
    ("xml:id", "XML identity", "provides XML-level element identity where supported", "XML elements", "XML identity + processor support", "xml:id id addressing"),
    ("domains", "Domain declaration", "declares domains used by a document type shell", "root elements/document type contexts", "DITA specialization architecture", "domains specialization"),
    ("specializations", "Specialization declaration", "declares specialization modules or ancestry where used", "document type contexts", "DITA specialization architecture", "specializations specialization"),
    ("base", "Base conditional attribute", "provides base conditional-processing extension values", "many DITA elements", "DITA conditional processing", "base profiling"),
    ("deliveryTarget", "Delivery target", "marks content for a delivery target or output channel", "many DITA elements where supported", "DITA conditional/output targeting semantics", "deliveryTarget output-targeting"),
    ("print", "Print applicability", "marks print-specific inclusion or exclusion intent", "many DITA elements", "DITA conditional processing + output implementation", "print pdf filtering"),
    ("search", "Search behavior hint", "indicates whether content should participate in search where supported", "map/topic contexts where supported", "Processor/search implementation", "search indexing"),
    ("query", "Query text", "carries query or search-related text in supported contexts", "search/query-related elements", "DITA element-specific semantics", "query search"),
    ("sort-as", "Sorting key", "provides alternate sort text", "index/glossary/metadata contexts", "Processor/indexing implementation", "sort-as sorting index"),
    ("start", "Start value", "sets a start value for ordered structures where supported", "ordered list or sequence contexts", "DITA element-specific semantics", "start ordered-list"),
    ("compact", "Compact rendering hint", "requests compact presentation where supported", "list/table contexts in older vocabularies", "Output implementation hint", "compact rendering"),
    ("morerows", "CALS row spanning", "makes a CALS table entry span additional rows below the current row", "CALS table entry only", "CALS table model in DITA", "morerows cals table row-span"),
    ("namest", "CALS column-span start", "names the starting column for a horizontal span", "CALS table entry", "CALS table model in DITA", "namest cals column-span"),
    ("nameend", "CALS column-span end", "names the ending column for a horizontal span", "CALS table entry", "CALS table model in DITA", "nameend cals column-span"),
    ("colname", "CALS column name", "associates an entry or colspec with a named table column", "CALS colspec/entry", "CALS table model in DITA", "colname cals table"),
    ("colnum", "CALS column number", "declares a column number in a colspec", "CALS colspec", "CALS table model in DITA", "colnum cals table"),
    ("colwidth", "CALS column width", "declares preferred column width", "CALS colspec", "CALS table model + output implementation", "colwidth cals pdf"),
    ("rowsep", "CALS row separator", "controls row separator rendering where supported", "CALS table elements", "CALS table model + output implementation", "rowsep cals"),
    ("colsep", "CALS column separator", "controls column separator rendering where supported", "CALS table elements", "CALS table model + output implementation", "colsep cals"),
    ("align", "Alignment", "sets horizontal alignment where supported", "tables, images, and other supported contexts", "Element-specific DITA/output behavior", "align layout"),
    ("valign", "Vertical alignment", "sets vertical alignment where supported", "CALS table contexts", "CALS table model + output implementation", "valign cals"),
    ("char", "Alignment character", "sets a character alignment marker where supported", "CALS table contexts", "CALS table model + output implementation", "char alignment"),
    ("charoff", "Character offset", "sets offset for character alignment where supported", "CALS table contexts", "CALS table model + output implementation", "charoff alignment"),
    ("rowsep", "CALS row separator", "controls row separator rendering where supported", "CALS table elements", "CALS table model + output implementation", "rowsep cals"),
    ("frame", "Table frame", "controls outer table frame rendering where supported", "CALS table/tgroup contexts", "CALS table model + output implementation", "frame cals table"),
    ("pgwide", "Page-wide table hint", "requests page-wide table treatment where supported", "CALS table", "Output implementation hint", "pgwide table pdf"),
    ("orient", "Orientation hint", "requests orientation such as landscape where supported", "CALS table contexts", "Output implementation hint", "orient landscape table"),
    ("rowheader", "Row-header semantics", "indicates row-header behavior where supported", "CALS table contexts", "CALS table accessibility/output behavior", "rowheader accessibility table"),
    ("headers", "Header association", "associates table cells with header IDs where supported", "table entries in supported models", "Table accessibility semantics + output implementation", "headers accessibility table"),
    ("scope", "Header/link scope", "classifies relationship scope or header applicability depending on element context", "references and table header contexts", "Context-specific DITA semantics", "scope references table"),
    ("alt", "Alternative text", "supplies alternative text for images or media where supported", "image/media contexts", "Accessibility semantics + output implementation", "alt accessibility image"),
    ("placement", "Image/object placement", "indicates inline or break placement for media", "image/object contexts", "DITA media semantics + output implementation", "placement image layout"),
    ("height", "Media height", "sets preferred height where supported", "image/object/media contexts", "Output implementation", "height image media"),
    ("width", "Media width", "sets preferred width where supported", "image/object/media contexts", "Output implementation", "width image media"),
    ("scale", "Media scale", "sets preferred scale percentage where supported", "image/media contexts", "Output implementation", "scale image media"),
    ("scalefit", "Media scale-to-fit", "requests fitting media into available area where supported", "image/media contexts", "Output implementation", "scalefit image media"),
    ("longdescref", "Long description reference", "points to a longer description for accessibility", "image/media contexts where supported", "Accessibility semantics + output implementation", "longdescref accessibility image"),
    ("keyscopeprefix", "Branch keyscope prefix", "adds a prefix to generated branch key scopes", "ditavalref/resource renaming contexts", "DITA branch filtering behavior", "keyscopeprefix branch-filtering"),
    ("keyscopesuffix", "Branch keyscope suffix", "adds a suffix to generated branch key scopes", "ditavalref/resource renaming contexts", "DITA branch filtering behavior", "keyscopesuffix branch-filtering"),
    ("resourceprefix", "Branch resource prefix", "adds a prefix to generated resources in branch filtering", "ditavalref/resource renaming contexts", "DITA branch filtering behavior", "resourceprefix branch-filtering"),
    ("resourcesuffix", "Branch resource suffix", "adds a suffix to generated resources in branch filtering", "ditavalref/resource renaming contexts", "DITA branch filtering behavior", "resourcesuffix branch-filtering"),
    ("filter", "Filter reference", "references filtering rules where supported", "ditavalref contexts", "DITA branch filtering behavior", "filter ditavalref"),
    ("format", "Resource format", "states or hints the target resource format", "references and key definitions", "DITA link/resource semantics", "format links"),
    ("href", "Resource URI", "points directly to the target resource", "references and key definitions", "DITA URI resolution", "href uri"),
    ("processing-role", "Map processing role", "controls normal versus resource-only processing semantics", "map references", "DITA map processing", "processing-role resource-only"),
    ("navtitle", "Map navigation label", "supplies navigation title text", "topicmeta/map references", "DITA title resolution", "navtitle titles"),
    ("searchtitle", "Search title", "supplies search-specific title text where supported", "topicmeta/title metadata", "Output/search implementation", "searchtitle search title"),
    ("linktext", "Link text", "supplies link text metadata where supported", "topicmeta/link metadata", "DITA linking + output implementation", "linktext links"),
    ("copy-to", "Copied resource target", "requests an alternate target copy/output identity", "topicref", "DITA resource identity + processor behavior", "copy-to"),
    ("mapref", "Map-reference role", "indicates map-to-map reference semantics when represented as role/domain behavior", "map reference contexts", "DITA map integration", "mapref map"),
    ("navref", "Navigation reference", "references external navigation where supported", "map contexts", "Navigation/output implementation", "navref navigation"),
    ("anchorref", "Anchor reference", "targets an anchor point for dynamic map assembly where supported", "map contexts", "DITA map integration", "anchorref map"),
    ("ditavalref", "Branch filtering element, not a normal attribute", "is commonly asked about as if it were an attribute, but DITA uses `<ditavalref>` as a map element that references branch-filtering rules", "map branches, usually as a child of map/topicref contexts where branch filtering is supported", "DITA branch filtering + DITA-OT/AEM/Oxygen implementation", "ditavalref branch-filtering correction"),
    ("conaction", "Conref push action", "declares push behavior such as pushbefore, pushafter, or pushreplace", "conref push contexts", "DITA conref push behavior", "conaction conref-push"),
    ("conref", "Content reference", "pulls content from a directly addressed reusable target", "reusable content contexts", "DITA content reuse", "conref"),
    ("conkeyref", "Keyed content reference", "pulls content from a key-addressed reusable target", "reusable content contexts", "DITA content reuse + key resolution", "conkeyref"),
    ("keyref", "Key reference", "resolves text/link targets through keys in the active map context", "key-aware references", "DITA key resolution", "keyref"),
    ("keys", "Key names", "declares key names made available by a map branch", "map references/key definitions", "DITA key definition", "keys"),
    ("id", "DITA/XML ID", "provides an addressable identity for topics and elements", "topics/elements", "DITA addressing", "id"),
]


_PROMPT_TEMPLATES: list[tuple[str, str]] = [
    ("concept", "What does @{attr} do in DITA?"),
    ("example", "Show a senior example for the DITA @{attr} attribute."),
    ("scope", "Where can @{attr} be used in DITA and what is its scope?"),
    ("mistakes", "What are common mistakes with @{attr} in DITA?"),
    ("troubleshoot", "How do I troubleshoot a problem involving @{attr} in DITA?"),
    ("processing", "How does @{attr} affect DITA processing or output?"),
    ("comparison", "How should a DITA expert explain @{attr} without confusing it with related attributes?"),
    ("validation", "What should validation check for @{attr} in an enterprise DITA repository?"),
    ("aem_oxygen", "How should AEM Guides or Oxygen users reason about @{attr}?"),
    ("rag", "What must a DITA chatbot include when answering questions about @{attr}?"),
    ("debug_output_parity", "Why might @{attr} behave differently in HTML, PDF, Oxygen preview, and AEM Guides output?"),
    ("migration_governance", "What governance rules should teams define for @{attr} during DITA migration?"),
    ("minimal_repro", "What minimal repro should I create for a suspected @{attr} issue?"),
]


_COMPLEX_ATTRIBUTE_PROMPTS: list[tuple[str, list[str], str]] = [
    (
        "Can copy-to fix duplicate output names created by branch filtering resourcesuffix?",
        ["copy-to", "resourcesuffix", "branch-filtering"],
        "Do not treat `@copy-to` as the first fix for branch-filtering output collisions. First check whether `@resourceprefix` or `@resourcesuffix` on the branch-filtering context should make generated resource names unique; use `@copy-to` only when you intentionally need a separate output identity for a referenced topic. Validate generated URIs, xrefs, related links, search entries, and context-help mappings.",
    ),
    (
        "Why does conkeyref resolve differently after keyscopeprefix is applied by ditavalref?",
        ["conkeyref", "keyscopeprefix", "ditavalref", "keyscope"],
        "`<ditavalref>` branch filtering can create branch-specific effective key scopes. `@keyscopeprefix` changes the generated key-scope names for the filtered branch, so a `@conkeyref` can resolve through a different key definition than it did in the unfiltered branch. Inspect the effective map, branch-specific key scope, key definitions, and preprocessed conref resolution.",
    ),
    (
        "When should searchtitle and linktext be used instead of navtitle?",
        ["searchtitle", "linktext", "navtitle"],
        "Use `navtitle` for navigation labels, `searchtitle` for search-oriented title text where the output supports it, and `linktext` for generated link text metadata. Do not use `navtitle` as a universal replacement for every title-like behavior. Validate TOC/navigation, search result title, related links, and xref/link rendering separately.",
    ),
    (
        "How do rowsep colsep frame and colwidth affect PDF table output?",
        ["rowsep", "colsep", "frame", "colwidth"],
        "`@rowsep`, `@colsep`, and `@frame` are CALS table ruling/frame hints, while `@colwidth` expresses preferred column width. PDF output depends on whether the processor and formatter honor those hints, table width constraints, filtered rows/cells, and CSS/template overrides. Inspect the CALS table model before debugging PDF styling.",
    ),
    (
        "What should I inspect when valign top is ignored in a cell with morerows?",
        ["valign", "morerows"],
        "`@valign` is a vertical alignment hint inside table cells, while `@morerows` changes the cell's row span. If top alignment is ignored, first verify that the CALS table grid is valid after row spanning and filtering, then inspect generated FO/HTML/PDF intermediate output and formatter support for vertical alignment in spanned cells.",
    ),
    (
        "How should xml:lang translate and dir be handled in multilingual PDF?",
        ["xml:lang", "translate", "dir"],
        "`xml:lang` identifies language, `@translate` controls translation handoff, and `@dir` controls text direction. For multilingual PDF, verify language inheritance, generated labels, fonts, hyphenation, RTL/LTR direction, protected product/code text, and PDF accessibility language tagging. Do not assume editor preview and final PDF use the same locale resources.",
    ),
    (
        "How should headers rowheader and colspec be validated for screen reader support?",
        ["headers", "rowheader", "colspec"],
        "For accessible tables, verify that `@headers` points to real header cell IDs, `@rowheader` correctly identifies row-header behavior where supported, and `colspec` names/widths do not hide structural table problems. Then validate generated HTML/PDF tagging, repeated headers, filtering effects, and whether header associations survive preprocessing.",
    ),
]


def _xml_example(attribute: str) -> str:
    examples = {
        "morerows": '<table><tgroup cols="2"><tbody><row><entry morerows="1">Spans two rows</entry><entry>Row 1</entry></row><row><entry>Row 2</entry></row></tbody></tgroup></table>',
        "namest": '<entry namest="col1" nameend="col3">Spans columns 1 through 3</entry>',
        "nameend": '<entry namest="col1" nameend="col3">Spans columns 1 through 3</entry>',
        "keyref": '<map><keydef keys="product-name"><topicmeta><keywords><keyword>Acme Pro</keyword></keywords></topicmeta></keydef><topicref href="install.dita"/></map>',
        "keys": '<map><keydef keys="product-name" href="reuse/product-name.dita" processing-role="resource-only"/></map>',
        "keyscope": '<map><topicref keyscope="admin"><keydef keys="install" href="admin-install.dita"/></topicref></map>',
        "conref": '<p conref="reuse.dita#reuse/install-note">Fallback text</p>',
        "conkeyref": '<p conkeyref="reuse-key/install-note">Fallback text</p>',
        "ditavalref": '<topicref href="install.dita"><ditavalref href="filters/admin.ditaval"/></topicref>',
        "processing-role": '<keydef keys="product-name" href="reuse/product-name.dita" processing-role="resource-only"/>',
        "toc": '<topicref href="legal-notices.dita" toc="no"/>',
        "linking": '<topicref href="reference.dita" linking="targetonly"/>',
        "copy-to": '<topicref href="shared/install.dita" copy-to="product-a-install.dita"/>',
        "chunk": '<topicref href="guide.dita" chunk="to-content"/>',
        "valign": '<entry valign="top">Align this cell content to the top of the row.</entry>',
        "align": '<entry align="center">Centered table cell content</entry>',
        "scale": '<image href="diagram.svg" scale="75"><alt>System architecture diagram</alt></image>',
        "scalefit": '<image href="wide-table.png" scalefit="yes" width="100%"><alt>Wide table screenshot</alt></image>',
        "colwidth": '<colspec colname="col1" colwidth="2*"/>',
        "rowheader": '<tgroup cols="2" rowheader="firstcol"><tbody><row><entry>Property</entry><entry>Description</entry></row></tbody></tgroup>',
        "headers": '<entry headers="header-product header-version">AEM Guides 2026</entry>',
        "href": '<xref href="concepts/overview.dita#overview">Overview</xref>',
        "scope": '<xref href="https://example.com/docs" scope="external" format="html">External docs</xref>',
        "format": '<xref href="release-notes.pdf" scope="external" format="pdf">Release notes</xref>',
        "outputclass": '<note outputclass="beta-warning">This feature is in beta.</note>',
        "audience": '<p audience="admin">Only administrators see this when the DITAVAL includes admin.</p>',
        "platform": '<p platform="linux">Run this command on Linux.</p>',
        "product": '<p product="product-a">Product A behavior.</p>',
        "props": '<p props="cloud">Cloud-only behavior.</p>',
        "xml:lang": '<topic id="intro" xml:lang="fr-FR"><title>Introduction</title><body/></topic>',
        "translate": '<ph translate="no">Acme CLI</ph>',
        "placement": '<image href="architecture.svg" placement="break"><alt>Architecture diagram</alt></image>',
        "alt": '<image href="warning.png"><alt>Warning icon</alt></image>',
    }
    return examples.get(attribute, f'<topicref {attribute}="value" href="example.dita"/>')


def _specific_attribute_note(attribute: str) -> str:
    notes = {
        "scale": (
            "- `@scale` is normally a percentage-style sizing hint for media; it should not be treated as a guaranteed pixel size.\n"
            "- For PDF issues, compare intrinsic image size, `@width`, `@height`, `@scalefit`, CSS/template rules, and formatter support.\n"
            "- In AEM Guides Native PDF or Oxygen PDF Chemistry, final sizing can be affected by CSS and page-area constraints."
        ),
        "scalefit": (
            "- `@scalefit` requests fit-to-available-area behavior; processors may interpret it differently for raster images, SVG, and PDF output.\n"
            "- Use it with explicit `@width`/`@height` only after testing the target HTML/PDF transform."
        ),
        "valign": (
            "- `@valign` is a CALS table vertical-alignment hint, commonly used on entries or table structures where the model allows it.\n"
            "- It affects vertical placement inside table cells; it does not repair invalid row spans, missing entries, or broken table grids.\n"
            "- PDF renderers can differ, so verify the generated table model and formatter output."
        ),
        "align": (
            "- `@align` is context-sensitive: table cell alignment is not the same as image placement or CSS text alignment.\n"
            "- Prefer semantic table markup first, then use output styling only when presentation truly needs control."
        ),
        "copy-to": (
            "- `@copy-to` changes output/resource identity, not the source topic's physical filename.\n"
            "- Test links, related links, context help, search indexing, duplicate topic inclusion, and generated output URIs.\n"
            "- Avoid using `@copy-to` as a substitute for clean reuse governance when separate source topics or key scopes are more maintainable."
        ),
        "chunk": (
            "- `@chunk` can change generated file boundaries and link rewriting; always compare source topic identity with output identity.\n"
            "- Chunking behavior is processor-sensitive, so HTML, WebHelp, PDF, and AEM output may not expose identical artifacts."
        ),
        "cascade": (
            "- `@cascade` controls how eligible cascading attributes merge or do not merge; it does not mean every XML attribute cascades.\n"
            "- Evaluate effective values after map hierarchy, branch filtering, and DITAVAL processing."
        ),
        "collection-type": (
            "- `@collection-type` affects generated relationship semantics among child topic references; it is not just a visual grouping control.\n"
            "- Verify related links separately in HTML/WebHelp and PDF because processors can render relationship links differently."
        ),
        "headers": (
            "- `@headers` supports table accessibility by associating cells with header IDs where the table model/output supports it.\n"
            "- Validate that referenced header IDs exist and survive filtering, chunking, and PDF tagging."
        ),
        "rowheader": (
            "- `@rowheader` is important for row-header semantics and accessible table output; it is not merely a styling switch.\n"
            "- Confirm the table structure and generated PDF/HTML accessibility tree."
        ),
        "format": (
            "- `@format` identifies the format of the referenced resource; the processing default is `dita` when no value is specified.\n"
            "- In map branches and in `<related-links>`, `@format` can cascade from the closest ancestor that specifies it.\n"
            "- Common values include `dita`, `ditamap`, `html`, and `pdf`; for other resource types, use the file extension without the dot, such as `txt` for `readme.txt`.\n"
            "- `format=\"ditamap\"` means the linked resource is a DITA map that contributes its referenced hierarchy at the current point in the referencing map; relationship tables from referenced maps are treated as children of the referencing map.\n"
            "- Do not confuse `@format` with `@scope`: `@format` says what kind of resource is referenced, while `@scope` says whether the relationship is local, peer, or external."
        ),
    }
    return notes.get(attribute, "")


def _family_note(attribute: str) -> str:
    if attribute in {"morerows", "namest", "nameend", "colname", "colnum", "colwidth", "rowsep", "colsep", "valign", "char", "charoff", "frame", "pgwide", "orient", "rowheader", "headers"}:
        return (
            "- Table note: CALS attributes apply to CALS table structures such as `<table>`, `<tgroup>`, `<row>`, and `<entry>` as allowed by the model; "
            "do not apply CALS spanning attributes like `@morerows`, `@namest`, or `@nameend` to `<simpletable>`.\n"
            "- PDF note: table rendering differences often come from filtered cells, invalid grids, column widths, image sizing, or formatter limits."
        )
    if attribute in {"conref", "conkeyref", "conrefend", "conaction"}:
        return (
            "- Reuse note: verify the target URI/key, topic ID, element ID, structural compatibility, filtering, and active publication dependency graph.\n"
            "- Processing note: compare editor preview with DITA-OT preprocessing output before debugging final HTML/PDF rendering."
        )
    if attribute in {"keyref", "keys", "keyscope", "keyscopeprefix", "keyscopesuffix"}:
        return (
            "- Key note: resolution depends on the active root map, key scope, filtered key definitions, and map inclusion order.\n"
            "- Editor note: Oxygen/AEM preview can differ from publishing if the selected root map or key-space context differs."
        )
    if attribute in {"processing-role", "toc", "linking", "collection-type", "copy-to", "chunk", "locktitle", "lockmeta", "navtitle", "searchtitle", "linktext"}:
        return (
            "- Map note: distinguish navigation inclusion, output generation, link participation, resource identity, and generated title text.\n"
            "- Output note: HTML, PDF, WebHelp, and AEM Guides may expose these map semantics differently."
        )
    if attribute in {"audience", "platform", "product", "props", "otherprops", "rev", "deliveryTarget", "print", "ditavalref", "filter", "resourceprefix", "resourcesuffix"}:
        return (
            "- Filtering note: separate authored profiling values from effective values after map cascade, DITAVAL, and branch filtering.\n"
            "- Branch note: branch filtering can create different effective keys, links, copied resources, and output names per branch."
        )
    if attribute in {"outputclass", "placement", "height", "width", "scale", "scalefit", "align"}:
        return (
            "- Styling note: this is usually an output/customization hook, not a guarantee that every processor renders the same result.\n"
            "- AEM/Oxygen note: verify the output preset, CSS/template, Native PDF/WebHelp pipeline, and generated intermediate HTML."
        )
    if attribute in {"xml:lang", "translate", "dir", "sort-as"}:
        return (
            "- Localization note: verify language inheritance, generated labels, sorting/collation, fonts, bidirectional text, and translation handoff behavior.\n"
            "- Output note: PDF and Web output can differ if locale, fonts, or generated text resources are not aligned."
        )
    if attribute in {"href", "scope", "format", "type", "id", "xml:id", "longdescref", "alt"}:
        return (
            "- Addressing/accessibility note: validate URI escaping, fragment IDs, external/local scope, target format, and accessible text requirements.\n"
            "- Repository note: moving or renaming files requires dependency checks for both direct URI references and key-based references."
        )
    return "- Expert note: verify source validity, effective map context, processor support, and output-specific behavior before giving a final answer."


def _answer(attribute: str, label: str, meaning: str, applies_to: str, behavior_scope: str, tags: str) -> str:
    return (
        "## Short answer\n"
        f"`@{attribute}` {meaning}. Use it only in the DITA contexts where the vocabulary or processor defines it, and verify the effective map/output context before treating the result as universal.\n\n"
        "## Scope\n"
        f"- Attribute: `@{attribute}`\n"
        f"- Primary concept: {label}\n"
        f"- Common contexts: {applies_to}\n"
        f"- Behavior scope: {behavior_scope}\n\n"
        "## XML example\n"
        "```xml\n"
        f"{_xml_example(attribute)}\n"
        "```\n\n"
        "## Senior explanation\n"
        f"In source XML, `@{attribute}` records authoring intent; the effective behavior can change after map resolution, filtering, key resolution, conref resolution, chunking, or output-specific transforms. "
        "A senior answer should say whether the behavior is defined by the DITA specification, inherited from XML/CALS, or implemented by DITA-OT, Oxygen, AEM Guides, or another processor. "
        "For troubleshooting, compare authored source with effective processed content and then with final output artifacts.\n\n"
        "## Attribute-family notes\n"
        f"{_family_note(attribute)}\n\n"
        + (f"## Attribute-specific senior notes\n{_specific_attribute_note(attribute)}\n\n" if _specific_attribute_note(attribute) else "")
        +
        "## Common mistakes\n"
        f"- Treating `@{attribute}` as valid on every DITA element instead of checking the allowed context.\n"
        "- Confusing source XML with effective processed content after map context, filtering, or key resolution.\n"
        "- Presenting processor-specific output behavior as a universal DITA specification rule.\n\n"
        "## Validation checklist\n"
        f"- Confirm `@{attribute}` is allowed on the element and vocabulary in use.\n"
        "- Validate referenced keys, URIs, IDs, table grid, filters, or output resources depending on the attribute family.\n"
        "- Test the intended root map, DITAVAL, output preset, and processor version.\n\n"
        "## Retrieval tags\n"
        f"- {tags}"
    )


def _complex_answer(prompt: str, attrs: list[str], summary: str) -> str:
    attr_text = ", ".join(f"`@{attr}`" if not attr.startswith("branch") and attr != "ditavalref" else f"`{attr}`" for attr in attrs)
    examples = "\n".join(_xml_example(attr) for attr in attrs if attr not in {"branch-filtering", "colspec"})
    if "colspec" in attrs:
        examples += "\n<colspec colname=\"col1\" colwidth=\"2*\"/>"
    if "branch-filtering" in attrs:
        examples += "\n<topicref href=\"install.dita\"><ditavalref href=\"filters/admin.ditaval\" resourcesuffix=\"-admin\"/></topicref>"
    return (
        "## Short answer\n"
        f"{summary}\n\n"
        "## Scope\n"
        f"- Composite attributes/concepts: {attr_text}\n"
        "- Behavior scope: DITA source semantics + effective map context + processor/output implementation.\n\n"
        "## XML example\n"
        "```xml\n"
        f"{examples.strip()}\n"
        "```\n\n"
        "## Senior explanation\n"
        "This is a multi-attribute question, so answer it by explaining how the attributes interact in the effective map/output context rather than defining only one attribute. "
        "Compare authored source XML, effective preprocessed content, and final output artifacts. Label DITA specification behavior separately from DITA-OT, Oxygen, AEM Guides, Native PDF, WebHelp, or formatter-specific behavior.\n\n"
        "## Attribute-family notes\n"
        "- Composite note: these attributes must be evaluated together because the observed behavior often comes from map context, filtering, key scope, output identity, table structure, or output rendering interaction.\n"
        "- Processor note: verify DITA-OT/Oxygen/AEM Guides behavior with the same root map, DITAVAL, output preset, and processor version.\n\n"
        "## Deterministic checks\n"
        "- Build a minimal map/topic sample that contains only the interacting attributes.\n"
        "- Inspect filtering, key scope, table grid, media sizing, link rewriting, or title metadata depending on the attribute family.\n"
        "- Compare HTML/WebHelp and PDF/Native PDF output only after confirming the same effective processed content.\n\n"
        "## Validation checklist\n"
        "- Validate each attribute in its allowed DITA context.\n"
        "- Validate the interaction in the effective root map, not only in a standalone topic.\n"
        "- Validate output-specific behavior in the intended transform and preset.\n\n"
        "## Common mistakes\n"
        "- Answering only one attribute when the problem is caused by interaction between attributes.\n"
        "- Treating processor-specific rendering as a universal DITA rule.\n"
        "- Debugging final PDF/WebHelp styling before validating the effective source structure."
    )


def get_dita_attribute_seed_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for attribute, label, meaning, applies_to, behavior_scope, tags in _ATTRIBUTE_ROWS:
        for prompt_kind, template in _PROMPT_TEMPLATES:
            prompt = template.format(attr=attribute)
            normalized = prompt.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            items.append(
                {
                    "prompt": prompt,
                    "final_answer": _answer(attribute, label, meaning, applies_to, behavior_scope, tags),
                    "tags": ["dita-attribute", prompt_kind, attribute, *tags.split()],
                    "topic": "dita_attributes",
                    "source_type": "dita_attribute_questions",
                    "answer_style": "senior_technical_docs",
                    "status": "approved",
                }
            )
    for prompt, attrs, summary in _COMPLEX_ATTRIBUTE_PROMPTS:
        normalized = prompt.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        items.append(
            {
                "prompt": prompt,
                "final_answer": _complex_answer(prompt, attrs, summary),
                "tags": ["dita-attribute", "complex", *attrs],
                "topic": "dita_attributes",
                "source_type": "dita_attribute_questions",
                "answer_style": "senior_technical_docs",
                "status": "approved",
            }
        )
    return items
