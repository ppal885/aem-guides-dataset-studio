"""Freeze generated benchmark output before any evaluator can read answers."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze_generated_output(
    output_path: Path,
    freeze_manifest_path: Path,
    *,
    split: str,
    record_id: str,
) -> dict[str, Any]:
    output = output_path.resolve()
    if not output.is_file():
        raise FileNotFoundError(output)
    payload = {
        "schema_version": "aem-guides-benchmark-output-freeze-v2",
        "split": split,
        "record_id": record_id,
        "output_path": str(output),
        "output_bytes": output.stat().st_size,
        "output_sha256": file_sha256(output),
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "frozen": True,
    }
    freeze_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    freeze_manifest_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return payload
