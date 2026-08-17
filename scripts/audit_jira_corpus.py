#!/usr/bin/env python3
"""Generate a Jira QA Chroma corpus coverage audit as JSON."""

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

from app.services.jira_corpus_audit_service import audit_jira_corpus  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--duplicate-sample-limit", type=int, default=20)
    parser.add_argument("--top-components-per-customer", type=int, default=10)
    args = parser.parse_args(argv or sys.argv[1:])
    report = audit_jira_corpus(
        duplicate_sample_limit=max(0, min(args.duplicate_sample_limit, 100)),
        top_components_per_customer=max(1, min(args.top_components_per_customer, 50)),
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.output), "totals": report.get("totals", {})}, indent=2))
    else:
        print(rendered)
    return 0 if report.get("available", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
