"""Measure the ticket-text signals of the repeated-QE-correction gates, instead of checking tickets by hand.

For every case in pattern_gate_cases.json (tickets QE corrected for a pattern) it runs the signals of the
skill's uac_completeness_check.py on the live ticket text and reports whether the gate asks for what QE asked
for (expect) and stays quiet where QE called it noise (forbid). On the human-UAC corpus (corpus.jsonl, no Jira
needed) it reports how often each signal fires - the noise budget a gate change must stay within.

Read-only: Jira is only read (backend/.env, JiraClient). --cache saves and reuses the ticket text.

Usage:
  python scripts/uac_eval/measure_pattern_gates.py                      # cases (live Jira) + corpus
  python scripts/uac_eval/measure_pattern_gates.py --cache out/sources.json
  python scripts/uac_eval/measure_pattern_gates.py --corpus-only
  python scripts/uac_eval/measure_pattern_gates.py --self-test
Exit 1 when a case misses what QE asked for or fires where QE called it noise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CASES = HERE / "pattern_gate_cases.json"
CORPUS = HERE / "corpus.jsonl"
sys.path.insert(0, str(ROOT / "skills" / "test-plan-generation" / "scripts"))
import uac_completeness_check as uc  # noqa: E402


def signals(source: dict) -> dict:
    """What the gates ask for on this ticket text."""
    attachments = [str(a.get("filename") or "") for a in source.get("attachments") or [] if isinstance(a, dict)]
    return {
        "action_settings": [s["label"] for s in uc.required_action_settings(source)],
        "after_state": uc.after_state_kinds(source),
        "tbd_attachments": [a for a in attachments if uc._DECIDING_ATTACHMENT.search(a)],
    }


def judge(case: dict, found: dict) -> list[str]:
    """The case's problems: a missing expectation or a forbidden signal."""
    problems = []
    for name, wanted in (case.get("expect") or {}).items():
        if name == "tbd_attachments_min":
            if len(found["tbd_attachments"]) < wanted:
                problems.append(f"expected at least {wanted} recording or document for TBDs to check, found "
                                f"{len(found['tbd_attachments'])}")
            continue
        missing = [w for w in wanted if w not in found.get(name, [])]
        if missing:
            problems.append(f"{name} misses {missing}")
    for name, banned in (case.get("forbid") or {}).items():
        hits = found.get(name, []) if "*" in banned else [b for b in banned if b in found.get(name, [])]
        if hits:
            problems.append(f"{name} fires {hits} where QE called it noise")
    return problems


def jira_source(key: str, env: Path) -> dict:
    sys.path.insert(0, str(ROOT / "backend"))
    from dotenv import load_dotenv  # noqa: PLC0415

    load_dotenv(env)
    from app.services.jira_client import JiraClient  # noqa: PLC0415

    fields = JiraClient().get_issue(key, fields="summary,description,comment,attachment").get("fields") or {}
    return {"summary": fields.get("summary") or "", "description": fields.get("description") or "",
            "comments": [{"body": c.get("body") or ""} for c in (fields.get("comment") or {}).get("comments") or []],
            "attachments": [{"filename": a.get("filename")} for a in fields.get("attachment") or []]}


def load_sources(keys: list[str], cache: Path | None, env: Path) -> dict[str, dict]:
    sources = json.loads(cache.read_text(encoding="utf-8")) if cache and cache.is_file() else {}
    for key in keys:
        if key not in sources:
            sources[key] = jira_source(key, env)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(sources, indent=1, ensure_ascii=False), encoding="utf-8")
    return sources


def run_cases(cases: list[dict], sources: dict[str, dict]) -> int:
    failed = 0
    print("Cases (QE corrections):")
    for case in cases:
        found = signals(sources[case["key"]])
        problems = judge(case, found)
        failed += bool(problems)
        print(f"  {'FAIL' if problems else 'ok  '} {case['key']} {case['pattern']}: "
              f"{'; '.join(problems) or 'as QE asked'}")
    print(f"  {len(cases) - failed}/{len(cases)} cases as QE asked")
    return failed


def run_line_cases(cases: list[dict]) -> int:
    """UAC lines QE corrected (guessed-decision) must ask for a decisions record; plain lines must not."""
    failed = 0
    print("Line cases (a handling choice needs a decisions record):")
    for case in cases:
        fired = bool(uc._handling_lines(case["line"]))
        ok = fired == case["needs_decision"]
        failed += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {case['key']}: {'asks' if fired else 'no record'} - {case['line'][:80]}")
    return failed


def corpus_rates(path: Path = CORPUS) -> dict:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    counts = {"tickets": len(rows), "action_settings": {}, "after_state": {}, "ac_lines": 0, "handling_lines": 0,
              "handling_tickets": 0}
    for row in rows:
        lines = [line for line in (row.get("human_ac") or "").splitlines() if line.strip()]
        handling = [line for line in lines if uc._handling_lines(line)]
        counts["ac_lines"] += len(lines)
        counts["handling_lines"] += len(handling)
        counts["handling_tickets"] += bool(handling)
        found = signals({"summary": row.get("summary") or "", "description": row.get("description") or ""})
        for name in ("action_settings", "after_state"):
            for value in found[name]:
                counts[name][value] = counts[name].get(value, 0) + 1
    return counts


def print_rates(counts: dict) -> None:
    total = counts["tickets"]
    print(f"Human-UAC corpus firing rate ({total} tickets, summary and description):")
    for name in ("action_settings", "after_state"):
        for value, n in sorted(counts[name].items(), key=lambda kv: -kv[1]):
            print(f"  {name}: {value} on {n} ticket(s) ({100 * n / total:.1f}%)")
        if not counts[name]:
            print(f"  {name}: never")
    if counts["ac_lines"]:
        print(f"  decisions: {counts['handling_lines']} of {counts['ac_lines']} human AC lines state a handling choice "
              f"({100 * counts['handling_lines'] / counts['ac_lines']:.1f}%), on {counts['handling_tickets']} ticket(s) "
              f"({100 * counts['handling_tickets'] / total:.1f}%)")


def self_test() -> int:
    replace = {"summary": "Find & Replace fails on a large map", "description": "Run Replace all."}
    found = signals(replace)
    assert "Enable Replace All" in found["action_settings"], found
    assert found["after_state"] == ["END_RESULT"], found
    steps = {"summary": "Doc state list is wrong", "description": "1. Create topic1\n2. Change the state"}
    assert signals(steps)["action_settings"] == [], "a reproduction step does not make topic creation the action"
    assert judge({"forbid": {"action_settings": ["*"]}}, signals(steps)) == []
    assert judge({"expect": {"action_settings": ["Enable Replace All"]}}, signals(steps))
    rec = {"summary": "x", "attachments": [{"filename": "call.mp4"}, {"filename": "a.png"}]}
    assert judge({"expect": {"tbd_attachments_min": 1}}, signals(rec)) == []
    assert uc._handling_lines("The second action waits and then uses the new versions.")
    assert not uc._handling_lines("Export baseline lists the newer version.")
    assert not uc._handling_lines("  TBD: Should the second action wait?")
    print("measure_pattern_gates self-test: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--cache", type=Path, help="save and reuse the fetched ticket text (JSON)")
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument("--env", type=Path, default=ROOT / "backend" / ".env",
                        help="the backend .env with the Jira settings (a worktree has none; pass the main checkout's)")
    parser.add_argument("--corpus-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    failed = 0
    if not args.corpus_only:
        cases = json.loads(args.cases.read_text(encoding="utf-8"))["cases"]
        data = json.loads(args.cases.read_text(encoding="utf-8"))
        failed = run_cases(cases, load_sources(sorted({c["key"] for c in cases}), args.cache, args.env))
        failed += run_line_cases(data.get("line_cases") or [])
    if args.corpus.is_file():
        print_rates(corpus_rates(args.corpus))
    else:
        print(f"corpus {args.corpus} not found; firing rate not measured")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
