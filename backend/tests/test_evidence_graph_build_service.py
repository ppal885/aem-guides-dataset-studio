import json

from app.db.dita_spec_models import DitaSpecChunk
from app.db.jira_enrichment_models import JiraEnrichedIssue, JiraIssueChunk
from app.services.evidence_graph_build_service import (
    GraphCollector,
    _build_dita_sql_chunk,
    _build_doc_record,
    _build_jira_chroma_record,
    _build_jira_issue,
    _canonical_release_value,
    _release_from_url,
)
from app.services.evidence_graph_contract import stable_key


def _edge(collector: GraphCollector, relation: str):
    return [edge for edge in collector.edges.values() if edge.relation == relation]


def test_release_urls_map_to_canonical_release_keys():
    assert _release_from_url(
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/release-info/"
        "release-notes/cloud-release-notes/2025-releases/2502-release/whats-new-2025-02-0"
    ) == ("cloud", "2025.02.0")
    assert _release_from_url(
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/release-info/"
        "release-notes/cloud-release-notes/2024-releases/2410-0-sp1-release/fixed-issues-2024-10-0-sp1"
    ) == ("cloud", "2024.10.0-sp1")
    assert _release_from_url(
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/release-info/"
        "release-notes/on-prem-release-notes/500-sp1-release/fixed-issues-5-0-0-sp1"
    ) == ("on-prem", "5.0.0-sp1")
    assert _release_from_url(
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/release-info/"
        "release-notes/44-release/44-release-notes/release-notes-4-4"
    ) == ("on-prem", "4.4")
    assert _canonical_release_value("AEM Guides Cloud 2025.2.0") == ("cloud", "2025.02.0")
    assert _canonical_release_value("5.0.0 SP1") == ("on-prem", "5.0.0-sp1")


def test_official_document_claim_requires_exact_source_containment():
    collector = GraphCollector()
    claim = "The editor preserves the external xref when scope is external."
    counts = _build_doc_record(
        collector,
        {
            "id": "doc-1",
            "document": f"Before publishing, {claim} Validate the generated output.",
            "metadata": {
                "title": "Cross references",
                "source_url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/cross-references",
                "source_type": "experienceleague",
                "workflow_cues": [claim, "The editor invents a missing target automatically."],
                "detected_constructs": ["xref", "@scope"],
                "output_contexts": ["HTML5"],
            },
        },
    )

    behavior_edges = _edge(collector, "HAS_EXPECTED_BEHAVIOR")
    assert len(behavior_edges) == 1
    assert collector.nodes[behavior_edges[0].target_key].label == claim
    assert behavior_edges[0].trust_tier == "authoritative"
    assert behavior_edges[0].properties["exact_source_text"] is True
    assert counts["derived_claims_rejected"] == 1
    assert _edge(collector, "DOCUMENTS_OUTPUT")
    assert len(_edge(collector, "MENTIONS_DITA_ENTITY")) == 2


def test_fixed_jira_requires_explicit_contract_rca_and_oracle_for_verified_history(monkeypatch):
    monkeypatch.setenv("EVIDENCE_GRAPH_DEFAULT_TENANT_ID", "kone")
    collector = GraphCollector()
    issue = JiraEnrichedIssue(
        jira_key="GUIDES-123",
        summary="External xref breaks during publish",
        description="POST /bin/fmdita/publish returns LinkResolutionException.",
        status="Closed",
        resolution="Fixed",
        components=["Editor"],
        customer_names=["KONE"],
        domain="authoring",
        affected_outputs=["Native PDF"],
        dita_entities=["xref", "@scope"],
        expected_behavior="External xrefs retain scope=external and remain clickable.",
        actual_behavior="The published link is removed.",
    )
    chunks = [
        JiraIssueChunk(
            jira_key="GUIDES-123",
            chunk_type="resolution_rca_chunk",
            chunk_text="Root cause: scope was dropped by the link serializer.",
        ),
        JiraIssueChunk(
            jira_key="GUIDES-123",
            chunk_type="test_evidence_chunk",
            chunk_text="Publish PDF and verify the external target remains clickable.",
        ),
    ]

    _build_jira_issue(collector, issue, chunks)

    assert collector.nodes[stable_key("jira_issue", "GUIDES-123")].tenant_id == "kone"
    assert all(node.tenant_id == "kone" for node in collector.nodes.values())
    assert all(
        evidence.tenant_id == "kone"
        for node in collector.nodes.values()
        for evidence in node.evidence
    )
    assert all(
        evidence.tenant_id == "kone"
        for edge in collector.edges.values()
        for evidence in edge.evidence
    )
    assert _edge(collector, "IN_DOMAIN")[0].properties == {"ranking_only": True}
    assert _edge(collector, "IN_COMPONENT")[0].target_key == stable_key("component", "Editor")
    assert _edge(collector, "HAS_ROOT_CAUSE")[0].trust_tier == "historical_verified"
    oracle = _edge(collector, "HAS_QA_ORACLE")[0]
    assert oracle.trust_tier == "historical_verified"
    assert oracle.properties["qa_oracle_source"] == "explicit_test_evidence"


def test_generated_fallback_oracle_never_becomes_trusted():
    collector = GraphCollector()
    issue = JiraEnrichedIssue(
        jira_key="GUIDES-124",
        summary="Image map hotspot regression",
        status="Closed",
        resolution="Fixed",
        components=["Editor"],
        domain="unknown",
        expected_behavior="Hotspots remain clickable in Preview.",
    )
    chunks = [
        JiraIssueChunk(
            jira_key="GUIDES-124",
            chunk_type="learning_behavior_chunk",
            chunk_text=(
                "QA oracle: Verify the captured behavior contract across supported outputs. "
                "Regression risks: preview links"
            ),
        )
    ]

    _build_jira_issue(collector, issue, chunks)

    oracle = _edge(collector, "HAS_QA_ORACLE")[0]
    assert oracle.trust_tier == "candidate"
    assert oracle.confidence == 0.2
    assert oracle.properties == {
        "qa_oracle_source": "derived_contract_fallback",
        "cannot_define_expected_behavior": True,
    }
    assert _edge(collector, "IN_DOMAIN")[0].properties["ranking_only"] is True


def test_closed_without_implemented_fix_resolution_is_not_historical_verified():
    collector = GraphCollector()
    issue = JiraEnrichedIssue(
        jira_key="GUIDES-125",
        summary="External xref regression",
        status="Closed",
        resolution="Closed",
        components=["Editor"],
        expected_behavior="Published xref remains clickable.",
    )
    chunks = [
        JiraIssueChunk(
            jira_key="GUIDES-125",
            chunk_type="resolution_rca_chunk",
            chunk_text="Root cause: scope omitted by serializer.",
        ),
        JiraIssueChunk(
            jira_key="GUIDES-125",
            chunk_type="test_evidence_chunk",
            chunk_text="Publish and verify the link is clickable.",
        ),
    ]

    _build_jira_issue(collector, issue, chunks)

    assert _edge(collector, "HAS_ROOT_CAUSE")[0].trust_tier == "supporting"
    assert _edge(collector, "HAS_QA_ORACLE")[0].trust_tier == "supporting"


def test_learning_chunk_needs_contract_rca_and_oracle_before_verified_promotion():
    collector = GraphCollector()
    _build_jira_chroma_record(
        collector,
        {
            "id": "GUIDES-126::learning",
            "document": (
                "Behavior contract: External xrefs remain clickable.\n"
                "Root cause evidence: Not explicitly captured.\n"
                "QA oracle: Not explicitly captured."
            ),
            "metadata": {
                "jira_key": "GUIDES-126",
                "chunk_type": "learning_behavior_chunk",
                "historical_outcome": "implemented_fix",
                "learning_confidence": "high",
                "is_verified_fix": True,
            },
        },
    )

    behavior = _edge(collector, "HAS_EXPECTED_BEHAVIOR")[0]
    assert behavior.trust_tier == "candidate"
    assert behavior.properties["cannot_define_expected_behavior"] is True
    assert not _edge(collector, "HAS_ROOT_CAUSE")
    assert not _edge(collector, "HAS_QA_ORACLE")


def test_dita_adapter_cites_attributes_children_specialization_and_constraints():
    collector = GraphCollector()
    chunk = DitaSpecChunk(
        id="dita-xref-1",
        element_name="xref-specialized",
        content_type="element_reference",
        parent_element="ph",
        children_elements=json.dumps(["keyword", "text"]),
        attributes=json.dumps(
            {
                "@dir": "Writing direction",
                "@domains": "Specialization domains",
                "sort-as": "Sort key",
                "@scope": "Target scope",
            }
        ),
        text_content=(
            "xref-specialized is a specialization of xref and is a constraint of ph."
        ),
        source_url="https://docs.oasis-open.org/dita/v1.3/os/part3-all-inclusive/langRef/xref.html",
    )

    _build_dita_sql_chunk(collector, chunk)

    attribute_targets = {edge.target_key for edge in _edge(collector, "HAS_ATTRIBUTE")}
    assert stable_key("dita_attribute", "dir") in attribute_targets
    assert stable_key("dita_attribute", "domains") in attribute_targets
    assert stable_key("dita_attribute", "sort-as") in attribute_targets
    assert stable_key("dita_attribute", "scope") in attribute_targets
    assert {edge.target_key for edge in _edge(collector, "SPECIALIZES")} == {
        stable_key("dita_element", "xref")
    }
    assert {edge.target_key for edge in _edge(collector, "CONSTRAINS")} == {
        stable_key("dita_element", "ph")
    }
    assert len(_edge(collector, "ALLOWS_CHILD")) == 3
    assert all(edge.evidence and edge.evidence[0].source_ref.startswith("https://docs.oasis-open.org") for edge in collector.edges.values())
