from types import SimpleNamespace

from app.services.jira_customer_profile_service import build_customer_profile_chunks


def _issue(key: str, summary: str, **overrides):
    values = {
        "jira_key": key,
        "summary": summary,
        "issue_type": "Customer Request",
        "status": "Closed",
        "priority": "Critical",
        "resolution": "Fixed",
        "domain": "publishing",
        "sub_domain": "publishing",
        "components": ["Publishing"],
        "affected_outputs": ["DITA-OT"],
        "affected_features": ["workflow"],
        "dita_entities": ["keyref"],
        "qa_risk_tags": ["customer-facing"],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_customer_profile_builds_counted_behavior_and_data_chunks():
    rows = [
        _issue("GUIDES-1", "Incremental publish fails for multiple ditavalrefs"),
        _issue(
            "GUIDES-2",
            "Oxygen cannot load DITA files from a folder with special characters",
            domain="uuid",
            components=["Oxygen", "Asset Management"],
            affected_outputs=[],
            dita_entities=["UUID"],
            priority="Major",
        ),
    ]

    chunks = build_customer_profile_chunks(rows, customer="EY", source_file_hash="a" * 64)

    assert {chunk["metadata"]["chunk_type"] for chunk in chunks} == {
        "customer_area_profile",
        "customer_jira_type_profile",
        "customer_data_workflow_profile",
        "customer_qa_risk_profile",
    }
    assert all(chunk["metadata"]["customer_key"] == "ey" for chunk in chunks)
    assert all(chunk["metadata"]["issue_count"] == 2 for chunk in chunks)
    joined = "\n".join(chunk["document"] for chunk in chunks)
    assert "Publishing (1)" in joined
    assert "Oxygen (1)" in joined
    assert "Conditional content and DITAVAL configuration (1)" in joined
    assert "Authoring or Oxygen integration (1)" in joined
    assert "GUIDES-1, GUIDES-2" in joined


def test_customer_profile_empty_input_produces_no_chunks():
    assert build_customer_profile_chunks([], customer="EY", source_file_hash="b" * 64) == []
