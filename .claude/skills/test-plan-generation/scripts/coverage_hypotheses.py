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
import hashlib
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

# Reuse discovery axes without replacing their identity with a broader family.
# `dimension` is the v3 family; `implied_dimension_axis` survives for probe coverage.
DISCOVERY_DIMENSION_BY_AXIS = {
    "VALUE_SET_CHANNEL": "CONTRACT_BOUNDARY", "CODE_PATH_CONSUMER": "CONSUMER",
    "OUTPUT_PRESET": "PUBLISHING_MODE", "TOPIC_TYPE": "TYPE_ABSTRACTION",
    "TERMINAL_STATE": "STATE_PARTITION", "LIFECYCLE": "LIFECYCLE",
    "CONFIG_BRANCH": "CONFIGURATION", "PERMISSION_ROLE": "STATE_PARTITION",
    "MIGRATION_PATH": "BACKWARD_COMPATIBILITY", "NEGATIVE_BOUNDARY": "STATE_PARTITION",
    "ENTRY_POINT": "CONTRACT_BOUNDARY", "REPRO_DIMENSION": "NFR_RISK",
    "DOWNSTREAM_REGRESSION": "DOWNSTREAM_REGRESSION",
}

# All explorers run; only evidence-backed signals emit candidates. These are
# questions about supplied model relationships, never lists of product features.
EXPLORATION_FIELDS = {
    "CONTRACT_BOUNDARY": ("trigger", "inputs", "constraints"),
    "CONSUMER": ("consumers", "downstream_decision_consumers", "shared_processors"),
    "STATE_PARTITION": ("affected_state", "fallback_paths", "error_paths"),
    "TYPE_ABSTRACTION": ("capabilities",),
    "REFERENCE_ARTIFACT": ("generated_artifacts", "artifact_shapes"),
    "DITA_SEMANTIC_DEPENDENCY": (),
    "LIFECYCLE": ("write_paths", "read_paths", "update_paths", "remove_paths", "recompute_paths"),
    "CONFIGURATION": ("configuration_branches", "configuration_dependencies"),
    "PUBLISHING_MODE": ("publishing_modes", "execution_modes"),
    "NFR_RISK": (),
    "BACKWARD_COMPATIBILITY": ("versioned_models", "deployment_modes"),
    "DOWNSTREAM_REGRESSION": ("side_effects", "processors"),
}
_FACT_SIGNALS = {
    "TYPE_ABSTRACTION": ("interface", "superclass", "polymorphic", "supported types", "generic model"),
    "REFERENCE_ARTIFACT": ("reference", "artifact"),
    "NFR_RISK": ("bulk", "recursive", "large collection", "many references", "backlog", "per-reference"),
}


def generate_from_model(manifest):
    """Return grounded exploration candidates and a trace of every family check.

    Claude authors the model from inspected evidence. Python enumerates questions
    over that model; it cannot supply facts, verification verdicts, or ACs.
    """
    model = manifest.get("behavior_model", {}) if isinstance(manifest, dict) else {}
    model = model if isinstance(model, dict) else {}
    raw_facts = model.get("facts", [])
    facts = [f for f in (raw_facts if isinstance(raw_facts, list) else []) if isinstance(f, dict)
             and isinstance(f.get("fact"), str) and f["fact"].strip()
             and isinstance(f.get("evidence_ids"), list) and f["evidence_ids"]
             and all(isinstance(e, str) and e.strip() for e in f["evidence_ids"])
             and isinstance(f.get("authority"), str) and f["authority"].strip()]
    evidence_ids = sorted({eid for f in facts for eid in f["evidence_ids"]})
    candidates, trace = [], []
    for dimension, fields in EXPLORATION_FIELDS.items():
        basis = []
        if facts:
            for name in fields:
                values = model.get(name)
                if isinstance(values, list):
                    for value in values:
                        if isinstance(value, str) and value.strip():
                            basis.append(f"behavior_model.{name}: {value.strip()}")
                        elif isinstance(value, dict) and isinstance(value.get("name"), str):
                            basis.append(f"behavior_model.{name}: {value['name']}")
            for fact in facts:
                if (dimension == "DITA_SEMANTIC_DEPENDENCY"
                    and fact["authority"] in {"DITA_SPEC", "DITA_OT"}) or any(
                    token in fact["fact"].casefold() for token in _FACT_SIGNALS.get(dimension, ())
                ):
                    basis.append(f"behavior_model.fact: {fact['fact']}")
        basis = list(dict.fromkeys(basis))
        trace.append({"generator": dimension,
                      "status": "ACTIVATED" if basis else "NO_GROUNDED_SIGNAL",
                      "technical_basis": basis})
        # One representative per family/model neighborhood, no Cartesian product.
        # Claude may split independent consumers after inspecting applicability.
        if basis:
            key = f"EXPLORER:{dimension}:" + hashlib.sha256(
                "\n".join(sorted(basis)).encode("utf-8")
            ).hexdigest()[:16]
            candidates.append({
                "hypothesis_id": "", "dimension": dimension,
                "candidate": f"Investigate {dimension.lower().replace('_', ' ')} for {basis[0]}",
                "reason": "An inspected behavior-model relationship activates this exploration family.",
                "technical_basis": basis, "current_evidence": evidence_ids,
                "generator": dimension, "equivalence_key": key,
                "status": "INVESTIGATION_CANDIDATE", "requires_more_evidence": True,
                "confidence": 0.0, "authority_class": "SUPPORTING_DISCOVERY",
            })
    return {"candidates": candidates, "explorers": trace}

# A hypothesis starts as a candidate and only later (Prompt 4) reaches a terminal
# status. Mirrors semantic_relationship_explorer's status machine.
CANDIDATE_STATUS = "INVESTIGATION_CANDIDATE"
TERMINAL_STATUSES = ("CONFIRMED", "INFERRED_HIGH_CONFIDENCE", "REJECTED", "UNRESOLVED")
ALL_STATUSES = (CANDIDATE_STATUS, *TERMINAL_STATUSES)

# Behavioural distance from the affected behaviour, most-direct first. Ranking uses
# this, NOT keyword similarity / retrieved-chunk count / model confidence alone.
BEHAVIORAL_DISTANCES = ("DIRECT", "ONE_HOP", "MULTI_HOP", "ANALOGOUS", "GENERIC_REGRESSION")


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
    # BehavioralRelevancePrioritizer (Prompt 8) fields - how directly this governs the
    # affected behaviour, so a direct dependency (e.g. a controlling attribute) is
    # investigated BEFORE distant regression candidates. Optional; default GENERIC.
    behavioral_distance: str = ""
    relevance_score: float = 0.0
    priority_reason: str = ""
    same_code_path: bool = False
    direct_semantic_dependency: bool = False

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
    if h.behavioral_distance and h.behavioral_distance not in BEHAVIORAL_DISTANCES:
        problems.append(f"{tag}: behavioral_distance '{h.behavioral_distance}' must be one of {', '.join(BEHAVIORAL_DISTANCES)}")
    if not (0.0 <= h.relevance_score <= 1.0):
        problems.append(f"{tag}: relevance_score {h.relevance_score} must be between 0.0 and 1.0")
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


def validate_coverage_block(data, *, require_ids=False):
    """Validate a manifest `coverage_hypotheses` list. Returns problem strings.

    Enforces per-hypothesis structure/evidence discipline AND that the recorded set
    is already collapsed (no un-collapsed equivalent candidates = no Cartesian
    explosion in the plan's coverage set)."""
    problems = []
    if not isinstance(data, list):
        return ["coverage_hypotheses must be a JSON list"]
    if any(not isinstance(x, dict) for x in data):
        return ["coverage_hypotheses entries must be objects"]
    ids = set()
    for item in data:
        hid = item.get("hypothesis_id")
        if require_ids and (not isinstance(hid, str) or not hid.strip() or hid in ids):
            problems.append("coverage_hypotheses requires unique non-empty hypothesis_id values")
        elif isinstance(hid, str) and hid.strip():
            ids.add(hid)
        for name in ("dimension", "candidate", "reason", "status", "equivalence_key", "behavioral_distance"):
            if name in item and not isinstance(item[name], str):
                problems.append(f"hypothesis {hid!r}: {name} must be a string")
        for name in ("confidence", "relevance_score"):
            if name in item and (isinstance(item[name], bool) or not isinstance(item[name], (int, float))):
                problems.append(f"hypothesis {hid!r}: {name} must be numeric")
        basis = item.get("technical_basis")
        if not isinstance(basis, list) or not basis or not all(
            isinstance(value, str) and value.strip() for value in basis
        ):
            problems.append(f"hypothesis {hid!r}: no technical_basis or malformed signals - supply a non-empty list of technical signals")
    if problems:
        return problems
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
