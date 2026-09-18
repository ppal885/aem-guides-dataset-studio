"""Regression guard for the DITA-OT publishing evidence producer/consumer contract.

``_build_publishing_transform_context`` emits an *envelope* whose retrieved rows live
under ``dita_ot_evidence``.  ``normalize_legacy_packet`` previously read only the
generic ``evidence``/``results``/``sources`` keys and fell through to wrapping the
envelope itself, which had two consequences:

  * every retrieved GitHub issue collapsed into one opaque, non-citable record, and
  * because the envelope is always seeded (even when the publishing gate is OFF), the
    "gated off" message was admitted as DITA_OT / CURRENT_IMPLEMENTATION evidence on
    every non-publishing ticket.

These tests pin both halves of the contract plus the legacy packet shapes that must
keep their prior behaviour.

Run from the repository root with:
    PYTHONPATH=backend python -m unittest discover -s backend/tests \
        -p test_dita_ot_evidence_envelope.py -v
"""

from __future__ import annotations

import unittest

from app.core.schemas_canonical_test_plan_runtime import EvidenceSourceType
from app.services.canonical_evidence_service import normalize_legacy_packet


TENANT = "dita-ot-envelope-test"

GATE_OFF_MESSAGE = (
    "DITA-OT publishing evidence is gated off because this Jira issue is not "
    "detected as publishing/PDF2/HTML/HTML5/transformation-related."
)

# Mirrors the row shape returned by retrieve_dita_ot_github_for_query.
GITHUB_ROWS = [
    {
        "url": "https://github.com/dita-ot/dita-ot/issues/111",
        "title": "PDF2 index entries lost for nested topicrefs",
        "snippet": "The PDF2 transform drops index entries when ...",
        "issue_number": 111,
    },
    {
        "url": "https://github.com/dita-ot/dita-ot/issues/222",
        "title": "HTML5 output preset ignores custom CSS",
        "snippet": "Custom CSS supplied through args.css is not ...",
        "issue_number": 222,
    },
    {
        "url": "https://github.com/dita-ot/dita-ot/issues/333",
        "title": "Chunking regression on map-level chunk attribute",
        "snippet": "Setting chunk on the map root produces ...",
        "issue_number": 333,
    },
]


def dita_ot_records(publishing_transform_context):
    bundle = normalize_legacy_packet(
        {
            "jira_key": "ENVELOPE-1",
            "issue": {"description": "Publishing output regression."},
            "publishing_transform_context": publishing_transform_context,
        },
        tenant_id=TENANT,
    )
    return [
        record
        for record in bundle.records
        if record.source_type == EvidenceSourceType.DITA_OT
    ]


class DitaOtEvidenceEnvelopeTests(unittest.TestCase):
    def test_gate_off_envelope_admits_no_dita_ot_evidence(self):
        # The producer always seeds dita_ot_evidence, so a non-publishing ticket still
        # carries an envelope.  Its gate prose is not DITA-OT implementation evidence.
        records = dita_ot_records(
            {
                "enabled": False,
                "gate": "publishing/pdf2/html/html5/dita-ot label-or-text",
                "detected_labels": [],
                "required_for_test_plan": False,
                "dita_ot_evidence": [],
                "message": GATE_OFF_MESSAGE,
            }
        )
        self.assertEqual(
            records,
            [],
            "A gated-off publishing envelope must not become DITA-OT evidence.",
        )

    def test_retrieval_error_envelope_admits_no_dita_ot_evidence(self):
        # An enabled gate whose retrieval failed has no rows; the error string is a
        # diagnostic, not a product-behaviour claim.
        records = dita_ot_records(
            {
                "enabled": True,
                "required_for_test_plan": True,
                "dita_ot_evidence": [],
                "error": "chroma collection dita_ot_github is unavailable",
            }
        )
        self.assertEqual(records, [])

    def test_gate_on_envelope_yields_one_citable_record_per_issue(self):
        records = dita_ot_records(
            {
                "enabled": True,
                "required_for_test_plan": True,
                "source": "dita_ot_github_rag_service",
                "dita_ot_evidence": list(GITHUB_ROWS),
            }
        )
        self.assertEqual(len(records), len(GITHUB_ROWS))

        keys = [record.source_key for record in records]
        self.assertEqual(
            len(set(keys)), len(GITHUB_ROWS), "Each issue needs a distinct source key."
        )
        for row, key in zip(GITHUB_ROWS, keys):
            self.assertTrue(key.startswith("dita-ot:"))
            # The key must be derived from the issue URL, not a positional index, so
            # downstream citations stay stable across retrieval-order changes.
            self.assertIn(str(row["issue_number"]), key)

        locations = {record.source_location for record in records}
        self.assertEqual(len(locations), len(GITHUB_ROWS))
        self.assertEqual(
            {record.content["title"] for record in records},
            {row["title"] for row in GITHUB_ROWS},
        )

    def test_legacy_packet_shapes_keep_their_prior_behaviour(self):
        # These shapes predate the envelope and must stay on the generic chain.
        self.assertEqual(
            len(dita_ot_records({"evidence": [GITHUB_ROWS[0], GITHUB_ROWS[1]]})), 2
        )
        self.assertEqual(len(dita_ot_records({"results": [GITHUB_ROWS[0]]})), 1)
        self.assertEqual(len(dita_ot_records({"sources": [GITHUB_ROWS[0]]})), 1)
        # A bare dict with no recognised list key is still wrapped as one record.
        self.assertEqual(len(dita_ot_records({"url": GITHUB_ROWS[0]["url"]})), 1)
        self.assertEqual(dita_ot_records({}), [])
        self.assertEqual(dita_ot_records([]), [])
        self.assertEqual(len(dita_ot_records(list(GITHUB_ROWS))), len(GITHUB_ROWS))


if __name__ == "__main__":
    unittest.main()
