"""Convergence evaluation: the virtual refinement team.

After mandated research resolves and before coverage finalizes, evaluate the
collected evidence for each material question from three explicit
perspectives:

- Product/PM  - the intended product contract (requirement-clarification and
  desired-behavior findings, ticket statements).
- Developer   - implementation states, constraints and branches established
  by code (implementation-evidence findings).
- QE          - observable behavior, negative cases, regression implications
  (observed-behavior findings plus worker limitations).

The stage identifies agreements, conflicts, and acceptance-changing
unknowns.  It is deterministic and advisory: it never invents a product
decision, and no convergence output changes evidence authority - the
resolver/sufficiency/promotion gates are untouched.
"""

from __future__ import annotations

import re

from app.core.schemas_canonical_test_plan_runtime import (
    ConvergenceRecord,
    ConvergenceStatus,
    ResearchFindingEvidenceRole,
    ResearchWorkerStatus,
)

_PM_ROLES = {
    ResearchFindingEvidenceRole.REQUIREMENT_CLARIFICATION,
    ResearchFindingEvidenceRole.DESIRED_BEHAVIOR,
    # Documented current behavior is the product's existing contract; it sits
    # with the PM/product view of what the product intends.
    ResearchFindingEvidenceRole.EXISTING_BEHAVIOR,
}
_DEV_ROLES = {ResearchFindingEvidenceRole.IMPLEMENTATION_EVIDENCE}
_QE_ROLES = {ResearchFindingEvidenceRole.OBSERVED_BEHAVIOR}

_UNKNOWN_STATUSES = {
    ResearchWorkerStatus.NOT_FOUND,
    ResearchWorkerStatus.NO_RELEVANT_EVIDENCE,
    ResearchWorkerStatus.SOURCE_UNAVAILABLE,
}

_MAX_VIEW_ITEMS = 3
_TOKEN_RE = re.compile(r"[a-z][a-z0-9-]{2,}")

# Conflict classification (decision semantics): only a genuine
# product-authority conflict may produce a human product-decision
# question/TBD.  A fix-clarification-vs-code disagreement is a
# REQUIREMENT_IMPLEMENTATION_MISMATCH: the established requirement stands
# and the mismatch is an implementation finding for the Developer
# perspective - QE is never asked to choose between established product
# intent and current implementation merely because the code differs.
CONFLICT_PRODUCT_CONTRACT = "PRODUCT_CONTRACT"
CONFLICT_IMPLEMENTATION = "IMPLEMENTATION"
CONFLICT_REQUIREMENT_IMPLEMENTATION_MISMATCH = (
    "REQUIREMENT_IMPLEMENTATION_MISMATCH"
)
CONFLICT_LIFECYCLE_CURRENTNESS = "LIFECYCLE_CURRENTNESS"
CONFLICT_EVIDENCE_QUALITY = "EVIDENCE_QUALITY"
_ACCEPTANCE_CHANGING_CONFLICTS = {
    CONFLICT_PRODUCT_CONTRACT,
}
# Conflicts that stay in the implementation/development lane.
_IMPLEMENTATION_LANE_CONFLICTS = {
    CONFLICT_IMPLEMENTATION,
    CONFLICT_REQUIREMENT_IMPLEMENTATION_MISMATCH,
}

_EVIDENCE_QUALITY_SIGNALS = (
    "truncat", "unreadable", "metadata only", "not supplied", "not opened",
    "cannot be verified", "could not be verified", "could not verify",
    "cannot verify", "unavailable", "absence of",
)
_LIFECYCLE_SIGNALS = (
    "fixed by", "in progress", "shipped", "release", "merged", "delivered",
    "current product", "current build", "status", "version", "backport",
)
# Implementation conflicts are about a behavioral mismatch between a claim
# and code: they need a code anchor AND a behavior verb.  The bare word
# "implementation" is not an anchor (lifecycle prose uses it too).
_IMPLEMENTATION_ANCHORS = (
    "code at", "at head", "revision", ".java", ".py", ".ts", ".jsx",
    "class ", "method", "function", "line ", "commit", "repo",
)
_IMPLEMENTATION_BEHAVIOR_VERBS = (
    "sets ", "flags", "asserts", "does not", "only on", "only flags",
    "reads ", "writes ", "returns ", "computes", "derives", "branches",
)
# Ticket-side authority signals: the conflicting claim comes from the
# ticket's own requirement/fix narrative, so the conflict is requirement
# vs implementation, not code vs code.
_TICKET_AUTHORITY_SIGNALS = (
    "jira", "comment", "fix comment", "ticket", "description states",
    "uac", "requirement", "acceptance",
)


def _compile_signals(signals: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    """Word-boundary matchers for one signal family.

    Naive substring matching let a short anchor fire inside an unrelated
    word: "repo" matched "Topic List report", so a pure
    documentation-versus-ticket conflict was classified as a code mismatch
    and routed to the implementation lane, where the reader never saw it.
    """

    compiled: list[re.Pattern[str]] = []
    for signal in signals:
        token = signal.strip()
        if not token:
            continue
        prefix = r"\b" if token[:1].isalnum() else ""
        suffix = r"\b" if token[-1:].isalnum() else ""
        compiled.append(re.compile(prefix + re.escape(token) + suffix))
    return tuple(compiled)


_EVIDENCE_QUALITY_RE = _compile_signals(_EVIDENCE_QUALITY_SIGNALS)
_LIFECYCLE_RE = _compile_signals(_LIFECYCLE_SIGNALS)
_IMPLEMENTATION_ANCHORS_RE = _compile_signals(_IMPLEMENTATION_ANCHORS)
_IMPLEMENTATION_BEHAVIOR_VERBS_RE = _compile_signals(_IMPLEMENTATION_BEHAVIOR_VERBS)
_TICKET_AUTHORITY_RE = _compile_signals(_TICKET_AUTHORITY_SIGNALS)


def _classify_conflict(text: str) -> str:
    """Classify one conflict statement.  Generic signal matching only - the
    class decides whether the conflict can change the acceptance contract,
    never whether the conflict is real."""

    lowered = (text or "").casefold()

    def _hits(patterns: tuple[re.Pattern[str], ...]) -> int:
        return sum(1 for pattern in patterns if pattern.search(lowered))

    # A strong implementation conflict (code anchor + behavior verb) wins
    # over an incidental evidence-quality mention inside the same sentence
    # (for example "code sets the flag only on Error ... excerpt truncated").
    strong_impl = _hits(_IMPLEMENTATION_ANCHORS_RE) and _hits(
        _IMPLEMENTATION_BEHAVIOR_VERBS_RE
    )
    if strong_impl:
        if _hits(_TICKET_AUTHORITY_RE):
            return CONFLICT_REQUIREMENT_IMPLEMENTATION_MISMATCH
        return CONFLICT_IMPLEMENTATION
    if _hits(_EVIDENCE_QUALITY_RE):
        return CONFLICT_EVIDENCE_QUALITY
    if _hits(_LIFECYCLE_RE):
        return CONFLICT_LIFECYCLE_CURRENTNESS
    if _hits(_IMPLEMENTATION_ANCHORS_RE):
        return CONFLICT_IMPLEMENTATION
    return CONFLICT_PRODUCT_CONTRACT


def _build_decision(
    agreements: list[str],
    pm_view: list[str],
    contract_conflicts: list[str],
    unknowns: list[str],
) -> str:
    """Convert a residual acceptance-changing uncertainty into one concrete
    product decision: what the evidence already establishes, what remains
    undecided, and what QE must decide.  Never the raw Jira problem
    prose."""

    parts: list[str] = []
    undecided = contract_conflicts[0] if contract_conflicts else unknowns[0]
    # The established anchor is the view item closest to the undecided
    # point, not merely the first view item.
    pool = list(agreements) or list(pm_view)
    established = ""
    if pool:
        undecided_tokens = _tokens(undecided)
        established = max(
            pool,
            key=lambda claim: _overlap_ratio(_tokens(claim), undecided_tokens),
        )
    if established:
        parts.append(f"Established by evidence: {established[:360]}")
    parts.append(f"Undecided: {undecided[:360]}")
    parts.append(
        "Decision needed: which interpretation defines the acceptance "
        "expectation for this question."
    )
    return " ".join(parts)[:1200]


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").casefold()))


def _overlap_ratio(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    # Overlap coefficient: shared substance relative to the smaller claim.
    return len(left & right) / max(1, min(len(left), len(right)))


class ConvergenceService:
    def evaluate(
        self,
        questions: list,
        research_records: list,
        worker_results: list,
    ) -> list[ConvergenceRecord]:
        by_question: dict[str, list] = {}
        for result in worker_results:
            by_question.setdefault(result.question_id, []).append(result)

        research_by_question = {
            row.question_id: row for row in (research_records or [])
        }
        records: list[ConvergenceRecord] = []
        for question in questions:
            results = by_question.get(question.question_id, [])
            research = research_by_question.get(question.question_id)
            if not results and research is None:
                continue

            pm_view: list[str] = []
            dev_view: list[str] = []
            qe_view: list[str] = []
            conflicts: list[str] = []
            unknowns: list[str] = []
            saw_partial = False
            saw_conflict = False
            # PM view priority: documented existing behavior first, then
            # requirement clarifications, then customer-stated desires.
            pm_bucketed: dict[ResearchFindingEvidenceRole, list[str]] = {
                role: [] for role in _PM_ROLES
            }
            for result in results:
                for finding in result.findings:
                    claim = str(finding.claim).strip()
                    if len(claim) > 400:
                        claim = claim[:400].rsplit(" ", 1)[0].rstrip() + "…"
                    if not claim:
                        continue
                    if finding.evidence_role in _PM_ROLES:
                        bucket = pm_bucketed[finding.evidence_role]
                        if len(bucket) < _MAX_VIEW_ITEMS:
                            bucket.append(claim)
                    elif finding.evidence_role in _DEV_ROLES and len(dev_view) < _MAX_VIEW_ITEMS:
                        dev_view.append(claim)
                    elif finding.evidence_role in _QE_ROLES and len(qe_view) < _MAX_VIEW_ITEMS:
                        qe_view.append(claim)
                for conflict in result.conflicts:
                    text = str(conflict).strip()
                    if text:
                        conflicts.append(text[:500])
                if result.status == ResearchWorkerStatus.CONFLICTED:
                    saw_conflict = True
                if result.status == ResearchWorkerStatus.PARTIAL:
                    saw_partial = True
                if result.status in _UNKNOWN_STATUSES:
                    reason = (
                        result.limitations[0][:300]
                        if result.limitations
                        else "research returned no answer"
                    )
                    unknowns.append(f"{result.status.value}: {reason}")
            # A question whose mandated research never answered is an
            # acceptance-changing unknown even when no worker row exists.
            if (
                research is not None
                and research.research_status.value in {"NOT_FOUND", "SOURCE_UNAVAILABLE"}
                and not unknowns
            ):
                unknowns.append(f"{research.research_status.value}: {research.reason[:300]}")

            # PM view priority: documented existing behavior first, then
            # requirement clarifications, then customer-stated desires.
            pm_view = [
                claim
                for role in (
                    ResearchFindingEvidenceRole.EXISTING_BEHAVIOR,
                    ResearchFindingEvidenceRole.REQUIREMENT_CLARIFICATION,
                    ResearchFindingEvidenceRole.DESIRED_BEHAVIOR,
                )
                for claim in pm_bucketed[role]
            ][:_MAX_VIEW_ITEMS]

            agreements: list[str] = []
            for pm_claim in pm_view:
                pm_tokens = _tokens(pm_claim)
                for other in dev_view + qe_view:
                    if _overlap_ratio(pm_tokens, _tokens(other)) >= 0.5:
                        agreements.append(pm_claim)
                        break

            conflicts = sorted(set(conflicts))
            conflict_classes = [_classify_conflict(text) for text in conflicts]
            contract_conflicts = [
                text
                for text, conflict_class in zip(conflicts, conflict_classes)
                if conflict_class in _ACCEPTANCE_CHANGING_CONFLICTS
            ]
            # Implementation-lane conflicts (code-internal contradictions and
            # requirement-vs-code mismatches) are Developer-perspective
            # findings: recorded, never turned into human product decisions.
            implementation_findings = [
                text
                for text, conflict_class in zip(conflicts, conflict_classes)
                if conflict_class in _IMPLEMENTATION_LANE_CONFLICTS
            ]
            unknowns = sorted(set(unknowns))
            # G2: a research unknown is acceptance-changing only when the
            # question has no establishing answer.  When research already
            # established documented existing behavior or the customer-stated
            # desired behavior, a remaining NOT_FOUND / SOURCE_UNAVAILABLE is
            # an evidence limitation, not a product decision.
            answered = bool(
                pm_bucketed[ResearchFindingEvidenceRole.EXISTING_BEHAVIOR]
                or pm_bucketed[ResearchFindingEvidenceRole.DESIRED_BEHAVIOR]
            )
            unknowns_acceptance_changing = bool(unknowns) and not answered
            # Only product-contract and implementation conflicts can change
            # the acceptance contract.  A lifecycle/currentness conflict (for
            # example "Fixed by" beside an In Progress linked issue) caps
            # shipped/current claims but never blocks an otherwise
            # established behavioral contract; evidence-quality conflicts cap
            # confidence only.
            acceptance_changing = bool(contract_conflicts) or (
                unknowns_acceptance_changing
            )

            if contract_conflicts or (saw_conflict and not conflicts):
                # CONFLICTED requires an acceptance-changing contract
                # conflict; a worker-level CONFLICTED with no classifiable
                # conflict text stays conservative.  Implementation-lane and
                # lifecycle/evidence conflicts converge with limits.
                status = ConvergenceStatus.CONFLICTED
            elif unknowns_acceptance_changing:
                status = ConvergenceStatus.UNRESOLVED
            elif saw_partial or conflicts or unknowns:
                status = ConvergenceStatus.CONVERGED_WITH_LIMITS
            else:
                status = ConvergenceStatus.CONVERGED

            decision = ""
            if acceptance_changing and status in {
                ConvergenceStatus.CONFLICTED,
                ConvergenceStatus.UNRESOLVED,
            }:
                decision = _build_decision(
                    sorted(set(agreements)),
                    pm_view,
                    contract_conflicts,
                    unknowns,
                )

            records.append(
                ConvergenceRecord(
                    question_id=question.question_id,
                    pm_view=pm_view,
                    dev_view=dev_view,
                    qe_view=qe_view,
                    agreements=sorted(set(agreements)),
                    conflicts=conflicts,
                    conflict_classes=conflict_classes,
                    implementation_findings=sorted(set(implementation_findings)),
                    acceptance_changing_unknowns=unknowns,
                    acceptance_changing=acceptance_changing,
                    decision=decision,
                    status=status,
                )
            )
        return records


CONVERGENCE_SERVICE = ConvergenceService()
