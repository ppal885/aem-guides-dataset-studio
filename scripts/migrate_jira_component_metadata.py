#!/usr/bin/env python3
"""Canonicalize Jira component metadata in Chroma without Jira API access."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
for candidate in (PROJECT_ROOT, BACKEND_DIR):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)

def _load_env_file(path: Path) -> str | None:
    if not path.exists():
        return f"env file not found: {path}"
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        return f"env file could not be read: {exc}"
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name or " " in name:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[name] = value
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--batch-size", type=int, default=500)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="apply metadata changes")
    mode.add_argument("--dry-run", action="store_true", help="scan only; this is the default")
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="return nonzero when the scan still finds records requiring migration",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    env_warning = _load_env_file(args.env_file) if args.env_file else None

    from app.services.jira_component_metadata_service import migrate_jira_component_primary

    result = migrate_jira_component_primary(
        dry_run=not args.apply,
        batch_size=max(1, min(args.batch_size, 5000)),
    )
    if env_warning:
        result["warning"] = env_warning
    print(json.dumps(result, indent=2))
    if args.require_clean and int(result.get("pending") or 0) != 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
