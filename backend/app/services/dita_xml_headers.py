from __future__ import annotations

import re
import xml.etree.ElementTree as ET

XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>'

DITA_DOCTYPES: dict[str, str] = {
    "map": '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">',
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


def replace_first_doctype_line(full_document: str, new_doctype_line: str) -> str:
    """
    Swap the first <!DOCTYPE ...> in a full XML document (after optional XML declaration).

    ``new_doctype_line`` must be a single logical line starting with <!DOCTYPE.
    """
    line = (new_doctype_line or "").strip()
    if not line.startswith("<!DOCTYPE"):
        return full_document
    raw = (full_document or "").lstrip("\ufeff")
    m = _XML_DECLARATION_PATTERN.match(raw)
    if not m:
        return full_document
    head = m.group(0)
    rest = raw[m.end() :]
    m2 = _DOCTYPE_PATTERN.match(rest)
    if not m2:
        return full_document
    return head + line + "\n" + rest[m2.end() :]


def extract_declared_doctype_line(content: str) -> str | None:
    """
    Return the first <!DOCTYPE ...> declaration as a single normalized line, or None.
    Skips an optional XML declaration at the start.
    """
    raw = (content or "").lstrip("\ufeff")
    m = _XML_DECLARATION_PATTERN.match(raw)
    rest = raw[m.end() :] if m else raw
    m2 = _DOCTYPE_PATTERN.match(rest)
    if not m2:
        return None
    fragment = m2.group(0).strip()
    line = " ".join(fragment.split())
    return line if line else None


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


def serialize_normalized_dita_tree(root: ET.Element, dita_type: str | None = None) -> bytes:
    """
    Serialize a parsed DITA tree while restoring the expected XML declaration
    and normalized DTD header for the resolved root type.
    """
    raw_xml = ET.tostring(root, encoding="unicode", method="xml")
    normalized, _ = normalize_dita_document(raw_xml, dita_type)
    return normalized.encode("utf-8")
