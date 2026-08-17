from __future__ import annotations

from datetime import datetime

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.jira_enrichment_models import JiraCustomerProfile, JiraEnrichedIssue
from app.services import jira_customer_profile_service as service


def test_profile_uses_distinct_jira_keys_and_corpus_frequency_wording(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    db = Session()
    db.add_all(
        [
            JiraEnrichedIssue(
                jira_key="GUIDES-1",
                issue_type="Bug",
                summary="DITA map output preset fails for XML content",
                customer_cohorts=["IBM"],
                components=["Publishing", "Authoring"],
                domain="publishing",
                affected_outputs=["Native PDF", "DITA-OT"],
                affected_features=["workflow"],
                dita_entities=["output preset"],
                resolutions=["Fixed"],
                automation_fit="Partial",
                source_file_hashes=["a"],
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            ),
            JiraEnrichedIssue(
                jira_key="GUIDES-2",
                issue_type="Customer Request",
                summary="Review task for versioned DITA topic",
                customer_cohorts=["IBM", "Swift"],
                components=["Publishing"],
                domain="publishing",
                affected_outputs=["Native PDF"],
                affected_features=["review"],
                dita_entities=["baseline"],
                resolutions=["Done"],
                automation_fit="Yes",
                source_file_hashes=["b"],
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            ),
        ]
    )
    db.commit()
    db.close()
    monkeypatch.setattr(service, "SessionLocal", Session)
    monkeypatch.setattr(service, "embed_texts_batched", lambda docs, batch_size: np.zeros((len(docs), 3)))
    captured = {}
    monkeypatch.setattr(service, "delete_documents", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        service,
        "add_documents",
        lambda collection, ids, documents, metadata, embeddings: captured.update(
            {"documents": documents, "metadata": metadata}
        )
        is None,
    )

    result = service.rebuild_customer_profiles(["IBM"])

    assert result["profiles"]["IBM"]["issue_count"] == 2
    assert any("frequently represented or affected" in document for document in captured["documents"])
    assert all(item["aggregate_context"] is True for item in captured["metadata"])
    assert all(item["direct_assertion_allowed"] is False for item in captured["metadata"])
    stored = Session().query(JiraCustomerProfile).filter_by(customer_key="ibm").one()
    assert stored.issue_count == 2
    assert stored.bug_issue_count == 1
    assert stored.bug_issue_percent == 50.0
    assert stored.problem_report_count == 1
    assert stored.problem_report_percent == 50.0
    assert stored.components[0]["name"] == "Publishing"
    assert {item["name"] for item in stored.issue_types} == {"Bug", "Customer Request"}
    assert {item["name"] for item in stored.content_data_signals} >= {"DITA maps", "DITA topics", "XML content", "Review tasks"}
    assert any("Content and data patterns" in document for document in captured["documents"])
    assert any("reported-problem taxonomy" in document for document in captured["documents"])
    assert any("bug concentration" in document for document in captured["documents"])
    assert any("regression recommendations" in document for document in captured["documents"])
    assert any("test-data recommendations" in document for document in captured["documents"])
    assert {item["name"] for item in stored.bug_taxonomy} >= {"Publishing or output generation"}
    assert stored.bug_concentrations["by_component"][0]["name"] in {"Publishing", "Authoring"}
    assert stored.regression_recommendations
    assert {item["data_pattern"] for item in stored.test_data_recommendations} >= {"DITA maps"}
    assert stored.exploratory_recommendations
    assert stored.approval_status == "draft"
    assert stored.classification_quality["product_area_coverage_percent"] == 100.0

    metadata_updates = {}
    monkeypatch.setattr(
        service,
        "update_documents_metadata",
        lambda collection, where, metadata: metadata_updates.update(metadata) is None,
    )
    approved = service.set_customer_profile_approval(
        "IBM", status="approved", reviewer="qa-reviewer", notes="Validated against representative tickets"
    )
    assert approved["approval_status"] == "approved"
    assert approved["approved_by"] == "qa-reviewer"
    assert metadata_updates["reviewed_customer_profile"] is True

    service.rebuild_customer_profiles(["IBM"])
    assert all(item["approval_status"] == "approved" for item in captured["metadata"])
    assert all(item["reviewed_customer_profile"] is True for item in captured["metadata"])


def test_profile_bug_concentration_excludes_customer_requests_from_bug_denominator():
    bug = JiraEnrichedIssue(
        jira_key="GUIDES-10",
        issue_type="Bug",
        summary="Publishing job stuck for a large DITA map",
        customer_cohorts=["KONE"],
        components=["Publishing"],
        domain="publishing",
        affected_features=["workflow"],
    )
    request = JiraEnrichedIssue(
        jira_key="GUIDES-11",
        issue_type="Customer Request",
        summary="Add a publishing option",
        customer_cohorts=["KONE"],
        components=["Publishing"],
        domain="publishing",
        affected_features=["workflow"],
    )

    profile = service._build_profile("KONE", [bug, request])

    assert profile["bug_issue_count"] == 1
    assert profile["bug_issue_percent"] == 50.0
    assert profile["bug_concentrations"]["by_component"][0]["issue_count"] == 1
    assert profile["bug_concentrations"]["by_component"][0]["problem_report_share_percent"] == 100.0


def test_customer_request_with_failure_language_contributes_to_problem_taxonomy():
    request = JiraEnrichedIssue(
        jira_key="GUIDES-12",
        issue_type="Customer Request",
        summary="AEM Sites publishing job is stuck and cancellation fails",
        customer_cohorts=["JPMC"],
        components=["Publishing"],
        domain="publishing",
        affected_outputs=["AEM Sites"],
        affected_features=["workflow"],
    )

    profile = service._build_profile("JPMC", [request])

    assert profile["bug_issue_count"] == 0
    assert profile["problem_report_count"] == 1
    assert profile["problem_report_percent"] == 100.0
    assert {item["name"] for item in profile["bug_taxonomy"]} >= {
        "Publishing or output generation",
        "Workflow or job-state failure",
    }
