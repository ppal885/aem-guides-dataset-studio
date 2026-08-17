#!/usr/bin/env python3
"""Preview or bootstrap the Jira QA incremental-sync cursor from indexed metadata."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env.docker"
for candidate in (PROJECT_ROOT, BACKEND_DIR):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)

def _load_env_file(path: Path) -> str | None:
    if not path.exists():
        return f"env file not found: {path}"
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
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
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--project", default="")
    parser.add_argument("--sync-state-id", default="")
    parser.add_argument("--apply", action="store_true", help="persist the proposed cursor")
    parser.add_argument("--force", action="store_true", help="repair even when a valid cursor exists")
    parser.add_argument("--skip-sql", action="store_true", help="derive only from Chroma metadata")
    args = parser.parse_args(argv or sys.argv[1:])
    env_warning = _load_env_file(args.env_file)

    from app.services.jira_sync_cursor_service import bootstrap_jira_sync_cursor

    try:
        report = bootstrap_jira_sync_cursor(
            args.project or None,
            sync_state_id=args.sync_state_id or None,
            dry_run=not args.apply,
            force=args.force,
            include_sql=not args.skip_sql,
        )
    except ValueError as exc:
        report = {"available": False, "valid": False, "error": str(exc)}
    if env_warning:
        report.setdefault("warnings", []).append(env_warning)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report.get("available") and report.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
