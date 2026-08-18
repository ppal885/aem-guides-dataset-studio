"""BehavioralRelevancePrioritizer (Prompt 8) - rank hypotheses by how DIRECTLY they
govern the affected behaviour, so a direct dependency (e.g. a controlling attribute)
is investigated before distant regression candidates.

WHY THIS EXISTS
---------------
Discovery breadth is not the problem; prioritisation is. A plan can surface
`topichead`, HTML5, and Legacy Sites while missing `locktitle` - the construct
semantically closest to the reported `navtitle` behaviour. This module ranks by
behavioural distance, NOT by keyword similarity, retrieved-chunk count, or model
confidence alone, and enforces the rule:

    A direct/one-hop (HIGH-relevance) governing dependency must be investigated to a
    terminal verdict before the gate can PASS - five low-value regression candidates
    cannot compensate for one unexplored direct semantic dependency.

Generic only: the distance is supplied per hypothesis from evidence, never hardcoded
(no "locktitle == DIRECT" rule). Stdlib only.
"""

# Behavioural distance, most-direct first. Rank index = priority.
DISTANCE_ORDER = ("DIRECT", "ONE_HOP", "MULTI_HOP", "ANALOGOUS", "GENERIC_REGRESSION")
_DISTANCE_RANK = {d: i for i, d in enumerate(DISTANCE_ORDER)}
# HIGH-relevance = the tiers that must be terminal before the gate can pass.
HIGH_RELEVANCE_DISTANCES = frozenset({"DIRECT", "ONE_HOP"})

# The relevance FACTORS, most-governing first (used to justify a distance, and as a
# documented ranking rubric - not a keyword/similarity signal).
RELEVANCE_FACTORS = (
    "DIRECT_SEMANTIC_DEPENDENCY",
    "SAME_BEHAVIORAL_DECISION",
    "SAME_CODE_BRANCH",
    "SAME_STATE_TRANSITION",
    "SAME_DATA_MODEL",
    "SAME_CONSUMER_PATH",
    "SAME_FAILURE_MECHANISM",
    "HISTORICAL_REGRESSION_EVIDENCE",
    "ANALOGOUS_BEHAVIOR",
    "GENERIC_REGRESSION_ONLY",
)

TERMINAL_STATUSES = frozenset({"CONFIRMED", "INFERRED_HIGH_CONFIDENCE", "REJECTED", "UNRESOLVED"})


def _get(h, key, default=None):
    if isinstance(h, dict):
        return h.get(key, default)
    return getattr(h, key, default)


def effective_distance(h):
    """Resolve a hypothesis's behavioural distance. Explicit distance wins; else infer
    a conservative distance from the boolean signals; else GENERIC_REGRESSION."""
    d = (_get(h, "behavioral_distance") or "").strip()
    if d in _DISTANCE_RANK:
        return d
    if _get(h, "direct_semantic_dependency"):
        return "DIRECT"
    if _get(h, "same_code_path"):
        return "ONE_HOP"
    return "GENERIC_REGRESSION"


def is_high_relevance(h):
    return effective_distance(h) in HIGH_RELEVANCE_DISTANCES


def _sort_key(h):
    dist_rank = _DISTANCE_RANK.get(effective_distance(h), len(DISTANCE_ORDER))
    # within the same distance, higher relevance_score first (negated for ascending sort)
    return (dist_rank, -float(_get(h, "relevance_score", 0.0) or 0.0))


def prioritize(hypotheses):
    """Return hypotheses ordered most-directly-governing first (stable within a tier)."""
    return sorted(hypotheses, key=_sort_key)


def _is_terminal(h, verdict_by_id):
    hid = _get(h, "hypothesis_id")
    verdict = verdict_by_id.get(hid)
    if verdict in TERMINAL_STATUSES:
        return True
    # a hypothesis may carry its own terminal status even without a separate verification
    return _get(h, "status") in TERMINAL_STATUSES and _get(h, "status") != "INVESTIGATION_CANDIDATE"


def high_relevance_unresolved(hypotheses, verifications=None):
    """HIGH-relevance (direct/one-hop) hypotheses that have NOT reached a terminal
    verdict. These block the gate regardless of how many low-value ones are done."""
    verdict_by_id = {}
    for v in (verifications or []):
        vid = _get(v, "hypothesis_id")
        if vid:
            verdict_by_id[vid] = _get(v, "verdict")
    return [h for h in hypotheses if is_high_relevance(h) and not _is_terminal(h, verdict_by_id)]


def validate_prioritization(hypotheses):
    """Optional consistency checks on the prioritisation metadata."""
    problems = []
    for h in hypotheses:
        d = (_get(h, "behavioral_distance") or "").strip()
        if d and d not in _DISTANCE_RANK:
            problems.append(f"hypothesis '{_get(h, 'hypothesis_id') or '?'}': behavioral_distance '{d}' is invalid")
        if is_high_relevance(h) and not (_get(h, "priority_reason") or "").strip():
            problems.append(
                f"hypothesis '{_get(h, 'hypothesis_id') or '?'}': a HIGH-relevance (direct/one-hop) hypothesis "
                f"must state a priority_reason (why it directly governs the affected behaviour)"
            )
    return problems


def summarize(hypotheses, verifications=None):
    ordered = prioritize(hypotheses)
    lines = ["Behavioural relevance ranking (most-direct first):"]
    for h in ordered:
        lines.append(f"  [{effective_distance(h)}] {_get(h, 'hypothesis_id')} - {_get(h, 'candidate')}")
    blocked = high_relevance_unresolved(hypotheses, verifications)
    if blocked:
        lines.append("  UNEXPLORED HIGH-RELEVANCE: " + ", ".join(_get(h, "hypothesis_id") for h in blocked))
    return "\n".join(lines)
