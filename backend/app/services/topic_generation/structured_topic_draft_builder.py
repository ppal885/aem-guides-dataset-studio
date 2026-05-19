"""
StructuredTopicDraftBuilder — merge screenshot IR into semantic plan, then build :class:`TopicDraft`.

No raw XML is produced here; serialization is a separate step (:class:`DitaSerializerService`
or LLM render path in the authoring service).
"""

from __future__ import annotations

from app.core.schemas_chat_authoring import ChatImageContext, ChatSemanticPlan, ScreenshotContentModel
from app.services.dita_topic_draft import TopicDraft, build_topic_draft, merge_structured_into_plan


class StructuredTopicDraftBuilder:
    def merge_screenshot_ir(self, plan: ChatSemanticPlan, structured: ScreenshotContentModel) -> ChatSemanticPlan:
        return merge_structured_into_plan(plan, structured)

    def build_draft(self, *, plan: ChatSemanticPlan, image_context: ChatImageContext) -> TopicDraft:
        return build_topic_draft(plan=plan, image_context=image_context)
