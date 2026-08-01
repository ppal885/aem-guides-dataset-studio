from pathlib import Path

from app.services.aem_guides_incident_answer_service import answer_aem_sites_oak_conflict_from_jira
from app.services.jira_csv_import_service import parse_jira_csv_bytes
from app.services.jira_enrichment_service import enrich_jira
from app.services.jira_qa_chunking_service import build_jira_qa_chunks


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = REPOSITORY_ROOT / "backend" / "storage" / "manual_jira_imports" / "GUIDES-53121.csv"


def test_guides_53121_csv_builds_high_signal_incident_chunks():
    parsed = parse_jira_csv_bytes(CSV_PATH.read_bytes(), CSV_PATH.name).issues[0]
    enriched = enrich_jira(parsed.issue)
    enriched.root_cause = parsed.root_cause
    enriched.test_plan = parsed.test_plan
    enriched.resolution = parsed.resolution
    enriched.linked_issue_refs = parsed.linked_issue_refs
    chunks = build_jira_qa_chunks(
        parsed.issue_key,
        parsed.issue,
        comments=parsed.comments,
        linked_issues=[],
        enriched=enriched,
    )
    chunk_types = {chunk["metadata"]["chunk_type"] for chunk in chunks}

    assert "resolution_rca_chunk" in chunk_types
    assert "test_evidence_chunk" in chunk_types
    assert "linked_issue_chunk" in chunk_types
    assert all("@AdobeOrg" not in chunk["document"] for chunk in chunks)


def test_oak_conflict_answer_uses_jira_boundaries(monkeypatch):
    rows = [
        {"chunk_type": "resolution_rca_chunk", "document": "OakState0002 during JCR commit."},
        {"chunk_type": "test_evidence_chunk", "document": "Sequential execution is temporary mitigation."},
    ]
    monkeypatch.setattr(
        "app.services.jira_qa_retrieval_service.get_chunks_for_jira_key",
        lambda jira_key: rows if jira_key == "GUIDES-53121" else [],
    )

    answer = answer_aem_sites_oak_conflict_from_jira(
        "How should AEM Guides recover from OakState0002 during concurrent AEM Sites publishing?"
    )

    assert answer is not None
    assert "does **not** establish an automatic AEM Guides recovery mechanism" in answer
    assert "temporary incident-derived mitigation" in answer
    assert "full-map overwrite/orphan-page behavior is **not** evidence" in answer
    assert "Support or Cloud Ops ownership" in answer
    assert "Use generate_dita_ot_output" not in answer


def test_incident_answer_falls_back_without_exact_chunks(monkeypatch):
    monkeypatch.setattr(
        "app.services.jira_qa_retrieval_service.get_chunks_for_jira_key",
        lambda jira_key: [],
    )

    assert answer_aem_sites_oak_conflict_from_jira("Explain OakState0002 in AEM Sites publishing") is None
    assert answer_aem_sites_oak_conflict_from_jira("What is searchtitle?") is None
