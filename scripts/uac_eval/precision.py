"""Precision signal for the UAC eval.

Motivation. The eval scores COVERAGE (recall) against the human gold, plus a
hallucination count. Nothing measures the failure class reviewers actually hit on
real tickets: over-decomposition (one behaviour split into many ACs), redundant /
restated ACs, and verbose per-AC prose. Because the only rewarded axis is coverage,
the harness quietly incentivises OVER-production of ACs - the exact drift reviewers
penalise. This module adds a precision axis so the combined score stops rewarding
recall alone.

Two layers, kept separate on purpose:

  1. deterministic (this file) - mechanical, judge-free metrics of an AC block:
     AC count, collapse excess (ACs that fit an existing near-duplicate cluster),
     lexical-redundancy pairs, verbose-AC count, and a gentle high-volume sanity
     penalty. These are cheap, reproducible, and not subject to LLM variance.

  2. judge-side (judge.py) - the reviewer-style semantic precision the regex cannot
     see (an AC that is an INSTANCE-OF another, wrong altitude). Reported alongside.

`precision_pct` is a 0-100 deterministic score (100 = tight, well-factored ACs).
`combined_pct` folds coverage and precision into one number via harmonic mean (an
F1 over recall and precision) so a plan cannot win by dumping ACs. Standard lib only.
"""
from __future__ import annotations

import re

# An AC line: "AC-01", "AC 1", "- AC-3:", numbered "1." bullets used as ACs.
_AC_LABEL_RE = re.compile(r"\bAC[-\s]?(\d+)\b", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.*\S)\s*$")
# Words that do not distinguish two ACs when measuring lexical overlap.
_STOP = frozenset(
    "the a an and or of to in on for is are be that this it with as by from at "
    "should must will shall verify ensure when then given user should_be able "
    "not no if into their its each any all both which while".split()
)

# Tuneable thresholds. The lexical threshold must stay aligned with the skill's
# coverage_forcing._validate_ac_redundancy gate.
REDUNDANCY_JACCARD = 0.6   # two ACs sharing >=60% of content words are near-duplicates
SANITY_AC_CEILING = 25     # breadth is allowed; only extreme dumps get a gentle count penalty
VERBOSE_WORDS = 45         # a single AC longer than this reads as a paragraph, not a criterion

COLLAPSE_EXCESS_PENALTY = 4
REDUNDANCY_PAIR_PENALTY = 6
VERBOSE_AC_PENALTY = 3
SANITY_EXCESS_PENALTY = 1


def _extract_ac_block(text: str) -> tuple[str, bool]:
    """Return (acceptance-criteria section, found).

    The canonical runtime titles its promoted sign-off criteria `## Acceptance
    contract`; baseline drafts may use `Acceptance criteria`. This isolates that ONE
    section and terminates at the next heading.

    CRITICAL: when no acceptance-criteria section exists (e.g. a blocked runtime plan
    that never produced a contract), return ("", False) - do NOT fall back to the whole
    document. The old whole-doc fallback counted every bullet in the plan (issue
    understanding, log snippets, coverage sections) as an "AC", producing absurd counts
    like 178. A plan with no contract has no ACs to score, and the caller must EXCLUDE it
    from precision rather than penalise or reward it."""
    if not text:
        return "", False
    m = re.search(
        r"(?:^|\n)\s*(?:#{1,4}\s*|\*\*)\s*"
        r"(?:Proposed acceptance contract|Acceptance contract|Acceptance criteria)\b.*?"
        r"(?=\n\s*(?:#{1,4}\s*|\*\*)\s*[A-Z][A-Za-z /]{2,40}\b|\Z)",
        text, re.S | re.I,
    )
    if m:
        return m.group(0).strip(), True
    return "", False


def _ac_items(block: str) -> list[str]:
    """Return the text of each acceptance-criterion line in the block.

    Prefers explicit AC-## labelled lines; falls back to bullet/numbered lines when
    the plan does not label them. One line per criterion; joins wrapped continuations
    is out of scope (criteria are single bullets in this house style)."""
    items: list[str] = []
    labelled = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _AC_LABEL_RE.search(line):
            labelled.append(line)
    if labelled:
        return labelled
    for raw in block.splitlines():
        m = _BULLET_RE.match(raw)
        if m:
            items.append(m.group(1).strip())
    return items


def _content_words(s: str) -> set[str]:
    toks = re.findall(r"[a-zA-Z][a-zA-Z0-9_.]+", s.lower())
    return {t for t in toks if t not in _STOP and len(t) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _redundancy_shape(word_sets: list[set[str]]) -> tuple[int, int]:
    """Return (semantic cluster count, near-duplicate pair count).

    Each Jaccard match is an undirected edge. Connected components form semantic
    clusters so transitive near-duplicates are counted as one collapsible behavior.
    Pair reporting remains the exact all-pairs count used by the previous scorer.
    """
    count = len(word_sets)
    if count == 0:
        return 0, 0

    parents = list(range(count))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    redundancy_pairs = 0
    for left in range(count):
        for right in range(left + 1, count):
            if _jaccard(word_sets[left], word_sets[right]) >= REDUNDANCY_JACCARD:
                redundancy_pairs += 1
                union(left, right)

    clusters = len({find(index) for index in range(count)})
    return clusters, redundancy_pairs


def analyze_ac(text: str) -> dict:
    """Deterministic precision metrics for a plan's acceptance-criteria block.

    When the plan has no acceptance-criteria section, returns ac_section_found=False and
    precision_pct=None so the caller EXCLUDES it from precision scoring (it is a
    'no contract produced' case, not an over-decomposed one)."""
    block, found = _extract_ac_block(text)
    if not found:
        return {
            "ac_count": 0,
            "unique_ac_labels": 0,
            "semantic_clusters": 0,
            "over_decomposition": 0,
            "sanity_excess": 0,
            "redundancy_pairs": 0,
            "verbose_ac_count": 0,
            "avg_ac_words": 0.0,
            "precision_pct": None,
            "ac_section_found": False,
        }
    items = _ac_items(block)
    n = len(items)
    # Keep label cardinality as a diagnostic, but decomposition is about acceptance
    # items and their semantic clusters, not label formatting or a flat count cap.
    labels = {m.lower() for line in items for m in _AC_LABEL_RE.findall(line)}
    unique_ac = len(labels) if labels else n

    word_sets = [_content_words(it) for it in items]
    semantic_clusters, redundancy_pairs = _redundancy_shape(word_sets)

    word_counts = [len(re.findall(r"\w+", it)) for it in items]
    verbose = sum(1 for w in word_counts if w > VERBOSE_WORDS)
    avg_words = round(sum(word_counts) / n, 1) if n else 0.0

    over_decomp = max(0, n - semantic_clusters)
    sanity_excess = max(0, n - SANITY_AC_CEILING)

    # Precision score: start at 100, deduct for each drift class, floor at 0.
    #   collapse excess: 4 pts per AC that can collapse into an existing cluster
    #   redundancy: 6 pts per near-duplicate pair (reviewers flag these hard)
    #   verbosity: 3 pts per over-long AC
    #   sanity excess: 1 pt per AC above 25, independent of semantic redundancy
    penalty = (
        COLLAPSE_EXCESS_PENALTY * over_decomp
        + REDUNDANCY_PAIR_PENALTY * redundancy_pairs
        + VERBOSE_AC_PENALTY * verbose
        + SANITY_EXCESS_PENALTY * sanity_excess
    )
    precision_pct = max(0, 100 - penalty)

    return {
        "ac_count": n,
        "unique_ac_labels": unique_ac,
        "semantic_clusters": semantic_clusters,
        "over_decomposition": over_decomp,
        "sanity_excess": sanity_excess,
        "redundancy_pairs": redundancy_pairs,
        "verbose_ac_count": verbose,
        "avg_ac_words": avg_words,
        "precision_pct": precision_pct,
        "ac_section_found": True,
    }


def combined_pct(coverage_pct: float | None, precision_pct: float | None) -> float | None:
    """Harmonic mean (F1) of coverage and precision, so neither axis wins alone."""
    if coverage_pct is None or precision_pct is None:
        return None
    c, p = float(coverage_pct), float(precision_pct)
    if c <= 0 or p <= 0:
        return 0.0
    return round(2 * c * p / (c + p), 1)


def _require(condition: bool, details: object) -> None:
    """Keep self-test checks active even when Python runs with optimization."""
    if not condition:
        raise AssertionError(details)


def run_self_tests() -> None:
    tight = (
        "## Acceptance criteria\n"
        "- AC-1: Translation succeeds for content moved from en to en_us.\n"
        "- AC-2: The move preserves the language-UUID path mapping.\n"
        "- AC-3: A blank keydef key surfaces an error indication, not a fallback label.\n"
    )
    t = analyze_ac(tight)
    _require(t["ac_count"] == 3, t)
    _require(t["over_decomposition"] == 0 and t["redundancy_pairs"] == 0, t)
    _require(t["precision_pct"] == 100, t)

    # 20 distinctly-worded ACs -> legitimate breadth, no collapse penalty.
    distinct = [
        "conref resolution keeps the source topic title",
        "keyref target displays its own navtitle",
        "figure caption renders above the image",
        "table summary reads from the volume attribute",
        "glossary entry sorts alphabetically within its group",
        "reltable link surfaces on both endpoints",
        "map metadata propagates to child topics on publish",
        "profile filtering hides excluded audience content",
        "index marker collates under the correct letter heading",
        "bookmap frontmatter precedes the first chapter",
        "chunk merge produces one output file per collection",
        "conditional text respects the ditaval flag",
        "xref to a task step numbers the referenced step",
        "footnote body appears once per printed page",
        "shortdesc becomes the search-result abstract",
        "related-links block sits after the topic body",
        "warehouse metadata retains the original creator timestamp",
        "review comments remain pinned to the selected range after reopen",
        "subject scheme validation rejects an invalid controlled value",
        "image renditions preserve alternative text in HTML output",
    ]
    many = "## Acceptance criteria\n" + "".join(
        f"- AC-{i}: The output verifies that {d}.\n" for i, d in enumerate(distinct, 1)
    )
    m = analyze_ac(many)
    _require(m["ac_count"] == 20 and m["unique_ac_labels"] == 20, m)
    _require(m["semantic_clusters"] == 20, m)
    _require(m["over_decomposition"] == 0, m)
    _require(m["redundancy_pairs"] == 0, m)
    _require(m["sanity_excess"] == 0, m)
    _require(m["precision_pct"] == 100, m)

    # 20 ACs describing only eight behaviors -> 12 collapsible ACs. Four
    # clusters contain three copies and four contain two copies (16 matching pairs).
    clustered_behaviors = [
        "duplicate detection rejects the repeated upload asset",
        "timeline version history records the replaced binary asset",
        "processing profile metadata applies after the upload completes",
        "translation status remains unchanged after source synchronization",
        "review comments stay attached after the topic refresh",
        "conditional filtering excludes the configured audience value",
        "cross reference labels resolve from the target title",
        "published navigation preserves the configured topic order",
    ]
    cluster_sizes = [3, 3, 3, 3, 2, 2, 2, 2]
    clustered_items: list[str] = []
    ac_number = 1
    for behavior, size in zip(clustered_behaviors, cluster_sizes):
        for _ in range(size):
            clustered_items.append(f"- AC-{ac_number}: {behavior}.\n")
            ac_number += 1
    clustered = analyze_ac("## Acceptance criteria\n" + "".join(clustered_items))
    _require(clustered["ac_count"] == 20, clustered)
    _require(clustered["semantic_clusters"] == 8, clustered)
    _require(clustered["over_decomposition"] == 12, clustered)
    _require(clustered["redundancy_pairs"] == 16, clustered)
    _require(clustered["precision_pct"] == 0, clustered)

    # Similarity grouping is transitive: A~B and B~C form one behavior cluster
    # even when A and C do not directly meet the threshold.
    transitive_sets = [
        {"alpha", "bravo", "charlie", "delta"},
        {"alpha", "bravo", "charlie", "delta", "echo", "foxtrot"},
        {"charlie", "delta", "echo", "foxtrot"},
    ]
    _require(_redundancy_shape(transitive_sets) == (1, 2), "transitive clustering failed")
    threshold_sets = [
        {"alpha", "bravo", "charlie"},
        {"alpha", "bravo", "charlie", "delta", "echo"},
    ]
    _require(_redundancy_shape(threshold_sets) == (1, 1), "Jaccard 0.6 must be inclusive")

    # Extreme but non-redundant breadth gets only the separate gentle ceiling penalty.
    at_ceiling = "## Acceptance criteria\n" + "".join(
        f"- AC-{i}: token{i} action{i} output{i} state{i}.\n" for i in range(1, 26)
    )
    ceiling = analyze_ac(at_ceiling)
    _require(ceiling["semantic_clusters"] == 25 and ceiling["over_decomposition"] == 0, ceiling)
    _require(ceiling["sanity_excess"] == 0 and ceiling["precision_pct"] == 100, ceiling)

    very_broad = "## Acceptance criteria\n" + "".join(
        f"- AC-{i}: token{i} action{i} output{i} state{i}.\n" for i in range(1, 27)
    )
    vb = analyze_ac(very_broad)
    _require(vb["semantic_clusters"] == 26 and vb["over_decomposition"] == 0, vb)
    _require(vb["sanity_excess"] == 1 and vb["precision_pct"] == 99, vb)

    pathological = "## Acceptance criteria\n" + "".join(
        f"- AC-{i}: path{i} trigger{i} result{i} state{i}.\n" for i in range(1, 41)
    )
    ph = analyze_ac(pathological)
    _require(ph["semantic_clusters"] == 40 and ph["over_decomposition"] == 0, ph)
    _require(ph["sanity_excess"] == 15 and ph["precision_pct"] == 85, ph)

    # Two near-duplicate ACs -> a redundancy pair.
    dup = (
        "## Acceptance criteria\n"
        "- AC-1: The cross reference label excludes the footnote callout text.\n"
        "- AC-2: The cross reference label must exclude footnote callout text.\n"
    )
    d = analyze_ac(dup)
    _require(d["semantic_clusters"] == 1 and d["over_decomposition"] == 1, d)
    _require(d["redundancy_pairs"] == 1, d)
    _require(d["precision_pct"] == 90, d)

    # No acceptance-criteria section -> excluded, NOT counted as 178 bullets.
    no_ac = (
        "## Issue understanding\n- Tenant IMS Org ID: 56734\n- Relevant Log Snippets\n"
        "- Customer Context\n- Business Impact\n"
        "## Semantic coverage\n- some coverage bullet\n- another coverage bullet\n"
    )
    na = analyze_ac(no_ac)
    _require(na["ac_section_found"] is False, na)
    _require(na["precision_pct"] is None and na["ac_count"] == 0, na)

    # A real acceptance-contract section terminates at the next heading.
    scoped = (
        "## Issue understanding\n- lots\n- of\n- noise\n- bullets\n- here\n"
        "## Acceptance contract\n"
        "- AC-1: Translation succeeds for moved content.\n"
        "- AC-2: The move preserves the language-UUID path mapping.\n"
        "## Semantic coverage\n- ignored\n- ignored2\n- ignored3\n"
    )
    s = analyze_ac(scoped)
    _require(s["ac_section_found"] is True and s["ac_count"] == 2, s)

    _require(combined_pct(90, 60) == 72.0, "combined score mismatch")
    _require(combined_pct(100, 0) == 0.0, "zero precision must produce zero combined")
    _require(combined_pct(None, 50) is None, "missing coverage must stay unscored")
    print("precision self-tests: PASS")


if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", help="a plan markdown file to score")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        run_self_tests()
        raise SystemExit(0)
    if args.file:
        print(json.dumps(analyze_ac(Path(args.file).read_text(encoding="utf-8")), indent=2))
