from app.services import jira_history_search_service as service


def test_history_search_rejects_noncanonical_component_without_retrieval():
    result = service.search_jira_history_evidence(
        "save failure",
        component="Platform and Integration",
    )

    assert result["error"] == "Unsupported Jira component."
    assert "Platform" in result["allowed_components"]


def test_history_search_exposes_unavailable_retrieval(monkeypatch):
    monkeypatch.setattr("app.services.vector_store_service.is_chroma_available", lambda: False)
    monkeypatch.setattr("app.services.embedding_service.is_embedding_available", lambda: True)

    result = service.search_jira_history_evidence("xref scope failure", component="Editor")

    assert result["searched_jira_qa"] is False
    assert result["match_count"] == 0
    assert "Do NOT conclude" in result["note"]


def test_history_search_returns_sanitized_deduplicated_rows(monkeypatch):
    monkeypatch.setattr("app.services.vector_store_service.is_chroma_available", lambda: True)
    monkeypatch.setattr("app.services.vector_store_service.get_collection_count", lambda name: 31905)
    monkeypatch.setattr("app.services.embedding_service.is_embedding_available", lambda: True)
    monkeypatch.setattr(
        "app.services.jira_historical_uac_contract_service.load_historical_uac_contracts",
        lambda keys: {
            "GUIDES-101": {
                "schema_version": "historical-uac-v3",
                "jira_key": "GUIDES-101",
                "source_snapshot_id": "jira:GUIDES-101:uac:abc",
                "confirmed_ac_eligible": False,
                "current_ticket_authority": False,
                "reuse_mode": "historical_verified_contract",
            }
        },
    )
    monkeypatch.setattr(
        "app.services.jira_qa_retrieval_service.semantic_search_jira_qa",
        lambda query, **kwargs: [
            {
                "jira_key": "GUIDES-100",
                "title": "Current issue",
                "score": 1.0,
                "metadata": {"customer": "KONE"},
            },
            {
                "jira_key": "GUIDES-101",
                "title": "Prior issue",
                "score": 0.91,
                "why_similar": "Shared xref serializer",
                "matching_entities": ["xref"],
                "matching_components": ["Editor"],
                "metadata": {
                    "customer": "EY",
                    "customer_names": '["EY"]',
                    "status": "Closed",
                    "resolution": "Fixed",
                },
                "learning": {
                    "is_verified_fix": True,
                    "root_cause": "Scope omitted by serializer",
                    "qa_oracle": "Published xref remains clickable",
                },
                "uac_evidence": {
                    "schema_version": "historical-uac-v3",
                    "clause_id": "UAC-01",
                    "source_text": "Published xref remains clickable.",
                },
            },
            {
                "jira_key": "GUIDES-101",
                "title": "Duplicate chunk",
                "score": 0.8,
                "metadata": {"customer": "EY"},
            },
            {
                "jira_key": "GUIDES-102",
                "title": "Different customer",
                "score": 0.95,
                "metadata": {"customer": "KONE"},
            },
        ],
    )

    result = service.search_jira_history_evidence(
        "xref scope failure",
        component="Editor",
        customer="EY",
        exclude_jira_key="GUIDES-100",
        top_k=10,
    )

    assert result["searched_jira_qa"] is True
    assert result["indexed_chunks"] == 31905
    assert result["match_count"] == 1
    assert result["results"][0]["jira_key"] == "GUIDES-101"
    assert result["results"][0]["root_cause"] == "Scope omitted by serializer"
    assert result["results"][0]["qa_oracle"] == "Published xref remains clickable"
    assert result["results"][0]["uac_evidence"]["clause_id"] == "UAC-01"
    contract = result["results"][0]["historical_uac_contract"]
    assert contract["source_snapshot_id"] == "jira:GUIDES-101:uac:abc"
    assert contract["confirmed_ac_eligible"] is False
    assert contract["version_applicability"]["requires_current_ticket_validation"] is True
    assert result["results"][0]["historical_match"]["qualified"] is True
    assert result["results"][0]["mutable_facts"]["verified_live"] is False
    assert result["results"][0]["evidence_snapshot_id"].startswith(
        "jira:GUIDES-101:history:"
    )


def test_history_search_rejects_area_only_candidate(monkeypatch):
    monkeypatch.setattr("app.services.vector_store_service.is_chroma_available", lambda: True)
    monkeypatch.setattr("app.services.vector_store_service.get_collection_count", lambda name: 10)
    monkeypatch.setattr("app.services.embedding_service.is_embedding_available", lambda: True)
    monkeypatch.setattr(
        "app.services.jira_historical_uac_contract_service.load_historical_uac_contracts",
        lambda keys: {},
    )
    monkeypatch.setattr(
        "app.services.jira_qa_retrieval_service.semantic_search_jira_qa",
        lambda query, **kwargs: [
            {
                "jira_key": "GUIDES-333",
                "title": "Unrelated new editor issue",
                "score": 0.99,
                "matching_components": ["Editor"],
                "metadata": {"customer": "KONE", "components": '["Editor"]'},
            }
        ],
    )

    result = service.search_jira_history_evidence(
        "toolbar save loses xref scope",
        component="Editor",
        customer="KONE",
    )

    assert result["match_count"] == 0
    assert result["rejected_candidate_count"] == 1
    assert result["rejected_candidates"][0]["historical_match"]["area_only_rejected"] is True


def test_history_search_matches_customer_cohort_metadata(monkeypatch):
    monkeypatch.setattr("app.services.vector_store_service.is_chroma_available", lambda: True)
    monkeypatch.setattr("app.services.vector_store_service.get_collection_count", lambda name: 10)
    monkeypatch.setattr("app.services.embedding_service.is_embedding_available", lambda: True)
    monkeypatch.setattr(
        "app.services.jira_historical_uac_contract_service.load_historical_uac_contracts",
        lambda keys: {},
    )
    monkeypatch.setattr(
        "app.services.jira_qa_retrieval_service.semantic_search_jira_qa",
        lambda query, **kwargs: [
            {
                "jira_key": "GUIDES-52916",
                "title": "New Editor table paste regression",
                "score": 0.9,
                "why_similar": "New editor table paste serializer",
                "learning": {
                    "is_verified_fix": True,
                    "root_cause": "New editor table paste serializer regression",
                },
                "metadata": {
                    "customer": "",
                    "customer_cohorts": '["American Bureau of Shipping"]',
                    "enrich_customers": '["American Bureau of Shipping", "Triaged"]',
                    "components": '["Editor"]',
                },
            }
        ],
    )

    result = service.search_jira_history_evidence(
        "new editor table paste",
        component="Editor",
        customer="American Bureau of Shipping",
    )

    assert result["match_count"] == 1
    assert result["results"][0]["customers"] == ["American Bureau of Shipping"]
