"""Tests for hybrid Jira retrieval."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.jira_retrieval_service import (
    MIN_ENTITY_OVERLAP,
    MIN_FINAL_SCORE,
    MIN_METADATA_SCORE,
    MIN_VECTOR_SCORE,
    RetrievedJira,
    _apply_enterprise_diversity,
    _candidate_confidence_score,
    _candidate_rejection_reasons,
    _metadata_where_plan,
    extract_structured_learning_evidence,
    extract_structured_uac_evidence,
    extract_hybrid_filters_from_issue_rows,
    retrieve_similar_jiras,
    retrieve_similar_jiras_debug,
)


def test_all_canonical_components_build_exact_membership_filters():
    for component in (
        "Editor",
        "Authoring",
        "Publishing",
        "Platform",
        "Schematron",
        "Integration",
    ):
        assert _metadata_where_plan(
            domain=None,
            sub_domain=None,
            issue_type=None,
            customer_names=[],
            components=[component],
        ) == [
            {
                "label": "component_membership_filtered",
                "where": {f"component_{component.casefold()}": True},
            }
        ]


@patch("app.services.jira_retrieval_service.query_collection", return_value=[])
@patch("app.services.jira_retrieval_service.is_embedding_available", return_value=True)
@patch("app.services.jira_retrieval_service.is_chroma_available", return_value=True)
def test_component_uses_strict_chroma_filter_without_unfiltered_fallback(
    _mock_chroma, _mock_embedding, mock_query
):
    debug: dict = {}

    rows = retrieve_similar_jiras(
        "hotspot link fails in preview",
        domain=None,
        dita_entities=[],
        affected_outputs=[],
        customer_names=[],
        base_components=["Editor"],
        query_embedding=[0.1, 0.2],
        retrieval_debug_sink=debug,
    )

    assert rows == []
    mock_query.assert_called_once()
    assert mock_query.call_args.kwargs["where"] == {"component_editor": True}
    assert debug["chroma"]["component_chroma_filter_applied"] is True
    assert debug["chroma"]["unfiltered_fallback_query"] is False


@patch("app.services.jira_retrieval_service.query_collection", return_value=[])
@patch("app.services.jira_retrieval_service.is_embedding_available", return_value=True)
@patch("app.services.jira_retrieval_service.is_chroma_available", return_value=True)
def test_domain_is_never_sent_as_a_chroma_filter(_mock_chroma, _mock_embedding, mock_query):
    debug: dict = {}

    rows = retrieve_similar_jiras(
        "publishing timeout during output generation",
        domain="publishing",
        dita_entities=[],
        affected_outputs=[],
        customer_names=[],
        query_embedding=[0.1, 0.2],
        retrieval_debug_sink=debug,
    )

    assert rows == []
    mock_query.assert_called_once()
    assert mock_query.call_args.kwargs["where"] is None
    assert debug["chroma"]["domain_chroma_filter_applied"] is False
    assert debug["chroma"]["domain_policy"] == "soft_boost_only"


@patch("app.services.jira_retrieval_service.query_collection")
@patch("app.services.jira_retrieval_service.is_embedding_available", return_value=True)
@patch("app.services.jira_retrieval_service.is_chroma_available", return_value=True)
def test_unknown_domain_candidate_remains_retrievable_by_content(
    _mock_chroma, _mock_embedding, mock_query
):
    mock_query.return_value = [
        {
            "id": "DXML-900::summary::0",
            "document": "Publishing timeout during output generation",
            "metadata": {
                "jira_key": "DXML-900",
                "title": "Publishing timeout",
                "chunk_type": "full_ticket_summary",
                "enrich_domain": "unknown",
                "labels": "[]",
                "components": "[]",
            },
            "distance": 0.05,
        }
    ]

    rows = retrieve_similar_jiras(
        "publishing timeout during output generation",
        domain="publishing",
        dita_entities=[],
        affected_outputs=[],
        customer_names=[],
        query_embedding=[0.1, 0.2],
        require_non_vector_evidence=False,
    )

    assert [row.jira_key for row in rows] == ["DXML-900"]
    assert mock_query.call_args.kwargs["where"] is None


def test_domain_is_not_subject_to_diversity_cap():
    ranked = [
        RetrievedJira(
            jira_key=f"DXML-{index}",
            title=f"Distinct ticket {index}",
            document=f"Distinct mechanism token-{index}",
            metadata={"enrich_domain": "publishing"},
            final_score=0.9 - (index * 0.01),
            strong_evidence=True,
        )
        for index in range(1, 6)
    ]

    result = _apply_enterprise_diversity(
        ranked,
        limit=5,
        max_per_customer=2,
    )

    assert [row.jira_key for row in result] == [f"DXML-{index}" for index in range(1, 6)]


def test_domain_match_is_only_a_soft_boost_not_an_evidence_gate():
    signals = {
        "domain_match": True,
        "domain_mismatch": False,
        "entity_overlap_count": 0,
        "output_overlap_count": 0,
        "customer_match": False,
        "component_overlap_count": 0,
        "issue_type_match": False,
        "query_entities": [],
        "query_outputs": [],
    }

    reasons = _candidate_rejection_reasons(
        vector_score=0.9,
        keyword_score=0.0,
        metadata_score=0.22,
        final_score=0.7,
        gate_signals=signals,
        evidence_gate_enabled=True,
        require_non_vector_evidence=True,
        meaningful_keyword_evidence=False,
    )

    assert [row["reason"] for row in reasons] == ["vector_only_weak_evidence"]


def test_domain_mismatch_does_not_reduce_candidate_confidence():
    signals = {
        "domain_match": False,
        "domain_mismatch": False,
        "entity_overlap_count": 1,
        "output_overlap_count": 0,
        "customer_match": False,
        "customer_conflict": False,
        "component_overlap_count": 0,
        "issue_type_match": False,
    }
    mismatch_signals = signals | {"domain_mismatch": True}

    baseline = _candidate_confidence_score(
        vector_score=0.8,
        metadata_score=0.4,
        final_score=0.6,
        gate_signals=signals,
        label_component_boost=0.0,
    )
    mismatched = _candidate_confidence_score(
        vector_score=0.8,
        metadata_score=0.4,
        final_score=0.6,
        gate_signals=mismatch_signals,
        label_component_boost=0.0,
    )

    assert mismatched == baseline


def test_extract_structured_learning_evidence_enforces_outcome_guardrail():
    fixed = extract_structured_learning_evidence(
        {
            "chunk_type": "learning_behavior_chunk",
            "document": (
                "Historical Jira learning: GUIDES-1\n"
                "Behavior contract: Queue successors resume after failed job cleanup.\n"
                "Root cause evidence: Concurrent commits targeted the same node.\n"
                "QA oracle: Run two publishes and verify terminal states.\n"
                "Regression risks: queue blockage"
            ),
            "metadata": {
                "learning_confidence": "medium",
                "historical_outcome": "implemented_fix",
            },
        }
    )
    caution = extract_structured_learning_evidence(
        {
            "chunk_type": "learning_behavior_chunk",
            "document": "Behavior contract: Do not reuse me.\nQA oracle: Do not reuse me.",
            "metadata": {
                "learning_confidence": "caution",
                "historical_outcome": "non_fix_decision",
            },
        }
    )

    assert fixed["reuse_mode"] == "verified_regression_contract"
    assert "terminal states" in fixed["qa_oracle"]
    assert caution["reuse_mode"] == "risk_signal_only"
    assert caution["behavior_contract"] == ""
    assert caution["qa_oracle"] == ""


def test_generated_fallback_oracle_is_never_returned_as_historical_test_evidence():
    evidence = extract_structured_learning_evidence(
        {
            "chunk_type": "learning_behavior_chunk",
            "document": (
                "Observed problem: Publishing queue stalls.\n"
                "Behavior contract: The queue must resume after cleanup.\n"
                "Root cause evidence: Concurrent commits targeted the same node.\n"
                "QA oracle: Verify the captured behavior contract after applying the fix."
            ),
            "metadata": {
                "learning_confidence": "medium",
                "historical_outcome": "implemented_fix",
                "is_verified_fix": True,
                "behavior_contract_complete": True,
                "root_cause_source": "jira_root_cause_field",
            },
        }
    )

    assert evidence["reuse_mode"] == "verified_regression_contract"
    assert evidence["is_verified_fix"] is False
    assert evidence["behavior_contract"]
    assert evidence["qa_oracle"] == ""
    assert evidence["qa_oracle_source"] == "generated_fallback"


def test_extract_structured_uac_evidence_preserves_source_and_blocks_candidates():
    supporting = extract_structured_uac_evidence(
        {
            "chunk_type": "historical_uac_clause_chunk",
            "document": "Historical Jira UAC clause: GUIDES-1 UAC-01\nSource text: Map links must render first.",
            "metadata": {
                "uac_schema_version": "historical-uac-v1",
                "uac_source_hash": "abc123",
                "uac_source_authority": "jira_accepted_uac",
                "uac_reuse_tier": "supporting",
                "uac_contract_complete": True,
                "uac_clause_id": "UAC-01",
                "uac_clause_stable_key": "jira:GUIDES-1:uac:abc",
                "uac_clause_kind": "in_scope",
                "uac_dimensions": '["ordering", "output"]',
            },
        }
    )
    candidate = extract_structured_uac_evidence(
        {
            "chunk_type": "historical_uac_clause_chunk",
            "document": "Source text: Check performance impact. TBD",
            "metadata": {
                "uac_reuse_tier": "candidate",
                "uac_contract_complete": False,
                "uac_clause_unresolved": True,
            },
        }
    )

    assert supporting["reuse_mode"] == "supporting_uac_contract"
    assert supporting["source_text"] == "Map links must render first."
    assert supporting["dimensions"] == ["ordering", "output"]
    assert candidate["reuse_mode"] == "risk_signal_only"
    assert candidate["clause_unresolved"] is True


@patch("app.services.jira_retrieval_service.query_collection")
@patch("app.services.jira_retrieval_service.embed_query")
@patch("app.services.jira_retrieval_service.is_embedding_available")
@patch("app.services.jira_retrieval_service.is_chroma_available")
def test_retrieval_prefers_reusable_learning_when_scores_are_comparable(
    mock_chroma, mock_emb, mock_embed, mock_q
):
    mock_chroma.return_value = True
    mock_emb.return_value = True
    mock_vec = MagicMock()
    mock_vec.tolist.return_value = [0.1] * 8
    mock_embed.return_value = mock_vec
    base_meta = {
        "jira_key": "GUIDES-LEARN",
        "title": "Publishing queue collision",
        "enrich_domain": "publishing",
        "enrich_entities": '["workflow"]',
        "enrich_outputs": '["AEM Sites"]',
        "labels": "[]",
        "components": "[]",
    }
    mock_q.return_value = [
        {
            "id": "summary",
            "document": "Publishing workflow queue collision AEM Sites",
            "metadata": {**base_meta, "chunk_type": "summary_chunk"},
            "distance": 0.10,
        },
        {
            "id": "learning",
            "document": "Publishing workflow queue collision AEM Sites",
            "metadata": {
                **base_meta,
                "chunk_type": "learning_behavior_chunk",
                "learning_confidence": "medium",
                "historical_outcome": "implemented_fix",
                "is_verified_fix": False,
            },
            "distance": 0.13,
        },
    ]

    rows = retrieve_similar_jiras(
        "publishing workflow queue collision AEM Sites",
        domain="publishing",
        dita_entities=["workflow"],
        affected_outputs=["AEM Sites"],
        customer_names=[],
        limit=3,
        recent_jira_keys=[],
    )

    assert rows[0].chunk_type == "learning_behavior_chunk"
    assert rows[0].score_breakdown["ranking_score"] > rows[0].final_score


def test_extract_hybrid_filters_from_rows():
    rows = [
        {
            "metadata": {
                "enrich_domain": "glossary",
                "enrich_entities": '["glossstatus", "bookmap"]',
                "enrich_outputs": '["native_pdf"]',
                "enrich_customers": '["Cisco"]',
            }
        }
    ]
    hy = extract_hybrid_filters_from_issue_rows(rows)
    assert hy["domain"] == "glossary"
    assert "glossstatus" in [x.lower() for x in hy["dita_entities"]]
    assert hy["affected_outputs"]
    assert hy["customer_names"]


@patch("app.services.jira_retrieval_service.query_collection")
@patch("app.services.jira_retrieval_service.embed_query")
@patch("app.services.jira_retrieval_service.is_embedding_available")
@patch("app.services.jira_retrieval_service.is_chroma_available")
def test_retrieve_similar_jiras_metadata_and_why(mock_chroma, mock_emb, mock_embed, mock_q):
    mock_chroma.return_value = True
    mock_emb.return_value = True
    mock_vec = MagicMock()
    mock_vec.tolist.return_value = [0.1] * 8
    mock_embed.return_value = mock_vec

    def _qc(coll, emb, k, where=None):
        assert coll == "jira_qa"
        meta_a = {
            "jira_key": "GUIDES-10",
            "title": "Glossary Native PDF glossStatus",
            "chunk_type": "full_ticket_summary",
            "enrich_domain": "glossary",
            "enrich_sub_domain": "native_pdf",
            "enrich_entities": '["glossstatus", "bookmap"]',
            "enrich_outputs": '["native_pdf"]',
            "labels": "[]",
            "components": "[]",
        }
        row = {
            "id": "x1",
            "document": "glossStatus inside glossary bookmap native pdf output",
            "metadata": meta_a,
            "distance": 0.15,
        }
        if where and where.get("enrich_domain") == "glossary":
            return [row]
        return [row]

    mock_q.side_effect = _qc

    out = retrieve_similar_jiras(
        "native pdf glossary glossStatus bookmap",
        domain="glossary",
        dita_entities=["glossstatus", "bookmap"],
        affected_outputs=["native_pdf"],
        customer_names=[],
        limit=5,
    )
    assert len(out) >= 1
    r0 = out[0]
    assert r0.jira_key == "GUIDES-10"
    assert r0.vector_score > 0
    assert r0.keyword_score >= 0
    assert r0.metadata_score > 0
    assert r0.final_score > 0
    assert r0.matching_entities == ["glossstatus", "bookmap"]
    assert r0.matching_outputs == ["native_pdf"]
    assert r0.score_breakdown["vector_weight"] == 0.45
    assert r0.score_breakdown["metadata_weight"] == 0.35
    assert r0.score_breakdown["keyword_weight"] == 0.2
    assert "glossstatus" in r0.why_similar.lower() or "native" in r0.why_similar.lower()
    mock_q.assert_called()


@patch("app.services.jira_retrieval_service.query_collection")
@patch("app.services.jira_retrieval_service.embed_query")
@patch("app.services.jira_retrieval_service.is_embedding_available")
@patch("app.services.jira_retrieval_service.is_chroma_available")
def test_retrieve_similar_jiras_score_formula_and_overlap_explainability(mock_chroma, mock_emb, mock_embed, mock_q):
    mock_chroma.return_value = True
    mock_emb.return_value = True
    mock_vec = MagicMock()
    mock_vec.tolist.return_value = [0.1] * 8
    mock_embed.return_value = mock_vec
    mock_q.return_value = [
        {
            "id": "formula-1",
            "document": "Cisco glossStatus native_pdf publishing component regression",
            "metadata": {
                "jira_key": "GUIDES-401",
                "title": "Cisco glossStatus Native PDF bug",
                "chunk_type": "full_ticket_summary",
                "enrich_domain": "glossary",
                "enrich_sub_domain": "native_pdf",
                "enrich_entities": '["glossstatus"]',
                "enrich_outputs": '["native_pdf"]',
                "enrich_customers": '["Cisco"]',
                "customer": "Cisco",
                "components": '["Publishing"]',
                "issue_type": "Bug",
                "labels": "[]",
            },
            "distance": 0.2,
        }
    ]

    out = retrieve_similar_jiras(
        "Cisco glossStatus native_pdf publishing bug",
        domain="glossary",
        dita_entities=["glossstatus"],
        affected_outputs=["native_pdf"],
        customer_names=["Cisco"],
        limit=3,
        base_components=["Publishing"],
        issue_type="Bug",
        recent_jira_keys=[],
    )

    assert len(out) == 1
    row = out[0]
    assert row.matching_entities == ["glossstatus"]
    assert row.matching_outputs == ["native_pdf"]
    assert row.matching_customers == ["Cisco"]
    assert row.matching_components == ["Publishing"]
    breakdown = row.score_breakdown
    expected = round(
        breakdown["weighted_vector"]
        + breakdown["weighted_metadata"]
        + breakdown["weighted_keyword"]
        - breakdown["penalty_total"],
        4,
    )
    assert row.final_score == expected
    assert breakdown["penalties"] == {}
    assert "Score blend" in row.why_similar


@patch("app.services.jira_retrieval_service.query_collection")
@patch("app.services.jira_retrieval_service.embed_query")
@patch("app.services.jira_retrieval_service.is_embedding_available")
@patch("app.services.jira_retrieval_service.is_chroma_available")
def test_retrieve_similar_jiras_filters_vector_only_weak_evidence(mock_chroma, mock_emb, mock_embed, mock_q):
    """High embedding match without entity/output/domain-customer overlap must not pass the evidence gate."""
    mock_chroma.return_value = True
    mock_emb.return_value = True
    mock_vec = MagicMock()
    mock_vec.tolist.return_value = [0.1] * 8
    mock_embed.return_value = mock_vec

    meta_a = {
        "jira_key": "GUIDES-99",
        "title": "Unrelated issue",
        "chunk_type": "full_ticket_summary",
        "enrich_domain": "maps",
        "enrich_sub_domain": "",
        "enrich_entities": '["xref"]',
        "enrich_outputs": '["html5"]',
        "labels": "[]",
        "components": "[]",
    }
    mock_q.return_value = [
        {
            "id": "x1",
            "document": "completely different wording about unrelated topic",
            "metadata": meta_a,
            "distance": 0.05,
        }
    ]
    out = retrieve_similar_jiras(
        "glossary glossStatus native pdf bookmap",
        domain="glossary",
        dita_entities=["glossstatus"],
        affected_outputs=["native_pdf"],
        customer_names=[],
        limit=5,
    )
    assert out == []


@patch("app.services.jira_retrieval_service.query_collection")
@patch("app.services.jira_retrieval_service.embed_query")
@patch("app.services.jira_retrieval_service.is_embedding_available")
@patch("app.services.jira_retrieval_service.is_chroma_available")
def test_retrieve_similar_jiras_rejects_unknown_query_vector_only(mock_chroma, mock_emb, mock_embed, mock_q):
    """When no metadata gate is available, a high vector score alone is not enough for UAC reuse."""
    mock_chroma.return_value = True
    mock_emb.return_value = True
    mock_vec = MagicMock()
    mock_vec.tolist.return_value = [0.1] * 8
    mock_embed.return_value = mock_vec
    mock_q.return_value = [
        {
            "id": "vector-only",
            "document": "profile preferences avatar unrelated admin screen",
            "metadata": {
                "jira_key": "GUIDES-VEC",
                "title": "Unrelated admin preference",
                "chunk_type": "summary_chunk",
                "labels": "[]",
                "components": "[]",
            },
            "distance": 0.02,
        }
    ]

    sink: dict = {}
    out = retrieve_similar_jiras(
        "short ambiguous Jira description",
        domain=None,
        dita_entities=[],
        affected_outputs=[],
        customer_names=[],
        limit=3,
        recent_jira_keys=[],
        retrieval_debug_sink=sink,
    )

    assert out == []
    assert any(d.get("reason") == "vector_only_weak_evidence" for d in sink["rejected_candidates"])


@patch("app.services.jira_retrieval_service.query_collection")
@patch("app.services.jira_retrieval_service.embed_query")
@patch("app.services.jira_retrieval_service.is_embedding_available")
@patch("app.services.jira_retrieval_service.is_chroma_available")
def test_retrieve_similar_jiras_debugs_rejection_reasons(mock_chroma, mock_emb, mock_embed, mock_q):
    mock_chroma.return_value = True
    mock_emb.return_value = True
    mock_vec = MagicMock()
    mock_vec.tolist.return_value = [0.1] * 8
    mock_embed.return_value = mock_vec
    mock_q.return_value = [
        {
            "id": "bad1",
            "document": "unrelated map xref html output",
            "metadata": {
                "jira_key": "GUIDES-777",
                "title": "Unrelated map issue",
                "chunk_type": "full_ticket_summary",
                "enrich_domain": "maps",
                "enrich_entities": '["xref"]',
                "enrich_outputs": '["html5"]',
                "labels": "[]",
                "components": "[]",
            },
            "distance": 0.08,
        }
    ]
    sink: dict = {}
    out = retrieve_similar_jiras(
        "glossary glossStatus native pdf",
        domain="glossary",
        dita_entities=["glossstatus"],
        affected_outputs=["native_pdf"],
        customer_names=[],
        limit=3,
        retrieval_debug_sink=sink,
    )
    assert out == []
    reasons = {row["reason"] for row in sink["dropped_candidates"]}
    assert "domain_gate_failed" not in reasons
    assert "entity_overlap_gate_failed" in reasons
    assert "output_overlap_gate_failed" in reasons
    scored = sink["candidates_after_scoring"][0]
    assert scored["selected"] is False
    assert scored["score_breakdown"]["confidence_score"] >= 0
    assert sink["thresholds"] == {
        "MIN_VECTOR_SCORE": MIN_VECTOR_SCORE,
        "MIN_METADATA_SCORE": MIN_METADATA_SCORE,
        "MIN_FINAL_SCORE": MIN_FINAL_SCORE,
        "MIN_ENTITY_OVERLAP": MIN_ENTITY_OVERLAP,
    }


@patch("app.services.jira_retrieval_service.query_collection")
@patch("app.services.jira_retrieval_service.embed_query")
@patch("app.services.jira_retrieval_service.is_embedding_available")
@patch("app.services.jira_retrieval_service.is_chroma_available")
def test_retrieve_similar_jiras_does_not_hard_cap_domain(mock_chroma, mock_emb, mock_embed, mock_q):
    mock_chroma.return_value = True
    mock_emb.return_value = True
    mock_vec = MagicMock()
    mock_vec.tolist.return_value = [0.1] * 8
    mock_embed.return_value = mock_vec

    def _meta(jk: str, dom: str):
        return {
            "jira_key": jk,
            "title": "T",
            "chunk_type": "full_ticket_summary",
            "enrich_domain": dom,
            "enrich_sub_domain": "native_pdf",
            "enrich_entities": '["glossstatus"]',
            "enrich_outputs": '["native_pdf"]',
            "labels": "[]",
            "components": "[]",
        }

    rows = [
        {
            "id": f"a{i}",
            "document": f"glossStatus glossary native pdf distinct mechanism token{i}",
            "metadata": _meta(f"G-{i}", "glossary"),
            "distance": 0.01 * i,
        }
        for i in range(5)
    ]
    mock_q.return_value = rows
    sink: dict = {}
    out = retrieve_similar_jiras(
        "glossary glossStatus native pdf",
        domain="glossary",
        dita_entities=["glossstatus"],
        affected_outputs=["native_pdf"],
        customer_names=[],
        limit=8,
        retrieval_debug_sink=sink,
    )
    domains = [str((r.metadata or {}).get("enrich_domain")) for r in out]
    assert domains.count("glossary") == 5
    assert not any(d.get("reason") == "max_similar_per_domain" for d in sink["dropped_candidates"])
    assert sink["diversity_limits"]["domain_cap_applied"] is False


@patch("app.services.jira_retrieval_service.query_collection")
@patch("app.services.jira_retrieval_service.embed_query")
@patch("app.services.jira_retrieval_service.is_embedding_available")
@patch("app.services.jira_retrieval_service.is_chroma_available")
def test_retrieve_similar_jiras_max_two_per_customer(mock_chroma, mock_emb, mock_embed, mock_q):
    mock_chroma.return_value = True
    mock_emb.return_value = True
    mock_vec = MagicMock()
    mock_vec.tolist.return_value = [0.1] * 8
    mock_embed.return_value = mock_vec

    def _row(i: int, dom: str):
        return {
            "id": f"cust-{i}",
            "document": f"Cisco customer issue {i} native pdf glossStatus publishing",
            "metadata": {
                "jira_key": f"GUIDES-C{i}",
                "title": f"Cisco issue {i}",
                "chunk_type": "full_ticket_summary",
                "enrich_domain": dom,
                "enrich_entities": '["glossstatus"]',
                "enrich_outputs": '["native_pdf"]',
                "enrich_customers": '["Cisco"]',
                "customer": "Cisco",
                "components": "[]",
                "labels": "[]",
            },
            "distance": 0.01 * i,
        }

    mock_q.return_value = [_row(1, "glossary"), _row(2, "publishing"), _row(3, "metadata"), _row(4, "maps")]
    sink: dict = {}
    out = retrieve_similar_jiras(
        "Cisco glossStatus native pdf",
        domain=None,
        dita_entities=["glossstatus"],
        affected_outputs=["native_pdf"],
        customer_names=["Cisco"],
        limit=5,
        retrieval_debug_sink=sink,
        recent_jira_keys=[],
    )

    assert len(out) == 2
    assert all(row.matching_customers == ["Cisco"] for row in out)
    assert any(d.get("reason") == "max_similar_per_customer" for d in sink["dropped_candidates"])


@patch("app.services.jira_retrieval_service.query_collection")
@patch("app.services.jira_retrieval_service.embed_query")
@patch("app.services.jira_retrieval_service.is_embedding_available")
@patch("app.services.jira_retrieval_service.is_chroma_available")
def test_retrieve_similar_jiras_suppresses_near_duplicate_jira(mock_chroma, mock_emb, mock_embed, mock_q):
    mock_chroma.return_value = True
    mock_emb.return_value = True
    mock_vec = MagicMock()
    mock_vec.tolist.return_value = [0.1] * 8
    mock_embed.return_value = mock_vec

    base_doc = "glossStatus native_pdf glossary rendering keeps same cross reference warning"
    rows = []
    for i, customer in enumerate(["Cisco", "Topcon"], start=1):
        rows.append(
            {
                "id": f"dup-{i}",
                "document": base_doc,
                "metadata": {
                    "jira_key": f"GUIDES-D{i}",
                    "title": "GlossStatus Native PDF duplicate",
                    "chunk_type": "full_ticket_summary",
                    "enrich_domain": "glossary",
                    "enrich_entities": '["glossstatus"]',
                    "enrich_outputs": '["native_pdf"]',
                    "enrich_customers": f'["{customer}"]',
                    "customer": customer,
                    "components": "[]",
                    "labels": "[]",
                },
                "distance": 0.01 * i,
            }
        )
    mock_q.return_value = rows
    sink: dict = {}

    out = retrieve_similar_jiras(
        "glossStatus native_pdf glossary rendering",
        domain="glossary",
        dita_entities=["glossstatus"],
        affected_outputs=["native_pdf"],
        customer_names=[],
        limit=5,
        retrieval_debug_sink=sink,
        recent_jira_keys=[],
    )

    assert len(out) == 1
    assert any(d.get("reason") == "near_duplicate_jira" for d in sink["dropped_candidates"])


@patch("app.services.jira_retrieval_service.query_collection")
@patch("app.services.jira_retrieval_service.embed_query")
@patch("app.services.jira_retrieval_service.is_embedding_available")
@patch("app.services.jira_retrieval_service.is_chroma_available")
def test_retrieve_similar_jiras_debug_sink(mock_chroma, mock_emb, mock_embed, mock_q):
    mock_chroma.return_value = True
    mock_emb.return_value = True
    mock_vec = MagicMock()
    mock_vec.tolist.return_value = [0.1] * 8
    mock_embed.return_value = mock_vec
    meta_a = {
        "jira_key": "GUIDES-10",
        "title": "T",
        "chunk_type": "full_ticket_summary",
        "enrich_domain": "glossary",
        "enrich_sub_domain": "",
        "enrich_entities": '["glossstatus"]',
        "enrich_outputs": '["native_pdf"]',
        "labels": "[]",
        "components": "[]",
    }
    mock_q.return_value = [
        {"id": "x1", "document": "glossStatus glossary native pdf", "metadata": meta_a, "distance": 0.1},
        {"id": "x1", "document": "dup id dropped", "metadata": meta_a, "distance": 0.2},
    ]
    sink: dict = {}
    retrieve_similar_jiras(
        "glossary glossStatus native pdf",
        domain="glossary",
        dita_entities=["glossstatus"],
        affected_outputs=["native_pdf"],
        customer_names=[],
        limit=3,
        retrieval_debug_sink=sink,
    )
    assert "retrieval_query" in sink
    assert sink["extracted"]["domain"] == "glossary"
    assert "candidates_before_rerank" in sink
    assert "candidates_after_scoring" in sink
    assert "candidates_after_rerank" in sink
    assert "candidates_final" in sink
    assert "dropped_candidates" in sink
    assert "rejected_candidates" in sink
    assert sink["rejected_candidates"] == sink["dropped_candidates"]
    assert any(d.get("reason") == "duplicate_chroma_chunk_id" for d in sink["dropped_candidates"])
    assert sink["candidates_after_scoring"][0]["score_breakdown"]["final_fused_score"] >= 0
    assert sink["candidates_final"][0]["why_similar"]


@patch("app.services.jira_retrieval_service.query_collection")
@patch("app.services.jira_retrieval_service.embed_query")
@patch("app.services.jira_retrieval_service.is_embedding_available")
@patch("app.services.jira_retrieval_service.is_chroma_available")
def test_retrieve_similar_jiras_debug_api(mock_chroma, mock_emb, mock_embed, mock_q):
    mock_chroma.return_value = True
    mock_emb.return_value = True
    mock_vec = MagicMock()
    mock_vec.tolist.return_value = [0.1] * 8
    mock_embed.return_value = mock_vec
    mock_q.return_value = [
        {
            "id": "debug-1",
            "document": "keyref keyscope native_pdf",
            "metadata": {
                "jira_key": "GUIDES-DEBUG",
                "title": "Keyref debug",
                "chunk_type": "full_ticket_summary",
                "enrich_domain": "keyref",
                "enrich_entities": '["keyref"]',
                "enrich_outputs": '["native_pdf"]',
                "labels": "[]",
                "components": "[]",
            },
            "distance": 0.1,
        }
    ]

    payload = retrieve_similar_jiras_debug(
        "keyref native_pdf",
        domain="keyref",
        dita_entities=["keyref"],
        affected_outputs=["native_pdf"],
        customer_names=[],
        limit=2,
        recent_jira_keys=[],
    )

    assert payload["results"][0]["jira_key"] == "GUIDES-DEBUG"
    assert payload["debug"]["candidates_final"][0]["score_breakdown"]["formula"].startswith("vector_score")
    assert "rejected_candidates" in payload["debug"]
