from __future__ import annotations

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_chunking_service import create_jira_chunks
from app.services.jira_learning_chunk_service import (
    LEARNING_CHUNK_TYPE,
    build_learning_document,
)
from app.services.jira_retrieval_service import _CHUNK_TYPE_WEIGHT


def test_learning_document_uses_supported_evidence_and_marks_verified_fix():
    built = build_learning_document(
        jira_key="GUIDES-50001",
        summary="Publishing queue stalls",
        domain="publishing",
        components=["AEM Sites"],
        outputs=["AEM Sites"],
        entities=["ditamap"],
        problem="Concurrent publishing leaves the job in post publishing.",
        behavior_contract="The queue must release after publishing completes.",
        resolution="Fixed",
        root_cause="Concurrent Oak commits targeted the same path.",
        qa_oracle="Run large-library publishing sequentially and verify terminal state.",
        risks=["regression", "production"],
    )
    assert built is not None
    document, metadata = built
    assert "Current Jira facts and approved UAC remain authoritative" in document
    assert metadata["learning_confidence"] == "high"
    assert metadata["historical_outcome"] == "implemented_fix"
    assert metadata["is_verified_fix"] is True
    assert metadata["evidence_facets"] == [
        "problem",
        "behavior_contract",
        "resolution",
        "root_cause",
        "qa_oracle",
    ]


def test_non_fix_resolution_is_caution_not_a_verified_fix():
    document, metadata = build_learning_document(
        jira_key="GUIDES-50002",
        summary="Expected behavior question",
        domain="authoring",
        components=[],
        outputs=[],
        entities=[],
        problem="The reporter expected a different result.",
        behavior_contract="The documented behavior is unchanged.",
        resolution="Working As Designed",
        root_cause="",
        qa_oracle="",
        risks=[],
    )
    assert "Historical outcome: Working As Designed" in document
    assert metadata["learning_confidence"] == "caution"
    assert metadata["historical_outcome"] == "expected_product_behavior"
    assert metadata["is_verified_fix"] is False


def test_resolved_enriched_jira_emits_learning_chunk_with_retrieval_priority():
    enriched = JiraEnrichedDocument(
        jira_key="GUIDES-50003",
        summary="Translation baseline selection",
        description="Baseline files are selected from the wrong version.",
        status="Closed",
        resolution="Fixed",
        domain="translation",
        expected_behavior="Use references captured at baseline creation time.",
        acceptance_criteria="Baseline selection must ignore later working-copy changes.",
        root_cause="The resolver used latest-version references.",
        qa_risk_tags=["regression"],
    )
    chunks = create_jira_chunks(enriched)
    learning = [chunk for chunk in chunks if chunk["chunk_type"] == LEARNING_CHUNK_TYPE]
    assert len(learning) == 1
    assert learning[0]["learning_confidence"] == "high"
    assert _CHUNK_TYPE_WEIGHT[LEARNING_CHUNK_TYPE] > _CHUNK_TYPE_WEIGHT["comment_chunk"]


def test_learning_rebuild_endpoint_is_admin_only_and_returns_stats(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.jira_learning_chunk_service.backfill_jira_learning_chunks",
        lambda **_kwargs: {
            "source_type": "jira_csv",
            "eligible_issues": 404,
            "indexed_issues": 404,
            "chunks": 404,
            "failed_issues": 0,
            "errors": [],
        },
    )
    response = client.post(
        "/api/v1/admin/jira-rag/learning-chunks/rebuild",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["chunks"] == 404
