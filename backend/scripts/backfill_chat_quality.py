"""Backfill chat_answer_quality rows from existing assistant messages."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.migrations import run_migrations
from app.db.session import SessionLocal
from app.services.chat_quality_service import backfill_quality_from_messages


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill chat answer quality metrics")
    parser.add_argument("--limit", type=int, default=5000, help="Max assistant messages to scan")
    parser.add_argument("--skip-migrations", action="store_true", help="Skip running DB migrations first")
    args = parser.parse_args()

    if not args.skip_migrations:
        run_migrations()

    db = SessionLocal()
    try:
        result = backfill_quality_from_messages(db, limit=args.limit)
    finally:
        db.close()

    print(f"Processed {result['processed']} assistant messages; created {result['created']} quality rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
