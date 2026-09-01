#!/usr/bin/env python3
"""Export the checked-in JSON Schema for the canonical EvidenceRecord."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.schemas_canonical_test_plan_runtime import EvidenceRecord


def main() -> int:
    path = ROOT / "schemas" / "evidence_record.schema.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(EvidenceRecord.model_json_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
