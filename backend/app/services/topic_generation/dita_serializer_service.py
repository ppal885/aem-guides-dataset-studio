"""
DitaSerializerService — programmatic DITA XML from :class:`TopicDraft` + reference profile.

LLM-based XML generation stays in :meth:`ChatDitaAuthoringService._render_dita_xml_with_mode`
for low strictness; this service is the supported path for medium/high strictness.
"""

from __future__ import annotations

from app.core.schemas_chat_authoring import (
    ChatDitaGenerationOptions,
    ChatImageContext,
    ReferenceStyleProfile,
)
from app.services.dita_topic_draft import TopicDraft
from app.services.structured_topic_draft import serialize_structured_topic_draft


class DitaSerializerService:
    @staticmethod
    def collect_ui_label_hints(image_context: ChatImageContext) -> set[str]:
        st = image_context.structured
        hints: set[str] = {x.strip() for x in st.ui_labels if x.strip()}
        for x in st.button_names:
            if x.strip():
                hints.add(x.strip())
        for x in st.menu_names:
            if x.strip():
                hints.add(x.strip())
        for el in image_context.ui_elements:
            lab = str(el.get("label") or "").strip()
            if lab:
                hints.add(lab)
        return hints

    def serialize_structured_draft(
        self,
        draft: TopicDraft,
        *,
        profile: ReferenceStyleProfile | None,
        options: ChatDitaGenerationOptions,
        ui_label_hints: set[str],
    ) -> str:
        return serialize_structured_topic_draft(
            draft,
            profile=profile,
            options=options,
            ui_label_hints=ui_label_hints,
        )
