"""Create and verify a deterministic fingerprint for the executing skill bundle."""

from __future__ import annotations

import hashlib
from pathlib import Path


SCHEMA_VERSION = "aem-guides-skill-bundle-fingerprint-v1"
INCLUDED_SUFFIXES = {".json", ".md", ".py", ".yaml", ".yml"}


def _included_files(skill_root: Path) -> list[Path]:
    root = skill_root.resolve()
    return sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in INCLUDED_SUFFIXES
            and "__pycache__" not in path.parts
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def fingerprint(skill_root: Path) -> dict:
    """Return a path-bound inventory hash for all maintained skill sources."""
    root = skill_root.resolve()
    if not (root / "SKILL.md").is_file() or not (root / "scripts").is_dir():
        raise ValueError(f"invalid test-plan-generation skill root: {root}")
    files = _included_files(root)
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix()
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content_hash.encode("ascii"))
        digest.update(b"\n")
    return {
        "schema_version": SCHEMA_VERSION,
        "root": str(root),
        "sha256": digest.hexdigest(),
        "file_count": len(files),
    }


def verify(record: object, *, expected_root: Path) -> None:
    """Raise ``ValueError`` when a receipt targets a different or changed skill."""
    if not isinstance(record, dict) or record.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"validator fingerprint schema_version must be {SCHEMA_VERSION}")
    root = Path(str(record.get("root", ""))).resolve()
    expected = expected_root.resolve()
    if root != expected:
        raise ValueError("validator fingerprint root does not match the executing skill")
    current = fingerprint(expected)
    if record.get("file_count") != current["file_count"]:
        raise ValueError("validator fingerprint file count mismatch")
    if str(record.get("sha256", "")).lower() != current["sha256"]:
        raise ValueError("validator fingerprint hash mismatch; rerun the full gate")
