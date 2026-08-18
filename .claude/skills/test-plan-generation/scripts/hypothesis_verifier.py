"""HypothesisVerifier - drive every hypothesis to a terminal verdict, and stop
richer exploration from becoming richer hallucination.

WHY THIS EXISTS
---------------
Prompts 2-3 produced INVESTIGATION_CANDIDATEs and directed retrieval. Increased
exploration must NOT increase unsupported UAC. This module enforces that every
hypothesis ends in exactly one verdict and that the verdict is justified by
evidence of the right authority, then routes each verdict to an allowed
disposition so unproven behavior cannot leak into acceptance criteria.

Verdicts:
- CONFIRMED               : direct authoritative evidence establishes the behavior.
- INFERRED_HIGH_CONFIDENCE: multiple strong technical facts, but NO explicit product
                            decision - kept explicitly as inference, not confirmed.
- REJECTED                : evidence disproves applicability.
- UNRESOLVED              : insufficient / conflicting evidence, or a product decision
                            is required, or product-vs-spec behavior is unclear.

Hard anti-hallucination rules (all generic, no domain/construct/Jira rules):
- UNRESOLVED -> OPEN_QUESTION only (never an expected result / AC).
- REJECTED   -> EXCLUDED / CONTEXT only (never AC, regression, or open question).
- CONFIRMED must rest on an authoritative source, not on embedding similarity alone
  and not on an existing test alone (a test expecting X is not, by itself, the
  current product contract).
- A spec-vs-implementation conflict (or any conflicting evidence) forces UNRESOLVED.

Stdlib only. Same dataclass/validate pattern (no future-annotations import).
"""

from dataclasses import dataclass, field


VERDICTS = ("CONFIRMED", "INFERRED_HIGH_CONFIDENCE", "REJECTED", "UNRESOLVED")

# Authorities that can, on their own, establish a CONFIRMED behavior.
AUTHORITATIVE_FOR_CONFIRMED = frozenset({
    "JIRA", "AEM_GUIDES_DOC", "EXPERIENCE_LEAGUE", "DITA_SPEC", "DITA_OT", "CURRENT_IMPLEMENTATION",
})
# Authorities that are evidence but NOT sufficient alone to confirm current product behavior.
INSUFFICIENT_ALONE = frozenset({"EXISTING_AUTOMATION", "HISTORICAL_BEHAVIOR"})
ALL_AUTHORITIES = AUTHORITATIVE_FOR_CONFIRMED | INSUFFICIENT_ALONE

# Where a verified hypothesis is allowed to land.
DISPOSITIONS = ("ACCEPTANCE_CRITERION", "INFERRED_AC", "REGRESSION", "OPEN_QUESTION", "EXCLUDED", "CONTEXT")

# Verdict -> allowed dispositions. This mapping IS the hallucination control.
ALLOWED_DISPOSITIONS = {
    "CONFIRMED": {"ACCEPTANCE_CRITERION", "REGRESSION"},
    "INFERRED_HIGH_CONFIDENCE": {"INFERRED_AC", "REGRESSION", "OPEN_QUESTION"},
    "REJECTED": {"EXCLUDED", "CONTEXT"},
    "UNRESOLVED": {"OPEN_QUESTION"},
}


@dataclass
class Verification:
    hypothesis_id: str = ""
    verdict: str = ""
    supporting_authorities: list = field(default_factory=list)   # authority tokens that support it
    supporting_evidence: list = field(default_factory=list)      # evidence ids used
    disproving_evidence: list = field(default_factory=list)
    conflict: bool = False               # spec-vs-impl or otherwise conflicting evidence
    product_decision: bool = False       # an explicit accepted product/engineering decision exists
    product_decision_required: bool = False
    insufficient: bool = False
    similarity_only: bool = False        # supported only by embedding/keyword similarity
    disposition: str = ""
    open_question_ref: str = ""
    note: str = ""

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


def validate_verification(v):
    problems = []
    tag = f"verification '{v.hypothesis_id or '?'}'"

    if v.verdict not in VERDICTS:
        problems.append(f"{tag}: verdict '{v.verdict}' must be one of {', '.join(VERDICTS)}")
        return problems  # nothing else is meaningful without a valid verdict

    for a in v.supporting_authorities:
        if a not in ALL_AUTHORITIES:
            problems.append(f"{tag}: authority '{a}' is not a known authority ({', '.join(sorted(ALL_AUTHORITIES))})")

    if v.disposition not in DISPOSITIONS:
        problems.append(f"{tag}: disposition '{v.disposition}' must be one of {', '.join(DISPOSITIONS)}")
    elif v.disposition not in ALLOWED_DISPOSITIONS[v.verdict]:
        problems.append(
            f"{tag}: verdict {v.verdict} cannot have disposition {v.disposition} - allowed: "
            f"{', '.join(sorted(ALLOWED_DISPOSITIONS[v.verdict]))} "
            f"(UNRESOLVED->OPEN_QUESTION only; REJECTED never enters an AC/regression/open-question)"
        )

    # Any conflict (incl. spec-vs-implementation divergence) forces UNRESOLVED.
    if v.conflict and v.verdict != "UNRESOLVED":
        problems.append(
            f"{tag}: conflicting evidence (e.g. DITA spec vs AEM Guides implementation) must be UNRESOLVED, "
            f"not {v.verdict} - surface the divergence as an Open Question"
        )

    if v.verdict == "CONFIRMED":
        if v.similarity_only:
            problems.append(f"{tag}: CONFIRMED cannot rest on embedding/keyword similarity alone")
        authoritative = [a for a in v.supporting_authorities if a in AUTHORITATIVE_FOR_CONFIRMED]
        if not authoritative:
            problems.append(
                f"{tag}: CONFIRMED needs at least one authoritative source "
                f"({', '.join(sorted(AUTHORITATIVE_FOR_CONFIRMED))})"
            )
        # existing test alone is not the current product contract
        if v.supporting_authorities and set(v.supporting_authorities) <= INSUFFICIENT_ALONE:
            problems.append(
                f"{tag}: CONFIRMED is justified only by {sorted(set(v.supporting_authorities))} - an existing "
                f"test or historical status alone is not the current product contract; add an authoritative source"
            )

    elif v.verdict == "INFERRED_HIGH_CONFIDENCE":
        if v.product_decision:
            problems.append(
                f"{tag}: an explicit product decision exists, so this should be CONFIRMED, not INFERRED_HIGH_CONFIDENCE"
            )
        if len(v.supporting_evidence) < 2:
            problems.append(
                f"{tag}: INFERRED_HIGH_CONFIDENCE needs multiple supporting facts (>=2 supporting_evidence)"
            )

    elif v.verdict == "REJECTED":
        if not v.disproving_evidence:
            problems.append(f"{tag}: REJECTED needs disproving_evidence")

    elif v.verdict == "UNRESOLVED":
        if not v.open_question_ref:
            problems.append(f"{tag}: UNRESOLVED must reference an Open Question (open_question_ref)")
        if not (v.conflict or v.product_decision_required or v.insufficient):
            problems.append(
                f"{tag}: UNRESOLVED must state a reason (conflict / product_decision_required / insufficient)"
            )

    return problems


def verify_all(coverage_hypotheses, verifications):
    """Cross-check: every coverage hypothesis is verified to a terminal verdict, and
    every verification is internally valid. Returns problem strings."""
    problems = []
    verifs = [Verification.from_dict(x) for x in (verifications or [])]
    for v in verifs:
        problems.extend(validate_verification(v))

    verified_ids = {v.hypothesis_id for v in verifs if v.hypothesis_id}
    for h in (coverage_hypotheses or []):
        hid = h.get("hypothesis_id") if isinstance(h, dict) else getattr(h, "hypothesis_id", "")
        status = h.get("status") if isinstance(h, dict) else getattr(h, "status", "")
        if hid and hid not in verified_ids:
            problems.append(
                f"coverage hypothesis '{hid}' (status {status}) has no verification - every candidate must reach a "
                f"terminal verdict (CONFIRMED / INFERRED_HIGH_CONFIDENCE / REJECTED / UNRESOLVED)"
            )
    return problems


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("verifications"), list)


def summarize(manifest):
    verifs = [Verification.from_dict(x) for x in (manifest.get("verifications", []) or [])]
    problems = verify_all(manifest.get("coverage_hypotheses", []), manifest.get("verifications", []))
    by_verdict = {}
    for v in verifs:
        by_verdict[v.verdict] = by_verdict.get(v.verdict, 0) + 1
    lines = [f"HypothesisVerifier: {'VALID' if not problems else 'INVALID'} ({len(verifs)} verification(s))"]
    lines.append("  verdicts: " + (", ".join(f"{k}={v}" for k, v in sorted(by_verdict.items())) or "(none)"))
    for p in problems:
        lines.append(f"  PROBLEM {p}")
    return "\n".join(lines)
