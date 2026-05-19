"""
ReferenceDitaAnalyzer — parse reference DITA and produce :class:`ChatReferenceDitaSummary`.

Structure + style notes for planning; profile is built via sanitized analysis only.
"""

from __future__ import annotations

from app.core.schemas_chat_authoring import ChatAttachmentRef, ChatReferenceDitaSummary
from app.core.structured_logging import get_structured_logger
from app.services import reference_dita_analyzer as ref_analyzer

logger = get_structured_logger(__name__)


class ReferenceDitaAnalyzer:
    async def summarize_attachment(
        self,
        *,
        reference_attachment: ChatAttachmentRef | None,
        reference_text: str,
    ) -> ChatReferenceDitaSummary:
        if not reference_attachment or not (reference_text or "").strip():
            logger.info_structured(
                "reference_dita_skipped",
                extra_fields={"event": "reference_dita_skipped", "reason": "no_attachment_or_empty"},
            )
            return ChatReferenceDitaSummary(
                style_notes=["Use a conservative, validation-safe DITA 1.3 structure."],
                structure_summary="No reference DITA file was attached.",
                style_profile=None,
            )
        profile, _warnings = ref_analyzer.analyze_reference_dita(reference_text)
        summary = ref_analyzer.build_reference_summary(
            filename=reference_attachment.filename,
            raw_text=reference_text,
            profile=profile,
        )
        logger.info_structured(
            "reference_dita_analyzed",
            extra_fields={
                "event": "reference_dita_analyzed",
                "filename": reference_attachment.filename,
                "root_type": summary.root_type,
                "parse_warning_count": len(profile.parse_warnings or []),
            },
        )
        return summary
