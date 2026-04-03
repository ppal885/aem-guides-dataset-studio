from __future__ import annotations

import re

XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>'

DITA_DOCTYPES: dict[str, str] = {
    "topic": '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">',
    "concept": '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "technicalContent/dtd/concept.dtd">',
    "reference": '<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "technicalContent/dtd/reference.dtd">',
    "task": '<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "technicalContent/dtd/task.dtd">',
    "glossentry": '<!DOCTYPE glossentry PUBLIC "-//OASIS//DTD DITA Glossentry//EN" "technicalContent/dtd/glossentry.dtd">',
}

_XML_DECLARATION_PATTERN = re.compile(r"^\ufeff?\s*<\?xml[^>]*\?>\s*", re.IGNORECASE)
_DOCTYPE_PATTERN = re.compile(r"^<!DOCTYPE[\s\S]*?>\s*", re.IGNORECASE)
_ROOT_TAG_PATTERN = re.compile(r"<([A-Za-z_][\w:.-]*)\b")


def get_dita_doctype(dita_type: str | None) -> str | None:
    if not dita_type:
        return None
    return DITA_DOCTYPES.get((dita_type or "").strip().lower())


def build_dita_header(dita_type: str | None) -> str:
    doctype = get_dita_doctype(dita_type)
    if not doctype:
        return XML_DECLARATION
    return f"{XML_DECLARATION}\n{doctype}"


def strip_xml_prolog(content: str) -> str:
    cleaned = (content or "").lstrip("\ufeff").strip()
    if not cleaned:
        return ""
    cleaned = _XML_DECLARATION_PATTERN.sub("", cleaned, count=1)
    cleaned = _DOCTYPE_PATTERN.sub("", cleaned, count=1)
    return cleaned.lstrip()


def detect_dita_type_from_content(content: str, fallback: str = "task") -> str:
    body = strip_xml_prolog(content)
    if not body:
        return fallback
    root_match = _ROOT_TAG_PATTERN.search(body)
    if not root_match:
        return fallback
    root_tag = root_match.group(1).lower()
    return root_tag if root_tag in DITA_DOCTYPES else fallback


def normalize_dita_document(content: str, dita_type: str | None = None) -> tuple[str, str]:
    body = strip_xml_prolog(content)
    if not body:
        resolved_type = (dita_type or "task").strip().lower() or "task"
        return build_dita_header(resolved_type), resolved_type

    resolved_type = (dita_type or "").strip().lower()
    if not resolved_type or resolved_type == "auto":
        resolved_type = detect_dita_type_from_content(body)
    elif resolved_type not in DITA_DOCTYPES:
        resolved_type = detect_dita_type_from_content(body, fallback=resolved_type)

    header = build_dita_header(resolved_type)
    return f"{header}\n{body}", resolved_type


def has_expected_dita_header(content: str, dita_type: str | None = None) -> bool:
    expected_type = (dita_type or "").strip().lower()
    if not expected_type or expected_type == "auto":
        expected_type = detect_dita_type_from_content(content)
    expected_header = build_dita_header(expected_type)
    trimmed = (content or "").lstrip("\ufeff").strip()
    return bool(trimmed) and trimmed.startswith(expected_header)
