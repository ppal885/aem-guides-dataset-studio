"""UAC language & readability policy gate (UACFIX-LANGUAGE-01), backward-compatible.

WHY THIS EXISTS
---------------
Target: DEEP INTERNAL QE REASONING + SIMPLE EXTERNAL QE LANGUAGE. Technically
correct ACs are still weak when wording is long, several ideas are packed into one
AC, implementation language leaks in, or a scenario is hard to identify. This is a
RENDERING/SYNTHESIS concern (the UAC Linter / AcceptanceContractSynthesizer), NOT a
discovery concern - it must never reduce coverage. The hard invariant is
LANGUAGE_SIMPLIFICATION must never cause MATERIAL_CANDIDATE_LOSS.

This gate complements `ac_readability.py` (soft first-read clarity REVIEW notes) and
`ac_presentation.py`. It runs only when the manifest declares an `ac_synthesis`
block that maps each final AC to the internal candidates it represents, so the
merge-safety invariant can be machine-checked. Absent block -> clean pass.

Generic only. Stdlib only. No product-specific literal language rules.
"""
from __future__ import annotations

import re

# Vague, untestable phrasing (lint: VAGUE_EXPECTATION).
VAGUE_PHRASES = (
    "works correctly", "should work", "verify that", "behaves as expected",
    "as expected", "work as intended", "function properly", "handle properly",
)

# Uninformative AC titles (lint: UNCLEAR_AC_TITLE).
BAD_TITLE_PATTERNS = (
    r"^correct\b", r"^handle\b", r"^regression behaviou?r$", r"^proper\b",
    r"^semantic processing$", r"^behaviou?r$",
)

# Implementation-symbol shapes that should not appear in an AC body unless the AC's
# acceptance artifact IS that technical contract (lint: IMPLEMENTATION_DETAIL_LEAK).
CLASS_METHOD_RE = re.compile(r"\b[A-Z][A-Za-z0-9_$]*\.[a-z][A-Za-z0-9_$]*\s*\(")
CSS_SELECTOR_RE = re.compile(r"[.#][A-Za-z_][A-Za-z0-9_-]*\s*[>{]")
FILE_SYMBOL_RE = re.compile(r"\b[A-Za-z0-9_/\\.-]+\.(?:java|py|js|ts|tsx|jsx)\b")

# Distinct material dimensions that must NOT be hidden by a merge.
MATERIAL_DIMENSIONS = frozenset({
    "configuration", "lifecycle", "identity", "consumer", "ordering",
    "failure", "negative_boundary",
})

LANGUAGE_LINTS = (
    "EXCESSIVE_TECHNICAL_LANGUAGE", "EXCESSIVE_EXPLANATION", "MULTIPLE_UNRELATED_CONTRACTS",
    "UNCLEAR_AC_TITLE", "HIDDEN_MATERIAL_SCENARIO", "REDUNDANT_AC",
    "IMPLEMENTATION_DETAIL_LEAK", "VAGUE_EXPECTATION", "AC_OQ_CONTRADICTION",
    "MATERIAL_CANDIDATE_LOSS",
)


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("ac_synthesis"), dict)


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def validate_final_ac(i, ac):
    problems = []
    tag = f"ac_synthesis.final_acs[{i}]"
    if not isinstance(ac, dict):
        return [f"{tag}: each final AC must be an object"]

    ac_ref = ac.get("ac_ref", "")
    title = str(ac.get("title", "")).strip()
    body = str(ac.get("body", "")).strip()

    # Title clarity.
    if not title:
        problems.append(f"{tag}: UNCLEAR_AC_TITLE - missing title (a title must name the behavior the AC protects)")
    else:
        low = _norm(title)
        if any(re.search(p, low) for p in BAD_TITLE_PATTERNS):
            problems.append(f"{tag}: UNCLEAR_AC_TITLE - '{title}' does not identify the scenario")

    # Vague, untestable phrasing.
    low_body = _norm(body)
    for phrase in VAGUE_PHRASES:
        if phrase in low_body:
            problems.append(f"{tag}: VAGUE_EXPECTATION - remove '{phrase}'; state a clear must / must-not outcome")
            break

    # Implementation-detail leak, unless the AC declares the symbol is the artifact.
    if not ac.get("technical_artifact_is_requirement"):
        if CLASS_METHOD_RE.search(body) or CSS_SELECTOR_RE.search(body) or FILE_SYMBOL_RE.search(body):
            problems.append(
                f"{tag}: IMPLEMENTATION_DETAIL_LEAK - internal symbol/selector/file in the AC body; "
                f"state observable product behavior (set technical_artifact_is_requirement only when the "
                f"artifact itself is the acceptance contract, e.g. a required temp file)"
            )

    # One primary behavior: multiple unrelated contracts packed in.
    if int(ac.get("distinct_contract_count", 1) or 1) > 1:
        problems.append(f"{tag}: MULTIPLE_UNRELATED_CONTRACTS - {ac_ref or 'AC'} packs more than one customer contract; split it")

    return problems


def validate(manifest):
    if not is_present(manifest):
        return []
    block = manifest["ac_synthesis"]
    problems = []

    final_acs = block.get("final_acs", [])
    if not isinstance(final_acs, list):
        return ["ac_synthesis.final_acs must be a list"]

    # Per-AC language lints.
    seen_bodies = {}
    for i, ac in enumerate(final_acs):
        problems.extend(validate_final_ac(i, ac))
        if isinstance(ac, dict):
            key = _norm(ac.get("body"))
            if key and key in seen_bodies:
                problems.append(
                    f"ac_synthesis.final_acs[{i}]: REDUNDANT_AC - body duplicates {seen_bodies[key]}"
                )
            elif key:
                seen_bodies[key] = ac.get("ac_ref", f"index {i}")

    # MATERIAL_CANDIDATE_LOSS = 0: every source candidate must survive into a final AC.
    source_candidates = block.get("source_candidate_ids")
    if source_candidates is not None:
        if not isinstance(source_candidates, list):
            problems.append("ac_synthesis.source_candidate_ids must be a list")
        else:
            retained = set()
            for ac in final_acs:
                if not isinstance(ac, dict):
                    continue
                for field in ("candidate_ids", "merged_candidate_ids"):
                    vals = ac.get(field) or []
                    if isinstance(vals, list):
                        retained.update(str(v) for v in vals if str(v).strip())
            lost = [str(c) for c in source_candidates if str(c) not in retained]
            if lost:
                problems.append(
                    "MATERIAL_CANDIDATE_LOSS - language simplification/merge dropped candidate(s) "
                    + ", ".join(sorted(lost)) + "; a merged AC must retain every candidate_id"
                )

    # Merges must not hide a distinct material dimension.
    for i, ac in enumerate(final_acs):
        if not isinstance(ac, dict):
            continue
        merged = ac.get("merged_candidate_ids") or []
        if isinstance(merged, list) and len(merged) > 1:
            hidden = [d for d in (ac.get("distinct_material_dimensions") or [])
                      if str(d).lower() in MATERIAL_DIMENSIONS]
            if hidden:
                problems.append(
                    f"ac_synthesis.final_acs[{i}]: HIDDEN_MATERIAL_SCENARIO - merge hides distinct material "
                    f"{', '.join(sorted(hidden))}; do not merge ACs that carry distinct material "
                    f"configuration/lifecycle/identity/consumer/ordering/failure/negative-boundary behavior"
                )

    return problems


def summarize(manifest):
    if not is_present(manifest):
        return "AcLanguagePolicy: NOT_PRESENT (backward-compatible)"
    problems = validate(manifest)
    n = len(manifest["ac_synthesis"].get("final_acs", []) or [])
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"AcLanguagePolicy: {status} ({n} final AC(s))"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(description="UAC language & readability policy gate (UACFIX-LANGUAGE-01)")
    ap.add_argument("--manifest")
    args = ap.parse_args()
    manifest = {}
    if args.manifest:
        with open(args.manifest, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    print(summarize(manifest))
    return 0 if not validate(manifest) else 1


if __name__ == "__main__":
    raise SystemExit(main())
