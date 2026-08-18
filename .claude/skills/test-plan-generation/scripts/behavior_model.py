"""BehaviorModelBuilder support - a structured behavior model + its validation.

WHY THIS EXISTS
---------------
The skill must answer "what is actually happening in the system?" BEFORE it asks
"what should we test?". Today that understanding lives only as in-context prose
(SKILL Phase 2) and is machine-checked only for the DITA dimension. This module
adds a structured, evidence-anchored BehaviorModel that Claude records in the
evidence manifest (`behavior_model` block) and that `run_gates.py` validates, so
raw retrieved chunks remain EVIDENCE and never stand in for behavioral understanding.

It is deliberately generic: it contains no domain/construct/Jira-specific rules
(no "guidesParentMaps", no element names). It only enforces structural and
evidence discipline plus one domain-agnostic completeness rule: if the model
describes changing or removing persistent state, it must also identify (or
explicitly flag as unknown) the path that WRITES that state - so a delete/cleanup
ticket cannot be modeled without investigating what created the state.

Stdlib only. Mirrors the dataclass/validate pattern of
`semantic_relationship_explorer.py` (no `from __future__ import annotations`, so
dataclass fields resolve under the skill's importlib loader).
"""

from dataclasses import dataclass, field
from typing import Any


# Authority layer that grounds a behavioral fact - the plan must know which source
# supports each conclusion so evidence is never conflated with inference. Superset
# of the semantic explorer's layers (this model spans all ticket types, not DITA).
AUTHORITY_LAYERS = (
    "JIRA",
    "AEM_GUIDES_DOC",
    "EXPERIENCE_LEAGUE",
    "DITA_SPEC",
    "DITA_OT",
    "CURRENT_IMPLEMENTATION",
    "EXISTING_AUTOMATION",
    "HISTORICAL_BEHAVIOR",
)

# The list-valued fields of a BehaviorModel (all optional; unknown stays unknown).
MODEL_LIST_FIELDS = (
    "trigger", "operations",
    "inputs", "outputs",
    "affected_state",
    "producers", "processors", "consumers",
    "write_paths", "read_paths", "update_paths", "remove_paths", "recompute_paths",
    "configuration_branches", "fallback_paths",
    "execution_modes", "publishing_modes",
    "versioned_models",
    "side_effects",
    "constraints", "unknowns",
    "evidence_ids",
)

# Fields that describe MUTATION of persistent/derived state.
_STATE_MUTATION_FIELDS = ("update_paths", "remove_paths", "recompute_paths")
# Fields that identify what CREATES the state.
_STATE_WRITER_FIELDS = ("write_paths", "producers")
# Domain-agnostic lifecycle verbs (generic reasoning about state, not a Jira answer).
_LIFECYCLE_VERBS = (
    "delete", "remove", "cleanup", "clean up", "purge", "update", "recompute",
    "reconcile", "clear", "invalidate", "regenerate",
)


@dataclass
class BehaviorFact:
    """One evidence-anchored behavioral fact. A fact without evidence is inference."""
    fact: str
    evidence_ids: list = field(default_factory=list)
    authority: str = ""
    confidence: float = 0.0

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            return cls(fact="", evidence_ids=[], authority="", confidence=0.0)
        return cls(
            fact=data.get("fact", ""),
            evidence_ids=list(data.get("evidence_ids", []) or []),
            authority=data.get("authority", ""),
            confidence=float(data.get("confidence", 0.0) or 0.0),
        )


@dataclass
class BehaviorModel:
    trigger: list = field(default_factory=list)
    operations: list = field(default_factory=list)
    inputs: list = field(default_factory=list)
    outputs: list = field(default_factory=list)
    affected_state: list = field(default_factory=list)
    producers: list = field(default_factory=list)
    processors: list = field(default_factory=list)
    consumers: list = field(default_factory=list)
    write_paths: list = field(default_factory=list)
    read_paths: list = field(default_factory=list)
    update_paths: list = field(default_factory=list)
    remove_paths: list = field(default_factory=list)
    recompute_paths: list = field(default_factory=list)
    configuration_branches: list = field(default_factory=list)
    fallback_paths: list = field(default_factory=list)
    execution_modes: list = field(default_factory=list)
    publishing_modes: list = field(default_factory=list)
    versioned_models: list = field(default_factory=list)
    side_effects: list = field(default_factory=list)
    constraints: list = field(default_factory=list)
    unknowns: list = field(default_factory=list)
    evidence_ids: list = field(default_factory=list)
    facts: list = field(default_factory=list)          # list[BehaviorFact]
    behavior_chains: list = field(default_factory=list)  # list[list[str]] multi-hop paths
    confidence: float = 0.0

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        kwargs = {}
        for f in MODEL_LIST_FIELDS:
            kwargs[f] = list(data.get(f, []) or [])
        kwargs["behavior_chains"] = list(data.get("behavior_chains", []) or [])
        kwargs["confidence"] = float(data.get("confidence", 0.0) or 0.0)
        kwargs["facts"] = [BehaviorFact.from_dict(x) for x in (data.get("facts", []) or [])]
        return cls(**kwargs)


def _mentions_lifecycle_op(model):
    text = " ".join(str(x) for x in (model.trigger + model.operations)).lower()
    return any(verb in text for verb in _LIFECYCLE_VERBS)


def _writer_flagged_unknown(model):
    for u in model.unknowns:
        low = str(u).lower()
        if "writ" in low or "creat" in low or "produc" in low or "origin" in low:
            return True
    return False


def validate_behavior_model(data):
    """Return a list of problem strings for a manifest `behavior_model` block.

    Empty list == valid. Enforces structure, evidence discipline on facts, a
    non-empty model, confidence range, and the state-lifecycle completeness rule.
    """
    problems = []
    if not isinstance(data, dict):
        return ["behavior_model must be a JSON object"]

    # List fields must be lists.
    for f in MODEL_LIST_FIELDS + ("facts", "behavior_chains"):
        if f in data and not isinstance(data[f], list):
            problems.append(f"behavior_model.{f} must be a list")

    model = BehaviorModel.from_dict(data)

    # Confidence range.
    if not (0.0 <= model.confidence <= 1.0):
        problems.append(f"behavior_model.confidence {model.confidence} must be between 0.0 and 1.0")

    # The model must actually say something (unknown is allowed, emptiness is not).
    has_shape = bool(
        model.trigger and (model.operations or model.inputs or model.outputs
                           or model.affected_state or model.consumers or model.processors)
    )
    if not has_shape:
        problems.append(
            "behavior_model is effectively empty - populate at least `trigger` plus one of "
            "operations/inputs/outputs/affected_state/consumers/processors (unknowns may stay in `unknowns`)"
        )

    # Evidence discipline: every stated fact must carry evidence + a known authority.
    for i, fct in enumerate(model.facts):
        tag = f"behavior_model.facts[{i}]"
        if not fct.fact:
            problems.append(f"{tag}: missing 'fact' text")
        if not fct.evidence_ids:
            problems.append(
                f"{tag}: a behavioral fact has no evidence_ids - a fact without evidence is inference, "
                f"move it to `unknowns` or attach evidence"
            )
        if fct.authority not in AUTHORITY_LAYERS:
            problems.append(
                f"{tag}: authority '{fct.authority}' must be one of {', '.join(AUTHORITY_LAYERS)}"
            )
        if not (0.0 <= fct.confidence <= 1.0):
            problems.append(f"{tag}: confidence {fct.confidence} must be between 0.0 and 1.0")

    # State-lifecycle completeness (domain-agnostic): if the model changes/removes
    # persistent state (or its trigger/operations use a lifecycle verb), it must also
    # identify what WRITES that state, or explicitly flag the writer as unknown.
    mutates_state = any(getattr(model, f) for f in _STATE_MUTATION_FIELDS)
    writer_known = any(getattr(model, f) for f in _STATE_WRITER_FIELDS)
    if (mutates_state or _mentions_lifecycle_op(model)) and not writer_known and not _writer_flagged_unknown(model):
        problems.append(
            "behavior_model describes changing/removing state (or a delete/cleanup/recompute operation) but "
            "does not identify what WRITES that state - add write_paths/producers, or record the missing "
            "writer in `unknowns` (a cleanup problem must also investigate the path that creates the state)"
        )

    return problems


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("behavior_model"), dict)


def summarize(data):
    model = BehaviorModel.from_dict(data)
    problems = validate_behavior_model(data)
    lines = [f"BehaviorModel: {'VALID' if not problems else 'INVALID'} (confidence {model.confidence})"]
    populated = [f for f in MODEL_LIST_FIELDS if getattr(model, f)]
    lines.append("  populated: " + (", ".join(populated) if populated else "(none)"))
    lines.append(f"  facts: {len(model.facts)}  chains: {len(model.behavior_chains)}  unknowns: {len(model.unknowns)}")
    for p in problems:
        lines.append(f"  PROBLEM {p}")
    return "\n".join(lines)
