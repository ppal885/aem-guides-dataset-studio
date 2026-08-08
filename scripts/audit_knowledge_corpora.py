#!/usr/bin/env python3
"""Generate an authority-aware documentation RAG knowledge-gap report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
for candidate in (PROJECT_ROOT, BACKEND_DIR):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)

from app.services.knowledge_corpus_audit_service import audit_knowledge_corpora  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--duplicate-sample-limit", type=int, default=10)
    parser.add_argument("--fail-on", choices=("none", "critical", "high"), default="none")
    args = parser.parse_args(argv or sys.argv[1:])
    report = audit_knowledge_corpora(
        duplicate_sample_limit=max(0, min(args.duplicate_sample_limit, 100))
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.output), "summary": report.get("summary", {})}, indent=2))
    else:
        print(rendered)
    if not report.get("available", True):
        return 1
    summary = report.get("summary") or {}
    if args.fail_on == "critical" and int(summary.get("critical_gap_count") or 0) > 0:
        return 2
    if args.fail_on == "high" and (
        int(summary.get("critical_gap_count") or 0) > 0
        or int(summary.get("high_gap_count") or 0) > 0
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
