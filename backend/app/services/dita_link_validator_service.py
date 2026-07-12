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

# Linking elements whose non-DITA @href target must declare @format so the processor
# knows how to handle it (e.g. .md needs format="mdita"). <image>/media are excluded.
_LINK_ELEMENTS = {"topicref", "xref", "link", "mapref", "navref", "keydef"}
_DITA_TARGET_EXTENSIONS = {".dita", ".ditamap", ".xml"}


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

        # ── missing @format on a non-DITA link target ───────────────────────────
        href = elem.get("href")
        if (
            href
            and tag in _LINK_ELEMENTS
            and scope not in ("external", "peer")
            and not _is_external(href)
            and not elem.get("format")
        ):
            ext = Path((href.split("#", 1)[0] or "")).suffix.lower()
            if ext and ext not in _DITA_TARGET_EXTENSIONS and ext not in _SKIP_EXTENSIONS:
                hint = ' (use format="mdita" for Markdown)' if ext in (".md", ".markdown") else ""
                broken.append({
                    "source_file": rel_source,
                    "element_tag": tag,
                    "attribute": "format",
                    "value": href,
                    "reason": f"Non-DITA target '{ext}' has no @format; the processor may mishandle it{hint}.",
                    "severity": "warning",
                })

        # ── href ──────────────────────────────────────────────────────────────
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

        # ── conkeyref ───────────────────────────────────────────────────────────
        conkeyref = elem.get("conkeyref")
        if conkeyref and defined_keys:
            # conkeyref format: keyname/elementId (or scope.keyname/elementId)
            key_part = conkeyref.split("/", 1)[0]
            base_key = key_part.split(".")[-1] if "." in key_part else key_part
            if base_key and base_key not in defined_keys:
                broken.append({
                    "source_file": rel_source,
                    "element_tag": tag,
                    "attribute": "conkeyref",
                    "value": conkeyref,
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

    # Assign severity: real publish-breakers are errors; @format hints are warnings.
    for b in all_broken:
        if "severity" not in b:
            b["severity"] = "error"

    # Build summary by attribute type
    summary: dict[str, int] = {
        "broken_hrefs": 0,
        "broken_conrefs": 0,
        "broken_keyrefs": 0,
        "broken_conkeyrefs": 0,
        "missing_format": 0,
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
        elif attr == "conkeyref":
            summary["broken_conkeyrefs"] += 1
        elif attr == "format":
            summary["missing_format"] += 1
        elif attr == "xml":
            summary["xml_parse_errors"] += 1
    error_count = sum(1 for b in all_broken if b.get("severity") != "warning")
    warning_count = sum(1 for b in all_broken if b.get("severity") == "warning")

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
        "error_count": error_count,
        "warning_count": warning_count,
        "publish_ready": error_count == 0,
        "broken_links": all_broken,
        "external_links": all_external,
        "summary": summary,
    }


def format_prepublish_report(report: dict) -> str:
    """Render a validate_bundle report as a reviewer-friendly pre-publish markdown summary."""
    total = report.get("total_files", 0)
    errors = report.get("error_count", 0)
    warnings = report.get("warning_count", 0)
    if total == 0:
        return "No `.dita`/`.ditamap` files were found to validate. Check the map/bundle path."

    if errors == 0 and warnings == 0:
        lines = [f"## ✅ Pre-publish check passed\nScanned **{total}** file(s) — no broken links, references, or missing `@format`."]
    else:
        verdict = "❌ Not publish-ready" if errors else "⚠️ Publish-ready with warnings"
        lines = [f"## {verdict}\nScanned **{total}** file(s): **{errors} error(s)**, **{warnings} warning(s)**."]

    findings = report.get("broken_links") or []
    errs = [f for f in findings if f.get("severity") != "warning"]
    warns = [f for f in findings if f.get("severity") == "warning"]

    def _rows(items: list[dict], heading: str) -> list[str]:
        if not items:
            return []
        out = ["", f"## {heading}", "| File | Element | Attribute | Value | Problem |", "|---|---|---|---|---|"]
        for f in items[:40]:
            val = str(f.get("value") or "")[:60].replace("|", "\\|")
            reason = str(f.get("reason") or "").replace("|", "\\|")
            src = f.get("source_file", "")
            tag = f.get("element_tag", "")
            attr = f.get("attribute", "")
            out.append(f"| `{src}` | `{tag}` | `@{attr}` | `{val}` | {reason} |")
        if len(items) > 40:
            out.append(f"| … | | | | {len(items) - 40} more |")
        return out

    lines += _rows(errs, "Errors (block publishing)")
    lines += _rows(warns, "Warnings (review before publishing)")
    ext = report.get("external_links") or []
    if ext:
        lines += ["", f"## External links ({len(ext)}) — not verified", *[f"- {u}" for u in ext[:15]]]
    return "\n".join(lines)
