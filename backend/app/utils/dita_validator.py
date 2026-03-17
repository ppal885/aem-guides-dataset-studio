"""DITA validator - check IDs, hrefs, conrefs, conrefend, keyrefs."""
import re
from pathlib import Path
from typing import Optional
from collections import defaultdict

import xml.etree.ElementTree as ET

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


def _parse_dita_files(folder: Path) -> list[tuple[Path, ET.Element]]:
    """Parse all .dita and .ditamap files in folder."""
    parsed = []
    for p in folder.rglob("*"):
        if p.suffix.lower() in (".dita", ".ditamap"):
            try:
                tree = ET.parse(p)
                parsed.append((p, tree.getroot()))
            except ET.ParseError as e:
                parsed.append((p, None))
    return parsed


def _collect_ids(root: ET.Element, ns: dict) -> list[tuple[str, str]]:
    """Collect (id, tag) from element and descendants."""
    ids = []
    for elem in root.iter():
        eid = elem.get("id")
        if eid:
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            ids.append((eid, tag))
    return ids


def _collect_ids_with_order(root: ET.Element) -> list[tuple[str, ET.Element]]:
    """Collect (id, element) in document order."""
    result = []
    for elem in root.iter():
        eid = elem.get("id")
        if eid:
            result.append((eid, elem))
    return result


def _collect_hrefs(root: ET.Element) -> list[str]:
    """Collect href values."""
    hrefs = []
    for elem in root.iter():
        h = elem.get("href")
        if h:
            hrefs.append(h)
        h = elem.get("conref")
        if h:
            hrefs.append(h.split("#")[0] if "#" in h else h)
    return hrefs


def _fragment_ids_in_file(frag: str, ids_in_file: set[str]) -> bool:
    """
    Check if fragment exists in the given file's ids.
    Supports: #elementId and #topicId/elementId (both ids must exist in file).
    """
    if not frag:
        return True
    if "/" in frag:
        parts = frag.split("/", 1)
        return parts[0] in ids_in_file and parts[1] in ids_in_file
    return frag in ids_in_file


def _get_element_id(elem: ET.Element) -> Optional[str]:
    """Get id of element (for self-loop check)."""
    return elem.get("id")


def validate_dita_folder(folder: Path) -> dict:
    """
    Validate DITA content in folder.
    Returns {errors: [], warnings: []}.
    Validates: duplicate ids, href, conref, conrefend (same-file and cross-file).
    Fails on: missing target, conrefend end before start, self-loop conref, duplicate ids.
    """
    folder = Path(folder)
    if not folder.exists() or not folder.is_dir():
        return {"errors": ["Folder does not exist"], "warnings": []}

    errors = []
    warnings = []
    ns = {"dita": "http://dita.oasis-open.org/architecture/2005/"}

    parsed = _parse_dita_files(folder)
    all_ids = defaultdict(list)
    ids_per_file = defaultdict(set)
    id_to_file = {}
    all_files = {}
    file_element_order = {}  # rel -> [(id, elem), ...] in document order

    for path, root in parsed:
        if root is None:
            errors.append(f"Parse error: {path.relative_to(folder)}")
            continue
        rel = str(path.relative_to(folder)).replace("\\", "/")
        all_files[rel] = path
        for eid, tag in _collect_ids(root, ns):
            all_ids[eid].append((rel, tag))
            ids_per_file[rel].add(eid)
            id_to_file[eid] = rel
        file_element_order[rel] = _collect_ids_with_order(root)

    for eid, locations in all_ids.items():
        if len(locations) > 1:
            errors.append(f"Duplicate ID '{eid}' in: {[l[0] for l in locations]}")

    for path, root in parsed:
        if root is None:
            continue
        rel = str(path.relative_to(folder)).replace("\\", "/")
        dir_path = path.parent
        ids_in_file = ids_per_file[rel]
        elem_order = {eid: i for i, (eid, _) in enumerate(file_element_order[rel])}

        for elem in root.iter():
            href = elem.get("href") or elem.get("conref")
            conrefend_val = elem.get("conrefend")

            if href:
                path_part = ""
                frag = ""
                if "#" in href:
                    path_part, frag = href.split("#", 1)
                else:
                    path_part = href

                target_file = rel
                if path_part:
                    target_path = (dir_path / path_part).resolve()
                    if not target_path.exists():
                        errors.append(f"Broken href '{path_part}' in {rel}")
                        continue
                    target_rel = str(target_path.relative_to(folder)).replace("\\", "/")
                    target_file = target_rel
                    target_ids = ids_per_file.get(target_rel, set())
                else:
                    target_ids = ids_in_file

                if frag and not _fragment_ids_in_file(frag, target_ids):
                    errors.append(f"Target fragment #{frag} missing in {rel}")

                if elem.get("conref") and _get_element_id(elem) and frag:
                    src_id = _get_element_id(elem)
                    if "/" in frag:
                        target_elem_id = frag.split("/")[-1]
                    else:
                        target_elem_id = frag
                    if src_id == target_elem_id and target_file == rel:
                        errors.append(f"Self-loop conref: element {src_id} references itself in {rel}")

            if conrefend_val:
                path_part_end = ""
                frag_end = ""
                if "#" in conrefend_val:
                    path_part_end, frag_end = conrefend_val.split("#", 1)
                else:
                    path_part_end = conrefend_val

                if not frag_end:
                    errors.append(f"conrefend missing fragment in {rel}")
                else:
                    target_file_end = rel
                    if path_part_end:
                        target_path_end = (dir_path / path_part_end).resolve()
                        if not target_path_end.exists():
                            errors.append(f"conrefend target file '{path_part_end}' missing in {rel}")
                        else:
                            target_rel_end = str(target_path_end.relative_to(folder)).replace("\\", "/")
                            target_file_end = target_rel_end
                            target_ids_end = ids_per_file.get(target_rel_end, set())
                    else:
                        target_ids_end = ids_in_file

                    if not _fragment_ids_in_file(frag_end, target_ids_end):
                        errors.append(f"conrefend target fragment #{frag_end} missing in {rel}")
                    elif href and elem.get("conref"):
                        frag = ""
                        if "#" in href:
                            _, frag = href.split("#", 1)
                        if frag and target_file_end == rel and target_file == rel:
                            start_id = frag.split("/")[-1] if "/" in frag else frag
                            end_id = frag_end.split("/")[-1] if "/" in frag_end else frag_end
                            start_idx = elem_order.get(start_id, -1)
                            end_idx = elem_order.get(end_id, -1)
                            if start_idx >= 0 and end_idx >= 0 and end_idx < start_idx:
                                errors.append(
                                    f"conrefend order invalid: end #{frag_end} before start #{frag} in {rel}"
                                )

        if rel.endswith(".dita"):
            for body in root.iter():
                btag = body.tag.split("}")[-1] if "}" in body.tag else body.tag
                if btag == "body":
                    for child in body.iter():
                        if child is body:
                            continue
                        ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                        if ctag == "topicmeta":
                            errors.append(f"Invalid topicmeta placement: topicmeta inside body in {rel}")
                            break

    return {"errors": errors, "warnings": warnings}
