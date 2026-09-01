"""Generation-side access to public Benchmark V2 inputs only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ALLOWED_SPLITS = {"train", "validation", "blind"}
_SEALED_ANSWER_FIELD = "ground" + "_truth"
FORBIDDEN_PUBLIC_FIELDS = {
    "acceptance_criteria",
    "authoritative_uac",
    _SEALED_ANSWER_FIELD,
    "human_uac",
    "post_uac_evidence",
    "uac_workflow_status",
}


class GenerationInputError(RuntimeError):
    pass


def _field_names(value: Any) -> set[str]:
    if isinstance(value, dict):
        names = {str(key).casefold() for key in value}
        for child in value.values():
            names.update(_field_names(child))
        return names
    if isinstance(value, list):
        names: set[str] = set()
        for child in value:
            names.update(_field_names(child))
        return names
    return set()


def load_generation_inputs(benchmark_root: Path, split: str) -> list[dict[str, Any]]:
    """Load a sealed public snapshot for generation."""

    if split not in ALLOWED_SPLITS:
        raise GenerationInputError(f"Unknown benchmark split: {split}")
    root = benchmark_root.resolve()
    path = (root / "public" / f"{split}_inputs.jsonl").resolve()
    if root not in path.parents:
        raise GenerationInputError("Resolved input path escaped the benchmark root")
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            forbidden = _field_names(row) & FORBIDDEN_PUBLIC_FIELDS
            if forbidden:
                raise GenerationInputError(
                    f"Public generation input contains forbidden fields: {sorted(forbidden)}"
                )
            rows.append(row)
    return rows
