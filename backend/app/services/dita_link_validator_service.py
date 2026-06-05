"""
DITA bundle link validator.

Scans a generated DITA bundle directory and reports all broken links:
  - href (topicref, xref, link, image, mapref, keydef) — file existence + id fragment
  - conref (file.dita#topicid/elemid) — file + both id parts
  - coderef (href inside <codeblock>) — file existence
  - keyref — key not defined in any collected <keydef keys="..."> in the bundle

Returns a structured dict used by both the API endpoint and the standalone script generator.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

_SKIP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".mp4", ".webm"}


def _is_external(href: str) -> bool:
    return bool(urlparse(href).scheme in ("http", "https", "ftp", "mailto", "data"))


def _tag_local(elem: ET.Element) -> str:
    tag = elem.tag
    return tag.split("}")[-1] if "}" in tag else tag


def _collect_ids(filepath: Path) -> set[str]:
    """Return all @id values in a DITA file."""
    ids: set[str] = set()
    try:
        for _, elem in ET.iterparse(str(filepath), events=("start",)):
            eid = elem.get("id")
            if eid:
                ids.add(eid)
    except ET.ParseError:
        pass
    return ids


def _collect_keydefs(filepath: Path) -> set[str]:
    """Return all key names defined via <keydef keys="..."> in a file."""
    keys: set[str] = set()
    try:
        tree = ET.parse(str(filepath))
        for elem in tree.iter():
            if _tag_local(elem) == "keydef":
                for k in (elem.get("keys") or "").split():
                    if k:
                        keys.add(k)
    except ET.ParseError:
        pass
    return keys


def _validate_file(
    source: Path,
    bundle_dir: Path,
    defined_keys: set[str],
    *,
    id_cache: dict[Path, set[str]],
) -> tuple[list[dict], list[str]]:
    """
    Validate all links in one DITA file.
    Returns (broken_links, external_links).
    """
    broken: list[dict] = []
    external: list[str] = []

    try:
        tree = ET.parse(str(source))
    except ET.ParseError as exc:
        return [
            {
                "source_file": str(source.relative_to(bundle_dir)),
                "element_tag": "?",
                "attribute": "xml",
                "value": str(source.name),
                "reason": f"XML parse error: {exc}",
            }
        ], []

    rel_source = str(source.relative_to(bundle_dir))

    for elem in tree.iter():
        tag = _tag_local(elem)
        scope = elem.get("scope", "")

        # ── href ──────────────────────────────────────────────────────────────
        href = elem.get("href")
        if href and scope not in ("external", "peer"):
            if _is_external(href):
                external.append(href)
            else:
                path_part, frag = (href.split("#", 1) + [None])[:2]
                if path_part:
                    resolved = (source.parent / path_part).resolve()
                    if not resolved.exists():
                        broken.append({
                            "source_file": rel_source,
                            "element_tag": tag,
                            "attribute": "href",
                            "value": href,
                            "reason": "File not found",
                        })
                    elif frag and resolved.suffix in (".dita", ".ditamap"):
                        ids = id_cache.setdefault(resolved, _collect_ids(resolved))
                        check_ids = [p for p in frag.split("/") if p]
                        missing = [i for i in check_ids if i not in ids]
                        if missing:
                            broken.append({
                                "source_file": rel_source,
                                "element_tag": tag,
                                "attribute": "href",
                                "value": href,
                                "reason": f"ID(s) not found in target: {', '.join(missing)}",
                            })
                elif frag:
                    # Same-document fragment
                    ids = id_cache.setdefault(source, _collect_ids(source))
                    check_ids = [p for p in frag.split("/") if p]
                    missing = [i for i in check_ids if i not in ids]
                    if missing:
                        broken.append({
                            "source_file": rel_source,
                            "element_tag": tag,
                            "attribute": "href",
                            "value": href,
                            "reason": f"Same-document ID(s) not found: {', '.join(missing)}",
                        })

        # ── conref ────────────────────────────────────────────────────────────
        conref = elem.get("conref")
        if conref:
            path_part, frag = (conref.split("#", 1) + [None])[:2]
            if path_part:
                resolved = (source.parent / path_part).resolve()
                if not resolved.exists():
                    broken.append({
                        "source_file": rel_source,
                        "element_tag": tag,
                        "attribute": "conref",
                        "value": conref,
                        "reason": "File not found",
                    })
                elif frag:
                    ids = id_cache.setdefault(resolved, _collect_ids(resolved))
                    # conref fragment format: topicid/elemid — check both parts
                    check_ids = [p for p in frag.split("/") if p]
                    missing = [i for i in check_ids if i not in ids]
                    if missing:
                        broken.append({
                            "source_file": rel_source,
                            "element_tag": tag,
                            "attribute": "conref",
                            "value": conref,
                            "reason": f"ID(s) not found in target: {', '.join(missing)}",
                        })

        # ── keyref ────────────────────────────────────────────────────────────
        keyref = elem.get("keyref")
        if keyref and defined_keys:
            # Strip optional scope prefix (scope.keyname → keyname)
            base_key = keyref.split(".")[-1] if "." in keyref else keyref
            if base_key not in defined_keys:
                broken.append({
                    "source_file": rel_source,
                    "element_tag": tag,
                    "attribute": "keyref",
                    "value": keyref,
                    "reason": "Key not defined in any map in this bundle",
                })

    return broken, external


def validate_bundle(bundle_dir: Path) -> dict:
    """
    Validate all links in a DITA bundle directory.

    Returns a structured report dict with:
      total_files, broken_link_count, broken_links[], external_links[], summary{}
    """
    bundle_dir = bundle_dir.resolve()
    dita_files: list[Path] = []
    for ext in ("*.dita", "*.ditamap"):
        dita_files.extend(bundle_dir.rglob(ext))
    dita_files.sort()

    logger.info_structured(
        "dita_link_validate_start",
        extra_fields={"bundle_dir": str(bundle_dir), "file_count": len(dita_files)},
    )

    # Pass 1 — collect all keydefs across all maps
    defined_keys: set[str] = set()
    for f in dita_files:
        if f.suffix == ".ditamap" or "map" in f.suffix:
            defined_keys.update(_collect_keydefs(f))
    # Also collect from .dita files that may have embedded keydefs
    for f in dita_files:
        if f.suffix == ".dita":
            defined_keys.update(_collect_keydefs(f))

    # Pass 2 — validate each file
    all_broken: list[dict] = []
    all_external: list[str] = []
    id_cache: dict[Path, set[str]] = {}

    for f in dita_files:
        broken, external = _validate_file(f, bundle_dir, defined_keys, id_cache=id_cache)
        all_broken.extend(broken)
        all_external.extend(external)

    # Deduplicate external links
    all_external = sorted(set(all_external))

    # Build summary by attribute type
    summary: dict[str, int] = {
        "broken_hrefs": 0,
        "broken_conrefs": 0,
        "broken_keyrefs": 0,
        "xml_parse_errors": 0,
    }
    for b in all_broken:
        attr = b.get("attribute", "")
        if attr == "href":
            summary["broken_hrefs"] += 1
        elif attr == "conref":
            summary["broken_conrefs"] += 1
        elif attr == "keyref":
            summary["broken_keyrefs"] += 1
        elif attr == "xml":
            summary["xml_parse_errors"] += 1

    logger.info_structured(
        "dita_link_validate_done",
        extra_fields={
            "file_count": len(dita_files),
            "broken": len(all_broken),
            "external": len(all_external),
        },
    )

    return {
        "bundle_dir": str(bundle_dir),
        "total_files": len(dita_files),
        "defined_key_count": len(defined_keys),
        "broken_link_count": len(all_broken),
        "broken_links": all_broken,
        "external_links": all_external,
        "summary": summary,
    }
