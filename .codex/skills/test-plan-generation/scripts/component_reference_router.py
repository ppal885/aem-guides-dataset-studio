"""Route a Jira to the smallest deterministic test-plan reference pack."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "test-plan-reference-routing-v9"
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
    "cannot reproduce",
    "canceled",
    "no longer applies",
    "transfer to product",
}
_COMPONENT_PATTERNS = {
    "Editor": re.compile(
        r"\b(?:web\s+editor|xml\s+editor|author\s+view|source\s+view|markup\s+editor|ckeditor|caret|cursor)\b",
        re.I,
    ),
    "Authoring": re.compile(
        r"\b(?:xref|cross[-\s]?reference|ditamap|map\s+reference|topic|image\s+files?|thumbnail|"
        r"repository\s+content\s+view|search\s+panel|asset\s+picker|file\s+browser|map\s+view|"
        r"explorer(?:\s+(?:panel|view))?|selection\s+count|child\s+nodes?|"
        r"folder\s+delet(?:e|ion)|delet(?:e|ing)\s+(?:a\s+)?folder)\b",
        re.I,
    ),
    "Publishing": re.compile(r"\b(?:native\s+pdf|aem\s+sites?|html5|dita[-\s]?ot|publish|output\s+preset)\b", re.I),
    "Platform": re.compile(r"\b(?:asset\s+processing|repository|dam|jcr|oak|index|workflow|api)\b", re.I),
    "Schematron": re.compile(r"\b(?:schematron|\.sch\b|validation\s+rule)\b", re.I),
    "Integration": re.compile(r"\b(?:translation|figma|external[-\s]+system|connector|integration|konnect)\b", re.I),
}
_THUMBNAIL_RE = re.compile(
    r"\b(?:thumbnail|home\s+repository\s+content\s+view|bottom\s+search\s+panel|lazy[-\s]?loading|layout\s+jank)\b",
    re.I,
)
_MULTI_SELECTION_RE = re.compile(r"\bmulti[-\s]?selection\b|\bselect\s+multiple\s+images?\b", re.I)
_XREF_MAP_RE = re.compile(r"\b(?:xref|cross[-\s]?reference)\b", re.I)
_MAP_RE = re.compile(r"\b(?:map|ditamap)\b", re.I)
_DISPLAY_NAME_RE = re.compile(r"\b(?:title|file\s*name|filename|display)\b", re.I)
_MAP_VIEW_SELECTION_COUNT_RE = re.compile(
    r"\bmap\s+view\b[^.\n]{0,260}\b(?:selected|selection\s+count|total\s+(?:number\s+of\s+)?"
    r"(?:items?|maps?|nodes?)\s+selected|child\s+nodes?|descendant\s+nodes?)\b|"
    r"\b(?:selected|selection\s+count|child\s+nodes?|descendant\s+nodes?)\b[^.\n]{0,180}\bmap\s+view\b",
    re.I,
)
_CRUD_API_OPERATION_RE = re.compile(
    r"\b(?:crud\s+apis?|create\s+api|update\s+(?:api|call)|api\s+to\s+(?:create|update))\b",
    re.I,
)
_CRUD_API_CONTRACT_RE = re.compile(
    r"\b(?:assets?|topics?|editor\s*data|file\s*content|metadata|guid|upsert|force\s+creation|"
    r"external[-\s]+system|human[-\s]?readable\s+file\s*names?)\b",
    re.I,
)
_BULK_ASSET_OVERWRITE_OPERATION_RE = re.compile(
    r"\b(?:overwrite|re[-\s]?upload|upload(?:ing|ed)?\s+(?:the\s+)?same|same[-\s]?name\s+assets?|"
    r"bulk\s+(?:asset\s+)?upload)\b",
    re.I,
)
_BULK_ASSET_OVERWRITE_CONTEXT_RE = re.compile(
    r"\b(?:assets?|files?|batch|200\+?|two\s+hundred)\b|/bin/fmdita/import\b",
    re.I,
)
_BULK_ASSET_OVERWRITE_FAILURE_RE = re.compile(
    r"\b(?:forced?\s+logout|redirect(?:ed|s)?\s+to\s+(?:the\s+)?login|"
    r"(?:indefinite|stuck)\s+(?:loader|loading|pending)|generic\s+error|csrf(?:\s+token)?)\b",
    re.I,
)
_EXPLORER_SORT_RE = re.compile(
    r"\b(?:web\s+editor\s+)?explorer(?:\s+(?:panel|view))?\b[^.\n]{0,320}"
    r"\b(?:sort(?:ed|ing)?|alphabetic(?:al|ally)?|order(?:ed|ing)?|ascending|descending)\b|"
    r"\b(?:sort(?:ed|ing)?|alphabetic(?:al|ally)?|order(?:ed|ing)?|ascending|descending)\b"
    r"[^.\n]{0,220}\b(?:web\s+editor\s+)?explorer(?:\s+(?:panel|view))?\b",
    re.I,
)
_EXPLORER_IMPLICIT_SORT_RE = re.compile(
    r"\b(?:honou?rs?|use|follow)\b[^.\n]{0,180}\bdisplay\s+preference\b"
    r"[^.\n]{0,180}\b(?:sort|order|sort\s+key)\b|"
    r"\b(?:file\s*name|filename|title)\b[^.\n]{0,180}\b(?:default\s+sort\s+key|sort\s+alphabetically)\b",
    re.I,
)
_EXPLORER_EXPLICIT_SORT_RE = re.compile(
    r"\b(?:explicit|user[-\s]?selectable|per[-\s]?user)\b[^.\n]{0,160}\bsort\s+controls?\b|"
    r"\bsort\s+controls?\b[^.\n]{0,180}\b(?:name|title|asc(?:ending)?|desc(?:ending)?)\b",
    re.I,
)
_EXPLORER_EXPLICIT_SORT_DESIGN_RE = re.compile(
    r"\bexplorer\s+header\b[^.\n]{0,180}\b(?:dedicated|standalone|independent)\s+sort\b|"
    r"\bsort\s+(?:icon|action|affordance|button)\b[^.\n]{0,180}"
    r"\b(?:right\s+of|beside|next\s+to)\b[^.\n]{0,80}\b(?:search|add)\b",
    re.I,
)
_EXPLORER_SORT_FEATURE_FLAG_RE = re.compile(r"\bfeature\s+flag\b", re.I)
_EXPLORER_SORT_FLAG_STATE_MATRIX_RE = re.compile(
    r"\bfeature\s+flag\b[^.\n]{0,180}\b(?:off|disabled)\b[^.\n]{0,100}\b(?:on|enabled)\b|"
    r"\bfeature\s+flag\b[^.\n]{0,180}\b(?:on|enabled)\b[^.\n]{0,100}\b(?:off|disabled)\b",
    re.I,
)
_EXPLORER_SORT_FLAG_KEY_RE = re.compile(
    r"\bfeature\s+flag(?:\s+(?:key|name))?\s*(?:is|=|:)?\s*`?[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+`?\b"
)
_EXPLORER_SORT_FLAG_DEFAULT_RE = re.compile(
    r"\bfeature\s+flag\b[^.\n]{0,140}\bdefault(?:\s+value)?\s*(?:is|=|:)?\s*"
    r"(?:true|false|on|off|enabled|disabled)\b|"
    r"\bdefault(?:\s+value)?\s*(?:is|=|:)?\s*(?:true|false|on|off|enabled|disabled)\b"
    r"[^.\n]{0,100}\bfeature\s+flag\b",
    re.I,
)
_EXPLORER_SORT_OFF_PRESENTATION_RE = re.compile(
    r"\b(?:feature\s+)?flag\s+(?:is\s+)?(?:off|disabled)\b[^.\n]{0,180}"
    r"\b(?:sort\s+)?(?:button|control|action|icon)\b[^.\n]{0,100}"
    r"\b(?:hidden|omitted|absent|disabled|not\s+(?:shown|visible)|unavailable)\b|"
    r"\b(?:sort\s+)?(?:button|control|action|icon)\b[^.\n]{0,120}"
    r"\b(?:hidden|omitted|absent|disabled|not\s+(?:shown|visible)|unavailable)\b[^.\n]{0,120}"
    r"\b(?:feature\s+)?flag\s+(?:is\s+)?(?:off|disabled)\b",
    re.I,
)
_EXPLORER_SORT_DEFAULT_STATE_REQUEST_RE = re.compile(
    r"\b(?:default|initial|first[-\s]?render)\b[^.\n]{0,100}"
    r"\b(?:sort\s+)?(?:button|control|action|icon)\b[^.\n]{0,80}\bstate\b|"
    r"\b(?:sort\s+)?(?:button|control|action|icon)\b[^.\n]{0,100}"
    r"\b(?:default|initial|first[-\s]?render)\s+state\b",
    re.I,
)
_EXPLORER_SORT_DEFAULT_STATE_VALUE_RE = re.compile(
    r"\b(?:default|initial|first[-\s]?render)\b[^.\n]{0,100}"
    r"\b(?:sort\s+)?(?:button|control|action|icon)\b[^.\n]{0,100}"
    r"\b(?:visible|hidden|enabled|disabled|active|inactive|selected|unselected)\b|"
    r"\b(?:sort\s+)?(?:button|control|action|icon)\b[^.\n]{0,100}"
    r"\b(?:visible|hidden|enabled|disabled|active|inactive|selected|unselected)\b"
    r"[^.\n]{0,100}\b(?:default|initial|first[-\s]?render)\b",
    re.I,
)
_FOLDER_DELETION_RE = re.compile(
    r"\bfolder\s+delet(?:e|ion)\b|\bdelet(?:e|ing)\s+(?:a\s+)?folders?\b",
    re.I,
)
_FOLDER_RESTORE_RE = re.compile(
    r"\b(?:restore\s+(?:a\s+)?folders?|trash(?:\s+can)?|recycle\s+bin)\b",
    re.I,
)
_CONDITIONAL_ATTRIBUTE_CONFIG_PATH_RE = re.compile(
    r"(?:/libs/fmdita/config/)?condattrlist(?:\.csv)?",
    re.I,
)
_CONDITIONAL_ATTRIBUTE_RE = re.compile(
    r"\b(?:condition(?:al)?\s+attributes?|conditional\s+attribute(?:s)?)\b",
    re.I,
)
_ATTRIBUTE_FRIENDLY_NAME_RE = re.compile(
    r"\battributes?\b[^.\n]{0,180}\b(?:friendly\s+names?|display\s+labels?)\b|"
    r"\b(?:friendly\s+names?|display\s+labels?)\b[^.\n]{0,180}\battributes?\b",
    re.I,
)
_CONFIG_DRIVEN_ENUMERATION_RE = re.compile(
    r"\b(?:config(?:uration|ured)?|dynamically?|runtime|profile|csv|allowlist|whitelist)\b",
    re.I,
)
_CONDITIONAL_ATTRIBUTE_LABEL_OR_SURFACE_RE = re.compile(
    r"\b(?:friendly\s+names?|display\s+labels?|fallback|full\s+tags(?:\s+view)?|"
    r"condition(?:al)?\s+attributes?|right\s+panel)\b",
    re.I,
)
_ATTRIBUTE_LABEL_SURFACE_RE = re.compile(
    r"\b(?:full\s+tags(?:\s+view)?|condition(?:al)?\s+attributes?)\b",
    re.I,
)


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
    if _MAP_VIEW_SELECTION_COUNT_RE.search(text):
        mechanisms.append("map_view_hierarchy_selection_count")
    if _CRUD_API_OPERATION_RE.search(text) and _CRUD_API_CONTRACT_RE.search(text):
        mechanisms.append("asset_crud_api_contract")
    if (
        _BULK_ASSET_OVERWRITE_OPERATION_RE.search(text)
        and _BULK_ASSET_OVERWRITE_CONTEXT_RE.search(text)
        and _BULK_ASSET_OVERWRITE_FAILURE_RE.search(text)
    ):
        mechanisms.append("bulk_asset_overwrite_session")
    if _EXPLORER_SORT_RE.search(text):
        mechanisms.append("explorer_filename_title_sorting")
    if _FOLDER_DELETION_RE.search(text):
        mechanisms.append("folder_deletion")
    if (
        _CONDITIONAL_ATTRIBUTE_CONFIG_PATH_RE.search(text)
        or (
            _CONDITIONAL_ATTRIBUTE_RE.search(text)
            and _CONFIG_DRIVEN_ENUMERATION_RE.search(text)
            and _CONDITIONAL_ATTRIBUTE_LABEL_OR_SURFACE_RE.search(text)
        )
        or (
            _ATTRIBUTE_FRIENDLY_NAME_RE.search(text)
            and _ATTRIBUTE_LABEL_SURFACE_RE.search(text)
        )
    ):
        mechanisms.append("config_driven_conditional_attribute_labels")
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
        if (
            _BULK_ASSET_OVERWRITE_OPERATION_RE.search(text)
            and _BULK_ASSET_OVERWRITE_CONTEXT_RE.search(text)
            and _BULK_ASSET_OVERWRITE_FAILURE_RE.search(text)
        ):
            return "Platform", source
        matches = [
            component
            for component, pattern in _COMPONENT_PATTERNS.items()
            if pattern.search(text)
        ]
        if matches:
            if "Authoring" in matches:
                return "Authoring", source
            if (
                "Integration" in matches
                and _CRUD_API_OPERATION_RE.search(text)
                and _CRUD_API_CONTRACT_RE.search(text)
            ):
                return "Integration", source
            return matches[0], source
    return "", "unclassified"


def route_references(
    *,
    component: str = "",
    summary: str = "",
    description: str = "",
    acceptance_criteria: str = "",
    design_evidence: str = "",
    resolution: str = "",
    labels: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    accepted_text = _clean(acceptance_criteria)
    summary_text = _clean(summary)
    description_text = _clean(description)
    design_text = _clean(design_evidence)
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
    if not accepted_text and "asset_crud_api_contract" in mechanisms:
        warnings.append("crud_api_request_without_accepted_uac_is_proposed_only")
    if not accepted_text and "explorer_filename_title_sorting" in mechanisms:
        warnings.append("explorer_sort_request_without_accepted_uac_is_proposed_only")
    if not accepted_text and "bulk_asset_overwrite_session" in mechanisms:
        warnings.append("bulk_overwrite_without_accepted_uac_is_proposed_only")
    if not accepted_text and "folder_deletion" in mechanisms:
        warnings.append("folder_deletion_without_accepted_uac_is_proposed_only")
    if "config_driven_conditional_attribute_labels" in mechanisms:
        warnings.append("configuration_driven_conditional_attribute_matrix_required")
    if "folder_deletion" in mechanisms:
        warnings.append("folder_deletion_surface_and_version_must_be_verified")
        if _FOLDER_RESTORE_RE.search(authoritative_scope):
            warnings.append("folder_restore_is_separate_from_delete_contract")
    explicit_sort_design = bool(
        "explorer_filename_title_sorting" in mechanisms
        and _EXPLORER_EXPLICIT_SORT_DESIGN_RE.search(design_text)
    )
    sort_contract_text = "\n".join(
        part for part in (authoritative_scope, design_text) if part
    )
    sort_feature_flag_contract = bool(
        "explorer_filename_title_sorting" in mechanisms
        and _EXPLORER_SORT_FEATURE_FLAG_RE.search(sort_contract_text)
    )
    sort_default_state_contract = bool(
        "explorer_filename_title_sorting" in mechanisms
        and _EXPLORER_SORT_DEFAULT_STATE_REQUEST_RE.search(sort_contract_text)
    )
    if explicit_sort_design:
        warnings.append("explorer_sort_explicit_control_selected_by_design")
    elif (
        "explorer_filename_title_sorting" in mechanisms
        and _EXPLORER_IMPLICIT_SORT_RE.search(authoritative_scope)
        and _EXPLORER_EXPLICIT_SORT_RE.search(authoritative_scope)
    ):
        warnings.append("explorer_sort_interaction_model_is_unresolved")
    if sort_feature_flag_contract:
        warnings.append("explorer_sort_feature_flag_state_matrix_required")
        if not _EXPLORER_SORT_FLAG_STATE_MATRIX_RE.search(sort_contract_text):
            warnings.append("explorer_sort_feature_flag_state_matrix_incomplete")
        if not _EXPLORER_SORT_FLAG_KEY_RE.search(sort_contract_text):
            warnings.append("explorer_sort_feature_flag_key_unresolved")
        if not _EXPLORER_SORT_FLAG_DEFAULT_RE.search(sort_contract_text):
            warnings.append("explorer_sort_feature_flag_default_value_unresolved")
        if not _EXPLORER_SORT_OFF_PRESENTATION_RE.search(sort_contract_text):
            warnings.append("explorer_sort_flag_off_presentation_unresolved")
    if sort_feature_flag_contract or sort_default_state_contract:
        warnings.append("explorer_sort_button_default_state_required")
        if not _EXPLORER_SORT_DEFAULT_STATE_VALUE_RE.search(sort_contract_text):
            warnings.append("explorer_sort_button_default_state_unresolved")

    references = ["references/component-routing.md"]
    if "config_driven_conditional_attribute_labels" in mechanisms:
        references.extend(
            [
                "references/component-authoring.md",
                "references/configuration-driven-enumerations.md",
            ]
        )
        load_full_reference = False
    elif primary_component == "Authoring":
        references.append("references/component-authoring.md")
        load_full_reference = False
    elif primary_component == "Integration" and "asset_crud_api_contract" in mechanisms:
        references.append("references/component-integration.md")
        load_full_reference = False
    elif primary_component == "Platform" and "bulk_asset_overwrite_session" in mechanisms:
        references.append("references/component-platform.md")
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
    elif "folder_deletion" in mechanisms:
        scope_mode = "proposed_only"
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
        "design_resolution": "explicit_sort_control" if explicit_sort_design else "",
        "feature_flag_matrix_required": sort_feature_flag_contract,
        "default_control_state_required": bool(
            sort_feature_flag_contract or sort_default_state_contract
        ),
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
        design_evidence=payload.get("design_evidence", ""),
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
