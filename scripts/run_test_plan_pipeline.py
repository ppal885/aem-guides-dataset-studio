#!/usr/bin/env python3
"""Run the unified AEM Guides test-plan pipeline from the CLI (HTTP or in-process)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root without installing the package.
_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from dotenv import load_dotenv

    load_dotenv(_BACKEND / ".env", override=True, encoding="utf-8-sig")
except ImportError:
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Run test-plan pipeline for a Jira key.")
    parser.add_argument("jira_key", help="e.g. GUIDES-49065")
    parser.add_argument("--tenant-id", default="kone")
    parser.add_argument("--evidence-k", type=int, default=8)
    parser.add_argument("--skip-uac-label-gate", action="store_true")
    parser.add_argument("--no-uac", action="store_true", help="Skip UAC intelligence stage")
    parser.add_argument("--no-draft", action="store_true", help="Skip draft test plan composition")
    parser.add_argument(
        "--write-starling",
        action="store_true",
        help="Write full-rag packet, pipeline JSON, and draft plan to starling repo",
    )
    parser.add_argument("--starling-path", default=None, help="Override STARLING_REPO_PATH")
    parser.add_argument("--publish-ui", action="store_true", help="Also save to Dataset Studio team UI")
    parser.add_argument("--threshold", type=int, default=50, help="Human review score threshold")
    parser.add_argument("--json", action="store_true", help="Print full JSON result")
    parser.add_argument("--http", action="store_true", help="Call backend HTTP API instead of in-process")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()

    payload = {
        "jira_key": args.jira_key,
        "tenant_id": args.tenant_id,
        "evidence_k": max(3, min(args.evidence_k, 12)),
        "include_repository_evidence": True,
        "max_repo_matches": 30,
        "skip_uac_label_gate": args.skip_uac_label_gate,
        "full_rag": True,
        "include_uac_intelligence": not args.no_uac,
        "compose_draft_plan": not args.no_draft,
        "write_starling_artifacts": args.write_starling,
        "starling_repo_path": args.starling_path,
        "publish_to_team_ui": args.publish_ui,
        "human_review_threshold": args.threshold,
    }

    if args.http:
        result = _run_http(args.base_url, payload)
    else:
        result = _run_inprocess(payload)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        from app.services.test_plan_pipeline_service import render_pipeline_result_markdown
        from app.core.schemas_test_plan_pipeline import TestPlanPipelineResult

        model = TestPlanPipelineResult.model_validate(result)
        text = render_pipeline_result_markdown(model)
        sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")

    score = (result.get("score") or {}).get("overall", 0)
    human = (result.get("score") or {}).get("human_review_required", True)
    print(f"\n--- Pipeline complete: score={score}, human_review={human} ---", file=sys.stderr)
    return 0 if not human else 2


def _run_inprocess(payload: dict) -> dict:
    from app.core.schemas_test_plan_pipeline import TestPlanPipelineRequest
    from app.services.test_plan_pipeline_service import run_test_plan_pipeline

    request = TestPlanPipelineRequest.model_validate(payload)
    result = run_test_plan_pipeline(request)
    return result.model_dump()


def _run_http(base_url: str, payload: dict) -> dict:
    import urllib.error
    import urllib.request

    url = f"{base_url.rstrip('/')}/api/v1/test-plans/pipeline"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Authorization": "Bearer dev-bypass"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {body}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
