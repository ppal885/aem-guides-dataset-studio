"""Merge difficult_eval_bank entries into learned_qa_seed.json (idempotent by prompt)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.evaluation.difficult_eval_bank import EXTENDED_SEED_ENTRIES  # noqa: E402

SEED_PATH = BACKEND_ROOT / "app" / "storage" / "learned_qa_seed.json"


def merge_seed() -> dict[str, int]:
    existing = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    if not isinstance(existing, list):
        raise ValueError("learned_qa_seed.json must be a list")

    prompts = {str(item.get("prompt") or "").strip().lower() for item in existing}
    added = 0
    skipped = 0
    for entry in EXTENDED_SEED_ENTRIES:
        prompt = str(entry.get("prompt") or "").strip()
        key = prompt.lower()
        if not prompt or key in prompts:
            skipped += 1
            continue
        existing.append(entry)
        prompts.add(key)
        added += 1

    SEED_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"before": len(existing) - added, "added": added, "skipped": skipped, "after": len(existing)}


if __name__ == "__main__":
    stats = merge_seed()
    print(f"Seed merge: before={stats['before']} added={stats['added']} skipped={stats['skipped']} after={stats['after']}")
