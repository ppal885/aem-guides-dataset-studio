"""
Resolve DITA DOCTYPE SYSTEM paths against generated ZIP layout.

Job config typically uses SYSTEM ids like ``technicalContent/dtd/topic.dtd``, which only
work for files at the dataset root. Topics under ``topics/tasks/`` would otherwise
resolve to missing paths. This module rewrites DOCTYPE system literals to correct
relative paths and ensures minimal stub DTDs exist under ``{base}/technicalContent/dtd/``.
"""

from __future__ import annotations

import os
import re
from typing import Dict, Optional

from app.generator.dtd_stubs import DATASET_DTD_STUBS
from app.generator.generate import safe_join

# Root element -> stub filename (match XML document element, case-sensitive).
ROOT_TO_DTD: dict[str, str] = {
    "topic": "topic.dtd",
    "task": "task.dtd",
    "concept": "concept.dtd",
    "reference": "reference.dtd",
    "glossentry": "glossentry.dtd",
    "map": "map.dtd",
    "bookmap": "bookmap.dtd",
    "subjectScheme": "subjectScheme.dtd",
}

# Catalog public IDs must match the document root; a <reference> with "DITA Topic//EN" loads the wrong grammar.
ROOT_ELEMENT_PUBLIC_ID: dict[str, str] = {
    "topic": "-//OASIS//DTD DITA Topic//EN",
    "task": "-//OASIS//DTD DITA Task//EN",
    "concept": "-//OASIS//DTD DITA Concept//EN",
    "reference": "-//OASIS//DTD DITA Reference//EN",
    "glossentry": "-//OASIS//DTD DITA Glossentry//EN",
    "map": "-//OASIS//DTD DITA Map//EN",
    "bookmap": "-//OASIS//DTD DITA BookMap//EN",
    "subjectScheme": "-//OASIS//DTD DITA Subject Scheme Map//EN",
}

_DOCTYPE_PUBLIC_RE = re.compile(
    rb"<!DOCTYPE\s+(\S+)\s+PUBLIC\s+\"([^\"]*)\"\s+\"([^\"]*)\"\s*>",
    re.IGNORECASE | re.DOTALL,
)
_DOCTYPE_SYSTEM_RE = re.compile(
    rb"<!DOCTYPE\s+(\S+)\s+SYSTEM\s+\"([^\"]*)\"\s*>",
    re.IGNORECASE | re.DOTALL,
)


def _posix_relpath(from_dir: str, to_file: str) -> str:
    rel = os.path.relpath(to_file.replace("/", os.sep), from_dir.replace("/", os.sep))
    return rel.replace("\\", "/")


def _norm_join(dir_path: str, relative: str) -> str:
    if not dir_path:
        return relative.replace("\\", "/")
    combined = os.path.normpath(
        os.path.join(dir_path.replace("/", os.sep), relative.replace("/", os.sep))
    )
    return combined.replace("\\", "/")


def _parse_root_element(data: bytes) -> Optional[str]:
    m = re.search(rb"<!DOCTYPE[^>]+>", data, re.IGNORECASE | re.DOTALL)
    pos = m.end() if m else 0
    m2 = re.search(rb"<\s*([a-zA-Z][\w:.-]*)", data[pos : pos + 20000])
    return m2.group(1).decode("utf-8") if m2 else None


def _stub_path(base: str, dtd_name: str) -> str:
    return safe_join(base, "technicalContent", "dtd", dtd_name)


def _ensure_stub(files: Dict[str, bytes], base: str, dtd_name: str) -> None:
    key = _stub_path(base, dtd_name)
    if key not in files and dtd_name in DATASET_DTD_STUBS:
        files[key] = DATASET_DTD_STUBS[dtd_name].encode("utf-8")


def _rewrite_one_file(path: str, data: bytes, files: Dict[str, bytes], base: str) -> Optional[bytes]:
    if not data.startswith(b"<?xml"):
        return None

    pub_m = _DOCTYPE_PUBLIC_RE.search(data)
    sys_m = _DOCTYPE_SYSTEM_RE.search(data)
    if not pub_m and not sys_m:
        return None

    if pub_m:
        decl_name = pub_m.group(1).decode("utf-8")
        original_public = pub_m.group(2).decode("utf-8")
        system_id = pub_m.group(3).decode("utf-8")
    else:
        decl_name = sys_m.group(1).decode("utf-8")
        original_public = None
        system_id = sys_m.group(2).decode("utf-8")

    if not system_id or system_id.startswith("http://") or system_id.startswith("https://"):
        return None

    root_el = _parse_root_element(data) or decl_name
    public_id = original_public
    if pub_m and original_public is not None:
        canonical_pub = ROOT_ELEMENT_PUBLIC_ID.get(root_el)
        if canonical_pub:
            public_id = canonical_pub

    file_dir = os.path.dirname(path).replace("\\", "/")
    resolved = _norm_join(file_dir, system_id)

    dtd_name = ROOT_TO_DTD.get(root_el)
    if not dtd_name:
        base_name = os.path.basename(system_id.replace("\\", "/"))
        dtd_name = base_name if base_name.endswith(".dtd") else f"{root_el}.dtd"

    _ensure_stub(files, base, dtd_name)
    stub_key = _stub_path(base, dtd_name)

    if stub_key not in files and dtd_name != "topic.dtd":
        dtd_name = "topic.dtd"
        _ensure_stub(files, base, dtd_name)
        stub_key = _stub_path(base, dtd_name)

    if stub_key not in files:
        return None

    # Keep existing system id when it already resolves inside the dataset (path OK); still fix root/public mismatch.
    if resolved in files:
        new_system = system_id
    else:
        new_system = _posix_relpath(file_dir, stub_key)

    decl_el = root_el
    if pub_m:
        candidate = f'<!DOCTYPE {decl_el} PUBLIC "{public_id}" "{new_system}">'.encode("utf-8")
        old_decl = data[pub_m.start() : pub_m.end()]
    else:
        candidate = f'<!DOCTYPE {decl_el} SYSTEM "{new_system}">'.encode("utf-8")
        old_decl = data[sys_m.start() : sys_m.end()]

    if old_decl == candidate:
        return None

    if pub_m:
        new_data = _DOCTYPE_PUBLIC_RE.sub(candidate, data, count=1)
    else:
        new_data = _DOCTYPE_SYSTEM_RE.sub(candidate, data, count=1)

    return new_data


def _should_process_path(path: str, base: str) -> bool:
    if base and not (path == base or path.startswith(base + "/")):
        return False
    lower = path.lower()
    return lower.endswith(".dita") or lower.endswith(".ditamap")


def ensure_dataset_dtd_resolution(files: Dict[str, bytes], base: str) -> None:
    """Mutate ``files`` in place: add missing stubs and fix DOCTYPE paths for DITA files under ``base``."""
    if not base or not files:
        return
    for path in list(files.keys()):
        if not _should_process_path(path, base):
            continue
        data = files.get(path)
        if not isinstance(data, (bytes, bytearray)):
            continue
        new_bytes = _rewrite_one_file(path, bytes(data), files, base)
        if new_bytes is not None:
            files[path] = new_bytes


def normalize_dtd_in_file_batch(batch: Dict[str, bytes], base: str) -> None:
    """Same as ``ensure_dataset_dtd_resolution`` but only for keys in ``batch`` (streaming)."""
    if not base or not batch:
        return
    for path in list(batch.keys()):
        if not _should_process_path(path, base):
            continue
        data = batch.get(path)
        if not isinstance(data, (bytes, bytearray)):
            continue
        new_bytes = _rewrite_one_file(path, bytes(data), batch, base)
        if new_bytes is not None:
            batch[path] = new_bytes
