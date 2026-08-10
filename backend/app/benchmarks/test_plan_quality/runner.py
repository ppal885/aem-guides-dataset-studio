from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.benchmarks.test_plan_quality.models import (
    BenchmarkArtifactFingerprints,
    BenchmarkCaseInput,
    BenchmarkManifest,
    BenchmarkRunMetadata,
    CaseReport,
    EvidenceCatalog,
    RetrievalArtifact,
    SuiteReport,
)
from app.benchmarks.test_plan_quality.scoring import fingerprint_helper_script, score_case


METRIC_THRESHOLD_FIELDS = {
    "case_pass_rate": "minimum_case_pass_rate",
    "gate_pass_rate": "minimum_gate_pass_rate",
    "ac_contract_rate": "minimum_ac_contract_rate",
    "history_precision_at_5": "minimum_history_precision_at_5",
    "history_recall_at_5": "minimum_history_recall_at_5",
    "retrieval_recall_at_10": "minimum_retrieval_recall_at_10",
    "citation_accuracy": "minimum_citation_accuracy",
    "performance_decision_accuracy": "minimum_performance_decision_accuracy",
    "history_version_accuracy": "minimum_history_version_accuracy",
    "fingerprint_integrity_rate": "minimum_fingerprint_integrity_rate",
    "hallucination_free_rate": "minimum_hallucination_free_rate",
}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate_reports(reports: list[CaseReport], manifest: BenchmarkManifest) -> dict[str, Any]:
    complete = [report for report in reports if report.metrics.artifact_complete]
    coverage = {
        component: sum(
            1
            for report in complete
            if report.component == component
        )
        for component in manifest.component_coverage()
    }
    return {
        "case_count": len(reports),
        "complete_case_count": len(complete),
        "case_pass_rate": _mean([1.0 if report.passed else 0.0 for report in reports]),
        "gate_pass_rate": _mean([1.0 if report.metrics.gate_pass else 0.0 for report in reports]),
        "ac_contract_rate": _mean([1.0 if report.metrics.ac_contract else 0.0 for report in reports]),
        "history_precision_at_5": _mean(
            [report.metrics.history_precision_at_5 for report in reports]
        ),
        "history_recall_at_5": _mean(
            [report.metrics.history_recall_at_5 for report in reports]
        ),
        "retrieval_recall_at_10": _mean(
            [report.metrics.retrieval_recall_at_10 for report in reports]
        ),
        "citation_accuracy": _mean(
            [report.metrics.citation_accuracy for report in reports]
        ),
        "performance_decision_accuracy": _mean(
            [1.0 if report.metrics.performance_decision_accuracy else 0.0 for report in reports]
        ),
        "history_version_accuracy": _mean(
            [1.0 if report.metrics.history_version_accuracy else 0.0 for report in reports]
        ),
        "fingerprint_integrity_rate": _mean(
            [1.0 if report.metrics.fingerprint_integrity else 0.0 for report in reports]
        ),
        "hallucination_free_rate": _mean(
            [1.0 if report.metrics.hallucination_free else 0.0 for report in reports]
        ),
        "component_coverage": coverage,
        "failed_case_ids": [report.case_id for report in reports if not report.passed],
    }


def threshold_failures(aggregates: dict[str, Any], manifest: BenchmarkManifest) -> list[str]:
    failures: list[str] = []
    thresholds = manifest.thresholds
    if aggregates["complete_case_count"] != thresholds.required_case_count:
        failures.append(
            f"complete_case_count={aggregates['complete_case_count']} is below required "
            f"{thresholds.required_case_count}"
        )
    for component, count in aggregates["component_coverage"].items():
        if count < thresholds.minimum_cases_per_component:
            failures.append(
                f"component {component} has {count} completed cases; "
                f"requires {thresholds.minimum_cases_per_component}"
            )
    for metric, threshold_field in METRIC_THRESHOLD_FIELDS.items():
        actual = float(aggregates.get(metric, 0.0))
        expected = float(getattr(thresholds, threshold_field))
        if actual + 1e-12 < expected:
            failures.append(f"{metric}={actual:.4f} is below required {expected:.4f}")
    return failures


def compare_baseline(
    aggregates: dict[str, Any],
    baseline_path: Path | None,
    manifest: BenchmarkManifest,
) -> list[str]:
    if baseline_path is None:
        return []
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"baseline could not be read: {exc}"]
    if not isinstance(baseline, dict):
        return ["baseline root must be a JSON object"]
    if baseline.get("schema_version") != "aem-guides-test-plan-benchmark-baseline-v1":
        return ["baseline schema_version is missing or unsupported"]
    if baseline.get("benchmark_id") != manifest.benchmark_id:
        return ["baseline benchmark_id does not match the scorer manifest"]
    if baseline.get("manifest_fingerprint") != manifest.fingerprint():
        return ["baseline manifest fingerprint does not match the scorer manifest"]
    expected = baseline.get("aggregates")
    if not isinstance(expected, dict):
        return ["baseline is missing aggregates"]
    failures: list[str] = []
    for metric in METRIC_THRESHOLD_FIELDS:
        prior = expected.get(metric)
        current = aggregates.get(metric)
        if not isinstance(prior, (int, float)) or not isinstance(current, (int, float)):
            failures.append(f"baseline comparison is missing numeric metric {metric}")
        elif current + 1e-12 < prior:
            failures.append(f"{metric} regressed from {prior:.4f} to {current:.4f}")
    return failures


def run_skill_self_tests(skill_root: Path) -> tuple[bool, str]:
    script = skill_root / "scripts" / "test_skill_scripts.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=skill_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = (result.stdout or "") + (result.stderr or "")
    passed = result.returncode == 0 and "ALL SELF-TESTS PASSED" in output
    return passed, output.strip()


def validate_run_integrity(
    manifest: BenchmarkManifest,
    *,
    run_root: Path,
    candidate_ref: str,
) -> list[str]:
    failures: list[str] = []
    run_path = run_root / "run.json"
    try:
        metadata = BenchmarkRunMetadata.model_validate_json(
            run_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, ValueError) as exc:
        return [f"run metadata is missing or invalid: {exc}"]
    if metadata.benchmark_id != manifest.benchmark_id:
        failures.append("run metadata benchmark_id does not match the scorer manifest")
    if metadata.manifest_fingerprint != manifest.fingerprint():
        failures.append("run metadata manifest fingerprint does not match the scorer manifest")
    if candidate_ref and metadata.candidate_ref and candidate_ref != metadata.candidate_ref:
        failures.append(
            f"candidate_ref mismatch: run={metadata.candidate_ref}, score={candidate_ref}"
        )

    helper_path = run_root / "compute-fingerprints.py"
    try:
        helper_text = helper_path.read_text(encoding="utf-8")
    except OSError as exc:
        failures.append(f"fingerprint helper is missing or unreadable: {exc}")
    else:
        if helper_text != fingerprint_helper_script():
            failures.append("compute-fingerprints.py was modified")

    shared_files = [
        run_path,
        run_root / "artifact-schemas.json",
        run_root / "candidate-contract.md",
        helper_path,
    ]
    for case in manifest.cases:
        case_dir = run_root / case.id
        input_path = case_dir / "case-input.json"
        task_path = case_dir / "task.md"
        try:
            actual = BenchmarkCaseInput.model_validate_json(
                input_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            failures.append(f"{case.id}: case-input.json is missing or invalid: {exc}")
            continue
        expected = BenchmarkCaseInput(
            schema_version="aem-guides-test-plan-benchmark-case-input-v1",
            case_id=case.id,
            jira_key=case.jira_key,
            component=case.component,
            customer=case.customer,
            query=case.query,
            lifecycle_stage=case.lifecycle_stage,
        )
        if actual.model_dump(mode="json") != expected.model_dump(mode="json"):
            failures.append(f"{case.id}: blinded case input was modified")
        if not task_path.is_file():
            failures.append(f"{case.id}: task.md is missing")
            continue
        public_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [*shared_files, input_path, task_path]
            if path.is_file()
        )
        leaked = [key for key in case.expected_history_keys if key in public_text]
        if leaked:
            failures.append(
                f"{case.id}: blinded candidate files disclose expected Jira key(s): "
                + ", ".join(leaked)
            )
    return failures


def evaluate_run(
    manifest: BenchmarkManifest,
    *,
    run_root: Path,
    skill_root: Path,
    candidate_ref: str = "",
    baseline_path: Path | None = None,
    run_self_tests: bool = True,
) -> SuiteReport:
    integrity_failures = validate_run_integrity(
        manifest,
        run_root=run_root,
        candidate_ref=candidate_ref,
    )
    reports = [
        score_case(case, case_dir=run_root / case.id, skill_root=skill_root)
        for case in manifest.cases
    ]
    aggregates = aggregate_reports(reports, manifest)
    thresholds = [*integrity_failures, *threshold_failures(aggregates, manifest)]
    baseline_failures = compare_baseline(aggregates, baseline_path, manifest)
    self_tests_passed = True
    if run_self_tests:
        self_tests_passed, self_test_output = run_skill_self_tests(skill_root)
        aggregates["skill_self_test_tail"] = "\n".join(self_test_output.splitlines()[-5:])
        if not self_tests_passed:
            thresholds.append("skill self-tests did not report ALL SELF-TESTS PASSED")
    release_eligible = manifest.golden_status == "approved"
    if not release_eligible:
        thresholds.append(
            "golden_status is seeded; an accountable QE reviewer must approve the manifest "
            "before it can establish or gate a production baseline"
        )
    passed = not thresholds and not baseline_failures and self_tests_passed
    return SuiteReport(
        benchmark_id=manifest.benchmark_id,
        manifest_fingerprint=manifest.fingerprint(),
        golden_status=manifest.golden_status,
        release_eligible=release_eligible,
        candidate_ref=candidate_ref,
        run_root=str(run_root.resolve()),
        case_reports=reports,
        aggregates=aggregates,
        threshold_failures=thresholds,
        baseline_failures=baseline_failures,
        skill_self_tests_passed=self_tests_passed,
        passed=passed,
    )


def prepare_run(
    manifest: BenchmarkManifest,
    *,
    run_root: Path,
    candidate_ref: str,
    skill_variant: str,
) -> None:
    if run_root.exists() and any(run_root.iterdir()):
        raise FileExistsError(f"benchmark run directory is not empty: {run_root}")
    run_root.mkdir(parents=True, exist_ok=True)
    metadata = {
        "schema_version": "aem-guides-test-plan-benchmark-run-v1",
        "benchmark_id": manifest.benchmark_id,
        "manifest_fingerprint": manifest.fingerprint(),
        "candidate_ref": candidate_ref,
        "skill_variant": skill_variant,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "goldens_disclosed_to_candidate": False,
    }
    (run_root / "run.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    schemas = {
        "retrieval.json": RetrievalArtifact.model_json_schema(),
        "evidence-catalog.json": EvidenceCatalog.model_json_schema(),
        "fingerprints.json": BenchmarkArtifactFingerprints.model_json_schema(),
    }
    (run_root / "artifact-schemas.json").write_text(
        json.dumps(schemas, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (run_root / "candidate-contract.md").write_text(
        _candidate_contract_text(),
        encoding="utf-8",
    )
    (run_root / "compute-fingerprints.py").write_text(
        fingerprint_helper_script(),
        encoding="utf-8",
    )
    for case in manifest.cases:
        case_dir = run_root / case.id
        case_dir.mkdir()
        public_input = {
            "schema_version": "aem-guides-test-plan-benchmark-case-input-v1",
            "case_id": case.id,
            "jira_key": case.jira_key,
            "component": case.component,
            "customer": case.customer,
            "query": case.query,
            "lifecycle_stage": case.lifecycle_stage,
        }
        (case_dir / "case-input.json").write_text(
            json.dumps(public_input, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (case_dir / "task.md").write_text(_task_text(public_input), encoding="utf-8")


def _candidate_contract_text() -> str:
    return (
        "# Test Plan Golden Benchmark Candidate Contract\n\n"
        "- Treat every case independently and use the selected test-plan-generation skill.\n"
        "- Do not inspect the scorer manifest, expected Jira matches, expected performance decisions, "
        "baselines, reports, or another candidate's artifacts.\n"
        "- Record successful indexed-history retrieval from `search_jira_history`; do not fabricate "
        "results when the tool is degraded.\n"
        "- Every returned historical Jira must pass same-mechanism qualification. Record release/version "
        "applicability, but never use release or version as a hard retrieval filter.\n"
        "- Cite only sources directly retrieved or inspected. Local code, attachment, and log sources "
        "require `sha256:<hex>` in `source_hash`.\n"
        "- Use `artifact-schemas.json` for `retrieval.json`, `evidence-catalog.json`, and "
        "`fingerprints.json`.\n"
        "- A graph path is traceability only and cannot be an AC's underlying source.\n"
        "- After all case artifacts are final, run `python ../compute-fingerprints.py .`; do not edit "
        "the helper or `fingerprints.json`.\n"
        "- Run the skill's mandatory gate before declaring a case complete.\n"
    )


def _task_text(case: dict[str, Any]) -> str:
    customer = case.get("customer") or "Unavailable from benchmark input"
    return (
        "Use the test-plan-generation skill to generate an evidence-backed plan.\n\n"
        f"- Jira: {case['jira_key']}\n"
        f"- Canonical component: {case['component']}\n"
        f"- Customer context: {customer}\n"
        f"- Lifecycle: {case['lifecycle_stage']}\n"
        f"- Mechanism-focused request: {case['query']}\n\n"
        "Do not inspect the benchmark manifest, expected history keys, expected performance decision, "
        "prior benchmark reports, or another candidate's artifacts. Collect evidence normally and write "
        "exactly these files in this case directory:\n\n"
        "- `full-plan.md`: the eleven-section validated body.\n"
        "- `combined-plan.md`: the body plus any required automation-evidence appendix.\n"
        "- `evidence-manifest.json`: the manifest consumed by the skill's mandatory gate.\n"
        "- `retrieval.json`: schema `aem-guides-test-plan-retrieval-v2`, recording both same_customer "
        "and cross_customer `search_jira_history` queries, same-mechanism qualification, soft "
        "release/version applicability, and ranked Jira keys.\n"
        "- `evidence-catalog.json`: schema `aem-guides-test-plan-evidence-catalog-v1`, listing every Jira, "
        "URL, DITA source, code path, attachment, Figma node, or log allowed to support an AC.\n\n"
        "- `fingerprints.json`: generate only after all other artifacts are final by running "
        "`python ../compute-fingerprints.py .`.\n\n"
        "Follow `../candidate-contract.md` and `../artifact-schemas.json`. Run the skill gate and "
        "fingerprint helper before finishing. Do not copy or infer golden answers.\n"
    )


def render_markdown_report(report: SuiteReport) -> str:
    status = "PASS" if report.passed else "FAIL"
    lines = [
        f"# Test Plan Golden Benchmark - {status}",
        "",
        f"- Benchmark: `{report.benchmark_id}`",
        f"- Candidate: `{report.candidate_ref or 'unrecorded'}`",
        f"- Golden status: `{report.golden_status}`",
        f"- Release eligible: `{str(report.release_eligible).lower()}`",
        f"- Complete cases: `{report.aggregates.get('complete_case_count', 0)}/{report.aggregates.get('case_count', 0)}`",
        f"- Case pass rate: `{report.aggregates.get('case_pass_rate', 0):.4f}`",
        f"- Gate pass rate: `{report.aggregates.get('gate_pass_rate', 0):.4f}`",
        f"- Historical precision@5: `{report.aggregates.get('history_precision_at_5', 0):.4f}`",
        f"- Historical recall@5: `{report.aggregates.get('history_recall_at_5', 0):.4f}`",
        f"- Retrieval recall@10: `{report.aggregates.get('retrieval_recall_at_10', 0):.4f}`",
        f"- Citation accuracy: `{report.aggregates.get('citation_accuracy', 0):.4f}`",
        f"- AC contract rate: `{report.aggregates.get('ac_contract_rate', 0):.4f}`",
        f"- Performance decision accuracy: `{report.aggregates.get('performance_decision_accuracy', 0):.4f}`",
        f"- Historical version accuracy: `{report.aggregates.get('history_version_accuracy', 0):.4f}`",
        f"- Fingerprint integrity rate: `{report.aggregates.get('fingerprint_integrity_rate', 0):.4f}`",
        f"- Hallucination-free rate: `{report.aggregates.get('hallucination_free_rate', 0):.4f}`",
        "",
        "## Findings",
        "",
    ]
    findings = [*report.threshold_failures, *report.baseline_failures]
    lines.extend([f"- {finding}" for finding in findings] or ["- No suite-level failures."])
    lines.extend(["", "## Cases", ""])
    for case in report.case_reports:
        case_status = "PASS" if case.passed else "FAIL"
        lines.append(f"- `{case.case_id}` / `{case.jira_key}` / `{case.component}`: {case_status}")
        for failure in case.failures:
            lines.append(f"  - {failure}")
    return "\n".join(lines).rstrip() + "\n"


def write_baseline(report: SuiteReport, path: Path) -> None:
    if not report.passed or not report.release_eligible:
        raise ValueError("a baseline may be written only from a passing, approved-golden run")
    payload = {
        "schema_version": "aem-guides-test-plan-benchmark-baseline-v1",
        "benchmark_id": report.benchmark_id,
        "manifest_fingerprint": report.manifest_fingerprint,
        "candidate_ref": report.candidate_ref,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "aggregates": {
            key: report.aggregates[key]
            for key in METRIC_THRESHOLD_FIELDS
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
