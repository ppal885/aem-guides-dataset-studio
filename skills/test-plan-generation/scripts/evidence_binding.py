"""Bind explicitly selected local files, without claiming semantic inspection.

Only paths selected by the author are read. No recursive scanning, network,
source text copying, or executed-query/USED/authority claims are generated.
"""

import hashlib
from pathlib import Path

from scaffold_support import AUTHOR_CONFIRM, object_list, strings


def catalog_entries(manifest):
    raw = manifest.get("evidence_catalog", [])
    if isinstance(raw, dict):
        raw = raw.get("sources") or raw.get("entries", [])
    entries = object_list(raw, "evidence_catalog")
    ids = [entry_id(row) for row in entries]
    if any(not eid for eid in ids) or len(set(ids)) != len(ids):
        raise ValueError("evidence_catalog requires unique non-empty id/source_id values")
    return entries


def entry_id(row):
    value = row.get("id") or row.get("source_id", "")
    if not isinstance(value, str):
        raise ValueError("evidence_catalog id/source_id must be a string")
    return value.strip()


def bind_files(manifest, files, *, base_dir):
    """Mutate a caller-owned manifest copy; failures remain explicit gaps.

    Complete an unhashed, path-bound entry without renaming its ID. Otherwise
    reuse an ID only for the same path AND bytes. Changed bytes get a new ID,
    leaving old evidence/decisions intact for the provenance gate to flag.
    """
    files = strings(files, "inspected_files")
    entries = catalog_entries(manifest)
    lifecycle = object_list(manifest.setdefault("evidence_lifecycle", []), "evidence_lifecycle")
    bindings, gaps = [], []
    for selected in files:
        path = Path(selected).expanduser()
        if not path.is_absolute():
            path = Path(base_dir) / path
        try:
            path = path.resolve(strict=True)
            if not path.is_file():
                raise ValueError("not a regular file")
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                before = path.stat()
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError("file changed while hashing")
        except (OSError, ValueError):
            gaps.append(f"Cannot bind selected file {selected!r}: missing, unreadable, non-file, or changed during hashing.")
            continue
        ref, source_hash = path.as_posix(), "sha256:" + digest.hexdigest()
        row = next((row for row in entries if row.get("source_ref") == ref
                    and row.get("source_hash") == source_hash), None)
        if row is None:
            unhashed = [row for row in entries if row.get("source_ref") == ref and not row.get("source_hash")]
            if len(unhashed) > 1:
                raise ValueError("multiple unhashed catalog IDs name the selected file; resolve the ambiguity first")
            if unhashed:
                row = unhashed[0]
                row["source_hash"] = source_hash
                row.setdefault("source_type", "code")
                row.setdefault("retrieval_method", "local_file_hash")
                row.setdefault("content_inspected", False)
        if row is None:
            eid = "E-FILE-" + hashlib.sha256((ref + "\n" + source_hash).encode("utf-8")).hexdigest()[:24]
            if any(entry_id(row) == eid for row in entries):
                raise ValueError("generated file evidence ID collides with an existing entry")
            row = {"id": eid, "source_type": "code", "source_ref": ref,
                   "source_hash": source_hash, "retrieval_method": "local_file_hash",
                   "content_inspected": False}
            entries.append(row)
        eid = entry_id(row)
        bindings.append({"evidence_id": eid, "source_ref": ref, "source_hash": source_hash})
        if not any(item.get("evidence_id") == eid for item in lifecycle):
            lifecycle.append({
                "evidence_id": eid, "source": "current repository", "query": "",
                "pass": "initial", "status": "RETRIEVED", "question_id": "",
                "hypothesis_id": "", "subject": "", "authority": "",
                "source_ref": ref, "source_hash": source_hash,
                "author_review_required": True,
                "review_note": AUTHOR_CONFIRM + ": record the actual inspection query and bindings; hashing is not semantic use.",
            })
    raw = manifest.get("evidence_catalog")
    if isinstance(raw, dict):
        key = "sources" if raw.get("sources") or "entries" not in raw else "entries"
        raw[key] = entries
    else:
        manifest["evidence_catalog"] = entries
    return {"bindings": bindings, "gaps": gaps}
