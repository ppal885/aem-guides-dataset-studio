from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.core.auth import UserIdentity
from app.evidence_gateway.config import CorpusConfig, EvidenceGatewaySettings, RepositoryConfig
from app.evidence_gateway.models import KnowledgeResult, SearchKnowledgeRequest
from app.evidence_gateway import repo_adapter


def test_mcp_tools_list_contract(client, auth_headers):
    response = client.post(
        "/mcp",
        headers=auth_headers,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    names = {tool["name"] for tool in payload["result"]["tools"]}
    assert {
        "health",
        "list_corpora",
        "search_knowledge",
        "fetch_evidence",
        "list_repositories",
        "search_code",
        "fetch_code_context",
        "get_code_diff",
    }.issubset(names)


def test_search_knowledge_enforces_authorized_corpora(monkeypatch):
    from app.evidence_gateway.service import EvidenceGatewayService

    settings = EvidenceGatewaySettings()
    settings.corpora = {
        "aem_guides": CorpusConfig("aem_guides", "aem_guides", "AEM", "documentation"),
        "dita_spec": CorpusConfig("dita_spec", "dita_spec", "DITA", "specification"),
    }
    settings.default_corpora = ("aem_guides",)
    user = UserIdentity(id="writer", roles=["writer"], allowed_tenants=["*"])

    def fake_search(query, corpus_ids, top_k, mode, settings):
        return [
            KnowledgeResult(
                chunk_id="aem_1",
                source_document_id="doc",
                corpus=corpus_ids[0],
                source_title="Title",
                canonical_uri="https://example.test/doc",
                relevance_score=1.0,
                retrieval_method="exact",
                passage="text",
            )
        ]

    monkeypatch.setattr("app.evidence_gateway.rag_adapter.search_knowledge", fake_search)
    service = EvidenceGatewayService(settings)

    allowed = service.search_knowledge(user, SearchKnowledgeRequest(query="baseline", corpus_ids=["aem_guides"]))
    assert allowed.results[0].corpus == "aem_guides"

    with pytest.raises(PermissionError):
        service.search_knowledge(user, SearchKnowledgeRequest(query="topicref", corpus_ids=["dita_spec"]))


def test_repository_search_and_context_are_read_only_and_bounded(tmp_path):
    repo = _make_repo(tmp_path)
    settings = EvidenceGatewaySettings()
    settings.subprocess_timeout_seconds = 5
    cfg = RepositoryConfig(alias="sample", root=repo)

    results = repo_adapter.search_code(cfg, "AEM Guides", "HEAD", ["src"], 5, settings)
    assert results
    assert results[0].relative_path == "src/example.txt"
    assert results[0].line_number == 1

    context = repo_adapter.fetch_code_context(
        cfg,
        revision="HEAD",
        relative_path="src/example.txt",
        start_line=1,
        end_line=2,
        correlation_id="cid",
        settings=settings,
    )
    assert context.lines == ["AEM Guides baseline", "DITA map"]


def test_repository_rejects_path_traversal(tmp_path):
    repo = _make_repo(tmp_path)
    settings = EvidenceGatewaySettings()
    cfg = RepositoryConfig(alias="sample", root=repo)

    with pytest.raises(ValueError):
        repo_adapter.fetch_code_context(
            cfg,
            revision="HEAD",
            relative_path="../secret.txt",
            start_line=1,
            end_line=1,
            correlation_id="cid",
            settings=settings,
        )


def test_repository_rejects_git_option_revision(tmp_path):
    repo = _make_repo(tmp_path)
    settings = EvidenceGatewaySettings()
    cfg = RepositoryConfig(alias="sample", root=repo)

    with pytest.raises(ValueError):
        repo_adapter.search_code(cfg, "text", "--help", [], 5, settings)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "example.txt").write_text("AEM Guides baseline\nDITA map\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "add", "src/example.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo

