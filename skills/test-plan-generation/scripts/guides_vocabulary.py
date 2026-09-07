"""AEM Guides product-vocabulary library for acceptance criteria.

Curated, human-approved vocabulary that keeps ACs in correct AEM Guides terms and
stops support/ticket wording from being asserted as a product concept the product
does not have. The library lives in data/guides_vocabulary.json:

  * block  - phrases naming a non-existent product concept (e.g. "stale preset").
             Fail-closed: a matching AC line is a gate failure.
  * advise - correct-term nudges too broad to hard-fail (the wrong word can be
             legitimate elsewhere, e.g. "workflow"). Surfaced as advisory only.

This encodes PRODUCT VOCABULARY, never code identifiers (no method/class names).
Governance: every entry is HUMAN_APPROVED and cites the source Jira; add entries
only from a real human correction. Standard library only.

CLI:
  python guides_vocabulary.py --check <file>   # print block + advise hits
  python guides_vocabulary.py --self-test
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parent.parent / "data" / "guides_vocabulary.json"
_AC_LINE_RE = re.compile(r"^\s*[-*]?\s*AC-?\d+\b", re.IGNORECASE)


def load_library(path: Path | None = None) -> dict[str, Any]:
    """Load the vocabulary library; return an empty library if the file is absent
    or malformed (fail-open on load so the gate never crashes authoring)."""
    p = path or _DATA
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"block": [], "advise": []}
    if not isinstance(data, dict):
        return {"block": [], "advise": []}
    data.setdefault("block", [])
    data.setdefault("advise", [])
    return data


def _compile(entry: dict[str, Any]) -> re.Pattern | None:
    pat = entry.get("pattern")
    if not isinstance(pat, str) or not pat:
        return None
    try:
        return re.compile(pat, re.IGNORECASE)
    except re.error:
        return None


def _ac_lines(text: str) -> list[str]:
    return [ln for ln in (text or "").splitlines() if _AC_LINE_RE.match(ln)]


def check(text: str, library: dict[str, Any] | None = None) -> tuple[list[str], list[str]]:
    """Return (block_failures, advisories) for the AC lines in text."""
    lib = library or load_library()
    block_hits: list[str] = []
    advise_hits: list[str] = []
    lines = _ac_lines(text)
    for kind, out in (("block", block_hits), ("advise", advise_hits)):
        for entry in lib.get(kind, []):
            rx = _compile(entry)
            if not rx:
                continue
            for line in lines:
                if rx.search(line):
                    msg = entry.get("message", "")
                    out.append(f"[{entry.get('id','?')}] {msg} Line: {line.strip()[:70]!r}.")
                    break  # one hit per entry is enough to flag
    return block_hits, advise_hits


def validate(text: str, library: dict[str, Any] | None = None) -> list[str]:
    """Fail-closed block-list failures only (advisories are not failures)."""
    block_hits, _ = check(text, library)
    return block_hits


def run_self_tests() -> None:
    lib = {
        "block": [{"id": "stale-preset", "pattern": r"stale[-\s]*(output\s*)?preset",
                   "message": "No stale-preset concept."}],
        "advise": [{"id": "run-workflow", "pattern": r"run'?s?\s+workflow|workflow\s+state",
                    "message": "Use output history."},
                   {"id": "generated-file-vague", "pattern": r"generated\s+file",
                    "message": "Name the fmdita-outputs folder."}],
    }
    bad = "- AC-01: advise the author to recreate the stale preset."
    b, a = check(bad, lib)
    assert any("stale-preset" in x for x in b), b
    wf = "- AC-02: when the run's workflow cannot be read, show status unavailable."
    b, a = check(wf, lib)
    assert b == [] and any("run-workflow" in x for x in a), (b, a)
    vague = "- AC-03: the generated file is present in the output folder."
    b, a = check(vague, lib)
    assert any("generated-file-vague" in x for x in a), a
    clean = "- AC-04: the generated output is present in the fmdita-outputs folder set for that preset."
    b, a = check(clean, lib)
    assert b == [] and a == [], (b, a)
    # non-AC lines are ignored
    assert check("A design note mentions a stale preset workaround.", lib) == ([], [])
    # the shipped library loads and is well-formed
    shipped = load_library()
    assert isinstance(shipped.get("block"), list) and isinstance(shipped.get("advise"), list)
    for entry in shipped["block"] + shipped["advise"]:
        assert _compile(entry) is not None, f"bad pattern: {entry.get('id')}"
        assert entry.get("governance") == "HUMAN_APPROVED", entry.get("id")
    print("guides_vocabulary self-tests: PASS")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", metavar="FILE")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        run_self_tests()
        return 0
    if args.check:
        text = Path(args.check).read_text(encoding="utf-8")
        block_hits, advise_hits = check(text)
        if block_hits:
            print("BLOCK (fail-closed):")
            for h in block_hits:
                print("  -", h)
        if advise_hits:
            print("ADVISE (review):")
            for h in advise_hits:
                print("  -", h)
        if not block_hits and not advise_hits:
            print("guides_vocabulary: no issues.")
        return 1 if block_hits else 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
