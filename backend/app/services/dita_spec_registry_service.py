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
