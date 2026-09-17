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
                    conflicts.append(str(conflict)[:500])
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

            if saw_conflict or conflicts:
                status = ConvergenceStatus.CONFLICTED
            elif unknowns:
                status = ConvergenceStatus.UNRESOLVED
            elif saw_partial:
                status = ConvergenceStatus.CONVERGED_WITH_LIMITS
            else:
                status = ConvergenceStatus.CONVERGED

            records.append(
                ConvergenceRecord(
                    question_id=question.question_id,
                    pm_view=pm_view,
                    dev_view=dev_view,
                    qe_view=qe_view,
                    agreements=sorted(set(agreements)),
                    conflicts=sorted(set(conflicts)),
                    acceptance_changing_unknowns=sorted(set(unknowns)),
                    status=status,
                )
            )
        return records


CONVERGENCE_SERVICE = ConvergenceService()
