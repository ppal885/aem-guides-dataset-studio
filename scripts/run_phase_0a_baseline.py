#!/usr/bin/env python3
"""Run and preserve the unchanged Phase 0A TRAIN V2 production baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
BENCHMARK_V2 = ROOT / "benchmark" / "v2"
for import_root in (BACKEND, BENCHMARK_V2):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND / ".env", override=True, encoding="utf-8-sig")
except ImportError:
    pass

from app.core.schemas_test_plan_pipeline import TestPlanPipelineRequest
from app.services.test_plan_pipeline_service import run_test_plan_pipeline
from freeze import file_sha256, freeze_generated_output
from generation_access import load_generation_inputs


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def canonical_hash(payload: Any) -> str:
    data = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def count_draft_scenarios(markdown: str) -> int:
    return len(re.findall(r"^\|\s*S-\d+\s*\|", markdown or "", flags=re.MULTILINE))


def parsed_metrics(result: dict[str, Any], raw_path: Path, wall_ms: int) -> dict[str, Any]:
    validation = result.get("validation") or {}
    score = result.get("score") or {}
    coverage = result.get("coverage_matrix") or {}
    draft = str(result.get("draft_test_plan_markdown") or "")
    acceptance_criteria = result.get("acceptance_criteria") or []
    test_cases = result.get("test_cases") or []
    stable_projection = {
        "jira_key": result.get("jira_key"),
        "evidence_snapshot_id": result.get("evidence_snapshot_id"),
        "plan_fingerprint": result.get("plan_fingerprint"),
        "stages_completed": result.get("stages_completed") or [],
        "acceptance_criteria": acceptance_criteria,
        "test_cases": test_cases,
        "coverage_matrix": coverage,
        "score": score,
        "rag_packet_summary": result.get("rag_packet_summary") or {},
        "draft_test_plan_markdown": draft,
        "validation": validation,
    }
    return {
        "schema_version": "aem-guides-phase-0a-baseline-run-v2",
        "jira_key": result.get("jira_key"),
        "correlation_id": result.get("correlation_id"),
        "pipeline_elapsed_ms": result.get("elapsed_ms"),
        "wall_elapsed_ms": wall_ms,
        "stages_completed": result.get("stages_completed") or [],
        "score": {
            "overall": score.get("overall"),
            "tier": score.get("tier"),
            "human_review_required": score.get("human_review_required"),
            "routing_status": score.get("routing_status"),
            "reason_codes": score.get("reason_codes") or [],
            "warnings": score.get("warnings") or [],
            "blockers": score.get("blockers") or [],
            "breakdown": score.get("breakdown") or {},
        },
        "counts": {
            "structured_acceptance_criteria": len(acceptance_criteria),
            "structured_test_cases": len(test_cases),
            "draft_scenario_rows": count_draft_scenarios(draft),
            "validation_errors": len(validation.get("errors") or []),
            "unmapped_uacs": len(coverage.get("unmapped_uacs") or []),
            "tests_missing_evidence": len(coverage.get("tests_missing_evidence") or []),
        },
        "coverage": coverage,
        "validation": {
            "valid": bool(validation.get("valid")),
            "errors": validation.get("errors") or [],
        },
        "retrieval": result.get("rag_packet_summary") or {},
        "evidence_snapshot_id": result.get("evidence_snapshot_id"),
        "plan_fingerprint": result.get("plan_fingerprint"),
        "raw_output": {
            "path": str(raw_path.relative_to(ROOT)).replace("\\", "/"),
            "bytes": raw_path.stat().st_size,
            "sha256": file_sha256(raw_path),
        },
        "draft_sha256": hashlib.sha256(draft.encode("utf-8")).hexdigest(),
        "acceptance_criteria_sha256": canonical_hash(acceptance_criteria),
        "test_cases_sha256": canonical_hash(test_cases),
        "stable_projection_sha256": canonical_hash(stable_projection),
        "token_count": None,
        "monetary_cost": None,
        "test_case_extraction_status": "NOT_APPLICABLE",
        "representation_consistency": len(test_cases) == count_draft_scenarios(draft),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jira-key", default="GUIDES-10214")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "analysis" / "phase_0a_recovery" / "baseline_runs",
    )
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    train_inputs = load_generation_inputs(BENCHMARK_V2, "train")
    train_by_id = {
        str(row.get("jira_key") or row.get("record_id") or ""): row
        for row in train_inputs
    }
    train_ids = set(train_by_id)
    if args.jira_key not in train_ids:
        raise RuntimeError(f"TRAIN_V2_MEMBERSHIP_REQUIRED: {args.jira_key}")

    payload = {
        "jira_key": args.jira_key,
        "tenant_id": "kone",
        "evidence_k": 5,
        "include_repository_evidence": True,
        "max_repo_matches": 15,
        "skip_uac_label_gate": False,
        "full_rag": True,
        "include_evidence_graph": True,
        "graph_max_paths": 20,
        "include_uac_intelligence": True,
        "compose_draft_plan": True,
        "write_starling_artifacts": False,
        "publish_to_team_ui": False,
        "human_review_threshold": 50,
    }
    request = TestPlanPipelineRequest.model_validate(payload)
    parsed_runs: list[dict[str, Any]] = []
    for run_number in range(1, args.runs + 1):
        started = time.perf_counter()
        result = run_test_plan_pipeline(
            request,
            entry_point="benchmark_v2",
            benchmark_input=train_by_id[args.jira_key],
            benchmark_split="train",
            benchmark_source_path=str(BENCHMARK_V2 / "public" / "train_inputs.jsonl"),
        ).model_dump()
        wall_ms = int((time.perf_counter() - started) * 1000)
        raw_path = output_dir / f"run_{run_number}_raw.json"
        write_json(raw_path, result)
        freeze_generated_output(
            raw_path,
            output_dir / f"run_{run_number}_freeze.json",
            split="train",
            record_id=args.jira_key,
        )
        parsed = parsed_metrics(result, raw_path, wall_ms)
        parsed_runs.append(parsed)
        write_json(output_dir / f"run_{run_number}_parsed.json", parsed)

    stable_hashes = [item["stable_projection_sha256"] for item in parsed_runs]
    comparison = {
        "schema_version": "aem-guides-phase-0a-baseline-reproducibility-v2",
        "jira_key": args.jira_key,
        "run_count": len(parsed_runs),
        "train_v2_membership_verified_from_public_inputs": True,
        "ground_truth_loaded_during_generation_or_parsing": False,
        "stable_projection_sha256": stable_hashes,
        "deterministic_reproduction": len(set(stable_hashes)) == 1,
        "plan_fingerprints": [item["plan_fingerprint"] for item in parsed_runs],
        "evidence_snapshot_ids": [item["evidence_snapshot_id"] for item in parsed_runs],
        "runtime_ms": [item["pipeline_elapsed_ms"] for item in parsed_runs],
        "raw_output_sha256": [item["raw_output"]["sha256"] for item in parsed_runs],
    }
    write_json(output_dir / "comparison.json", comparison)
    print(json.dumps(comparison, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
