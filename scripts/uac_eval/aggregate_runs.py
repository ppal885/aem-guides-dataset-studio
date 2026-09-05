"""Aggregate saved UAC evaluation runs for the static observability dashboard.

The aggregator is intentionally a presentation adapter: it copies metrics already
reported by judge-pipeline JSON files and never recalculates evaluation results.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any


RUN_GLOB = "judge_pipeline*.json"
OUTPUT_NAME = "dashboard_data.json"
METRIC_KEYS = (
    "coverage",
    "det_precision",
    "combined",
    "halluc",
    "judge_precision",
    "holistic",
    "no_ac_section",
)
PER_METRIC_KEYS = (
    "coverage_pct",
    "hallucinations",
    "holistic",
    "precision_pct",
    "combined_pct",
    "ac_count",
    "over_decomposition",
    "redundancy_pairs",
    "verbose_ac_count",
    "ac_section_found",
    "judge_precision",
    "judge_redundant",
    "judge_over_decomposed",
)
METADATA_KEYS = ("n", "model", "seed", "vm")


class RunFormatError(ValueError):
    """Raised when a judge-pipeline run does not satisfy its minimal contract."""


def _load_run(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RunFormatError(f"Cannot read {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise RunFormatError(f"{path.name}: top-level JSON value must be an object")
    if not isinstance(value.get("agg"), dict):
        raise RunFormatError(f"{path.name}: agg must be an object")
    for mode in ("pipeline", "baseline"):
        if not isinstance(value["agg"].get(mode), dict):
            raise RunFormatError(f"{path.name}: agg.{mode} must be an object")
    if not isinstance(value.get("per"), list):
        raise RunFormatError(f"{path.name}: per must be a list")
    if any(not isinstance(item, dict) for item in value["per"]):
        raise RunFormatError(f"{path.name}: every per item must be an object")
    return value


def _normalize_metrics(value: Any) -> dict[str, Any]:
    return {key: value.get(key) for key in METRIC_KEYS}


def _normalize_per_item(item: dict[str, Any], run_name: str) -> dict[str, Any]:
    """Copy a per-ticket row and make absent reported fields explicit nulls."""
    normalized = dict(item)
    nested_modes = [mode for mode in ("pipeline", "baseline") if mode in item]
    if nested_modes:
        for mode in nested_modes:
            source = item[mode]
            if not isinstance(source, dict):
                raise RunFormatError(f"{run_name}: per.{mode} must be an object")
            metrics = dict(source)
            for key in PER_METRIC_KEYS:
                metrics.setdefault(key, None)
            normalized[mode] = metrics
    else:
        for key in PER_METRIC_KEYS:
            normalized.setdefault(key, None)
    return normalized


def _timestamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def normalize_run(path: Path, value: dict[str, Any]) -> dict[str, Any]:
    """Normalize one run without deriving or changing any reported metric."""
    agg = value["agg"]
    record: dict[str, Any] = {
        "run_id": path.name,
        "ts": _timestamp(path),
    }
    record.update({key: value.get(key) for key in METADATA_KEYS})
    record.update(
        {
            "agg_pipeline": _normalize_metrics(agg.get("pipeline")),
            "agg_baseline": _normalize_metrics(agg.get("baseline")),
            "per": [_normalize_per_item(item, path.name) for item in value["per"]],
        }
    )
    return record


def collect_runs(directory: Path) -> list[dict[str, Any]]:
    """Read qualifying judge-pipeline run files in deterministic timestamp order."""
    directory = directory.resolve()
    runs = [normalize_run(path, _load_run(path)) for path in directory.glob(RUN_GLOB)]
    return sorted(runs, key=lambda item: (item["ts"], item["run_id"]))


def write_dashboard_data(directory: Path, output_path: Path | None = None) -> int:
    """Write the dashboard payload and return the number of included runs."""
    directory = directory.resolve()
    destination = (output_path or directory / OUTPUT_NAME).resolve()
    runs = collect_runs(directory)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"runs": runs}, indent=2, ensure_ascii=False) + "\n"
    destination.write_text(payload, encoding="utf-8")
    return len(runs)


def _write_fixture(path: Path, value: dict[str, Any], timestamp: int) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")
    os.utime(path, (timestamp, timestamp))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_self_tests() -> None:
    old_per = [
        {
            "key": "CASE-OLD",
            "component": "Publishing",
            "pipeline_status": "completed",
            "pipeline": {"coverage_pct": 80, "hallucinations": 1},
            "baseline": {"coverage_pct": 40, "hallucinations": 2},
        }
    ]
    old_run = {
        "agg": {
            "pipeline": {"coverage": 80, "halluc": 1.0, "holistic": 4.0},
            "baseline": {"coverage": 40, "halluc": 2.0, "holistic": 3.0},
        },
        "per": old_per,
    }
    new_per = [
        {
            "key": "CASE-NEW",
            "component": "Editor",
            "pipeline_status": "completed",
            "pipeline": {
                "coverage_pct": 95,
                "precision_pct": 75,
                "combined_pct": 83.0,
                "ac_section_found": True,
            },
            "baseline": {
                "coverage_pct": 50,
                "precision_pct": None,
                "combined_pct": None,
                "ac_section_found": False,
            },
        }
    ]
    new_run = {
        "n": 1,
        "model": "fixture-model",
        "seed": 17,
        "vm": "fixture-vm",
        "agg": {
            "pipeline": {
                "coverage": 95,
                "det_precision": 75,
                "combined": 83.0,
                "halluc": 0.0,
                "judge_precision": 4.0,
                "holistic": 4.5,
                "no_ac_section": 0,
            },
            "baseline": {
                "coverage": 50,
                "det_precision": None,
                "combined": None,
                "halluc": 2.0,
                "judge_precision": 3.0,
                "holistic": 3.0,
                "no_ac_section": 1,
            },
        },
        "per": new_per,
    }

    with tempfile.TemporaryDirectory(prefix="aggregate-runs-test-") as tmp:
        directory = Path(tmp)
        _write_fixture(directory / "judge_pipeline_old.json", old_run, 1_700_000_000)
        _write_fixture(directory / "judge_pipeline_new.json", new_run, 1_700_000_100)
        _write_fixture(directory / "score_report_skip.json", old_run, 1_700_000_200)
        _write_fixture(directory / "train_priors.json", old_run, 1_700_000_300)
        (directory / "judge_pipeline_old.md").write_text(
            "model: must-not-be-read\nn: 99\n", encoding="utf-8"
        )

        output = directory / OUTPUT_NAME
        count = write_dashboard_data(directory, output)
        payload = json.loads(output.read_text(encoding="utf-8"))
        runs = payload["runs"]

        _require(count == 2 and len(runs) == 2, "only two judge-pipeline runs are included")
        _require(
            [run["run_id"] for run in runs]
            == ["judge_pipeline_old.json", "judge_pipeline_new.json"],
            "runs are sorted by timestamp",
        )
        _require(
            runs[0]["ts"]
            == datetime.fromtimestamp(1_700_000_000, timezone.utc).isoformat(),
            "the run timestamp comes from the file mtime in UTC",
        )
        _require(runs[0]["n"] is None and runs[0]["model"] is None, "missing metadata stays null")
        _require(runs[0]["seed"] is None and runs[0]["vm"] is None, "markdown metadata is not read")
        _require(runs[0]["agg_pipeline"]["coverage"] == 80, "reported aggregate is preserved")
        _require(runs[0]["agg_pipeline"]["det_precision"] is None, "missing aggregate precision is null")
        _require(runs[0]["agg_pipeline"]["combined"] is None, "missing aggregate combined score is null")
        _require(runs[0]["agg_pipeline"]["no_ac_section"] is None, "missing no-AC aggregate is null")
        _require(
            runs[0]["per"][0]["pipeline"]["precision_pct"] is None
            and runs[0]["per"][0]["pipeline"]["combined_pct"] is None,
            "missing per-ticket precision fields are explicit nulls",
        )
        _require(
            runs[0]["per"][0]["key"] == old_per[0]["key"],
            "per-ticket source fields are preserved",
        )
        _require(runs[1]["n"] == 1 and runs[1]["model"] == "fixture-model", "JSON metadata is copied")
        _require(runs[1]["seed"] == 17 and runs[1]["vm"] == "fixture-vm", "JSON run context is copied")
        _require(runs[1]["agg_pipeline"]["det_precision"] == 75, "reported precision is preserved")
        _require(runs[1]["agg_baseline"]["no_ac_section"] == 1, "reported no-AC count is preserved")

        malformed_path = directory / "judge_pipeline_malformed.json"
        malformed = {
            **old_run,
            "agg": {**old_run["agg"], "pipeline": []},
        }
        _write_fixture(malformed_path, malformed, 1_700_000_200)
        try:
            collect_runs(directory)
        except RunFormatError as exc:
            _require("agg.pipeline must be an object" in str(exc), "malformed aggregate error is specific")
        else:
            raise AssertionError("malformed aggregate mode must fail closed")

    print("aggregate_runs self-tests: PASS")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate judge-pipeline JSON runs for the static dashboard."
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run isolated in-memory fixture tests and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.self_test:
        run_self_tests()
        return 0

    directory = Path(__file__).resolve().parent
    count = write_dashboard_data(directory)
    print(f"Found {count} judge_pipeline run(s); wrote {directory / OUTPUT_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
