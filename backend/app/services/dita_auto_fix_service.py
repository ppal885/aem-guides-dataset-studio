"""DITA auto-fix service - programmatically fix common validation errors."""
from collections import defaultdict
from pathlib import Path

import xml.etree.ElementTree as ET

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


def _collect_ids_from_root(root: ET.Element) -> list[tuple[ET.Element, str]]:
    """Return [(element, id)] for all elements with id attribute."""
    result = []
    for elem in root.iter():
        eid = elem.get("id")
        if eid:
            result.append((elem, eid))
    return result


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
            xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True, method="xml")
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


def auto_fix_dita_folder(folder: Path) -> dict:
    """
    Run all safe auto-fixes on DITA folder.
    Returns combined stats from fix_duplicate_ids.
    """
    folder = Path(folder)
    result = {"ids_renamed": 0, "files_modified": 0, "errors": []}
    dup_result = fix_duplicate_ids(folder)
    result["ids_renamed"] = dup_result["ids_renamed"]
    result["files_modified"] = dup_result["files_modified"]
    result["errors"].extend(dup_result["errors"])
    return result
