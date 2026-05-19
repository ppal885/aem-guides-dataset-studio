"""
Remove or soften same-document xref/conref attributes that do not resolve to an @id in the topic.

Preserves visible text where possible so user content is not silently deleted.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from app.services.dita_xml_headers import normalize_dita_document, strip_xml_prolog


def _ln(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1].lower() if tag else ""


def _parse_href_fragment(href: str) -> tuple[str | None, list[str]]:
    h = (href or "").strip()
    if not h:
        return None, []
    if h.startswith("#"):
        frag = h[1:].strip()
        if not frag:
            return None, []
        return None, [p for p in frag.split("/") if p]
    if "#" in h:
        file_part, frag = h.split("#", 1)
        file_part = file_part.strip() or None
        parts = [p for p in frag.strip().split("/") if p]
        return file_part, parts
    return h, []


def _all_ids(root: ET.Element) -> set[str]:
    return {str(e.get("id")) for e in root.iter() if e.get("id")}


def _fragments_resolve(ids: set[str], parts: list[str]) -> bool:
    if not parts:
        return True
    if len(parts) == 1:
        return parts[0] in ids
    return all(p in ids for p in parts)


def sanitize_same_document_links(xml: str) -> tuple[str, list[str]]:
    """
    Return updated XML and a list of human-readable repair actions.

    - Drops empty xref @href.
    - For same-document href/conref with missing fragment targets: remove attribute; keep element text.
    """
    body = strip_xml_prolog(xml or "")
    if not body.strip():
        return xml, []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return xml, ["link_sanitize_skipped:malformed_xml"]

    ids = _all_ids(root)
    actions: list[str] = []

    for elem in root.iter():
        tag = _ln(elem.tag)
        if tag == "xref":
            href = elem.get("href")
            if href is not None and not str(href).strip():
                del elem.attrib["href"]
                actions.append("removed_empty_xref_href")
                continue
            if not href:
                continue
            file_part, parts = _parse_href_fragment(str(href))
            if file_part is None and parts and not _fragments_resolve(ids, parts):
                elem.attrib.pop("href", None)
                actions.append(f"removed_unresolved_xref:{href!s}"[:200])

        cr = elem.get("conref")
        if cr is not None:
            if not str(cr).strip():
                del elem.attrib["conref"]
                actions.append(f"removed_empty_conref_on_{tag}")
                continue
            file_part, parts = _parse_href_fragment(str(cr))
            if file_part is None and parts and not _fragments_resolve(ids, parts):
                elem.attrib.pop("conref", None)
                actions.append(f"removed_unresolved_conref:{cr!s}"[:200])

    inner = ET.tostring(root, encoding="unicode", short_empty_elements=False)
    dt = _ln(root.tag)
    if dt not in {"topic", "task", "concept", "reference"}:
        return xml, actions + ["link_sanitize_skipped:unsupported_root"]
    full, _ = normalize_dita_document(inner, dt)
    return full, actions
