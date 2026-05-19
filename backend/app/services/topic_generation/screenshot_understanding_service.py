"""
ScreenshotUnderstandingService — vision-based structured understanding (not OCR-only dump).

Delegates to ``extract_screenshot_context`` which returns :class:`ChatImageContext` with
:class:`ScreenshotContentModel` (sections, steps, tables, UI cues, confidence).
"""

from __future__ import annotations

from app.core.schemas_chat_authoring import ChatAttachmentRef, ChatImageContext
from app.core.structured_logging import get_structured_logger
from app.services.screenshot_understanding_service import extract_screenshot_context

logger = get_structured_logger(__name__)


class ScreenshotUnderstandingService:
    """Extensible facade: swap implementation or add caching without changing the pipeline."""

    async def understand(
        self,
        *,
        image: ChatAttachmentRef,
        image_bytes: bytes,
        user_prompt: str,
    ) -> ChatImageContext:
        try:
            ctx = await extract_screenshot_context(
                image=image,
                image_bytes=image_bytes,
                user_prompt=user_prompt,
            )
        except Exception as exc:
            logger.error_structured(
                "screenshot_understanding_failed",
                extra_fields={
                    "event": "screenshot_understanding_failed",
                    "asset_id": image.asset_id,
                    "error": str(exc),
                },
                exc_info=True,
            )
            raise
        logger.info_structured(
            "screenshot_understanding_ok",
            extra_fields={
                "event": "screenshot_understanding_ok",
                "asset_id": image.asset_id,
                "vision_provider": ctx.vision_provider,
                "structured_confidence": ctx.structured.confidence,
            },
        )
        return ctx
