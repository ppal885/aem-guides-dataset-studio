#!/usr/bin/env python3
"""Safely synchronize a local evidence clone while preserving developer work."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def run(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "git command failed").strip())
    return result.stdout.strip()


def optional(repo: Path, *args: str) -> str:
    try:
        return run(repo, *args)
    except RuntimeError:
        return ""


def status(repo: Path) -> str:
    return run(repo, "status", "--porcelain=v1", "--untracked-files=all")


def operation_in_progress(repo: Path) -> str:
    checks = {"merge": "MERGE_HEAD", "cherry-pick": "CHERRY_PICK_HEAD", "revert": "REVERT_HEAD"}
    for label, ref in checks.items():
        if optional(repo, "rev-parse", "-q", "--verify", ref):
            return label
    for name in ("rebase-merge", "rebase-apply"):
        git_path = optional(repo, "rev-parse", "--git-path", name)
        resolved_git_path = Path(git_path)
        if git_path and not resolved_git_path.is_absolute():
            resolved_git_path = repo / resolved_git_path
        if git_path and resolved_git_path.exists():
            return "rebase"
    return ""


def upstream_state(repo: Path) -> tuple[str, int, int]:
    upstream = optional(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if not upstream:
        return "", 0, 0
    counts = run(repo, "rev-list", "--left-right", "--count", "HEAD...@{upstream}").split()
    return upstream, int(counts[0]), int(counts[1])


def dirty_submodule(repo: Path, porcelain: str) -> str:
    paths = run(repo, "config", "-f", ".gitmodules", "--get-regexp", "path", check=False)
    submodules = [line.split(maxsplit=1)[1] for line in paths.splitlines() if len(line.split(maxsplit=1)) == 2]
    for line in porcelain.splitlines():
        changed = line[3:].split(" -> ")[-1].replace("\\", "/")
        for submodule in submodules:
            normalized = submodule.replace("\\", "/").rstrip("/")
            if changed == normalized or changed.startswith(normalized + "/"):
                return submodule
    return ""


def find_stash_ref(repo: Path, oid: str) -> str:
    for line in run(repo, "stash", "list", "--format=%gd %H").splitlines():
        ref, _, commit = line.partition(" ")
        if commit == oid:
            return ref
    return ""


def restore_after_failure(repo: Path, oid: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "stash", "apply", "--index", oid],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return "restored; safety stash retained" if result.returncode == 0 else "restore failed; safety stash retained"


def synchronize(repo_path: str, stash_dirty: bool) -> tuple[dict, int]:
    requested = Path(repo_path).expanduser().resolve()
    repo = Path(run(requested, "rev-parse", "--show-toplevel")).resolve()
    branch = optional(repo, "symbolic-ref", "--short", "HEAD")
    pre_sha = run(repo, "rev-parse", "HEAD")
    pre_status = status(repo)
    report = {
        "repository": str(repo),
        "branch": branch or "DETACHED",
        "pre_sync_sha": pre_sha,
        "pre_sync_dirty": bool(pre_status),
        "fetch": "not run",
        "pull": "not run",
        "stash_oid": "",
        "stash_ref": "",
        "restore_command": "",
    }

    operation = operation_in_progress(repo)
    if operation:
        report.update({"status": "blocked", "reason": f"Git {operation} operation is in progress"})
        return report, 2
    try:
        run(repo, "fetch", "--all", "--prune", "--tags")
        report["fetch"] = "succeeded"
    except RuntimeError as exc:
        report.update({"status": "blocked", "fetch": "failed", "reason": str(exc)})
        return report, 2

    upstream, ahead, behind = upstream_state(repo)
    report.update({"upstream": upstream, "ahead_before": ahead, "behind_before": behind})
    if not branch:
        report.update({"status": "blocked", "reason": "Detached HEAD; inspect a verified remote ref"})
        return report, 2
    if not upstream:
        report.update({"status": "blocked", "reason": "No upstream configured; inspect a verified remote ref"})
        return report, 2
    if ahead and behind:
        report.update({"status": "blocked", "reason": "Branch diverged; merge/rebase is prohibited"})
        return report, 2

    submodule = dirty_submodule(repo, pre_status)
    if submodule:
        report.update({"status": "blocked", "reason": f"Dirty submodule cannot be safely stashed: {submodule}"})
        return report, 2

    stash_oid = ""
    if pre_status:
        if not stash_dirty:
            report.update({"status": "blocked", "reason": "Dirty worktree; rerun with --stash-dirty"})
            return report, 2
        before = optional(repo, "rev-parse", "-q", "--verify", "refs/stash")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        message = f"test-plan-generation-sync:{timestamp}:{branch}:{pre_sha[:12]}"
        run(repo, "stash", "push", "--include-untracked", "-m", message)
        stash_oid = optional(repo, "rev-parse", "-q", "--verify", "refs/stash")
        if not stash_oid or stash_oid == before:
            report.update({"status": "blocked", "reason": "Developer changes were not safely stashed"})
            return report, 2
        report.update(
            {
                "stash_oid": stash_oid,
                "stash_ref": find_stash_ref(repo, stash_oid),
                "restore_command": f"git stash apply --index {stash_oid}",
            }
        )

    if behind and not ahead:
        try:
            run(repo, "pull", "--ff-only")
            report["pull"] = "fast-forwarded"
        except RuntimeError as exc:
            restoration = restore_after_failure(repo, stash_oid) if stash_oid else "not needed"
            report.update(
                {"status": "blocked", "pull": "failed", "reason": str(exc), "failure_restore": restoration}
            )
            return report, 2
    else:
        report["pull"] = "not needed"

    upstream_after, ahead_after, behind_after = upstream_state(repo)
    report.update(
        {
            "status": "synchronized",
            "post_sync_sha": run(repo, "rev-parse", "HEAD"),
            "post_sync_dirty": bool(status(repo)),
            "upstream": upstream_after,
            "ahead_after": ahead_after,
            "behind_after": behind_after,
            "evidence_ref": upstream_after if ahead_after else "HEAD",
        }
    )
    return report, 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repository")
    parser.add_argument("--stash-dirty", action="store_true")
    args = parser.parse_args()
    try:
        report, code = synchronize(args.repository, args.stash_dirty)
    except Exception as exc:
        report, code = {"status": "error", "reason": str(exc)}, 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
