"""batch_evidence_prep.py - run the repetitive per-ticket evidence-fetch step (PR ref
fetch + diff --stat against a base branch) for a whole batch of tickets in one pass,
instead of one at a time.

WHY THIS EXISTS
---------------
Processing several tickets from one PR-review batch means repeating the same three
commands per ticket: fetch the PR ref, diff --stat it against the base branch, note the
result. Doing this by hand across 7 tickets is slow and easy to get inconsistent (missed
fetch, wrong base ref). This collapses it into one command over a small JSON batch file
and prints a consolidated, per-ticket report - it does not interpret the diff or write any
plan content; it only gathers the raw evidence faster.

Read-only: fetches PR refs into local tracking branches (pr-<n>) and runs `git diff
--stat`. Never pushes, never posts anywhere, never touches Jira.

Usage:
    python batch_evidence_prep.py --batch tickets.json

tickets.json:
    [
      {"key": "<ISSUE-KEY-1>", "repo": "C:\\product-repo", "pr": 1234},
      {"key": "<ISSUE-KEY-2>", "repo": "C:\\editor-repo", "pr": 1235, "base": "origin/develop"}
    ]

"base" defaults to "origin/develop" when omitted.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _run(args, cwd):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def prep_one(entry: dict) -> dict:
    key = str(entry.get("key", "")).strip()
    repo = str(entry.get("repo", "")).strip()
    pr = entry.get("pr")
    base = str(entry.get("base") or "origin/develop").strip()
    result = {"key": key, "repo": repo, "pr": pr, "base": base}
    if not key or not repo or not pr:
        result["error"] = "entry requires 'key', 'repo', and 'pr'"
        return result
    if not Path(repo).exists():
        result["error"] = f"repo path does not exist: {repo}"
        return result
    rc, out, err = _run(["git", "fetch", "origin", f"+refs/pull/{pr}/head:pr-{pr}"], repo)
    result["fetch_ok"] = rc == 0
    result["fetch_output"] = (out + err).strip()[-1500:]
    rc2, out2, err2 = _run(["git", "diff", "--stat", f"{base}...pr-{pr}"], repo)
    result["diff_ok"] = rc2 == 0
    result["diff_stat"] = out2.strip() if rc2 == 0 else (out2 + err2).strip()
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--batch", required=True, help="path to a JSON file listing tickets to prep")
    args = p.parse_args()

    batch_path = Path(args.batch)
    if not batch_path.exists():
        print(f"ERROR: batch file not found: {batch_path}", file=sys.stderr)
        return 1
    tickets = json.loads(batch_path.read_text(encoding="utf-8"))
    if not isinstance(tickets, list) or not tickets:
        print("ERROR: batch file must be a non-empty JSON list", file=sys.stderr)
        return 1

    report = [prep_one(t) for t in tickets]
    print(json.dumps(report, indent=2))
    failures = [r["key"] for r in report if r.get("error") or not r.get("fetch_ok") or not r.get("diff_ok")]
    if failures:
        print(f"\nWARN: {len(failures)} ticket(s) had a fetch/diff problem: {', '.join(failures)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
