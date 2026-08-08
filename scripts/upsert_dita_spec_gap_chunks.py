#!/usr/bin/env python3
"""Upsert authoritative curated DITA gap chunks into the dita_spec collection."""

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

from app.services.dita_spec_curated_chunk_service import (  # noqa: E402
    load_curated_dita_spec_chunks,
    upsert_curated_dita_spec_chunks,
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    records = load_curated_dita_spec_chunks()
    upserted = 0 if args.dry_run else upsert_curated_dita_spec_chunks(batch_size=max(1, args.batch_size))
    print(json.dumps({
        "collection": "dita_spec",
        "chunks_seen": len(records),
        "chunks_upserted": upserted,
        "mode": "dry-run" if args.dry_run else "upsert",
        "constructs": [record["construct"] for record in records],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
