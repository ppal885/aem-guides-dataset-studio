from __future__ import annotations

import base64
import json
import os
import re
import struct
from statistics import mean
from typing import Any

from app.core.schemas_chat_authoring import (
    ChatAttachmentRef,
    ChatImageContext,
    DiagramGroupItem,
    DiagramInterpretationModel,
    DiagramRelationshipItem,
    ScreenshotClassificationFeatureModel,
    ScreenshotTypeClassification,
    ScreenshotBoundingBox,
    ScreenshotContentModel,
    ScreenshotDiagramTreeNode,
    ScreenshotEmbeddedGraphic,
    ScreenshotImageCharacterization,
    ScreenshotIntentRouteDecision,
    ScreenshotEmphasisCue,
    ScreenshotFieldValueItem,
    ScreenshotHeadingItem,
    ScreenshotLayoutRegion,
    ScreenshotHierarchyNode,
    ScreenshotNoteItem,
    ScreenshotParagraphItem,
    ScreenshotPassOutput,
    ScreenshotProceduralContentItem,
    ScreenshotProceduralModel,
    ScreenshotProceduralStep,
    ScreenshotProceduralSubstep,
    ScreenshotRegionItem,
    ScreenshotSemanticBlock,
    ScreenshotSettingField,
    ScreenshotSettingOption,
    ScreenshotSettingsReferenceModel,
    ScreenshotSettingsSection,
    ScreenshotSectionItem,
    ScreenshotTableItem,
    ScreenshotTextBlock,
    ScreenshotUnresolvedBlock,
    ScreenshotUnderstandingTrace,
)
from app.core.structured_logging import get_structured_logger
from app.services.llm_service import build_openai_chat_completion_kwargs, is_llm_available
from app.services.screenshot_intent_router import ScreenshotIntentRouter
from app.services.screenshot_type_classifier import ScreenshotTypeClassifier

logger = get_structured_logger(__name__)
_SCREENSHOT_TYPE_CLASSIFIER = ScreenshotTypeClassifier()
_SCREENSHOT_INTENT_ROUTER = ScreenshotIntentRouter()

_OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
_OPENAI_MODEL = (os.getenv("OPENAI_VISION_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
_AZURE_OPENAI_API_KEY = (os.getenv("AZURE_OPENAI_API_KEY") or "").strip()
_AZURE_OPENAI_ENDPOINT = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip()
_AZURE_OPENAI_API_VERSION = (os.getenv("AZURE_OPENAI_API_VERSION") or "").strip()
_AZURE_OPENAI_MODEL = (
    os.getenv("AZURE_OPENAI_VISION_MODEL")
    or os.getenv("AZURE_OPENAI_MODEL")
    or os.getenv("AZURE_OPENAI_DEPLOYMENT")
    or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
    or os.getenv("OPENAI_VISION_MODEL")
    or os.getenv("OPENAI_MODEL")
    or "gpt-4o-mini"
).strip()
_ANTHROPIC_API_KEY = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
_ANTHROPIC_MODEL = (os.getenv("ANTHROPIC_VISION_MODEL") or os.getenv("ANTHROPIC_MODEL") or "claude-3-5-sonnet-20241022").strip()
_VISION_TIMEOUT = float(os.getenv("SCREENSHOT_UNDERSTANDING_TIMEOUT_SEC") or "60")
_MIN_REGION_CONFIDENCE = 0.45

_VISION_AUX_KEYS = frozenset({"image_characterization", "embedded_diagrams", "embedded_graphics", "diagram_interpretation"})

_EMBEDDED_GRAPHIC_KINDS = frozenset(
    {
        "dita_map_hierarchy",
        "flowchart",
        "sequence_diagram",
        "architecture_block",
        "screenshot_within_screenshot",
        "table_or_matrix",
        "unclassified",
    }
)

_REGION_TYPE_ALIASES: dict[str, str] = {
    "subtitle": "heading",
    "subheading": "heading",
    "header": "heading",
    "text": "paragraph",
    "body_text": "paragraph",
    "body": "paragraph",
    "bullet": "bullet_list",
    "bullets": "bullet_list",
    "ordered_list": "numbered_list",
    "step_list": "numbered_list",
    "steps": "numbered_list",
    "callout": "note",
    "tip": "note",
    "caution": "warning",
    "alert": "warning",
    "form": "field_value_block",
    "fields": "field_value_block",
    "kv": "field_value_block",
    "key_value": "field_value_block",
    "ui": "ui_control_text",
    "ui_label": "ui_control_text",
    "control": "ui_control_text",
    "controls": "ui_control_text",
    "criteria": "acceptance_criteria",
    "settings": "field_value_block",
    "settings_panel": "field_value_block",
    "configuration": "field_value_block",
    "configuration_panel": "field_value_block",
    "properties_panel": "field_value_block",
    "dialog": "field_value_block",
}

_ORDERED_STEP_RE = re.compile(r"^\s*(\d+[\.\)])\s+(.*\S)\s*$")
_INDENTED_ORDERED_STEP_RE = re.compile(r"^\s{2,}(\d+[\.\)]|[a-zA-Z][\.\)])\s+(.*\S)\s*$")
_PREREQ_HEADING_RE = re.compile(r"\b(before you begin|prereq|prerequisite|prerequisites|requirements?|what you need)\b", re.IGNORECASE)
_CONTEXT_HEADING_RE = re.compile(r"\b(context|overview|about this task|about this procedure|introduction)\b", re.IGNORECASE)
_RESULT_HEADING_RE = re.compile(r"\b(result|results|after you complete|after completing|outcome)\b", re.IGNORECASE)
_EXAMPLE_HEADING_RE = re.compile(r"\b(example|examples|command|commands|sample|samples)\b", re.IGNORECASE)
_CHECKBOX_LINE_RE = re.compile(r"^\s*(?:\[(?P<box>[xX ])\]|(?P<glyph>[☑☐✓]))\s+(?P<label>.*\S)\s*$")
_RADIO_LINE_RE = re.compile(r"^\s*(?:\((?P<radio>[xX ])\)|(?P<glyph>[◉○]))\s+(?P<label>.*\S)\s*$")
_COLON_FIELD_RE = re.compile(r"^\s*(?P<label>[^:]{1,80}?)\s*:\s*(?P<value>.+?)\s*$")
_DROPDOWN_HINT_RE = re.compile(r"(?:▼|▾|\bselect\b|\bchoose\b|\bdropdown\b)", re.IGNORECASE)
_BUTTON_LABELS = {"save", "cancel", "apply", "close", "submit", "next", "back", "ok", "done"}

# Re-declare symbol-driven patterns with unicode escapes so checkbox/radio/dropdown
# heuristics remain reliable even if the source file has legacy mojibake characters.
_CHECKBOX_LINE_RE = re.compile(
    r"^\s*(?:\[(?P<box>[xX ])\]|(?P<glyph>[\u2611\u2610\u2713\u2714]))\s+(?P<label>.*\S)\s*$"
)
_RADIO_LINE_RE = re.compile(
    r"^\s*(?:\((?P<radio>[xX ])\)|(?P<glyph>[\u25c9\u25cb]))\s+(?P<label>.*\S)\s*$"
)
_DROPDOWN_HINT_RE = re.compile(r"(?:[\u25bc\u25be]|\bselect\b|\bchoose\b|\bdropdown\b)", re.IGNORECASE)

_VISION_PROVIDER_ALIASES = {
    "": "inherit",
    "inherit": "inherit",
    "default": "inherit",
    "auto": "inherit",
    "openai": "openai",
    "azure": "azure_openai",
    "azure_openai": "azure_openai",
    "azure-openai": "azure_openai",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "disabled": "fallback",
    "disable": "fallback",
    "off": "fallback",
    "none": "fallback",
    "fallback": "fallback",
}


def _data_url(mime_type: str, payload: bytes) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _clip_text(value: str, limit: int = 320) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        value = " ".join((raw or "").split()).strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _split_lines(value: str) -> list[str]:
    return [line.strip(" \t\r\n-•") for line in (value or "").splitlines() if line.strip()]


def _is_probable_label(value: str) -> bool:
    compact = " ".join((value or "").split())
    if not compact:
        return False
    if compact.endswith(":"):
        return True
    words = compact.split()
    if len(words) > 5:
        return False
    return compact[0].isupper() and compact.lower() != compact


def _normalize_inline_text(value: str) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").split()).strip()


def _normalize_line_preserve_indent(value: str) -> str:
    raw = str(value or "").replace("\u00a0", " ").replace("\t", "    ").rstrip("\r\n")
    if not raw.strip():
        return ""
    leading_spaces = len(raw) - len(raw.lstrip(" "))
    normalized = raw.strip()
    return f"{' ' * leading_spaces}{normalized}" if leading_spaces else normalized


def _is_bullet_like_line(value: str) -> bool:
    return bool(re.match(r"^\s*[-*]\s+\S", value or ""))


def _is_list_like_line(value: str) -> bool:
    text = str(value or "")
    return bool(_ORDERED_STEP_RE.match(text) or _INDENTED_ORDERED_STEP_RE.match(text) or _is_bullet_like_line(text))


def _looks_like_stackable_field_label(value: str) -> bool:
    compact = _normalize_inline_text(value).rstrip(":")
    if not compact or _is_list_like_line(compact):
        return False
    if compact.casefold() in _BUTTON_LABELS:
        return False
    if re.search(r"[.!?]$", compact) and not str(value or "").strip().endswith(":"):
        return False
    words = compact.split()
    if len(words) > 7:
        return False
    return str(value or "").strip().endswith(":") or _is_probable_label(compact)


def _looks_like_field_value_text(value: str) -> bool:
    compact = _normalize_inline_text(value)
    if not compact or _is_list_like_line(compact):
        return False
    if compact.casefold() in _BUTTON_LABELS or compact.endswith(":"):
        return False
    if re.search(
        r"\b(?:yes|no|on|off|enabled|disabled|selected|unselected|true|false|default)\b",
        compact,
        re.IGNORECASE,
    ):
        return True
    if re.search(r"[\d/@\\.%]", compact):
        return True
    return len(compact.split()) <= 8


def _can_pair_stacked_field_value(label_line: str, value_line: str, following_line: str | None = None) -> bool:
    if not _looks_like_stackable_field_label(label_line):
        return False
    value = _normalize_inline_text(value_line)
    if not _looks_like_field_value_text(value):
        return False
    if following_line and _looks_like_stackable_field_label(following_line):
        return True
    return len(value.split()) <= 5 or bool(
        re.search(r"\b(?:yes|no|on|off|enabled|disabled|selected|true|false)\b", value, re.IGNORECASE)
    )


def _should_merge_wrapped_lines(previous: str, current: str) -> bool:
    prev = _normalize_inline_text(previous)
    cur = _normalize_inline_text(current)
    if not prev or not cur:
        return False
    if _is_list_like_line(prev) or _is_list_like_line(cur):
        return False
    if _looks_like_stackable_field_label(prev) or _looks_like_stackable_field_label(cur):
        return False
    if _CHECKBOX_LINE_RE.match(prev) or _CHECKBOX_LINE_RE.match(cur) or _RADIO_LINE_RE.match(prev) or _RADIO_LINE_RE.match(cur):
        return False
    if prev.endswith(("/", "-", "(")):
        return True
    if prev.endswith((".", "!", "?", ":", ";")) and len(prev.split()) >= 3:
        return False
    if cur[0].islower() or cur[0].isdigit() or cur.startswith(("(", "/", "%")):
        return True
    return len(prev.split()) <= 4 and len(cur.split()) <= 6


def _infer_region_type_from_lines_or_text(
    *,
    lines: list[str],
    text: str = "",
    fallback_type: str = "unknown",
) -> str:
    normalized_fallback = _normalize_region_type(fallback_type)
    signal_lines = [str(line or "") for line in lines if str(line or "").strip()]
    joined_text = "\n".join(signal_lines).strip() or str(text or "").strip()
    if not joined_text:
        return normalized_fallback

    nonempty_lines = [line for line in signal_lines if _normalize_inline_text(line)]
    if len(nonempty_lines) >= 2:
        table_rows = _infer_table_rows_from_lines(nonempty_lines)
        if len(table_rows) >= 2:
            return "table"

    extracted_pairs = _extract_field_values_from_lines(nonempty_lines, None)
    if extracted_pairs:
        return "field_value_block"

    if nonempty_lines:
        ordered_count = sum(1 for line in nonempty_lines if _ORDERED_STEP_RE.match(line) or _INDENTED_ORDERED_STEP_RE.match(line))
        bullet_count = sum(1 for line in nonempty_lines if _is_bullet_like_line(line))
        control_count = sum(1 for line in nonempty_lines if _CHECKBOX_LINE_RE.match(line) or _RADIO_LINE_RE.match(line))
        if ordered_count >= 1 and ordered_count >= bullet_count:
            return "numbered_list"
        if bullet_count >= 1:
            return "bullet_list"
        if control_count >= max(1, len(nonempty_lines) // 2):
            return "ui_control_text"

    compact_text = _normalize_inline_text(joined_text)
    if compact_text.startswith(("`", "$", ">")) or _EXAMPLE_HEADING_RE.search(compact_text):
        return "code"
    if re.search(r"\b(note|tip)\b", compact_text, re.IGNORECASE):
        return "note"
    if re.search(r"\b(warning|caution|important)\b", compact_text, re.IGNORECASE):
        return "warning"
    if normalized_fallback in {"unknown", "paragraph"} and len(compact_text.split()) <= 12 and _is_probable_label(compact_text):
        return "heading"
    return normalized_fallback


def _merge_wrapped_text_lines(lines: list[str]) -> list[str]:
    merged: list[str] = []
    for raw_line in lines:
        line = _normalize_inline_text(raw_line)
        if not line:
            continue
        if not merged:
            merged.append(line)
            continue
        previous = merged[-1]
        if _should_merge_wrapped_lines(previous, line):
            if previous.endswith("-"):
                merged[-1] = previous[:-1].rstrip() + line
            else:
                merged[-1] = f"{previous} {line}".strip()
        else:
            merged.append(line)
    return merged


def _structure_preserving_ui_lines(lines: list[str]) -> list[str]:
    kept: list[str] = []
    for raw in lines:
        value = _normalize_inline_text(raw)
        if not value:
            continue
        lower = value.casefold()
        if lower in _BUTTON_LABELS:
            continue
        if value.startswith("<") and value.endswith(">"):
            kept.append(value)
            continue
        if any(
            token in lower
            for token in ("topic", "taskbody", "shortdesc", "prolog", "conbody", "refbody", "map", "topicref", "mapref", "keyref", "conref", "conkeyref")
        ):
            kept.append(value)
            continue
        if len(value.split()) >= 3:
            kept.append(value)
    return kept


def _parse_json_loose(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:].strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _png_dimensions(image_bytes: bytes) -> tuple[int, int] | None:
    if len(image_bytes) < 24 or image_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", image_bytes[16:24])
    return int(width), int(height)


def assess_screenshot_input_quality(image_bytes: bytes, mime_type: str) -> tuple[float, list[str]]:
    quality = 1.0
    warnings: list[str] = []

    if not image_bytes:
        return 0.0, ["The screenshot payload was empty."]
    if len(image_bytes) < 8_000:
        quality *= 0.72
        warnings.append("The screenshot file is very small, so layout and text may be incomplete.")
    if mime_type == "image/png":
        dims = _png_dimensions(image_bytes)
        if dims:
            width, height = dims
            if width < 500 or height < 300:
                quality *= 0.7
                warnings.append("The screenshot dimensions are small, so headings and field groups may be ambiguous.")
        else:
            warnings.append("The PNG metadata could not be read for image quality checks.")
    return max(0.05, min(1.0, quality)), warnings


def _vision_aux_from_semantic_payload(parsed: dict[str, Any]) -> dict[str, Any]:
    return {k: parsed[k] for k in _VISION_AUX_KEYS if k in parsed and parsed[k] is not None}


def _normalize_embedded_graphic_kind(raw: Any) -> str:
    v = str(raw or "unclassified").strip().lower().replace(" ", "_").replace("-", "_")
    return v if v in _EMBEDDED_GRAPHIC_KINDS else "unclassified"


def _parse_diagram_tree_node(data: Any, *, depth: int = 0, max_depth: int = 14) -> ScreenshotDiagramTreeNode | None:
    if depth > max_depth or not isinstance(data, dict):
        return None
    title = " ".join(str(data.get("title") or "").split()).strip()
    dtype = str(data.get("dita_type") or "topic").strip().lower().replace(" ", "_")
    if dtype in {"map", "ditamap", "dita_map"}:
        dtype = "map_root"
    if dtype not in {"map_root", "concept", "task", "reference", "topic"}:
        dtype = "topic"
    children: list[ScreenshotDiagramTreeNode] = []
    raw_children = data.get("children")
    if isinstance(raw_children, list):
        for ch in raw_children[:28]:
            node = _parse_diagram_tree_node(ch, depth=depth + 1, max_depth=max_depth)
            if node is not None:
                children.append(node)
    if not title and not children:
        return None
    return ScreenshotDiagramTreeNode(
        title=title or "(unlabeled)",
        dita_type=dtype,
        children=children,
        confidence=_to_confidence(data.get("confidence"), 0.72),
    )


def _parse_one_embedded_graphic(entry: dict[str, Any]) -> ScreenshotEmbeddedGraphic | None:
    kind = _normalize_embedded_graphic_kind(entry.get("kind"))
    label = " ".join(str(entry.get("label") or "").split()).strip()
    description = " ".join(str(entry.get("description") or "").split()).strip()
    root_raw = entry.get("outline_root") or entry.get("root")
    root = _parse_diagram_tree_node(root_raw) if root_raw else None
    if not label and not description and root is None:
        return None
    return ScreenshotEmbeddedGraphic(kind=kind, label=label, description=description, diagram_root=root)  # type: ignore[arg-type]


def _parse_embedded_graphics_payload(raw: Any) -> list[ScreenshotEmbeddedGraphic]:
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out: list[ScreenshotEmbeddedGraphic] = []
    for item in raw[:8]:
        if isinstance(item, dict):
            g = _parse_one_embedded_graphic(item)
            if g is not None:
                out.append(g)
    return out


def _parse_image_characterization_payload(raw: Any) -> ScreenshotImageCharacterization | None:
    if not isinstance(raw, dict):
        return None
    primary = " ".join(str(raw.get("primary_scene") or "").split()).strip()
    embedded = " ".join(str(raw.get("embedded_content_summary") or "").split()).strip()
    intent = " ".join(str(raw.get("author_intent_hypothesis") or "").split()).strip()
    secondary: list[str] = []
    for item in raw.get("secondary_elements") or []:
        s = " ".join(str(item).split()).strip()
        if s:
            secondary.append(s)
    if not primary and not embedded and not intent and not secondary:
        return None
    return ScreenshotImageCharacterization(
        primary_scene=primary,
        secondary_elements=secondary[:16],
        embedded_content_summary=embedded,
        author_intent_hypothesis=intent,
    )


def _normalize_diagram_kind(raw: Any) -> str:
    value = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "hierarchy_diagram": "hierarchy",
        "tree": "hierarchy",
        "tree_diagram": "hierarchy",
        "taxonomy_diagram": "taxonomy",
        "relationship_diagram": "relationship",
        "concept_map": "relationship",
        "flowchart": "flow_structure",
        "flow": "flow_structure",
        "sequence": "flow_structure",
        "structure": "hierarchy",
    }
    value = aliases.get(value, value)
    return value if value in {"hierarchy", "taxonomy", "relationship", "flow_structure", "unknown"} else "unknown"


def _normalize_diagram_orientation(raw: Any) -> str:
    value = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "concept": "conceptual",
        "concepts": "conceptual",
        "reference_topic": "reference",
        "task": "procedural",
        "procedure": "procedural",
    }
    value = aliases.get(value, value)
    return value if value in {"conceptual", "procedural", "reference", "mixed", "unknown"} else "unknown"


def _parse_diagram_relationships(raw: Any) -> list[DiagramRelationshipItem]:
    if not isinstance(raw, list):
        return []
    items: list[DiagramRelationshipItem] = []
    for entry in raw[:80]:
        if not isinstance(entry, dict):
            continue
        source = " ".join(str(entry.get("source") or "").split()).strip()
        target = " ".join(str(entry.get("target") or "").split()).strip()
        if not source or not target:
            continue
        kind = str(entry.get("kind") or "unknown").strip().lower().replace(" ", "_").replace("-", "_")
        if kind not in {"parent_child", "association", "flow", "grouping", "unknown"}:
            kind = "unknown"
        items.append(
            DiagramRelationshipItem(
                source=source,
                target=target,
                kind=kind,  # type: ignore[arg-type]
                label=" ".join(str(entry.get("label") or "").split()).strip(),
                confidence=_to_confidence(entry.get("confidence"), 0.72),
            )
        )
    return items


def _parse_diagram_groups(raw: Any) -> list[DiagramGroupItem]:
    if not isinstance(raw, list):
        return []
    groups: list[DiagramGroupItem] = []
    for entry in raw[:40]:
        if not isinstance(entry, dict):
            continue
        name = " ".join(str(entry.get("name") or "").split()).strip()
        members = _dedupe_preserve_order([str(item).strip() for item in (entry.get("members") or []) if str(item).strip()])
        if not name and not members:
            continue
        groups.append(
            DiagramGroupItem(
                name=name or "Group",
                members=members[:40],
                confidence=_to_confidence(entry.get("confidence"), 0.7),
            )
        )
    return groups


def _parse_diagram_interpretation_payload(raw: Any) -> DiagramInterpretationModel | None:
    if not isinstance(raw, dict):
        return None
    kind = _normalize_diagram_kind(raw.get("diagram_kind"))
    orientation = _normalize_diagram_orientation(raw.get("content_orientation"))
    dominant_meaning = " ".join(str(raw.get("dominant_meaning") or "").split()).strip()
    key_entities = _dedupe_preserve_order([str(item).strip() for item in (raw.get("key_entities") or []) if str(item).strip()])
    relationships = _parse_diagram_relationships(raw.get("relationships"))
    groups = _parse_diagram_groups(raw.get("groups"))
    warnings = _dedupe_preserve_order([str(item).strip() for item in (raw.get("warnings") or []) if str(item).strip()])
    if not dominant_meaning and not key_entities and not relationships and not groups:
        return None
    return DiagramInterpretationModel(
        diagram_kind=kind,  # type: ignore[arg-type]
        content_orientation=orientation,  # type: ignore[arg-type]
        dominant_meaning=dominant_meaning,
        key_entities=key_entities[:80],
        relationships=relationships,
        groups=groups,
        confidence=_to_confidence(raw.get("confidence"), 0.72),
        warnings=warnings,
    )


def _parse_classification_features_payload(raw: Any) -> ScreenshotClassificationFeatureModel | None:
    if not isinstance(raw, dict):
        return None
    try:
        return ScreenshotClassificationFeatureModel.model_validate(raw)
    except Exception:
        return None


def _parse_screenshot_type_classification_payload(raw: Any) -> ScreenshotTypeClassification | None:
    if not isinstance(raw, dict):
        return None
    try:
        return ScreenshotTypeClassification.model_validate(raw)
    except Exception:
        return None


def _parse_screenshot_intent_route_payload(raw: Any) -> ScreenshotIntentRouteDecision | None:
    if not isinstance(raw, dict):
        return None
    try:
        return ScreenshotIntentRouteDecision.model_validate(raw)
    except Exception:
        return None


def _flatten_diagram_entities(node: ScreenshotDiagramTreeNode) -> list[str]:
    entities = [node.title] if node.title else []
    for child in node.children:
        entities.extend(_flatten_diagram_entities(child))
    return entities


def _diagram_relationships_from_tree(
    node: ScreenshotDiagramTreeNode,
    *,
    kind: str,
    items: list[DiagramRelationshipItem] | None = None,
) -> list[DiagramRelationshipItem]:
    rels = items or []
    if not node.children:
        return rels
    relationship_kind = "flow" if kind == "flow_structure" else "parent_child"
    for child in node.children:
        if node.title and child.title:
            rels.append(
                DiagramRelationshipItem(
                    source=node.title,
                    target=child.title,
                    kind=relationship_kind,  # type: ignore[arg-type]
                    confidence=min(node.confidence, child.confidence),
                )
            )
        _diagram_relationships_from_tree(child, kind=kind, items=rels)
    return rels


def _diagram_groups_from_tree(root: ScreenshotDiagramTreeNode) -> list[DiagramGroupItem]:
    groups: list[DiagramGroupItem] = []
    if root.title and root.children:
        groups.append(
            DiagramGroupItem(
                name=root.title,
                members=_dedupe_preserve_order([child.title for child in root.children if child.title]),
                confidence=root.confidence,
            )
        )
    for child in root.children:
        if child.title and child.children:
            groups.append(
                DiagramGroupItem(
                    name=child.title,
                    members=_dedupe_preserve_order([grand.title for grand in child.children if grand.title]),
                    confidence=child.confidence,
                )
            )
    return groups


def _derive_diagram_interpretation(
    *,
    parsed: dict[str, Any],
    embedded_graphics: list[ScreenshotEmbeddedGraphic],
    image_characterization: ScreenshotImageCharacterization | None,
    title: str,
    regions: list[ScreenshotRegionItem],
) -> DiagramInterpretationModel | None:
    explicit = _parse_diagram_interpretation_payload(parsed.get("diagram_interpretation"))
    if explicit is not None:
        return explicit

    if not embedded_graphics:
        return None

    primary = embedded_graphics[0]
    kind = "unknown"
    if primary.kind == "dita_map_hierarchy":
        kind = "hierarchy"
    elif primary.kind == "flowchart":
        kind = "flow_structure"
    elif primary.kind == "sequence_diagram":
        kind = "flow_structure"
    elif primary.kind == "architecture_block":
        kind = "relationship"
    elif primary.kind == "table_or_matrix":
        kind = "relationship"

    orientation = "unknown"
    if kind in {"hierarchy", "taxonomy", "relationship"}:
        orientation = "conceptual"
    elif kind == "flow_structure":
        orientation = "procedural"

    if image_characterization:
        hint = f"{image_characterization.primary_scene} {image_characterization.author_intent_hypothesis}".lower()
        if "reference" in hint or "properties" in hint or "settings" in hint:
            orientation = "reference"
        elif "concept" in hint or "taxonomy" in hint or "hierarchy" in hint:
            orientation = "conceptual"
        elif "workflow" in hint or "step" in hint or "flow" in hint or "procedure" in hint:
            orientation = "procedural"

    key_entities: list[str] = []
    relationships: list[DiagramRelationshipItem] = []
    groups: list[DiagramGroupItem] = []
    warnings: list[str] = []
    confidences: list[float] = []

    for graphic in embedded_graphics[:6]:
        if graphic.diagram_root is not None:
            key_entities.extend(_flatten_diagram_entities(graphic.diagram_root))
            relationships.extend(_diagram_relationships_from_tree(graphic.diagram_root, kind=kind))
            groups.extend(_diagram_groups_from_tree(graphic.diagram_root))
            confidences.append(graphic.diagram_root.confidence)
        if graphic.description:
            warnings.extend([graphic.description] if "unclear" in graphic.description.lower() else [])

    key_entities = _dedupe_preserve_order([entity for entity in key_entities if entity and entity != "(unlabeled)"])[:80]

    region_titles = [
        region.text or region.label
        for region in regions
        if region.region_type in {"title", "heading"} and (region.text or region.label)
    ]
    if not key_entities:
        key_entities = _dedupe_preserve_order(region_titles)[:20]

    if kind == "unknown" and relationships:
        rel_kinds = {rel.kind for rel in relationships}
        if rel_kinds == {"parent_child"}:
            kind = "hierarchy"
        elif "flow" in rel_kinds:
            kind = "flow_structure"
        else:
            kind = "relationship"

    dominant_meaning = ""
    if primary.kind == "dita_map_hierarchy":
        dominant_meaning = "DITA map hierarchy showing topic organization and parent-child structure."
    elif kind == "hierarchy":
        dominant_meaning = "Hierarchy diagram showing parent-child structure among labeled entities."
    elif kind == "taxonomy":
        dominant_meaning = "Taxonomy diagram grouping related entities into classification branches."
    elif kind == "relationship":
        dominant_meaning = "Relationship diagram showing associations among labeled entities."
    elif kind == "flow_structure":
        dominant_meaning = "Flow or structure diagram showing progression or linked stages."

    if title and not dominant_meaning:
        dominant_meaning = f"Diagram centered on {title}."
    if image_characterization and image_characterization.embedded_content_summary and not dominant_meaning:
        dominant_meaning = image_characterization.embedded_content_summary

    confidence = round(mean(confidences), 3) if confidences else 0.62
    if not dominant_meaning and not key_entities and not relationships:
        return None

    return DiagramInterpretationModel(
        diagram_kind=kind,  # type: ignore[arg-type]
        content_orientation=orientation,  # type: ignore[arg-type]
        dominant_meaning=dominant_meaning,
        key_entities=key_entities,
        relationships=relationships[:120],
        groups=groups[:40],
        confidence=confidence,
        warnings=_dedupe_preserve_order(warnings),
    )


def _flatten_diagram_tree_lines(node: ScreenshotDiagramTreeNode, depth: int = 0, max_lines: int = 48) -> list[str]:
    lines: list[str] = []
    if len(lines) >= max_lines:
        return lines
    indent = "  " * depth
    lines.append(f"{indent}• {node.title} [{node.dita_type}]")
    for ch in node.children:
        if len(lines) >= max_lines:
            break
        lines.extend(_flatten_diagram_tree_lines(ch, depth + 1, max_lines=max_lines))
    return lines[:max_lines]


def _vision_system_prompt() -> str:
    return (
        "You are a screenshot understanding model for enterprise authoring.\n"
        "Analyze the screenshot semantically, not as a flat OCR dump.\n"
        "Return JSON only.\n\n"
        "Required goals:\n"
        "1. Detect visual regions and keep unrelated text separate.\n"
        "2. Classify each region as one of: title, heading, paragraph, bullet_list, numbered_list, note, warning, code, table, field_value_block, ui_control_text, acceptance_criteria, unknown.\n"
        "3. Preserve local grouping for bullets, numbered steps, field/value pairs, notes, warnings, tables, and UI labels.\n"
        "4. Reconstruct reading order.\n"
        "5. Infer hierarchy from title and headings.\n"
        "6. Mark uncertain or cropped regions explicitly instead of guessing.\n"
        "7. Never invent hidden text.\n\n"
        "Return keys:\n"
        "- summary\n"
        "- title\n"
        "- inferred_workflow\n"
        "- visible_text\n"
        "- regions: array of region objects with region_id, region_type, label, text, lines, items, field_values, table_rows, heading_level, bbox, order_hint, confidence, uncertain, uncertainty_reason\n"
        "- reading_order: ordered region_id array\n"
        "- semantic_hierarchy: array with node_id, title, level, purpose, region_ids, confidence\n"
        "- headings, sections, numbered_steps, bullet_lists, notes, tables, field_value_pairs, code_snippets, ui_labels, menu_names, button_names, acceptance_criteria\n"
        "- settings_reference (object, when the UI is mostly forms/settings/properties): see below\n"
        "- image_characterization (object, when the image contains mixed UI + diagram or diagram-heavy content)\n"
        "- embedded_graphics (array, when the image contains hierarchy/taxonomy/relationship/flow diagrams)\n"
        "- diagram_interpretation (object, when a labeled-node diagram is visible)\n"
        "- confidence\n"
        "- field_confidence\n"
        "- uncertainty_warnings\n"
        "- warnings\n\n"
        "settings_reference (omit if the screen is not a form/settings/properties panel):\n"
        "- title: dialog or panel title if visible\n"
        "- tabs: string array of visible tab labels left-to-right\n"
        "- active_tab: which tab is selected, if clear\n"
        "- helper_text: short explanatory strings under fields (not body copy)\n"
        "- sections: array of objects with title, optional tab, description (string array), fields, parameter_tables\n"
        "- fields: array of objects with label, value, control_type, helper_text (string array), options, confidence\n"
        "- control_type must be one of: text, dropdown, checkbox, radio, toggle, table, unknown\n"
        "- options: array of objects with label, selected (boolean or null), confidence for radio groups, dropdowns, checkboxes\n"
        "- parameter_tables: array of objects with caption, headers (string array), rows (array of string arrays), confidence\n"
        "- Preserve label↔value association; do not merge unrelated fields into one paragraph.\n"
        "- Group fields under the same visible section heading or card title.\n\n"
        "diagram_interpretation (omit if there is no meaningful diagram):\n"
        "- diagram_kind: hierarchy | taxonomy | relationship | flow_structure | unknown\n"
        "- content_orientation: conceptual | procedural | reference | mixed | unknown\n"
        "- dominant_meaning: concise sentence about what the image means overall\n"
        "- key_entities: main labeled nodes or concepts\n"
        "- relationships: source/target/kind pairs when visible\n"
        "- groups: named branches or clusters when visible\n"
        "- confidence and warnings\n"
        "- A DITA map hierarchy or taxonomy should usually be conceptual, not procedural, unless explicit step-flow evidence dominates.\n\n"
        "Important extraction rules:\n"
        "- Keep numbered procedures separate from bullets.\n"
        "- Keep field names separate from values when possible.\n"
        "- Keep UI controls separate from explanatory prose.\n"
        "- Keep acceptance criteria separate from generic lists.\n"
        "- If a region is too blurry, partial, or cut off, set uncertain=true and explain why.\n"
        "- For tables, preserve rows. Use headers only when they are truly visible.\n"
        "- Prefer omission over hallucination.\n"
        "- CRITICAL: Do NOT emit raw HTML/DOM tag names (body, html, div, ul, ol, li, p, span, nav, "
        "header, footer, section, article, aside, table, thead, tbody, tr, th, td, a, form, input, "
        "button, h1-h6, etc.) as text content in 'items', 'lines', 'text', or 'details' fields. "
        "If the only visible text in a region is such tag names, classify it as region_type='unknown', "
        "set uncertain=true, and leave items/lines empty.\n"
        "- When a screenshot contains a visible DOM tree inspector or browser dev-tools panel, treat "
        "all tag-name nodes as ui_labels only; do NOT promote them into bullet_lists or numbered_steps.\n"
        "- bullet_lists and numbered_steps must contain human-readable English sentences or phrases "
        "describing the UI's content — not structural tag names from the underlying HTML."
    )


_MAP_HIERARCHY_SYSTEM_PROMPT = (
    "You read screenshots of DITA information-architecture diagrams, hierarchy charts, or map trees.\n"
    "Boxes are often labeled with topic types (concept, task, reference) or \"DITA map\" at the root.\n"
    "Return JSON only with keys: map_title (string), root (object or null), roots (array, optional), "
    "confidence (number 0..1), warnings (string array).\n\n"
    "Each tree node uses:\n"
    "- title: visible label text (short).\n"
    "- dita_type: one of map_root, concept, task, reference, topic.\n"
    "  Use map_root only for the diagram root that represents the map container (not a .dita topic file).\n"
    "- children: array of child nodes in the same shape.\n\n"
    "If a single root box exists (e.g. \"DITA map\"), use root. If multiple top-level siblings, use roots instead of root.\n"
    "Infer types from color legends or captions when visible; otherwise use topic.\n"
    "If the image is not a hierarchy/structure diagram, set root to null and explain in warnings.\n"
    "Do not invent nodes. Prefer omission over guessing.\n"
)


def _layout_pass_prompt() -> str:
    return (
        "Pass 1: detect document blocks and layout regions only.\n"
        "Return JSON with key `regions`.\n"
        "Each region must include: region_id, layout_type, label, bbox, order_hint, confidence, uncertain, uncertainty_reason.\n"
        "Do not extract detailed text here. Focus on coarse blocks like title banner, heading block, paragraph block, list block, "
        "table block, field/value form block, grouped settings or properties panel, tab strip, dropdown cluster, checkbox group, "
        "note/callout block, code block, and UI control cluster."
    )


def _text_pass_prompt(layout_regions: list[ScreenshotLayoutRegion]) -> str:
    region_brief = [
        {
            "region_id": region.region_id,
            "layout_type": region.layout_type,
            "label": region.label,
            "bbox": region.bbox.model_dump(mode="json") if region.bbox else None,
        }
        for region in layout_regions
    ]
    return (
        "Pass 2: extract text for each detected region.\n"
        "Return JSON with key `text_blocks`.\n"
        "Each text block must include: region_id, raw_text, lines, confidence, uncertain, uncertainty_reason.\n"
        "Keep text grouped by the provided region ids. Do not classify semantics yet.\n"
        f"Regions:\n{json.dumps(region_brief, ensure_ascii=True)}"
    )


def _classification_pass_prompt(text_blocks: list[ScreenshotTextBlock]) -> str:
    block_brief = [
        {
            "region_id": block.region_id,
            "layout_type": block.layout_type,
            "lines": block.lines[:12],
            "raw_text": _clip_text(block.raw_text, 220),
        }
        for block in text_blocks
    ]
    return (
        "Pass 3: classify each region into semantic content types.\n"
        "Allowed semantic types: title, heading, paragraph, bullet_list, numbered_list, note, warning, code, table, "
        "field_value_block, ui_control_text, acceptance_criteria, unknown.\n"
        "Return JSON with key `semantic_blocks`.\n"
        "Each semantic block must include: region_id, semantic_type, label, text, lines, items, field_values, table_rows, "
        "heading_level, confidence, uncertain, uncertainty_reason.\n"
        "For settings/forms/properties UIs, populate field_values with {{field, value}} objects (labels separate from values); "
        "use items for checkbox/radio lines; use table_rows for parameter matrices.\n"
        "If the image includes a hierarchy, taxonomy, relationship, or flow diagram, also return `embedded_graphics`, "
        "`image_characterization`, and `diagram_interpretation`. A DITA map hierarchy should bias toward conceptual interpretation.\n"
        "Also return key `settings_reference` when the screenshot is primarily a configuration or properties UI: "
        "tabs (string array), active_tab, sections with nested fields (label, value, control_type, helper_text, options), "
        "and parameter_tables — same shape as the single-pass schema.\n"
        "Preserve ambiguity when confidence is low. Do not invent missing values.\n"
        f"Blocks:\n{json.dumps(block_brief, ensure_ascii=True)}"
    )


def _normalize_region_type(raw: Any) -> str:
    value = str(raw or "unknown").strip().lower().replace(" ", "_").replace("-", "_")
    value = _REGION_TYPE_ALIASES.get(value, value)
    if value not in {
        "title",
        "heading",
        "paragraph",
        "bullet_list",
        "numbered_list",
        "note",
        "warning",
        "code",
        "table",
        "field_value_block",
        "ui_control_text",
        "acceptance_criteria",
        "unknown",
    }:
        return "unknown"
    return value


def _to_confidence(value: Any, default: float = 0.5) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def _parse_bbox(value: Any) -> ScreenshotBoundingBox | None:
    if not isinstance(value, dict):
        return None
    bbox = ScreenshotBoundingBox(
        x=value.get("x"),
        y=value.get("y"),
        width=value.get("width"),
        height=value.get("height"),
    )
    if bbox.x is None and bbox.y is None and bbox.width is None and bbox.height is None:
        return None
    return bbox


def _log_stage_output(
    *,
    asset_id: str | None,
    stage_name: str,
    payload: dict[str, Any],
    summary: str,
) -> ScreenshotPassOutput:
    logger.info_structured(
        "screenshot_understanding_stage_completed",
        extra_fields={
            "asset_id": asset_id,
            "stage_name": stage_name,
            "summary": summary,
            "payload_preview": json.dumps(payload, ensure_ascii=False)[:1800],
        },
    )
    return ScreenshotPassOutput(
        pass_name=stage_name,
        summary=summary,
        region_count=len(payload.get("regions") or payload.get("text_blocks") or payload.get("semantic_blocks") or []),
        warning_count=len(payload.get("warnings") or payload.get("uncertainty_warnings") or []),
        payload=payload,
    )


def _parse_layout_regions(parsed: dict[str, Any]) -> list[ScreenshotLayoutRegion]:
    regions: list[ScreenshotLayoutRegion] = []
    raw_regions = parsed.get("regions")
    if not isinstance(raw_regions, list):
        raw_regions = []
    for index, entry in enumerate(raw_regions):
        if not isinstance(entry, dict):
            continue
        region_id = str(entry.get("region_id") or f"layout-{index + 1}").strip() or f"layout-{index + 1}"
        layout_type = _normalize_region_type(entry.get("layout_type") or entry.get("region_type"))
        regions.append(
            ScreenshotLayoutRegion(
                region_id=region_id,
                layout_type=layout_type,
                label=" ".join(str(entry.get("label") or "").split()).strip(),
                bbox=_parse_bbox(entry.get("bbox")),
                order_hint=int(entry.get("order_hint")) if str(entry.get("order_hint") or "").isdigit() else None,
                confidence=_to_confidence(entry.get("confidence"), 0.68),
                uncertain=bool(entry.get("uncertain")),
                uncertainty_reason=" ".join(str(entry.get("uncertainty_reason") or "").split()).strip() or None,
            )
        )
    if not regions:
        for region in _regions_from_legacy_schema(parsed):
            regions.append(
                ScreenshotLayoutRegion(
                    region_id=region.region_id,
                    layout_type=region.region_type,
                    label=region.label,
                    bbox=region.bbox,
                    order_hint=region.order_hint,
                    confidence=region.confidence,
                    uncertain=region.uncertain,
                    uncertainty_reason=region.uncertainty_reason,
                )
            )
    return regions


def _parse_text_blocks(parsed: dict[str, Any], layout_regions: list[ScreenshotLayoutRegion]) -> list[ScreenshotTextBlock]:
    layout_map = {region.region_id: region for region in layout_regions}
    raw_blocks = parsed.get("text_blocks")
    blocks: list[ScreenshotTextBlock] = []
    if isinstance(raw_blocks, list):
        for entry in raw_blocks:
            if not isinstance(entry, dict):
                continue
            region_id = str(entry.get("region_id") or "").strip()
            layout = layout_map.get(region_id)
            raw_text = str(entry.get("raw_text") or entry.get("text") or "").strip()
            lines = [
                _normalize_line_preserve_indent(str(line))
                for line in (entry.get("lines") or [])
                if _normalize_line_preserve_indent(str(line))
            ] or [_normalize_line_preserve_indent(line) for line in raw_text.splitlines() if _normalize_line_preserve_indent(line)]
            blocks.append(
                ScreenshotTextBlock(
                    region_id=region_id or f"text-{len(blocks) + 1}",
                    layout_type=layout.layout_type if layout else _normalize_region_type(entry.get("layout_type")),
                    bbox=layout.bbox if layout else _parse_bbox(entry.get("bbox")),
                    raw_text=raw_text,
                    lines=lines,
                    confidence=_to_confidence(entry.get("confidence"), layout.confidence if layout else 0.64),
                    uncertain=bool(entry.get("uncertain")),
                    uncertainty_reason=" ".join(str(entry.get("uncertainty_reason") or "").split()).strip() or None,
                )
            )
    if not blocks:
        for region in _parse_regions(parsed):
            blocks.append(
                ScreenshotTextBlock(
                    region_id=region.region_id,
                    layout_type=region.region_type,
                    bbox=region.bbox,
                    raw_text=region.text,
                    lines=_region_lines(region),
                    confidence=region.confidence,
                    uncertain=region.uncertain,
                    uncertainty_reason=region.uncertainty_reason,
                )
            )
    return blocks


def _parse_semantic_blocks(parsed: dict[str, Any], text_blocks: list[ScreenshotTextBlock]) -> list[ScreenshotSemanticBlock]:
    text_map = {block.region_id: block for block in text_blocks}
    raw_blocks = parsed.get("semantic_blocks")
    blocks: list[ScreenshotSemanticBlock] = []
    if isinstance(raw_blocks, list):
        for entry in raw_blocks:
            if not isinstance(entry, dict):
                continue
            region_id = str(entry.get("region_id") or "").strip()
            text_block = text_map.get(region_id)
            blocks.append(
                ScreenshotSemanticBlock(
                    region_id=region_id or f"semantic-{len(blocks) + 1}",
                    semantic_type=_normalize_region_type(entry.get("semantic_type") or entry.get("region_type")),
                    label=" ".join(str(entry.get("label") or "").split()).strip(),
                    text=" ".join(str(entry.get("text") or (text_block.raw_text if text_block else "")).split()).strip(),
                    lines=[
                        _normalize_line_preserve_indent(str(line))
                        for line in (entry.get("lines") or [])
                        if _normalize_line_preserve_indent(str(line))
                    ]
                    or (text_block.lines if text_block else []),
                    items=[str(item).strip() for item in (entry.get("items") or []) if str(item).strip()],
                    field_values=_parse_field_values(entry.get("field_values"), source_region_id=region_id or None),
                    table_rows=[
                        [" ".join(str(cell).split()) for cell in row if str(cell).strip()]
                        for row in (entry.get("table_rows") or [])
                        if isinstance(row, list)
                    ] or (
                        _infer_table_rows_from_lines(
                            [
                                _normalize_line_preserve_indent(str(line))
                                for line in (entry.get("lines") or [])
                                if _normalize_line_preserve_indent(str(line))
                            ]
                            or (text_block.lines if text_block else [])
                        )
                        if _normalize_region_type(entry.get("semantic_type") or entry.get("region_type")) == "table"
                        else []
                    ),
                    heading_level=int(entry.get("heading_level")) if str(entry.get("heading_level") or "").isdigit() else None,
                    bbox=text_block.bbox if text_block else _parse_bbox(entry.get("bbox")),
                    order_hint=None,
                    confidence=_to_confidence(entry.get("confidence"), text_block.confidence if text_block else 0.65),
                    uncertain=bool(entry.get("uncertain")),
                    uncertainty_reason=" ".join(str(entry.get("uncertainty_reason") or "").split()).strip() or None,
                )
            )
    if not blocks:
        for region in _parse_regions(parsed):
            blocks.append(
                ScreenshotSemanticBlock(
                    region_id=region.region_id,
                    semantic_type=region.region_type,
                    label=region.label,
                    text=region.text,
                    lines=region.lines,
                    items=region.items,
                    field_values=region.field_values,
                    table_rows=region.table_rows,
                    heading_level=region.heading_level,
                    bbox=region.bbox,
                    order_hint=region.order_hint,
                    confidence=region.confidence,
                    uncertain=region.uncertain,
                    uncertainty_reason=region.uncertainty_reason,
                )
            )
    return blocks


def _parse_field_values(values: Any, source_region_id: str | None = None) -> list[ScreenshotFieldValueItem]:
    pairs: list[ScreenshotFieldValueItem] = []
    if not isinstance(values, list):
        return pairs
    for entry in values:
        if isinstance(entry, dict):
            field = " ".join(str(entry.get("field") or "").split()).strip()
            raw_value = entry.get("value")
            if isinstance(raw_value, list):
                value = " | ".join(" ".join(str(part).split()) for part in raw_value if str(part).strip())
            else:
                value = " ".join(str(raw_value or "").split()).strip()
            if field or value:
                pairs.append(
                    ScreenshotFieldValueItem(
                        field=field,
                        value=value,
                        confidence=_to_confidence(entry.get("confidence"), 0.7),
                        source_region_id=source_region_id or str(entry.get("source_region_id") or "").strip() or None,
                    )
                )
    return pairs


def _extract_field_values_from_lines(lines: list[str], source_region_id: str | None = None) -> list[ScreenshotFieldValueItem]:
    pairs: list[ScreenshotFieldValueItem] = []
    normalized_lines = [str(line or "").rstrip() for line in lines if str(line or "").strip()]
    index = 0
    while index < len(normalized_lines):
        raw_line = normalized_lines[index]
        compact = _normalize_inline_text(raw_line)
        if not compact:
            index += 1
            continue

        checkbox = _CHECKBOX_LINE_RE.match(compact)
        if checkbox:
            label = _normalize_inline_text(checkbox.group("label") or "")
            if label:
                selected = bool(checkbox.group("box") and checkbox.group("box").strip().lower() == "x")
                pairs.append(
                    ScreenshotFieldValueItem(
                        field=label,
                        value="On" if selected else "Off",
                        confidence=0.64,
                        source_region_id=source_region_id,
                    )
                )
            index += 1
            continue

        radio = _RADIO_LINE_RE.match(compact)
        if radio:
            label = _normalize_inline_text(radio.group("label") or "")
            if label:
                selected = bool(radio.group("radio") and radio.group("radio").strip().lower() == "x")
                pairs.append(
                    ScreenshotFieldValueItem(
                        field=label,
                        value="Selected" if selected else "Not selected",
                        confidence=0.64,
                        source_region_id=source_region_id,
                    )
                )
            index += 1
            continue

        colon_match = _COLON_FIELD_RE.match(compact)
        if colon_match:
            field = _normalize_inline_text(colon_match.group("label") or "")
            value = _normalize_inline_text(colon_match.group("value") or "")
            if field and value and len(field.split()) <= 8:
                pairs.append(
                    ScreenshotFieldValueItem(
                        field=field,
                        value=value,
                        confidence=0.62,
                        source_region_id=source_region_id,
                    )
                )
            index += 1
            continue

        column_parts = [_normalize_inline_text(part) for part in re.split(r"\s{2,}|\t+", raw_line) if _normalize_inline_text(part)]
        if len(column_parts) >= 2 and len(column_parts[0].split()) <= 8:
            pairs.append(
                ScreenshotFieldValueItem(
                    field=column_parts[0].rstrip(":"),
                    value=" | ".join(part for part in column_parts[1:] if part),
                    confidence=0.58,
                    source_region_id=source_region_id,
                )
            )
            index += 1
            continue

        next_line = normalized_lines[index + 1] if index + 1 < len(normalized_lines) else None
        following_line = normalized_lines[index + 2] if index + 2 < len(normalized_lines) else None
        if next_line and _can_pair_stacked_field_value(compact, next_line, following_line):
            pairs.append(
                ScreenshotFieldValueItem(
                    field=compact.rstrip(":"),
                    value=_normalize_inline_text(next_line),
                    confidence=0.56,
                    source_region_id=source_region_id,
                )
            )
            index += 2
            continue

        index += 1
    return pairs


def _split_tabular_row(raw_line: str) -> list[str]:
    line = str(raw_line or "").rstrip()
    if not line.strip():
        return []
    pipe_parts = [_normalize_inline_text(part) for part in re.split(r"\s*\|\s*", line) if _normalize_inline_text(part)]
    if len(pipe_parts) >= 2:
        return pipe_parts
    gap_parts = [_normalize_inline_text(part) for part in re.split(r"\s{2,}|\t+", line) if _normalize_inline_text(part)]
    if len(gap_parts) >= 2:
        return gap_parts
    return []


def _infer_table_rows_from_lines(lines: list[str]) -> list[list[str]]:
    rows = [_split_tabular_row(line) for line in lines]
    rows = [row for row in rows if len(row) >= 2]
    if len(rows) < 2:
        return []
    target_columns = max(len(row) for row in rows)
    if target_columns < 2:
        return []
    normalized: list[list[str]] = []
    for row in rows:
        if len(row) > target_columns:
            normalized.append(row[:target_columns])
        elif len(row) < target_columns:
            normalized.append(row + [""] * (target_columns - len(row)))
        else:
            normalized.append(row)
    return normalized


def _parse_region(entry: Any, index: int) -> ScreenshotRegionItem:
    if not isinstance(entry, dict):
        return ScreenshotRegionItem(region_id=f"region-{index + 1}", region_type="unknown", confidence=0.0, uncertain=True)

    region_id = str(entry.get("region_id") or f"region-{index + 1}").strip() or f"region-{index + 1}"
    raw_lines = entry.get("lines")
    lines = (
        [
            _normalize_line_preserve_indent(str(line))
            for line in raw_lines
            if _normalize_line_preserve_indent(str(line))
        ]
        if isinstance(raw_lines, list)
        else [_normalize_line_preserve_indent(line) for line in str(entry.get("text") or "").splitlines() if _normalize_line_preserve_indent(line)]
    )
    region_text = " ".join(str(entry.get("text") or "").split()).strip()
    region_type = _infer_region_type_from_lines_or_text(
        lines=lines,
        text=region_text,
        fallback_type=entry.get("region_type"),
    )
    items = [str(item).strip() for item in (entry.get("items") or []) if str(item).strip()]
    field_values = _parse_field_values(entry.get("field_values"), source_region_id=region_id)
    if not field_values and region_type == "field_value_block":
        field_values = _extract_field_values_from_lines(lines, source_region_id=region_id)
    table_rows = []
    for row in entry.get("table_rows") or []:
        if isinstance(row, list):
            cells = [" ".join(str(cell).split()) for cell in row if str(cell).strip()]
            if cells:
                table_rows.append(cells)
    if not table_rows and region_type == "table":
        table_rows = _infer_table_rows_from_lines(lines)

    return ScreenshotRegionItem(
        region_id=region_id,
        region_type=region_type,
        label=" ".join(str(entry.get("label") or "").split()).strip(),
        text=region_text,
        lines=lines,
        items=items,
        field_values=field_values,
        table_rows=table_rows,
        heading_level=int(entry.get("heading_level")) if str(entry.get("heading_level") or "").isdigit() else None,
        bbox=_parse_bbox(entry.get("bbox")),
        order_hint=int(entry.get("order_hint")) if str(entry.get("order_hint") or "").isdigit() else None,
        confidence=_to_confidence(entry.get("confidence"), 0.65),
        uncertain=bool(entry.get("uncertain")),
        uncertainty_reason=" ".join(str(entry.get("uncertainty_reason") or "").split()).strip() or None,
    )


def _regions_from_legacy_schema(parsed: dict[str, Any]) -> list[ScreenshotRegionItem]:
    regions: list[ScreenshotRegionItem] = []
    index = 0

    def add(region_type: str, *, text: str = "", label: str = "", lines: list[str] | None = None, items: list[str] | None = None, field_values: list[ScreenshotFieldValueItem] | None = None, table_rows: list[list[str]] | None = None, heading_level: int | None = None, confidence: float = 0.7, uncertain: bool = False, reason: str | None = None) -> None:
        nonlocal index
        index += 1
        regions.append(
            ScreenshotRegionItem(
                region_id=f"legacy-{index}",
                region_type=_normalize_region_type(region_type),
                label=label,
                text=text,
                lines=list(lines or []),
                items=list(items or []),
                field_values=list(field_values or []),
                table_rows=[list(row) for row in (table_rows or [])],
                heading_level=heading_level,
                confidence=confidence,
                uncertain=uncertain,
                uncertainty_reason=reason,
            )
        )

    if parsed.get("title"):
        add("title", text=str(parsed.get("title")), lines=[str(parsed.get("title"))], confidence=0.9)
    for heading in parsed.get("headings") or []:
        if isinstance(heading, dict):
            text = " ".join(str(heading.get("text") or "").split()).strip()
            if text:
                add("heading", text=text, lines=[text], heading_level=int(heading.get("level") or 2), confidence=_to_confidence(heading.get("confidence"), 0.82))
    for section in parsed.get("sections") or []:
        if not isinstance(section, dict):
            continue
        name = " ".join(str(section.get("name") or "").split()).strip()
        details = [" ".join(str(item).split()) for item in (section.get("details") or []) if str(item).strip()]
        add("paragraph", label=name, text=" ".join([name, *details]).strip(), lines=details or ([name] if name else []), confidence=_to_confidence(section.get("confidence"), 0.74))
    for steps in parsed.get("numbered_steps") or []:
        pass
    if parsed.get("numbered_steps"):
        add("numbered_list", items=[str(item).strip() for item in parsed.get("numbered_steps") if str(item).strip()], confidence=0.84)
    for bullet_list in parsed.get("bullet_lists") or []:
        if isinstance(bullet_list, list):
            items = [str(item).strip() for item in bullet_list if str(item).strip()]
            if items:
                add("bullet_list", items=items, confidence=0.78)
    for note in parsed.get("notes") or []:
        if isinstance(note, dict):
            text = " ".join(str(note.get("text") or "").split()).strip()
            if text:
                add(note.get("kind") or "note", text=text, lines=[text], confidence=_to_confidence(note.get("confidence"), 0.72))
    for table in parsed.get("tables") or []:
        if isinstance(table, dict):
            rows = [list(map(str, row)) for row in (table.get("rows") or []) if isinstance(row, list)]
            if rows:
                add("table", label=str(table.get("caption") or "").strip(), table_rows=rows, confidence=_to_confidence(table.get("confidence"), 0.7))
    pairs = _parse_field_values(parsed.get("field_value_pairs"), None)
    if pairs:
        add("field_value_block", field_values=pairs, lines=[f"{pair.field}: {pair.value}" for pair in pairs], confidence=0.8)
    for snippet in parsed.get("code_snippets") or []:
        text = str(snippet).strip()
        if text:
            add("code", text=text, lines=_split_lines(text), confidence=0.83)
    ui_values = [str(v).strip() for v in (parsed.get("ui_labels") or []) if str(v).strip()]
    if ui_values:
        add("ui_control_text", items=ui_values, lines=ui_values, confidence=0.66)
    criteria = [str(v).strip() for v in (parsed.get("acceptance_criteria") or []) if str(v).strip()]
    if criteria:
        add("acceptance_criteria", items=criteria, lines=criteria, confidence=0.79)
    return regions


def _parse_regions(parsed: dict[str, Any]) -> list[ScreenshotRegionItem]:
    raw_regions = parsed.get("regions")
    if isinstance(raw_regions, list) and raw_regions:
        return [_parse_region(entry, index) for index, entry in enumerate(raw_regions)]
    return _regions_from_legacy_schema(parsed)


def _parsed_from_multi_pass(
    *,
    layout_regions: list[ScreenshotLayoutRegion],
    text_blocks: list[ScreenshotTextBlock],
    semantic_blocks: list[ScreenshotSemanticBlock],
    initial_summary: str = "",
) -> dict[str, Any]:
    layout_map = {region.region_id: region for region in layout_regions}
    text_map = {block.region_id: block for block in text_blocks}
    semantic_map = {block.region_id: block for block in semantic_blocks}
    region_entries: list[dict[str, Any]] = []

    def _sort_key(region_id: str) -> tuple[Any, ...]:
        layout = layout_map.get(region_id)
        text_block = text_map.get(region_id)
        semantic = semantic_map.get(region_id)
        bbox = (
            (layout.bbox if layout else None)
            or (text_block.bbox if text_block else None)
            or (semantic.bbox if semantic else None)
        )
        order_hint = (
            layout.order_hint
            if layout and layout.order_hint is not None
            else (
                semantic.order_hint
                if semantic and semantic.order_hint is not None
                else None
            )
        )
        return (
            order_hint if order_hint is not None else 10_000,
            bbox.y if bbox and bbox.y is not None else 10_000.0,
            bbox.x if bbox and bbox.x is not None else 10_000.0,
            region_id,
        )

    ordered_region_ids = sorted(
        set(layout_map) | set(text_map) | set(semantic_map),
        key=_sort_key,
    )
    reading_order = list(ordered_region_ids)

    for region_id in ordered_region_ids:
        layout = layout_map.get(region_id)
        text_block = text_map.get(region_id)
        semantic = semantic_map.get(region_id)
        lines = (
            list(semantic.lines)
            if semantic and semantic.lines
            else (list(text_block.lines) if text_block and text_block.lines else [])
        )
        region_type = (
            semantic.semantic_type
            if semantic is not None
            else _infer_region_type_from_lines_or_text(
                lines=lines,
                text=text_block.raw_text if text_block is not None else "",
                fallback_type=layout.layout_type if layout is not None else (text_block.layout_type if text_block is not None else "unknown"),
            )
        )
        field_values = (
            [pair.model_dump(mode="json") for pair in semantic.field_values]
            if semantic and semantic.field_values
            else (
                [pair.model_dump(mode="json") for pair in _extract_field_values_from_lines(lines, region_id)]
                if region_type == "field_value_block"
                else []
            )
        )
        table_rows = (
            semantic.table_rows
            if semantic and semantic.table_rows
            else (_infer_table_rows_from_lines(lines) if region_type == "table" else [])
        )
        confidence_candidates = [
            semantic.confidence if semantic is not None else 0.0,
            text_block.confidence if text_block is not None else 0.0,
            layout.confidence if layout is not None else 0.0,
        ]
        confidence_candidates = [value for value in confidence_candidates if value > 0]
        uncertainty_reasons = [
            reason
            for reason in (
                semantic.uncertainty_reason if semantic is not None else None,
                text_block.uncertainty_reason if text_block is not None else None,
                layout.uncertainty_reason if layout is not None else None,
            )
            if reason
        ]
        missing_semantic = semantic is None and (text_block is not None or layout is not None)
        region_entries.append(
            {
                "region_id": region_id,
                "region_type": region_type,
                "label": (
                    (semantic.label if semantic else "")
                    or (layout.label if layout else "")
                ),
                "text": (
                    (semantic.text if semantic else "")
                    or (text_block.raw_text if text_block else "")
                ),
                "lines": lines,
                "items": list(semantic.items) if semantic else [],
                "field_values": field_values,
                "table_rows": table_rows,
                "heading_level": semantic.heading_level if semantic else None,
                "bbox": (
                    ((semantic.bbox if semantic else None) or (text_block.bbox if text_block else None) or (layout.bbox if layout else None)).model_dump(mode="json")
                    if ((semantic.bbox if semantic else None) or (text_block.bbox if text_block else None) or (layout.bbox if layout else None))
                    else None
                ),
                "order_hint": layout.order_hint if layout and layout.order_hint is not None else (semantic.order_hint if semantic else None),
                "confidence": round(mean(confidence_candidates), 3) if confidence_candidates else 0.0,
                "uncertain": bool(
                    (semantic.uncertain if semantic else False)
                    or (text_block.uncertain if text_block else False)
                    or (layout.uncertain if layout else False)
                    or missing_semantic
                ),
                "uncertainty_reason": (
                    uncertainty_reasons[0]
                    if uncertainty_reasons
                    else (
                        "No semantic classification was returned for this extracted region."
                        if missing_semantic
                        else None
                    )
                ),
            }
        )

    title = next((entry["text"] for entry in region_entries if entry["region_type"] == "title" and entry["text"]), "")
    headings = [
        {
            "level": entry.get("heading_level") or (1 if entry["region_type"] == "title" else 2),
            "text": entry["text"] or entry["label"],
            "source_region_id": entry["region_id"],
            "confidence": entry["confidence"],
        }
        for entry in region_entries
        if entry["region_type"] in {"title", "heading"} and (entry["text"] or entry["label"])
    ]
    numbered_steps = [
        item
        for entry in region_entries
        if entry["region_type"] == "numbered_list"
        for item in (entry.get("items") or entry.get("lines") or [])
        if str(item).strip()
    ]
    bullet_lists = [
        [item for item in (entry.get("items") or entry.get("lines") or []) if str(item).strip()]
        for entry in region_entries
        if entry["region_type"] == "bullet_list"
    ]
    notes = [
        {
            "kind": "warning" if entry["region_type"] == "warning" else "note",
            "text": entry["text"] or " ".join(entry.get("lines") or []),
            "source_region_id": entry["region_id"],
            "confidence": entry["confidence"],
        }
        for entry in region_entries
        if entry["region_type"] in {"note", "warning"} and (entry["text"] or entry.get("lines"))
    ]
    tables = [
        {
            "caption": entry["label"],
            "headers": entry["table_rows"][0] if len(entry["table_rows"]) > 1 else [],
            "rows": entry["table_rows"][1:] if len(entry["table_rows"]) > 1 else entry["table_rows"],
            "source_region_id": entry["region_id"],
            "confidence": entry["confidence"],
        }
        for entry in region_entries
        if entry["region_type"] == "table" and entry.get("table_rows")
    ]
    field_value_pairs = [
        pair
        for entry in region_entries
        if entry["region_type"] == "field_value_block"
        for pair in entry.get("field_values") or []
    ]
    ui_labels = [
        item
        for entry in region_entries
        if entry["region_type"] == "ui_control_text"
        for item in (entry.get("items") or entry.get("lines") or [])
        if str(item).strip()
    ]
    acceptance_criteria = [
        item
        for entry in region_entries
        if entry["region_type"] == "acceptance_criteria"
        for item in (entry.get("items") or entry.get("lines") or [])
        if str(item).strip()
    ]
    uncertainties = [
        str(entry.get("uncertainty_reason") or "").strip()
        for entry in region_entries
        if entry.get("uncertain") and str(entry.get("uncertainty_reason") or "").strip()
    ]

    return {
        "summary": initial_summary,
        "title": title,
        "regions": region_entries,
        "reading_order": reading_order,
        "headings": headings,
        "numbered_steps": numbered_steps,
        "bullet_lists": [items for items in bullet_lists if items],
        "notes": notes,
        "tables": tables,
        "field_value_pairs": field_value_pairs,
        "ui_labels": ui_labels,
        "acceptance_criteria": acceptance_criteria,
        "uncertainty_warnings": uncertainties,
    }


def _reconstruct_reading_order(regions: list[ScreenshotRegionItem], parsed: dict[str, Any]) -> list[str]:
    by_id = {region.region_id: region for region in regions}
    explicit = [str(item).strip() for item in (parsed.get("reading_order") or []) if str(item).strip() in by_id]
    if explicit:
        seen = set(explicit)
        remaining = [region.region_id for region in regions if region.region_id not in seen]
        return explicit + remaining

    ordered = sorted(
        regions,
        key=lambda region: (
            region.order_hint if region.order_hint is not None else 10_000,
            region.bbox.y if region.bbox and region.bbox.y is not None else 10_000.0,
            region.bbox.x if region.bbox and region.bbox.x is not None else 10_000.0,
            region.region_id,
        ),
    )
    return [region.region_id for region in ordered]


def _region_lines(region: ScreenshotRegionItem) -> list[str]:
    if region.lines:
        lines = [line for line in region.lines if line]
    elif region.items:
        lines = [item for item in region.items if item]
    else:
        lines = []
    if lines:
        if region.region_type in {"paragraph", "note", "warning", "heading", "title"}:
            return _merge_wrapped_text_lines(lines)
        return [_normalize_inline_text(line) for line in lines if _normalize_inline_text(line)]
    if region.field_values:
        return [f"{pair.field}: {pair.value}".strip(": ") for pair in region.field_values if pair.field or pair.value]
    if region.table_rows:
        return [" | ".join(row) for row in region.table_rows if row]
    if region.text:
        return _merge_wrapped_text_lines(_split_lines(region.text) or [region.text])
    return []


def _derive_hierarchy(
    regions: list[ScreenshotRegionItem],
    reading_order: list[str],
    parsed: dict[str, Any],
    title: str,
) -> list[ScreenshotHierarchyNode]:
    if isinstance(parsed.get("semantic_hierarchy"), list) and parsed.get("semantic_hierarchy"):
        nodes: list[ScreenshotHierarchyNode] = []
        for index, entry in enumerate(parsed["semantic_hierarchy"]):
            if not isinstance(entry, dict):
                continue
            nodes.append(
                ScreenshotHierarchyNode(
                    node_id=str(entry.get("node_id") or f"node-{index + 1}").strip() or f"node-{index + 1}",
                    title=" ".join(str(entry.get("title") or "").split()).strip(),
                    level=max(1, int(entry.get("level") or 1)),
                    purpose=" ".join(str(entry.get("purpose") or "").split()).strip(),
                    region_ids=[str(item).strip() for item in (entry.get("region_ids") or []) if str(item).strip()],
                    confidence=_to_confidence(entry.get("confidence"), 0.74),
                )
            )
        if nodes:
            return nodes

    by_id = {region.region_id: region for region in regions}
    nodes: list[ScreenshotHierarchyNode] = []
    if title:
        title_region = next((region for region in regions if region.region_type == "title"), None)
        nodes.append(
            ScreenshotHierarchyNode(
                node_id="root-title",
                title=title,
                level=1,
                purpose="Top-level screenshot title",
                region_ids=[title_region.region_id] if title_region else [],
                confidence=title_region.confidence if title_region else 0.9,
            )
        )

    for region_id in reading_order:
        region = by_id.get(region_id)
        if region is None or region.region_type not in {"title", "heading"}:
            continue
        heading_text = region.text or region.label or " ".join(_region_lines(region)[:1]).strip()
        if not heading_text:
            continue
        if title and heading_text.casefold() == title.casefold():
            continue
        nodes.append(
            ScreenshotHierarchyNode(
                node_id=f"heading-{region.region_id}",
                title=heading_text,
                level=region.heading_level or (2 if region.region_type == "heading" else 1),
                purpose="Inferred heading from screenshot layout",
                region_ids=[region.region_id],
                confidence=region.confidence,
            )
        )
    return nodes


def _derive_sections(
    regions: list[ScreenshotRegionItem],
    reading_order: list[str],
    hierarchy: list[ScreenshotHierarchyNode],
    parsed: dict[str, Any],
) -> list[ScreenshotSectionItem]:
    if isinstance(parsed.get("sections"), list) and parsed.get("sections"):
        sections: list[ScreenshotSectionItem] = []
        for section in parsed["sections"]:
            if not isinstance(section, dict):
                continue
            sections.append(
                ScreenshotSectionItem(
                    name=" ".join(str(section.get("name") or "").split()).strip(),
                    purpose=" ".join(str(section.get("purpose") or "").split()).strip(),
                    details=[str(item).strip() for item in (section.get("details") or []) if str(item).strip()],
                    confidence=_to_confidence(section.get("confidence"), 0.74),
                    source_region_ids=[str(item).strip() for item in (section.get("source_region_ids") or []) if str(item).strip()],
                )
            )
        if sections:
            return sections

    by_id = {region.region_id: region for region in regions}
    heading_ids = {node.region_ids[0]: node for node in hierarchy if node.region_ids}
    sections: list[ScreenshotSectionItem] = []
    current: ScreenshotSectionItem | None = None
    consumed: set[str] = set()

    for region_id in reading_order:
        region = by_id.get(region_id)
        if region is None:
            continue
        if region.region_type in {"title"}:
            continue
        if region.uncertain and region.confidence < _MIN_REGION_CONFIDENCE:
            explicit_structured_signal = False
            if region.region_type == "field_value_block":
                explicit_structured_signal = bool(
                    region.field_values
                    or _extract_field_values_from_lines(region.lines or region.items, region.region_id)
                )
            elif region.region_type == "table":
                explicit_structured_signal = bool(region.table_rows)
            elif region.region_type in {"numbered_list", "bullet_list", "acceptance_criteria", "ui_control_text"}:
                explicit_structured_signal = bool(region.items or _region_lines(region))
            if not explicit_structured_signal:
                continue
        if region.region_id in heading_ids:
            node = heading_ids[region.region_id]
            current = ScreenshotSectionItem(
                name=node.title,
                purpose=node.purpose or f"Content under {node.title}",
                details=[],
                confidence=node.confidence,
                source_region_ids=list(node.region_ids),
            )
            sections.append(current)
            consumed.add(region.region_id)
            continue

        detail_lines = _region_lines(region)
        if region.region_type in {"numbered_list", "bullet_list", "acceptance_criteria", "ui_control_text"}:
            detail_lines = region.items or detail_lines
        if region.region_type == "paragraph":
            detail_lines = _merge_wrapped_text_lines(detail_lines)
        if region.region_type == "field_value_block":
            detail_lines = (
                [f"{pair.field}: {pair.value}".strip(": ") for pair in region.field_values if pair.field or pair.value]
                or [f"{pair.field}: {pair.value}".strip(": ") for pair in _extract_field_values_from_lines(region.lines or region.items, region.region_id) if pair.field or pair.value]
                or detail_lines
            )
        if region.region_type == "table":
            detail_lines = [" | ".join(row) for row in region.table_rows[:8]]
        if region.region_type == "ui_control_text":
            detail_lines = _structure_preserving_ui_lines(detail_lines)
        if not detail_lines:
            continue

        if current is None:
            current = ScreenshotSectionItem(
                name=region.label or "Overview",
                purpose="Recovered content from screenshot regions without a clear heading.",
                details=[],
                confidence=region.confidence,
                source_region_ids=[],
            )
            sections.append(current)
        current.details.extend(detail_lines[:12])
        current.source_region_ids.append(region.region_id)
        current.confidence = max(current.confidence or 0.0, region.confidence)
        consumed.add(region.region_id)

    return sections


def _derive_paragraphs(regions: list[ScreenshotRegionItem], parsed: dict[str, Any]) -> list[ScreenshotParagraphItem]:
    paragraphs: list[ScreenshotParagraphItem] = []
    raw_items = parsed.get("paragraphs")
    if isinstance(raw_items, list):
        for entry in raw_items:
            if not isinstance(entry, dict):
                continue
            text = " ".join(str(entry.get("text") or "").split()).strip()
            if not text:
                continue
            paragraphs.append(
                ScreenshotParagraphItem(
                    text=text,
                    confidence=_to_confidence(entry.get("confidence"), 0.7),
                    source_region_id=str(entry.get("source_region_id") or "").strip() or None,
                )
            )
    if paragraphs:
        return paragraphs

    for region in regions:
        if region.region_type != "paragraph":
            continue
        if region.uncertain and region.confidence < _MIN_REGION_CONFIDENCE:
            continue
        text = " ".join(_merge_wrapped_text_lines(region.lines or _split_lines(region.text) or [region.text])).strip()
        if not text:
            continue
        if _looks_like_stackable_field_label(text) and ":" not in text:
            continue
        if text.casefold() in _BUTTON_LABELS:
            continue
        paragraphs.append(
            ScreenshotParagraphItem(
                text=text,
                confidence=region.confidence,
                source_region_id=region.region_id,
            )
        )
    return paragraphs


def _derive_acceptance_criteria(regions: list[ScreenshotRegionItem], parsed: dict[str, Any]) -> list[str]:
    explicit = [str(item).strip() for item in (parsed.get("acceptance_criteria") or []) if str(item).strip()]
    if explicit:
        return _dedupe_preserve_order(explicit)

    values: list[str] = []
    for region in regions:
        if region.region_type != "acceptance_criteria":
            continue
        values.extend(region.items or _region_lines(region))
    return _dedupe_preserve_order(values)


def _derive_flat_substeps(
    regions: list[ScreenshotRegionItem],
    parsed: dict[str, Any],
    *,
    procedural_model: ScreenshotProceduralModel | None,
) -> list[ScreenshotProceduralSubstep]:
    if procedural_model and procedural_model.steps:
        return [
            substep.model_copy()
            for step in procedural_model.steps
            for substep in step.substeps
            if substep.command.strip()
        ]

    flat_substeps: list[ScreenshotProceduralSubstep] = []
    raw_model = parsed.get("procedural_model")
    if isinstance(raw_model, dict):
        try:
            proc = ScreenshotProceduralModel.model_validate(raw_model)
        except Exception:
            proc = None
        if proc is not None and proc.steps:
            return [
                substep.model_copy()
                for step in proc.steps
                for substep in step.substeps
                if substep.command.strip()
            ]

    for region in regions:
        if region.region_type != "numbered_list":
            continue
        for raw_line in region.lines or region.items:
            line = str(raw_line or "").rstrip()
            if not line.strip():
                continue
            match = _INDENTED_ORDERED_STEP_RE.match(line)
            if not match:
                continue
            flat_substeps.append(
                ScreenshotProceduralSubstep(
                    marker=match.group(1),
                    command=match.group(2).strip(),
                    confidence=max(0.0, min(1.0, region.confidence - 0.03)),
                    source_region_id=region.region_id,
                )
            )
    return flat_substeps


def _derive_unresolved_blocks(regions: list[ScreenshotRegionItem]) -> list[ScreenshotUnresolvedBlock]:
    unresolved: list[ScreenshotUnresolvedBlock] = []
    for region in regions:
        low_confidence = region.confidence < _MIN_REGION_CONFIDENCE
        ambiguous = region.uncertain or low_confidence or region.region_type == "unknown"
        if not ambiguous:
            continue
        lines = _region_lines(region)
        raw_text = " ".join(lines).strip()
        if not raw_text and not region.text:
            raw_text = (region.label or "").strip()
        if not raw_text:
            continue
        reason = region.uncertainty_reason or (
            "Low-confidence extraction; preserve as unresolved instead of inferring structure."
            if low_confidence
            else "Ambiguous screenshot region."
        )
        unresolved.append(
            ScreenshotUnresolvedBlock(
                region_id=region.region_id,
                candidate_type=region.region_type,
                raw_text=raw_text,
                lines=lines,
                reason=reason,
                confidence=region.confidence,
            )
        )
    return unresolved


def _derive_field_confidence(parsed: dict[str, Any], regions: list[ScreenshotRegionItem]) -> dict[str, float]:
    field_confidence: dict[str, float] = {}
    for key, value in (parsed.get("field_confidence") or {}).items():
        try:
            field_confidence[str(key)] = _to_confidence(value, 0.5)
        except Exception:
            continue
    if regions and "regions" not in field_confidence:
        field_confidence["regions"] = round(mean(region.confidence for region in regions), 3)
    return field_confidence


def _ui_hints_from_parsed(parsed: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    for key in ("ui_labels", "button_names", "menu_names"):
        hints.extend(str(item).strip() for item in (parsed.get(key) or []) if str(item).strip())
    return _dedupe_preserve_order(hints)


def _extract_ui_controls_from_text(text: str, ui_hints: list[str]) -> list[str]:
    matched: list[str] = []
    haystack = text or ""
    for hint in sorted(ui_hints, key=len, reverse=True):
        if hint and hint in haystack:
            matched.append(hint)
    return _dedupe_preserve_order(matched)


def _procedural_content(
    *,
    text: str,
    kind: str,
    confidence: float,
    source_region_id: str | None,
) -> ScreenshotProceduralContentItem:
    return ScreenshotProceduralContentItem(
        text=" ".join((text or "").split()).strip(),
        kind=kind,  # type: ignore[arg-type]
        confidence=max(0.0, min(1.0, confidence)),
        source_region_id=source_region_id,
    )


def _raw_lines_for_region(region_id: str, text_blocks: list[ScreenshotTextBlock], semantic: ScreenshotSemanticBlock) -> list[str]:
    text_block = next((block for block in text_blocks if block.region_id == region_id), None)
    if text_block and text_block.raw_text:
        raw_lines = [line.rstrip("\r") for line in text_block.raw_text.splitlines() if line.strip()]
        if raw_lines:
            return raw_lines
    if semantic.lines:
        return list(semantic.lines)
    if semantic.items:
        return list(semantic.items)
    if semantic.text:
        return [semantic.text]
    return []


def _steps_from_semantic_block(
    block: ScreenshotSemanticBlock,
    *,
    text_blocks: list[ScreenshotTextBlock],
    ui_hints: list[str],
) -> list[ScreenshotProceduralStep]:
    raw_lines = _raw_lines_for_region(block.region_id, text_blocks, block)
    steps: list[ScreenshotProceduralStep] = []
    current: ScreenshotProceduralStep | None = None

    for raw_line in raw_lines:
        line = raw_line.rstrip()
        if not line.strip():
            continue
        substep_match = _INDENTED_ORDERED_STEP_RE.match(line)
        if substep_match and current is not None:
            marker = substep_match.group(1)
            command = substep_match.group(2).strip()
            current.substeps.append(
                ScreenshotProceduralSubstep(
                    marker=marker,
                    command=command,
                    confidence=max(0.0, min(1.0, block.confidence - 0.03)),
                    source_region_id=block.region_id,
                )
            )
            continue

        step_match = _ORDERED_STEP_RE.match(line)
        if step_match:
            marker = step_match.group(1)
            command = step_match.group(2).strip()
            current = ScreenshotProceduralStep(
                marker=marker,
                command=command,
                ui_controls=_extract_ui_controls_from_text(command, ui_hints),
                confidence=block.confidence,
                source_region_id=block.region_id,
            )
            steps.append(current)
            continue

        if current is not None:
            current.info_lines.append(" ".join(line.split()).strip())
            continue

    if not steps and block.items:
        for idx, item in enumerate(block.items, start=1):
            command = " ".join(item.split()).strip()
            if not command:
                continue
            steps.append(
                ScreenshotProceduralStep(
                    marker=f"{idx}.",
                    command=command,
                    ui_controls=_extract_ui_controls_from_text(command, ui_hints),
                    confidence=block.confidence,
                    source_region_id=block.region_id,
                )
            )
    return steps


def _derive_procedural_model(
    semantic_blocks: list[ScreenshotSemanticBlock],
    *,
    text_blocks: list[ScreenshotTextBlock],
    title: str,
    parsed: dict[str, Any],
) -> ScreenshotProceduralModel | None:
    if not semantic_blocks:
        return None

    ui_hints = _ui_hints_from_parsed(parsed)
    prerequisites: list[ScreenshotProceduralContentItem] = []
    context_items: list[ScreenshotProceduralContentItem] = []
    steps: list[ScreenshotProceduralStep] = []
    notes: list[ScreenshotNoteItem] = []
    result_items: list[ScreenshotProceduralContentItem] = []
    examples: list[ScreenshotProceduralContentItem] = []
    ambiguity_notes: list[str] = []

    mode: str = "context"
    seen_first_step = False
    current_step: ScreenshotProceduralStep | None = None

    for block in semantic_blocks:
        candidate_text = block.text or " ".join(block.lines or block.items).strip()
        lower_text = candidate_text.lower()
        raw_lines = [line for line in _raw_lines_for_region(block.region_id, text_blocks, block) if line.strip()]

        if block.semantic_type == "title":
            continue
        if block.semantic_type == "heading":
            heading_kind = "context"
            if _PREREQ_HEADING_RE.search(lower_text):
                mode = "prerequisite"
                heading_kind = "prerequisite"
            elif _RESULT_HEADING_RE.search(lower_text):
                mode = "result"
                heading_kind = "result"
                current_step = None
            elif _EXAMPLE_HEADING_RE.search(lower_text):
                mode = "example"
                heading_kind = "example"
                current_step = None
            elif _CONTEXT_HEADING_RE.search(lower_text):
                mode = "context"
                heading_kind = "context"
                current_step = None
            else:
                if seen_first_step:
                    current_step = None

            trailing_lines: list[str] = []
            for line in raw_lines:
                normalized = " ".join(line.split()).strip().rstrip(":")
                if normalized.casefold() == candidate_text.strip().rstrip(":").casefold():
                    continue
                trailing_lines.append(" ".join(line.split()).strip())

            if trailing_lines:
                if heading_kind == "prerequisite":
                    target_bucket = prerequisites
                elif heading_kind == "result":
                    target_bucket = result_items
                elif heading_kind == "example":
                    target_bucket = examples
                else:
                    target_bucket = context_items
                for line in trailing_lines:
                    target_bucket.append(
                        _procedural_content(
                            text=line,
                            kind="context" if heading_kind == "context" else heading_kind,
                            confidence=block.confidence,
                            source_region_id=block.region_id,
                        )
                    )
            continue

        if block.semantic_type in {"note", "warning"}:
            note_text = candidate_text
            if note_text:
                notes.append(
                    ScreenshotNoteItem(
                        kind="warning" if block.semantic_type == "warning" else "note",
                        text=note_text,
                        confidence=block.confidence,
                        source_region_id=block.region_id,
                    )
                )
            continue

        if block.semantic_type == "code":
            examples.append(
                _procedural_content(
                    text="\n".join(_raw_lines_for_region(block.region_id, text_blocks, block)),
                    kind="code",
                    confidence=block.confidence,
                    source_region_id=block.region_id,
                )
            )
            continue

        if block.semantic_type == "table":
            table_text = " | ".join(block.table_rows[0]) if block.table_rows else candidate_text
            if table_text:
                examples.append(
                    _procedural_content(
                        text=table_text,
                        kind="example",
                        confidence=block.confidence,
                        source_region_id=block.region_id,
                    )
                )
            continue

        if block.semantic_type == "numbered_list":
            derived_steps = _steps_from_semantic_block(block, text_blocks=text_blocks, ui_hints=ui_hints)
            if derived_steps:
                steps.extend(derived_steps)
                current_step = steps[-1]
                seen_first_step = True
            else:
                ambiguity_notes.append("A numbered block was detected but could not be reliably split into individual steps.")
            continue

        if block.semantic_type == "ui_control_text":
            if current_step is not None:
                current_step.ui_controls = _dedupe_preserve_order(current_step.ui_controls + list(block.items or block.lines))
            continue

        paragraph_lines = raw_lines
        if not paragraph_lines:
            continue

        if block.semantic_type == "acceptance_criteria":
            if seen_first_step:
                for line in paragraph_lines:
                    result_items.append(
                        _procedural_content(
                            text=line,
                            kind="result",
                            confidence=block.confidence,
                            source_region_id=block.region_id,
                        )
                    )
            continue

        if seen_first_step and current_step is not None and block.semantic_type == "paragraph" and mode not in {"result", "example"}:
            current_step.info_lines.extend(" ".join(line.split()).strip() for line in paragraph_lines if line.strip())
            continue

        target_kind = mode
        if not seen_first_step and _PREREQ_HEADING_RE.search(lower_text):
            target_kind = "prerequisite"
        elif not seen_first_step and mode == "context":
            target_kind = "context"
        elif seen_first_step and mode == "result":
            target_kind = "result"
        elif seen_first_step and mode == "example":
            target_kind = "example"

        target_bucket: list[ScreenshotProceduralContentItem]
        if target_kind == "prerequisite":
            target_bucket = prerequisites
        elif target_kind == "result":
            target_bucket = result_items
        elif target_kind == "example":
            target_bucket = examples
        else:
            target_bucket = context_items

        item_kind = "command" if block.semantic_type == "paragraph" and any(ctrl in candidate_text for ctrl in ui_hints) and target_kind == "example" else target_kind
        for line in paragraph_lines:
            target_bucket.append(
                _procedural_content(
                    text=line,
                    kind="context" if item_kind not in {"prerequisite", "result", "example", "command", "code"} else item_kind,
                    confidence=block.confidence,
                    source_region_id=block.region_id,
                )
            )

    if not steps and any(block.semantic_type == "numbered_list" for block in semantic_blocks):
        ambiguity_notes.append("The screenshot looks procedural, but the numbered content was too noisy to recover reliable steps.")

    if not (steps or prerequisites or context_items or notes or result_items or examples):
        return None

    confidence_values = [item.confidence for item in prerequisites + context_items + result_items + examples]
    confidence_values.extend(step.confidence for step in steps)
    confidence_values.extend(note.confidence or 0.0 for note in notes)
    model_confidence = round(mean([value for value in confidence_values if value > 0]) if confidence_values else 0.4, 3)
    return ScreenshotProceduralModel(
        title=title,
        prerequisites=prerequisites,
        context=context_items,
        steps=steps,
        notes=notes,
        result=result_items,
        examples=examples,
        confidence=model_confidence,
        ambiguity_notes=_dedupe_preserve_order(ambiguity_notes),
    )


_ALLOWED_SETTINGS_CT = frozenset({"text", "dropdown", "checkbox", "radio", "toggle", "table", "unknown"})


def _normalize_settings_control_type(raw: Any) -> str:
    v = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "check_box": "checkbox",
        "drop_down": "dropdown",
        "select": "dropdown",
        "combo": "dropdown",
        "combobox": "dropdown",
        "switch": "toggle",
        "boolean": "checkbox",
    }
    v = aliases.get(v, v)
    return v if v in _ALLOWED_SETTINGS_CT else "unknown"


def _settings_reference_nonempty(model: ScreenshotSettingsReferenceModel | None) -> bool:
    if model is None:
        return False
    if model.tabs or model.active_tab or model.helper_text or model.parameter_tables:
        return True
    return any(
        (sec.title or sec.tab or sec.fields or sec.parameter_tables or sec.description) for sec in model.sections
    )


def _coerce_option_selected(raw: Any) -> bool | None:
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        if raw == 1:
            return True
        if raw == 0:
            return False
        return None
    s = str(raw).strip().lower()
    if s in {"true", "yes", "y", "on", "selected", "checked"}:
        return True
    if s in {"false", "no", "n", "off", "unselected"}:
        return False
    return None


def _parse_settings_table_dict(entry: dict[str, Any]) -> ScreenshotTableItem | None:
    caption = " ".join(str(entry.get("caption") or "").split()).strip()
    headers = [str(c).strip() for c in (entry.get("headers") or []) if str(c).strip()]
    rows: list[list[str]] = []
    for row in entry.get("rows") or entry.get("table_rows") or []:
        if isinstance(row, list):
            cells = [" ".join(str(c).split()).strip() for c in row]
            if any(cells):
                rows.append(cells)
    if not rows and not headers:
        return None
    return ScreenshotTableItem(
        caption=caption,
        headers=headers,
        rows=rows,
        confidence=_to_confidence(entry.get("confidence"), 0.68),
        source_region_id=str(entry.get("source_region_id") or "").strip() or None,
    )


def _parse_settings_reference_payload(raw: Any) -> ScreenshotSettingsReferenceModel | None:
    if not isinstance(raw, dict):
        return None
    try:
        title = " ".join(str(raw.get("title") or "").split()).strip()
        tabs = _dedupe_preserve_order([str(t).strip() for t in (raw.get("tabs") or []) if str(t).strip()])
        active_tab = " ".join(str(raw.get("active_tab") or "").split()).strip() or None
        helper_text = [str(h).strip() for h in (raw.get("helper_text") or []) if str(h).strip()]

        sections: list[ScreenshotSettingsSection] = []
        for sec in raw.get("sections") or []:
            if not isinstance(sec, dict):
                continue
            fields: list[ScreenshotSettingField] = []
            for fd in sec.get("fields") or []:
                if not isinstance(fd, dict):
                    continue
                label = " ".join(str(fd.get("label") or "").split()).strip()
                value = " ".join(str(fd.get("value") or "").split()).strip()
                opts: list[ScreenshotSettingOption] = []
                for op in fd.get("options") or []:
                    if not isinstance(op, dict):
                        continue
                    ol = " ".join(str(op.get("label") or "").split()).strip()
                    if not ol:
                        continue
                    opts.append(
                        ScreenshotSettingOption(
                            label=ol,
                            selected=_coerce_option_selected(op.get("selected")),
                            confidence=_to_confidence(op.get("confidence"), 0.72),
                            source_region_id=str(op.get("source_region_id") or "").strip() or None,
                        )
                    )
                htx = [str(x).strip() for x in (fd.get("helper_text") or []) if str(x).strip()]
                if not htx and fd.get("description"):
                    ds = " ".join(str(fd.get("description") or "").split()).strip()
                    if ds:
                        htx = [ds]
                if not label and not value and not opts:
                    continue
                fields.append(
                    ScreenshotSettingField(
                        label=label,
                        value=value,
                        control_type=_normalize_settings_control_type(fd.get("control_type")),  # type: ignore[arg-type]
                        helper_text=htx,
                        options=opts,
                        confidence=_to_confidence(fd.get("confidence"), 0.72),
                        source_region_id=str(fd.get("source_region_id") or "").strip() or None,
                    )
                )
            param_tables: list[ScreenshotTableItem] = []
            for tb in sec.get("parameter_tables") or []:
                if isinstance(tb, dict):
                    st = _parse_settings_table_dict(tb)
                    if st:
                        param_tables.append(st)
            stitle = " ".join(str(sec.get("title") or "").split()).strip()
            stab = " ".join(str(sec.get("tab") or "").split()).strip() or None
            desc = [str(x).strip() for x in (sec.get("description") or []) if str(x).strip()]
            if not stitle and not fields and not param_tables and not desc and not stab:
                continue
            sections.append(
                ScreenshotSettingsSection(
                    title=stitle,
                    tab=stab,
                    description=desc,
                    fields=fields,
                    parameter_tables=param_tables,
                    confidence=_to_confidence(sec.get("confidence"), 0.72),
                    source_region_ids=[str(x).strip() for x in (sec.get("source_region_ids") or []) if str(x).strip()],
                )
            )

        top_tables: list[ScreenshotTableItem] = []
        for tb in raw.get("parameter_tables") or []:
            if isinstance(tb, dict):
                st = _parse_settings_table_dict(tb)
                if st:
                    top_tables.append(st)

        amb = [str(x).strip() for x in (raw.get("ambiguity_notes") or []) if str(x).strip()]
        model = ScreenshotSettingsReferenceModel(
            title=title,
            tabs=tabs,
            active_tab=active_tab,
            sections=sections,
            helper_text=helper_text,
            parameter_tables=top_tables,
            confidence=_to_confidence(raw.get("confidence"), 0.72),
            ambiguity_notes=amb,
        )
        return model if _settings_reference_nonempty(model) else None
    except Exception:
        return None


def _guess_control_from_value(value: str, label: str) -> str:
    v = (value or "").strip()
    lab = (label or "").strip()
    combined = f"{lab} {v}".lower()
    if _DROPDOWN_HINT_RE.search(combined) or "▼" in v or "▾" in v:
        return "dropdown"
    if _CHECKBOX_LINE_RE.match(v):
        return "checkbox"
    if _RADIO_LINE_RE.match(v):
        return "radio"
    return "text" if v else "unknown"


def _infer_tabs_from_regions(regions: list[ScreenshotRegionItem]) -> list[str]:
    tab_candidates: list[str] = []
    for region in regions:
        if region.region_type != "ui_control_text":
            continue
        region_values = list(region.items or region.lines)
        multi_control_region = len(region_values) >= 2
        for raw in region_values:
            value = _normalize_inline_text(raw)
            if not value:
                continue
            if value.casefold() in _BUTTON_LABELS:
                continue
            if _CHECKBOX_LINE_RE.match(value) or _RADIO_LINE_RE.match(value):
                continue
            if _looks_like_stackable_field_label(value) and not value.endswith(":") and not multi_control_region:
                continue
            if 1 <= len(value.split()) <= 3:
                tab_candidates.append(value)
    deduped = _dedupe_preserve_order(tab_candidates)
    return deduped[:8] if len(deduped) >= 2 else []


def _consume_field_like_line_indices(lines: list[str]) -> set[int]:
    consumed: set[int] = set()
    for index, raw in enumerate(lines):
        line = _normalize_inline_text(raw)
        if not line:
            continue
        if _CHECKBOX_LINE_RE.match(line) or _RADIO_LINE_RE.match(line) or _COLON_FIELD_RE.match(line):
            consumed.add(index)
            continue
        column_parts = _split_tabular_row(raw)
        if len(column_parts) >= 2 and len(column_parts[0].split()) <= 8:
            consumed.add(index)
            continue
        next_line = lines[index + 1] if index + 1 < len(lines) else None
        following_line = lines[index + 2] if index + 2 < len(lines) else None
        if next_line and _can_pair_stacked_field_value(line, next_line, following_line):
            consumed.add(index)
            consumed.add(index + 1)
    return consumed


def _derive_settings_reference_model(
    regions: list[ScreenshotRegionItem],
    reading_order: list[str],
    parsed: dict[str, Any],
) -> ScreenshotSettingsReferenceModel | None:
    by_id = {region.region_id: region for region in regions}
    sections_out: list[ScreenshotSettingsSection] = []
    current = ScreenshotSettingsSection(
        title="",
        fields=[],
        parameter_tables=[],
        description=[],
        confidence=0.62,
        source_region_ids=[],
    )

    def flush_current() -> None:
        nonlocal current
        if current.fields or current.parameter_tables or current.description or (current.title and current.title.strip()):
            if not (current.title or "").strip():
                current.title = "Form and settings"
            sections_out.append(current)
        current = ScreenshotSettingsSection(
            title="",
            fields=[],
            parameter_tables=[],
            description=[],
            confidence=0.62,
            source_region_ids=[],
        )

    for rid in reading_order:
        region = by_id.get(rid)
        if region is None:
            continue
        if region.region_type == "title":
            continue
        if region.region_type == "heading":
            flush_current()
            current = ScreenshotSettingsSection(
                title=(region.text or region.label or "Settings").strip()[:200],
                fields=[],
                parameter_tables=[],
                description=[],
                confidence=region.confidence,
                source_region_ids=[region.region_id],
            )
            continue
        if region.region_type == "field_value_block":
            region_lines = region.lines or _region_lines(region)
            region_pairs = region.field_values or _extract_field_values_from_lines(region_lines, region.region_id)
            inferred_rows = _infer_table_rows_from_lines(region_lines)
            if inferred_rows and len(inferred_rows) >= 2 and len(region_pairs) <= 1:
                current.parameter_tables.append(
                    ScreenshotTableItem(
                        caption=region.label or "Parameters",
                        headers=inferred_rows[0],
                        rows=inferred_rows[1:],
                        confidence=max(region.confidence - 0.04, 0.45),
                        source_region_id=region.region_id,
                    )
                )
            consumed_indices = _consume_field_like_line_indices(region_lines)
            helper_lines = [
                _normalize_inline_text(line)
                for index, line in enumerate(region_lines)
                if index not in consumed_indices
                and _normalize_inline_text(line)
                and not _looks_like_stackable_field_label(line)
                and not _is_list_like_line(line)
            ]
            for pair_index, pair in enumerate(region_pairs):
                if not pair.field and not pair.value:
                    continue
                ct = _guess_control_from_value(pair.value, pair.field)
                current.fields.append(
                    ScreenshotSettingField(
                        label=pair.field,
                        value=pair.value,
                        control_type=ct,  # type: ignore[arg-type]
                        helper_text=helper_lines if helper_lines and pair_index == len(region_pairs) - 1 else [],
                        confidence=pair.confidence or 0.64,
                        source_region_id=pair.source_region_id or region.region_id,
                    )
                )
            for line in region_lines:
                cm = _CHECKBOX_LINE_RE.match(line)
                if cm:
                    selected = bool(cm.group("box") and cm.group("box").strip().lower() == "x")
                    label = (cm.group("label") or "").strip()
                    if label:
                        current.fields.append(
                            ScreenshotSettingField(
                                label=label,
                                value="On" if selected else "Off",
                                control_type="checkbox",
                                options=[
                                    ScreenshotSettingOption(
                                        label=label,
                                        selected=selected,
                                        confidence=region.confidence * 0.95,
                                        source_region_id=region.region_id,
                                    )
                                ],
                                confidence=region.confidence * 0.9,
                                source_region_id=region.region_id,
                            )
                        )
                rm = _RADIO_LINE_RE.match(line)
                if rm:
                    selected = bool(rm.group("radio") and rm.group("radio").strip().lower() == "x")
                    label = (rm.group("label") or "").strip()
                    if label:
                        current.fields.append(
                            ScreenshotSettingField(
                                label=label,
                                value="Selected" if selected else "Not selected",
                                control_type="radio",
                                options=[
                                    ScreenshotSettingOption(
                                        label=label,
                                        selected=selected,
                                        confidence=region.confidence * 0.95,
                                        source_region_id=region.region_id,
                                    )
                                ],
                                confidence=region.confidence * 0.9,
                                source_region_id=region.region_id,
                            )
                        )
            current.source_region_ids.append(region.region_id)
            continue
        if region.region_type == "table" and region.table_rows:
            tbl = ScreenshotTableItem(
                caption=region.label,
                headers=region.table_rows[0] if len(region.table_rows) > 1 else [],
                rows=region.table_rows[1:] if len(region.table_rows) > 1 else region.table_rows,
                confidence=region.confidence,
                source_region_id=region.region_id,
            )
            current.parameter_tables.append(tbl)
            current.source_region_ids.append(region.region_id)
            continue
        if region.region_type == "ui_control_text":
            for item in region.items or region.lines:
                line = str(item).strip()
                if not line:
                    continue
                cm = _CHECKBOX_LINE_RE.match(line)
                if cm:
                    selected = bool(cm.group("box") and cm.group("box").strip().lower() == "x")
                    label = (cm.group("label") or "").strip()
                    if label:
                        current.fields.append(
                            ScreenshotSettingField(
                                label=label,
                                value="On" if selected else "Off",
                                control_type="checkbox",
                                confidence=region.confidence * 0.88,
                                source_region_id=region.region_id,
                            )
                        )
                    continue
                rm = _RADIO_LINE_RE.match(line)
                if rm:
                    selected = bool(rm.group("radio") and rm.group("radio").strip().lower() == "x")
                    label = (rm.group("label") or "").strip()
                    if label:
                        current.fields.append(
                            ScreenshotSettingField(
                                label=label,
                                value="Selected" if selected else "Not selected",
                                control_type="radio",
                                confidence=region.confidence * 0.88,
                                source_region_id=region.region_id,
                            )
                        )
            if region.region_id not in current.source_region_ids:
                current.source_region_ids.append(region.region_id)
            continue
        if region.region_type == "paragraph":
            text = (region.text or " ".join(region.lines)).strip()
            if 0 < len(text) < 220:
                current.description.append(text)
                current.source_region_ids.append(region.region_id)

    flush_current()

    tabs = _dedupe_preserve_order([str(t).strip() for t in (parsed.get("tabs") or []) if str(t).strip()])
    active = str(parsed.get("active_tab") or "").strip() or None
    if not tabs and isinstance(parsed.get("settings_reference"), dict):
        sr = parsed["settings_reference"]
        if isinstance(sr, dict):
            tabs = _dedupe_preserve_order([str(t).strip() for t in (sr.get("tabs") or []) if str(t).strip()])
            active = str(sr.get("active_tab") or "").strip() or None
    if not tabs:
        tabs = _infer_tabs_from_regions(regions)
    if tabs and active is None:
        active = tabs[0]

    if not sections_out:
        return None

    field_count = sum(len(s.fields) for s in sections_out)
    table_count = sum(len(s.parameter_tables) for s in sections_out)
    if field_count == 0 and table_count == 0:
        flat = _parse_field_values(parsed.get("field_value_pairs"), None)
        if len(flat) < 2:
            return None
        bucket = ScreenshotSettingsSection(
            title="Form and settings",
            fields=[
                ScreenshotSettingField(
                    label=p.field,
                    value=p.value,
                    control_type=_guess_control_from_value(p.value, p.field),  # type: ignore[arg-type]
                    confidence=p.confidence or 0.62,
                    source_region_id=p.source_region_id,
                )
                for p in flat[:40]
                if p.field or p.value
            ],
            confidence=0.6,
        )
        sections_out = [bucket]

    confidences = [s.confidence for s in sections_out if s.confidence]
    model_conf = round(mean(confidences), 3) if confidences else 0.62
    return ScreenshotSettingsReferenceModel(
        title="",
        tabs=tabs,
        active_tab=active,
        sections=sections_out,
        helper_text=[],
        parameter_tables=[],
        confidence=model_conf,
        ambiguity_notes=[],
    )


def _build_structured_from_parsed(parsed: dict[str, Any]) -> ScreenshotContentModel:
    regions = _parse_regions(parsed)
    reading_order = _reconstruct_reading_order(regions, parsed)

    settings_ref = _parse_settings_reference_payload(parsed.get("settings_reference"))
    if not _settings_reference_nonempty(settings_ref):
        settings_ref = _derive_settings_reference_model(regions, reading_order, parsed)

    title = " ".join(str(parsed.get("title") or "").split()).strip()
    if not title:
        title = next((region.text or region.label for region in regions if region.region_type == "title" and (region.text or region.label)), "")
    if not title:
        title = next((region.text for region in regions if region.region_type == "heading" and region.text), "")

    headings: list[ScreenshotHeadingItem] = []
    for heading in parsed.get("headings") or []:
        if isinstance(heading, dict):
            text = " ".join(str(heading.get("text") or "").split()).strip()
            if text:
                headings.append(
                    ScreenshotHeadingItem(
                        level=max(1, int(heading.get("level") or 1)),
                        text=text,
                        confidence=_to_confidence(heading.get("confidence"), 0.78),
                        source_region_id=str(heading.get("source_region_id") or "").strip() or None,
                    )
                )
    if not headings:
        for region in regions:
            if region.region_type in {"title", "heading"} and (region.text or region.label):
                headings.append(
                    ScreenshotHeadingItem(
                        level=region.heading_level or (1 if region.region_type == "title" else 2),
                        text=region.text or region.label,
                        confidence=region.confidence,
                        source_region_id=region.region_id,
                    )
                )

    hierarchy = _derive_hierarchy(regions, reading_order, parsed, title)
    sections = _derive_sections(regions, reading_order, hierarchy, parsed)
    paragraphs = _derive_paragraphs(regions, parsed)

    numbered_steps = [str(item).strip() for item in (parsed.get("numbered_steps") or []) if str(item).strip()]
    if not numbered_steps:
        for region in regions:
            if region.region_type == "numbered_list":
                numbered_steps.extend(region.items or _region_lines(region))
    numbered_steps = _dedupe_preserve_order(numbered_steps)

    bullet_lists: list[list[str]] = []
    for value in parsed.get("bullet_lists") or []:
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
            if items:
                bullet_lists.append(items)
    if not bullet_lists:
        for region in regions:
            if region.region_type == "bullet_list" and (region.items or region.lines):
                bullet_lists.append(_dedupe_preserve_order(region.items or region.lines))

    notes: list[ScreenshotNoteItem] = []
    for note in parsed.get("notes") or []:
        if isinstance(note, dict):
            text = " ".join(str(note.get("text") or "").split()).strip()
            if text:
                notes.append(
                    ScreenshotNoteItem(
                        kind=str(note.get("kind") or "note"),
                        text=text,
                        confidence=_to_confidence(note.get("confidence"), 0.7),
                        source_region_id=str(note.get("source_region_id") or "").strip() or None,
                    )
                )
    if not notes:
        for region in regions:
            if region.region_type in {"note", "warning"}:
                text = region.text or " ".join(_region_lines(region))
                if text:
                    notes.append(
                        ScreenshotNoteItem(
                            kind="warning" if region.region_type == "warning" else "note",
                            text=text,
                            confidence=region.confidence,
                            source_region_id=region.region_id,
                        )
                    )

    tables: list[ScreenshotTableItem] = []
    for table in parsed.get("tables") or []:
        if isinstance(table, dict):
            rows = [list(map(str, row)) for row in (table.get("rows") or []) if isinstance(row, list)]
            headers = [str(cell).strip() for cell in (table.get("headers") or []) if str(cell).strip()]
            if rows or headers:
                tables.append(
                    ScreenshotTableItem(
                        caption=" ".join(str(table.get("caption") or "").split()).strip(),
                        headers=headers,
                        rows=rows,
                        confidence=_to_confidence(table.get("confidence"), 0.68),
                        source_region_id=str(table.get("source_region_id") or "").strip() or None,
                    )
                )
    if not tables:
        for region in regions:
            if region.region_type == "table" and region.table_rows:
                headers = region.table_rows[0] if len(region.table_rows) > 1 else []
                rows = region.table_rows[1:] if headers else region.table_rows
                tables.append(
                    ScreenshotTableItem(
                        caption=region.label,
                        headers=headers,
                        rows=rows,
                        confidence=region.confidence,
                        source_region_id=region.region_id,
                    )
                )

    field_value_pairs = _parse_field_values(parsed.get("field_value_pairs"), None)
    if not field_value_pairs:
        for region in regions:
            if region.field_values:
                field_value_pairs.extend(region.field_values)
            elif region.region_type == "field_value_block":
                field_value_pairs.extend(_extract_field_values_from_lines(_region_lines(region), region.region_id))
    deduped_pairs: list[ScreenshotFieldValueItem] = []
    seen_pairs: set[tuple[str, str]] = set()
    for pair in field_value_pairs:
        key = (pair.field.casefold(), pair.value.casefold())
        if key in seen_pairs or (not pair.field and not pair.value):
            continue
        seen_pairs.add(key)
        deduped_pairs.append(pair)

    code_snippets = [str(snippet).strip() for snippet in (parsed.get("code_snippets") or []) if str(snippet).strip()]
    if not code_snippets:
        for region in regions:
            if region.region_type == "code":
                snippet = "\n".join(_region_lines(region)) if region.lines else region.text
                if snippet.strip():
                    code_snippets.append(snippet.strip())

    ui_labels = [str(value).strip() for value in (parsed.get("ui_labels") or []) if str(value).strip()]
    if not ui_labels:
        for region in regions:
            if region.region_type == "ui_control_text":
                ui_labels.extend(region.items or _region_lines(region))
    ui_labels = _dedupe_preserve_order(ui_labels)

    menu_names = _dedupe_preserve_order([str(value).strip() for value in (parsed.get("menu_names") or []) if str(value).strip()])
    button_names = _dedupe_preserve_order([str(value).strip() for value in (parsed.get("button_names") or []) if str(value).strip()])

    emphasis_cues: list[ScreenshotEmphasisCue] = []
    for cue in parsed.get("emphasis_cues") or []:
        if isinstance(cue, dict):
            text = " ".join(str(cue.get("text") or "").split()).strip()
            style = " ".join(str(cue.get("cue") or "").split()).strip()
            if text:
                emphasis_cues.append(
                    ScreenshotEmphasisCue(
                        text=text,
                        cue=style,
                        confidence=_to_confidence(cue.get("confidence"), 0.66),
                        source_region_id=str(cue.get("source_region_id") or "").strip() or None,
                    )
                )

    uncertain_region_ids = [region.region_id for region in regions if region.uncertain or region.confidence < _MIN_REGION_CONFIDENCE]
    confidence_values = [region.confidence for region in regions if region.confidence > 0]
    confidence = _to_confidence(parsed.get("confidence"), mean(confidence_values) if confidence_values else 0.35)
    field_confidence = _derive_field_confidence(parsed, regions)
    warnings = [str(item).strip() for item in (parsed.get("uncertainty_warnings") or []) if str(item).strip()]
    warnings.extend(
        region.uncertainty_reason
        for region in regions
        if region.uncertain and region.uncertainty_reason
    )

    procedural_model = None
    if isinstance(parsed.get("procedural_model"), dict):
        try:
            procedural_model = ScreenshotProceduralModel.model_validate(parsed.get("procedural_model"))
        except Exception:
            procedural_model = None

    image_characterization = _parse_image_characterization_payload(parsed.get("image_characterization"))
    embedded_graphics = _parse_embedded_graphics_payload(
        parsed.get("embedded_graphics") or parsed.get("embedded_diagrams")
    )
    diagram_interpretation = _derive_diagram_interpretation(
        parsed=parsed,
        embedded_graphics=embedded_graphics,
        image_characterization=image_characterization,
        title=title,
        regions=regions,
    )
    screenshot_type_classification = _parse_screenshot_type_classification_payload(
        parsed.get("screenshot_type_classification")
    )
    screenshot_intent_route_decision = _parse_screenshot_intent_route_payload(
        parsed.get("screenshot_intent_route_decision")
    )
    substeps = _derive_flat_substeps(regions, parsed, procedural_model=procedural_model)
    unresolved_blocks = _derive_unresolved_blocks(regions)
    warnings = _dedupe_preserve_order(
        warnings + [block.reason for block in unresolved_blocks if block.reason]
    )
    if diagram_interpretation is not None:
        warnings = _dedupe_preserve_order(warnings + list(diagram_interpretation.warnings))

    structured = ScreenshotContentModel(
        title=title,
        regions=regions,
        reading_order=reading_order,
        semantic_hierarchy=hierarchy,
        headings=headings,
        paragraphs=paragraphs,
        sections=sections,
        numbered_steps=numbered_steps,
        substeps=substeps,
        bullet_lists=bullet_lists,
        notes=notes,
        tables=tables,
        field_value_pairs=deduped_pairs,
        code_snippets=_dedupe_preserve_order(code_snippets),
        ui_labels=ui_labels,
        menu_names=menu_names,
        button_names=button_names,
        emphasis_cues=emphasis_cues,
        acceptance_criteria=_derive_acceptance_criteria(regions, parsed),
        procedural_model=procedural_model,
        settings_reference_model=settings_ref if _settings_reference_nonempty(settings_ref) else None,
        image_characterization=image_characterization,
        embedded_graphics=embedded_graphics,
        diagram_interpretation=diagram_interpretation,
        screenshot_type_classification=screenshot_type_classification,
        screenshot_intent_route_decision=screenshot_intent_route_decision,
        uncertain_region_ids=uncertain_region_ids,
        unresolved_blocks=unresolved_blocks,
        confidence=confidence,
        field_confidence=field_confidence,
        uncertainty_warnings=warnings,
    )
    return structured


def apply_ir_heuristics(
    base: ScreenshotContentModel,
    *,
    parsed: dict[str, Any],
    image_bytes: bytes,
    mime_type: str,
) -> ScreenshotContentModel:
    ui_labels = _dedupe_preserve_order(list(base.ui_labels))
    button_names = _dedupe_preserve_order(list(base.button_names))
    menu_names = _dedupe_preserve_order(list(base.menu_names))

    for item in parsed.get("ui_elements") or []:
        if not isinstance(item, dict):
            continue
        label = " ".join(str(item.get("label") or "").split()).strip()
        kind = str(item.get("kind") or "").strip().lower()
        if not label:
            continue
        if kind == "button":
            button_names = _dedupe_preserve_order(button_names + [label])
        elif kind == "menu":
            menu_names = _dedupe_preserve_order(menu_names + [label])
        else:
            ui_labels = _dedupe_preserve_order(ui_labels + [label])

    promoted_buttons = {
        label for label in ui_labels
        if label.casefold() in {"cancel", "save", "apply", "close", "submit", "next", "back"}
    }
    if promoted_buttons:
        button_names = _dedupe_preserve_order(button_names + sorted(promoted_buttons))
        ui_labels = [label for label in ui_labels if label not in promoted_buttons]

    sections = list(base.sections)
    if not sections and base.semantic_hierarchy:
        sections = [
            ScreenshotSectionItem(
                name=node.title,
                purpose=node.purpose or f"Recovered section for {node.title}",
                details=[],
                confidence=node.confidence,
                source_region_ids=list(node.region_ids),
            )
            for node in base.semantic_hierarchy
            if node.level >= 2 and node.title
        ]
    if not sections and base.headings:
        sections = [
            ScreenshotSectionItem(
                name=heading.text,
                purpose=f"Recovered heading from screenshot layout (level {heading.level}).",
                details=[],
                confidence=heading.confidence,
                source_region_ids=[heading.source_region_id] if heading.source_region_id else [],
            )
            for heading in base.headings
            if heading.level >= 2 and heading.text
        ]

    if base.settings_reference_model and _settings_reference_nonempty(base.settings_reference_model):
        sections = [
            s
            for s in sections
            if s.name.strip().lower() not in {"field details", "configuration values"}
        ]

    if (
        base.field_value_pairs
        and not any(section.name.lower() in {"field details", "configuration values"} for section in sections)
        and not (base.settings_reference_model and _settings_reference_nonempty(base.settings_reference_model))
    ):
        details = [f"{pair.field}: {pair.value}".strip(": ") for pair in base.field_value_pairs[:12] if pair.field or pair.value]
        if details:
            sections.append(
                ScreenshotSectionItem(
                    name="Field details",
                    purpose="Recovered field and value pairs from the screenshot.",
                    details=details,
                    confidence=mean([(pair.confidence or 0.6) for pair in base.field_value_pairs]) if base.field_value_pairs else 0.6,
                    source_region_ids=_dedupe_preserve_order([pair.source_region_id or "" for pair in base.field_value_pairs if pair.source_region_id]),
                )
            )

    quality_factor, quality_warnings = assess_screenshot_input_quality(image_bytes, mime_type)
    uncertainty_warnings = _dedupe_preserve_order(base.uncertainty_warnings + quality_warnings)
    confidence = max(0.05, min(1.0, base.confidence * quality_factor))
    if base.uncertain_region_ids:
        confidence *= max(0.55, 1.0 - min(0.35, 0.08 * len(base.uncertain_region_ids)))

    if not base.title and base.headings:
        title = base.headings[0].text
    else:
        title = base.title

    return base.model_copy(
        update={
            "title": title,
            "ui_labels": ui_labels,
            "button_names": button_names,
            "menu_names": menu_names,
            "sections": sections,
            "confidence": round(confidence, 3),
            "uncertainty_warnings": uncertainty_warnings,
        }
    )


def _image_context_from_parsed(
    parsed: dict[str, Any],
    *,
    raw_model: str,
    provider: str,
    image_bytes: bytes,
    mime_type: str,
    screenshot_context: str | None = None,
    understanding_trace: ScreenshotUnderstandingTrace | None = None,
) -> ChatImageContext:
    structured = apply_ir_heuristics(
        _build_structured_from_parsed(parsed),
        parsed=parsed,
        image_bytes=image_bytes,
        mime_type=mime_type,
    )
    screenshot_type_classification = structured.screenshot_type_classification or _parse_screenshot_type_classification_payload(
        parsed.get("screenshot_type_classification")
    )
    if screenshot_type_classification is None:
        _, screenshot_type_classification = _SCREENSHOT_TYPE_CLASSIFIER.classify(
            structured,
            screenshot_context=screenshot_context,
        )
        structured = structured.model_copy(
            update={"screenshot_type_classification": screenshot_type_classification}
        )

    screenshot_intent_route_decision = (
        structured.screenshot_intent_route_decision
        or _parse_screenshot_intent_route_payload(parsed.get("screenshot_intent_route_decision"))
    )
    if screenshot_intent_route_decision is None and screenshot_type_classification is not None:
        screenshot_intent_route_decision = _SCREENSHOT_INTENT_ROUTER.route(screenshot_type_classification)
        structured = structured.model_copy(
            update={"screenshot_intent_route_decision": screenshot_intent_route_decision}
        )

    ordered_text: list[str] = []
    by_id = {region.region_id: region for region in structured.regions}
    for region_id in structured.reading_order:
        region = by_id.get(region_id)
        if region is None:
            continue
        ordered_text.extend(_region_lines(region))
    if not ordered_text:
        ordered_text = [str(item).strip() for item in (parsed.get("visible_text") or []) if str(item).strip()]
    ordered_text = _dedupe_preserve_order(ordered_text)

    summary = " ".join(str(parsed.get("summary") or "").split()).strip()
    if not summary:
        parts: list[str] = []
        if structured.title:
            parts.append(f"Screen title: {structured.title}.")
        if structured.procedural_model and structured.procedural_model.steps:
            parts.append(f"Recovered a procedure with {len(structured.procedural_model.steps)} top-level step(s).")
        if structured.numbered_steps:
            parts.append(f"Detected {len(structured.numbered_steps)} likely steps.")
        if structured.field_value_pairs:
            parts.append(f"Recovered {len(structured.field_value_pairs)} field/value pairs.")
        if structured.settings_reference_model and _settings_reference_nonempty(structured.settings_reference_model):
            sm = structured.settings_reference_model
            assert sm is not None
            n_fields = sum(len(sec.fields) for sec in sm.sections)
            tab_hint = f", tabs: {', '.join(sm.tabs[:5])}" if sm.tabs else ""
            parts.append(f"Settings UI: {len(sm.sections)} group(s), {n_fields} field(s){tab_hint}.")
        if structured.diagram_interpretation is not None:
            diagram = structured.diagram_interpretation
            parts.append(
                f"Diagram: {diagram.diagram_kind} with {len(diagram.key_entities)} key entit"
                f"{'y' if len(diagram.key_entities) == 1 else 'ies'} ({diagram.content_orientation})."
            )
        if structured.screenshot_type_classification is not None:
            parts.append(
                "Screenshot classified as "
                f"{structured.screenshot_type_classification.screenshot_type.replace('_', ' ')} "
                f"({structured.screenshot_type_classification.confidence:.2f} confidence)."
            )
        if structured.screenshot_intent_route_decision is not None:
            parts.append(
                "Intent routed to "
                f"{structured.screenshot_intent_route_decision.chosen_route.replace('_', ' ')} "
                f"({structured.screenshot_intent_route_decision.route_confidence:.2f} confidence)."
            )
        if structured.tables:
            parts.append(f"Detected {len(structured.tables)} table regions.")
        if structured.unresolved_blocks:
            parts.append(f"Preserved {len(structured.unresolved_blocks)} low-confidence block(s) without forcing structure.")
        if structured.uncertain_region_ids:
            parts.append(f"{len(structured.uncertain_region_ids)} region(s) were uncertain.")
        summary = " ".join(parts).strip() or "Recovered partial semantic structure from the screenshot."

    inferred_workflow = " ".join(str(parsed.get("inferred_workflow") or "").split()).strip()
    if not inferred_workflow and structured.procedural_model and structured.procedural_model.steps:
        inferred_workflow = f"Procedure with {len(structured.procedural_model.steps)} ordered step(s)."
    elif not inferred_workflow and structured.numbered_steps:
        inferred_workflow = f"Procedure with {len(structured.numbered_steps)} ordered step(s)."

    warnings = _dedupe_preserve_order(
        [str(item).strip() for item in (parsed.get("warnings") or []) if str(item).strip()]
        + structured.uncertainty_warnings
    )
    return ChatImageContext(
        summary=summary,
        visible_text=ordered_text[:80],
        ui_elements=[
            {"label": label, "kind": "control"}
            for label in (structured.button_names or structured.menu_names or structured.ui_labels)[:20]
        ],
        inferred_workflow=inferred_workflow,
        warnings=warnings,
        raw_model=raw_model,
        vision_provider=provider,
        structured=structured,
        understanding_trace=understanding_trace,
    )


def _fallback_context(*, provider: str, image_bytes: bytes, mime_type: str, user_prompt: str, warning: str) -> ChatImageContext:
    parsed = {
        "summary": "Screenshot understanding ran in fallback mode and preserved only minimal safe context.",
        "title": "",
        "visible_text": [_clip_text(user_prompt, 240)] if user_prompt.strip() else [],
        "confidence": 0.12,
        "warnings": [warning],
        "uncertainty_warnings": [warning],
        "regions": [],
    }
    trace = ScreenshotUnderstandingTrace(
        provider=provider,
        model="fallback",
        warnings=[warning],
        stages=[
            ScreenshotPassOutput(
                pass_name="fallback",
                summary=warning,
                warning_count=1,
                payload=parsed,
            )
        ],
    )
    return _image_context_from_parsed(
        parsed,
        raw_model="fallback",
        provider=provider,
        image_bytes=image_bytes,
        mime_type=mime_type,
        screenshot_context=user_prompt,
        understanding_trace=trace,
    )


def _configured_screenshot_vision_provider() -> str:
    raw = (os.getenv("SCREENSHOT_VISION_PROVIDER") or "").strip().lower()
    return _VISION_PROVIDER_ALIASES.get(raw, "inherit")


def _azure_vision_required() -> bool:
    configured = _configured_screenshot_vision_provider()
    llm_provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    return configured == "azure_openai" or llm_provider in {"azure", "azure_openai", "azure-openai"}


def _screenshot_vision_diagnostics() -> tuple[str, str | None]:
    configured = _configured_screenshot_vision_provider()
    llm_provider = (os.getenv("LLM_PROVIDER") or "").strip().lower() or "unset"
    azure_available = bool(
        _AZURE_OPENAI_API_KEY and _AZURE_OPENAI_ENDPOINT and _AZURE_OPENAI_API_VERSION and _AZURE_OPENAI_MODEL
    )

    if _azure_vision_required():
        if azure_available:
            return ("azure_openai", None)
        return (
            "fallback",
            "Azure OpenAI vision is required but not fully configured. Set AZURE_OPENAI_API_KEY, "
            "AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION, and AZURE_OPENAI_MODEL "
            "(or AZURE_OPENAI_VISION_MODEL) in backend/.env.",
        )

    if configured == "fallback":
        return (
            "fallback",
            "Screenshot vision is explicitly disabled by SCREENSHOT_VISION_PROVIDER, so screenshot understanding returned only a conservative fallback.",
        )

    if configured == "azure_openai":
        if azure_available:
            return ("azure_openai", None)
        return (
            "fallback",
            "SCREENSHOT_VISION_PROVIDER is set to Azure OpenAI, but AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, "
            "AZURE_OPENAI_API_VERSION, or AZURE_OPENAI_MODEL is missing; screenshot understanding returned only a conservative fallback.",
        )

    if configured == "openai":
        if _OPENAI_API_KEY:
            return ("openai", None)
        return (
            "fallback",
            "SCREENSHOT_VISION_PROVIDER is set to openai, but OPENAI_API_KEY is not configured; screenshot understanding returned only a conservative fallback.",
        )

    if configured == "anthropic":
        if _ANTHROPIC_API_KEY:
            return ("anthropic", None)
        return (
            "fallback",
            "SCREENSHOT_VISION_PROVIDER is set to anthropic, but ANTHROPIC_API_KEY is not configured; screenshot understanding returned only a conservative fallback.",
        )

    if llm_provider in {"azure", "azure_openai", "azure-openai"} and azure_available:
        return ("azure_openai", None)
    if llm_provider == "openai" and _OPENAI_API_KEY:
        return ("openai", None)
    if llm_provider in {"anthropic", "bedrock"} and _ANTHROPIC_API_KEY:
        return ("anthropic", None)
    if azure_available:
        return ("azure_openai", None)
    if _OPENAI_API_KEY:
        return ("openai", None)
    if _ANTHROPIC_API_KEY:
        return ("anthropic", None)

    if llm_provider == "groq":
        return (
            "fallback",
            "LLM_PROVIDER is set to groq, but this repo's screenshot-understanding pipeline currently needs OpenAI or Anthropic credentials for real vision analysis; screenshot understanding returned only a conservative fallback.",
        )
    if llm_provider in {"anthropic", "bedrock"}:
        return (
            "fallback",
            "Screenshot understanding expected Anthropic vision credentials, but ANTHROPIC_API_KEY is not configured; screenshot understanding returned only a conservative fallback.",
        )
    if llm_provider in {"azure", "azure_openai", "azure-openai"}:
        return (
            "fallback",
            "Screenshot understanding expected Azure OpenAI vision credentials, but AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION, or AZURE_OPENAI_MODEL is not configured; screenshot understanding returned only a conservative fallback.",
        )
    if llm_provider == "openai":
        return (
            "fallback",
            "Screenshot understanding expected OpenAI vision credentials, but OPENAI_API_KEY is not configured; screenshot understanding returned only a conservative fallback.",
        )
    return (
        "fallback",
        "Vision provider unavailable; screenshot understanding returned only a conservative fallback.",
    )


def _choose_vision_provider() -> str:
    provider, _ = _screenshot_vision_diagnostics()
    return provider


class ScreenshotUnderstandingService:
    async def inspect(
        self,
        *,
        image: ChatAttachmentRef,
        image_bytes: bytes,
        user_prompt: str,
    ) -> ScreenshotUnderstandingTrace:
        provider, fallback_warning = _screenshot_vision_diagnostics()
        if provider == "fallback" or not is_llm_available():
            warning = fallback_warning or "Vision provider unavailable; screenshot understanding returned only a conservative fallback."
            if _azure_vision_required():
                raise RuntimeError(warning)
            fallback_model = ScreenshotContentModel(confidence=0.12, uncertainty_warnings=[warning])
            classification_features, screenshot_type_classification = _SCREENSHOT_TYPE_CLASSIFIER.classify(
                fallback_model,
                screenshot_context=user_prompt,
            )
            screenshot_intent_route_decision = _SCREENSHOT_INTENT_ROUTER.route(screenshot_type_classification)
            return ScreenshotUnderstandingTrace(
                provider=provider,
                model="fallback",
                classification_features=classification_features,
                screenshot_type_classification=screenshot_type_classification,
                screenshot_intent_route_decision=screenshot_intent_route_decision,
                warnings=[warning],
                stages=[
                    ScreenshotPassOutput(
                        pass_name="fallback",
                        summary=warning,
                        warning_count=1,
                        payload={"warnings": [warning]},
                    )
                ],
            )

        layout_parsed, raw_model = await self._run_layout_pass(
            provider=provider,
            image_bytes=image_bytes,
            mime_type=image.mime_type,
            user_prompt=user_prompt,
        )
        layout_regions = _parse_layout_regions(layout_parsed)
        layout_stage = _log_stage_output(
            asset_id=image.asset_id,
            stage_name="detect_layout_regions",
            payload=layout_parsed,
            summary=f"Detected {len(layout_regions)} layout region(s).",
        )

        text_parsed, _ = await self._run_text_pass(
            provider=provider,
            image_bytes=image_bytes,
            mime_type=image.mime_type,
            user_prompt=user_prompt,
            layout_regions=layout_regions,
        )
        text_blocks = _parse_text_blocks(text_parsed, layout_regions)
        text_stage = _log_stage_output(
            asset_id=image.asset_id,
            stage_name="extract_text_per_block",
            payload=text_parsed,
            summary=f"Extracted text for {len(text_blocks)} block(s).",
        )

        semantic_parsed, _ = await self._run_classification_pass(
            provider=provider,
            image_bytes=image_bytes,
            mime_type=image.mime_type,
            user_prompt=user_prompt,
            text_blocks=text_blocks,
        )
        semantic_blocks = _parse_semantic_blocks(semantic_parsed, text_blocks)
        semantic_stage = _log_stage_output(
            asset_id=image.asset_id,
            stage_name="classify_semantic_blocks",
            payload=semantic_parsed,
            summary=f"Classified {len(semantic_blocks)} semantic block(s).",
        )

        composed = _parsed_from_multi_pass(
            layout_regions=layout_regions,
            text_blocks=text_blocks,
            semantic_blocks=semantic_blocks,
            initial_summary=" ".join(str(layout_parsed.get("summary") or text_parsed.get("summary") or semantic_parsed.get("summary") or "").split()).strip(),
        )
        for aux_source in (layout_parsed, text_parsed, semantic_parsed):
            composed.update(_vision_aux_from_semantic_payload(aux_source))
        for key in ("ui_labels", "button_names", "menu_names", "warnings", "visible_text"):
            if semantic_parsed.get(key):
                composed[key] = semantic_parsed.get(key)
            elif text_parsed.get(key):
                composed[key] = text_parsed.get(key)
            elif layout_parsed.get(key):
                composed[key] = layout_parsed.get(key)
        if isinstance(semantic_parsed.get("settings_reference"), dict):
            composed["settings_reference"] = semantic_parsed["settings_reference"]
        structure_model = _build_structured_from_parsed(composed)
        procedural_model = _derive_procedural_model(
            semantic_blocks,
            text_blocks=text_blocks,
            title=structure_model.title,
            parsed=composed,
        )
        structure_stage = _log_stage_output(
            asset_id=image.asset_id,
            stage_name="reconstruct_structure",
            payload={
                "reading_order": structure_model.reading_order,
                "semantic_hierarchy": [node.model_dump(mode="json") for node in structure_model.semantic_hierarchy],
                "procedural_step_count": len(procedural_model.steps) if procedural_model else 0,
            },
            summary=f"Reconstructed {len(structure_model.reading_order)} ordered region(s), {len(structure_model.semantic_hierarchy)} hierarchy node(s), and {len(procedural_model.steps) if procedural_model else 0} procedural step(s).",
        )

        final_model = apply_ir_heuristics(
            structure_model,
            parsed=composed,
            image_bytes=image_bytes,
            mime_type=image.mime_type,
        )
        if procedural_model is not None:
            final_model = final_model.model_copy(
                update={
                    "procedural_model": procedural_model,
                    "substeps": [
                        substep.model_copy()
                        for step in procedural_model.steps
                        for substep in step.substeps
                        if substep.command.strip()
                    ],
                }
            )
        classification_features, screenshot_type_classification = _SCREENSHOT_TYPE_CLASSIFIER.classify(
            final_model,
            screenshot_context=user_prompt,
        )
        screenshot_intent_route_decision = _SCREENSHOT_INTENT_ROUTER.route(screenshot_type_classification)
        final_model = final_model.model_copy(
            update={
                "screenshot_type_classification": screenshot_type_classification,
                "screenshot_intent_route_decision": screenshot_intent_route_decision,
            }
        )
        normalize_stage = _log_stage_output(
            asset_id=image.asset_id,
            stage_name="normalize_screenshot_content_model",
            payload={
                "title": final_model.title,
                "section_count": len(final_model.sections),
                "paragraph_count": len(final_model.paragraphs),
                "step_count": len(final_model.numbered_steps),
                "substep_count": len(final_model.substeps),
                "procedural_step_count": len(final_model.procedural_model.steps) if final_model.procedural_model else 0,
                "field_value_count": len(final_model.field_value_pairs),
                "settings_section_count": len(final_model.settings_reference_model.sections)
                if final_model.settings_reference_model
                else 0,
                "diagram_kind": final_model.diagram_interpretation.diagram_kind
                if final_model.diagram_interpretation
                else None,
                "diagram_entity_count": len(final_model.diagram_interpretation.key_entities)
                if final_model.diagram_interpretation
                else 0,
                "screenshot_type": final_model.screenshot_type_classification.screenshot_type
                if final_model.screenshot_type_classification
                else None,
                "intent_route": final_model.screenshot_intent_route_decision.chosen_route
                if final_model.screenshot_intent_route_decision
                else None,
                "uncertain_region_ids": list(final_model.uncertain_region_ids),
                "unresolved_block_count": len(final_model.unresolved_blocks),
                "confidence": final_model.confidence,
                "features": classification_features.model_dump(mode="json"),
                "classification": screenshot_type_classification.model_dump(mode="json"),
            },
            summary=f"Normalized screenshot into content model with confidence {final_model.confidence:.2f}.",
        )
        classification_stage = _log_stage_output(
            asset_id=image.asset_id,
            stage_name="classify_screenshot_type",
            payload={
                "features": classification_features.model_dump(mode="json"),
                "classification": screenshot_type_classification.model_dump(mode="json"),
            },
            summary=(
                "Classified screenshot as "
                f"{screenshot_type_classification.screenshot_type} "
                f"({screenshot_type_classification.confidence:.2f} confidence)."
            ),
        )
        routing_stage = _log_stage_output(
            asset_id=image.asset_id,
            stage_name="route_screenshot_intent",
            payload=screenshot_intent_route_decision.model_dump(mode="json", by_alias=True),
            summary=(
                "Routed screenshot intent to "
                f"{screenshot_intent_route_decision.chosen_route} "
                f"({screenshot_intent_route_decision.route_confidence:.2f} confidence)."
            ),
        )

        warnings = _dedupe_preserve_order(
            final_model.uncertainty_warnings
            + [str(item).strip() for item in (layout_parsed.get("warnings") or []) if str(item).strip()]
            + [str(item).strip() for item in (text_parsed.get("warnings") or []) if str(item).strip()]
            + [str(item).strip() for item in (semantic_parsed.get("warnings") or []) if str(item).strip()]
        )
        return ScreenshotUnderstandingTrace(
            provider=provider,
            model=raw_model,
            layout_regions=layout_regions,
            text_blocks=text_blocks,
            semantic_blocks=semantic_blocks,
            procedural_model=procedural_model,
            settings_reference_model=final_model.settings_reference_model,
            image_characterization=final_model.image_characterization,
            embedded_graphics=final_model.embedded_graphics,
            diagram_interpretation=final_model.diagram_interpretation,
            classification_features=classification_features,
            screenshot_type_classification=screenshot_type_classification,
            screenshot_intent_route_decision=screenshot_intent_route_decision,
            reading_order=final_model.reading_order,
            semantic_hierarchy=final_model.semantic_hierarchy,
            final_confidence=final_model.confidence,
            warnings=warnings,
            stages=[layout_stage, text_stage, semantic_stage, structure_stage, normalize_stage, classification_stage, routing_stage],
        )

    async def understand(
        self,
        *,
        image: ChatAttachmentRef,
        image_bytes: bytes,
        user_prompt: str,
    ) -> ChatImageContext:
        provider, fallback_warning = _screenshot_vision_diagnostics()
        if provider == "fallback" or not is_llm_available():
            warning = fallback_warning or "Vision provider unavailable; screenshot understanding returned only a conservative fallback."
            if _azure_vision_required():
                raise RuntimeError(warning)
            logger.warning_structured(
                "screenshot_understanding_fallback_mode",
                extra_fields={"asset_id": image.asset_id, "provider": provider},
            )
            return _fallback_context(
                provider=provider,
                image_bytes=image_bytes,
                mime_type=image.mime_type,
                user_prompt=user_prompt,
                warning=warning,
            )

        trace = await self.inspect(image=image, image_bytes=image_bytes, user_prompt=user_prompt)
        parsed = _parsed_from_multi_pass(
            layout_regions=trace.layout_regions,
            text_blocks=trace.text_blocks,
            semantic_blocks=trace.semantic_blocks,
        )
        if trace.procedural_model is not None:
            parsed["procedural_model"] = trace.procedural_model.model_dump(mode="json")
        if trace.settings_reference_model is not None:
            parsed["settings_reference"] = trace.settings_reference_model.model_dump(mode="json")
        if trace.image_characterization is not None:
            parsed["image_characterization"] = trace.image_characterization.model_dump(mode="json")
        if trace.embedded_graphics:
            parsed["embedded_graphics"] = [graphic.model_dump(mode="json") for graphic in trace.embedded_graphics]
        if trace.diagram_interpretation is not None:
            parsed["diagram_interpretation"] = trace.diagram_interpretation.model_dump(mode="json")
        if trace.classification_features is not None:
            parsed["screenshot_classification_features"] = trace.classification_features.model_dump(mode="json")
        if trace.screenshot_type_classification is not None:
            parsed["screenshot_type_classification"] = trace.screenshot_type_classification.model_dump(mode="json")
        if trace.screenshot_intent_route_decision is not None:
            parsed["screenshot_intent_route_decision"] = trace.screenshot_intent_route_decision.model_dump(
                mode="json",
                by_alias=True,
            )
        return _image_context_from_parsed(
            parsed,
            raw_model=trace.model or "unknown-vision-model",
            provider=trace.provider or provider,
            image_bytes=image_bytes,
            mime_type=image.mime_type,
            screenshot_context=user_prompt,
            understanding_trace=trace,
        )

    async def extract_map_hierarchy_outline(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        user_prompt: str,
    ) -> tuple[dict[str, Any], str]:
        """Single vision pass: diagram → JSON outline for :func:`map_hierarchy_bundle.parse_map_outline_payload`."""
        provider = _choose_vision_provider()
        if provider == "fallback" or not is_llm_available():
            warning = _screenshot_vision_diagnostics()[1] or "Vision provider unavailable; screenshot understanding returned only a conservative fallback."
            if _azure_vision_required():
                raise RuntimeError(warning)
            return {}, "fallback"
        parsed, model = await self._run_vision_pass(
            provider=provider,
            system_prompt=_MAP_HIERARCHY_SYSTEM_PROMPT,
            image_bytes=image_bytes,
            mime_type=mime_type,
            user_prompt=user_prompt or "(none)",
        )
        return (parsed if isinstance(parsed, dict) else {}), model

    async def _run_layout_pass(
        self,
        *,
        provider: str,
        image_bytes: bytes,
        mime_type: str,
        user_prompt: str,
    ) -> tuple[dict[str, Any], str]:
        return await self._run_vision_pass(
            provider=provider,
            system_prompt=_layout_pass_prompt(),
            image_bytes=image_bytes,
            mime_type=mime_type,
            user_prompt=user_prompt,
        )

    async def _run_text_pass(
        self,
        *,
        provider: str,
        image_bytes: bytes,
        mime_type: str,
        user_prompt: str,
        layout_regions: list[ScreenshotLayoutRegion],
    ) -> tuple[dict[str, Any], str]:
        return await self._run_vision_pass(
            provider=provider,
            system_prompt=_text_pass_prompt(layout_regions),
            image_bytes=image_bytes,
            mime_type=mime_type,
            user_prompt=user_prompt,
        )

    async def _run_classification_pass(
        self,
        *,
        provider: str,
        image_bytes: bytes,
        mime_type: str,
        user_prompt: str,
        text_blocks: list[ScreenshotTextBlock],
    ) -> tuple[dict[str, Any], str]:
        return await self._run_vision_pass(
            provider=provider,
            system_prompt=_classification_pass_prompt(text_blocks),
            image_bytes=image_bytes,
            mime_type=mime_type,
            user_prompt=user_prompt,
        )

    async def _run_vision_pass(
        self,
        *,
        provider: str,
        system_prompt: str,
        image_bytes: bytes,
        mime_type: str,
        user_prompt: str,
    ) -> tuple[dict[str, Any], str]:
        if provider == "openai":
            return await self._vision_openai(
                system_prompt=system_prompt,
                image_bytes=image_bytes,
                mime_type=mime_type,
                user_prompt=user_prompt,
            )
        if provider == "azure_openai":
            return await self._vision_azure_openai(
                system_prompt=system_prompt,
                image_bytes=image_bytes,
                mime_type=mime_type,
                user_prompt=user_prompt,
            )
        return await self._vision_anthropic(
            system_prompt=system_prompt,
            image_bytes=image_bytes,
            mime_type=mime_type,
            user_prompt=user_prompt,
        )

    async def _vision_openai(self, *, system_prompt: str, image_bytes: bytes, mime_type: str, user_prompt: str) -> tuple[dict[str, Any], str]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=_OPENAI_API_KEY, timeout=_VISION_TIMEOUT)
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"User prompt:\n{user_prompt or '(none)'}"},
                    {"type": "image_url", "image_url": {"url": _data_url(mime_type, image_bytes)}},
                ],
            },
        ]
        completion = await client.chat.completions.create(
            **build_openai_chat_completion_kwargs(
                model=_OPENAI_MODEL,
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=2400,
                messages=messages,
            )
        )
        content = completion.choices[0].message.content if completion.choices else "{}"
        return _parse_json_loose(content or "{}"), _OPENAI_MODEL

    async def _vision_azure_openai(self, *, system_prompt: str, image_bytes: bytes, mime_type: str, user_prompt: str) -> tuple[dict[str, Any], str]:
        from openai import AsyncAzureOpenAI

        client = AsyncAzureOpenAI(
            api_key=_AZURE_OPENAI_API_KEY,
            api_version=_AZURE_OPENAI_API_VERSION,
            azure_endpoint=_AZURE_OPENAI_ENDPOINT,
            timeout=_VISION_TIMEOUT,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": _data_url(mime_type, image_bytes)}},
                ],
            },
        ]
        completion = await client.chat.completions.create(
            **build_openai_chat_completion_kwargs(
                model=_AZURE_OPENAI_MODEL,
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=2400,
                messages=messages,
            )
        )
        content = completion.choices[0].message.content if completion.choices else "{}"
        return _parse_json_loose(content or "{}"), _AZURE_OPENAI_MODEL

    async def _vision_anthropic(self, *, system_prompt: str, image_bytes: bytes, mime_type: str, user_prompt: str) -> tuple[dict[str, Any], str]:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=_ANTHROPIC_API_KEY, timeout=_VISION_TIMEOUT)
        message = await client.messages.create(
            model=_ANTHROPIC_MODEL,
            max_tokens=2400,
            temperature=0.0,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"User prompt:\n{user_prompt or '(none)'}"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": base64.b64encode(image_bytes).decode("ascii"),
                            },
                        },
                    ],
                }
            ],
        )
        text_parts = [getattr(block, "text", "") for block in getattr(message, "content", []) if getattr(block, "type", "") == "text"]
        return _parse_json_loose("\n".join(text_parts)), _ANTHROPIC_MODEL


_service: ScreenshotUnderstandingService | None = None


def get_screenshot_understanding_service() -> ScreenshotUnderstandingService:
    global _service
    if _service is None:
        _service = ScreenshotUnderstandingService()
    return _service


async def extract_map_hierarchy_outline_from_image(
    *,
    image_bytes: bytes,
    mime_type: str,
    user_prompt: str,
) -> tuple[dict[str, Any], str]:
    return await get_screenshot_understanding_service().extract_map_hierarchy_outline(
        image_bytes=image_bytes,
        mime_type=mime_type,
        user_prompt=user_prompt,
    )


async def extract_screenshot_context(
    *,
    image: ChatAttachmentRef,
    image_bytes: bytes,
    user_prompt: str,
) -> ChatImageContext:
    return await get_screenshot_understanding_service().understand(
        image=image,
        image_bytes=image_bytes,
        user_prompt=user_prompt,
    )
