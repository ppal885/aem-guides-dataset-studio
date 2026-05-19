"""
TopicTypeInferenceService — chooses task | concept | reference | topic from options,
prompt heuristics, screenshot IR, and reference root type (no brittle XML regex on output).
"""

from __future__ import annotations

from app.core.schemas_chat_authoring import (
    ChatDitaGenerationOptions,
    ChatDitaType,
    ChatImageContext,
    ReferenceStyleProfile,
)
from app.services.dita_topic_draft import infer_topic_type


class TopicTypeInferenceService:
    def infer(
        self,
        *,
        options: ChatDitaGenerationOptions,
        user_prompt: str,
        image_context: ChatImageContext,
        profile: ReferenceStyleProfile | None,
    ) -> ChatDitaType:
        return infer_topic_type(
            options=options,
            user_prompt=user_prompt,
            image_context=image_context,
            profile=profile,
        )
