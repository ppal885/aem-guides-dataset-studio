#!/usr/bin/env python3
"""Backfill filterable source provenance in documentation Chroma collections."""

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

from app.services.knowledge_corpus_audit_service import migrate_knowledge_corpus_metadata  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args(argv or sys.argv[1:])
    report = migrate_knowledge_corpus_metadata(
        dry_run=args.dry_run,
        batch_size=max(1, min(args.batch_size, 2000)),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if (
        report.get("available")
        and int(report.get("total_failed") or 0) == 0
        and int(report.get("scan_failure_count") or 0) == 0
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
