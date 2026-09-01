#!/usr/bin/env python3
"""Wrap hash-bound, gate-passed skill artifacts in the canonical runtime contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import importlib.util
from pathlib import Path


RECEIPT_SCHEMA = "aem-guides-gate-receipt-v1"
REQUIRED_ARTIFACTS = ("plan", "manifest", "combined", "compact", "extracted_acs")


def _load(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        module_name, Path(__file__).with_name(filename)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


skill_fingerprint_mod = _load(
    "skill_bundle_fingerprint_for_adapter", "skill_bundle_fingerprint.py"
)


def _repository_root(explicit: str | None = None) -> Path:
    for direct in (explicit, os.environ.get("AEM_STUDIO_REPO")):
        if direct:
            candidate = Path(direct).expanduser().resolve()
            if (candidate / "backend" / "app").is_dir():
                return candidate
    for start in (Path(__file__).resolve(), Path.cwd().resolve()):
        for parent in (start, *start.parents):
            if (parent / "backend" / "app").is_dir():
                return parent
    raise RuntimeError(
        "Cannot locate the Dataset Studio repository containing backend/app; "
        "pass --repo-root or set AEM_STUDIO_REPO"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt_path(receipt_file: Path, raw_path: object) -> Path:
    path = Path(str(raw_path or ""))
    if not path.is_absolute():
        path = receipt_file.parent / path
    return path.resolve()


def verify_receipt(
    receipt_file: Path,
    *,
    jira_key: str,
    plan_path: Path,
    manifest_path: Path,
    skill_root: Path | None = None,
) -> dict:
    receipt_file = receipt_file.resolve()
    receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict) or receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise ValueError(f"receipt schema_version must be {RECEIPT_SCHEMA}")
    if receipt.get("passed") is not True or receipt.get("postable") is not True:
        raise ValueError("receipt must record passed=true and postable=true")
    if str(receipt.get("issue", "")).upper() != jira_key.upper():
        raise ValueError("receipt issue does not match --jira-key")

    executing_skill_root = (
        skill_root.resolve()
        if skill_root is not None
        else Path(__file__).resolve().parent.parent
    )
    skill_fingerprint_mod.verify(
        receipt.get("validator"), expected_root=executing_skill_root
    )

    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("receipt artifacts must be an object")
    resolved: dict[str, Path] = {}
    for name in REQUIRED_ARTIFACTS:
        record = artifacts.get(name)
        if not isinstance(record, dict):
            raise ValueError(f"receipt is missing artifacts.{name}")
        path = _receipt_path(receipt_file, record.get("path"))
        expected = str(record.get("sha256", "")).lower()
        if not path.is_file():
            raise ValueError(f"receipt artifact does not exist: {path}")
        if not expected or _sha256(path) != expected:
            raise ValueError(f"receipt hash mismatch for artifacts.{name}")
        resolved[name] = path

    if resolved["plan"] != plan_path.resolve():
        raise ValueError("receipt plan path does not match --plan")
    if resolved["manifest"] != manifest_path.resolve():
        raise ValueError("receipt manifest path does not match --manifest")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jira-key", required=True)
    parser.add_argument("--tenant-id", default="kone")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--claude-question-submission", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args()

    try:
        verify_receipt(
            args.receipt,
            jira_key=args.jira_key,
            plan_path=args.plan,
            manifest_path=args.manifest,
        )
        root = _repository_root(args.repo_root)
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        print(f"ERROR: canonical runtime adaptation refused: {exc}", file=sys.stderr)
        return 2

    backend = root / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from app.core.schemas_canonical_test_plan_runtime import (  # noqa: PLC0415
        ClaudeMissingQuestionSubmission,
        GenerationProfile,
        RuntimeEntryPoint,
    )
    from app.services.canonical_test_plan_runtime import (  # noqa: PLC0415
        CANONICAL_TEST_PLAN_RUNTIME,
    )

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    plan_markdown = args.plan.read_text(encoding="utf-8")
    claude_question_submission = None
    if args.claude_question_submission is not None:
        try:
            if args.claude_question_submission.stat().st_size > 2_000_000:
                raise ValueError("Claude question submission exceeds 2 MB")
            claude_question_submission = (
                ClaudeMissingQuestionSubmission.model_validate_json(
                    args.claude_question_submission.read_text(encoding="utf-8")
                )
            )
        except (OSError, ValueError) as exc:
            print(
                f"ERROR: invalid Claude question submission: {exc}",
                file=sys.stderr,
            )
            return 2
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
        gate_status="passed",
        claude_question_submission=claude_question_submission,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(args.out)
    return 0 if result.status in {"completed", "needs_human_review"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
