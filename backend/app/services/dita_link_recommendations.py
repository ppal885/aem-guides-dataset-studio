"""
Safe link guidance for generated DITA — recommends map keys / id targets instead of inventing hrefs.

Differentiator vs blind xref generation: surface actionable items for authors without fabricating paths.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from app.core.schemas_topic_generation import LinkRecommendation
from app.services.dita_xml_headers import strip_xml_prolog


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


def build_link_recommendations(xml: str) -> list[LinkRecommendation]:
    """
    Return human-readable recommendations (no fabricated URLs).

    Each item: kind, severity (info|warning|error), summary, action.
    """
    body = strip_xml_prolog(xml or "")
    if not body.strip():
        return []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return [
            LinkRecommendation(
                kind="parse",
                severity="error",
                summary="Topic XML is not well-formed; fix markup before adding links.",
                action="Repair XML structure, then re-run validation.",
            )
        ]

    ids = _all_ids(root)
    out: list[LinkRecommendation] = []

    for elem in root.iter():
        tag = _ln(elem.tag)
        if tag == "xref":
            href = elem.get("href")
            if href is not None and not str(href).strip():
                out.append(
                    LinkRecommendation(
                        kind="xref",
                        severity="warning",
                        summary="Empty xref @href — link will not resolve in AEM Guides.",
                        action="Remove the xref or set href to a vetted repository path; prefer keyref + map keydef for reuse.",
                    )
                )
                continue
            if not href:
                continue
            fp, parts = _parse_href_fragment(str(href))
            if fp is None and parts and not _fragments_resolve(ids, parts):
                out.append(
                    LinkRecommendation(
                        kind="xref",
                        severity="error",
                        summary=f'Same-document xref target is missing: "{href}".',
                        action="Add matching @id elements in this topic, or change to keyref with a keydef on your root map.",
                    )
                )
            elif fp and str(fp).strip():
                out.append(
                    LinkRecommendation(
                        kind="xref",
                        severity="info",
                        summary=f'Cross-file xref to "{fp}" — verify path in CCMS and map hierarchy.',
                        action="Confirm href relative to map; register topic in ditamap before publish.",
                    )
                )

        cr = elem.get("conref")
        if cr is not None:
            if not str(cr).strip():
                out.append(
                    LinkRecommendation(
                        kind="conref",
                        severity="warning",
                        summary="Empty @conref — invalid reuse in DITA.",
                        action="Remove conref or point to a reviewed library topic#element id.",
                    )
                )
                continue
            fp, parts = _parse_href_fragment(str(cr))
            if fp is None and parts and not _fragments_resolve(ids, parts):
                out.append(
                    LinkRecommendation(
                        kind="conref",
                        severity="error",
                        summary=f'Same-document conref target is missing: "{cr}".',
                        action="Add target @id or switch to a shared conref library topic.",
                    )
                )
            elif fp and str(fp).strip():
                out.append(
                    LinkRecommendation(
                        kind="conref",
                        severity="info",
                        summary=f'Cross-file conref "{fp}" — ensure file is in scope for your AEM Guides publication.',
                        action="Validate conref path and reuse policy with your content architect.",
                    )
                )

        kr = elem.get("keyref")
        if kr is not None and not str(kr).strip():
            out.append(
                LinkRecommendation(
                    kind="keyref",
                    severity="warning",
                    summary="Empty @keyref.",
                    action="Set keys to a value defined on your DITA map or root map.",
                )
            )

    # De-duplicate by (kind, summary) preserving order
    seen: set[tuple[str, str]] = set()
    unique: list[LinkRecommendation] = []
    for item in out:
        key = (item.kind, item.summary)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:24]
