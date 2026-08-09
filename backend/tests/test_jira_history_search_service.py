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


def test_history_search_matches_customer_cohort_metadata(monkeypatch):
    monkeypatch.setattr("app.services.vector_store_service.is_chroma_available", lambda: True)
    monkeypatch.setattr("app.services.vector_store_service.get_collection_count", lambda name: 10)
    monkeypatch.setattr("app.services.embedding_service.is_embedding_available", lambda: True)
    monkeypatch.setattr(
        "app.services.jira_qa_retrieval_service.semantic_search_jira_qa",
        lambda query, **kwargs: [
            {
                "jira_key": "GUIDES-52916",
                "title": "New Editor table paste regression",
                "score": 0.9,
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
