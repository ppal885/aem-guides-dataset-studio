"""
Structured DITA draft before XML serialization.

Full AST types may extend this module later. Today the programmatic pipeline uses
:class:`TopicDraft`; :func:`serialize_structured_topic_draft` is the stable entry
point for that tree so callers do not depend on raw XML string building first.
"""

from __future__ import annotations

from app.core.schemas_chat_authoring import ChatDitaGenerationOptions, ReferenceStyleProfile
from app.services.dita_topic_draft import TopicDraft
from app.services.dita_topic_serializer import serialize_topic_draft

StructuredTopicDraft = TopicDraft


def serialize_structured_topic_draft(
    draft: StructuredTopicDraft,
    *,
    profile: ReferenceStyleProfile | None,
    options: ChatDitaGenerationOptions,
    ui_label_hints: set[str],
) -> str:
    """
    Serialize an internal draft model to DITA XML (declaration + DOCTYPE via normalize).

    Uses ElementTree only (no hand-built tag strings). Indentation follows
    ``ReferenceStyleProfile.xml_indent_style`` when set.
    """
    return serialize_topic_draft(draft, profile=profile, options=options, ui_label_hints=ui_label_hints)
