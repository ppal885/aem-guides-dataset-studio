"""DITA auto-fix service - programmatically fix common validation errors."""
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

import xml.etree.ElementTree as ET

from app.core.structured_logging import get_structured_logger
from app.services.dita_xml_headers import serialize_normalized_dita_tree

logger = get_structured_logger(__name__)

# Extension → @format token for the deterministic missing-@format fix. Only formats we can
# infer unambiguously from a link target's extension; anything else is left for manual review.
_FORMAT_BY_EXTENSION = {
    ".md": "mdita",
    ".markdown": "mdita",
    ".html": "html",
    ".htm": "html",
    ".pdf": "pdf",
    ".txt": "txt",
}
_FORMAT_FIX_LINK_ELEMENTS = {"topicref", "xref", "link", "mapref", "navref", "keydef"}


def _is_external_href(href: str) -> bool:
    return urlparse(href).scheme in ("http", "https", "ftp", "mailto", "data")


def _collect_ids_from_root(root: ET.Element) -> list[tuple[ET.Element, str]]:
    """Return [(element, id)] for all elements with id attribute."""
    result = []
    for elem in root.iter():
        eid = elem.get("id")
        if eid:
            result.append((elem, eid))
    return result


def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def fix_duplicate_ids(folder: Path) -> dict:
    """
    Fix duplicate IDs by renaming duplicates to id_2, id_3, etc.
    Keeps the first occurrence of each ID (by file path order), renames the rest.
    Returns {ids_renamed: int, files_modified: int, errors: []}.
    """
    folder = Path(folder)
    if not folder.exists() or not folder.is_dir():
        return {"ids_renamed": 0, "files_modified": 0, "errors": ["Folder does not exist"]}

    parsed = []
    for p in sorted(folder.rglob("*")):
        if p.suffix.lower() in (".dita", ".ditamap"):
            try:
                tree = ET.parse(p)
                parsed.append((p, tree.getroot(), tree))
            except ET.ParseError:
                continue

    all_ids = defaultdict(list)
    path_to_tree = {}
    for path, root, tree in parsed:
        if root is None:
            continue
        path_to_tree[path] = tree
        rel = str(path.relative_to(folder)).replace("\\", "/")
        for elem, eid in _collect_ids_from_root(root):
            all_ids[eid].append((rel, path, elem))

    renames_by_file = defaultdict(list)
    for eid, occurrences in all_ids.items():
        if len(occurrences) <= 1:
            continue
        for i, (rel, path, elem) in enumerate(occurrences):
            if i == 0:
                continue
            new_id = f"{eid}_{i + 1}"
            renames_by_file[path].append((elem, new_id))

    stats = {"ids_renamed": 0, "files_modified": 0, "errors": []}
    for path, renames in renames_by_file.items():
        if not renames:
            continue
        try:
            for elem, new_id in renames:
                elem.set("id", new_id)
                stats["ids_renamed"] += 1
            tree = path_to_tree[path]
            root = tree.getroot()
            xml_bytes = serialize_normalized_dita_tree(root, _strip_ns(root.tag))
            path.write_bytes(xml_bytes)
            stats["files_modified"] += 1
        except Exception as ex:
            stats["errors"].append(f"{path.relative_to(folder)}: {ex}")

    if stats["ids_renamed"]:
        logger.info_structured(
            "DITA auto-fix: duplicate IDs",
            extra_fields={
                "folder": str(folder),
                "ids_renamed": stats["ids_renamed"],
                "files_modified": stats["files_modified"],
            },
        )
    return stats


def fix_missing_format(folder: Path) -> dict:
    """
    Add a deterministic @format to linking elements whose local @href points at a non-DITA
    target that can be inferred from its extension (.md→mdita, .html→html, .pdf→pdf, .txt→txt).
    Leaves ambiguous targets untouched. Returns {format_added, files_modified, changes[], errors[]}.
    """
    folder = Path(folder)
    stats: dict = {"format_added": 0, "files_modified": 0, "changes": [], "errors": []}
    if not folder.exists() or not folder.is_dir():
        stats["errors"].append("Folder does not exist")
        return stats

    for path in sorted(folder.rglob("*")):
        if path.suffix.lower() not in (".dita", ".ditamap"):
            continue
        try:
            tree = ET.parse(path)
            root = tree.getroot()
        except ET.ParseError:
            continue

        pending: list[tuple[ET.Element, str, str, str]] = []
        for elem in root.iter():
            tag = _strip_ns(elem.tag)
            if tag not in _FORMAT_FIX_LINK_ELEMENTS:
                continue
            href = elem.get("href")
            if not href or elem.get("format"):
                continue
            if elem.get("scope", "") in ("external", "peer") or _is_external_href(href):
                continue
            ext = Path(href.split("#", 1)[0]).suffix.lower()
            fmt = _FORMAT_BY_EXTENSION.get(ext)
            if fmt:
                pending.append((elem, fmt, href, tag))

        if not pending:
            continue
        for elem, fmt, _href, _tag in pending:
            elem.set("format", fmt)
        try:
            xml_bytes = serialize_normalized_dita_tree(root, _strip_ns(root.tag))
            path.write_bytes(xml_bytes)
            stats["files_modified"] += 1
            rel = str(path.relative_to(folder)).replace("\\", "/")
            for _elem, fmt, href, tag in pending:
                stats["format_added"] += 1
                stats["changes"].append({"file": rel, "element": tag, "href": href, "format": fmt})
        except Exception as ex:
            stats["errors"].append(f"{path.relative_to(folder)}: {ex}")

    if stats["format_added"]:
        logger.info_structured(
            "DITA auto-fix: missing @format",
            extra_fields={"folder": str(folder), "format_added": stats["format_added"], "files_modified": stats["files_modified"]},
        )
    return stats


def auto_fix_dita_folder(folder: Path) -> dict:
    """
    Run all safe auto-fixes on DITA folder.
    Returns combined stats from fix_duplicate_ids and fix_missing_format.
    """
    folder = Path(folder)
    result = {"ids_renamed": 0, "format_added": 0, "files_modified": 0, "changes": [], "errors": []}
    dup_result = fix_duplicate_ids(folder)
    fmt_result = fix_missing_format(folder)
    result["ids_renamed"] = dup_result["ids_renamed"]
    result["format_added"] = fmt_result["format_added"]
    result["files_modified"] = dup_result["files_modified"] + fmt_result["files_modified"]
    result["changes"] = fmt_result["changes"]
    result["errors"].extend(dup_result["errors"])
    result["errors"].extend(fmt_result["errors"])
    return result
