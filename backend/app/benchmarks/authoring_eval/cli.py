"""
Run the authoring benchmark from the backend root:

    python -m app.benchmarks.authoring_eval.cli
    python -m app.benchmarks.authoring_eval.cli --manifest path/to/manifest.yaml --json-out report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Screenshot + reference DITA authoring benchmark")
    default_manifest = Path(__file__).resolve().parent / "dataset" / "manifest.yaml"
    parser.add_argument("--manifest", type=Path, default=default_manifest, help="Path to manifest.yaml")
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=None,
        help="Dataset directory (defaults to manifest parent)",
    )
    parser.add_argument(
        "--no-mock-aem",
        action="store_true",
        help="Do not mock _save_to_aem (insertion cases will likely fail without real AEM env)",
    )
    parser.add_argument("--json-out", type=Path, default=None, help="Write full JSON report to this path")
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    dataset_root = args.dataset_root.resolve() if args.dataset_root else manifest_path.parent

    from app.benchmarks.authoring_eval.runner import run_manifest_sync

    report = run_manifest_sync(manifest_path, dataset_root=dataset_root, mock_aem_save=not args.no_mock_aem)

    summary = {
        "manifest": str(manifest_path),
        "aggregates": report.aggregates,
        "cases": [
            {
                "case_id": c.case_id,
                "ok": c.ok,
                "status": c.result_status,
                "dita_type": c.generated_dita_type,
                "failures": c.assertion_failures,
                "dimensions": c.dimensions.model_dump(mode="json"),
            }
            for c in report.case_reports
        ],
    }
    text = json.dumps(summary, indent=2)
    print(text)
    if args.json_out:
        args.json_out.write_text(text, encoding="utf-8")
    return 0 if report.aggregates.get("all_assertions_passed") else 1


if __name__ == "__main__":
    sys.exit(main())
