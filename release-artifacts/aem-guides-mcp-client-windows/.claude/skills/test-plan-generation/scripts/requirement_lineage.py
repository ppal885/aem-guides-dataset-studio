"""Requirement Lineage gate - end-to-end AC traceability and integrity.

WHY THIS EXISTS
---------------
Every final AC must be mechanically traceable to the evidence that justified
it: Original Source -> Evidence -> Question -> Research (when required) ->
Question Resolution -> Sufficiency -> Coverage Decision -> Equivalence Group
(when applicable) -> Written AC -> Reviewer Decision.  This gate validates the
manifest `requirement_lineage` block and its referential integrity against the
R1/Q1/S1/C1/E1 blocks.  It adds traceability and integrity only - it
introduces no new acceptance semantics.

ID strategy: existing production IDs are preserved (question_id, research_id,
coverage_id, merge/equivalence id, ac_id); the lineage block records the
conceptual families SRC- (original source) and REV- (review decision) and
references the existing IDs without rewriting them.

Rules enforced (all generic; structural integrity only - lineage proves
provenance, not semantic correctness):

- Every referenced ID exists in the producing block; the ID's type is valid
  for the relation.
- Every admitted evidence item traces to an original source; a question never
  cites a nonexistent evidence or research ID; unsuccessful research stays
  visible (TBD lineage) instead of being erased.
- AC lineage binds to admitted ACCEPTANCE coverage and preserves the exact
  question/evidence/research unions of the coverage decisions and equivalence
  groups it references; unrelated evidence never contaminates an AC.
- A QE_REGRESSION member of an equivalence group never becomes acceptance
  authority through the group - the AC's acceptance coverage must include an
  ACCEPTANCE-class member.
- Human-facing Source lines derive only from the admitted supporting source
  lineage and never contain internal IDs (Q-, COV-, SUF-, EQ-, DR-, canonical
  outcome, attestations).
- The Reviewer binds to the exact Writer revision; a Writer change or a
  source/question revision change makes the dependent lineage/review stale.
- Every Writer-package AC has complete lineage; an unresolved ACCEPTANCE_TBD
  question keeps a TBD lineage record (question, research attempt, partial or
  insufficient result, reason, refs) and never references an AC.

Backward-compatible: absent `requirement_lineage` -> clean pass.
Generic only. Stdlib only.
"""
from __future__ import annotations

import re

from question_resolver import ANSWER_AUTHORITIES

SOURCE_TYPES = (
    "JIRA_ACCEPTANCE_CRITERIA",
    "JIRA_EXPECTED_RESULT",
    "JIRA_DESCRIPTION",
    "JIRA_COMMENT",
    "JIRA_ATTACHMENT",
    "OFFICIAL_PRODUCT_DOC",
    "SPECIFICATION",
    "IMPLEMENTATION",
    "HISTORICAL_JIRA",
    "OTHER_APPROVED_SOURCE",
)

SOURCE_STATUSES = ("ADMITTED", "RETRIEVED", "REJECTED", "UNAVAILABLE")

REVIEW_DECISIONS = ("APPROVED", "REJECTED", "CHANGES_REQUESTED")

TBD_RESEARCH_STATES = ("PARTIAL", "NOT_FOUND", "SOURCE_UNAVAILABLE", "CONFLICTED")

# Internal IDs and machinery that must never leak into human UAC output.
_INTERNAL_JARGON_RE = re.compile(
    r"\b(?:Q|COV|SUF|EQ|DR|EV|SRC|REV|MERGE)-[A-Za-z0-9]"
    r"|canonical_outcome|semantic attestation",
    re.IGNORECASE,
)


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(
        manifest.get("requirement_lineage"), dict
    )


def _nonempty(v):
    return bool(v.strip()) if isinstance(v, str) else bool(v)


def _chain_context(manifest):
    """Collect the existing R1/Q1/S1/C1/E1 blocks for referential checks."""

    ctx = {}
    plan = manifest.get("question_plan")
    ctx["questions"] = {}
    if isinstance(plan, dict):
        for source in (plan.get("items"),
                       (plan.get("overflow") or {}).get("items")):
            if isinstance(source, list):
                for row in source:
                    if isinstance(row, dict) and row.get("question_id"):
                        ctx["questions"][row["question_id"]] = row
    resolutions = manifest.get("question_resolutions")
    ctx["resolutions"] = {}
    if isinstance(resolutions, dict):
        for row in resolutions.get("items", []):
            if isinstance(row, dict):
                ref = row.get("question_ref") or row.get("question_id")
                if ref:
                    ctx["resolutions"][ref] = row
    research = manifest.get("question_research")
    ctx["question_research"] = {}
    if isinstance(research, dict):
        for row in research.get("items", []):
            if isinstance(row, dict) and row.get("question_ref"):
                ctx["question_research"][row["question_ref"]] = row
    doc_research = manifest.get("doc_research")
    ctx["doc_results"] = {}
    if isinstance(doc_research, dict):
        for row in doc_research.get("results", []):
            if isinstance(row, dict) and row.get("research_id"):
                ctx["doc_results"][row["research_id"]] = row
    coverage = manifest.get("coverage_decisions")
    ctx["coverage"] = {}
    ctx["handoff"] = None
    if isinstance(coverage, dict):
        for row in coverage.get("items", []):
            if isinstance(row, dict) and row.get("coverage_id"):
                ctx["coverage"][row["coverage_id"]] = row
        if isinstance(coverage.get("writer_handoff"), list):
            ctx["handoff"] = set(coverage["writer_handoff"])
    equivalence = manifest.get("coverage_equivalence")
    ctx["merges"] = {}
    if isinstance(equivalence, dict):
        for row in equivalence.get("merges", []):
            if isinstance(row, dict):
                mid = row.get("equivalence_id") or row.get("merge_id")
                if mid:
                    ctx["merges"][mid] = row
    writer = manifest.get("writer_package")
    ctx["writer_acs"] = {}
    if isinstance(writer, dict):
        for row in writer.get("acs", []):
            if isinstance(row, dict) and row.get("ac_id"):
                ctx["writer_acs"][row["ac_id"]] = row
    return ctx


def _merge_members(merge):
    return list(merge.get("coverage_refs") or merge.get("merged_coverage_ids") or [])


def _validate_sources(block):
    problems = []
    sources = block.get("sources", [])
    if not isinstance(sources, list):
        return ["requirement_lineage.sources must be a list"], {}
    seen = set()
    evidence_to_source = {}
    for i, row in enumerate(sources):
        tag = f"requirement_lineage.sources[{i}]"
        if not isinstance(row, dict):
            problems.append(f"{tag}: each source must be an object")
            continue
        source_id = row.get("source_id")
        if not _nonempty(source_id):
            problems.append(f"{tag}: missing source_id")
        elif source_id in seen:
            problems.append(f"{tag}: duplicate source_id '{source_id}'")
        seen.add(source_id)
        if row.get("source_type") not in SOURCE_TYPES:
            problems.append(
                f"{tag}: source_type '{row.get('source_type')}' must be one of "
                f"{', '.join(SOURCE_TYPES)}"
            )
        authority_role = row.get("authority_role")
        if authority_role is not None and authority_role not in ANSWER_AUTHORITIES:
            problems.append(
                f"{tag}: authority_role '{authority_role}' must reuse the "
                "existing answer-authority vocabulary"
            )
        status = row.get("status")
        if status not in SOURCE_STATUSES:
            problems.append(
                f"{tag}: status '{status}' must be one of "
                f"{', '.join(SOURCE_STATUSES)}"
            )
        evidence_ids = row.get("evidence_ids")
        if not isinstance(evidence_ids, list):
            problems.append(
                f"{tag}: evidence_ids must be a list - every admitted evidence "
                "item traces to an original source"
            )
            evidence_ids = []
        for evidence_id in evidence_ids:
            if evidence_id in evidence_to_source:
                problems.append(
                    f"{tag}: evidence '{evidence_id}' is already traced to "
                    f"'{evidence_to_source[evidence_id]}'"
                )
            evidence_to_source[evidence_id] = source_id
    return problems, evidence_to_source


def _validate_ac_lineage(i, row, ctx, evidence_to_source, admitted_source_ids,
                         source_versions):
    problems = []
    tag = f"requirement_lineage.ac_lineage[{i}]"
    if not isinstance(row, dict):
        return [f"{tag}: each AC lineage must be an object"]
    ac_id = row.get("ac_id")
    if not _nonempty(ac_id):
        problems.append(f"{tag}: missing ac_id")
    if ctx["writer_acs"] and ac_id not in ctx["writer_acs"]:
        problems.append(
            f"{tag}: '{ac_id}' is not an admitted Writer AC - the Writer must "
            "not invent lineage IDs"
        )

    coverage_refs = row.get("coverage_refs") or []
    equivalence_refs = row.get("equivalence_refs") or []
    question_refs = row.get("question_refs") or []
    evidence_refs = row.get("evidence_refs") or []
    research_refs = row.get("research_refs") or []
    source_refs = row.get("source_refs") or []

    if not coverage_refs:
        problems.append(
            f"{tag}: every final AC binds to admitted coverage - coverage_refs "
            "is required"
        )
    for cid in coverage_refs:
        coverage = ctx["coverage"].get(cid)
        if coverage is None:
            problems.append(f"{tag}: coverage_ref '{cid}' does not exist")
            continue
        if coverage.get("coverage_class") != "ACCEPTANCE":
            problems.append(
                f"{tag}: coverage '{cid}' is "
                f"{coverage.get('coverage_class')} - AC lineage binds to "
                "admitted ACCEPTANCE coverage only"
            )
        if ctx["handoff"] is not None and cid not in ctx["handoff"]:
            problems.append(
                f"{tag}: coverage '{cid}' was never admitted to the Writer"
            )
    for merge_id in equivalence_refs:
        if merge_id not in ctx["merges"]:
            problems.append(
                f"{tag}: equivalence_ref '{merge_id}' does not exist"
            )

    # The lineage must equal the exact unions of what it references.
    member_coverages = [
        ctx["coverage"][cid] for cid in coverage_refs if cid in ctx["coverage"]
    ]
    member_merges = [ctx["merges"][m] for m in equivalence_refs if m in ctx["merges"]]
    for merge in member_merges:
        for cid in _merge_members(merge):
            if cid in ctx["coverage"]:
                member_coverages.append(ctx["coverage"][cid])
    expected_questions = sorted({
        qid for row in member_coverages for qid in (row.get("question_ids") or [])
    })
    if member_coverages and sorted(set(question_refs)) != expected_questions:
        problems.append(
            f"{tag}: question_refs must equal the referenced coverage/equivalence "
            f"questions {expected_questions} - no fabricated or dropped lineage"
        )
    expected_evidence = sorted({
        eid for row in member_coverages for eid in (row.get("evidence_ids") or [])
    })
    if member_coverages and sorted(set(evidence_refs)) != expected_evidence:
        problems.append(
            f"{tag}: evidence_refs must equal the referenced evidence "
            f"{expected_evidence} - unrelated evidence never contaminates an AC"
        )
    expected_research = sorted({
        rid for row in member_coverages for rid in (row.get("research_ids") or [])
    })
    if member_coverages and sorted(set(research_refs)) != expected_research:
        problems.append(
            f"{tag}: research_refs must cover the referenced research "
            f"{expected_research} - Doc Research contribution stays visible "
            "when actually used"
        )
    for qid in question_refs:
        if ctx["questions"] and qid not in ctx["questions"]:
            problems.append(f"{tag}: question_ref '{qid}' does not exist")
    for rid in research_refs:
        if ctx["doc_results"] and rid not in ctx["doc_results"]:
            problems.append(
                f"{tag}: research_ref '{rid}' is not a Doc Researcher result"
            )

    # A QE_REGRESSION member never becomes acceptance authority through a
    # group: the AC's acceptance coverage must include an ACCEPTANCE member.
    for merge_id in equivalence_refs:
        merge = ctx["merges"].get(merge_id)
        if merge is None:
            continue
        members = [
            ctx["coverage"][cid]
            for cid in _merge_members(merge)
            if cid in ctx["coverage"]
        ]
        acceptance_members = {
            row["coverage_id"]
            for row in members
            if row.get("coverage_class") == "ACCEPTANCE"
        }
        if acceptance_members and not (set(coverage_refs) & acceptance_members):
            problems.append(
                f"{tag}: equivalence group '{merge_id}' is grounded here only "
                "through regression members - QE_REGRESSION never becomes "
                "acceptance authority through a merge"
            )

    # Source binding and human Source lines.
    if evidence_to_source:
        for eid in evidence_refs:
            if eid not in evidence_to_source:
                problems.append(
                    f"{tag}: evidence '{eid}' traces to no original source"
                )
        expected_sources = sorted({
            evidence_to_source[eid]
            for eid in evidence_refs
            if eid in evidence_to_source
        })
        if sorted(set(source_refs)) != expected_sources:
            problems.append(
                f"{tag}: source_refs must be exactly the admitted sources "
                f"behind the evidence {expected_sources} - an unused retrieved "
                "source never appears in a Source line"
            )
    for sid in source_refs:
        if admitted_source_ids is not None and sid not in admitted_source_ids:
            problems.append(
                f"{tag}: source '{sid}' is unknown or not ADMITTED"
            )
    human_line = row.get("human_source_line")
    if human_line is not None:
        if not str(human_line).startswith("Source:"):
            problems.append(
                f"{tag}: human_source_line must follow the human 'Source: ...' "
                "form"
            )
        if _INTERNAL_JARGON_RE.search(str(human_line)):
            problems.append(
                f"{tag}: human_source_line contains internal lineage jargon - "
                "normal UAC output never exposes internal IDs"
            )
    if not _nonempty(row.get("writer_revision")):
        problems.append(
            f"{tag}: missing writer_revision - the Reviewer binds to the exact "
            "Writer draft"
        )
    recorded_versions = row.get("source_versions") or {}
    for sid, version in recorded_versions.items():
        current = source_versions.get(sid)
        if current is not None and current != version:
            problems.append(
                f"{tag}: source '{sid}' moved from {version} to {current} - a "
                "source revision invalidates the dependent lineage"
            )
    return problems


def validate(manifest):
    if not is_present(manifest):
        return []
    block = manifest["requirement_lineage"]
    ctx = _chain_context(manifest)

    problems = []
    source_problems, evidence_to_source = _validate_sources(block)
    problems.extend(source_problems)
    sources = block.get("sources", [])
    admitted_source_ids = None
    source_versions = {}
    if isinstance(sources, list):
        admitted_source_ids = {
            row.get("source_id")
            for row in sources
            if isinstance(row, dict) and row.get("status") == "ADMITTED"
        }
        source_versions = {
            row["source_id"]: row["source_version"]
            for row in sources
            if isinstance(row, dict)
            and row.get("source_id")
            and row.get("source_version") is not None
        }

    # Question lineage: a question never cites nonexistent evidence/research.
    if evidence_to_source:
        known_evidence = set(evidence_to_source)
        for qid, question in ctx["questions"].items():
            for eid in question.get("triggering_evidence_ids") or []:
                if eid not in known_evidence:
                    problems.append(
                        f"requirement_lineage: question '{qid}' cites "
                        f"nonexistent evidence '{eid}'"
                    )

    # Complete lineage for every final AC.
    seen_acs = set()
    ac_revisions = {}
    ac_lineage = block.get("ac_lineage", [])
    if not isinstance(ac_lineage, list):
        problems.append("requirement_lineage.ac_lineage must be a list")
        ac_lineage = []
    for i, row in enumerate(ac_lineage):
        problems.extend(
            _validate_ac_lineage(
                i, row, ctx, evidence_to_source, admitted_source_ids,
                source_versions,
            )
        )
        if isinstance(row, dict):
            ac_id = row.get("ac_id")
            if ac_id:
                if ac_id in seen_acs:
                    problems.append(
                        f"requirement_lineage.ac_lineage[{i}]: duplicate ac_id "
                        f"'{ac_id}'"
                    )
                seen_acs.add(ac_id)
                ac_revisions[ac_id] = row.get("writer_revision")
    if ctx["writer_acs"]:
        for ac_id in sorted(set(ctx["writer_acs"]) - seen_acs):
            problems.append(
                f"requirement_lineage: Writer AC '{ac_id}' has no lineage - "
                "every final AC must be mechanically traceable"
            )

    # TBD lineage: unresolved acceptance questions remain visible.
    tbd_lineage = block.get("tbd_lineage", [])
    if not isinstance(tbd_lineage, list):
        problems.append("requirement_lineage.tbd_lineage must be a list")
        tbd_lineage = []
    seen_tbd = set()
    for i, row in enumerate(tbd_lineage):
        tag = f"requirement_lineage.tbd_lineage[{i}]"
        if not isinstance(row, dict):
            problems.append(f"{tag}: each TBD record must be an object")
            continue
        qid = row.get("question_ref")
        if not _nonempty(qid):
            problems.append(f"{tag}: missing question_ref")
        if qid:
            if qid in seen_tbd:
                problems.append(f"{tag}: duplicate TBD record for '{qid}'")
            seen_tbd.add(qid)
            resolution = ctx["resolutions"].get(qid)
            if resolution is not None:
                status = resolution.get("status") or resolution.get("disposition")
                if status != "ACCEPTANCE_TBD":
                    problems.append(
                        f"{tag}: question '{qid}' resolved {status} - TBD "
                        "lineage is only for unresolved acceptance dimensions"
                    )
        research_status = row.get("research_status")
        if research_status is not None and research_status not in (
            TBD_RESEARCH_STATES
        ):
            problems.append(
                f"{tag}: research_status '{research_status}' must be one of "
                f"{', '.join(TBD_RESEARCH_STATES)}"
            )
        for rid in row.get("research_refs") or []:
            if ctx["doc_results"] and rid not in ctx["doc_results"]:
                problems.append(
                    f"{tag}: research_ref '{rid}' is not a Doc Researcher "
                    "result - unsuccessful research stays visible, never "
                    "fabricated"
                )
        if not _nonempty(row.get("reason_unresolved")):
            problems.append(
                f"{tag}: reason_unresolved is required - the TBD explanation "
                "is why it exists"
            )
        if row.get("ac_refs"):
            problems.append(
                f"{tag}: an unresolved path never references a confirmed AC"
            )
    if ctx["resolutions"]:
        for qid, resolution in sorted(ctx["resolutions"].items()):
            status = resolution.get("status") or resolution.get("disposition")
            if status == "ACCEPTANCE_TBD" and qid not in seen_tbd:
                problems.append(
                    f"requirement_lineage: ACCEPTANCE_TBD question '{qid}' has "
                    "no TBD lineage - unresolved paths never disappear"
                )

    # Review lineage: the Reviewer binds to the exact Writer revision.
    reviews = block.get("reviews", [])
    if not isinstance(reviews, list):
        problems.append("requirement_lineage.reviews must be a list")
        reviews = []
    seen_reviews = set()
    for i, row in enumerate(reviews):
        tag = f"requirement_lineage.reviews[{i}]"
        if not isinstance(row, dict):
            problems.append(f"{tag}: each review must be an object")
            continue
        review_id = row.get("review_id")
        if not _nonempty(review_id):
            problems.append(f"{tag}: missing review_id")
        elif review_id in seen_reviews:
            problems.append(f"{tag}: duplicate review_id '{review_id}'")
        seen_reviews.add(review_id)
        if row.get("decision") not in REVIEW_DECISIONS:
            problems.append(
                f"{tag}: decision '{row.get('decision')}' must be one of "
                f"{', '.join(REVIEW_DECISIONS)}"
            )
        reviewed_revision = row.get("reviewed_writer_revision")
        if not _nonempty(reviewed_revision):
            problems.append(
                f"{tag}: missing reviewed_writer_revision - the Reviewer binds "
                "to the exact Writer draft"
            )
        for ac_id in row.get("ac_ids") or []:
            if seen_acs and ac_id not in seen_acs:
                problems.append(
                    f"{tag}: reviewed AC '{ac_id}' has no lineage"
                )
            current_revision = ac_revisions.get(ac_id)
            if (
                current_revision is not None
                and reviewed_revision
                and current_revision != reviewed_revision
            ):
                problems.append(
                    f"{tag}: AC '{ac_id}' was revised to {current_revision} "
                    f"after review of {reviewed_revision} - approval is never "
                    "reused across changed drafts"
                )
    return problems


def trace_ac(manifest, ac_id):
    """Answer "why is this AC here?" from the lineage artifact (audit output)."""

    block = manifest.get("requirement_lineage") or {}
    rows = block.get("ac_lineage") or []
    row = next((r for r in rows if isinstance(r, dict)
                and r.get("ac_id") == ac_id), None)
    if row is None:
        return [f"{ac_id}: no lineage"]
    lines = [f"{ac_id} <- coverage {row.get('coverage_refs')}"]
    if row.get("equivalence_refs"):
        lines.append(f"  merged through {row['equivalence_refs']}")
    lines.append(f"  <- questions {row.get('question_refs')}")
    if row.get("research_refs"):
        lines.append(f"  <- research {row['research_refs']}")
    lines.append(f"  <- evidence {row.get('evidence_refs')}")
    lines.append(f"  <- sources {row.get('source_refs')}")
    lines.append(f"  writer_revision={row.get('writer_revision')}")
    return lines


def summarize(manifest):
    if not is_present(manifest):
        return "RequirementLineage: NOT_PRESENT (backward-compatible)"
    problems = validate(manifest)
    block = manifest["requirement_lineage"]
    s = len(block.get("sources", []) or [])
    a = len(block.get("ac_lineage", []) or [])
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"RequirementLineage: {status} ({s} source(s), {a} AC lineage(s))"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(
        description="Requirement Lineage gate for end-to-end AC traceability"
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
