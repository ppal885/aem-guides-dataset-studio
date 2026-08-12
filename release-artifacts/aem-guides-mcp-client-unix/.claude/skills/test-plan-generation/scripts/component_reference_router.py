"""Route a Jira to the smallest deterministic test-plan reference pack."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "test-plan-reference-routing-v1"
CANONICAL_COMPONENTS = (
    "Editor",
    "Authoring",
    "Publishing",
    "Platform",
    "Schematron",
    "Integration",
)
_CAUTION_RESOLUTIONS = {
    "duplicate",
    "working as designed",
    "won't do",
    "won't fix",
    "not a bug",
    "rejected",
    "deferred",
    "question answered",
}
_COMPONENT_PATTERNS = {
    "Editor": re.compile(
        r"\b(?:web\s+editor|xml\s+editor|author\s+view|source\s+view|markup\s+editor|ckeditor|caret|cursor)\b",
        re.I,
    ),
    "Authoring": re.compile(
        r"\b(?:xref|cross[-\s]?reference|ditamap|map\s+reference|topic|image\s+files?|thumbnail|"
        r"repository\s+content\s+view|search\s+panel|asset\s+picker|file\s+browser)\b",
        re.I,
    ),
    "Publishing": re.compile(r"\b(?:native\s+pdf|aem\s+sites?|html5|dita[-\s]?ot|publish|output\s+preset)\b", re.I),
    "Platform": re.compile(r"\b(?:asset\s+processing|repository|dam|jcr|oak|index|workflow|api)\b", re.I),
    "Schematron": re.compile(r"\b(?:schematron|\.sch\b|validation\s+rule)\b", re.I),
    "Integration": re.compile(r"\b(?:translation|figma|external\s+system|connector|integration|konnect)\b", re.I),
}
_THUMBNAIL_RE = re.compile(
    r"\b(?:thumbnail|home\s+repository\s+content\s+view|bottom\s+search\s+panel|lazy[-\s]?loading|layout\s+jank)\b",
    re.I,
)
_MULTI_SELECTION_RE = re.compile(r"\bmulti[-\s]?selection\b|\bselect\s+multiple\s+images?\b", re.I)
_XREF_MAP_RE = re.compile(r"\b(?:xref|cross[-\s]?reference)\b", re.I)
_MAP_RE = re.compile(r"\b(?:map|ditamap)\b", re.I)
_DISPLAY_NAME_RE = re.compile(r"\b(?:title|file\s*name|filename|display)\b", re.I)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _canonical_component(value: Any) -> str:
    normalized = _clean(value).casefold()
    for component in CANONICAL_COMPONENTS:
        if normalized == component.casefold():
            return component
    return ""


def _detect_mechanisms(text: str) -> tuple[str, ...]:
    mechanisms: list[str] = []
    if _THUMBNAIL_RE.search(text):
        mechanisms.append("asset_browser_thumbnail")
    if _MULTI_SELECTION_RE.search(text):
        mechanisms.append("asset_picker_multi_selection")
    if _XREF_MAP_RE.search(text) and _MAP_RE.search(text) and _DISPLAY_NAME_RE.search(text):
        mechanisms.append("xref_map_display_label")
    return tuple(mechanisms)


def _infer_component(
    *,
    acceptance_criteria: str,
    summary: str,
    description: str,
) -> tuple[str, str]:
    for source, text in (
        ("jira_acceptance_field", acceptance_criteria),
        ("jira_summary", summary),
        ("jira_description", description),
    ):
        matches = [
            component
            for component, pattern in _COMPONENT_PATTERNS.items()
            if pattern.search(text)
        ]
        if matches:
            if "Authoring" in matches:
                return "Authoring", source
            return matches[0], source
    return "", "unclassified"


def route_references(
    *,
    component: str = "",
    summary: str = "",
    description: str = "",
    acceptance_criteria: str = "",
    resolution: str = "",
    labels: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    accepted_text = _clean(acceptance_criteria)
    summary_text = _clean(summary)
    description_text = _clean(description)
    explicit_component = _canonical_component(component)
    if explicit_component:
        primary_component = explicit_component
        component_source = "jira_component"
    else:
        primary_component, component_source = _infer_component(
            acceptance_criteria=accepted_text,
            summary=summary_text,
            description=description_text,
        )

    authoritative_scope = accepted_text or "\n".join(
        part for part in (summary_text, description_text) if part
    )
    mechanisms = _detect_mechanisms(authoritative_scope)
    description_mechanisms = _detect_mechanisms(description_text)
    warnings: list[str] = []
    if accepted_text and description_mechanisms and not set(mechanisms) & set(description_mechanisms):
        warnings.append("accepted_uac_overrides_description_scope")
    if (
        accepted_text
        and "asset_browser_thumbnail" in mechanisms
        and "asset_picker_multi_selection" in description_mechanisms
    ):
        warnings.append("stale_multi_selection_request_is_not_thumbnail_uac")

    normalized_resolution = _clean(resolution).casefold()
    if not accepted_text:
        warnings.append("accepted_uac_missing")
    if not accepted_text and normalized_resolution in _CAUTION_RESOLUTIONS:
        warnings.append("caution_resolution_without_uac_is_proposed_only")

    references = ["references/component-routing.md"]
    if primary_component == "Authoring":
        references.append("references/component-authoring.md")
        load_full_reference = False
    else:
        references.append("references/uac-reference-examples.md")
        load_full_reference = True

    accepted_labels = {
        re.sub(r"[^a-z0-9]+", "", _clean(label).casefold()) for label in labels
    }
    accepted_label_present = bool(
        accepted_labels & {"uacdone", "uacapproved", "uacaccepted", "uacverified"}
    )
    if accepted_text:
        scope_mode = "accepted_field_primary" if accepted_label_present else "jira_field_requires_acceptance_check"
    elif normalized_resolution in _CAUTION_RESOLUTIONS:
        scope_mode = "proposed_only"
    else:
        scope_mode = "description_candidate"

    return {
        "schema_version": SCHEMA_VERSION,
        "primary_component": primary_component,
        "component_source": component_source,
        "mechanisms": list(mechanisms),
        "scope_mode": scope_mode,
        "accepted_uac_present": bool(accepted_text),
        "accepted_label_present": accepted_label_present,
        "references": references,
        "load_full_uac_reference": load_full_reference,
        "warnings": list(dict.fromkeys(warnings)),
    }


def _load_input(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.casefold() == ".json":
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("Input JSON must be an object")
        return payload
    return {"description": text}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--component", default="")
    parser.add_argument("--summary", default="")
    parser.add_argument("--resolution", default="")
    parser.add_argument("--label", action="append", default=[])
    args = parser.parse_args()
    payload = _load_input(args.input)
    routed = route_references(
        component=args.component or payload.get("component", ""),
        summary=args.summary or payload.get("summary", ""),
        description=payload.get("description", ""),
        acceptance_criteria=payload.get("acceptance_criteria", ""),
        resolution=args.resolution or payload.get("resolution", ""),
        labels=[*payload.get("labels", []), *args.label],
    )
    rendered = json.dumps(routed, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
