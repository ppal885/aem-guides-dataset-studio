from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from pydantic import ValidationError

from app.benchmarks.test_plan_quality.models import BenchmarkManifest
from app.benchmarks.test_plan_quality.runner import (
    evaluate_run,
    prepare_run,
    render_markdown_report,
    write_baseline,
)


PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = PACKAGE_ROOT / "dataset" / "manifest.yaml"
PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SKILL_ROOT = PROJECT_ROOT / ".codex" / "skills" / "test-plan-generation"


def _candidate_ref() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _load_manifest(path: Path) -> BenchmarkManifest:
    try:
        return BenchmarkManifest.load_yaml(path.resolve())
    except (OSError, ValidationError, ValueError) as exc:
        raise SystemExit(f"Invalid benchmark manifest: {exc}") from exc


def _prepared_candidate_ref(run_root: Path) -> str:
    try:
        payload = json.loads((run_root / "run.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    value = payload.get("candidate_ref") if isinstance(payload, dict) else ""
    return value.strip() if isinstance(value, str) else ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Golden benchmark for the AEM Guides test-plan-generation skill"
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate golden schema and coverage")
    validate.add_argument("--json", action="store_true")

    prepare = subparsers.add_parser("prepare", help="Prepare blinded case directories")
    prepare.add_argument("--run-root", type=Path, required=True)
    prepare.add_argument("--candidate-ref", default="")
    prepare.add_argument("--skill-variant", choices=("codex", "claude"), default="codex")

    score = subparsers.add_parser("score", help="Score generated benchmark artifacts")
    score.add_argument("--run-root", type=Path, required=True)
    score.add_argument("--skill-root", type=Path, default=DEFAULT_SKILL_ROOT)
    score.add_argument("--candidate-ref", default="")
    score.add_argument("--baseline", type=Path, default=None)
    score.add_argument("--json-out", type=Path, default=None)
    score.add_argument("--markdown-out", type=Path, default=None)
    score.add_argument("--write-baseline", type=Path, default=None)
    score.add_argument("--skip-skill-self-tests", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = _load_manifest(args.manifest)

    if args.command == "validate":
        payload = {
            "valid": True,
            "benchmark_id": manifest.benchmark_id,
            "schema_version": manifest.schema_version,
            "golden_status": manifest.golden_status,
            "case_count": len(manifest.cases),
            "component_coverage": manifest.component_coverage(),
            "performance_decisions": {
                decision: sum(
                    1
                    for case in manifest.cases
                    if case.expected_performance_decision == decision
                )
                for decision in ("required", "conditional", "not_required")
            },
            "manifest_fingerprint": manifest.fingerprint(),
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"VALID: {payload['case_count']} cases; coverage={payload['component_coverage']}; "
                f"goldens={payload['golden_status']}"
            )
        return 0

    if args.command == "prepare":
        candidate_ref = args.candidate_ref or _candidate_ref()
        prepare_run(
            manifest,
            run_root=args.run_root.resolve(),
            candidate_ref=candidate_ref,
            skill_variant=args.skill_variant,
        )
        print(f"Prepared blinded benchmark run: {args.run_root.resolve()}")
        return 0

    candidate_ref = (
        args.candidate_ref
        or _prepared_candidate_ref(args.run_root.resolve())
        or _candidate_ref()
    )
    report = evaluate_run(
        manifest,
        run_root=args.run_root.resolve(),
        skill_root=args.skill_root.resolve(),
        candidate_ref=candidate_ref,
        baseline_path=args.baseline.resolve() if args.baseline else None,
        run_self_tests=not args.skip_skill_self_tests,
    )
    json_text = report.model_dump_json(indent=2)
    markdown_text = render_markdown_report(report)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json_text + "\n", encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(markdown_text, encoding="utf-8")
    if args.write_baseline:
        write_baseline(report, args.write_baseline.resolve())
    print(markdown_text, end="")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
