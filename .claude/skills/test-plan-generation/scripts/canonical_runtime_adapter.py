#!/usr/bin/env python3
"""Wrap a gate-checked Codex/Claude plan in the canonical runtime contract.

The skill is normally installed OUTSIDE the product repo (for example under
~/.claude/skills), so resolving the repository root by walking up from this
file's own location fails. Repo-root resolution therefore tries, in order:
an explicit --repo-root, the AEM_STUDIO_REPO env var, a walk up from this file,
and a walk up from the current working directory. If none locates a repo that
contains backend/app, this sidecar recorder SOFT-SKIPS (prints a NOTE and exits
0) instead of crashing the validated pipeline - the canonical envelope is an
optional versioned sidecar, not the gate verdict.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _repository_root(explicit: str | None = None) -> Path | None:
    # 1) explicit --repo-root, then 2) AEM_STUDIO_REPO env var (must themselves hold backend/app)
    for direct in (explicit, os.environ.get("AEM_STUDIO_REPO")):
        if direct:
            cand = Path(direct).expanduser()
            if (cand / "backend" / "app").is_dir():
                return cand
    # 3) walk up from this file's location, then 4) from the current working directory
    for start in (Path(__file__).resolve(), Path.cwd().resolve()):
        for parent in (start, *start.parents):
            if (parent / "backend" / "app").is_dir():
                return parent
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jira-key", required=True)
    parser.add_argument("--tenant-id", default="kone")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--gate-status", choices=("passed", "failed"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Path to the Dataset Studio repo (the dir containing backend/app). "
        "Defaults to AEM_STUDIO_REPO, then a walk up from this file / the CWD.",
    )
    args = parser.parse_args()

    root = _repository_root(args.repo_root)
    if root is None:
        print(
            "NOTE: canonical_runtime_adapter skipped - could not locate a repository containing "
            "backend/app (pass --repo-root <dataset-studio-dir> or set AEM_STUDIO_REPO to record the "
            "canonical sidecar). The gate verdict and indexing are unaffected."
        )
        return 0

    backend = root / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    try:
        from app.core.schemas_canonical_test_plan_runtime import (  # noqa: PLC0415
            GenerationProfile,
            RuntimeEntryPoint,
        )
        from app.services.canonical_test_plan_runtime import (  # noqa: PLC0415
            CANONICAL_TEST_PLAN_RUNTIME,
        )
    except Exception as exc:  # noqa: BLE001 - sidecar must never crash the validated pipeline
        print(
            f"NOTE: canonical_runtime_adapter skipped - canonical runtime module unavailable at "
            f"{backend} ({exc}). The gate verdict and indexing are unaffected."
        )
        return 0

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    plan_markdown = args.plan.read_text(encoding="utf-8")
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key=args.jira_key,
        tenant_id=args.tenant_id,
        entry_point=RuntimeEntryPoint.CODEX_SKILL,
        generation_profile=GenerationProfile.CODEX_CANONICAL,
    )
    result = CANONICAL_TEST_PLAN_RUNTIME.adapt_codex_artifacts(
        request=request,
        manifest=manifest,
        plan_markdown=plan_markdown,
        gate_status=args.gate_status,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(args.out)
    return 0 if result.status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
