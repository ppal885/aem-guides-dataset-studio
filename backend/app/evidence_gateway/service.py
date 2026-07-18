from __future__ import annotations

from uuid import uuid4

from app.core.auth import UserIdentity
from app.evidence_gateway import authz, rag_adapter, repo_adapter
from app.evidence_gateway.config import EvidenceGatewaySettings, get_settings
from app.evidence_gateway.models import (
    CorpusInfo,
    FetchCodeContextRequest,
    FetchCodeContextResponse,
    FetchEvidenceRequest,
    FetchEvidenceResponse,
    GetCodeDiffRequest,
    GetCodeDiffResponse,
    RepositoryInfo,
    SearchCodeRequest,
    SearchCodeResponse,
    SearchKnowledgeRequest,
    SearchKnowledgeResponse,
)
from app.services.embedding_service import get_embedding_diagnostics
from app.services.vector_store_service import is_chroma_available


class EvidenceGatewayService:
    def __init__(self, settings: EvidenceGatewaySettings | None = None) -> None:
        self.settings = settings or get_settings()

    def health(self, user: UserIdentity, correlation_id: str | None = None) -> dict:
        cid = correlation_id or str(uuid4())
        authz.ensure_gateway_access(user, self.settings)
        counts = rag_adapter.collection_status(self.settings)
        return {
            "status": "ok" if is_chroma_available() else "degraded",
            "service_version": self.settings.service_version,
            "correlation_id": cid,
            "rag": {
                "vector_database": "chromadb",
                "available": is_chroma_available(),
                "embedding": get_embedding_diagnostics(),
                "collections": counts,
            },
            "repositories": {
                "available": bool(self.settings.repositories),
                "count": len(authz.authorized_repositories(user, self.settings)),
            },
        }

    def list_corpora(self, user: UserIdentity) -> list[CorpusInfo]:
        allowed = authz.authorized_corpora(user, self.settings)
        counts = rag_adapter.collection_status(self.settings)
        return [
            CorpusInfo(
                corpus_id=cfg.corpus_id,
                display_name=cfg.display_name,
                source_type=cfg.source_type,
                available_versions=list(cfg.versions),
                document_count=counts.get(cfg.corpus_id),
                supported_filters=["corpus_ids", "source_versions", "source_types"],
            )
            for cid, cfg in sorted(self.settings.corpora.items())
            if cid in allowed
        ]

    def search_knowledge(self, user: UserIdentity, request: SearchKnowledgeRequest, correlation_id: str | None = None) -> SearchKnowledgeResponse:
        cid = correlation_id or str(uuid4())
        corpus_ids = authz.require_corpora(user, self.settings, request.corpus_ids)
        results = rag_adapter.search_knowledge(
            request.query,
            corpus_ids=corpus_ids,
            top_k=request.top_k,
            mode=request.retrieval_mode,
            settings=self.settings,
        )
        return SearchKnowledgeResponse(correlation_id=cid, results=results)

    def fetch_evidence(self, user: UserIdentity, request: FetchEvidenceRequest, correlation_id: str | None = None) -> FetchEvidenceResponse:
        cid = correlation_id or str(uuid4())
        allowed = authz.authorized_corpora(user, self.settings)
        chunks, missing = rag_adapter.fetch_chunks(request.chunk_ids, request.neighbor_window, allowed, self.settings)
        return FetchEvidenceResponse(correlation_id=cid, chunks=chunks, missing_chunk_ids=missing)

    def list_repositories(self, user: UserIdentity) -> list[RepositoryInfo]:
        allowed = authz.authorized_repositories(user, self.settings)
        repos = {alias: repo for alias, repo in self.settings.repositories.items() if alias in allowed}
        return repo_adapter.list_repositories(repos, self.settings)

    def search_code(self, user: UserIdentity, request: SearchCodeRequest, correlation_id: str | None = None) -> SearchCodeResponse:
        cid = correlation_id or str(uuid4())
        authz.require_repository(user, self.settings, request.repository_alias)
        repo = self.settings.repositories[request.repository_alias]
        results = repo_adapter.search_code(repo, request.query, request.revision, request.path_filters, request.max_results, self.settings)
        return SearchCodeResponse(correlation_id=cid, results=results)

    def fetch_code_context(self, user: UserIdentity, request: FetchCodeContextRequest, correlation_id: str | None = None) -> FetchCodeContextResponse:
        cid = correlation_id or str(uuid4())
        authz.require_repository(user, self.settings, request.repository_alias)
        return repo_adapter.fetch_code_context(
            self.settings.repositories[request.repository_alias],
            request.revision,
            request.relative_path,
            request.start_line,
            request.end_line,
            cid,
            self.settings,
        )

    def get_code_diff(self, user: UserIdentity, request: GetCodeDiffRequest, correlation_id: str | None = None) -> GetCodeDiffResponse:
        cid = correlation_id or str(uuid4())
        authz.require_repository(user, self.settings, request.repository_alias)
        return repo_adapter.get_code_diff(
            self.settings.repositories[request.repository_alias],
            request.base_revision,
            request.head_revision,
            request.path_filters,
            request.max_response_bytes,
            cid,
            self.settings,
        )

