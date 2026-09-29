#!/usr/bin/env python3
"""Record which gates and checks fire on real runs, and report how often.

WHY THIS EXISTS
---------------
The skill has about a hundred gate functions, and only one of them (coverage_forcing, as a whole) has
ever been measured. A gate that never fires costs reading time and maintenance for nothing; a gate
that fires on every run tells good plans from bad ones no better than a coin. Before any gate is
merged, demoted or removed, the decision needs its firing rate on real runs. This module only
records and reports: it never changes a gate result, a plan or a receipt.

RECORD (one JSON line per run)
------------------------------
{"at": "<ISO time>", "tool": "run_gates" | "uac-runner" | ..., "key": "<Jira key or ''>",
 "checks": {"<gate or check name>": <number of problems>}, "sub_checks": {"<group>": {"<name>": n}},
 "notes": <advisory note count>, "passed": true | false}

Only the gates that reported at least one problem appear in "checks" for run_gates (its failures
carry the gate's name as a prefix); a check group that ran and found nothing is recorded with 0 when
the caller knows the full list (the VM runner and coverage_forcing sub-checks do).

Usage:
    python gate_firing_log.py report LOG.jsonl [LOG.jsonl ...] [--since YYYY-MM-DD] [--tool NAME]

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path

_BRACKET = re.compile(r"^\s*\[([^\]]+)\]")
_GATE_WORD = re.compile(r"^\s*([A-Z][A-Z0-9 /_-]*? GATE)\s*:")


def gate_of(failure: str) -> str:
    """The gate a failure line belongs to, from its "[name]" or "NAME GATE:" prefix."""
    text = str(failure or "")
    bracket = _BRACKET.match(text)
    if bracket:
        return bracket.group(1).strip().lower()
    word = _GATE_WORD.match(text)
    if word:
        return re.sub(r"[\s/_]+", "-", word.group(1).strip().lower())
    return "unprefixed"


def count_by_gate(failures: list[str]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for failure in failures or []:
        counts[gate_of(failure)] += 1
    return dict(sorted(counts.items()))


def record(path: Path | str, *, tool: str, key: str = "", checks: dict[str, int],
           sub_checks: dict[str, dict[str, int]] | None = None, notes: int = 0, passed: bool | None = None) -> dict:
    """Append one run record. A logging failure never breaks the caller: it returns the record anyway."""
    entry = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "tool": tool, "key": key,
        "checks": {str(k): int(v) for k, v in (checks or {}).items()},
        "sub_checks": {str(g): {str(k): int(v) for k, v in (c or {}).items()} for g, c in (sub_checks or {}).items()},
        "notes": int(notes),
        "passed": (not any((checks or {}).values())) if passed is None else bool(passed),
    }
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except (OSError, ValueError):
        pass
    return entry


def load(paths: list[Path | str], since: str = "", tool: str = "") -> list[dict]:
    records = []
    for path in paths:
        path = Path(path)
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            if since and str(entry.get("at") or "")[:10] < since:
                continue
            if tool and entry.get("tool") != tool:
                continue
            records.append(entry)
    return records


def summarize(records: list[dict]) -> dict:
    """Per check: runs where it fired, total problems, and runs where it was known to have run clean."""
    runs = len(records)
    fired: dict[str, int] = defaultdict(int)
    problems: dict[str, int] = defaultdict(int)
    clean: dict[str, int] = defaultdict(int)
    sub: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for entry in records:
        for name, count in (entry.get("checks") or {}).items():
            if count:
                fired[name] += 1
                problems[name] += count
            else:
                clean[name] += 1
        for group, checks in (entry.get("sub_checks") or {}).items():
            for name, count in checks.items():
                sub[group][name][0] += 1
                sub[group][name][1] += 1 if count else 0
    return {"runs": runs, "passed": sum(1 for e in records if e.get("passed")),
            "checks": {n: {"fired": fired.get(n, 0), "problems": problems.get(n, 0), "clean": clean.get(n, 0)}
                       for n in sorted(set(fired) | set(clean))},
            "sub_checks": {g: {n: {"runs": v[0], "fired": v[1]} for n, v in sorted(c.items())}
                           for g, c in sorted(sub.items())}}


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def report_lines(records: list[dict], title: str = "Gate firing") -> list[str]:
    s = summarize(records)
    runs = s["runs"]
    lines = [f"## {title}", ""]
    if not runs:
        return lines + ["No runs recorded.", ""]
    lines += [f"{runs} run(s); {s['passed']} with no problems ({_pct(s['passed'], runs)}). A check that fires on "
              "nearly every run does not separate good drafts from bad ones; a check that never fires may be "
              "unneeded. Neither is a reason to change a check on its own - read what it caught first.", "",
              "| Check | Runs it fired | Share of runs | Problems |", "| --- | --- | --- | --- |"]
    for name, row in sorted(s["checks"].items(), key=lambda kv: (-kv[1]["fired"], kv[0])):
        lines.append(f"| {name} | {row['fired']} | {_pct(row['fired'], runs)} | {row['problems']} |")
    for group, checks in s["sub_checks"].items():
        lines += ["", f"Sub-checks of {group}:", "", "| Sub-check | Runs | Fired | Share |", "| --- | --- | --- | --- |"]
        for name, row in sorted(checks.items(), key=lambda kv: (-kv[1]["fired"], kv[0])):
            lines.append(f"| {name} | {row['runs']} | {row['fired']} | {_pct(row['fired'], row['runs'])} |")
        never = [n for n, row in checks.items() if row["runs"] and not row["fired"]]
        if never:
            lines += ["", f"Never fired in {group}: " + ", ".join(sorted(never)) + "."]
    return lines + [""]


def run_self_tests() -> None:
    import tempfile

    assert gate_of("[coverage-forcing] performance is not dispositioned") == "coverage-forcing"
    assert gate_of("SECURITY GATE: INPUT_SAFETY missing") == "security-gate"
    assert gate_of("ROOT-CAUSE/FIX GATE: no fix contract") == "root-cause-fix-gate"
    assert gate_of("something else") == "unprefixed"
    assert count_by_gate(["[a] x", "[a] y", "[b] z"]) == {"a": 2, "b": 1}
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "sub" / "gate-firing.jsonl"
        record(log, tool="t", key="K-1", checks={"a": 2, "b": 0},
               sub_checks={"coverage-forcing": {"x": 1, "y": 0}})
        record(log, tool="t", key="K-2", checks={"a": 0, "b": 0},
               sub_checks={"coverage-forcing": {"x": 0, "y": 0}})
        record(log, tool="other", checks={"c": 1})
        rows = load([log], tool="t")
        assert len(rows) == 2 and rows[0]["passed"] is False and rows[1]["passed"] is True
        s = summarize(rows)
        assert s["checks"]["a"] == {"fired": 1, "problems": 2, "clean": 1}
        assert s["sub_checks"]["coverage-forcing"]["y"] == {"runs": 2, "fired": 0}
        text = "\n".join(report_lines(rows))
        assert "| a | 1 | 50% | 2 |" in text and "Never fired in coverage-forcing: y." in text
        assert load([log], since="2999-01-01") == []
        assert record(Path(tmp) / "no" / "\0bad", tool="t", checks={})["passed"] is True  # never raises


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    rep = sub.add_parser("report", help="print how often each gate and check fired")
    rep.add_argument("logs", nargs="+", type=Path)
    rep.add_argument("--since", default="", help="only runs on or after this date (YYYY-MM-DD)")
    rep.add_argument("--tool", default="", help="only runs by this tool (run_gates, uac-runner, ...)")
    sub.add_parser("self-test", help="run the module self-tests")
    args = parser.parse_args(argv)
    if args.command == "self-test":
        run_self_tests()
        print("gate_firing_log self-tests passed")
        return 0
    print("\n".join(report_lines(load(args.logs, args.since, args.tool))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
