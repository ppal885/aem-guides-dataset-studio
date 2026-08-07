"""Extract the Acceptance Criteria block of a validated test plan into structured JSON.

The AC section is authored as sphere-tagged Given|When|Then lines:

    - AC-01 [Proposed]: (Basic) Given <precondition> | When <trigger> | Then <outcome>.

A downstream automation-drafting step should consume THIS JSON, not re-parse the
prose, so it maps sphere->test category, given->fixtures/preconditions,
when->action, then->assertion deterministically (no hallucinated re-parsing).

Run: python scripts/extract_acs.py <plan-file> [--out <file.json>]
Emits a JSON list of {id, status, sphere, given, when, then, raw} to stdout
(or the --out file). Only lines that match the exact AC contract are emitted;
malformed AC lines are reported on stderr so they can be fixed before handoff.

Stdlib only. This is a read-only projection of the validated plan; it never
edits the plan and is not part of the pass/fail gate.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


HEADING_RE = re.compile(r"^\*\*(.+?)\*\*$")
AC_RE = re.compile(
    r"^- (AC-\d{2}) \[(Confirmed|Proposed)\]: "
    r"\((Basic|Negative|Integration|Performance)\) "
    r"Given (.+?) \| When (.+?) \| Then (.+?)\s*$"
)


def _acceptance_lines(text: str) -> list[str]:
    lines = text.splitlines()
    out: list[str] = []
    in_section = False
    for line in lines:
        heading = HEADING_RE.match(line.strip())
        if heading:
            in_section = heading.group(1) == "Acceptance Criteria"
            continue
        if in_section and line.strip():
            out.append(line.rstrip())
    return out


def extract(text: str) -> tuple[list[dict[str, str]], list[str]]:
    acs: list[dict[str, str]] = []
    problems: list[str] = []
    for line in _acceptance_lines(text):
        if not line.startswith("- AC-"):
            continue
        m = AC_RE.match(line)
        if not m:
            problems.append(f"unparseable AC line (not sphere-tagged Given|When|Then): {line}")
            continue
        ac_id, status, sphere, given, when, then = m.groups()
        acs.append(
            {
                "id": ac_id,
                "status": status,
                "sphere": sphere,
                "given": given.strip(),
                "when": when.strip(),
                "then": then.strip().rstrip("."),
                "raw": line[2:].strip(),
            }
        )
    return acs, problems


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: extract_acs.py <plan-file> [--out <file.json>]", file=sys.stderr)
        return 2
    plan_path = Path(argv[0])
    if not plan_path.is_file():
        print(f"plan file not found: {plan_path}", file=sys.stderr)
        return 2
    out_path = None
    if "--out" in argv:
        out_path = Path(argv[argv.index("--out") + 1])

    acs, problems = extract(plan_path.read_text(encoding="utf-8"))
    for p in problems:
        print(f"WARN: {p}", file=sys.stderr)
    payload = json.dumps(acs, indent=2, ensure_ascii=False)
    if out_path:
        out_path.write_text(payload + "\n", encoding="utf-8")
        print(f"wrote {len(acs)} acceptance criteria to {out_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
