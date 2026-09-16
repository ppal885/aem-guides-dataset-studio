"""Historical Jira Evidence Safety gate (H1) - similarity is discovery, not authority.

WHY THIS EXISTS
---------------
Historical Jira is useful evidence: it can surface known behavior, terminology,
previous regression paths, relevant configurations, and likely documentation or
code locations.  But similarity to an old ticket must NEVER automatically make
that ticket an authority for the current ticket.  This gate extends the existing
historical-evidence path (temporal_evidence, evidence_authority_resolver, the
Q1 resolver's NON_ESTABLISHING HISTORICAL_JIRA authority, and the
data/authority_policy.json rankings) with a question-bound per-item assessment.
It does NOT create a competing framework, a new authority hierarchy, or a
retrieval evaluation: retrieval rank remains discovery metadata.

Manifest block ``historical_jira_assessment`` -> ``items[]``.  Every historical
Jira item considered for a material Question records:

    history_id, question_id, jira_key_or_source_id, relationship,
    feature_match, surface_match, version_match, configuration_match,
    failure_mode_match, expected_behavior_match, currentness,
    superseded_status, human_accepted_ac_available, applicability,
    authority_role, allowed_use, reason, limitations[]
    (optional: evidence_kind, authority_basis)

Closed relationships:

- AUTHORITATIVE_HISTORY - only when EXISTING source-authority policy
  explicitly allows that historical source to establish the claim for the
  current Question; requires ``authority_basis`` naming the permitting rule and
  exact applicability.  A historical Human Accepted AC is NOT automatically
  authoritative for a different current ticket.
- SUPPORTING_PRECEDENT - materially same behavior, applicable surface,
  established version/configuration applicability, no conflict with current
  higher-authority evidence.  May contribute; S1 still evaluates the complete
  evidence.  Never overrides current Jira requirements.
- DISCOVERY_ONLY - helps locate terminology, sources, configurations,
  regression dimensions, documentation/code paths, or previous investigations.
  Cannot directly establish an Acceptance answer and never enters final Source
  lines as acceptance authority.
- NOT_APPLICABLE - material applicability differs (wrong surface, wrong
  version, different deployment/configuration/workflow, customer-specific
  behavior).  High semantic similarity must not override NOT_APPLICABLE.
- CONFLICTING_HISTORY - materially conflicts with current evidence; the
  disagreement is preserved and routed through existing Q1/S1 conflict/TBD
  behavior.  Never silently resolved.

Hard rules enforced (all generic; no ticket keys or feature names):

- history_id unique; question_id must exist in the Question Plan; relationship
  and allowed_use are closed enums and must be compatible; match dimensions,
  currentness, and superseded_status are closed enums; reason and limitations
  recorded.
- AUTHORITATIVE_HISTORY requires authority_basis plus exact applicability
  (surface/version/configuration/expected-behavior all SAME).
- DIFFERENT surface/version/configuration match => NOT_APPLICABLE (similarity
  cannot override applicability).
- DIFFERENT expected behavior => never AUTHORITATIVE_HISTORY /
  SUPPORTING_PRECEDENT.
- SUPERSEDED history never establishes or supports current behavior.
- Historical ACTUAL_RESULT / REPRODUCTION / SUSPECTED_ROOT_CAUSE remains
  observation/investigation: allowed_use DISCOVERY or NONE, never
  AUTHORITATIVE_HISTORY.
- DISCOVERY_ONLY / NOT_APPLICABLE evidence never appears as establishing
  evidence in an ANSWERED resolution; NOT_APPLICABLE never appears in any
  answer or coverage evidence.
- CONFLICTING_HISTORY never silently resolves a Question: the resolution stays
  CONFLICTED / ACCEPTANCE_TBD / PARTIALLY_ANSWERED (or ANSWERED only with the
  contradictions retained per the Q1 rule).
- S1 integration: a SUFFICIENT question never rests on DISCOVERY_ONLY /
  NOT_APPLICABLE / CONFLICTING_HISTORY evidence; SUPPORTING_PRECEDENT may
  contribute but never alone establishes.
- C1 integration: historical evidence never directly creates a Coverage
  Decision - it may appear in coverage evidence only through its bound
  Question and only as AUTHORITATIVE_HISTORY / SUPPORTING_PRECEDENT.
- L1 integration: historical evidence reaches AC lineage (and therefore final
  Source lines) only when legitimately admitted as AUTHORITATIVE_HISTORY /
  SUPPORTING_PRECEDENT; DISCOVERY_ONLY remains auditable outside AC lineage.

Backward-compatible: absent ``historical_jira_assessment`` -> clean pass.
Generic only.  Stdlib only.
"""
from __future__ import annotations

from question_resolver import ANSWER_AUTHORITIES

RELATIONSHIPS = (
    "AUTHORITATIVE_HISTORY",
    "SUPPORTING_PRECEDENT",
    "DISCOVERY_ONLY",
    "NOT_APPLICABLE",
    "CONFLICTING_HISTORY",
)

MATCH_VALUES = ("SAME", "SIMILAR", "DIFFERENT", "UNKNOWN")

MATCH_DIMENSIONS = (
    "feature_match",
    "surface_match",
    "version_match",
    "configuration_match",
    "failure_mode_match",
    "expected_behavior_match",
)

# Dimensions whose DIFFERENT value forces NOT_APPLICABLE regardless of
# similarity (spec: wrong surface, wrong version, different configuration).
APPLICABILITY_DIMENSIONS = ("surface_match", "version_match", "configuration_match")

CURRENTNESS_VALUES = ("CURRENT", "STALE", "SUPERSEDED", "UNKNOWN")

SUPERSEDED_VALUES = ("SUPERSEDED", "NOT_SUPERSEDED", "UNKNOWN")

ALLOWED_USES = (
    "ESTABLISH_ANSWER",
    "SUPPORT_ANSWER",
    "DISCOVERY",
    "NONE",
    "CONFLICT_SIGNAL",
)

# allowed_use compatibility per relationship.
USE_BY_RELATIONSHIP = {
    "AUTHORITATIVE_HISTORY": frozenset({"ESTABLISH_ANSWER"}),
    "SUPPORTING_PRECEDENT": frozenset({"SUPPORT_ANSWER"}),
    "DISCOVERY_ONLY": frozenset({"DISCOVERY"}),
    "NOT_APPLICABLE": frozenset({"NONE"}),
    "CONFLICTING_HISTORY": frozenset({"CONFLICT_SIGNAL"}),
}

EVIDENCE_KINDS = (
    "EXPECTED_RESULT",
    "ACCEPTED_AC",
    "ACTUAL_RESULT",
    "REPRODUCTION",
    "SUSPECTED_ROOT_CAUSE",
    "DOCUMENTATION",
    "OTHER",
)

# Historical observations/investigation stay observations (spec section 10).
OBSERVATION_KINDS = frozenset({
    "ACTUAL_RESULT", "REPRODUCTION", "SUSPECTED_ROOT_CAUSE",
})

# Relationships whose evidence may contribute to establishing/supporting a
# current answer (S1 may still decide the complete evidence is insufficient).
ESTABLISHING_RELATIONSHIPS = frozenset({
    "AUTHORITATIVE_HISTORY", "SUPPORTING_PRECEDENT",
})


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(
        manifest.get("historical_jira_assessment"), dict
    )


def _nonempty(value):
    return bool(value.strip()) if isinstance(value, str) else bool(value)


def _chain_context(manifest):
    """Collect the existing Q1/S1/C1/L1 blocks for referential checks."""

    ctx = {"questions": set(), "resolutions": {}, "coverage": {},
           "sufficiency": {}, "ac_lineage": []}
    plan = manifest.get("question_plan")
    if isinstance(plan, dict):
        for source in (plan.get("items"),
                       (plan.get("overflow") or {}).get("items")):
            if isinstance(source, list):
                for row in source:
                    if isinstance(row, dict) and row.get("question_id"):
                        ctx["questions"].add(row["question_id"])
    resolutions = manifest.get("question_resolutions")
    if isinstance(resolutions, dict):
        for row in resolutions.get("items", []):
            if isinstance(row, dict):
                ref = row.get("question_ref") or row.get("question_id")
                if ref:
                    ctx["resolutions"][ref] = row
    coverage = manifest.get("coverage_decisions")
    if isinstance(coverage, dict):
        for row in coverage.get("items", []):
            if isinstance(row, dict) and row.get("coverage_id"):
                ctx["coverage"][row["coverage_id"]] = row
    sufficiency = manifest.get("evidence_sufficiency")
    if isinstance(sufficiency, dict):
        for row in sufficiency.get("question_assessments", []):
            if isinstance(row, dict):
                ref = row.get("question_ref") or row.get("question_id")
                if ref:
                    ctx["sufficiency"][ref] = row
    lineage = manifest.get("requirement_lineage")
    if isinstance(lineage, dict) and isinstance(lineage.get("ac_lineage"), list):
        ctx["ac_lineage"] = [
            row for row in lineage["ac_lineage"] if isinstance(row, dict)
        ]
    return ctx


def _resolution_disposition(row):
    return row.get("disposition") or row.get("status")


def _answer_source_ids(row):
    answer = row.get("answer")
    if isinstance(answer, dict):
        ids = answer.get("source_ids")
        if isinstance(ids, list):
            return [str(v) for v in ids]
    ids = row.get("source_ids")
    if isinstance(ids, list):
        return [str(v) for v in ids]
    return []


def _answer_contradictions(row):
    answer = row.get("answer")
    if isinstance(answer, dict) and isinstance(answer.get("contradictions"), list):
        return answer["contradictions"]
    if isinstance(row.get("contradictions"), list):
        return row["contradictions"]
    return []


def validate(manifest):
    problems = []
    if not is_present(manifest):
        return problems

    block = manifest["historical_jira_assessment"]
    items = block.get("items", [])
    if not isinstance(items, list):
        return ["historical_jira_assessment.items must be a list"]

    ctx = _chain_context(manifest)
    seen = set()
    by_id = {}

    for i, item in enumerate(items):
        tag = f"historical_jira_assessment.items[{i}]"
        if not isinstance(item, dict):
            problems.append(f"{tag}: each assessment must be an object")
            continue

        history_id = item.get("history_id")
        if not _nonempty(history_id):
            problems.append(f"{tag}: missing history_id")
            continue
        if history_id in seen:
            problems.append(f"{tag}: duplicate history_id '{history_id}'")
        seen.add(history_id)
        by_id[history_id] = (tag, item)

        question_id = item.get("question_id")
        if not _nonempty(question_id):
            problems.append(f"{tag}: missing question_id - every historical "
                            "use binds to a specific Question")
        elif ctx["questions"] and question_id not in ctx["questions"]:
            problems.append(
                f"{tag}: question_id '{question_id}' does not exist in the "
                "Question Plan - historical Jira is never admitted globally"
            )
        source_ref = item.get("jira_key_or_source_id")
        if not _nonempty(source_ref):
            problems.append(f"{tag}: missing jira_key_or_source_id - the "
                            "historical source identity is preserved")

        relationship = item.get("relationship")
        if relationship not in RELATIONSHIPS:
            problems.append(
                f"{tag}: relationship '{relationship}' must be one of "
                f"{', '.join(RELATIONSHIPS)} - never classified from vector "
                "similarity or lexical overlap alone"
            )
            continue

        for dim in MATCH_DIMENSIONS:
            if item.get(dim) not in MATCH_VALUES:
                problems.append(
                    f"{tag}: {dim} '{item.get(dim)}' must be one of "
                    f"{', '.join(MATCH_VALUES)}"
                )
        if item.get("currentness") not in CURRENTNESS_VALUES:
            problems.append(
                f"{tag}: currentness '{item.get('currentness')}' must be one "
                f"of {', '.join(CURRENTNESS_VALUES)}"
            )
        if item.get("superseded_status") not in SUPERSEDED_VALUES:
            problems.append(
                f"{tag}: superseded_status '{item.get('superseded_status')}' "
                f"must be one of {', '.join(SUPERSEDED_VALUES)}"
            )
        if not isinstance(item.get("human_accepted_ac_available"), bool):
            problems.append(
                f"{tag}: human_accepted_ac_available must be a boolean"
            )
        if not _nonempty(item.get("applicability")):
            problems.append(
                f"{tag}: missing applicability - exact applicability is "
                "required for every historical use"
            )
        authority_role = item.get("authority_role")
        if authority_role is not None and authority_role not in ANSWER_AUTHORITIES:
            problems.append(
                f"{tag}: authority_role '{authority_role}' must reuse the "
                "existing answer-authority vocabulary"
            )
        allowed_use = item.get("allowed_use")
        if allowed_use not in ALLOWED_USES:
            problems.append(
                f"{tag}: allowed_use '{allowed_use}' must be one of "
                f"{', '.join(ALLOWED_USES)}"
            )
        elif allowed_use not in USE_BY_RELATIONSHIP[relationship]:
            problems.append(
                f"{tag}: allowed_use '{allowed_use}' is incompatible with "
                f"relationship '{relationship}'"
            )
        if not _nonempty(item.get("reason")):
            problems.append(f"{tag}: missing reason")
        if not isinstance(item.get("limitations"), list):
            problems.append(f"{tag}: limitations must be a list")

        evidence_kind = item.get("evidence_kind")
        if evidence_kind is not None and evidence_kind not in EVIDENCE_KINDS:
            problems.append(
                f"{tag}: evidence_kind '{evidence_kind}' must be one of "
                f"{', '.join(EVIDENCE_KINDS)}"
            )

        # AUTHORITATIVE_HISTORY is narrow: an existing authority rule must
        # permit the use, and applicability must be exact. A historical Human
        # Accepted AC is not automatically authoritative for a different
        # current ticket.
        if relationship == "AUTHORITATIVE_HISTORY":
            if not _nonempty(item.get("authority_basis")):
                problems.append(
                    f"{tag}: AUTHORITATIVE_HISTORY requires authority_basis "
                    "naming the existing source-authority rule that permits "
                    "the use - do not create a new authority hierarchy"
                )
            for dim in APPLICABILITY_DIMENSIONS + ("expected_behavior_match",):
                if item.get(dim) != "SAME":
                    problems.append(
                        f"{tag}: AUTHORITATIVE_HISTORY requires exact "
                        f"applicability - {dim} must be SAME"
                    )
            if item.get("human_accepted_ac_available") and not _nonempty(
                item.get("authority_basis")
            ):
                problems.append(
                    f"{tag}: a historical Human Accepted AC is NOT "
                    "automatically authoritative for a different current "
                    "ticket"
                )

        # Material applicability differences force NOT_APPLICABLE; high
        # semantic similarity must not override it.
        if any(item.get(dim) == "DIFFERENT" for dim in APPLICABILITY_DIMENSIONS):
            if relationship != "NOT_APPLICABLE":
                problems.append(
                    f"{tag}: material applicability differs "
                    f"({', '.join(d for d in APPLICABILITY_DIMENSIONS if item.get(d) == 'DIFFERENT')}) "
                    "- relationship must be NOT_APPLICABLE; high semantic "
                    "similarity must not override NOT_APPLICABLE"
                )

        # A different expected behavior can never establish or support the
        # current answer.
        if (item.get("expected_behavior_match") == "DIFFERENT"
                and relationship in ESTABLISHING_RELATIONSHIPS):
            problems.append(
                f"{tag}: expected behavior differs - historical Jira cannot "
                "establish or support the current expected behavior"
            )

        # Superseded history never establishes or supports current behavior.
        if (item.get("superseded_status") == "SUPERSEDED"
                or item.get("currentness") == "SUPERSEDED"):
            if relationship in ESTABLISHING_RELATIONSHIPS:
                problems.append(
                    f"{tag}: superseded history never establishes or "
                    "supports current behavior"
                )

        # Historical observations stay observations.
        if evidence_kind in OBSERVATION_KINDS:
            if relationship == "AUTHORITATIVE_HISTORY":
                problems.append(
                    f"{tag}: a historical {evidence_kind} remains an "
                    "observation - it never becomes AUTHORITATIVE_HISTORY"
                )
            if allowed_use not in (None, "DISCOVERY", "NONE"):
                problems.append(
                    f"{tag}: a historical {evidence_kind} remains "
                    "observation/investigation - allowed_use must be "
                    "DISCOVERY or NONE, never an acceptance requirement"
                )

    # ---- Cross-block bindings (Q1/S1/C1/L1) --------------------------------
    for history_id, (tag, item) in by_id.items():
        relationship = item.get("relationship")
        source_ref = str(item.get("jira_key_or_source_id") or "")
        question_id = item.get("question_id")

        resolution = ctx["resolutions"].get(question_id)
        if resolution is not None and source_ref:
            disposition = _resolution_disposition(resolution)
            cited = source_ref in _answer_source_ids(resolution)
            if relationship in ("DISCOVERY_ONLY", "NOT_APPLICABLE") and cited:
                problems.append(
                    f"{tag}: {relationship} evidence cannot directly "
                    f"establish an Acceptance answer - '{source_ref}' is cited "
                    f"by the resolution of '{question_id}'"
                )
            if relationship == "CONFLICTING_HISTORY":
                if disposition == "ANSWERED" and not _answer_contradictions(resolution):
                    problems.append(
                        f"{tag}: CONFLICTING_HISTORY cannot silently resolve "
                        f"'{question_id}' - stay CONFLICTED/ACCEPTANCE_TBD or "
                        "retain the contradictions per the Q1 rule"
                    )

        # NOT_APPLICABLE never contributes establishing evidence anywhere.
        if relationship == "NOT_APPLICABLE" and source_ref:
            for ref, row in ctx["resolutions"].items():
                if source_ref in _answer_source_ids(row):
                    problems.append(
                        f"{tag}: NOT_APPLICABLE evidence '{source_ref}' "
                        f"cannot contribute establishing evidence to '{ref}'"
                    )

        # S1 integration: sufficiency never rests on non-establishing history.
        assessment = ctx["sufficiency"].get(question_id)
        if assessment is not None and source_ref:
            suff_evidence = [str(v) for v in assessment.get("evidence_ids", [])]
            status = (assessment.get("sufficiency_status")
                      or assessment.get("sufficiency"))
            if source_ref in suff_evidence:
                if relationship not in ESTABLISHING_RELATIONSHIPS:
                    problems.append(
                        f"{tag}: {relationship} evidence cannot make "
                        f"'{question_id}' SUFFICIENT - it is not establishing "
                        "evidence"
                    )
                elif (relationship == "SUPPORTING_PRECEDENT"
                      and status == "SUFFICIENT"
                      and suff_evidence == [source_ref]):
                    problems.append(
                        f"{tag}: SUPPORTING_PRECEDENT alone never makes "
                        f"'{question_id}' SUFFICIENT - S1 evaluates the "
                        "complete current evidence"
                    )
            if (relationship == "CONFLICTING_HISTORY"
                    and status == "SUFFICIENT"):
                problems.append(
                    f"{tag}: CONFLICTING_HISTORY cannot silently produce "
                    f"SUFFICIENT for '{question_id}'"
                )

        # C1 integration: historical evidence reaches coverage only through
        # its bound Question and only as establishing/supporting lineage.
        if source_ref:
            for cid, cov in ctx["coverage"].items():
                cov_evidence = [str(v) for v in cov.get("evidence_ids", [])]
                if source_ref not in cov_evidence:
                    continue
                if relationship not in ESTABLISHING_RELATIONSHIPS:
                    problems.append(
                        f"{tag}: {relationship} evidence cannot ground "
                        f"coverage '{cid}' - historical Jira cannot directly "
                        "create a Coverage Decision"
                    )
                elif question_id not in (cov.get("question_ids") or []):
                    problems.append(
                        f"{tag}: historical evidence in coverage '{cid}' must "
                        f"arrive through its bound Question '{question_id}' - "
                        "Historical Jira -> Question-bound assessment -> "
                        "Question Resolution/Sufficiency -> Coverage Reasoner"
                    )

        # L1 integration: final Source lines include historical Jira only when
        # legitimately admitted; DISCOVERY_ONLY stays auditable outside it.
        if source_ref:
            for row in ctx["ac_lineage"]:
                refs = [str(v) for v in row.get("evidence_refs", [])]
                if source_ref in refs and relationship not in ESTABLISHING_RELATIONSHIPS:
                    problems.append(
                        f"{tag}: {relationship} evidence never reaches AC "
                        f"lineage / final Source lines ('{row.get('ac_id')}') - "
                        "unused historical Jira must not contaminate them"
                    )

    return problems


def summarize(manifest):
    if not is_present(manifest):
        return "historical_jira_assessment: NOT PRESENT (clean pass)"
    items = manifest["historical_jira_assessment"].get("items", []) or []
    by_rel = {}
    for row in items:
        if isinstance(row, dict):
            rel = row.get("relationship", "?")
            by_rel[rel] = by_rel.get(rel, 0) + 1
    parts = ", ".join(f"{k}={v}" for k, v in sorted(by_rel.items())) or "none"
    return f"historical_jira_assessment: {len(items)} item(s) ({parts})"


def main():  # pragma: no cover - CLI helper
    import json
    import sys

    if len(sys.argv) != 2:
        print("usage: historical_jira_safety.py MANIFEST.json")
        return 2
    manifest = json.load(open(sys.argv[1], encoding="utf-8"))
    problems = validate(manifest)
    print(summarize(manifest))
    for problem in problems:
        print(f"FAIL: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
