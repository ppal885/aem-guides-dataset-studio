"""Resolve and copy DITA map closures for scoped DITA-OT runs."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from xml.etree import ElementTree as ET

EXTERNAL_HREF_PREFIXES = ("http://", "https://", "mailto:", "ftp://", "file://")
DITA_LIKE_EXTENSIONS = {".dita", ".ditamap", ".xml", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf"}


def _is_local_href(href: str) -> bool:
    value = (href or "").strip()
    if not value or value.startswith("#"):
        return False
    lowered = value.lower()
    return not lowered.startswith(EXTERNAL_HREF_PREFIXES)


def _should_follow_ref(element: ET.Element, href: str) -> bool:
    scope = (element.get("scope") or "").strip().lower()
    if scope in {"external", "peer"}:
        return False
    format_attr = (element.get("format") or "").strip().lower()
    if format_attr and format_attr not in {"dita", "ditamap", "xml", ""}:
        suffix = Path(href.split("#", 1)[0]).suffix.lower()
        if suffix not in DITA_LIKE_EXTENSIONS:
            return False
    return _is_local_href(href)


def _local_hrefs_from_xml(path: Path) -> list[str]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return []
    hrefs: list[str] = []
    for element in root.iter():
        href = element.get("href")
        if href and _should_follow_ref(element, href):
            hrefs.append(href.split("#", 1)[0])
    return hrefs


def collect_map_closure(map_path: Path) -> set[Path]:
    """Return absolute paths reachable from a ditamap via local href references."""
    root_map = map_path.resolve()
    if not root_map.is_file():
        raise FileNotFoundError(f"Map not found: {root_map}")

    seen: set[Path] = set()
    queue: list[Path] = [root_map]

    while queue:
        current = queue.pop()
        current = current.resolve()
        if current in seen or not current.is_file():
            continue
        seen.add(current)

        suffix = current.suffix.lower()
        if suffix not in {".ditamap", ".dita", ".xml"}:
            continue

        for href in _local_hrefs_from_xml(current):
            target = (current.parent / href).resolve()
            if target.suffix.lower() not in DITA_LIKE_EXTENSIONS and target.suffix:
                seen.add(target)
                continue
            if target not in seen:
                queue.append(target)

    return seen


def copy_map_closure_to_dir(map_path: Path, dest_dir: Path) -> list[Path]:
    """Copy only the map closure into dest_dir, preserving relative paths when possible."""
    map_path = map_path.resolve()
    dest_dir = dest_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    base_dir = map_path.parent
    for source in sorted(collect_map_closure(map_path)):
        try:
            relative = source.relative_to(base_dir)
        except ValueError:
            relative = Path(source.name)
        target = dest_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(target)
    return copied
