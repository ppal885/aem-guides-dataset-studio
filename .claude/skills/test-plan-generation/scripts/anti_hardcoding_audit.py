"""Anti-hardcoding audit for the DITA semantic-relationship explorer (section 21).

The explorer must discover construct relationships from authoritative evidence at
runtime, never from a growing hand-coded list of construct pairs baked into
production code or prompts. This audit fails the build when it finds an
UNCONDITIONAL, hand-authored construct->construct mapping such as::

    if navtitle:
        test_locktitle()

    RULES = {"keyref": "keyscope", "conref": "conkeyref"}

    navtitle -> locktitle          # as a bare rule line

A mapping is ACCEPTABLE (not flagged) when its provenance is preserved — i.e. it
is derived from the indexed spec / semantic index and the line or its immediate
context carries an evidence/provenance marker — or when it appears in a context
explicitly marked as an illustrative example or anti-pattern (the navtitle example
is allowed to live in docs and regression tests, never as a live production rule).

What is scanned:
  * ``.py`` files (production scripts) — the strict target. Test files
    (``test_*.py``) and this auditor are skipped: regression fixtures are allowed
    to contain the anti-pattern on purpose.
  * ``.md`` / ``.txt`` prompt files — flagged only for a bare rule-arrow between
    two DITA constructs with no exemption marker nearby.

Stdlib only. Returns (failures, notes); exit non-zero on any failure.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


# DITA construct NAMES that are DISTINCTIVE — they essentially never occur as an
# ordinary variable/English word, so branching on one (`if navtitle:`) is an
# unambiguous hardcoding smell. This is a list of names, not a relationship truth
# table: naming the tokens we police says nothing about which pairs are related.
UNAMBIGUOUS_CONSTRUCTS = frozenset({
    # attributes
    "navtitle", "locktitle", "keyref", "keyscope", "conkeyref", "conrefend",
    "conref", "processing-role", "collection-type", "copy-to", "otherprops",
    # elements
    "topicref", "topichead", "topicgroup", "mapref", "keydef", "topicmeta",
    "reltable", "relrow", "relcell", "glossentry", "glossterm", "glossarylist",
    "subjectscheme", "enumerationdef", "hasinstance", "bookmap", "frontmatter",
    "backmatter", "booklists", "mathml", "equation-block", "equation-inline",
})

# Construct names that ALSO occur constantly as ordinary code/English tokens
# (`if data:`, `status == "verified"`, `type`, `format`). These are still real DITA
# names, so a construct->construct mapping literal that pairs one of them WITH an
# unambiguous construct is flagged — but a lone `if data:` is not.
AMBIGUOUS_CONSTRUCTS = frozenset({
    "keys", "href", "scope", "format", "type", "chunk", "linking", "toc", "print",
    "search", "cascade", "props", "audience", "platform", "product", "rev",
    "status", "data", "val", "prop",
})

DITA_CONSTRUCTS = UNAMBIGUOUS_CONSTRUCTS | AMBIGUOUS_CONSTRUCTS

# Words that, when present on the mapping line or an adjacent line, mark the pair
# as evidence-derived or as a deliberate illustration — so it is NOT a violation.
EXEMPTION_MARKERS = (
    "evidence", "provenance", "derived", "from_index", "from-index", "indexed",
    "example", "illustrative", "anti-pattern", "antipattern", "must not", "must-not",
    "do not", "don't", "regression test", "hypothesis", "candidate", "vocabulary",
    "schema", "not a mapping", "not a construct", "docstring-example",
)

# Match an UNAMBIGUOUS DITA construct as a standalone token — word-boundaried and
# not part of a larger identifier. This avoids false positives on ordinary code and
# English: `scope_text`/`re.search` never match (ambiguous names are excluded from
# this set entirely), while `if navtitle:`, `@locktitle`, and `"conref"` do. Longer
# names first so `keyscope` wins over `scope`. A leading `@` (attr sigil) is allowed.
_STANDALONE_RE = re.compile(
    r"(?<![\w.\-])@?("
    + "|".join(re.escape(c) for c in sorted(UNAMBIGUOUS_CONSTRUCTS, key=len, reverse=True))
    + r")(?![\w\-])"
)
# a bare rule arrow: tokenA -> tokenB  or  tokenA → tokenB
_ARROW_RULE_RE = re.compile(r"([A-Za-z][\w\-]*)\s*(?:->|→)\s*([A-Za-z][\w\-]*)")
# a dict/tuple literal pairing two quoted tokens: "a": "b"  or  ("a", "b")
_PAIR_LITERAL_RE = re.compile(r"""["']([A-Za-z][\w\-]*)["']\s*[:,]\s*["']([A-Za-z][\w\-]*)["']""")


def _standalone_constructs_in(text: str) -> set[str]:
    return {m.lower() for m in _STANDALONE_RE.findall(text)}


def _is_flaggable_pair(a: str, b: str) -> bool:
    """A construct->construct mapping is flaggable only when both tokens are DITA
    constructs, they differ, and at least one is unambiguous — so a coincidental
    `{"type": "format"}` in generic code is not treated as a DITA truth table."""
    la, lb = a.lower(), b.lower()
    return (
        la in DITA_CONSTRUCTS and lb in DITA_CONSTRUCTS and la != lb
        and (la in UNAMBIGUOUS_CONSTRUCTS or lb in UNAMBIGUOUS_CONSTRUCTS)
    )


def _has_exemption(context: str) -> bool:
    low = context.lower()
    return any(marker in low for marker in EXEMPTION_MARKERS)


def _audit_python(path: Path) -> list[str]:
    findings: list[str] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        context = "\n".join(lines[max(0, i - 2): i + 3])
        if _has_exemption(context):
            continue

        # Shape 1: production logic branching directly on a DITA construct — the exact
        # prohibited pattern `if navtitle: ...`. Only a STANDALONE construct token in
        # an if/elif condition counts, so `if re.search(...)` / `scope_text` are safe.
        cond = re.match(r"(?:el)?if\s+(.*?):", stripped)
        if cond:
            guard_constructs = _standalone_constructs_in(cond.group(1))
            if guard_constructs:
                findings.append(
                    f"{path.name}:{i + 1}: production logic branches on DITA construct(s) "
                    f"{sorted(guard_constructs)} — `if <construct>` is the banned hardcoding "
                    f"pattern; derive the relationship from indexed evidence at runtime "
                    f"(or mark provenance/example)"
                )
                continue

        # Shape 2: dict/tuple literal pairing two DISTINCT construct string-literals.
        for a, b in _PAIR_LITERAL_RE.findall(stripped):
            if _is_flaggable_pair(a, b):
                findings.append(
                    f"{path.name}:{i + 1}: hardcoded construct pair literal "
                    f"'{a.lower()}' -> '{b.lower()}' — a construct->construct truth table is "
                    f"disallowed unless derived from the indexed spec with provenance preserved"
                )
    return findings


def _audit_prompt(path: Path) -> list[str]:
    findings: list[str] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, line in enumerate(lines):
        for a, b in _ARROW_RULE_RE.findall(line):
            if _is_flaggable_pair(a, b):
                context = "\n".join(lines[max(0, i - 4): i + 4])
                if _has_exemption(context):
                    continue
                findings.append(
                    f"{path.name}:{i + 1}: bare construct rule-arrow '{a.lower()} -> {b.lower()}' "
                    f"with no provenance/example marker — a prompt must not encode a fixed construct "
                    f"mapping; derive it from evidence or mark it as an illustrative example"
                )
    return findings


def audit_paths(paths: list[Path]) -> tuple[list[str], list[str]]:
    """Audit a list of files/dirs. Returns (failures, notes)."""
    failures: list[str] = []
    scanned = 0
    self_name = Path(__file__).name
    for root in paths:
        files: list[Path]
        if root.is_dir():
            files = [p for p in root.rglob("*") if p.is_file()]
        else:
            files = [root]
        for f in files:
            if ".git" in f.parts or "__pycache__" in f.parts:
                continue
            if f.suffix == ".py":
                if f.name == self_name or f.name.startswith("test_"):
                    continue
                scanned += 1
                failures.extend(_audit_python(f))
            elif f.suffix in (".md", ".txt"):
                scanned += 1
                failures.extend(_audit_prompt(f))
    notes = [f"anti-hardcoding audit scanned {scanned} file(s)"]
    return failures, notes


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit for hardcoded DITA construct mappings.")
    parser.add_argument("paths", nargs="*", help="files or dirs to scan (default: the skill root)")
    args = parser.parse_args()
    if args.paths:
        roots = [Path(p) for p in args.paths]
    else:
        roots = [Path(__file__).resolve().parent.parent]  # the skill root

    failures, notes = audit_paths(roots)
    for note in notes:
        print(f"NOTE: {note}")
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        print(f"\nANTI-HARDCODING AUDIT FAILED ({len(failures)} issue(s)).")
        return 1
    print("ANTI-HARDCODING AUDIT PASSED — no unconditional construct->construct mappings found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
