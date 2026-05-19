"""Coverage and verified-example registry for DITA chat and generation.

This module is intentionally policy-oriented: it answers "do we know how to
explain, exemplify, and generate this construct?" before the chat or generation
layer guesses.  The goal is to make missing coverage visible in tests and debug
metadata instead of discovering gaps one user prompt at a time.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.services.dita_attribute_catalog import get_attribute_spec, list_attribute_names
from app.services.dita_construct_semantics_service import get_construct_library_snapshot
from app.services.dita_spec_registry_service import get_element_spec, list_element_names


CoverageStatus = Literal["strong", "partial", "unsupported_explicit", "gap"]


TOP_VALUE_CONSTRUCTS: tuple[str, ...] = (
    "topicref",
    "topichead",
    "topicgroup",
    "mapref",
    "navref",
    "reltable",
    "relrow",
    "relcell",
    "keydef",
    "keyref",
    "keys",
    "keyscope",
    "conref",
    "conrefend",
    "conkeyref",
    "xref",
    "related-links",
    "link",
    "linklist",
    "linkinfo",
    "subjectscheme",
    "subjectdef",
    "ditaval",
    "ditavalref",
    "refbody",
    "refsyn",
    "codeblock",
    "codeph",
    "foreign",
    "data",
    "data-about",
    "prop",
    "revprop",
    "val",
    "startflag",
    "endflag",
    "alt-text",
)

TOP_VALUE_ATTRIBUTES: tuple[str, ...] = (
    "href",
    "keyref",
    "keys",
    "keyscope",
    "conref",
    "conrefend",
    "conkeyref",
    "scope",
    "format",
    "type",
    "processing-role",
    "toc",
    "linking",
    "collection-type",
    "chunk",
    "copy-to",
    "navtitle",
    "locktitle",
    "audience",
    "platform",
    "product",
    "props",
    "otherprops",
    "rev",
    "deliveryTarget",
    "outputclass",
    "importance",
    "scale",
    "scalefit",
    "width",
    "height",
)


def known_construct_names() -> tuple[str, ...]:
    """Return every construct/element currently known to the DITA layer.

    This is intentionally broader than TOP_VALUE_CONSTRUCTS.  The top-value
    list is the high-priority CI gate; this list is the full coverage audit
    surface built from the spec registry plus the construct semantics service.
    """
    names = {
        _normalize_name(name)
        for name in (*list_element_names(), *get_construct_library_snapshot().keys())
        if _normalize_name(name)
    }
    return tuple(sorted(names))


def known_attribute_names() -> tuple[str, ...]:
    """Return every attribute currently known to the DITA attribute catalog."""
    names = {_normalize_name(name) for name in list_attribute_names() if _normalize_name(name)}
    return tuple(sorted(names))

DETERMINISTIC_GENERATION_STRATEGIES: dict[str, str] = {
    "topicref": "maps.topicref_basic",
    "topichead": "maps.topichead_basic",
    "topicgroup": "maps.topicgroup_basic",
    "mapref": "maps.mapref_basic",
    "navref": "maps.navref_basic",
    "reltable": "maps.reltable_basic",
    "relrow": "maps.reltable_basic",
    "relcell": "maps.reltable_basic",
    "keyscope": "keyscope_demo",
    "xref": "xref_variety_bundle",
    "conref": "conref_pack",
    "conrefend": "conref_pack",
    "conkeyref": "dita_conref_keyref_dataset_recipe",
    "keyref": "keys.keydef_basic",
    "keys": "keys.keydef_basic",
    "keydef": "keys.keydef_basic",
    "subjectscheme": "dita_subject_scheme_dataset_recipe",
    "subjectdef": "dita_subject_scheme_dataset_recipe",
    "ditaval": "conditionals.audience_filter",
    "ditavalref": "conditionals.audience_filter",
    "related-links": "xref_variety_bundle",
    "link": "xref_variety_bundle",
    "linklist": "xref_variety_bundle",
    "linkinfo": "xref_variety_bundle",
    "refbody": "reference_topics",
    "refsyn": "reference_topics",
    "codeblock": "reference_topics",
    "codeph": "reference_topics",
}

EXPLICITLY_UNSUPPORTED_GENERATION: dict[str, str] = {
    "foreign": "Supported for explanation and snippets, but full generation is blocked unless the requested foreign vocabulary and fallback policy are explicit.",
    "data": "Supported for explanation and snippets; standalone dataset generation is not enabled because data is processor/specialization dependent.",
    "data-about": "Supported for explanation and snippets; standalone dataset generation is not enabled because data-about is metadata-context dependent.",
    "prop": "Generated only as part of a DITAVAL profile, not as a standalone topic artifact.",
    "revprop": "Generated only as part of a DITAVAL profile, not as a standalone topic artifact.",
    "val": "Generated only as a .ditaval profile root, not as a topic.",
    "startflag": "Generated only as part of a DITAVAL flagging profile.",
    "endflag": "Generated only as part of a DITAVAL flagging profile.",
    "alt-text": "Generated only as part of a DITAVAL flagging profile.",
}

PUBLISHING_SENSITIVE_CONSTRUCTS: frozenset[str] = frozenset(
    {
        "topicref",
        "topichead",
        "topicgroup",
        "mapref",
        "navref",
        "reltable",
        "related-links",
        "link",
        "linklist",
        "linkinfo",
        "foreign",
        "ditaval",
        "ditavalref",
        "toc",
        "chunk",
        "processing-role",
        "print",
    }
)


@dataclass(frozen=True)
class CoverageExample:
    label: str
    snippet: str
    source: str
    deterministic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DitaConstructCoverage:
    name: str
    item_type: Literal["element", "attribute"]
    coverage_status: CoverageStatus
    definition_present: bool
    structure_present: bool
    example_source: str
    generation_strategy: str
    publishing_source_policy: str
    source_url: str = ""
    gaps: tuple[str, ...] = ()
    deterministic_example: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DitaConstructCoverageReport:
    entries: tuple[DitaConstructCoverage, ...]

    @property
    def gaps(self) -> tuple[DitaConstructCoverage, ...]:
        return tuple(entry for entry in self.entries if entry.coverage_status == "gap")

    @property
    def ok(self) -> bool:
        return not self.gaps

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "entries": [entry.to_dict() for entry in self.entries],
            "gaps": [entry.to_dict() for entry in self.gaps],
        }


def _normalize_name(value: str) -> str:
    return str(value or "").strip().strip("<>@").replace("_", "-").lower()


def _construct_template(name: str) -> str:
    templates = {
        "topicref": '<map>\n  <title>Operations Guide</title>\n  <topicref href="overview.dita" navtitle="Overview"/>\n</map>',
        "topichead": '<map>\n  <title>Operations Guide</title>\n  <topichead navtitle="Operations">\n    <topicref href="start.dita"/>\n  </topichead>\n</map>',
        "topicgroup": '<map>\n  <title>Operations Guide</title>\n  <topicgroup>\n    <topicref href="start.dita"/>\n    <topicref href="stop.dita"/>\n  </topicgroup>\n</map>',
        "mapref": '<map>\n  <title>Parent Guide</title>\n  <mapref href="child-map.ditamap"/>\n</map>',
        "navref": '<map>\n  <title>Parent Guide</title>\n  <navref href="navigation.ditamap"/>\n</map>',
        "reltable": '<map>\n  <title>Guide</title>\n  <reltable>\n    <relrow>\n      <relcell><topicref href="install.dita"/></relcell>\n      <relcell><topicref href="configure.dita"/></relcell>\n    </relrow>\n  </reltable>\n</map>',
        "relrow": '<reltable>\n  <relrow>\n    <relcell><topicref href="a.dita"/></relcell>\n    <relcell><topicref href="b.dita"/></relcell>\n  </relrow>\n</reltable>',
        "relcell": '<relcell>\n  <topicref href="related-topic.dita"/>\n</relcell>',
        "keydef": '<map>\n  <title>Key definitions</title>\n  <keydef keys="support-docs" href="https://example.com/support" scope="external" format="html">\n    <topicmeta><linktext>Support documentation</linktext></topicmeta>\n  </keydef>\n</map>',
        "keyref": '<map>\n  <keydef keys="install-guide" href="install.dita"/>\n  <topicref href="consumer.dita"/>\n</map>\n\n<topic id="consumer">\n  <title>Consumer</title>\n  <body><p>See <xref keyref="install-guide">installation guidance</xref>.</p></body>\n</topic>',
        "keys": '<map>\n  <topicref keys="install-guide" href="install.dita"/>\n</map>',
        "keyscope": '<map>\n  <title>Scoped keys</title>\n  <topicref keyscope="product-a">\n    <keydef keys="product-name" href="product-a.dita"/>\n    <topicref href="consumer.dita"/>\n  </topicref>\n</map>',
        "conref": '<topic id="consumer">\n  <title>Consumer</title>\n  <body><p conref="reuse.dita#reuse/reusable-note"/></body>\n</topic>',
        "conrefend": '<topic id="consumer">\n  <title>Consumer</title>\n  <body><p conref="reuse.dita#reuse/start" conrefend="reuse.dita#reuse/end"/></body>\n</topic>',
        "conkeyref": '<map>\n  <keydef keys="reuse-key" href="reuse.dita"/>\n  <topicref href="consumer.dita"/>\n</map>\n\n<topic id="consumer">\n  <title>Consumer</title>\n  <body><p conkeyref="reuse-key/reusable-note"/></body>\n</topic>',
        "xref": '<topic id="source">\n  <title>Source</title>\n  <body><p>See <xref href="target.dita#target/details">target details</xref>.</p></body>\n</topic>',
        "related-links": '<topic id="source">\n  <title>Source</title>\n  <body><p>Primary content.</p></body>\n  <related-links><link href="target.dita"/></related-links>\n</topic>',
        "link": '<related-links>\n  <link href="target.dita"><linktext>Target topic</linktext></link>\n</related-links>',
        "linklist": '<related-links>\n  <linklist>\n    <title>Related tasks</title>\n    <link href="install.dita"><linktext>Install</linktext></link>\n  </linklist>\n</related-links>',
        "linkinfo": '<related-links>\n  <link href="install.dita">\n    <linktext>Install</linktext>\n    <linkinfo>Use this topic before configuring the product.</linkinfo>\n  </link>\n</related-links>',
        "subjectscheme": '<subjectScheme>\n  <subjectdef keys="audience-values">\n    <subjectdef keys="admin"/>\n    <subjectdef keys="developer"/>\n  </subjectdef>\n  <enumerationdef>\n    <attributedef name="audience"/>\n    <subjectdef keyref="audience-values"/>\n  </enumerationdef>\n</subjectScheme>',
        "subjectdef": '<subjectScheme>\n  <subjectdef keys="platform-values">\n    <subjectdef keys="linux"/>\n    <subjectdef keys="windows"/>\n  </subjectdef>\n</subjectScheme>',
        "ditaval": '<val>\n  <prop att="audience" val="internal" action="exclude"/>\n  <prop att="platform" val="linux" action="include"/>\n</val>',
        "ditavalref": '<map>\n  <topicref href="install.dita">\n    <ditavalref href="profiles/linux.ditaval" format="ditaval"/>\n  </topicref>\n</map>',
        "refbody": '<reference id="kubectl-get">\n  <title>kubectl get</title>\n  <refbody><section><title>Purpose</title><p>List Kubernetes resources.</p></section></refbody>\n</reference>',
        "refsyn": '<reference id="kubectl-apply">\n  <title>kubectl apply</title>\n  <refbody><refsyn><codeblock outputclass="language-bash">kubectl apply -f deployment.yaml</codeblock></refsyn></refbody>\n</reference>',
        "codeblock": '<topic id="yaml-example">\n  <title>YAML example</title>\n  <body><codeblock outputclass="language-yaml">apiVersion: v1\nkind: ConfigMap</codeblock></body>\n</topic>',
        "codeph": '<topic id="inline-code">\n  <title>Inline code</title>\n  <body><p>Run <codeph>kubectl get pods</codeph> before troubleshooting.</p></body>\n</topic>',
        "foreign": '<topic id="foreign-svg">\n  <title>Foreign content</title>\n  <body><foreign><svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"/></foreign></body>\n</topic>',
        "data": '<topic id="metadata-example">\n  <title>Metadata</title>\n  <body><p>Visible text.</p><data name="source-system" value="cms"/></body>\n</topic>',
        "data-about": '<topic id="data-about-example">\n  <title>Metadata subject</title>\n  <body><data name="review"><data-about href="target.dita"/></data></body>\n</topic>',
        "val": '<val>\n  <prop att="audience" val="draft" action="exclude"/>\n</val>',
        "prop": '<val>\n  <prop att="audience" val="external" action="include"/>\n</val>',
        "revprop": '<val>\n  <revprop val="rev-2026" action="flag"/>\n</val>',
        "startflag": '<val>\n  <prop att="audience" val="admin" action="flag">\n    <startflag imageref="flags/admin-start.svg"><alt-text>Admin-only content starts</alt-text></startflag>\n  </prop>\n</val>',
        "endflag": '<val>\n  <prop att="audience" val="admin" action="flag">\n    <endflag imageref="flags/admin-end.svg"><alt-text>Admin-only content ends</alt-text></endflag>\n  </prop>\n</val>',
        "alt-text": '<startflag imageref="flags/admin-start.svg">\n  <alt-text>Admin-only content starts</alt-text>\n</startflag>',
    }
    return templates.get(name, "")


def _attribute_template(name: str) -> str:
    templates = {
        "keyscope": '<map>\n  <topicref keyscope="product-a">\n    <keydef keys="product-name" href="product-a.dita"/>\n  </topicref>\n</map>',
        "processing-role": '<map>\n  <topicref href="shared-warning.dita" processing-role="resource-only"/>\n</map>',
        "chunk": '<map chunk="to-content">\n  <topicref href="part-1.dita"/>\n  <topicref href="part-2.dita"/>\n</map>',
        "toc": '<map>\n  <topicref href="reference-data.dita" toc="no"/>\n</map>',
        "linking": '<map>\n  <topicref href="overview.dita" linking="normal"/>\n</map>',
        "collection-type": '<map>\n  <topicref href="workflow.dita" collection-type="sequence">\n    <topicref href="step-1.dita"/>\n    <topicref href="step-2.dita"/>\n  </topicref>\n</map>',
        "href": '<topic id="source"><title>Source</title><body><p>See <xref href="target.dita">target</xref>.</p></body></topic>',
        "keyref": '<topic id="source"><title>Source</title><body><p>See <xref keyref="install-guide">install guide</xref>.</p></body></topic>',
        "keys": '<map><topicref keys="install-guide" href="install.dita"/></map>',
        "conref": '<p conref="reuse.dita#reuse/common-warning"/>',
        "conrefend": '<p conref="reuse.dita#reuse/start" conrefend="reuse.dita#reuse/end"/>',
        "conkeyref": '<p conkeyref="reuse-key/common-warning"/>',
        "format": '<xref href="https://example.com" scope="external" format="html">External site</xref>',
        "scope": '<xref href="https://example.com" scope="external" format="html">External site</xref>',
        "outputclass": '<codeblock outputclass="language-yaml">kind: ConfigMap</codeblock>',
        "scalefit": '<image href="diagram.png" scalefit="yes"><alt>Architecture diagram</alt></image>',
    }
    return templates.get(name, "")


def verified_examples_for_construct(name: str, *, item_type: Literal["element", "attribute"] = "element") -> tuple[CoverageExample, ...]:
    normalized = _normalize_name(name)
    examples: list[CoverageExample] = []
    if item_type == "attribute":
        spec = get_attribute_spec(normalized)
        for item in (spec.correct_examples if spec else [])[:3]:
            snippet = str(item or "").strip()
            if snippet:
                examples.append(CoverageExample("Verified attribute example", snippet, "attribute_catalog"))
        template = _attribute_template(normalized)
        if template and not any(example.snippet == template for example in examples):
            examples.append(CoverageExample("Deterministic attribute template", template, "deterministic_template", True))
        return tuple(examples)

    spec = get_element_spec(normalized)
    for item in (spec.correct_examples if spec else [])[:3]:
        snippet = str(item or "").strip()
        if snippet:
            examples.append(CoverageExample("Verified element example", snippet, "spec_registry"))
    template = _construct_template(normalized)
    if template and not any(example.snippet == template for example in examples):
        examples.append(CoverageExample("Deterministic construct template", template, "deterministic_template", True))
    return tuple(examples)


def _publishing_policy(name: str, *, item_type: str) -> str:
    normalized = _normalize_name(name)
    if normalized in PUBLISHING_SENSITIVE_CONSTRUCTS or item_type == "attribute" and normalized in PUBLISHING_SENSITIVE_CONSTRUCTS:
        return "dita_spec_first_then_processor_docs"
    return "dita_spec_first"


def _generation_strategy(name: str, semantics: dict[str, Any]) -> str:
    normalized = _normalize_name(name)
    if normalized in DETERMINISTIC_GENERATION_STRATEGIES:
        return f"deterministic:{DETERMINISTIC_GENERATION_STRATEGIES[normalized]}"
    if normalized in EXPLICITLY_UNSUPPORTED_GENERATION:
        return "unsupported_explicit"
    if semantics and bool(semantics.get("requires_contract_path")):
        return "contract_llm_with_validation"
    if semantics:
        return "deterministic_generic_topic"
    return "missing"


def coverage_for_construct(name: str, *, item_type: Literal["element", "attribute"] = "element") -> DitaConstructCoverage:
    normalized = _normalize_name(name)
    semantics = get_construct_library_snapshot().get(normalized, {}) if item_type == "element" else {}
    examples = verified_examples_for_construct(normalized, item_type=item_type)
    source_url = ""
    definition_present = False
    structure_present = False

    if item_type == "attribute":
        attr = get_attribute_spec(normalized)
        source_url = attr.source_url if attr else ""
        definition_present = bool(attr and attr.text_content)
        structure_present = bool(attr and (attr.supported_elements or attr.syntax or attr.semantic_class))
        generation_strategy = "attribute_supported_in_construct_contract" if attr else "missing"
    else:
        spec = get_element_spec(normalized)
        source_url = str((spec.source_url if spec else "") or semantics.get("source_url") or "")
        definition_present = bool((spec and spec.description) or semantics.get("notes"))
        structure_present = bool(
            (spec and (spec.allowed_children or spec.allowed_parents or spec.supported_attributes))
            or semantics.get("required_elements")
            or semantics.get("valid_root_types")
        )
        generation_strategy = _generation_strategy(normalized, semantics)

    gaps: list[str] = []
    if not definition_present:
        gaps.append("definition")
    if not structure_present:
        gaps.append("structure")
    if not examples:
        gaps.append("verified_example")
    if item_type == "element" and generation_strategy == "missing":
        gaps.append("generation_strategy")

    if gaps:
        status: CoverageStatus = "gap"
    elif generation_strategy == "unsupported_explicit":
        status = "unsupported_explicit"
    elif definition_present and structure_present and examples:
        status = "strong"
    else:
        status = "partial"

    return DitaConstructCoverage(
        name=normalized,
        item_type=item_type,
        coverage_status=status,
        definition_present=definition_present,
        structure_present=structure_present,
        example_source=examples[0].source if examples else "",
        generation_strategy=generation_strategy,
        publishing_source_policy=_publishing_policy(normalized, item_type=item_type),
        source_url=source_url,
        gaps=tuple(gaps),
        deterministic_example=next((example.snippet for example in examples if example.deterministic), ""),
    )


def build_dita_construct_coverage_report(
    names: tuple[str, ...] | list[str] | None = None,
    *,
    include_attributes: bool = True,
) -> DitaConstructCoverageReport:
    construct_names = tuple(_normalize_name(name) for name in (names or known_construct_names()) if _normalize_name(name))
    entries: list[DitaConstructCoverage] = [
        coverage_for_construct(name, item_type="element") for name in construct_names
    ]
    if include_attributes:
        entries.extend(coverage_for_construct(name, item_type="attribute") for name in known_attribute_names())
    return DitaConstructCoverageReport(entries=tuple(entries))


def metadata_for_dita_construct(name: str, *, item_type: Literal["element", "attribute"] = "element") -> dict[str, str]:
    coverage = coverage_for_construct(name, item_type=item_type)
    return {
        "coverage_status": coverage.coverage_status,
        "example_source": coverage.example_source,
        "generation_strategy": coverage.generation_strategy,
        "publishing_source_policy": coverage.publishing_source_policy,
    }
