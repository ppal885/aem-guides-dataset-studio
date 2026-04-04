from __future__ import annotations

from fastapi import HTTPException, status

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


def raise_api_error(exc: Exception, *, default_detail: str) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    logger.error_structured(
        default_detail,
        extra_fields={"error": str(exc)},
        exc_info=True,
    )
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=default_detail) from exc
