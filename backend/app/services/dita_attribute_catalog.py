"""Attribute catalog: look up DITA attribute specs from seed for test data generation.

Given an attribute name (e.g. "format"), returns valid values, supported elements,
combination attributes, and builds test scenario descriptions.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple

SEED_PATH = Path(__file__).resolve().parent.parent / "storage" / "dita_spec_seed.json"
_ATTRIBUTE_EXAMPLE_TAG_PATTERN = r"<([A-Za-z][A-Za-z0-9_.:-]*)\b[^>]*\b{attr_name}\s*="
_FENCED_XML_BLOCK_RE = re.compile(r"```(?:xml)?\s*\r?\n(.*?)```", re.IGNORECASE | re.DOTALL)
ID_ATTRIBUTES_SOURCE_URL = "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/idAttributes.html"
METADATA_ATTRIBUTES_SOURCE_URL = "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/metadataAttributes.html"
LOCALIZATION_ATTRIBUTES_SOURCE_URL = "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/localizationAttributes.html"
DEBUG_ATTRIBUTES_SOURCE_URL = "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/debugAttributes.html"
ARCHITECTURAL_ATTRIBUTES_SOURCE_URL = "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/architecturalAttributes.html"
COMMON_MAP_ATTRIBUTES_SOURCE_URL = "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/commonMapAttributes.html"
CALS_TABLE_ATTRIBUTES_SOURCE_URL = "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/calsTableAttributes.html"
DISPLAY_ATTRIBUTES_SOURCE_URL = "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/displayAttributes.html#display-atts"
DATE_ATTRIBUTES_SOURCE_URL = "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/dateAttributes.html"
LINK_RELATIONSHIP_ATTRIBUTES_SOURCE_URL = "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/linkRelationshipAttributes.html"
COMMON_ATTRIBUTES_SOURCE_URL = "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/commonAttributes.html"
SIMPLETABLE_ATTRIBUTES_SOURCE_URL = "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/simpletableAttributes.html"


class AttributeSpec(NamedTuple):
    """Resolved attribute specification from the seed."""

    attribute_name: str
    all_valid_values: list[str]
    supported_elements: list[str]
    combination_attributes: list[str]
    default_scenarios: list[str]
    usage_contexts: list[str]
    common_mistakes: list[str]
    correct_examples: list[str]
    text_content: str  # raw spec text for RAG injection
    source_url: str
    semantic_class: str
    syntax: str


@lru_cache(maxsize=1)
def _supplemental_attribute_specs() -> dict[str, AttributeSpec]:
    """Structured overrides for important DITA attributes missing from seed data."""

    def _spec(
        name: str,
        *,
        values: list[str] | None = None,
        elements: list[str] | None = None,
        combinations: list[str] | None = None,
        contexts: list[str] | None = None,
        mistakes: list[str] | None = None,
        example: str = "",
        text: str = "",
        source_url: str = "https://dita-lang.org/1.3/dita/langref/attributes/attributes",
        semantic_class: str = "open_token",
        syntax: str = "",
    ) -> AttributeSpec:
        return AttributeSpec(
            attribute_name=name,
            all_valid_values=list(values or []),
            supported_elements=list(elements or []),
            combination_attributes=list(combinations or []),
            default_scenarios=list(contexts or []),
            usage_contexts=list(contexts or []),
            common_mistakes=list(mistakes or []),
            correct_examples=[example] if example else [],
            text_content=text or f"The @{name} attribute is a DITA attribute used in construct-specific contexts.",
            source_url=source_url,
            semantic_class=semantic_class,
            syntax=syntax,
        )

    specs = {
        "scalefit": AttributeSpec(
            attribute_name="scalefit",
            all_valid_values=["yes", "no", "-dita-use-conref-target"],
            supported_elements=["image", "hazardsymbol"],
            combination_attributes=["height", "width", "scale"],
            default_scenarios=[
                "If @height, @width, or @scale is specified, those attributes determine image size and @scalefit is ignored.",
                'If none of @height, @width, or @scale is specified and @scalefit="yes", the image scales uniformly to fit the available space.',
            ],
            usage_contexts=[
                "Use @scalefit on image-like elements when the processor should fit the image to the available column or table-cell space.",
                "Use -dita-use-conref-target when image sizing should be inherited during conref resolution.",
            ],
            common_mistakes=[
                "Expecting @scalefit to apply when @height, @width, or @scale is already set.",
                "Using @scalefit on non-image elements.",
            ],
            correct_examples=[
                '<image href="images/bike.png" scalefit="yes"><alt>Bike illustration</alt></image>',
            ],
            text_content=(
                "The @scalefit attribute specifies whether an image is scaled up or down to fit within available "
                "space.\n\n"
                "Syntax: yes, no, or -dita-use-conref-target.\n\n"
                "If @height, @width, or @scale is specified, those attributes determine the image size and "
                "@scalefit is ignored. If none of those attributes is specified and @scalefit=\"yes\", the image "
                "is scaled uniformly to fit the available width or height, whichever is more constraining."
            ),
            source_url="https://dita-lang.org/dita/langref/base/image",
            semantic_class="boolean_like",
            syntax="yes, no, or -dita-use-conref-target",
        )
    }
    specs.update(
        {
            "id": _spec(
                "id",
                elements=["topic", "concept", "task", "reference", "section", "fig", "table", "topicref"],
                combinations=["conref", "conrefend", "xref", "href"],
                contexts=[
                    "Use @id to give a DITA element a unique XML identifier for addressing, reuse, and cross references.",
                    "Topic roots need stable IDs when other topics, maps, conrefs, or xrefs target them.",
                ],
                mistakes=[
                    "Duplicating the same @id in one XML document.",
                    "Expecting an @id to be globally unique outside its document without a qualified URI or key-based reference.",
                ],
                example='<topic id="installing"><title>Installing</title><body><p id="prereqs">Check prerequisites.</p></body></topic>',
                source_url=ID_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="XML name token unique within the XML document",
            ),
            "xml:lang": _spec(
                "xml:lang",
                elements=["topic", "concept", "task", "reference", "map", "topicref", "section", "p"],
                combinations=["dir", "translate"],
                contexts=["Use @xml:lang to identify the language of the element and inherited content."],
                mistakes=["Setting @xml:lang inconsistently across translated topic roots and maps."],
                example='<topic id="intro" xml:lang="en-US"><title>Introduction</title></topic>',
                source_url=LOCALIZATION_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="language tag such as en, en-US, or fr-FR",
            ),
            "dir": _spec(
                "dir",
                values=["ltr", "rtl", "lro", "rlo", "-dita-use-conref-target"],
                elements=["topic", "concept", "task", "reference", "map", "topicref", "section", "p"],
                combinations=["xml:lang", "translate"],
                contexts=["Use @dir to control text direction for bidirectional or right-to-left language content."],
                mistakes=["Using @dir as a styling shortcut instead of language-direction metadata."],
                example='<p dir="rtl" xml:lang="ar">...</p>',
                source_url=LOCALIZATION_ATTRIBUTES_SOURCE_URL,
                semantic_class="enum",
                syntax="ltr, rtl, lro, rlo, or -dita-use-conref-target",
            ),
            "translate": _spec(
                "translate",
                values=["yes", "no", "-dita-use-conref-target"],
                elements=["topic", "concept", "task", "reference", "map", "topicref", "section", "p", "codeph", "keyword"],
                combinations=["xml:lang", "dir"],
                contexts=["Use @translate to indicate whether the element content should be translated."],
                mistakes=["Marking user-visible content translate=\"no\" just because it contains product names or code-like terms."],
                example='<keyword translate="no">kubectl</keyword>',
                source_url=LOCALIZATION_ATTRIBUTES_SOURCE_URL,
                semantic_class="boolean_like",
                syntax="yes, no, or -dita-use-conref-target",
            ),
            "xtrf": _spec(
                "xtrf",
                elements=["topic", "concept", "task", "reference", "map", "topicref", "section", "p"],
                combinations=["xtrc"],
                contexts=["Use @xtrf as processor-supplied debug or tracing metadata that identifies the source file."],
                mistakes=["Authoring @xtrf manually as user-facing content or relying on it for publishing semantics."],
                source_url=DEBUG_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="processor-defined source-file trace string",
            ),
            "xtrc": _spec(
                "xtrc",
                elements=["topic", "concept", "task", "reference", "map", "topicref", "section", "p"],
                combinations=["xtrf"],
                contexts=["Use @xtrc as processor-supplied debug or tracing metadata that identifies source context such as line or location."],
                mistakes=["Treating @xtrc as stable authoring metadata; processors can generate or change it."],
                source_url=DEBUG_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="processor-defined source-context trace string",
            ),
            "class": _spec(
                "class",
                elements=["topic", "concept", "task", "reference", "map", "topicref", "section", "p"],
                combinations=["domains", "specializations"],
                contexts=["Use @class as DITA architecture metadata that declares the specialization ancestry of an element."],
                mistakes=["Editing @class by hand in authored content instead of letting the DTD/schema or processor supply the correct value."],
                source_url=ARCHITECTURAL_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="DITA specialization ancestry string",
            ),
            "domains": _spec(
                "domains",
                elements=["topic", "concept", "task", "reference", "map", "bookmap"],
                combinations=["class"],
                contexts=["Use @domains on root elements to declare the domains and specializations available to the document type."],
                mistakes=["Using @domains as author-visible classification metadata instead of DITA architecture metadata."],
                source_url=ARCHITECTURAL_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="DITA domains contribution string",
            ),
            "specializations": _spec(
                "specializations",
                elements=["topic", "concept", "task", "reference", "map", "bookmap"],
                combinations=["domains", "class"],
                contexts=["Use @specializations as DITA architecture metadata for specialization declarations where supported by the grammar."],
                mistakes=["Confusing architecture-level specialization declarations with subject-scheme taxonomies."],
                source_url=ARCHITECTURAL_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="DITA specialization declaration string",
            ),
            "ditaarch:ditaarchversion": _spec(
                "ditaarch:DITAArchVersion",
                elements=["topic", "concept", "task", "reference", "map", "bookmap"],
                combinations=["class", "domains"],
                contexts=["Use @ditaarch:DITAArchVersion as architecture metadata that identifies the DITA architecture version."],
                mistakes=["Using @ditaarch:DITAArchVersion as product version metadata."],
                source_url=ARCHITECTURAL_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="DITA architecture version token",
            ),
            "href": _spec(
                "href",
                elements=["topicref", "xref", "link", "image", "object", "mapref", "ditavalref"],
                combinations=["format", "scope", "type", "keyref"],
                contexts=["Use @href for URI-based references to topics, maps, non-DITA resources, or DITAVAL profiles."],
                mistakes=["Using @href for key-based indirection when @keyref or @conkeyref is required."],
                example='<xref href="installing.dita#installing/prereqs">Installation prerequisites</xref>',
                semantic_class="reference_like",
                syntax="URI reference",
            ),
            "role": _spec(
                "role",
                elements=["xref", "link", "topicref"],
                combinations=["otherrole", "href", "keyref", "scope", "format", "type"],
                contexts=["Use @role on link relationship elements to classify the relationship between the current content and the target."],
                mistakes=["Using @role as visible link text; it is relationship metadata for processors and output transforms."],
                example='<link href="troubleshooting.dita" role="friend">Related troubleshooting</link>',
                source_url=LINK_RELATIONSHIP_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="relationship role token; use @otherrole for custom role detail where required",
            ),
            "otherrole": _spec(
                "otherrole",
                elements=["xref", "link", "topicref"],
                combinations=["role", "href", "keyref"],
                contexts=["Use @otherrole to carry a processor- or project-defined relationship role when the standard @role value is not specific enough."],
                mistakes=["Setting @otherrole without a clear governing convention for how processors should interpret it."],
                example='<link href="api-reference.dita" role="other" otherrole="api-contract">API contract reference</link>',
                source_url=LINK_RELATIONSHIP_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="custom relationship role token",
            ),
            "copy-to": _spec(
                "copy-to",
                elements=["topicref"],
                combinations=["href", "keys"],
                contexts=["Use @copy-to on map references when output should use an alternate resource name."],
                mistakes=["Using @copy-to without a map reference context."],
                example='<topicref href="installing.dita" copy-to="installing-admin.dita"/>',
                semantic_class="reference_like",
                syntax="URI reference",
            ),
            "navtitle": _spec(
                "navtitle",
                elements=["topicref", "topichead", "topicgroup", "mapref"],
                combinations=["locktitle", "href"],
                contexts=["Use @navtitle to provide or override navigation text in a map context."],
                mistakes=["Expecting @navtitle to replace the actual topic title unless @locktitle is used appropriately."],
                example='<topicref href="installing.dita" navtitle="Install the product"/>',
                source_url=COMMON_MAP_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="navigation title text",
            ),
            "processing-role": _spec(
                "processing-role",
                values=["normal", "resource-only", "-dita-use-conref-target"],
                elements=["topicref", "keydef", "mapref", "topichead", "topicgroup"],
                combinations=["href", "keys", "toc", "linking"],
                contexts=["Use @processing-role on map references to decide whether the target is normal publishable content or resource-only content for keys/reuse."],
                mistakes=["Forgetting processing-role=\"resource-only\" on conref warehouses, subject-scheme maps, or key resources that should not appear as normal output topics."],
                example='<topicref href="shared/reuse.dita" processing-role="resource-only"/>',
                source_url=COMMON_MAP_ATTRIBUTES_SOURCE_URL,
                semantic_class="map_scoped",
                syntax="normal, resource-only, or -dita-use-conref-target",
            ),
            "collection-type": _spec(
                "collection-type",
                values=["unordered", "sequence", "choice", "family", "-dita-use-conref-target"],
                elements=["topicref", "topichead", "topicgroup"],
                combinations=["linking", "toc"],
                contexts=["Use @collection-type on map branches to describe relationships among child topicrefs and guide generated navigation links."],
                mistakes=["Setting collection-type=\"sequence\" on a leaf topicref with no children and expecting previous/next links."],
                example='<topicref href="tutorial.dita" collection-type="sequence"><topicref href="step-1.dita"/></topicref>',
                source_url=COMMON_MAP_ATTRIBUTES_SOURCE_URL,
                semantic_class="map_scoped",
                syntax="unordered, sequence, choice, family, or -dita-use-conref-target",
            ),
            "linking": _spec(
                "linking",
                values=["normal", "sourceonly", "targetonly", "none", "-dita-use-conref-target"],
                elements=["topicref", "topichead", "topicgroup", "relcolspec"],
                combinations=["collection-type", "toc"],
                contexts=["Use @linking on map references to control generated link behavior for the referenced topic or relationship-table column."],
                mistakes=["Using linking=\"none\" when the topic still needs to be a generated cross-reference target."],
                example='<topicref href="glossary.dita" linking="targetonly"/>',
                source_url=COMMON_MAP_ATTRIBUTES_SOURCE_URL,
                semantic_class="map_scoped",
                syntax="normal, sourceonly, targetonly, none, or -dita-use-conref-target",
            ),
            "print": _spec(
                "print",
                values=["yes", "no", "printonly", "-dita-use-conref-target"],
                elements=["topicref", "topichead", "topicgroup"],
                combinations=["toc", "linking"],
                contexts=["Use @print on map references to control whether referenced content participates in print-oriented output."],
                mistakes=["Assuming print=\"no\" only hides visible print pages while leaving the topic in print navigation."],
                example='<topicref href="online-only.dita" print="no" toc="no"/>',
                source_url=COMMON_MAP_ATTRIBUTES_SOURCE_URL,
                semantic_class="map_scoped",
                syntax="yes, no, printonly, or -dita-use-conref-target",
            ),
            "search": _spec(
                "search",
                values=["yes", "no", "-dita-use-conref-target"],
                elements=["topicref", "topichead", "topicgroup"],
                combinations=["toc", "print"],
                contexts=["Use @search on map references to control whether referenced content should be included in search indexing where processors support it."],
                mistakes=["Confusing @search with @toc; search indexing and navigation visibility are separate processor concerns."],
                example='<topicref href="legal.dita" search="no"/>',
                source_url=COMMON_MAP_ATTRIBUTES_SOURCE_URL,
                semantic_class="map_scoped",
                syntax="yes, no, or -dita-use-conref-target",
            ),
            "locktitle": _spec(
                "locktitle",
                values=["yes", "no", "-dita-use-conref-target"],
                elements=["topicref", "topichead", "topicgroup"],
                combinations=["navtitle", "href"],
                contexts=["Use @locktitle to say whether map-provided navigation title text should override the referenced topic title."],
                mistakes=["Setting @navtitle and forgetting locktitle=\"yes\" when the processor should use the map title."],
                example='<topicref href="install.dita" navtitle="Quick setup" locktitle="yes"/>',
                source_url=COMMON_MAP_ATTRIBUTES_SOURCE_URL,
                semantic_class="map_scoped",
                syntax="yes, no, or -dita-use-conref-target",
            ),
            "chunk": _spec(
                "chunk",
                elements=["topicref", "topichead", "topicgroup", "mapref"],
                combinations=["href", "copy-to"],
                contexts=["Use @chunk on map references to influence how processors split, select, or merge referenced topic content into output artifacts."],
                mistakes=["Using processor-specific chunk values as if they were portable DITA values."],
                example='<topicref href="guide.dita" chunk="to-content"/>',
                source_url=COMMON_MAP_ATTRIBUTES_SOURCE_URL,
                semantic_class="map_scoped",
                syntax="space-separated chunk behavior tokens such as to-content, by-topic, by-document, select-topic, select-branch, or select-document",
            ),
            "audience": _spec(
                "audience",
                elements=["topic", "concept", "task", "reference", "topicref", "section", "p"],
                combinations=["platform", "product", "props", "otherprops"],
                contexts=["Use @audience for profiling and conditional processing by intended reader group."],
                mistakes=["Using @audience values without defining or documenting the profiling scheme."],
                example='<topicref href="admin.dita" audience="admin"/>',
                source_url=METADATA_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="one or more space-separated profiling tokens",
            ),
            "platform": _spec(
                "platform",
                elements=["topic", "concept", "task", "reference", "topicref", "section", "p"],
                combinations=["audience", "product", "props", "otherprops"],
                contexts=["Use @platform for platform-specific profiling and filtering."],
                example='<section platform="linux"><title>Linux settings</title><p>Use the Linux package.</p></section>',
                source_url=METADATA_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="one or more space-separated profiling tokens",
            ),
            "product": _spec(
                "product",
                elements=["topic", "concept", "task", "reference", "topicref", "section", "p"],
                combinations=["audience", "platform", "props", "otherprops"],
                contexts=["Use @product for product- or variant-specific profiling."],
                example='<topicref href="pro-install.dita" product="pro"/>',
                source_url=METADATA_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="one or more space-separated profiling tokens",
            ),
            "props": _spec(
                "props",
                elements=["topic", "concept", "task", "reference", "topicref", "section", "p"],
                combinations=["audience", "platform", "product", "otherprops"],
                contexts=["Use @props as a general conditional-processing attribute for specialized profiling values."],
                source_url=METADATA_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="one or more space-separated profiling tokens",
            ),
            "otherprops": _spec(
                "otherprops",
                elements=["topic", "concept", "task", "reference", "topicref", "section", "p"],
                combinations=["audience", "platform", "product", "props"],
                contexts=["Use @otherprops for conditional processing values that do not fit the base profiling attributes."],
                source_url=METADATA_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="one or more space-separated profiling tokens",
            ),
            "rev": _spec(
                "rev",
                elements=["topic", "concept", "task", "reference", "topicref", "section", "p"],
                contexts=["Use @rev to identify content associated with a revision or change marker."],
                source_url=METADATA_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="one or more space-separated revision tokens",
            ),
            "deliverytarget": _spec(
                "deliveryTarget",
                elements=["topic", "concept", "task", "reference", "topicref", "section", "p"],
                combinations=["audience", "platform", "product"],
                contexts=["Use @deliveryTarget to profile content for a delivery target or output channel."],
                source_url=METADATA_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="one or more space-separated delivery-target tokens",
            ),
            "expiry": _spec(
                "expiry",
                elements=["created", "revised"],
                combinations=["date", "modified", "golive"],
                contexts=["Use @expiry on critical-date metadata to record when content expires or should be reviewed."],
                mistakes=["Putting @expiry directly on a topic or map instead of on date metadata such as <created> or <revised>."],
                example='<created date="2026-01-15" expiry="2027-01-15"/>',
                source_url=DATE_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="date or date-time value supported by the DITA date attribute group",
            ),
            "golive": _spec(
                "golive",
                elements=["created", "revised"],
                combinations=["date", "modified", "expiry"],
                contexts=["Use @golive on critical-date metadata to record when content is intended to become active or published."],
                mistakes=["Using @golive as a publishing scheduler by itself; processors or CMS workflows must consume the metadata."],
                example='<revised modified="2026-02-01" golive="2026-02-15"/>',
                source_url=DATE_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="date or date-time value supported by the DITA date attribute group",
            ),
            "outputclass": _spec(
                "outputclass",
                elements=["topic", "concept", "task", "reference", "topicref", "section", "p", "codeblock", "codeph"],
                contexts=["Use @outputclass to pass output-specific classification to downstream processors."],
                mistakes=["Using @outputclass as semantic source data instead of processor styling/classification metadata."],
                example='<codeblock outputclass="language-yaml">apiVersion: v1</codeblock>',
                source_url=COMMON_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="one or more output classification tokens",
            ),
            "importance": _spec(
                "importance",
                values=["optional", "required", "recommended", "-dita-use-conref-target"],
                elements=["note", "step", "cmd"],
                contexts=["Use @importance where DITA allows importance classification for task or note content."],
                source_url=COMMON_ATTRIBUTES_SOURCE_URL,
                semantic_class="enum",
                syntax="optional, required, recommended, or -dita-use-conref-target",
            ),
            "base": _spec(
                "base",
                elements=["topic", "concept", "task", "reference", "map", "topicref", "section", "p"],
                combinations=["props", "outputclass"],
                contexts=["Use @base as a common DITA extension point for specialization or processor-defined metadata."],
                mistakes=["Treating @base values as standardized publishing switches without a governing specialization or processor rule."],
                source_url=COMMON_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="processor- or specialization-defined token value",
            ),
            "status": _spec(
                "status",
                values=["new", "changed", "deleted", "unchanged", "-dita-use-conref-target"],
                elements=["topic", "concept", "task", "reference", "section", "p", "topicref"],
                contexts=["Use @status to mark change status for content where the grammar allows common attributes."],
                mistakes=["Using @status as workflow state in AEM Guides; it is DITA source metadata, not a product workflow state by itself."],
                example='<p status="changed">The command now supports dry-run mode.</p>',
                source_url=COMMON_ATTRIBUTES_SOURCE_URL,
                semantic_class="enum",
                syntax="new, changed, deleted, unchanged, or -dita-use-conref-target",
            ),
            "expanse": _spec(
                "expanse",
                values=["page", "column", "textline", "spread", "-dita-use-conref-target"],
                elements=["fig", "lines", "pre", "codeblock", "simpletable"],
                combinations=["frame", "scale", "outputclass"],
                contexts=["Use @expanse on display-oriented block elements to request horizontal placement or width behavior."],
                mistakes=["Assuming every output processor honors @expanse identically; display attributes can be processor-dependent."],
                example='<fig expanse="page"><title>Deployment overview</title><image href="deployment.png"/></fig>',
                source_url=DISPLAY_ATTRIBUTES_SOURCE_URL,
                semantic_class="enum",
                syntax="page, column, textline, spread, or -dita-use-conref-target",
            ),
            "scale": _spec(
                "scale",
                elements=["fig", "lines", "pre", "codeblock", "simpletable", "object"],
                combinations=["width", "height", "scalefit"],
                contexts=["Use @scale to express a percentage-like scaling value for display-oriented content."],
                source_url=DISPLAY_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="numeric scaling value",
            ),
            "width": _spec(
                "width",
                elements=["image", "object", "fig"],
                combinations=["height", "scale", "scalefit"],
                contexts=["Use @width to indicate the horizontal display dimension where supported."],
                semantic_class="open_token",
                syntax="number optionally followed by pc, pt, px, in, cm, mm, or em",
            ),
            "height": _spec(
                "height",
                elements=["image", "object", "fig"],
                combinations=["width", "scale", "scalefit"],
                contexts=["Use @height to indicate the vertical display dimension where supported."],
                semantic_class="open_token",
                syntax="number optionally followed by pc, pt, px, in, cm, mm, or em",
            ),
            "colsep": _spec(
                "colsep",
                values=["0", "1", "-dita-use-conref-target"],
                elements=["table", "tgroup", "colspec", "row", "entry"],
                combinations=["rowsep", "frame"],
                contexts=["Use @colsep in CALS tables to control column separator rules where supported by the output processor."],
                mistakes=["Using CALS separator attributes on <simpletable> or <properties>, which are not CALS tables."],
                example='<entry colsep="1">Value</entry>',
                source_url=CALS_TABLE_ATTRIBUTES_SOURCE_URL,
                semantic_class="enum",
                syntax="0, 1, or -dita-use-conref-target",
            ),
            "rowsep": _spec(
                "rowsep",
                values=["0", "1", "-dita-use-conref-target"],
                elements=["table", "tgroup", "colspec", "row", "entry"],
                combinations=["colsep", "frame"],
                contexts=["Use @rowsep in CALS tables to control row separator rules where supported by the output processor."],
                mistakes=["Expecting @rowsep to control all table borders when @frame and CSS/output styling also apply."],
                example='<row rowsep="1"><entry>Label</entry><entry>Value</entry></row>',
                source_url=CALS_TABLE_ATTRIBUTES_SOURCE_URL,
                semantic_class="enum",
                syntax="0, 1, or -dita-use-conref-target",
            ),
            "align": _spec(
                "align",
                values=["left", "right", "center", "justify", "char", "-dita-use-conref-target"],
                elements=["tgroup", "colspec", "entry"],
                combinations=["char", "charoff"],
                contexts=["Use @align in CALS tables to control horizontal alignment for entries or columns."],
                mistakes=["Using @align for semantic meaning instead of table presentation behavior."],
                example='<entry align="center">Status</entry>',
                source_url=CALS_TABLE_ATTRIBUTES_SOURCE_URL,
                semantic_class="enum",
                syntax="left, right, center, justify, char, or -dita-use-conref-target",
            ),
            "valign": _spec(
                "valign",
                values=["top", "middle", "bottom", "-dita-use-conref-target"],
                elements=["thead", "tbody", "row", "entry"],
                contexts=["Use @valign in CALS tables to control vertical alignment."],
                source_url=CALS_TABLE_ATTRIBUTES_SOURCE_URL,
                semantic_class="enum",
                syntax="top, middle, bottom, or -dita-use-conref-target",
            ),
            "rowheader": _spec(
                "rowheader",
                values=["firstcol", "headers", "norowheader", "-dita-use-conref-target"],
                elements=["table", "tgroup"],
                contexts=["Use @rowheader in CALS tables to identify row-header behavior for accessibility and rendering."],
                mistakes=["Relying only on visual styling instead of row-header semantics where the table needs accessible row labels."],
                source_url=CALS_TABLE_ATTRIBUTES_SOURCE_URL,
                semantic_class="enum",
                syntax="firstcol, headers, norowheader, or -dita-use-conref-target",
            ),
            "frame": _spec(
                "frame",
                values=["top", "bottom", "topbot", "all", "sides", "none", "-dita-use-conref-target"],
                elements=["table", "fig", "lines", "pre", "codeblock", "simpletable"],
                combinations=["colsep", "rowsep"],
                contexts=["Use @frame on display-oriented block elements to request borders or rule lines where supported by the output processor."],
                source_url=DISPLAY_ATTRIBUTES_SOURCE_URL,
                semantic_class="enum",
                syntax="top, bottom, topbot, all, sides, none, or -dita-use-conref-target",
            ),
            "keycol": _spec(
                "keycol",
                elements=["simpletable"],
                combinations=["relcolwidth"],
                contexts=["Use @keycol on <simpletable> to identify the column that functions as the row header column."],
                mistakes=["Using @keycol on CALS <table>; CALS tables use their own header structures and table attributes."],
                example='<simpletable keycol="1"><strow><stentry>Name</stentry><stentry>Value</stentry></strow></simpletable>',
                source_url=SIMPLETABLE_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="1-based column number token",
            ),
            "relcolwidth": _spec(
                "relcolwidth",
                elements=["simpletable"],
                combinations=["keycol"],
                contexts=["Use @relcolwidth on <simpletable> to provide proportional column-width hints."],
                mistakes=["Using CALS @colwidth syntax on <simpletable>; simple tables use @relcolwidth instead."],
                example='<simpletable relcolwidth="1* 3*"><strow><stentry>Key</stentry><stentry>Value</stentry></strow></simpletable>',
                source_url=SIMPLETABLE_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="space-separated relative column-width tokens such as 1* 3*",
            ),
            "refcols": _spec(
                "refcols",
                elements=["simpletable"],
                combinations=["keycol", "relcolwidth"],
                contexts=["Use @refcols only where a simpletable specialization or processor defines reference-column behavior."],
                mistakes=["Assuming @refcols has the same meaning as CALS column-span attributes; it belongs to the simpletable attribute group."],
                source_url=SIMPLETABLE_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="space-separated column reference tokens",
            ),
            "cols": _spec(
                "cols",
                elements=["tgroup"],
                combinations=["colspec"],
                contexts=["Use @cols on <tgroup> to declare the number of columns in a CALS table group."],
                mistakes=["Declaring @cols that does not match the effective column structure."],
                example='<tgroup cols="3">',
                source_url=CALS_TABLE_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="positive integer column count",
            ),
            "colname": _spec(
                "colname",
                elements=["colspec", "entry"],
                combinations=["namest", "nameend"],
                contexts=["Use @colname to name or target a CALS table column."],
                source_url=CALS_TABLE_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="column name token",
            ),
            "namest": _spec(
                "namest",
                elements=["entry"],
                combinations=["nameend"],
                contexts=["Use @namest with @nameend on a CALS table entry to span a range of named columns."],
                source_url=CALS_TABLE_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="starting column name token",
            ),
            "nameend": _spec(
                "nameend",
                elements=["entry"],
                combinations=["namest"],
                contexts=["Use @nameend with @namest on a CALS table entry to span a range of named columns."],
                source_url=CALS_TABLE_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="ending column name token",
            ),
            "morerows": _spec(
                "morerows",
                elements=["entry"],
                contexts=["Use @morerows on a CALS table entry to span additional rows."],
                mistakes=["Using @morerows without checking that the resulting table grid remains valid."],
                source_url=CALS_TABLE_ATTRIBUTES_SOURCE_URL,
                semantic_class="open_token",
                syntax="non-negative integer row-span count",
            ),
        }
    )
    return specs


@lru_cache(maxsize=1)
def _load_seed() -> list[dict[str, Any]]:
    try:
        with open(SEED_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def _normalize_string_list(items: Any) -> list[str]:
    values: list[str] = []
    if isinstance(items, list):
        for item in items:
            text = str(item or "").strip()
            if text and text not in values:
                values.append(text)
    return values


def _parse_attribute_map(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _clean_attribute_text(attr_name: str, text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    cleaned = re.sub(rf"^<{re.escape(attr_name)}>", f"@{attr_name}", cleaned, count=1, flags=re.IGNORECASE)
    cleaned = re.sub(
        rf"\bWhat is {re.escape(attr_name)}\?",
        f"What is @{attr_name}?",
        cleaned,
        count=1,
        flags=re.IGNORECASE,
    )
    return cleaned


def _attribute_uses_open_token_syntax(attr_name: str, values: list[str], text: str) -> bool:
    """Detect attributes whose syntax accepts arbitrary names/tokens rather than fixed enum values."""

    if not values:
        return False
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    if "valid values" in normalized:
        return False
    if "syntax:" not in normalized:
        return False
    if "space-separated" not in normalized:
        return False
    # keyscope-style attributes accept arbitrary scope names rather than a closed set of literals.
    return (
        f"@{attr_name}" in normalized
        and (
            "same naming rules as keys" in normalized
            or "same naming rules as" in normalized
            or "scope names" in normalized
            or "key names" in normalized
        )
    )


def _extract_attribute_syntax(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    match = re.search(r"Syntax:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if not match:
        return ""
    syntax = str(match.group(1) or "").strip()
    return syntax.splitlines()[0].strip().rstrip(".")


def _extract_xml_examples_from_markdown_fences(text: str, attr_name: str) -> list[str]:
    """Recover example XML from ```xml fences in seed text when correct_examples is omitted."""
    attr_key = str(attr_name or "").strip().lower()
    if not attr_key or not str(text or "").strip():
        return []
    # Avoid spurious matches like attoc= for attribute toc
    attr_assign = re.compile(rf"(?:^|[^\w:.-]){re.escape(attr_key)}\s*=", re.IGNORECASE)
    out: list[str] = []
    for match in _FENCED_XML_BLOCK_RE.finditer(text):
        block = str(match.group(1) or "").strip()
        if not block or "<" not in block:
            continue
        if not attr_assign.search(block):
            continue
        if block not in out:
            out.append(block)
        if len(out) >= 3:
            break
    return out


def _infer_attribute_semantic_class(
    attr_name: str,
    *,
    all_valid_values: list[str],
    supported_elements: list[str],
    syntax: str,
    text_content: str,
) -> str:
    normalized_name = str(attr_name or "").strip().lower()
    normalized_text = str(text_content or "").lower()
    normalized_syntax = str(syntax or "").lower()
    normalized_elements = {str(item or "").strip().lower() for item in supported_elements if str(item or "").strip()}
    if normalized_name in {
        "keyscope",
        "processing-role",
        "chunk",
        "collection-type",
        "linking",
        "toc",
        "print",
        "navtitle",
        "locktitle",
        "search",
    }:
        return "map_scoped"
    if normalized_name in {"href", "conref", "conkeyref", "keyref", "conrefend", "copy-to"}:
        return "reference_like"
    if normalized_name in {"format"} or "uri" in normalized_syntax or "path" in normalized_syntax:
        return "path_like"
    if normalized_name in {"id", "xml:lang"}:
        return "open_token"
    if normalized_name == "dir":
        return "enum"
    if {"yes", "no"}.issubset({value.lower() for value in all_valid_values}):
        return "boolean_like"
    if _attribute_uses_open_token_syntax(normalized_name, all_valid_values, text_content):
        return "open_token"
    if all_valid_values:
        return "enum"
    if normalized_name.endswith("ref") or "reference" in normalized_text:
        return "reference_like"
    if "topicref" in normalized_elements or "map" in normalized_elements:
        return "map_scoped"
    return "open_token" if normalized_syntax else "enum"


def _looks_like_attribute_entry(entry: dict[str, Any]) -> bool:
    raw_name = str(entry.get("element_name") or "").strip()
    if not raw_name:
        return False
    if entry.get("content_type") in {"attribute", "conref"}:
        return True
    text_content = str(entry.get("text_content") or "").strip().lower()
    if not text_content:
        return False

    normalized_name = raw_name
    if normalized_name.endswith("_attribute"):
        normalized_name = normalized_name[: -len("_attribute")]
    normalized_name = normalized_name.replace("_", "-").strip().lower()
    if not normalized_name:
        return False

    attribute_signals = (
        f"@{normalized_name} attribute",
        f"the @{normalized_name} attribute",
        f"{normalized_name} attribute on <",
    )
    return any(signal in text_content for signal in attribute_signals)


def _attribute_map_looks_like_valid_values(entry: dict[str, Any], attribute_map: dict[str, Any]) -> bool:
    if not attribute_map:
        return False
    tdc = entry.get("test_data_coverage") or {}
    if _normalize_string_list(tdc.get("all_values")):
        return True
    text_content = str(entry.get("text_content") or "").strip().lower()
    return "valid values" in text_content


def _entry_matches_attribute(entry: dict[str, Any], attr_name: str) -> bool:
    ename = str(entry.get("element_name") or "")
    if not ename:
        return False
    candidates = {
        f"{attr_name}_attribute",
        f"{attr_name.replace('-', '_')}_attribute",
        attr_name,
    }
    if ename in candidates:
        return True
    return attr_name.replace("-", "_") in ename and entry.get("content_type") in {"attribute", "conref"}


def _find_attribute_entries(attr_name: str) -> list[dict[str, Any]]:
    """Find all seed entries that contribute to a single attribute spec."""
    seed = _load_seed()
    candidates = {
        f"{attr_name}_attribute",
        f"{attr_name.replace('-', '_')}_attribute",
        attr_name,
    }
    return [
        entry
        for entry in seed
        if str(entry.get("element_name") or "") in candidates and _looks_like_attribute_entry(entry)
    ]


@lru_cache(maxsize=1)
def list_attribute_names() -> tuple[str, ...]:
    """Return normalized DITA attribute names available in the seed catalog."""
    names: set[str] = set()
    for entry in _load_seed():
        if not _looks_like_attribute_entry(entry):
            continue
        raw = str(entry.get("element_name") or "").strip()
        if not raw:
            continue
        if raw.endswith("_attribute"):
            raw = raw[: -len("_attribute")]
        normalized = raw.replace("_", "-").strip().lower()
        if normalized:
            names.add(normalized)
    names.update(str(name).replace("_", "-").strip().lower() for name in _supplemental_attribute_specs().keys())
    return tuple(sorted(names))


def get_attribute_spec(attr_name: str) -> AttributeSpec | None:
    """Look up attribute from dita_spec_seed.json, return full spec."""
    normalized_attr_name = str(attr_name or "").strip().replace("_", "-").lower()
    if not normalized_attr_name:
        return None

    supplemental = _supplemental_attribute_specs().get(normalized_attr_name)
    entries = _find_attribute_entries(normalized_attr_name)
    if not entries:
        return supplemental

    attr_name = normalized_attr_name

    all_valid_values: list[str] = []
    supported_elements: list[str] = []
    combination_attributes: list[str] = []
    default_scenarios: list[str] = []
    usage_contexts: list[str] = []
    common_mistakes: list[str] = []
    correct_examples: list[str] = []
    source_url = ""
    text_candidates: list[str] = []

    attr_pattern = re.compile(
        _ATTRIBUTE_EXAMPLE_TAG_PATTERN.format(attr_name=re.escape(attr_name)),
        flags=re.IGNORECASE,
    )

    for entry in entries:
        tdc = entry.get("test_data_coverage") or {}
        all_valid_values.extend(_normalize_string_list(tdc.get("all_values")))
        supported_elements.extend(_normalize_string_list(tdc.get("supported_elements")))
        combination_attributes.extend(_normalize_string_list(tdc.get("combination_attributes")))
        default_scenarios.extend(_normalize_string_list(tdc.get("default_scenarios")))

        entry_usage_contexts = _normalize_string_list(entry.get("usage_contexts"))
        usage_contexts.extend(entry_usage_contexts)
        default_scenarios.extend(entry_usage_contexts)
        common_mistakes.extend(_normalize_string_list(entry.get("common_mistakes")))
        correct_examples.extend(_normalize_string_list(entry.get("correct_examples")))

        attribute_map = _parse_attribute_map(entry.get("attributes"))
        normalized_attribute_map_keys = [
            key.replace("_", "-").strip().lower()
            for key in attribute_map
            if key and key.replace("_", "-").strip().lower() != attr_name
        ]
        if _attribute_map_looks_like_valid_values(entry, attribute_map):
            all_valid_values.extend(normalized_attribute_map_keys)
        else:
            combination_attributes.extend(normalized_attribute_map_keys)

        text_content = _clean_attribute_text(attr_name, str(entry.get("text_content") or ""))
        if text_content:
            text_candidates.append(text_content)
            for match in attr_pattern.finditer(text_content):
                element_name = str(match.group(1) or "").strip().lower()
                if element_name:
                    supported_elements.append(element_name)

        for example in _normalize_string_list(entry.get("correct_examples")):
            for match in attr_pattern.finditer(example):
                element_name = str(match.group(1) or "").strip().lower()
                if element_name:
                    supported_elements.append(element_name)

        entry_source_url = str(entry.get("source_url") or "").strip()
        if entry_source_url and not source_url:
            source_url = entry_source_url

    if not correct_examples and text_candidates:
        correct_examples.extend(
            _extract_xml_examples_from_markdown_fences("\n\n".join(text_candidates), attr_name)
        )

    def _dedupe(items: list[str]) -> list[str]:
        seen: list[str] = []
        for item in items:
            normalized = str(item or "").strip()
            if normalized and normalized not in seen:
                seen.append(normalized)
        return seen

    text_content = max(text_candidates, key=len) if text_candidates else ""
    all_valid_values = _dedupe(all_valid_values)
    if _attribute_uses_open_token_syntax(attr_name, all_valid_values, text_content):
        all_valid_values = []
    syntax = _extract_attribute_syntax(text_content)
    semantic_class = _infer_attribute_semantic_class(
        attr_name,
        all_valid_values=all_valid_values,
        supported_elements=_dedupe(supported_elements),
        syntax=syntax,
        text_content=text_content,
    )

    resolved = AttributeSpec(
        attribute_name=attr_name,
        all_valid_values=all_valid_values,
        supported_elements=_dedupe(supported_elements),
        combination_attributes=_dedupe(combination_attributes),
        default_scenarios=_dedupe(default_scenarios),
        usage_contexts=_dedupe(usage_contexts),
        common_mistakes=_dedupe(common_mistakes),
        correct_examples=_dedupe(correct_examples),
        text_content=text_content,
        source_url=source_url,
        semantic_class=semantic_class,
        syntax=syntax,
    )

    if supplemental is None:
        return resolved

    merged_valid_values = _dedupe([*resolved.all_valid_values, *supplemental.all_valid_values])
    merged_supported_elements = _dedupe([*resolved.supported_elements, *supplemental.supported_elements])
    merged_combination_attributes = _dedupe(
        [*resolved.combination_attributes, *supplemental.combination_attributes]
    )
    merged_default_scenarios = _dedupe([*resolved.default_scenarios, *supplemental.default_scenarios])
    merged_usage_contexts = _dedupe([*resolved.usage_contexts, *supplemental.usage_contexts])
    merged_common_mistakes = _dedupe([*resolved.common_mistakes, *supplemental.common_mistakes])
    merged_correct_examples = _dedupe([*resolved.correct_examples, *supplemental.correct_examples])
    merged_text_content = resolved.text_content or supplemental.text_content
    authoritative_group_sources = {
        ID_ATTRIBUTES_SOURCE_URL,
        METADATA_ATTRIBUTES_SOURCE_URL,
        LOCALIZATION_ATTRIBUTES_SOURCE_URL,
        DEBUG_ATTRIBUTES_SOURCE_URL,
        ARCHITECTURAL_ATTRIBUTES_SOURCE_URL,
        COMMON_MAP_ATTRIBUTES_SOURCE_URL,
        CALS_TABLE_ATTRIBUTES_SOURCE_URL,
        DISPLAY_ATTRIBUTES_SOURCE_URL,
        DATE_ATTRIBUTES_SOURCE_URL,
        LINK_RELATIONSHIP_ATTRIBUTES_SOURCE_URL,
        COMMON_ATTRIBUTES_SOURCE_URL,
        SIMPLETABLE_ATTRIBUTES_SOURCE_URL,
    }
    if supplemental.source_url in authoritative_group_sources:
        merged_source_url = supplemental.source_url
    else:
        merged_source_url = resolved.source_url or supplemental.source_url
    merged_syntax = resolved.syntax or supplemental.syntax
    merged_semantic_class = _infer_attribute_semantic_class(
        attr_name,
        all_valid_values=merged_valid_values,
        supported_elements=merged_supported_elements,
        syntax=merged_syntax,
        text_content=merged_text_content,
    )
    return AttributeSpec(
        attribute_name=resolved.attribute_name,
        all_valid_values=merged_valid_values,
        supported_elements=merged_supported_elements,
        combination_attributes=merged_combination_attributes,
        default_scenarios=merged_default_scenarios,
        usage_contexts=merged_usage_contexts,
        common_mistakes=merged_common_mistakes,
        correct_examples=merged_correct_examples,
        text_content=merged_text_content,
        source_url=merged_source_url,
        semantic_class=merged_semantic_class,
        syntax=merged_syntax,
    )


def build_test_scenarios(
    attr_name: str,
    elements: list[str],
    mentioned_values: list[str],
) -> list[str]:
    """Generate test scenario descriptions for all value×element combinations."""
    spec = get_attribute_spec(attr_name)
    if spec is None:
        return [f"{attr_name}={v} on relevant elements" for v in mentioned_values]

    scenarios: list[str] = []
    target_elements = elements or spec.supported_elements[:4]
    all_values = spec.all_valid_values or mentioned_values

    # Generate scenarios for each value on primary element
    primary_elem = target_elements[0] if target_elements else "topicref"
    for val in all_values:
        scenarios.append(f"{primary_elem} with {attr_name}={val}")

    # Default/omitted case
    for ds in spec.default_scenarios:
        scenarios.append(ds)

    # Cross-element coverage for mentioned values
    for elem in target_elements[1:]:
        for val in mentioned_values or all_values[:3]:
            scenarios.append(f"{elem} with {attr_name}={val}")

    # Combination scenarios
    for combo_attr in spec.combination_attributes[:3]:
        scenarios.append(
            f"{primary_elem} with {attr_name}={all_values[0] if all_values else 'value'} + {combo_attr}"
        )

    return scenarios
