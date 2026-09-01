"""PRSupersessionCheck - when a ticket's history references more than one PR/branch,
force the plan to declare which one is authoritative and why, instead of silently
grounding on whichever PR was noticed first.

WHY THIS EXISTS
---------------
A ticket can accumulate more than one PR over its lifetime - a narrower first attempt
later superseded by a broader fix, two parallel PRs for different platforms, or an
abandoned branch left linked in Jira dev-panel metadata. Grounding a plan on the first PR
found (instead of checking whether a later one supersedes it) produces Acceptance Criteria
for a fix that will never actually ship. This module enforces that when more than one
PR/branch is in play, the plan states which is authoritative and records what the
diff comparison showed - never silently picks one.

It hardcodes no repo, ticket, or PR number - stdlib only for the validator. The CLI mode
(`python pr_supersession_check.py <repo> <base_ref> <pr_a> <pr_b>`) automates the tedious
part (fetch both refs, diff them against the base and against each other) so the
comparison itself does not have to be redone by hand for every ticket.
"""

from __future__ import annotations

import json
import subprocess
import sys

PR_STATUSES = ("AUTHORITATIVE", "SUPERSEDED", "PARALLEL_UNRELATED", "UNRESOLVED")


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("pr_references"), list)


def validate_pr_references(value, *, open_question_ids=None):
    """Validate a manifest `pr_references` list. Returns problem strings.

    Omitting the field, or a single-PR list, is always valid - there is nothing to
    reconcile until a ticket has more than one PR/branch in play.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        return ["pr_references must be a list"]
    problems = []
    open_ids = None if open_question_ids is None else set(open_question_ids)
    for i, item in enumerate(value):
        if not isinstance(item, dict):
            problems.append(f"pr_references[{i}] must be an object")
            continue
        ref = str(item.get("pr_ref", "")).strip()
        if not ref:
            problems.append(f"pr_references[{i}] is missing 'pr_ref' (e.g. '#8098' or 'PR 8135')")
        status = str(item.get("status", "")).strip()
        if status not in PR_STATUSES:
            problems.append(f"pr_references[{i}].status must be one of: {', '.join(PR_STATUSES)}")
        if status == "UNRESOLVED":
            oq = str(item.get("open_question_ref", "")).strip()
            if not oq:
                problems.append(f"pr_references[{i}] is UNRESOLVED but has no open_question_ref")
            elif open_ids is not None and oq not in open_ids:
                problems.append(f"pr_references[{i}].open_question_ref '{oq}' is not in the plan's open_questions")

    if len(value) > 1:
        authoritative = [
            item for item in value
            if isinstance(item, dict) and str(item.get("status", "")).strip() == "AUTHORITATIVE"
        ]
        for item in authoritative:
            if not str(item.get("comparison_note", "")).strip():
                problems.append(
                    f"pr_references entry '{item.get('pr_ref', '?')}' is AUTHORITATIVE but has no "
                    f"comparison_note explaining what the diff against the other PR(s) showed"
                )
        resolved = [
            item for item in value
            if isinstance(item, dict) and str(item.get("status", "")).strip() != "UNRESOLVED"
        ]
        if resolved and len(authoritative) != 1:
            problems.append(
                "pr_references lists more than one PR/branch but does not mark exactly one "
                "AUTHORITATIVE (with the rest SUPERSEDED/PARALLEL_UNRELATED) - reconcile which PR "
                "is the real grounding source, or mark entries UNRESOLVED with an Open Question"
            )
    return problems


def _run(args, cwd):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def compare(repo_path: str, base_ref: str, pr_a: str, pr_b: str) -> dict:
    """Fetch two PR refs into a local clone and report their file-level overlap plus a
    direct diff between them, so a supersession call can be made from evidence."""
    fetch_log = {}
    for label, number in (("pr_a", pr_a), ("pr_b", pr_b)):
        rc, out, err = _run(["git", "fetch", "origin", f"+refs/pull/{number}/head:pr-{number}"], repo_path)
        fetch_log[label] = {"ok": rc == 0, "output": (out + err).strip()[-1000:]}

    def _stat_files(ref_range: str) -> tuple[set[str], str]:
        rc, out, err = _run(["git", "diff", "--stat", ref_range], repo_path)
        files = {line.split("|")[0].strip() for line in out.splitlines() if "|" in line}
        return files, out if rc == 0 else (out + err)

    files_a, stat_a = _stat_files(f"{base_ref}...pr-{pr_a}")
    files_b, stat_b = _stat_files(f"{base_ref}...pr-{pr_b}")
    _, between_stat = _stat_files(f"pr-{pr_a}...pr-{pr_b}")
    return {
        "repo_path": repo_path,
        "base_ref": base_ref,
        "pr_a": pr_a,
        "pr_b": pr_b,
        "fetch": fetch_log,
        "files_only_in_pr_a": sorted(files_a - files_b),
        "files_only_in_pr_b": sorted(files_b - files_a),
        "files_in_both": sorted(files_a & files_b),
        "pr_a_diff_stat": stat_a,
        "pr_b_diff_stat": stat_b,
        "pr_a_to_pr_b_diff_stat": between_stat,
    }


def main() -> int:
    if len(sys.argv) != 5:
        print(
            "Usage: python pr_supersession_check.py <repo_path> <base_ref> <pr_a_number> <pr_b_number>",
            file=sys.stderr,
        )
        return 1
    _, repo_path, base_ref, pr_a, pr_b = sys.argv
    print(json.dumps(compare(repo_path, base_ref, pr_a, pr_b), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
