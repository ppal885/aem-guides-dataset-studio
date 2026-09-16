"""Doc Research routing gate - enforces invocation of the EXISTING UAC Doc
Researcher (backward-compatible).

WHY THIS EXISTS
---------------
The Doc Researcher role exists, but the agentic UAC workflow could continue
without invoking it even when existing product documentation materially
affects acceptance reasoning.  This gate validates the manifest
`doc_research` block: an explicit research-routing contract recorded after
Evidence, before Coverage/Writer.  It introduces no new agent and changes no
source authority.

Routing states:

- ``RESEARCH_NOT_REQUIRED`` - documentation would not materially change
  acceptance reasoning (e.g. an explicit authoritative Human Accepted AC is
  sufficient).  Requires `not_required_reason`.
- ``DOC_RESEARCH_REQUIRED`` - a material trigger fired.  HARD GATE: without a
  terminal Doc Researcher result, Coverage/Writer MUST NOT proceed.
- Terminal result states: ``DOC_RESEARCH_COMPLETED``, ``DOC_RESEARCH_PARTIAL``,
  ``DOC_RESEARCH_UNAVAILABLE``, ``DOC_RESEARCH_CONFLICTED``.

Material triggers (route to DOC_RESEARCH_REQUIRED): the ticket changes existing
documented functionality; existing behavior must be understood or preserved;
configuration semantics are not sufficiently established by the ticket;
product/version/surface applicability needs confirmation; backward
compatibility materially affects acceptance; terminology materially affects
behavior; ticket evidence is insufficient but authorized product documentation
may answer the missing behavior; the Evidence Agent explicitly requests
documentation research.  Never route merely because related documentation
exists: DOC_RESEARCH_REQUIRED requires at least one declared trigger.

The Doc Researcher result contract: ``research_id``, ``status``, ``topics[]``,
``findings[]``, ``source_ids[]``, ``applicability``, ``limitations[]``,
``conflicts[]``, and ``produced_by`` naming the existing Doc Researcher role
(the coordinator/main agent must not impersonate it).  Every finding carries
``claim``, ``source_id``, ``source_type``, ``authority``, ``applicability``,
``currentness`` when available, and ``evidence_role`` (EXISTING_BEHAVIOR /
REQUIREMENT_CLARIFICATION / SUPPORTING_CONTEXT).

Reviewer rules enforced: required research was skipped (hard gate); a finding
cites documentation the research never retrieved; PARTIAL research is
represented as complete; existing documentation is cited as proof of new
behavior; NOT_FOUND treated as evidence of the opposite behavior; the
Researcher writing ACs or deciding acceptance scope.

The Writer receives only admitted research: ``admitted_research_ids`` must
reference real results, and RESEARCH_NOT_REQUIRED admits nothing.

Backward-compatible: absent `doc_research` -> clean pass.
Generic only. Stdlib only.
"""
from __future__ import annotations

ROUTING_STATES = (
    "RESEARCH_NOT_REQUIRED",
    "DOC_RESEARCH_REQUIRED",
    "DOC_RESEARCH_COMPLETED",
    "DOC_RESEARCH_PARTIAL",
    "DOC_RESEARCH_UNAVAILABLE",
    "DOC_RESEARCH_CONFLICTED",
)

TERMINAL_STATES = frozenset({
    "DOC_RESEARCH_COMPLETED",
    "DOC_RESEARCH_PARTIAL",
    "DOC_RESEARCH_UNAVAILABLE",
    "DOC_RESEARCH_CONFLICTED",
})

ROUTING_TRIGGERS = (
    "CHANGES_DOCUMENTED_FUNCTIONALITY",
    "EXISTING_BEHAVIOR_MUST_BE_UNDERSTOOD_OR_PRESERVED",
    "CONFIGURATION_SEMANTICS_UNESTABLISHED",
    "APPLICABILITY_NEEDS_CONFIRMATION",
    "BACKWARD_COMPATIBILITY_MATERIAL",
    "TERMINOLOGY_MATERIAL",
    "JIRA_EVIDENCE_INSUFFICIENT_DOC_MAY_ANSWER",
    "EVIDENCE_AGENT_REQUEST",
)

EVIDENCE_ROLES = (
    "EXISTING_BEHAVIOR",
    "REQUIREMENT_CLARIFICATION",
    "SUPPORTING_CONTEXT",
)

# The existing role that produces Doc Researcher results.
DOC_RESEARCHER_ROLE = "uac-doc-researcher"

# Fields a result must never carry: the Researcher does not author acceptance.
_FORBIDDEN_RESULT_FIELDS = (
    "ac_id",
    "acceptance_criteria",
    "acceptance_decision",
    "promoted_to_ac",
    "decides_scope",
)
# NOT_FOUND / absence is never evidence of the opposite behavior.
_FORBIDDEN_FINDING_FIELDS = (
    "absence_proves",
    "absence_is_negative_proof",
    "proves_absence",
)


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("doc_research"), dict)


def _nonempty(v):
    return bool(v.strip()) if isinstance(v, str) else bool(v)


def _validate_finding(result_index, finding_index, finding, behavior_new_ids):
    problems = []
    tag = f"doc_research.results[{result_index}].findings[{finding_index}]"
    if not isinstance(finding, dict):
        return [f"{tag}: each finding must be an object"]
    for field in ("claim", "source_id", "source_type", "authority",
                  "applicability"):
        if not _nonempty(finding.get(field)):
            problems.append(f"{tag}: missing {field}")
    role = finding.get("evidence_role")
    if role not in EVIDENCE_ROLES:
        problems.append(
            f"{tag}: evidence_role '{role}' must be one of "
            f"{', '.join(EVIDENCE_ROLES)}"
        )
    for field in _FORBIDDEN_FINDING_FIELDS:
        if finding.get(field):
            problems.append(
                f"{tag}: {field} is forbidden - absence of evidence is never "
                "evidence of the opposite behavior"
            )
    behavior_ref = finding.get("supports_behavior_ref")
    if (
        role == "EXISTING_BEHAVIOR"
        and behavior_ref
        and behavior_ref in behavior_new_ids
    ):
        problems.append(
            f"{tag}: existing documentation must not be cited as proof of new "
            f"behavior ('{behavior_ref}' is a NEW_REQUIREMENT)"
        )
    return problems


def _validate_result(i, result, behavior_new_ids):
    problems = []
    tag = f"doc_research.results[{i}]"
    if not isinstance(result, dict):
        return [f"{tag}: each result must be an object"]

    if not _nonempty(result.get("research_id")):
        problems.append(f"{tag}: missing research_id")
    status = result.get("status")
    if status not in TERMINAL_STATES:
        problems.append(
            f"{tag}: status '{status}' must be a terminal state: "
            f"{', '.join(sorted(TERMINAL_STATES))}"
        )
    produced_by = result.get("produced_by")
    if produced_by != DOC_RESEARCHER_ROLE:
        problems.append(
            f"{tag}: produced_by must name the existing Doc Researcher role "
            f"('{DOC_RESEARCHER_ROLE}') - the coordinator must not impersonate "
            "the Researcher"
        )
    topics = result.get("topics")
    if not isinstance(topics, list) or not topics:
        problems.append(f"{tag}: topics must be a non-empty list")
    question_refs = result.get("question_refs")
    if question_refs is not None and not isinstance(question_refs, list):
        problems.append(
            f"{tag}: question_refs must be a list when present - it binds the "
            "research to the questions it answered"
        )
    findings = result.get("findings")
    if not isinstance(findings, list):
        problems.append(f"{tag}: findings must be a list")
        findings = []
    source_ids = result.get("source_ids")
    if not isinstance(source_ids, list):
        problems.append(f"{tag}: source_ids must be a list")
        source_ids = []
    if not _nonempty(result.get("applicability")):
        problems.append(f"{tag}: missing applicability")
    for field in ("limitations", "conflicts"):
        if not isinstance(result.get(field), list):
            problems.append(f"{tag}: {field} must be a list (empty allowed)")
    for field in _FORBIDDEN_RESULT_FIELDS:
        if field in result and result[field]:
            problems.append(
                f"{tag}: {field} is forbidden - the Doc Researcher does not "
                "write ACs and does not decide final acceptance scope"
            )

    cited = set()
    for j, finding in enumerate(findings):
        problems.extend(_validate_finding(i, j, finding, behavior_new_ids))
        if isinstance(finding, dict) and _nonempty(finding.get("source_id")):
            cited.add(finding["source_id"])
    if cited and not cited.issubset(set(source_ids)):
        problems.append(
            f"{tag}: findings cite sources {sorted(cited - set(source_ids))} "
            "missing from source_ids"
        )
    if status == "DOC_RESEARCH_COMPLETED" and not findings:
        problems.append(
            f"{tag}: COMPLETED research requires at least one finding"
        )
    if status in {"DOC_RESEARCH_PARTIAL", "DOC_RESEARCH_UNAVAILABLE"} and not (
        result.get("limitations")
    ):
        problems.append(
            f"{tag}: {status} research must record what is missing in "
            "limitations - absence is never represented as complete"
        )
    if status == "DOC_RESEARCH_UNAVAILABLE" and findings:
        problems.append(
            f"{tag}: UNAVAILABLE research cannot produce findings"
        )
    if status == "DOC_RESEARCH_CONFLICTED" and not result.get("conflicts"):
        problems.append(
            f"{tag}: CONFLICTED research must retain the competing claims in "
            "conflicts"
        )
    return problems


def validate(manifest):
    if not is_present(manifest):
        return []
    block = manifest["doc_research"]
    routing = block.get("routing")
    if not isinstance(routing, dict):
        return ["doc_research.routing must be an object"]

    problems = []
    state = routing.get("state")
    if state not in ROUTING_STATES:
        problems.append(
            f"doc_research.routing.state '{state}' must be one of "
            f"{', '.join(ROUTING_STATES)}"
        )
        return problems
    triggers = routing.get("triggers", [])
    if not isinstance(triggers, list):
        problems.append("doc_research.routing.triggers must be a list")
        triggers = []
    unknown = [t for t in triggers if t not in ROUTING_TRIGGERS]
    if unknown:
        problems.append(
            f"doc_research.routing.triggers: unknown triggers {unknown} - use "
            f"{', '.join(ROUTING_TRIGGERS)}"
        )

    results = block.get("results", [])
    if not isinstance(results, list):
        problems.append("doc_research.results must be a list")
        results = []

    # New-requirement behaviors for the "docs never prove new behavior" rule.
    behavior_new_ids = set()
    classification = manifest.get("behavior_classification")
    if isinstance(classification, dict):
        for row in classification.get("items", []):
            if isinstance(row, dict) and row.get("behavior_class") == "NEW_REQUIREMENT":
                behavior_new_ids.add(row.get("target_ref"))

    if state == "RESEARCH_NOT_REQUIRED":
        if not _nonempty(routing.get("not_required_reason")):
            problems.append(
                "doc_research.routing: RESEARCH_NOT_REQUIRED requires "
                "not_required_reason explaining why documentation would not "
                "materially change acceptance reasoning"
            )
        if triggers:
            problems.append(
                "doc_research.routing: RESEARCH_NOT_REQUIRED cannot declare "
                "material triggers"
            )
        if results:
            problems.append(
                "doc_research: RESEARCH_NOT_REQUIRED cannot carry research "
                "results"
            )
    else:
        if not triggers:
            problems.append(
                "doc_research.routing: DOC_RESEARCH_REQUIRED requires at least "
                "one material trigger - never invoke the Doc Researcher merely "
                "because related documentation exists"
            )
        if state == "DOC_RESEARCH_REQUIRED":
            # HARD GATE: Coverage/Writer MUST NOT proceed without a terminal
            # Doc Researcher result.
            problems.append(
                "doc_research: DOC_RESEARCH_REQUIRED has no terminal Doc "
                "Researcher result - Coverage/Writer MUST NOT proceed"
            )
        elif not results:
            problems.append(
                f"doc_research: routing state {state} requires the Doc "
                "Researcher result that produced it"
            )
        else:
            if not any(row.get("status") == state for row in results
                       if isinstance(row, dict)):
                problems.append(
                    f"doc_research: routing state {state} has no matching "
                    "result status - PARTIAL research must not be represented "
                    "as complete, and vice versa"
                )
            research_id = routing.get("research_id")
            known_ids = {
                row.get("research_id") for row in results if isinstance(row, dict)
            }
            if _nonempty(research_id) and research_id not in known_ids:
                problems.append(
                    f"doc_research.routing: research_id '{research_id}' does "
                    "not reference a Doc Researcher result"
                )

    for i, result in enumerate(results):
        problems.extend(_validate_result(i, result, behavior_new_ids))

    # The Writer receives only admitted research through the existing
    # reasoning path.
    admitted = block.get("admitted_research_ids", [])
    if admitted:
        if not isinstance(admitted, list):
            problems.append("doc_research.admitted_research_ids must be a list")
            admitted = []
        known_ids = {
            row.get("research_id") for row in results if isinstance(row, dict)
        }
        for rid in admitted:
            if rid not in known_ids:
                problems.append(
                    f"doc_research.admitted_research_ids: '{rid}' is not a Doc "
                    "Researcher result - the Writer never receives arbitrary "
                    "raw search results"
                )
        if state == "RESEARCH_NOT_REQUIRED":
            problems.append(
                "doc_research.admitted_research_ids: nothing is admitted when "
                "research was not required"
            )
    return problems


def summarize(manifest):
    if not is_present(manifest):
        return "DocResearchRouting: NOT_PRESENT (backward-compatible)"
    problems = validate(manifest)
    block = manifest["doc_research"]
    state = (block.get("routing") or {}).get("state", "?")
    n = len(block.get("results", []) or [])
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"DocResearchRouting: {status} (state={state}, {n} result(s))"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(
        description="Doc Research routing gate (existing UAC Doc Researcher)"
    )
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
