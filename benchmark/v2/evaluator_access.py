"""Evaluator-only access after an immutable candidate output freeze."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from .freeze import file_sha256
except ImportError:  # Direct-file loading used by the standalone guard tests.
    from freeze import file_sha256


class EvaluationAccessError(RuntimeError):
    pass


def load_ground_truth_after_freeze(
    benchmark_root: Path,
    split: str,
    record_id: str,
    output_path: Path,
    freeze_manifest_path: Path,
) -> dict[str, Any]:
    if split not in {"train", "validation", "blind"}:
        raise EvaluationAccessError(f"Unknown benchmark split: {split}")
    if not freeze_manifest_path.is_file():
        raise EvaluationAccessError("Generated output must be frozen before evaluation")
    freeze = json.loads(freeze_manifest_path.read_text(encoding="utf-8"))
    output = output_path.resolve()
    if not freeze.get("frozen"):
        raise EvaluationAccessError("Freeze manifest is not final")
    if freeze.get("split") != split or freeze.get("record_id") != record_id:
        raise EvaluationAccessError("Freeze manifest does not match the requested benchmark record")
    if Path(str(freeze.get("output_path"))).resolve() != output:
        raise EvaluationAccessError("Freeze manifest points to a different generated output")
    if file_sha256(output) != freeze.get("output_sha256"):
        raise EvaluationAccessError("Generated output changed after freeze")

    path = benchmark_root.resolve() / "private" / f"{split}_ground_truth.jsonl"
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("record_id") == record_id:
                return row
    raise EvaluationAccessError(f"No ground truth found for record {record_id}")
