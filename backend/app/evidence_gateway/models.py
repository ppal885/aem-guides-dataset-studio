from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class EvidenceError(BaseModel):
    code: str
    message: str
    correlation_id: str


class CorpusInfo(BaseModel):
    corpus_id: str
    display_name: str
    source_type: str
    available_versions: list[str] = Field(default_factory=list)
    last_indexed_timestamp: str | None = None
    document_count: int | None = None
    supported_filters: list[str] = Field(default_factory=list)


class SearchKnowledgeRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    corpus_ids: list[str] = Field(default_factory=list, max_length=8)
    source_versions: list[str] = Field(default_factory=list, max_length=8)
    source_types: list[str] = Field(default_factory=list, max_length=8)
    top_k: int = Field(default=5, ge=1, le=20)
    retrieval_mode: Literal["auto", "semantic", "exact"] = "auto"
    rerank: bool = True


class KnowledgeResult(BaseModel):
    chunk_id: str
    source_document_id: str
    corpus: str
    source_title: str
    source_version: str | None = None
    section: str | None = None
    canonical_uri: str
    indexed_timestamp: str | None = None
    relevance_score: float
    retrieval_method: str
    passage: str
    truncated: bool = False


class SearchKnowledgeResponse(BaseModel):
    correlation_id: str
    results: list[KnowledgeResult]


class FetchEvidenceRequest(BaseModel):
    chunk_ids: list[str] = Field(min_length=1, max_length=10)
    neighbor_window: int = Field(default=0, ge=0, le=2)


class EvidenceChunk(BaseModel):
    chunk_id: str
    selected: bool
    neighbor_of: str | None = None
    source_document_id: str
    corpus: str
    source_title: str
    source_version: str | None = None
    section: str | None = None
    canonical_uri: str
    indexed_timestamp: str | None = None
    text: str
    truncated: bool = False


class FetchEvidenceResponse(BaseModel):
    correlation_id: str
    chunks: list[EvidenceChunk]
    missing_chunk_ids: list[str] = Field(default_factory=list)


class RepositoryInfo(BaseModel):
    alias: str
    revision: str | None = None
    branch: str | None = None
    last_refreshed_timestamp: str | None = None
    diff_access_supported: bool = True


class SearchCodeRequest(BaseModel):
    repository_alias: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=1, max_length=500)
    revision: str | None = Field(default=None, max_length=128)
    path_filters: list[str] = Field(default_factory=list, max_length=16)
    max_results: int = Field(default=20, ge=1, le=50)


class CodeSearchResult(BaseModel):
    repository_alias: str
    revision: str
    relative_path: str
    line_number: int
    line: str
    context_before: list[str] = Field(default_factory=list)
    context_after: list[str] = Field(default_factory=list)
    truncated: bool = False


class SearchCodeResponse(BaseModel):
    correlation_id: str
    results: list[CodeSearchResult]


class FetchCodeContextRequest(BaseModel):
    repository_alias: str = Field(min_length=1, max_length=80)
    revision: str = Field(min_length=1, max_length=128)
    relative_path: str = Field(min_length=1, max_length=500)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    @field_validator("end_line")
    @classmethod
    def _line_order(cls, value: int, info):
        start = info.data.get("start_line")
        if start and value < start:
            raise ValueError("end_line must be greater than or equal to start_line")
        return value


class FetchCodeContextResponse(BaseModel):
    correlation_id: str
    repository_alias: str
    revision: str
    relative_path: str
    start_line: int
    end_line: int
    lines: list[str]
    truncated: bool = False


class GetCodeDiffRequest(BaseModel):
    repository_alias: str = Field(min_length=1, max_length=80)
    base_revision: str = Field(min_length=1, max_length=128)
    head_revision: str = Field(min_length=1, max_length=128)
    path_filters: list[str] = Field(default_factory=list, max_length=16)
    max_response_bytes: int = Field(default=120_000, ge=1_000, le=500_000)


class GetCodeDiffResponse(BaseModel):
    correlation_id: str
    repository_alias: str
    base_revision: str
    head_revision: str
    diff: str
    truncated: bool = False


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

