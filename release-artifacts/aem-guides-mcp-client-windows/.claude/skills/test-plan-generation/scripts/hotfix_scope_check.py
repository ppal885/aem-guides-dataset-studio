"""Check that every Acceptance Criterion of a hotfix or backport UAC belongs to the hotfix.

WHAT IT DOES
------------
A hotfix UAC is scoped by two things only: the lines of the hotfix ticket itself, and the code the
hotfix actually changes. A mainline (parent) ticket's accepted Acceptance Criteria are an oracle for
behaviour the hotfix changes, never scope on their own, and behaviour that is identical on the base
branch and the hotfix branch is not a regression the hotfix can introduce.

The author writes HOTFIX_SCOPE.json next to UAC.md:

    {
      "ticket_lines": ["<a requirement line copied from the hotfix ticket>", ...],
      "diffs": [{"repo": "<absolute path of a local clone>", "base": "<base ref>", "head": "<hotfix ref>"}],
      "acs": [
        {"ac": 1, "basis": "TICKET_LINE", "ticket_line": "<one of ticket_lines>"},
        {"ac": 4, "basis": "CHANGED_CODE", "files": [{"path": "<repo-relative path>", "lines": "78-89"}]},
        {"ac": 9, "basis": "PARENT_TICKET", "reason": "..."}
      ]
    }

This script fails when an Acceptance Criterion has no entry, when a TICKET_LINE is not one of the
ticket lines or is a generic "no regression" line (that line cannot scope anything by itself; a
regression criterion must cite the changed code it guards), when none of the cited lines of a CHANGED_CODE file were added or changed by
`git diff -U0 <base>...<head>` in a listed clone (checked with git, never taken on trust; a file the
hotfix touched elsewhere does not count), or when an Acceptance Criterion rests only on a
parent ticket or on unchanged behaviour and carries no TBD for the product owner.

Usage:
    python hotfix_scope_check.py UAC_MD HOTFIX_SCOPE_JSON

Stdlib only.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

SCOPE_FILE = "HOTFIX_SCOPE.json"
IN_SCOPE_BASES = ("TICKET_LINE", "CHANGED_CODE")
OUT_OF_SCOPE_BASES = ("PARENT_TICKET", "UNCHANGED_BEHAVIOUR")
HOTFIX_SIGNAL = re.compile(r"\bhot\s*-?\s*fix\b|\bbackport(?:ed|ing)?\b|release-hotfix", re.IGNORECASE)
GENERIC_REGRESSION_LINE = re.compile(
    r"^(?:there should be |ensure |make sure )?(?:no|zero) (?:regression|regressions|impact|side effects?)\b"
    r"|^(?:nothing|existing (?:functionality|behaviou?r)) (?:else )?should (?:not )?(?:break|be (?:impacted|affected))"
    r"|^existing functionality should (?:work|continue)", re.IGNORECASE)
_AC_BLOCK = re.compile(r"^- Acceptance Criteria (\d+):(.*?)(?=^- Acceptance Criteria \d+:|\Z)", re.M | re.S)


def is_hotfix(*texts: str) -> bool:
    """True when the ticket text says it is a hotfix or a backport."""
    return any(HOTFIX_SIGNAL.search(t or "") for t in texts)


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[*_{}|`\"'‘’“”]", " ", str(text).lower()).split()).strip(" .,:;!?-")


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_changed_lines(diff_text: str) -> dict[str, set[int]]:
    """Map each file of a `git diff -U0` to the head-side line numbers the diff added or changed.

    A pure deletion marks the lines on both sides of the gap, so a criterion about the code around a
    removed line still counts as touched."""
    changed: dict[str, set[int]] = {}
    current = None
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            name = line[4:].strip()
            current = None if name == "/dev/null" else name[2:] if name.startswith("b/") else name
            if current is not None:
                changed.setdefault(current, set())
            continue
        match = _HUNK.match(line)
        if match and current is not None:
            start, count = int(match.group(1)), int(match.group(2) if match.group(2) is not None else 1)
            changed[current].update(range(start, start + count) if count else (start, start + 1))
    return changed


def git_changed_lines(repo: str, base: str, head: str) -> dict[str, set[int]]:
    result = subprocess.run(["git", "-C", repo, "diff", "-U0", f"{base}...{head}"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip()[:200])
    return parse_changed_lines(result.stdout)


def _line_numbers(spec) -> set[int]:
    numbers: set[int] = set()
    for part in re.split(r"[,\s]+", str(spec or "").strip()):
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if match:
            start = int(match.group(1))
            numbers.update(range(start, int(match.group(2) or start) + 1))
    return numbers


def check(scope: dict, uac_text: str,
          changed_lines: Callable[[str, str, str], dict[str, set[int]]] = git_changed_lines) -> list[str]:
    """Return problems; an empty list means every Acceptance Criterion is in hotfix scope."""
    if not isinstance(scope, dict):
        return [f"{SCOPE_FILE} must be a JSON object"]
    blocks = {int(n): body for n, body in _AC_BLOCK.findall(uac_text)}
    lines = {_normalize(line) for line in scope.get("ticket_lines") or [] if str(line).strip()}
    problems: list[str] = []
    if not lines:
        problems.append(f"{SCOPE_FILE}: list the hotfix ticket's own requirement lines in \"ticket_lines\"")

    diff_lines: dict[str, set[int]] = {}
    if not scope.get("diffs"):
        problems.append(f"{SCOPE_FILE}: list the hotfix diff in \"diffs\" (repo, base ref, hotfix ref)")
    for number, diff in enumerate(scope.get("diffs") or [], 1):
        try:
            for path, numbers in changed_lines(str(diff["repo"]), str(diff["base"]), str(diff["head"])).items():
                diff_lines.setdefault(path, set()).update(numbers)
        except (KeyError, TypeError):
            problems.append(f"{SCOPE_FILE}: diff {number} needs repo, base and head")
        except (OSError, RuntimeError) as exc:
            problems.append(f"{SCOPE_FILE}: could not read the hotfix diff {number} ({exc})")

    entries = {}
    for entry in scope.get("acs") or []:
        if isinstance(entry, dict) and isinstance(entry.get("ac"), int):
            entries[entry["ac"]] = entry
    for ac in sorted(blocks):
        entry = entries.get(ac)
        label = f"Acceptance Criteria {ac:02d}"
        if entry is None:
            problems.append(f"{label}: no entry in {SCOPE_FILE}; say which hotfix ticket line or changed code it covers")
            continue
        basis = entry.get("basis")
        if basis == "TICKET_LINE":
            ticket_line = _normalize(entry.get("ticket_line") or "")
            if ticket_line not in lines:
                problems.append(f"{label}: its ticket_line is not one of the hotfix ticket lines")
            elif GENERIC_REGRESSION_LINE.search(ticket_line):
                problems.append(f"{label}: a generic no-regression line does not scope an Acceptance Criterion; "
                                "cite the code the hotfix changed (CHANGED_CODE) that this check guards")
        elif basis == "CHANGED_CODE":
            files = [f for f in entry.get("files") or [] if isinstance(f, dict)]
            if not files:
                problems.append(f"{label}: CHANGED_CODE needs files, each with a path and the cited lines")
            touched = False
            for item in files:
                path = str(item.get("path") or "").replace("\\", "/").strip()
                cited = _line_numbers(item.get("lines"))
                if not path or not cited:
                    problems.append(f"{label}: every CHANGED_CODE file needs a path and the cited lines")
                    continue
                changed = set()
                for diff_path, numbers in diff_lines.items():
                    if diff_path == path or diff_path.endswith("/" + path) or path.endswith("/" + diff_path):
                        changed |= numbers
                touched = touched or bool(cited & changed)
            if files and not touched:
                problems.append(f"{label}: none of its cited lines were added or changed by the hotfix, so it is "
                                "not a hotfix regression; remove it, raise it on the parent ticket, or add a TBD")
        elif basis in OUT_OF_SCOPE_BASES:
            if "TBD:" not in blocks[ac]:
                problems.append(f"{label}: rests only on {basis.lower().replace('_', ' ')}, which the hotfix does not "
                                "change; remove it from the hotfix UAC, raise it on the parent ticket, or add a TBD")
        else:
            problems.append(f"{label}: basis {basis!r} is not one of "
                            f"{', '.join(IN_SCOPE_BASES + OUT_OF_SCOPE_BASES)}")
    for ac in sorted(set(entries) - set(blocks)):
        problems.append(f"{SCOPE_FILE} names Acceptance Criteria {ac:02d}, which is not in the UAC")
    return problems


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(__doc__)
        return 2
    uac_text = Path(args[0]).read_text(encoding="utf-8")
    try:
        scope = json.loads(Path(args[1]).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        print(f"FAIL: {SCOPE_FILE} could not be read: {exc}")
        return 1
    problems = check(scope, uac_text)
    for problem in problems:
        print(f"FAIL: {problem}")
    print("PASS: every Acceptance Criterion is in hotfix scope" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
