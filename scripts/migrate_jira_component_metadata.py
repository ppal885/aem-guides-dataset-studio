#!/usr/bin/env python3
"""Backfill scalar Jira component metadata in Chroma without Jira API access."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
for candidate in (PROJECT_ROOT, BACKEND_DIR):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)

from app.services.jira_component_metadata_service import migrate_jira_component_primary  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv or sys.argv[1:])
    result = migrate_jira_component_primary(dry_run=args.dry_run, batch_size=max(1, args.batch_size))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
