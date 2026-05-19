"""Guides QA RAG (framework + bundled corpora in Chroma)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.auth import CurrentUser
from app.services.guides_qa_rag_service import guides_rag_full_reindex, guides_rag_health, guides_rag_query

router = APIRouter(dependencies=[CurrentUser])


@router.get("/health")
def get_guides_qa_rag_health_route() -> dict[str, Any]:
    return guides_rag_health()


@router.post("/reindex")
def guides_qa_rag_reindex() -> dict[str, Any]:
    return guides_rag_full_reindex()


class GuidesRagQueryBody(BaseModel):
    collection_key: str = Field(..., min_length=2, max_length=64)
    query: str = Field(..., min_length=1, max_length=12000)
    k: int = Field(default=8, ge=1, le=50)


@router.post("/query")
def guides_qa_rag_query_route(body: GuidesRagQueryBody) -> dict[str, Any]:
    return guides_rag_query(body.collection_key, body.query, body.k)


@router.post("/screenshots/upload")
def guides_qa_rag_screenshots_upload() -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={"detail": "Screenshot corpus upload is not implemented in this backend build."},
    )


@router.post("/screenshot-descriptions/record")
def guides_qa_rag_screenshot_descriptions_record() -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={"detail": "Screenshot description ingest is not implemented in this backend build."},
    )


@router.post("/visual-search")
def guides_qa_rag_visual_search() -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={"detail": "CLIP / visual search is not implemented in this backend build."},
    )
