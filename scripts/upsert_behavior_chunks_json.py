#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Upsert prebuilt behavior chunk JSON into the configured Chroma store."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
for candidate in (PROJECT_ROOT, BACKEND_DIR, Path(__file__).resolve().parent):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)

from index_dita_behavior_corpus import upsert_to_chroma  # noqa: E402


DEFAULT_INPUT = PROJECT_ROOT / "backend" / "storage" / "aem_guides_enriched_behavior_chunks.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    records = load_records(args.input)
    if args.dry_run:
        upserted = 0
        mode = "dry-run"
    else:
        upserted = upsert_to_chroma(records, batch_size=max(1, args.batch_size)) if records else 0
        mode = "upsert"
    print(
        json.dumps(
            {
                "input": str(args.input),
                "chunks_seen": len(records),
                "chunks_upserted": upserted,
                "mode": mode,
            },
            indent=2,
        )
    )
    return 0


def load_records(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"expected JSON array in {path}")
    return [record for record in raw if isinstance(record, dict)]


if __name__ == "__main__":
    raise SystemExit(main())
