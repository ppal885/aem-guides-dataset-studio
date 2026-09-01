from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.scan_benchmark_integrity import TEXT_SUFFIXES, scan_records


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


GENERATION = _load("benchmark_v2_generation_access", ROOT / "generation_access.py")
FREEZE = _load("freeze", ROOT / "freeze.py")
EVALUATOR = _load("benchmark_v2_evaluator_access", ROOT / "evaluator_access.py")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_generation_loader_can_read_only_sealed_public_fields(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "public" / "blind_inputs.jsonl",
        [{"record_id": "GUIDES-1", "pre_uac_evidence": {"summary": "public input"}}],
    )
    rows = GENERATION.load_generation_inputs(tmp_path, "blind")
    assert rows[0]["record_id"] == "GUIDES-1"


def test_generation_loader_fails_closed_on_answer_field(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "public" / "blind_inputs.jsonl",
        [{"record_id": "GUIDES-1", "human_uac": ["must remain sealed"]}],
    )
    with pytest.raises(GENERATION.GenerationInputError):
        GENERATION.load_generation_inputs(tmp_path, "blind")


def test_evaluator_cannot_read_before_output_freeze(tmp_path: Path) -> None:
    output = tmp_path / "generated.json"
    output.write_text("{}\n", encoding="utf-8")
    _write_jsonl(
        tmp_path / "private" / "blind_ground_truth.jsonl",
        [{"record_id": "GUIDES-1", "atomic_requirements": []}],
    )
    with pytest.raises(EVALUATOR.EvaluationAccessError, match="frozen"):
        EVALUATOR.load_ground_truth_after_freeze(
            tmp_path,
            "blind",
            "GUIDES-1",
            output,
            tmp_path / "freeze.json",
        )


def test_evaluator_reads_only_after_matching_freeze(tmp_path: Path) -> None:
    output = tmp_path / "generated.json"
    output.write_text('{"plan":"frozen"}\n', encoding="utf-8")
    freeze_path = tmp_path / "freeze.json"
    _write_jsonl(
        tmp_path / "private" / "blind_ground_truth.jsonl",
        [{"record_id": "GUIDES-1", "atomic_requirements": []}],
    )
    FREEZE.freeze_generated_output(output, freeze_path, split="blind", record_id="GUIDES-1")
    result = EVALUATOR.load_ground_truth_after_freeze(
        tmp_path, "blind", "GUIDES-1", output, freeze_path
    )
    assert result["record_id"] == "GUIDES-1"


def test_output_tampering_after_freeze_is_rejected(tmp_path: Path) -> None:
    output = tmp_path / "generated.json"
    output.write_text('{"plan":"before"}\n', encoding="utf-8")
    freeze_path = tmp_path / "freeze.json"
    _write_jsonl(
        tmp_path / "private" / "blind_ground_truth.jsonl",
        [{"record_id": "GUIDES-1", "atomic_requirements": []}],
    )
    FREEZE.freeze_generated_output(output, freeze_path, split="blind", record_id="GUIDES-1")
    output.write_text('{"plan":"after"}\n', encoding="utf-8")
    with pytest.raises(EVALUATOR.EvaluationAccessError, match="changed"):
        EVALUATOR.load_ground_truth_after_freeze(
            tmp_path, "blind", "GUIDES-1", output, freeze_path
        )


def test_generation_module_has_no_evaluator_answer_path() -> None:
    source = (ROOT / "generation_access.py").read_text(encoding="utf-8").casefold()
    forbidden_path = "pri" + "vate"
    forbidden_answer = "ground" + "_truth"
    assert forbidden_path not in source
    assert forbidden_answer not in source


def test_evaluator_imports_through_package_boundary() -> None:
    module = importlib.import_module("benchmark.v2.evaluator_access")
    assert callable(module.load_ground_truth_after_freeze)


def test_scanner_covers_repo_test_formats_and_reports_real_line(tmp_path: Path) -> None:
    required_suffixes = {".feature", ".java", ".properties", ".ps1", ".sh", ".xml"}
    assert required_suffixes <= TEXT_SUFFIXES
    behavior = (
        "When the synthetic benchmark action runs with a valid fixture, the observable result "
        "must preserve every expected field and report no partial state or duplicate output."
    )
    candidate = tmp_path / "synthetic.feature"
    candidate.write_text(f"Feature: sealed scan\n\nScenario: exact text\n{behavior}\n", encoding="utf-8")
    report = scan_records(
        tmp_path,
        [
            {
                "record_id": "SAFE-1",
                "atomic_requirements": [
                    {"atomic_requirement_id": "SAFE-1:REQ-01", "behavior": behavior}
                ],
            }
        ],
        tracked_files=[candidate],
    )
    exact = [
        item for item in report["matches"] if item["match_category"] == "EXACT_REQUIREMENT_HASH"
    ]
    assert exact
    assert exact[0]["location"].endswith(":4")


def test_real_v2_split_is_disjoint_and_public_inputs_are_sealed() -> None:
    manifest_path = ROOT / "manifests" / "split_manifest.json"
    if not manifest_path.exists():
        pytest.skip("Benchmark V2 has not been built yet")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    train = set(manifest["jira_ids"]["train"])
    validation = set(manifest["jira_ids"]["validation"])
    blind = set(manifest["jira_ids"]["blind"])
    assert not train & validation
    assert not train & blind
    assert not validation & blind
    for split in ("train", "validation", "blind"):
        rows = GENERATION.load_generation_inputs(ROOT, split)
        assert len(rows) == manifest["counts"][split]


def test_real_v2_answer_fingerprints_and_duplicate_families_are_disjoint() -> None:
    records_path = ROOT / "manifests" / "authoritative_records.json"
    duplicate_path = ROOT / "manifests" / "duplicate_families.json"
    if not records_path.exists() or not duplicate_path.exists():
        pytest.skip("Benchmark V2 has not been rebuilt with duplicate-family integrity")
    records = json.loads(records_path.read_text(encoding="utf-8"))["records"]
    active = [row for row in records if row.get("assigned_split")]
    source_splits: dict[str, set[str]] = {}
    atomic_splits: dict[str, set[str]] = {}
    full_atomic_sets: dict[tuple[str, ...], set[str]] = {}
    for row in active:
        split = row["assigned_split"]
        for fingerprint in row["authoritative_source_hashes"]:
            if fingerprint:
                source_splits.setdefault(fingerprint, set()).add(split)
        for fingerprint in row["atomic_requirement_hashes"]:
            atomic_splits.setdefault(fingerprint, set()).add(split)
        full_atomic_sets.setdefault(tuple(row["atomic_requirement_hashes"]), set()).add(split)
    assert all(len(splits) == 1 for splits in source_splits.values())
    assert all(len(splits) == 1 for splits in atomic_splits.values())
    assert all(len(splits) == 1 for splits in full_atomic_sets.values())
    duplicate = json.loads(duplicate_path.read_text(encoding="utf-8"))
    assert not any(duplicate["cross_partition_fingerprint_overlaps"].values())
    assert duplicate["cross_partition_near_duplicate_pairs"] == []


def test_train_mining_does_not_import_full_corpus_candidate_definitions() -> None:
    taxonomy_path = ROOT / "train_mining" / "reasoning_pattern_taxonomy_train_v2.json"
    provenance_path = ROOT / "manifests" / "provenance.json"
    if not taxonomy_path.exists() or not provenance_path.exists():
        pytest.skip("Benchmark V2 has not been built yet")
    taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert taxonomy["historical_candidate_definitions_imported"] is False
    assert provenance["historical_pattern_candidates_loaded_by_v2_builder"] is False
    assert taxonomy["validation_ground_truth_used_for_pattern_discovery"] is False
    assert taxonomy["blind_ground_truth_used_for_pattern_discovery"] is False
    for pattern in taxonomy["patterns"]:
        assert pattern["activation_signals"]
        assert pattern["negative_activation"]
        assert pattern["reasoning_questions"]
        assert pattern["possible_outputs"]
