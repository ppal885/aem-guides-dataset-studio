"""CoverageHypothesisGenerator support - generic coverage dimensions + hypotheses.

WHY THIS EXISTS
---------------
Phase-2 gives us a structured BehaviorModel ("what is happening"). This module is
the disciplined bridge to "what might need testing" WITHOUT jumping to test cases.
Its philosophy is strict:

    technical evidence -> potential missing dimension -> INVESTIGATION_CANDIDATE

Never "AI thinks it may matter -> add a test". A candidate is a hypothesis to be
explored and verified later (Prompt 4); it is NOT an Acceptance Criterion.

The DITA semantic explorer (`semantic_relationship_explorer.py`) is the exemplar
for the DITA_SEMANTIC_DEPENDENCY dimension; this module generalizes the same
pattern - a controlled dimension vocabulary, evidence-anchored hypothesis records,
a status machine that starts at INVESTIGATION_CANDIDATE, and Cartesian-collapse so
one construct/entity with many related facets does not explode into an N-way matrix.

It contains NO domain/construct/Jira-specific rules: dimensions are generic and
the concrete candidates are always supplied from evidence at run time.

Stdlib only. Same dataclass/validate pattern (no future-annotations import).
"""

from dataclasses import dataclass, field
from typing import Any


# Generic coverage dimensions. These are reasoning CATEGORIES, not construct pairs
# or ticket answers. Which ones activate is decided per-Jira from the BehaviorModel.
COVERAGE_DIMENSIONS = (
    "CONTRACT_BOUNDARY",
    "CONSUMER",
    "CONSUMER_POLICY",
    "STATE_PARTITION",
    "TYPE_ABSTRACTION",
    "REFERENCE_ARTIFACT",
    "DITA_SEMANTIC_DEPENDENCY",
    "LIFECYCLE",
    "CONFIGURATION",
    "PUBLISHING_MODE",
    "NFR_RISK",
    "BACKWARD_COMPATIBILITY",
    "DOWNSTREAM_REGRESSION",
)

# A hypothesis starts as a candidate and only later (Prompt 4) reaches a terminal
# status. Mirrors semantic_relationship_explorer's status machine.
CANDIDATE_STATUS = "INVESTIGATION_CANDIDATE"
TERMINAL_STATUSES = ("CONFIRMED", "INFERRED_HIGH_CONFIDENCE", "REJECTED", "UNRESOLVED")
ALL_STATUSES = (CANDIDATE_STATUS, *TERMINAL_STATUSES)


@dataclass
class CoverageHypothesis:
    hypothesis_id: str = ""
    dimension: str = ""
    candidate: str = ""
    reason: str = ""
    technical_basis: list = field(default_factory=list)   # the technical signals that justify it
    current_evidence: list = field(default_factory=list)  # evidence ids inspected so far
    activated_patterns: list = field(default_factory=list)
    status: str = CANDIDATE_STATUS
    requires_more_evidence: bool = True
    confidence: float = 0.0
    equivalence_key: str = ""  # hypotheses sharing this collapse to one representative

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


def validate_hypothesis(h):
    """Validate one coverage hypothesis. Returns problem strings."""
    problems = []
    tag = f"hypothesis '{h.hypothesis_id or h.candidate or '?'}'"
    if h.dimension not in COVERAGE_DIMENSIONS:
        problems.append(f"{tag}: dimension '{h.dimension}' is not one of {', '.join(COVERAGE_DIMENSIONS)}")
    if not h.candidate:
        problems.append(f"{tag}: missing 'candidate' (the potential missing dimension to investigate)")
    if not h.reason:
        problems.append(f"{tag}: missing 'reason'")
    # The core discipline: a candidate must come from a technical signal, not a hunch.
    if not h.technical_basis:
        problems.append(
            f"{tag}: no technical_basis - a coverage candidate must be justified by a technical signal "
            f"(a behavior fact, code path, config branch, consumer, spec relationship, or scale signal), "
            f"not speculation"
        )
    if h.status not in ALL_STATUSES:
        problems.append(f"{tag}: status '{h.status}' is not one of {', '.join(ALL_STATUSES)}")
    if not isinstance(h.requires_more_evidence, bool):
        problems.append(f"{tag}: requires_more_evidence must be a boolean")
    if not (0.0 <= h.confidence <= 1.0):
        problems.append(f"{tag}: confidence {h.confidence} must be between 0.0 and 1.0")
    return problems


def collapse_hypotheses(hypotheses):
    """Cartesian-explosion protection. Two hypotheses collapse when they share the
    same dimension and the same equivalence_key (or, absent a key, the same
    normalized candidate). Returns (kept_representatives, collapsed_duplicates)."""
    kept, collapsed = [], []
    seen = set()
    for h in hypotheses:
        obj = h if isinstance(h, CoverageHypothesis) else CoverageHypothesis.from_dict(h)
        key = (obj.dimension, (obj.equivalence_key or obj.candidate).strip().lower())
        if key in seen:
            collapsed.append(h)
        else:
            seen.add(key)
            kept.append(h)
    return kept, collapsed


def validate_coverage_block(data):
    """Validate a manifest `coverage_hypotheses` list. Returns problem strings.

    Enforces per-hypothesis structure/evidence discipline AND that the recorded set
    is already collapsed (no un-collapsed equivalent candidates = no Cartesian
    explosion in the plan's coverage set)."""
    problems = []
    if not isinstance(data, list):
        return ["coverage_hypotheses must be a JSON list"]
    hyps = [CoverageHypothesis.from_dict(x) for x in data]
    for h in hyps:
        problems.extend(validate_hypothesis(h))
    _, collapsed = collapse_hypotheses(hyps)
    if collapsed:
        # collapsed items are the CoverageHypothesis objects that were passed in
        dims = sorted({(h.dimension, (h.equivalence_key or h.candidate)) for h in collapsed})
        problems.append(
            f"coverage_hypotheses contains {len(collapsed)} equivalent candidate(s) that should collapse to a "
            f"single representative (avoid a Cartesian matrix): {dims}"
        )
    return problems


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("coverage_hypotheses"), list)


def summarize(data):
    problems = validate_coverage_block(data)
    hyps = [CoverageHypothesis.from_dict(x) for x in (data or [])]
    by_dim = {}
    for h in hyps:
        by_dim.setdefault(h.dimension, 0)
        by_dim[h.dimension] += 1
    lines = [f"CoverageHypotheses: {'VALID' if not problems else 'INVALID'} ({len(hyps)} candidate(s))"]
    for d, n in sorted(by_dim.items()):
        lines.append(f"  {d}: {n}")
    for p in problems:
        lines.append(f"  PROBLEM {p}")
    return "\n".join(lines)
