"""Extract canonical Acceptance Criteria as deterministic automation input."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ac_contract import (  # noqa: E402
    AC_EXACT_FORMAT,
    acceptance_lines,
    parse_ac_line,
    validate_ac_paste_safety,
    validate_ac_readability,
    validate_ac_sequence,
)
from ac_decidability import evaluate_plan  # noqa: E402


def extract(text: str) -> tuple[list[dict[str, str]], list[str]]:
    criteria: list[dict[str, str]] = []
    problems: list[str] = []
    for line in acceptance_lines(text):
        criterion = parse_ac_line(line)
        if criterion is None:
            problems.append(f"unparseable AC line; expected `{AC_EXACT_FORMAT}`: {line}")
            continue
        criteria.append(dict(criterion))
        problems.extend(
            f"{criterion['id']}: {problem}"
            for problem in validate_ac_paste_safety(criterion)
        )
        problems.extend(
            f"{criterion['id']}: {problem}"
            for problem in validate_ac_readability(criterion)
        )
    problems.extend(validate_ac_sequence(criteria))
    decidability_failures, _ = evaluate_plan(text)
    problems.extend(decidability_failures)
    # Never hand a partial or semantically invalid AC payload to automation, Jira,
    # compact rendering, or a downstream adapter.
    return ([], problems) if problems else (criteria, [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract strict Given/When/Then AC records for automation drafting."
    )
    parser.add_argument("plan_file")
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    plan_path = Path(args.plan_file)
    if not plan_path.is_file():
        print(f"plan file not found: {plan_path}", file=sys.stderr)
        return 2

    criteria, problems = extract(plan_path.read_text(encoding="utf-8"))
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        print("No automation input was emitted because the AC contract is invalid.", file=sys.stderr)
        return 1

    payload = json.dumps(criteria, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        out_path = Path(args.out)
        out_path.write_text(payload, encoding="utf-8")
        print(f"wrote {len(criteria)} acceptance criteria to {out_path}")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
