"""DITA semantic-neighbourhood activation gate (UACGAP-03).

When a ticket names a DITA construct whose SEMANTICS govern the behaviour (an
attribute like @navtitle / @frame / @rowsep / @conref / @keyref, or an element
like topichead / mapref / reltable), the plan must not stop at the one construct
the reporter named - the governing and dependent neighbours (e.g. @locktitle
governs @navtitle; the referenced <title> feeds it; topichead is the href-less
variant) are exactly where coverage is silently missed.

This gate makes that neighbourhood NON-OPTIONAL to consider. It does not force the
heavy strict explorer: when a construct is detected the manifest must declare a
`dita_semantics` block that is either

  * active:true  -> the canonical strict explorer (coverage_gate) runs, or
  * active:false -> with a non-empty `neighbourhood_assessment` that names the
                    primary construct(s) and the governing/dependent neighbours
                    considered (and where they are covered), or states there is no
                    in-scope neighbour and why.

Plans that name no governing DITA construct are unaffected (backward-compatible).

Generic only. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PREFIX = "DITA SEMANTICS GATE:"
BLOCK = "dita_semantics"

# The detection vocabulary lives in data/dita_constructs.json - a flat lexical list
# of DITA construct names, NOT a construct->construct relationship table. Loading it
# from data keeps this gate free of any hand-coded construct mapping: the governing
# and dependent neighbours of a named construct are discovered by the author at run
# time; this list only decides WHEN that discovery is forced.
def _load_vocabulary() -> tuple[set[str], set[str]]:
    path = Path(__file__).resolve().parents[1] / "data" / "dita_constructs.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set(), set()
    attrs = {str(x).lower() for x in data.get("governing_attributes", []) if str(x).strip()}
    words = {str(x).lower() for x in data.get("distinctive_constructs", []) if str(x).strip()}
    return attrs, words


DITA_ATTRS, UNAMBIGUOUS_CONSTRUCTS = _load_vocabulary()

_ATTR_RE = re.compile(r"@([a-z][a-z0-9-]*)", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z][a-z0-9-]*", re.IGNORECASE)


def _issue_text(manifest: dict[str, Any]) -> str:
    issue = manifest.get("issue") if isinstance(manifest, dict) else None
    if not isinstance(issue, dict):
        return ""
    return "\n".join(str(issue.get(k, "")) for k in ("summary", "description", "title"))


def detect_constructs(plan_body: str = "", manifest: dict[str, Any] | None = None) -> list[str]:
    manifest_data = manifest if isinstance(manifest, dict) else {}
    hay = (_issue_text(manifest_data) + "\n" + (plan_body or "")).lower()
    found: set[str] = set()
    for m in _ATTR_RE.finditer(hay):
        name = m.group(1).lower()
        if name in DITA_ATTRS:
            found.add(name)
    words = set(_WORD_RE.findall(hay))
    found |= (words & UNAMBIGUOUS_CONSTRUCTS)
    return sorted(found)


def is_present(plan_body: str = "", manifest: dict[str, Any] | None = None) -> bool:
    manifest_data = manifest if isinstance(manifest, dict) else {}
    if str(manifest_data.get("behaviour_matters", True)).lower() == "false":
        return False
    return bool(detect_constructs(plan_body, manifest_data))


def _problem(message: str) -> str:
    return f"{PREFIX} {message}"


def validate(plan_body: str = "", manifest: dict[str, Any] | None = None) -> list[str]:
    manifest_data = manifest if isinstance(manifest, dict) else {}
    constructs = detect_constructs(plan_body, manifest_data)
    if not constructs or str(manifest_data.get("behaviour_matters", True)).lower() == "false":
        return []

    block = manifest_data.get(BLOCK)
    named = ", ".join(constructs[:6])
    if not isinstance(block, dict):
        return [_problem(
            f"named DITA construct(s) [{named}] carry governing semantics, but no dita_semantics "
            f"block is declared - add one that is either active:true (the strict semantic explorer "
            f"runs) or active:false with a neighbourhood_assessment naming the governing/dependent "
            f"neighbours considered and where they are covered"
        )]

    # active:true delegates to the canonical strict explorer via coverage_gate; nothing more here.
    if block.get("active") is True:
        return []

    problems: list[str] = []
    primary = block.get("primary_constructs")
    if not isinstance(primary, list) or not any(str(x).strip() for x in primary):
        problems.append(_problem(
            "dita_semantics.active is not true, so primary_constructs must list the DITA construct(s) "
            "whose neighbourhood was assessed"
        ))
    assessment = str(block.get("neighbourhood_assessment", "")).strip()
    if len(assessment) < 40:
        problems.append(_problem(
            "dita_semantics.neighbourhood_assessment must name the governing and dependent neighbours "
            "of the construct(s) (e.g. what governs it, what it inherits from, its href-less/specialized "
            "variants) and where each is covered, or state there is no in-scope neighbour and why"
        ))
    return problems


def summarize(plan_body: str = "", manifest: dict[str, Any] | None = None) -> str:
    constructs = detect_constructs(plan_body, manifest)
    if not constructs:
        return "dita semantics gate: no governing construct named"
    problems = validate(plan_body, manifest)
    status = "CLEAN" if not problems else f"{len(problems)} issue(s)"
    return f"dita semantics gate: constructs {constructs} | {status}"


def main() -> int:
    parser = argparse.ArgumentParser(description="DITA semantic-neighbourhood activation gate")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    import pathlib
    plan_body = pathlib.Path(args.plan).read_text(encoding="utf-8") if pathlib.Path(args.plan).exists() else ""
    manifest_data = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8")) if pathlib.Path(args.manifest).exists() else {}
    problems = validate(plan_body, manifest_data)
    if problems:
        for p in problems:
            print(p)
        return 1
    print(summarize(plan_body, manifest_data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
