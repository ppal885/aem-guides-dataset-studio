"""Offline acceptance-stage regression; this does not simulate the full runtime.

Oracle: references/map-collection-publishing-evidence.md (cb55d104).
The retrieved claims below are deliberately wrong synthetic summaries, not Adobe
documentation. Document verification must not establish their ticket applicability.
Run from the repository root with:
    PYTHONPATH=backend python -m unittest discover -s backend/tests \
        -p test_map_collection_evidence_boundary.py -v
"""

from __future__ import annotations

import unittest

from app.core.schemas_canonical_test_plan_runtime import (
    AuthorityClass,
    CoverageDisposition,
    EvidenceSourceType,
    PromotionStatus,
    ScopeResolution,
)
from app.services.canonical_evidence_service import normalize_legacy_packet
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE as reasoning,
)


REQUIREMENT = "The selected maps should receive the metadata update."
NEARBY_CLAIMS = (
    (
        "new-map-collection",
        "Adding a map to a Map Collection should enable all associated presets "
        "automatically.",
    ),
    (
        "map-collection-filter-summary",
        "Generate All should publish only maps visible after applying a filter.",
    ),
    (
        "map-collection-removal-summary",
        "Remove From Collection should delete the map asset from the repository.",
    ),
    (
        "map-collection-retention-summary",
        "Deleting a collection should retain all generated outputs permanently.",
    ),
)


def evaluate_boundary(*, human_accepted: bool):
    issue = {"description": REQUIREMENT}
    if human_accepted:
        issue.update(labels=["accepted_uac"], acceptance_criteria=[REQUIREMENT])
    bundle = normalize_legacy_packet(
        {
            "jira_key": "BOUNDARY-1",
            "issue": issue,
            "experience_league_evidence": [
                {
                    "canonical_url": f"https://example.invalid/{source}",
                    "text": claim,
                    "authority": "DOCUMENT_VERIFIED",
                }
                for source, claim in NEARBY_CLAIMS
            ],
        },
        tenant_id="map-collection-boundary-test",
    )
    facts = reasoning.extract_contract_facts(bundle)
    # Isolate promotion with an established ticket scope and no unrelated blocker.
    scope = ScopeResolution(in_scope=["Map Collection bulk metadata selection"])
    coverage = reasoning.classify_coverage(facts, [], [], [], scope, [])
    candidates = reasoning.resolve_acceptance_contract(facts, coverage, [])
    _, decisions = reasoning.acceptance_promotion_gate(
        candidates, facts, scope, coverage
    )
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    promoted = {
        by_id[decision.candidate_id].statement: decision.resulting_disposition
        for decision in decisions
        if decision.status == PromotionStatus.PROMOTED
    }
    return bundle, candidates, promoted


class MapCollectionEvidenceBoundaryTests(unittest.TestCase):
    def test_document_verification_does_not_become_human_acceptance(self):
        bundle, candidates, promoted = evaluate_boundary(human_accepted=True)
        docs = [
            record for record in bundle.records
            if record.source_type == EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION
        ]
        self.assertEqual(len(docs), len(NEARBY_CLAIMS))
        self.assertEqual(
            {record.source_location for record in docs},
            {f"https://example.invalid/{source}" for source, _ in NEARBY_CLAIMS},
        )
        for record in docs:
            self.assertEqual(
                record.requirement_authority, AuthorityClass.OFFICIAL_PRODUCT_CONTRACT
            )
            self.assertEqual(record.content["authority"], "DOCUMENT_VERIFIED")
        for candidate in candidates:
            if candidate.statement in {claim for _, claim in NEARBY_CLAIMS}:
                self.assertFalse(candidate.accepted_human_contract)
        self.assertEqual(
            promoted, {REQUIREMENT: CoverageDisposition.ACCEPTANCE_CONTRACT}
        )

    def test_nearby_documentation_cannot_expand_proposed_uac(self):
        # Documentation remains authoritative investigation evidence, but it cannot
        # establish current-ticket applicability without a ticket-scoped fact.
        _, _, promoted = evaluate_boundary(human_accepted=False)
        self.assertEqual(
            promoted,
            {REQUIREMENT: CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT},
            "Nearby workflow/default/filter/deletion claims require source "
            "and scope verification.",
        )


if __name__ == "__main__":
    unittest.main()
