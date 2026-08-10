from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.benchmarks.test_plan_quality import runner, scoring
from app.benchmarks.test_plan_quality.models import (
    BenchmarkManifest,
    CaseMetrics,
    CaseReport,
    EvidenceCatalog,
    GoldenCase,
    RetrievalArtifact,
)


DATASET = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "benchmarks"
    / "test_plan_quality"
    / "dataset"
    / "manifest.yaml"
)


def _manifest() -> BenchmarkManifest:
    return BenchmarkManifest.load_yaml(DATASET)


def _case() -> GoldenCase:
    return GoldenCase(
        id="editor-toolbar-history",
        jira_key="GUIDES-100",
        component="Editor",
        customer="Example Customer",
        query="Toolbar action fails in the new editor.",
        expected_history_keys=["GUIDES-90"],
        expected_performance_decision="not_required",
        required_query_terms=["toolbar"],
        source_basis=[
            "Explicit duplicate relationship in sanitized Jira evidence.",
            "Functional toolbar failure has no performance-risk signal.",
        ],
    )


def _write_case_artifacts(
    case_dir: Path,
    *,
    selected_key: str = "GUIDES-90",
    retrieved_key: str = "GUIDES-90",
    performance_decision: str = "not_required",
    trust_tier: str = "authoritative",
    version_applicability: str = "unknown",
) -> None:
    case_dir.mkdir(parents=True)
    plan = f"""**Acceptance Criteria**
- AC-01 [Confirmed]: (Basic) Given a configured toolbar | When the action is selected | Then the action completes. | Evidence: JIRA:GUIDES-100.

**Known Jira Bugs / Past Similar Tickets**
- {selected_key} - Same toolbar action mechanism.
"""
    (case_dir / "full-plan.md").write_text(plan, encoding="utf-8")
    (case_dir / "combined-plan.md").write_text(plan, encoding="utf-8")
    (case_dir / "evidence-manifest.json").write_text(
        json.dumps({"performance_assessment": {"decision": performance_decision}}),
        encoding="utf-8",
    )
    retrieval = {
        "schema_version": "aem-guides-test-plan-retrieval-v2",
        "tool": "search_jira_history",
        "indexed_history_run": True,
        "issue": "GUIDES-100",
        "queries": [
            {
                "scope": "same_customer",
                "query": "toolbar action mechanism",
                "component": "Editor",
                "customer": "Example Customer",
                "hard_version_filter_applied": False,
                "results": [
                    {
                        "jira_key": retrieved_key,
                        "rank": 1,
                        "source_ref": retrieved_key,
                        "mechanism_qualified": True,
                        "version_applicability": version_applicability,
                    }
                ],
            },
            {
                "scope": "cross_customer",
                "query": "toolbar action mechanism",
                "component": "Editor",
                "customer": "",
                "hard_version_filter_applied": False,
                "results": [],
            },
        ],
    }
    (case_dir / "retrieval.json").write_text(json.dumps(retrieval), encoding="utf-8")
    catalog = {
        "schema_version": "aem-guides-test-plan-evidence-catalog-v1",
        "issue": "GUIDES-100",
        "sources": [
            {
                "source_id": "JIRA:GUIDES-100",
                "source_type": "jira",
                "source_ref": "GUIDES-100",
                "trust_tier": trust_tier,
                "verification_method": "jira_mcp",
                "source_hash": "",
            }
        ],
    }
    (case_dir / "evidence-catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    scoring.write_benchmark_fingerprints(case_dir, case_dir.name)


def _fake_skill_module(_skill_root: Path, filename: str, _module_name: str):
    if filename == "ac_contract.py":
        def parse_ac_line(line: str):
            evidence = line.split("Evidence:", 1)[1].strip().rstrip(".")
            return {"id": "AC-01", "evidence": evidence}

        return SimpleNamespace(
            acceptance_lines=lambda text: [
                line for line in text.splitlines() if line.startswith("- AC-")
            ],
            parse_ac_line=parse_ac_line,
            validate_ac_sequence=lambda criteria: [] if len(criteria) == 1 else ["bad sequence"],
        )
    return SimpleNamespace(run=lambda *_args: ([], []))


def _passing_report(case: GoldenCase) -> CaseReport:
    return CaseReport(
        case_id=case.id,
        jira_key=case.jira_key,
        component=case.component,
        passed=True,
        metrics=CaseMetrics(
            artifact_complete=True,
            gate_pass=True,
            ac_contract=True,
            history_precision_at_5=1.0,
            history_recall_at_5=1.0,
            retrieval_recall_at_10=1.0,
            citation_accuracy=1.0,
            performance_decision_accuracy=True,
            history_version_accuracy=True,
            fingerprint_integrity=True,
            hallucination_free=True,
        ),
    )


def test_default_manifest_has_balanced_component_and_performance_coverage():
    manifest = _manifest()

    assert len(manifest.cases) == 18
    assert manifest.component_coverage() == {
        "Editor": 3,
        "Authoring": 3,
        "Publishing": 3,
        "Platform": 3,
        "Schematron": 3,
        "Integration": 3,
    }
    assert {case.expected_performance_decision for case in manifest.cases} == {
        "required",
        "conditional",
        "not_required",
    }
    assert manifest.golden_status == "seeded"


def test_prepare_run_is_blinded_and_schema_driven(tmp_path: Path):
    manifest = _manifest()
    run_root = tmp_path / "run"

    runner.prepare_run(
        manifest,
        run_root=run_root,
        candidate_ref="candidate-sha",
        skill_variant="codex",
    )

    assert runner.validate_run_integrity(
        manifest,
        run_root=run_root,
        candidate_ref="candidate-sha",
    ) == []
    schemas = json.loads((run_root / "artifact-schemas.json").read_text(encoding="utf-8"))
    retrieval_required = schemas["retrieval.json"]["required"]
    source_required = schemas["evidence-catalog.json"]["$defs"]["EvidenceSource"]["required"]
    assert {"tool", "indexed_history_run", "issue", "queries"}.issubset(retrieval_required)
    assert {"verification_method", "source_ref", "trust_tier"}.issubset(source_required)
    assert "fingerprints.json" in schemas
    assert (run_root / "compute-fingerprints.py").read_text(
        encoding="utf-8"
    ) == scoring.fingerprint_helper_script()
    for case in manifest.cases:
        public_text = (
            (run_root / case.id / "case-input.json").read_text(encoding="utf-8")
            + (run_root / case.id / "task.md").read_text(encoding="utf-8")
        )
        assert all(key not in public_text for key in case.expected_history_keys)


def test_run_integrity_rejects_modified_input_and_leaked_golden(tmp_path: Path):
    manifest = _manifest()
    run_root = tmp_path / "run"
    runner.prepare_run(
        manifest,
        run_root=run_root,
        candidate_ref="candidate-sha",
        skill_variant="claude",
    )
    case = manifest.cases[0]
    input_path = run_root / case.id / "case-input.json"
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    payload["query"] = "tampered"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    task_path = run_root / case.id / "task.md"
    task_path.write_text(
        task_path.read_text(encoding="utf-8") + f"\nExpected: {case.expected_history_keys[0]}\n",
        encoding="utf-8",
    )
    (run_root / "compute-fingerprints.py").write_text("# modified\n", encoding="utf-8")

    failures = runner.validate_run_integrity(
        manifest,
        run_root=run_root,
        candidate_ref="candidate-sha",
    )

    assert any("blinded case input was modified" in failure for failure in failures)
    assert any("disclose expected Jira" in failure for failure in failures)
    assert any("compute-fingerprints.py was modified" in failure for failure in failures)


def test_score_case_accepts_grounded_deterministic_output(tmp_path: Path, monkeypatch):
    case = _case()
    case_dir = tmp_path / case.id
    _write_case_artifacts(case_dir)
    monkeypatch.setattr(scoring, "load_skill_module", _fake_skill_module)

    report = scoring.score_case(case, case_dir=case_dir, skill_root=tmp_path / "skill")

    assert report.passed is True
    assert report.metrics.model_dump() == {
        "artifact_complete": True,
        "gate_pass": True,
        "ac_contract": True,
        "history_precision_at_5": 1.0,
        "history_recall_at_5": 1.0,
        "retrieval_recall_at_10": 1.0,
        "citation_accuracy": 1.0,
        "performance_decision_accuracy": True,
        "history_version_accuracy": True,
        "fingerprint_integrity": True,
        "hallucination_free": True,
    }


def test_acceptance_ids_are_never_parsed_as_past_jira():
    plan = """**Known Jira Bugs / Past Similar Tickets**
- AC-01 - This is an acceptance identifier, not a Jira issue.
"""

    assert scoring.selected_history_keys(plan, "GUIDES-100") == []


def test_score_case_rejects_unretrieved_history_untrusted_citation_and_perf_mismatch(
    tmp_path: Path,
    monkeypatch,
):
    case = _case()
    case_dir = tmp_path / case.id
    _write_case_artifacts(
        case_dir,
        selected_key="GUIDES-999",
        retrieved_key="GUIDES-80",
        performance_decision="required",
        trust_tier="candidate",
    )
    monkeypatch.setattr(scoring, "load_skill_module", _fake_skill_module)

    report = scoring.score_case(case, case_dir=case_dir, skill_root=tmp_path / "skill")

    assert report.passed is False
    assert report.metrics.hallucination_free is False
    assert report.metrics.citation_accuracy == 0.0
    assert report.metrics.performance_decision_accuracy is False
    assert report.unverified_jira_keys == ["GUIDES-999"]
    assert report.unverified_evidence_sources == ["JIRA:GUIDES-100"]
    assert any("not present in recorded retrieval" in failure for failure in report.failures)


def test_score_case_rejects_wrong_history_version_classification(
    tmp_path: Path,
    monkeypatch,
):
    case = _case()
    case_dir = tmp_path / case.id
    _write_case_artifacts(case_dir, version_applicability="same_release")
    monkeypatch.setattr(scoring, "load_skill_module", _fake_skill_module)

    report = scoring.score_case(case, case_dir=case_dir, skill_root=tmp_path / "skill")

    assert report.passed is False
    assert report.metrics.history_version_accuracy is False
    assert report.actual_history_versions == {"GUIDES-90": "same_release"}
    assert any("release/version applicability mismatch" in failure for failure in report.failures)


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        (("queries", 0, "results", 0, "mechanism_qualified"), False),
        (("queries", 0, "hard_version_filter_applied"), True),
    ],
)
def test_retrieval_contract_rejects_unqualified_or_hard_filtered_history(
    tmp_path: Path,
    field_path: tuple[object, ...],
    value: object,
):
    case_dir = tmp_path / "editor-toolbar-history"
    _write_case_artifacts(case_dir)
    payload = json.loads((case_dir / "retrieval.json").read_text(encoding="utf-8"))
    target = payload
    for part in field_path[:-1]:
        target = target[part]
    target[field_path[-1]] = value

    with pytest.raises(ValueError):
        RetrievalArtifact.model_validate(payload)


def test_score_case_rejects_plan_tampering_after_fingerprinting(
    tmp_path: Path,
    monkeypatch,
):
    case = _case()
    case_dir = tmp_path / case.id
    _write_case_artifacts(case_dir)
    plan_path = case_dir / "full-plan.md"
    plan_path.write_text(plan_path.read_text(encoding="utf-8") + "\nTampered.\n", encoding="utf-8")
    monkeypatch.setattr(scoring, "load_skill_module", _fake_skill_module)

    report = scoring.score_case(case, case_dir=case_dir, skill_root=tmp_path / "skill")

    assert report.passed is False
    assert report.metrics.fingerprint_integrity is False
    assert any("fingerprints.json does not match" in failure for failure in report.failures)


def test_generated_fingerprint_helper_matches_scorer(tmp_path: Path):
    case_dir = tmp_path / "editor-toolbar-history"
    _write_case_artifacts(case_dir)
    (case_dir / "fingerprints.json").unlink()
    helper_path = tmp_path / "compute-fingerprints.py"
    helper_path.write_text(scoring.fingerprint_helper_script(), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(helper_path), str(case_dir)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    submitted = json.loads((case_dir / "fingerprints.json").read_text(encoding="utf-8"))
    expected = scoring.compute_benchmark_fingerprints(
        case_dir,
        case_dir.name,
    ).model_dump(mode="json")
    assert submitted == expected


def test_seeded_goldens_block_release_and_approved_goldens_allow_baseline(
    tmp_path: Path,
    monkeypatch,
):
    seeded = _manifest()
    seeded_run = tmp_path / "seeded"
    runner.prepare_run(
        seeded,
        run_root=seeded_run,
        candidate_ref="candidate-sha",
        skill_variant="codex",
    )
    monkeypatch.setattr(runner, "score_case", lambda case, **_kwargs: _passing_report(case))

    seeded_report = runner.evaluate_run(
        seeded,
        run_root=seeded_run,
        skill_root=tmp_path / "skill",
        candidate_ref="candidate-sha",
        run_self_tests=False,
    )

    assert seeded_report.passed is False
    assert seeded_report.release_eligible is False
    assert any("golden_status is seeded" in failure for failure in seeded_report.threshold_failures)
    with pytest.raises(ValueError, match="approved-golden"):
        runner.write_baseline(seeded_report, tmp_path / "blocked-baseline.json")

    approved_payload = seeded.model_dump(mode="json")
    approved_payload.update(
        golden_status="approved",
        approved_by="Principal QE Reviewer",
        approved_at="2026-08-09T00:00:00Z",
    )
    with pytest.raises(ValueError, match="per-case approval"):
        BenchmarkManifest.model_validate(approved_payload)
    for case_payload in approved_payload["cases"]:
        case_payload["review"] = {
            "status": "approved",
            "reviewed_by": "Principal QE Reviewer",
            "reviewed_at": "2026-08-09T00:00:00Z",
        }
    approved = BenchmarkManifest.model_validate(approved_payload)
    approved_run = tmp_path / "approved"
    runner.prepare_run(
        approved,
        run_root=approved_run,
        candidate_ref="candidate-sha",
        skill_variant="codex",
    )
    approved_report = runner.evaluate_run(
        approved,
        run_root=approved_run,
        skill_root=tmp_path / "skill",
        candidate_ref="candidate-sha",
        run_self_tests=False,
    )
    baseline_path = tmp_path / "baseline.json"
    runner.write_baseline(approved_report, baseline_path)

    assert approved_report.passed is True
    assert approved_report.release_eligible is True
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert baseline["manifest_fingerprint"] == approved.fingerprint()
    assert baseline["aggregates"]["hallucination_free_rate"] == 1.0


def test_score_case_reports_missing_skill_contract_without_crashing(tmp_path: Path):
    case = _case()
    case_dir = tmp_path / case.id
    _write_case_artifacts(case_dir)

    report = scoring.score_case(
        case,
        case_dir=case_dir,
        skill_root=tmp_path / "missing-skill",
    )

    assert report.passed is False
    assert report.metrics.ac_contract is False
    assert report.metrics.gate_pass is False
    assert any("could not execute the AC contract" in failure for failure in report.failures)
    assert any("could not execute skill gates" in failure for failure in report.failures)


def test_local_evidence_with_spaces_requires_matching_hash(tmp_path: Path):
    source_path = tmp_path / "repo with spaces" / "ToolbarTest.java"
    source_path.parent.mkdir()
    source_path.write_text("class ToolbarTest {}\n", encoding="utf-8")
    catalog = EvidenceCatalog.model_validate(
        {
            "issue": "GUIDES-100",
            "sources": [
                {
                    "source_id": "CODE:toolbar-test",
                    "source_type": "code",
                    "source_ref": str(source_path),
                    "trust_tier": "authoritative",
                    "verification_method": "repo_read",
                    "source_hash": scoring._sha256(source_path),
                }
            ],
        }
    )

    tokens, invalid = scoring._verified_catalog_tokens(catalog, {"GUIDES-100"})

    assert invalid == []
    assert "CODE:toolbar-test" in tokens
    catalog.sources[0].source_hash = "sha256:" + ("0" * 64)
    _tokens, invalid = scoring._verified_catalog_tokens(catalog, {"GUIDES-100"})
    assert invalid == ["CODE:toolbar-test"]
