"""Create and verify deterministic fingerprints for maintained skill files."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import overload


SCHEMA_VERSION = "aem-guides-skill-bundle-fingerprint-v2"
INCLUDED_SUFFIXES = frozenset({".json", ".md", ".py", ".yaml", ".yml"})

# These files intentionally differ between the Codex source and other clients.
# They are not part of cross-copy enforcement and must never be overwritten by
# the selective global sync.
CODEX_ONLY_EXTENSIONS = frozenset(
    {
        "SKILL.md",
        "references/quality-gate-checklist.md",
        "scripts/test_skill_scripts.py",
    }
)

CANONICAL_ENV = "AEM_GUIDES_TEST_PLAN_CANONICAL_ROOT"
SYNC_SCRIPT = Path("scripts") / "sync_test_plan_skill_copies.py"
CANONICAL_RELATIVE_ROOT = Path(".codex") / "skills" / "test-plan-generation"


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _included_files(skill_root: Path) -> list[Path]:
    root = skill_root.expanduser().resolve()
    return sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and path.suffix.lower() in INCLUDED_SUFFIXES
            and "__pycache__" not in path.parts
            and _relative(path, root) not in CODEX_ONLY_EXTENSIONS
        ),
        key=lambda path: _relative(path, root),
    )


def enforced_relative_paths(skill_root: Path | str) -> tuple[str, ...]:
    """Return the stable, non-Codex-only file set enforced across copies."""
    root = Path(skill_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"invalid test-plan-generation skill root: {root}")
    return tuple(_relative(path, root) for path in _included_files(root))


def _file_hashes(skill_root: Path) -> dict[str, str]:
    root = skill_root.expanduser().resolve()
    return {
        _relative(path, root): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in _included_files(root)
    }


def fingerprint(skill_root: Path | str) -> dict:
    """Return an aggregate and per-file hash for the enforced skill file set."""
    root = Path(skill_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"invalid test-plan-generation skill root: {root}")
    files = _file_hashes(root)
    digest = hashlib.sha256()
    for relative, content_hash in files.items():
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content_hash.encode("ascii"))
        digest.update(b"\n")
    return {
        "schema_version": SCHEMA_VERSION,
        "root": str(root),
        "sha256": digest.hexdigest(),
        "file_count": len(files),
        "files": files,
    }


def _repository_candidates(*starts: Path) -> list[Path]:
    candidates: list[Path] = []
    for start in starts:
        resolved = start.expanduser().resolve()
        current = resolved if resolved.is_dir() else resolved.parent
        candidates.extend((current, *current.parents))

    home = Path.home().resolve()
    try:
        first_level = [path for path in home.iterdir() if path.is_dir()]
    except OSError:
        first_level = []
    candidates.extend(first_level)
    for container in first_level:
        try:
            candidates.extend(path for path in container.iterdir() if path.is_dir())
        except OSError:
            continue
    return list(dict.fromkeys(candidates))


def canonical_skill_root(copy_dir: Path | str | None = None) -> Path:
    """Locate the repository-owned ``.codex`` source of truth."""
    explicit = os.environ.get(CANONICAL_ENV, "").strip()
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        if candidate.name != "test-plan-generation":
            candidate = candidate / CANONICAL_RELATIVE_ROOT
        if candidate.is_dir():
            return candidate
        raise RuntimeError(f"{CANONICAL_ENV} does not identify a skill directory")

    starts = [Path(__file__).resolve(), Path.cwd().resolve()]
    if copy_dir is not None:
        starts.insert(0, Path(copy_dir).expanduser().resolve())
    for repository in _repository_candidates(*starts):
        candidate = repository / CANONICAL_RELATIVE_ROOT
        if candidate.is_dir() and (repository / SYNC_SCRIPT).is_file():
            return candidate.resolve()
    raise RuntimeError("canonical test-plan-generation source could not be located")


def _verify_receipt_record(record: object, *, expected_root: Path) -> None:
    """Raise ``ValueError`` when a receipt targets a changed skill file set."""
    if not isinstance(record, dict) or record.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"validator fingerprint schema_version must be {SCHEMA_VERSION}")
    root = Path(str(record.get("root", ""))).expanduser().resolve()
    expected = expected_root.expanduser().resolve()
    if root != expected:
        raise ValueError("validator fingerprint root does not match the executing skill")
    current = fingerprint(expected)
    if record.get("file_count") != current["file_count"]:
        raise ValueError("validator fingerprint file count mismatch")
    if str(record.get("sha256", "")).lower() != current["sha256"]:
        raise ValueError("validator fingerprint hash mismatch; rerun the full gate")


def _verify_copy(copy_dir: Path | str) -> tuple[bool, list[str]]:
    copy_root = Path(copy_dir).expanduser().resolve()
    canonical_root = canonical_skill_root(copy_root)
    expected = _file_hashes(canonical_root)
    drifted: list[str] = []
    for relative, expected_hash in expected.items():
        candidate = copy_root / Path(relative)
        if not candidate.is_file() or candidate.is_symlink():
            drifted.append(relative)
            continue
        try:
            actual_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
        except OSError:
            drifted.append(relative)
            continue
        if actual_hash != expected_hash:
            drifted.append(relative)
    return not drifted, drifted


@overload
def verify(copy_dir: Path | str) -> tuple[bool, list[str]]: ...


@overload
def verify(record: object, *, expected_root: Path) -> None: ...


def verify(value: object, *, expected_root: Path | None = None):
    """Verify a copy, while retaining receipt-fingerprint compatibility.

    ``verify(copy_dir)`` returns ``(ok, drifted_files)`` for the enforced file
    set. The keyword-only legacy form validates a hash-bound gate receipt.
    """
    if expected_root is not None:
        _verify_receipt_record(value, expected_root=expected_root)
        return None
    if not isinstance(value, (str, os.PathLike)):
        raise TypeError("copy_dir must be a filesystem path")
    return _verify_copy(Path(value))
