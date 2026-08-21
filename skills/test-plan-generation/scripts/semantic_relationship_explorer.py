"""Generic DITA semantic-relationship explorer — model, vocabulary, and gate.

WHY THIS EXISTS
---------------
A recurring weakness of the test-plan skill: it detects the DITA construct a Jira
names explicitly (say ``navtitle``) but never investigates the OTHER constructs
that control, inherit into, resolve, filter, override, or otherwise change that
construct's processing behaviour (say ``@locktitle``, key resolution, or the
map/topic title-precedence chain). Coverage then silently misses the branch that
actually breaks.

The fix must NOT be a growing list of hand-coded pairs (this is the BANNED
anti-pattern, shown here only as an illustration)::

    if navtitle: test_locktitle()   # banned example — do not do this
    if keyref:   test_keyscope()    # banned example — do not do this

That is unscalable and wrong. This module is the scalable alternative: it defines
a GENERIC model of a semantic neighbourhood plus the gate that proves the
neighbourhood was actually explored. Crucially, it contains **no construct->construct
truth table**. Every relationship is supplied as evidence-derived input (from the
evidence manifest's ``dita_semantics`` block, which itself traces each relation to
an authoritative RAG / spec / clone probe). This module only:

  * defines the controlled vocabulary (relation types, authority layers, versions,
    terminal statuses) — a schema, not a mapping;
  * validates that every supplied relation carries semantic evidence;
  * buckets relations into a semantic neighbourhood by relation TYPE (not by
    construct name);
  * turns material relations into coverage hypotheses;
  * collapses equivalent hypotheses so a construct with N related attributes does
    not explode into an N-way Cartesian matrix;
  * evaluates the SemanticCoverageGate: every applicable dimension must end
    COVERED, INVESTIGATED_AND_REJECTED, or UNRESOLVED_AND_EXPOSED, else the gate
    is NEEDS_REVIEW.

Stdlib only. Consumed by run_gates.py and the self-tests; never edits a plan.
"""

from dataclasses import dataclass, field
from typing import Any


# --- Controlled vocabulary (schema, not a construct truth table) -------------

# The smallest correct relation vocabulary. Direction is source -> target, read
# as "<source_construct> <RELATION> <target_construct>". These are relationship
# KINDS; which constructs stand in them is always evidence-supplied, never here.
RELATION_TYPES: dict[str, str] = {
    "CONTROLS": "target's presence/value changes how source is processed",
    "CHANGES_PROCESSING_OF": "source alters the processing path of target",
    "OVERRIDES": "source value takes precedence over target value",
    "FALLS_BACK_TO": "when source is absent/unresolved, target supplies the value",
    "INHERITS_FROM": "source's effective value can be inherited from target (ancestor)",
    "RESOLVES_FROM": "source's effective value is resolved from target",
    "REQUIRES": "source is invalid/unprocessed unless target is present",
    "OPTIONALLY_USES": "source may use target but does not require it",
    "EXCLUDES": "source and target cannot both apply",
    "FILTERED_BY": "source is included/excluded based on target (conditional processing)",
    "SCOPED_BY": "target defines the scope in which source resolves",
    "TARGETS": "source points at target (reference target)",
    "REFERENCES": "source references target (generic reference edge)",
    "CONTAINS": "source structurally contains target",
    "SPECIALIZES": "source is a specialization of target",
    "DERIVES_FROM": "source derives its type/semantics from target",
    "AFFECTS_OUTPUT_OF": "source changes the generated output of target",
}

# Which neighbourhood bucket (from the section-3 JSON shape) a relation TYPE fills.
# This is a fixed relation-type -> bucket schema, analogous to sphere names in the
# AC contract. It is NOT a construct mapping.
RELATION_BUCKET: dict[str, str] = {
    "CONTROLS": "controlling_constructs",
    "CHANGES_PROCESSING_OF": "processing_dependencies",
    "OVERRIDES": "precedence_dependencies",
    "FALLS_BACK_TO": "fallback_dependencies",
    "INHERITS_FROM": "inheritance_dependencies",
    "RESOLVES_FROM": "resolution_dependencies",
    "REQUIRES": "validity_constraints",
    "OPTIONALLY_USES": "dependent_constructs",
    "EXCLUDES": "validity_constraints",
    "FILTERED_BY": "filtering_dependencies",
    "SCOPED_BY": "resolution_dependencies",
    "TARGETS": "reference_dependencies",
    "REFERENCES": "reference_dependencies",
    "CONTAINS": "structural_dependencies",
    "SPECIALIZES": "inheritance_dependencies",
    "DERIVES_FROM": "inheritance_dependencies",
    "AFFECTS_OUTPUT_OF": "processing_dependencies",
}

# Authority layer that supports a conclusion — the plan must know which one grounds
# each relation so DITA-spec intent is never conflated with product implementation.
AUTHORITY_LAYERS = (
    "DITA_SPEC",
    "DITA_OT",
    "AEM_GUIDES_DOC",
    "AEM_GUIDES_IMPLEMENTATION",
    "HISTORICAL_BEHAVIOR",
)

DITA_VERSIONS = ("1.2", "1.3", "both", "unknown")

# A relation begins as a candidate and must reach a terminal status.
CANDIDATE_STATUS = "INVESTIGATION_CANDIDATE"
TERMINAL_STATUSES = ("CONFIRMED", "INFERRED_HIGH_CONFIDENCE", "REJECTED", "UNRESOLVED")
ALL_STATUSES = (CANDIDATE_STATUS, *TERMINAL_STATUSES)

# The neighbourhood buckets, in the section-3 order.
NEIGHBOURHOOD_BUCKETS = (
    "controlling_constructs",
    "dependent_constructs",
    "parent_dependencies",
    "child_dependencies",
    "reference_dependencies",
    "resolution_dependencies",
    "inheritance_dependencies",
    "fallback_dependencies",
    "precedence_dependencies",
    "processing_dependencies",
    "structural_dependencies",
    "filtering_dependencies",
    "validity_constraints",
)


# --- Relation model ----------------------------------------------------------

@dataclass
class SemanticRelation:
    """One evidence-derived edge in the semantic neighbourhood.

    Every field that grounds a conclusion is required: a relation with no evidence
    is rejected (a relation is never asserted just because two constructs appear
    near each other in documentation).
    """

    source_construct: str
    target_construct: str
    relation: str
    dita_version: str = "unknown"
    authority: str = ""
    evidence: list[str] = field(default_factory=list)
    material: bool = True          # does it materially affect the reported behaviour?
    states: list[str] = field(default_factory=list)  # meaningful value-states to cover
    status: str = CANDIDATE_STATUS
    behavioral_branch: str = ""
    equivalence_key: str = ""      # hypotheses sharing this key collapse together
    reason: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SemanticRelation":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


def validate_relation(rel: SemanticRelation) -> list[str]:
    """Schema + evidence validation for one relation. Returns problem strings."""
    problems: list[str] = []
    tag = f"{rel.source_construct or '?'} -{rel.relation or '?'}-> {rel.target_construct or '?'}"
    if not rel.source_construct or not rel.target_construct:
        problems.append(f"{tag}: source_construct and target_construct are both required")
    if rel.relation not in RELATION_TYPES:
        problems.append(
            f"{tag}: relation '{rel.relation}' is not in the supported vocabulary "
            f"({', '.join(sorted(RELATION_TYPES))})"
        )
    if rel.status not in ALL_STATUSES:
        problems.append(f"{tag}: status '{rel.status}' is not one of {', '.join(ALL_STATUSES)}")
    # Evidence discipline: a MATERIAL relation must carry semantic evidence and a
    # resolved authority + version, or it is an unproven near-adjacency, not a fact.
    if rel.material:
        if not rel.evidence:
            problems.append(
                f"{tag}: material relation has no evidence — do not assert a dependency "
                f"from documentation proximity; attach the authoritative probe/quote"
            )
        if rel.authority not in AUTHORITY_LAYERS:
            problems.append(
                f"{tag}: material relation must name an authority layer ({', '.join(AUTHORITY_LAYERS)})"
            )
        if rel.dita_version not in DITA_VERSIONS:
            problems.append(f"{tag}: dita_version '{rel.dita_version}' must be one of {', '.join(DITA_VERSIONS)}")
    return problems


# --- Neighbourhood assembly --------------------------------------------------

def build_neighborhood(
    primary_construct: str,
    construct_type: str,
    relations: list[SemanticRelation],
) -> dict[str, Any]:
    """Assemble the section-3 semantic-neighbourhood record from relations.

    Relations are bucketed by relation TYPE. Only material relations populate the
    behavioural buckets; every relation's evidence is aggregated. Parent/child
    buckets are filled from CONTAINS/INHERITS edges relative to the primary
    construct so structural direction is preserved.
    """
    neighborhood: dict[str, Any] = {
        "primary_construct": primary_construct,
        "construct_type": construct_type,
    }
    for bucket in NEIGHBOURHOOD_BUCKETS:
        neighborhood[bucket] = []
    neighborhood["related_product_behavior"] = []
    evidence: list[str] = []

    for rel in relations:
        evidence.extend(rel.evidence)
        if not rel.material:
            continue
        bucket = RELATION_BUCKET.get(rel.relation)
        if not bucket:
            continue
        entry = {
            "construct": rel.target_construct,
            "relation": rel.relation,
            "dita_version": rel.dita_version,
            "authority": rel.authority,
            "status": rel.status,
        }
        neighborhood[bucket].append(entry)
        # Structural direction refinements.
        if rel.relation == "CONTAINS":
            neighborhood["child_dependencies"].append(entry)
        if rel.relation in ("INHERITS_FROM", "SCOPED_BY") and rel.target_construct != primary_construct:
            neighborhood["parent_dependencies"].append(entry)
        if rel.relation == "AFFECTS_OUTPUT_OF":
            neighborhood["related_product_behavior"].append(entry)

    neighborhood["evidence"] = evidence
    return neighborhood


# --- Coverage hypotheses -----------------------------------------------------

def coverage_hypothesis(rel: SemanticRelation) -> dict[str, Any]:
    """Turn one material relation into a coverage hypothesis (section-15 shape)."""
    return {
        "dimension": "DITA_SEMANTIC_DEPENDENCY",
        "primary_construct": rel.source_construct,
        "dependent_construct": rel.target_construct,
        "relationship": rel.relation,
        "behavioral_branch": rel.behavioral_branch or "; ".join(rel.states),
        "reason": rel.reason,
        "evidence": rel.evidence,
        "status": rel.status,
        "dita_version": rel.dita_version,
        "authority": rel.authority,
    }


def generate_coverage_hypotheses(relations: list[SemanticRelation]) -> list[dict[str, Any]]:
    """Every material, non-rejected relation becomes a coverage hypothesis."""
    return [
        coverage_hypothesis(rel)
        for rel in relations
        if rel.material and rel.status != "REJECTED"
    ]


def collapse_equivalent_paths(
    hypotheses: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Cartesian-explosion protection (section 17).

    Two hypotheses are equivalent when they exercise the same behavioural branch
    of the same relationship on an equivalent dependent construct. Equivalence is
    keyed by (relationship, behavioral_branch, dependent_construct) unless the
    caller supplied an explicit ``equivalence_key`` on the source relation, which
    then overrides construct identity so representative scenarios can stand in for
    a family. Returns (kept_representatives, collapsed_duplicates).
    """
    kept: list[dict[str, Any]] = []
    collapsed: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for hyp in hypotheses:
        key = (
            hyp.get("relationship", ""),
            (hyp.get("behavioral_branch") or "").strip().lower(),
            (hyp.get("equivalence_key") or hyp.get("dependent_construct") or "").strip().lower(),
        )
        if key in seen:
            collapsed.append(hyp)
        else:
            seen.add(key)
            kept.append(hyp)
    return kept, collapsed


# --- Semantic coverage gate --------------------------------------------------

# Gate dimensions and how each is resolved from the dita_semantics manifest block.
# "applicable_when" gates the *_WHEN_APPLICABLE dimensions.
GATE_DIMENSIONS = (
    "PRIMARY_CONSTRUCT_IDENTIFIED",
    "GOVERNING_SPEC_RETRIEVED",
    "SEMANTIC_NEIGHBORHOOD_EXPLORED",
    "CONTROLLING_DEPENDENCIES_EXPLORED",
    "INHERITANCE_EXPLORED_WHEN_APPLICABLE",
    "FALLBACK_PRECEDENCE_EXPLORED_WHEN_APPLICABLE",
    "REFERENCE_RESOLUTION_EXPLORED_WHEN_APPLICABLE",
    "MEANINGFUL_STATE_PARTITIONS_EXPLORED",
    "DITA_VERSION_AUTHORITY_RESOLVED",
    "PRODUCT_IMPLEMENTATION_CHECKED",
    "AUTOMATION_SEMANTIC_PATHS_CHECKED",
    "UNRESOLVED_SEMANTICS_EXPOSED",
)

# Relation types that make a *_WHEN_APPLICABLE dimension applicable.
_INHERITANCE_RELATIONS = {"INHERITS_FROM", "SPECIALIZES", "DERIVES_FROM"}
_FALLBACK_PRECEDENCE_RELATIONS = {"FALLS_BACK_TO", "OVERRIDES"}
_REFERENCE_RELATIONS = {"RESOLVES_FROM", "REFERENCES", "TARGETS", "SCOPED_BY", "FILTERED_BY"}

_DIM_COVERED = "COVERED"
_DIM_REJECTED = "INVESTIGATED_AND_REJECTED"
_DIM_EXPOSED = "UNRESOLVED_AND_EXPOSED"
_DIM_NA = "NOT_APPLICABLE"
_DIM_NEEDS_REVIEW = "NEEDS_REVIEW"


def _relation_dimension_status(relevant: list[SemanticRelation]) -> str:
    """Collapse a set of relations for one dimension into a dimension status."""
    if not relevant:
        return _DIM_NA
    # Any material relation still left as a bare candidate = never investigated.
    if any(r.material and r.status == CANDIDATE_STATUS for r in relevant):
        return _DIM_NEEDS_REVIEW
    if any(r.material and r.status in ("CONFIRMED", "INFERRED_HIGH_CONFIDENCE") for r in relevant):
        return _DIM_COVERED
    if any(r.material and r.status == "UNRESOLVED" for r in relevant):
        return _DIM_EXPOSED
    # everything material was rejected (or only immaterial relations remain)
    return _DIM_REJECTED


def evaluate_semantic_gate(semantics: dict[str, Any]) -> tuple[str, dict[str, str], list[str]]:
    """Evaluate the SemanticCoverageGate over a manifest ``dita_semantics`` block.

    Returns (overall_status, per_dimension_status, failures). overall_status is
    "PASSED" only when every applicable dimension ended COVERED,
    INVESTIGATED_AND_REJECTED, or UNRESOLVED_AND_EXPOSED. If any material
    dependency exists but was never investigated (left a bare candidate, or a
    material relation lacks evidence), the gate is NEEDS_REVIEW.
    """
    failures: list[str] = []
    if not semantics.get("active"):
        return "SKIPPED", {}, failures

    raw_relations = semantics.get("relations", []) or []
    relations = [SemanticRelation.from_dict(r) for r in raw_relations]

    for rel in relations:
        failures.extend(f"[relation] {p}" for p in validate_relation(rel))

    material = [r for r in relations if r.material]
    controlling = [r for r in material if r.relation in ("CONTROLS", "CHANGES_PROCESSING_OF")]
    inheritance = [r for r in material if r.relation in _INHERITANCE_RELATIONS]
    fallback_prec = [r for r in material if r.relation in _FALLBACK_PRECEDENCE_RELATIONS]
    reference = [r for r in material if r.relation in _REFERENCE_RELATIONS]

    dims: dict[str, str] = {}

    dims["PRIMARY_CONSTRUCT_IDENTIFIED"] = (
        _DIM_COVERED if semantics.get("primary_constructs") else _DIM_NEEDS_REVIEW
    )
    dims["GOVERNING_SPEC_RETRIEVED"] = (
        _DIM_COVERED if semantics.get("governing_spec_retrieved") else _DIM_NEEDS_REVIEW
    )
    dims["SEMANTIC_NEIGHBORHOOD_EXPLORED"] = (
        _DIM_COVERED if relations else _DIM_NEEDS_REVIEW
    )
    dims["CONTROLLING_DEPENDENCIES_EXPLORED"] = _relation_dimension_status(controlling)
    dims["INHERITANCE_EXPLORED_WHEN_APPLICABLE"] = _relation_dimension_status(inheritance)
    dims["FALLBACK_PRECEDENCE_EXPLORED_WHEN_APPLICABLE"] = _relation_dimension_status(fallback_prec)
    dims["REFERENCE_RESOLUTION_EXPLORED_WHEN_APPLICABLE"] = _relation_dimension_status(reference)

    # Meaningful state partitions: a covered/exposed material relation should name
    # the value-states that create distinct behaviour, else the branch is untested.
    resolved_material = [
        r for r in material
        if r.status in ("CONFIRMED", "INFERRED_HIGH_CONFIDENCE", "UNRESOLVED")
    ]
    if not resolved_material:
        dims["MEANINGFUL_STATE_PARTITIONS_EXPLORED"] = _DIM_NA if not material else _DIM_NEEDS_REVIEW
    elif all(r.states or r.behavioral_branch for r in resolved_material):
        dims["MEANINGFUL_STATE_PARTITIONS_EXPLORED"] = _DIM_COVERED
    else:
        dims["MEANINGFUL_STATE_PARTITIONS_EXPLORED"] = _DIM_NEEDS_REVIEW

    # Version + authority resolved for every material relation, or exposed as open.
    if not material:
        dims["DITA_VERSION_AUTHORITY_RESOLVED"] = _DIM_NA
    elif all(r.dita_version in DITA_VERSIONS and r.dita_version != "unknown" and r.authority in AUTHORITY_LAYERS
             for r in material):
        dims["DITA_VERSION_AUTHORITY_RESOLVED"] = _DIM_COVERED
    elif semantics.get("version_authority_open_questions"):
        dims["DITA_VERSION_AUTHORITY_RESOLVED"] = _DIM_EXPOSED
    else:
        dims["DITA_VERSION_AUTHORITY_RESOLVED"] = _DIM_NEEDS_REVIEW

    dims["PRODUCT_IMPLEMENTATION_CHECKED"] = (
        _DIM_COVERED if semantics.get("product_implementation_checked") else _DIM_NEEDS_REVIEW
    )
    dims["AUTOMATION_SEMANTIC_PATHS_CHECKED"] = (
        _DIM_COVERED if semantics.get("automation_semantic_paths_checked") else _DIM_NEEDS_REVIEW
    )
    # Unresolved semantics must be exposed, not swallowed. Covered when there are
    # none, or when the ones that exist are listed in `unresolved`.
    unresolved_relations = [r for r in material if r.status == "UNRESOLVED"]
    if not unresolved_relations and not semantics.get("unresolved"):
        dims["UNRESOLVED_SEMANTICS_EXPOSED"] = _DIM_COVERED
    elif semantics.get("unresolved"):
        dims["UNRESOLVED_SEMANTICS_EXPOSED"] = _DIM_EXPOSED
    else:
        dims["UNRESOLVED_SEMANTICS_EXPOSED"] = _DIM_NEEDS_REVIEW

    for dim, status in dims.items():
        if status == _DIM_NEEDS_REVIEW:
            failures.append(
                f"[semantic-gate] {dim} = NEEDS_REVIEW — an applicable semantic dependency was "
                f"not investigated to a terminal status (COVERED / INVESTIGATED_AND_REJECTED / "
                f"UNRESOLVED_AND_EXPOSED)"
            )

    overall = "PASSED" if not failures else _DIM_NEEDS_REVIEW
    return overall, dims, failures


def summarize(semantics: dict[str, Any]) -> str:
    """Human-readable one-block summary of the gate result (for CLI / notes)."""
    overall, dims, failures = evaluate_semantic_gate(semantics)
    lines = [f"Semantic coverage gate: {overall}"]
    for dim in GATE_DIMENSIONS:
        lines.append(f"  {dim}: {dims.get(dim, _DIM_NA)}")
    for f in failures:
        lines.append(f"  FAIL {f}")
    return "\n".join(lines)
