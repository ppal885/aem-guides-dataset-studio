"""
Extract link and identifier surfaces from reference DITA for over-copying checks.

Security: parsing only local benchmark files; do not pass untrusted multi-MB XML without limits.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from app.services.dita_xml_headers import strip_xml_prolog


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1].lower() if tag else ""


def extract_reference_fingerprints(raw_reference: str) -> dict[str, set[str]]:
    """
    Return sets of @id values, xref @href, and @conref string values from the reference topic.

    Used to flag accidental reuse in generated output (identifiers and link targets).
    """
    ids: set[str] = set()
    hrefs: set[str] = set()
    conrefs: set[str] = set()
    body = strip_xml_prolog(raw_reference or "")
    if not body.strip():
        return {"ids": ids, "hrefs": hrefs, "conrefs": conrefs}
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return {"ids": ids, "hrefs": hrefs, "conrefs": conrefs}

    for elem in root.iter():
        eid = elem.get("id")
        if eid and str(eid).strip():
            ids.add(str(eid).strip())
        if _local(elem.tag) == "xref":
            h = elem.get("href")
            if h and str(h).strip():
                hrefs.add(str(h).strip())
        cr = elem.get("conref")
        if cr and str(cr).strip():
            conrefs.add(str(cr).strip())
    return {"ids": ids, "hrefs": hrefs, "conrefs": conrefs}


def over_copying_score(
    generated_xml: str,
    *,
    ref_ids: set[str],
    ref_hrefs: set[str],
    ref_conrefs: set[str],
) -> tuple[float, list[str]]:
    """
    Binary-style risk for gating: ``0`` if no exact reuse of reference ids/hrefs/conrefs, else ``1``.

    Also returns human-readable hit reasons (for debugging prompt regressions).
    """
    reasons: list[str] = []
    hits = 0

    body = strip_xml_prolog(generated_xml or "")
    if not body.strip():
        return 1.0, ["empty_generated_xml"]

    for h in ref_hrefs:
        if len(h) > 1 and h in body:
            hits += 1
            reasons.append(f"reference_href_reused:{h[:120]}")
    for c in ref_conrefs:
        if len(c) > 1 and c in body:
            hits += 1
            reasons.append(f"reference_conref_reused:{c[:120]}")
    for i in ref_ids:
        if not i:
            continue
        needle = f'id="{i}"'
        if needle in body or f"id='{i}'" in body:
            hits += 1
            reasons.append(f"reference_id_reused:{i[:120]}")

    return (1.0 if hits > 0 else 0.0), reasons[:20]
