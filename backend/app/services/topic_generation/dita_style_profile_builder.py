"""
DitaStyleProfileBuilder — reference topic → sanitized style profile only.

Uses ``analyze_reference_dita`` from the reference analyzer module: never copies
id, href, conref, keyref, or other link/navigation attributes into the profile.
"""

from __future__ import annotations

from app.core.schemas_chat_authoring import ReferenceStyleProfile
from app.services import reference_dita_analyzer as ref_analyzer

# Re-export for callers that want the low-level function without the class.
analyze_reference_dita = ref_analyzer.analyze_reference_dita


class DitaStyleProfileBuilder:
    def build(self, raw_xml: str) -> tuple[ReferenceStyleProfile, list[str]]:
        return ref_analyzer.analyze_reference_dita(raw_xml or "")
