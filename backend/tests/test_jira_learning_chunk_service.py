from __future__ import annotations

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.db.jira_enrichment_models import JiraEnrichedIssue, JiraIssueChunk
from app.services.jira_chunking_service import create_jira_chunks
from app.services.jira_learning_chunk_service import (
    LEARNING_CHUNK_TYPE,
    _learning_from_sql,
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
    assert learning[0]["learning_confidence"] == "medium"
    assert learning[0]["is_verified_fix"] is False
    assert learning[0]["qa_oracle_source"] == "missing"
    assert _CHUNK_TYPE_WEIGHT[LEARNING_CHUNK_TYPE] > _CHUNK_TYPE_WEIGHT["comment_chunk"]


def test_incomplete_uac_does_not_become_verified_learning_or_generated_oracle():
    enriched = JiraEnrichedDocument(
        jira_key="GUIDES-50004",
        summary="Baseline preview performance",
        description="Preview can be slow for a large map.",
        status="Closed",
        resolution="Fixed",
        domain="editor",
        acceptance_criteria="Check performance impact. TBD",
        root_cause="The preview loaded every topic eagerly.",
    )

    chunks = create_jira_chunks(enriched)
    learning = next(chunk for chunk in chunks if chunk["chunk_type"] == LEARNING_CHUNK_TYPE)

    assert learning["learning_confidence"] == "caution"
    assert learning["is_verified_fix"] is False
    assert learning["behavior_contract_complete"] is False
    assert learning["qa_oracle_source"] == "missing"
    assert "verify the captured behavior contract" not in learning["chunk_text"].lower()


def test_learning_refresh_analyzes_full_jira_uac_instead_of_legacy_four_k_chunk():
    complete_prefix = "\n".join(
        f"Requirement {index:03d} must retain the configured baseline value." for index in range(90)
    )
    full_uac = complete_prefix + "\nCheck performance impact. TBD"
    issue = JiraEnrichedIssue(
        jira_key="GUIDES-50005",
        summary="Baseline metadata refresh",
        description=f"Problem.\n\n## UAC Criteria (custom field)\n{full_uac}",
        status="Closed",
        resolution="Fixed",
        source_type="jira_csv",
        labels=["UAC_Done"],
        components=["Publishing"],
        customer_names=[],
        domain="publishing",
        affected_outputs=["AEM Sites"],
        dita_entities=["ditamap"],
        qa_risk_tags=["regression"],
    )
    chunks = [
        JiraIssueChunk(
            jira_key=issue.jira_key,
            chunk_type="problem_chunk",
            chunk_text="Baseline metadata comes from the working copy.",
        ),
        JiraIssueChunk(
            jira_key=issue.jira_key,
            chunk_type="acceptance_criteria_chunk",
            chunk_text="Acceptance criteria:\n" + full_uac[:4000],
        ),
    ]

    built = _learning_from_sql(issue, chunks)

    assert built is not None
    _, metadata = built
    assert metadata["behavior_contract_complete"] is False
    assert metadata["learning_confidence"] == "caution"


def test_explicit_analysis_and_qa_comment_can_verify_a_complete_historical_contract():
    enriched = JiraEnrichedDocument(
        jira_key="GUIDES-44393",
        summary="MathML outputclass propagation",
        description="MathML outputclass is absent from merged output.",
        status="Closed",
        resolution="Fixed",
        labels=["UAC_Done"],
        domain="publishing",
        affected_outputs=["Native PDF", "Merged HTML"],
        acceptance_criteria=(
            "*Feature Flag - No feature flag*\n"
            "MathML outputclass must propagate to Native PDF and merged HTML."
        ),
        comments_digest=(
            "QA verification:\n"
            "Verified on build 2026.06.2315. MathML outputclass propagates to Native PDF and merged HTML.\n\n"
            "Analysis:\n"
            "The outputclass was dropped when the img node was replaced with the math node."
        ),
    )

    chunks = create_jira_chunks(enriched)
    learning = next(chunk for chunk in chunks if chunk["chunk_type"] == LEARNING_CHUNK_TYPE)
    contract = next(chunk for chunk in chunks if chunk["chunk_type"] == "historical_uac_contract_chunk")

    assert learning["learning_confidence"] == "high"
    assert learning["is_verified_fix"] is True
    assert learning["root_cause_source"] == "jira_comment_explicit_analysis"
    assert learning["qa_oracle_source"] == "jira_comment_qa_verification"
    assert contract["uac_reuse_tier"] == "historical_verified"
    assert contract["uac_contract_complete"] is True


def test_metadata_filter_learning_uses_confirmed_index_rca_not_superseded_hypothesis():
    enriched = JiraEnrichedDocument(
        jira_key="GUIDES-28847",
        summary="Metadata Report Filter Fails to Display All DITA Topics",
        description="The DITA Topic filter returned 2 files from a corpus of 442 topics.",
        status="Closed",
        resolution="Fixed",
        labels=["KONE", "UAC_Not_Required", "Won't_Automate"],
        domain="platform",
        acceptance_criteria="UAC Not Required",
        comments_digest=(
            "[2025-05-06] Support: RCA:\n"
            "The root cause could be linked to a custom index, which seems to impact results. "
            "To confirm, I suggest disabling it.\n"
            "[2025-05-08] Engineering: This indicated a problem with indexing of the damAssetLucene index. "
            "Reindexing damAssetLucene fixed the filtering results, so the issue is environment-specific. "
            "The initial assumption that custom namespaced metadata caused the problem is invalid.\n"
            "[2025-05-16] Support: KONE IT team has tested and validated that it is fixed after re-indexing."
        ),
    )

    chunks = create_jira_chunks(enriched)
    learning = next(chunk for chunk in chunks if chunk["chunk_type"] == LEARNING_CHUNK_TYPE)

    assert learning["learning_confidence"] == "caution"
    assert learning["is_verified_fix"] is False
    assert learning["root_cause_source"] == "jira_comment_confirmed_root_cause"
    assert learning["qa_oracle_source"] == "jira_comment_customer_validation"
    assert "damAssetLucene" in learning["chunk_text"]
    assert "root cause could be linked" not in learning["chunk_text"]
    assert any(chunk["chunk_type"] == "uac_status_chunk" for chunk in chunks)
    assert not any(chunk["chunk_type"] == "acceptance_criteria_chunk" for chunk in chunks)


def test_fixed_resolution_closed_by_configuration_migration_is_not_a_product_fix():
    enriched = JiraEnrichedDocument(
        jira_key="GUIDES-28667",
        summary="Custom button in preview mode not available unless file is locked",
        description=(
            "A custom Export PDF button for DITA-OT PDF appears in preview only while the file is locked. "
            "The customer supplied KONEui_config.json."
        ),
        status="Closed",
        resolution="Fixed",
        labels=["Doc_Required", "KONE", "Triaged"],
        components=["Authoring"],
        domain="authoring",
        comments_digest=(
            "[2025-04-25] Engineering: Attached the updated editor_toolbar.json which adds the button "
            "for both lock and unlock scenario.\n"
            "[2025-04-30] Support: The given code helped the customer unblock, but it is still a "
            "workaround and not a fix.\n"
            "[2025-05-06] Engineering: Custom buttons configured in ui_config.json would not work and "
            "would need to be ported to editor_toolbar.js.\n"
            "[2025-05-07] Engineering: Closing this as no further action is pending. Documentation will "
            "be tracked in GUIDES-28909."
        ),
    )

    chunks = create_jira_chunks(enriched)
    learning = next(chunk for chunk in chunks if chunk["chunk_type"] == LEARNING_CHUNK_TYPE)

    assert learning["learning_strategy_version"] == "jira-history-v4"
    assert learning["historical_outcome"] == "configuration_migration"
    assert learning["resolution_mechanism"] == "configuration_migration"
    assert learning["resolution_evidence_source"] == "jira_comment_configuration_migration"
    assert learning["learning_confidence"] == "caution"
    assert learning["is_verified_fix"] is False
    assert "workaround and not a fix" in learning["chunk_text"]
    assert "ported to editor_toolbar.js" in learning["chunk_text"]
    assert "Documentation will be tracked in GUIDES-28909" in learning["chunk_text"]
    assert not any(chunk["chunk_type"] == "acceptance_criteria_chunk" for chunk in chunks)


def test_later_explicit_product_fix_overrides_an_earlier_workaround():
    built = build_learning_document(
        jira_key="GUIDES-50006",
        summary="Custom preview action",
        domain="authoring",
        components=["Authoring"],
        outputs=[],
        entities=[],
        problem="The configured action was unavailable in preview.",
        behavior_contract="The configured action must remain available in preview.",
        resolution="Fixed",
        root_cause="The preview action registry omitted the configured action.",
        qa_oracle="Verify the action on the fixed build in both supported states.",
        risks=["regression"],
        resolution_context=(
            "[2025-04-01] Support: This configuration is a workaround and not a fix.\n"
            "[2025-04-10] Engineering: The product fix has been merged and verified on build 2606."
        ),
    )

    assert built is not None
    _, metadata = built
    assert metadata["historical_outcome"] == "implemented_fix"
    assert metadata["resolution_mechanism"] == "product_fix"
    assert metadata["resolution_evidence_source"] == "jira_comment_product_fix"
    assert metadata["learning_confidence"] == "high"
    assert metadata["is_verified_fix"] is True


def test_no_uac_image_move_fix_is_candidate_regression_evidence_with_build_provenance():
    enriched = JiraEnrichedDocument(
        jira_key="GUIDES-25769",
        summary="Unable to Drag and Drop Images from one place to another within a topic",
        description=(
            "In Author View, moving an image within the same topic breaks the image. "
            "The image reference no longer exists in Source view, causing data loss."
        ),
        status="Closed",
        resolution="Fixed",
        labels=["Automated", "KONE", "UAC_Not_Required", "Won't_Automate"],
        components=["Authoring"],
        domain="authoring",
        affected_features=["image_authoring"],
        dita_entities=["image"],
        qa_risk_tags=["critical", "customer-facing", "data-loss"],
        acceptance_criteria="UAC Not Required",
        comments_digest=(
            "[2025-01-24] QA: Verified on 5.0.207 this has been fixed.\n"
            "[2025-03-04] Engineering: This is already fixed in develop. Cherry picked for hotfix. "
            "https://git.corp.adobe.com/AdobeStarling/xmleditor/pull/5088/files\n"
            "[2025-03-11] QA: Verified on \"4.6.0.164\".\n"
            "[2025-04-05] QA: This is working fine on hotfix 4.6.4, hence closing this as fixed."
        ),
    )

    chunks = create_jira_chunks(enriched)
    learning = next(chunk for chunk in chunks if chunk["chunk_type"] == LEARNING_CHUNK_TYPE)

    assert learning["historical_outcome"] == "implemented_fix"
    assert learning["resolution_mechanism"] == "product_fix"
    assert learning["resolution_evidence_source"] == "jira_comment_product_fix"
    assert learning["qa_oracle_source"] == "jira_comment_version_validation"
    assert learning["behavior_contract_source"] == "missing"
    assert learning["behavior_contract_complete"] is False
    assert learning["root_cause_source"] == "missing"
    assert learning["learning_confidence"] == "caution"
    assert learning["is_verified_fix"] is False
    assert "5.0.207" in learning["chunk_text"]
    assert "4.6.0.164" in learning["chunk_text"]
    assert "hotfix 4.6.4" in learning["chunk_text"]
    assert "do not infer" in learning["chunk_text"]
    assert any(chunk["chunk_type"] == "uac_status_chunk" for chunk in chunks)
    assert not any(chunk["chunk_type"] == "acceptance_criteria_chunk" for chunk in chunks)


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
