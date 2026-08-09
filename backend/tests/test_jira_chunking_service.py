"""Tests for smart Jira chunking (``jira_chunking_service``)."""

from __future__ import annotations

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_chunking_service import (
    SMART_JIRA_CHUNK_TYPES,
    build_comments_digest,
    create_jira_chunks,
    smart_chunks_to_chroma_rows,
)
from app.services.jira_uac_analysis_service import HISTORICAL_UAC_CHUNK_TYPES


def test_create_jira_chunks_has_required_keys():
    doc = JiraEnrichedDocument(
        jira_key="EPV-123",
        summary="Glossary publish",
        description="Expected: gloss works.\nActual: glossStatus wrong.\nSteps to reproduce: 1. open bookmap",
        issue_type="Bug",
        status="Open",
        priority="Major",
        labels=["l10n"],
        components=["Publishing"],
        customer_names=["Cisco"],
        domain="native_pdf",
        sub_domain="glossary",
        dita_entities=["glossentry", "glossStatus", "bookmap"],
        affected_outputs=["Native PDF"],
        expected_behavior="PDF matches editor",
        actual_behavior="glossentry dropped",
        qa_risk_tags=["regression"],
        automation_fit="Partial (5.0)",
        comments_digest="[2024-01-02] dev: verified repro on 4.3",
    )
    chunks = create_jira_chunks(doc)
    types = {c["chunk_type"] for c in chunks}
    assert types >= {
        "summary_chunk",
        "problem_chunk",
        "expected_actual_chunk",
        "comment_chunk",
        "reproduction_chunk",
        "qa_signal_chunk",
        "customer_signal_chunk",
        "domain_entity_chunk",
    }
    for c in chunks:
        assert set(c.keys()) >= {
            "jira_key",
            "chunk_type",
            "chunk_text",
            "domain",
            "customer_names",
            "affected_outputs",
            "dita_entities",
        }
        assert c["jira_key"] == "EPV-123"
        assert c["domain"] == "native_pdf"
    dom = next(x for x in chunks if x["chunk_type"] == "domain_entity_chunk")
    assert "EPV-123" in dom["chunk_text"]
    assert "native_pdf" in dom["chunk_text"].lower() or "glossary" in dom["chunk_text"].lower()
    assert "glossentry" in dom["chunk_text"]


def test_smart_chunk_types_disjoint_from_legacy_names():
    assert "summary_chunk" in SMART_JIRA_CHUNK_TYPES
    assert "full_ticket_summary" not in SMART_JIRA_CHUNK_TYPES


def test_uac_not_required_is_status_evidence_not_acceptance_contract():
    doc = JiraEnrichedDocument(
        jira_key="GUIDES-30001",
        summary="Configuration-gated navtitle button",
        status="Closed",
        resolution="Working as Designed",
        labels=["KONE", "Doc_Required"],
        acceptance_criteria="UAC Not Required",
    )

    chunks = create_jira_chunks(doc)
    chunk_types = {chunk["chunk_type"] for chunk in chunks}

    assert "uac_status_chunk" in chunk_types
    assert "acceptance_criteria_chunk" not in chunk_types
    assert not (chunk_types & HISTORICAL_UAC_CHUNK_TYPES)


def test_build_comments_digest_filters_short():
    comments = [
        {"author": "a", "created": "t", "body_text": "ok"},
        {"author": "b", "created": "t2", "body_text": "x" * 50 + " regression confirmed in publish"},
    ]
    d = build_comments_digest(comments)
    assert "regression" in d.lower()
    assert "ok" not in d


def test_create_jira_chunks_emits_deterministic_historical_uac_contracts():
    doc = JiraEnrichedDocument(
        jira_key="GUIDES-38333",
        summary="Native PDF reltable links",
        description="Reltable links are missing from Native PDF output.",
        status="Closed",
        resolution="Fixed",
        labels=["UAC_Done"],
        components=["Publishing"],
        domain="publishing",
        affected_outputs=["Native PDF"],
        acceptance_criteria=(
            "Problem Statement:\n"
            "Reltable links are missing from Native PDF output.\n"
            "Acceptance Criteria:\n"
            "Scope: Native PDF\n"
            "Map-level related links must render before topic-level related links.\n"
            "Mentioned with https://jira.corp.adobe.com/browse/GUIDES-22950\n"
            "Out of scope:\n"
            "HTML5 output is excluded."
        ),
        root_cause="The transform omitted reltable relationships.",
        test_plan="Generate Native PDF and verify the related-link order.",
    )

    chunks = create_jira_chunks(doc)
    uac_chunks = [chunk for chunk in chunks if chunk["chunk_type"] in HISTORICAL_UAC_CHUNK_TYPES]

    assert {chunk["chunk_type"] for chunk in uac_chunks} == HISTORICAL_UAC_CHUNK_TYPES
    assert all(chunk["uac_llm_used"] is False for chunk in uac_chunks)
    assert all(chunk["uac_source_authority"] == "jira_accepted_uac" for chunk in uac_chunks)
    assert all(chunk["uac_reuse_tier"] == "historical_verified" for chunk in uac_chunks)
    assert len({chunk["uac_source_hash"] for chunk in uac_chunks}) == 1


def test_comment_digest_prioritizes_latest_explicit_scope_beyond_regular_limit():
    comments = [
        {
            "author": "qa",
            "created": f"2024-11-{(index % 20) + 1:02d}T08:00:00.000+0000",
            "body_text": "Verified a regular regression scenario with enough detail to retain this comment.",
        }
        for index in range(45)
    ]
    comments.append(
        {
            "author": "qa lead",
            "created": "2024-11-26T09:00:00.000+0000",
            "body_text": (
                "Scope:\n"
                "Add new conditions via Folder Profile, ensuring existing conditions remain unchanged.\n"
                "Editing existing conditions must be done using XML Editor."
            ),
        }
    )

    digest = build_comments_digest(comments)

    assert digest.startswith("[2024-11-26T09:00:00.000+0000] qa lead: Scope:")
    assert "Editing existing conditions must be done using XML Editor" in digest


def test_create_jira_chunks_learns_accepted_final_scope_from_comment_when_field_is_empty():
    doc = JiraEnrichedDocument(
        jira_key="GUIDES-23526",
        summary="Conditional Attribute grouping lost through Folder Profile",
        description="Saving a new condition through Folder Profile can flatten existing groups.",
        status="Closed",
        resolution="Fixed",
        labels=["UAC_Done", "KONE"],
        components=["Authoring"],
        customer_names=["KONE"],
        domain="authoring",
        comments_digest=(
            "[2024-11-26T09:00:00.000+0000] qa: "
            "Editing an existing condition can reset its group and color; this is beyond the scope of this bug.\n"
            "Scope:\n"
            "- Add new conditions via Folder Profile, ensuring existing conditions remain unchanged.\n"
            "- Editing existing conditions must be done using XML Editor."
        ),
    )

    chunks = create_jira_chunks(doc)
    acceptance = next(chunk for chunk in chunks if chunk["chunk_type"] == "acceptance_criteria_chunk")
    contract = next(chunk for chunk in chunks if chunk["chunk_type"] == "historical_uac_contract_chunk")
    learning = next(chunk for chunk in chunks if chunk["chunk_type"] == "learning_behavior_chunk")

    assert acceptance["uac_source_origin"] == "jira_comment_accepted_scope"
    assert contract["uac_source_origin"] == "jira_comment_accepted_scope"
    assert contract["uac_source_authority"] == "jira_accepted_uac"
    assert "Folder Profile" in contract["chunk_text"]
    assert "jira_comment_accepted_scope" in learning["behavior_contract_source"]


def test_create_jira_chunks_marks_mainline_uac_as_candidate_for_hotfix_copy():
    doc = JiraEnrichedDocument(
        jira_key="GUIDES-29778",
        summary="Metadata Manage hotfix",
        status="Closed",
        resolution="Fixed",
        labels=["UAC_Done", "HotfixCandidate5.1"],
        acceptance_criteria="Common tags must be returned and Manage must disable until the API responds.",
        root_cause="The allAssets query omitted UUID-to-path conversion.",
        comments_digest=(
            "This ticket is created for 5.0.1 hotfix only.\n"
            "UAC mentioned in this ticket is done for 2507.\n"
            "For hotfix, we have just done the point fix."
        ),
        test_plan="Tested common tags and Manage disable/enable on hotfix 5.0.1.2.",
    )

    contract = next(
        chunk
        for chunk in create_jira_chunks(doc)
        if chunk["chunk_type"] == "historical_uac_contract_chunk"
    )

    assert contract["uac_release_scope_split"] is True
    assert contract["uac_reuse_tier"] == "candidate"
    assert contract["uac_contract_complete"] is False


def test_configuration_migration_resolution_metadata_reaches_chroma_rows():
    doc = JiraEnrichedDocument(
        jira_key="GUIDES-28667",
        summary="Custom Preview button requires toolbar migration",
        description="The custom Export PDF button appears only while the file is locked.",
        status="Closed",
        resolution="Fixed",
        labels=["KONE", "Doc_Required"],
        components=["Authoring"],
        comments_digest=(
            "The customer was unblocked, but this is still a workaround and not a fix.\n"
            "Custom buttons in ui_config.json would not work and need to be ported to editor_toolbar.js."
        ),
    )
    chunks = create_jira_chunks(doc)
    rows = smart_chunks_to_chroma_rows(
        doc.jira_key,
        {
            "key": doc.jira_key,
            "fields": {
                "summary": doc.summary,
                "description": doc.description,
                "labels": doc.labels,
                "components": [{"name": "Authoring"}],
            },
        },
        doc,
        chunks,
    )
    learning = next(row for row in rows if row["metadata"]["chunk_type"] == "learning_behavior_chunk")

    assert learning["metadata"]["historical_outcome"] == "configuration_migration"
    assert learning["metadata"]["resolution_mechanism"] == "configuration_migration"
    assert learning["metadata"]["resolution_evidence_source"] == "jira_comment_configuration_migration"
    assert learning["metadata"]["is_verified_fix"] is False
