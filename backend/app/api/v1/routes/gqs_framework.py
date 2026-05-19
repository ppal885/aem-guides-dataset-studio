"""Guides QA framework index (XPath library, page methods, step phrases) — health + reindex."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.core.auth import CurrentUser
from app.services.framework_index_service import build_framework_indexes, read_framework_qa_health

router = APIRouter(dependencies=[CurrentUser])


@router.get("/qa-health")
def framework_qa_health() -> dict[str, Any]:
    return read_framework_qa_health()


@router.post("/reindex")
def framework_reindex() -> dict[str, Any]:
    return build_framework_indexes()
