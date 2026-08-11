"""
CLI wrapper: index a validated test plan markdown into jira_qa ChromaDB.

Usage:
    python scripts/index_test_plan.py --key GUIDES-XXXXX [--plan /path/to/plan.md] [--dry-run]

When --plan is omitted, reads output/test-plans/<KEY>-test-plan.md (the shared saved location).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_BACKEND))

from dotenv import load_dotenv

load_dotenv(_REPO_BACKEND / ".env")


def main() -> int:
    parser = argparse.ArgumentParser(description="Index a validated test plan into jira_qa ChromaDB")
    parser.add_argument("--key", required=True, help="Jira key (e.g. GUIDES-52249)")
    parser.add_argument("--plan", default=None, help="Path to plan markdown (default: output/test-plans/<KEY>-test-plan.md)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and show chunks without indexing")
    args = parser.parse_args()

    from app.services.test_plan_index_service import _parse_sections, _build_rows, index_test_plan
    from app.services.test_plan_artifact_service import TEST_PLANS_DIR, _normalize_jira_key
    import hashlib

    key = _normalize_jira_key(args.key)

    if args.plan:
        plan_path = Path(args.plan)
    else:
        plan_path = TEST_PLANS_DIR / f"{key}-test-plan.md"

    if not plan_path.exists():
        print(f"ERROR: plan file not found: {plan_path}", file=sys.stderr)
        return 1

    markdown = plan_path.read_text(encoding="utf-8")
    plan_hash = hashlib.sha256(markdown.encode()).hexdigest()
    sections = _parse_sections(markdown)

    if not sections:
        print("ERROR: no recognised sections — is this a validated 11-section plan?", file=sys.stderr)
        return 1

    rows = _build_rows(key, sections, plan_hash)
    print(f"Plan: {plan_path.name}  key={key}  sha256={plan_hash[:16]}...")
    print(f"Sections parsed: {len(sections)}  Chunks to index: {len(rows)}")
    for r in rows:
        meta = r["metadata"]
        print(f"  [{meta['chunk_type']:30s}] {meta['section_title'][:60]}  ({len(r['document'])} chars)")

    if args.dry_run:
        print("\nDry-run: no data written.")
        return 0

    result = index_test_plan(key, markdown=markdown)
    if result["indexed"]:
        print(f"\nOK: {result['chunks_indexed']} chunks indexed for {key}.")
        return 0
    else:
        print(f"\nERROR: {result.get('reason', 'unknown')}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
