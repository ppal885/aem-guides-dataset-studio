"""Build deterministic Windows and Unix MCP client team archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "release-artifacts"
PACKAGE_ROOT = "aem-guides-mcp-client"
PACKAGE_VERSION = "2026.08.13"
ARCHIVE_TIMESTAMP = (2026, 8, 13, 0, 0, 0)
PLATFORMS = ("windows", "unix")
IGNORED_NAMES = {"__pycache__", ".DS_Store", ".pytest_cache"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


def _source_dir(platform: str) -> Path:
    return RELEASE_DIR / f"aem-guides-mcp-client-{platform}"


def _output_path(platform: str) -> Path:
    return RELEASE_DIR / f"aem-guides-mcp-client-{platform}.zip"


def _included_files(source_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(source_dir.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(source_dir)
        if any(part in IGNORED_NAMES for part in relative.parts):
            continue
        if path.is_file() and path.suffix not in IGNORED_SUFFIXES:
            files.append(path)
    return files


def _archive_info(relative: Path, platform: str) -> zipfile.ZipInfo:
    archive_name = f"{PACKAGE_ROOT}/{relative.as_posix()}"
    info = zipfile.ZipInfo(archive_name, date_time=ARCHIVE_TIMESTAMP)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    mode = 0o755 if platform == "unix" and relative.suffix == ".sh" else 0o644
    info.external_attr = mode << 16
    return info


def _validate_source(source_dir: Path) -> None:
    version = (source_dir / "VERSION").read_text(encoding="utf-8").strip()
    if version != PACKAGE_VERSION:
        raise RuntimeError(
            f"{source_dir / 'VERSION'} is {version!r}; expected {PACKAGE_VERSION!r}"
        )
    required = (
        source_dir / "README.md",
        source_dir / ".claude" / "skills" / "test-plan-generation" / "SKILL.md",
        source_dir
        / ".claude"
        / "skills"
        / "test-plan-generation"
        / "scripts"
        / "authoring_state_contract.py",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"Package source is incomplete: {missing}")


def _validate_archive(output_path: Path) -> None:
    with zipfile.ZipFile(output_path) as archive:
        bad_file = archive.testzip()
        if bad_file:
            raise RuntimeError(f"ZIP integrity failed at {bad_file}")
        names = archive.namelist()
        required = {
            f"{PACKAGE_ROOT}/README.md",
            f"{PACKAGE_ROOT}/VERSION",
            f"{PACKAGE_ROOT}/.claude/skills/test-plan-generation/SKILL.md",
            f"{PACKAGE_ROOT}/.claude/skills/test-plan-generation/scripts/authoring_state_contract.py",
        }
        missing = sorted(required - set(names))
        if missing:
            raise RuntimeError(f"ZIP missing required entries: {missing}")
        if names != sorted(names):
            raise RuntimeError("ZIP entries are not deterministically ordered")
        invalid_roots = [name for name in names if not name.startswith(f"{PACKAGE_ROOT}/")]
        if invalid_roots:
            raise RuntimeError(f"ZIP has unexpected roots: {invalid_roots[:3]}")
        archived_version = archive.read(f"{PACKAGE_ROOT}/VERSION").decode().strip()
        if archived_version != PACKAGE_VERSION:
            raise RuntimeError(f"ZIP version is {archived_version!r}")


def build(platform: str) -> dict[str, object]:
    source_dir = _source_dir(platform)
    output_path = _output_path(platform)
    _validate_source(source_dir)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for source in _included_files(source_dir):
            relative = source.relative_to(source_dir)
            archive.writestr(
                _archive_info(relative, platform),
                source.read_bytes(),
                compress_type=zipfile.ZIP_STORED,
            )
    _validate_archive(output_path)
    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    return {
        "platform": platform,
        "version": PACKAGE_VERSION,
        "output": str(output_path),
        "bytes": output_path.stat().st_size,
        "sha256": digest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("all",) + PLATFORMS, default="all")
    args = parser.parse_args()
    platforms = PLATFORMS if args.platform == "all" else (args.platform,)
    print(json.dumps([build(platform) for platform in platforms], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
