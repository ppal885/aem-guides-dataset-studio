#!/usr/bin/env python3
"""Conservatively backfill unknown Jira domains in Chroma and SQL."""

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
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--apply", action="store_true", help="apply changes; default is dry-run")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--skip-sql", action="store_true")
    args = parser.parse_args(argv or sys.argv[1:])
    env_warning = _load_env_file(args.env_file)

    from app.services.jira_domain_metadata_service import migrate_unknown_jira_domains

    report = migrate_unknown_jira_domains(
        dry_run=not args.apply,
        batch_size=max(1, min(args.batch_size, 2000)),
        sync_sql=not args.skip_sql,
    )
    if env_warning:
        report.setdefault("warnings", []).append(env_warning)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sql_sync = report.get("sql_sync") or {}
    sql_failed = bool(args.apply and not args.skip_sql and not sql_sync.get("skipped") and not sql_sync.get("available"))
    return 0 if report.get("available") and int(report.get("failed_chunk_count") or 0) == 0 and not sql_failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
