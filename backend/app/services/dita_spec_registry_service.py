"""Structured DITA spec registry built from the local seed corpus.

This service provides a normalized element-focused view over the mixed
seed entries so spec tools can answer from merged facts instead of a
single matching chunk.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.dita_attribute_catalog import list_attribute_names

SEED_PATH = Path(__file__).resolve().parent.parent / "storage" / "dita_spec_seed.json"
_FENCED_XML_BLOCK_RE = re.compile(r"```(?:xml)?\s*\r?\n(.*?)```", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class DitaElementSpec:
    """Normalized element-level DITA spec facts."""

    name: str
    description: str
    source_url: str
    parent_element: str
    allowed_children: list[str]
    allowed_parents: list[str]
    supported_attributes: list[str]
    attribute_usage: dict[str, str]
    usage_contexts: list[str]
    common_mistakes: list[str]
    correct_examples: list[str]


def _load_seed() -> list[dict[str, Any]]:
    try:
        with open(SEED_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _normalize_name(text: Any) -> str:
    return str(text or "").strip().strip("<>").replace("_", "-").lower()


# Seed entries sometimes use suffixes like ``fig_element`` → ``fig-element``. Merge those into the base element key.
_CANONICAL_ELEMENT_KEYS: dict[str, str] = {
    "fig-element": "fig",
    "figgroup-element": "figgroup",
}


def canonical_element_name(name: str) -> str:
    """Map alternate seed element_name values onto the primary registry key."""
    normalized = _normalize_name(name)
    return _CANONICAL_ELEMENT_KEYS.get(normalized, normalized)


def _normalize_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _parse_children(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return _normalize_string_list(raw)
    if isinstance(raw, tuple):
        return _normalize_string_list(list(raw))
    if not isinstance(raw, str):
        raw = str(raw)
    if not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
        return _normalize_string_list(parsed if isinstance(parsed, list) else [])
    except json.JSONDecodeError:
        # Seed sometimes stores children as comma-separated text, e.g. "title, desc, figgroup, image".
        parts = re.split(r"[\s,]+", raw.strip()) if raw.strip() else []
        cleaned: list[str] = []
        for part in parts:
            p = part.strip().strip("<>").strip()
            if p and p not in cleaned:
                cleaned.append(p)
        return cleaned


def _parse_attributes(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {
            str(key).strip(): str(value).strip()
            for key, value in raw.items()
            if str(key).strip()
        }
    if not isinstance(raw, str):
        raw = str(raw)
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {
                str(key).strip(): str(value).strip()
                for key, value in parsed.items()
                if str(key).strip()
            }
    except json.JSONDecodeError:
        return {}
    return {}


def _looks_like_element_entry(entry: dict[str, Any], attribute_names: set[str]) -> bool:
    raw_name = str(entry.get("element_name") or "").strip()
    if not raw_name:
        return False
    normalized = _normalize_name(raw_name)
    content_type = str(entry.get("content_type") or "").strip().lower()
    if raw_name.endswith("_attribute") or content_type == "attribute":
        return False
    if normalized in attribute_names and content_type != "element":
        return False
    return True


def _dedupe_list(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _extract_xml_examples(text: Any) -> list[str]:
    if not isinstance(text, str) or not text.strip():
        return []
    examples = [
        " ".join(match.group(1).strip().split())
        for match in _FENCED_XML_BLOCK_RE.finditer(text)
        if match.group(1).strip()
    ]
    return _dedupe_list(examples)


def _registry_overrides() -> dict[str, dict[str, Any]]:
    """Provide structured coverage for important elements missing from the seed."""
    return {
        "ditavalref": {
            "name": "ditavalref",
            "description": (
                "<ditavalref> applies a DITAVAL file to the parent map branch for branch filtering. "
                "Inside <ditavalref>, DITA uses <ditavalmeta> for branch-filter metadata such as "
                "<dvrResourceSuffix>, <dvrResourcePrefix>, <dvrKeyscopeSuffix>, and <dvrKeyscopePrefix>."
            ),
            "source_url": "",
            "parent_element": "topicref",
            "allowed_children": ["ditavalmeta"],
            "supported_attributes": ["href"],
            "attribute_usage": {
                "href": "References the DITAVAL file applied to the parent branch."
            },
            "usage_contexts": [
                "Use <ditavalref> inside a map branch when different branches need different conditional filtering.",
                "Branch filtering is a DITA 1.3 map feature rather than a topic-body structure.",
            ],
            "common_mistakes": [
                "Applying <ditavalref> at the map root instead of a specific branch.",
                "Repeating the same topic in filtered branches without a resource suffix or prefix, which can cause output filename conflicts.",
            ],
            "correct_examples": [
                "<topicref href=\"installation.dita\"><ditavalref href=\"ditaval/windows.ditaval\"><ditavalmeta><dvrResourceSuffix>-win</dvrResourceSuffix></ditavalmeta></ditavalref></topicref>",
            ],
        },
        "topichead": {
            "name": "topichead",
            "description": (
                "<topichead> is a title-only container in a DITA map. It creates a navigation heading "
                "without pointing to a topic file."
            ),
            "source_url": "https://dita-lang.org/dita/langref/base/topichead",
            "parent_element": "map",
            "allowed_children": ["topicmeta", "topicref", "topichead", "topicgroup"],
            "supported_attributes": ["navtitle", "keys", "processing-role", "toc", "linking"],
            "attribute_usage": {
                "navtitle": "Provides the navigation title for the topichead.",
                "toc": "Controls whether the topichead participates in navigation/TOC processing.",
            },
            "usage_contexts": [
                "Use <topichead> when a map needs a visible grouping heading but no standalone topic file.",
                "Place child <topicref> elements under the <topichead> to create the grouped navigation branch.",
            ],
            "common_mistakes": [
                "Adding @href to <topichead>; use <topicref> when the map entry points to a topic.",
                "Expecting <topichead> to contain topic body content.",
            ],
            "correct_examples": [
                "<map>\n  <title>Operations Guide</title>\n  <topichead navtitle=\"Cluster operations\">\n    <topicref href=\"start-cluster.dita\"/>\n    <topicref href=\"stop-cluster.dita\"/>\n  </topichead>\n</map>",
            ],
        },
        "indextermref": {
            "name": "indextermref",
            "description": (
                "<indextermref> is an empty (content-free) element used to add a page-number reference to an "
                "existing index entry elsewhere in the document, without generating a new, separate index entry "
                "at the point of reference. It targets an index term via @keyref rather than duplicating the term.\n\n"
                "Status varies by DITA version and is not fully consistent: the DITA 1.0 language specification "
                "documents this purpose explicitly but simultaneously states @keyref on <indextermref> is 'not "
                "currently implemented' and the element is 'not currently supported in DITA processing', flagging "
                "possible future deprecation. Later element-reference pages describe it with a reserved/placeholder "
                "status rather than a fully worked-out content model. Separately, the general DITA 1.2 key-reference "
                "processing architecture (which governs @keyref resolution broadly) lists <indextermref> alongside "
                "<indexterm> as one of the elements without @href, whose matching content — when it does carry a "
                "@keyref — is taken from <keyword>/<term> inside <keywords> inside the referenced key definition's "
                "<topicmeta>.\n\n"
                "Practical guidance: <indextermref> is rarely used in practice; most authors use <indexterm> "
                "directly for index entries. Actual support in DITA-OT or other specific processors was not "
                "verified in this session — treat runtime/processing behavior as unconfirmed rather than assumed."
            ),
            "source_url": "https://docs.oasis-open.org/dita/v1.0/langspec/indextermref.html",
            "parent_element": "",
            "allowed_children": [],
            "supported_attributes": ["keyref"],
            "attribute_usage": {
                "keyref": (
                    "Identifies the index term/key that should receive the page-number reference. "
                    "Documented in the DITA 1.0 spec as 'not currently implemented' at that time; "
                    "current processor support is unverified."
                ),
            },
            "usage_contexts": [
                "Use <indextermref> only when you specifically want to add a page number to an existing index "
                "entry without creating a second, separate index entry at the reference point.",
                "For ordinary indexing, use <indexterm> directly rather than <indextermref>.",
            ],
            "common_mistakes": [
                "Expecting <indextermref> to create a new visible index entry — it does not; it only contributes "
                "a page reference to an entry defined elsewhere.",
                "Assuming @keyref on <indextermref> is universally supported by all DITA processors — support has "
                "historically been inconsistent and should be verified against the specific toolchain in use.",
            ],
            "correct_examples": [
                "<p>Use <indextermref keyref=\"yellow\"/> lemon zest to add a tangy citrus flavor to the cake icing.</p>",
            ],
        },
        "indexlist": {
            "name": "indexlist",
            "description": (
                "<indexlist> is an empty marker element placed inside <booklists> (which itself sits in "
                "<frontmatter> or <backmatter> of a <bookmap>) telling the publishing processor to generate "
                "a back-of-book index at this location, built from the <indexterm> entries collected across "
                "all topics referenced by the bookmap.\n\n"
                "It is one of several sibling marker elements inside <booklists> — <toc>, <indexlist>, "
                "<figurelist>, <tablelist>, <glossarylist>, <bibliolist>, <booklist>, <trademarklist>, "
                "<abbrevlist> — each triggering generation of a different auto-compiled list/index.\n\n"
                "If @href is omitted, the processor generates the index content automatically (this is the "
                "normal usage — <indexlist/> as a self-closing empty element). @href instead points to a "
                "manually-authored listing topic, overriding auto-generation."
            ),
            "source_url": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/indexlist.html",
            "parent_element": "booklists",
            "allowed_children": [],
            "supported_attributes": ["navtitle", "href"],
            "attribute_usage": {
                "navtitle": (
                    "Title for the generated index as it appears in navigation/TOC. DITA 1.2+ prefers "
                    "specifying this via <navtitle> inside <topicmeta> instead of the @navtitle attribute."
                ),
                "href": (
                    "Points to a manually-authored index listing topic. If omitted, the processor "
                    "auto-generates the index from <indexterm> entries collected across the bookmap "
                    "(the normal, most common usage)."
                ),
            },
            "usage_contexts": [
                "Place <indexlist/> inside <booklists> under <backmatter> to generate a traditional "
                "back-of-book index in Native PDF / DITA-OT PDF bookmap output.",
                "Leave @href unset for auto-generation from <indexterm> entries; only set @href when "
                "substituting a manually-authored index listing.",
            ],
            "common_mistakes": [
                "Expecting <indexlist> alone (without any <indexterm> entries in the referenced topics) "
                "to produce a non-empty index — it only compiles what indexterm entries actually exist.",
                "Placing <indexlist> directly under <backmatter> instead of inside <booklists> — it is "
                "only a valid child of <booklists>, not of <frontmatter>/<backmatter> directly.",
            ],
            "correct_examples": [
                "<bookmap>\n  <backmatter>\n    <booklists>\n      <indexlist/>\n    </booklists>\n  </backmatter>\n</bookmap>",
            ],
        },
        "toc": {
            "name": "toc",
            "description": (
                "<toc> is an empty marker element inside <booklists> telling the processor the author wants "
                "a table of contents generated at this location. If @href is omitted, the processor generates "
                "the TOC automatically from the bookmap's topicref structure. If @href references a topic or "
                "map, that becomes a manually-authored TOC substitute instead of auto-generation — the same "
                "auto-vs-manual pattern used by every other <booklists> child (<indexlist>, <tablelist>, etc.)."
            ),
            "source_url": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/toc.html",
            "parent_element": "booklists",
            "allowed_children": [],
            "supported_attributes": ["navtitle", "href"],
            "attribute_usage": {
                "href": (
                    "Points to a topic/map containing a manually-authored TOC. Omit it (use <toc/>) for "
                    "processor auto-generation from the bookmap's topicref structure — the normal usage."
                ),
                "navtitle": "Title for the generated TOC as it appears in navigation.",
            },
            "usage_contexts": [
                "Place <toc/> inside <booklists> (commonly in <frontmatter>) for an auto-generated table of "
                "contents in Native PDF / DITA-OT PDF bookmap output.",
            ],
            "common_mistakes": [
                "Confusing this bookmap <toc> marker element with the map-level @toc attribute (which "
                "controls whether an individual topicref appears in the generated TOC) — they are unrelated.",
            ],
            "correct_examples": [
                "<bookmap>\n  <frontmatter>\n    <booklists>\n      <toc/>\n    </booklists>\n  </frontmatter>\n</bookmap>",
            ],
        },
        "tablelist": {
            "name": "tablelist",
            "description": (
                "<tablelist> is an empty marker element inside <booklists> telling the processor the author "
                "wants a list of tables generated at this location, compiled from <table>/<simpletable> "
                "titles across the bookmap's referenced topics. Same auto-vs-manual @href pattern as its "
                "<booklists> siblings (<toc>, <indexlist>, <figurelist>, etc.)."
            ),
            "source_url": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/tablelist.html",
            "parent_element": "booklists",
            "allowed_children": [],
            "supported_attributes": ["navtitle", "href"],
            "attribute_usage": {
                "href": "Points to a manually-authored list-of-tables topic; omit for auto-generation.",
                "navtitle": "Title for the generated list as it appears in navigation.",
            },
            "usage_contexts": [
                "Place <tablelist/> inside <booklists> (commonly in <backmatter>) to generate a list of "
                "tables in Native PDF / DITA-OT PDF bookmap output.",
            ],
            "common_mistakes": [
                "Expecting <tablelist> to produce entries for tables that have no <title> — only titled "
                "tables/simpletables typically appear in the generated listing.",
            ],
            "correct_examples": [
                "<bookmap>\n  <backmatter>\n    <booklists>\n      <tablelist/>\n    </booklists>\n  </backmatter>\n</bookmap>",
            ],
        },
        "glossarylist": {
            "name": "glossarylist",
            "description": (
                "<glossarylist> is an empty marker element inside <booklists> telling the processor the "
                "author wants a list of glossary entries generated at this location, compiled from "
                "<glossentry>/<glossgroup> content referenced by the bookmap. Same auto-vs-manual @href "
                "pattern as its <booklists> siblings."
            ),
            "source_url": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/glossarylist.html",
            "parent_element": "booklists",
            "allowed_children": [],
            "supported_attributes": ["navtitle", "href"],
            "attribute_usage": {
                "href": "Points to a manually-authored glossary list topic; omit for auto-generation.",
                "navtitle": "Title for the generated glossary list as it appears in navigation.",
            },
            "usage_contexts": [
                "Place <glossarylist/> inside <booklists> (commonly in <backmatter>) to generate a glossary "
                "list in Native PDF / DITA-OT PDF bookmap output, alongside referenced <glossentry> topics.",
            ],
            "common_mistakes": [
                "Adding <glossarylist> without actually referencing any <glossentry>/<glossgroup> topics in "
                "the bookmap — the generated list will be empty.",
            ],
            "correct_examples": [
                "<bookmap>\n  <backmatter>\n    <booklists>\n      <glossarylist/>\n    </booklists>\n  </backmatter>\n</bookmap>",
            ],
        },
        "trademarklist": {
            "name": "trademarklist",
            "description": (
                "<trademarklist> is an empty marker element inside <booklists> telling the processor the "
                "author wants a list of trademarks generated at this location. Unlike most <booklists> "
                "siblings, auto-generation from <tm> markup is less commonly implemented — @href pointing "
                "to a manually-authored trademark listing is the more typical/reliable usage."
            ),
            "source_url": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/trademarklist.html",
            "parent_element": "booklists",
            "allowed_children": [],
            "supported_attributes": ["navtitle", "href"],
            "attribute_usage": {
                "href": (
                    "Points to a manually-authored list-of-trademarks topic. If specified, an external "
                    "processor may generate the list at this location; auto-generation without @href is "
                    "less reliably supported than for siblings like <toc>/<indexlist> — verify against the "
                    "actual product/processor rather than assuming parity."
                ),
                "navtitle": "Title for the generated trademark list as it appears in navigation.",
            },
            "usage_contexts": [
                "Place <trademarklist href=\"listoftrademarks.dita\"/> inside <booklists> (commonly in "
                "<backmatter>) alongside <indexlist/> for a manually-authored trademark list — the spec's "
                "own worked example pairs these two directly.",
            ],
            "common_mistakes": [
                "Assuming <trademarklist/> (no @href) auto-generates reliably the same way <toc/> or "
                "<indexlist/> do — trademark-list auto-generation support is less consistent; validate "
                "actual product behavior against the applicable DITA specification and supported AEM "
                "Guides implementation.",
            ],
            "correct_examples": [
                "<bookmap>\n  <backmatter>\n    <booklists>\n      <trademarklist href=\"listoftrademarks.dita\"/>\n      <indexlist/>\n    </booklists>\n  </backmatter>\n</bookmap>",
            ],
        },
        "topicgroup": {
            "name": "topicgroup",
            "description": (
                "<topicgroup> is a non-titled grouping element in a DITA map. It organizes child "
                "<topicref> branches without creating its own visible heading or linked topic."
            ),
            "source_url": "https://dita-lang.org/dita/langref/base/topicgroup",
            "parent_element": "map",
            "allowed_children": ["topicmeta", "topicref", "topichead", "topicgroup"],
            "supported_attributes": ["collection-type", "processing-role", "toc", "linking"],
            "attribute_usage": {
                "collection-type": "Can express relationship behavior for the grouped branch.",
                "processing-role": "Can influence whether grouped references are normal content or resource-only.",
                "toc": "Can influence whether descendants participate in navigation when supported by the processor.",
                "linking": "Can control relationship-link behavior for the grouped branch.",
            },
            "usage_contexts": [
                "Use <topicgroup> when map branches need invisible structural grouping rather than a displayed heading.",
                "In PDF or web output, child <topicref> entries drive the visible content and navigation; <topicgroup> itself should not become a standalone heading.",
                "Use <topichead> instead when the output needs a visible grouping label in navigation or a TOC.",
            ],
            "common_mistakes": [
                "Expecting <topicgroup> to create a PDF heading or TOC entry.",
                "Using <topicgroup> when a visible navigation label is required; use <topichead> for that case.",
                "Putting topic body content directly inside <topicgroup>; it belongs in referenced topic files.",
            ],
            "correct_examples": [
                "<map>\n  <title>Operations Guide</title>\n  <topicref href=\"overview.dita\"/>\n  <topicgroup>\n    <topicref href=\"start-cluster.dita\"/>\n    <topicref href=\"stop-cluster.dita\"/>\n  </topicgroup>\n</map>",
            ],
        },
    }


@lru_cache(maxsize=1)
def _build_registry() -> dict[str, DitaElementSpec]:
    attribute_names = set(list_attribute_names())
    merged: dict[str, dict[str, Any]] = {}

    for entry in _load_seed():
        if not isinstance(entry, dict) or not _looks_like_element_entry(entry, attribute_names):
            continue

        raw_name = str(entry.get("element_name") or "").strip()
        normalized = canonical_element_name(_normalize_name(raw_name))
        if not normalized:
            continue

        record = merged.setdefault(
            normalized,
            {
                "name": normalized,
                "description": "",
                "source_url": "",
                "parent_element": "",
                "allowed_children": [],
                "supported_attributes": [],
                "attribute_usage": {},
                "usage_contexts": [],
                "common_mistakes": [],
                "correct_examples": [],
            },
        )

        text_content = str(entry.get("text_content") or "").strip()
        if len(text_content) > len(record["description"]):
            record["description"] = text_content

        meta = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        source_url = str(entry.get("source_url") or meta.get("source_url") or "").strip()
        if source_url and not record["source_url"]:
            record["source_url"] = source_url

        parent_element = str(entry.get("parent_element") or "").strip()
        if parent_element and not record["parent_element"]:
            record["parent_element"] = parent_element

        record["allowed_children"].extend(_parse_children(entry.get("children_elements")))
        attribute_usage = _parse_attributes(entry.get("attributes"))
        record["attribute_usage"].update(attribute_usage)
        record["supported_attributes"].extend(attribute_usage.keys())
        record["usage_contexts"].extend(_normalize_string_list(entry.get("usage_contexts")))
        record["common_mistakes"].extend(_normalize_string_list(entry.get("common_mistakes")))
        record["correct_examples"].extend(_normalize_string_list(entry.get("correct_examples")))
        record["correct_examples"].extend(_extract_xml_examples(text_content))

    for normalized, override in _registry_overrides().items():
        record = merged.setdefault(
            normalized,
            {
                "name": normalized,
                "description": "",
                "source_url": "",
                "parent_element": "",
                "allowed_children": [],
                "supported_attributes": [],
                "attribute_usage": {},
                "usage_contexts": [],
                "common_mistakes": [],
                "correct_examples": [],
            },
        )
        if override.get("description"):
            record["description"] = str(override.get("description") or "").strip()
        if override.get("source_url"):
            record["source_url"] = str(override.get("source_url") or "").strip()
        if override.get("parent_element"):
            record["parent_element"] = str(override.get("parent_element") or "").strip()
        record["allowed_children"].extend(_normalize_string_list(override.get("allowed_children")))
        attribute_usage = override.get("attribute_usage") or {}
        if isinstance(attribute_usage, dict):
            record["attribute_usage"].update(
                {
                    str(key).strip(): str(value).strip()
                    for key, value in attribute_usage.items()
                    if str(key).strip()
                }
            )
        record["supported_attributes"].extend(
            _normalize_string_list(override.get("supported_attributes"))
        )
        record["usage_contexts"].extend(_normalize_string_list(override.get("usage_contexts")))
        record["common_mistakes"].extend(_normalize_string_list(override.get("common_mistakes")))
        record["correct_examples"].extend(_normalize_string_list(override.get("correct_examples")))

    reverse_parents: dict[str, list[str]] = {}
    for element_name, record in merged.items():
        explicit_parent = _normalize_name(record["parent_element"])
        if explicit_parent and explicit_parent in merged:
            reverse_parents.setdefault(element_name, []).append(explicit_parent)
        for child in record["allowed_children"]:
            child_name = _normalize_name(child)
            if child_name:
                reverse_parents.setdefault(child_name, []).append(element_name)

    registry: dict[str, DitaElementSpec] = {}
    for element_name, record in merged.items():
        registry[element_name] = DitaElementSpec(
            name=record["name"],
            description=str(record["description"] or "").strip(),
            source_url=str(record["source_url"] or "").strip(),
            parent_element=str(record["parent_element"] or "").strip(),
            allowed_children=_dedupe_list(record["allowed_children"]),
            allowed_parents=_dedupe_list(reverse_parents.get(element_name, [])),
            supported_attributes=_dedupe_list(record["supported_attributes"]),
            attribute_usage=dict(record["attribute_usage"]),
            usage_contexts=_dedupe_list(record["usage_contexts"]),
            common_mistakes=_dedupe_list(record["common_mistakes"]),
            correct_examples=_dedupe_list(record["correct_examples"]),
        )
    return registry


def list_element_names() -> tuple[str, ...]:
    """Return normalized DITA element names available in the registry."""
    return tuple(sorted(_build_registry().keys()))


def get_element_spec(name: str) -> DitaElementSpec | None:
    """Return a normalized element spec entry."""
    normalized = canonical_element_name(_normalize_name(name))
    if not normalized:
        return None
    return _build_registry().get(normalized)
