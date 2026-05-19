"""Hardcoded AEM Guides QA heuristics for the QA Copilot reasoning layer."""

from __future__ import annotations

from app.core.aem_guides_taxonomy import taxonomy_bullet_summary_for_prompt

# Reference text injected into LLM prompts (not retrieved from Jira).
AEM_GUIDES_QA_DOMAIN_KNOWLEDGE = """
AEM Guides / DITA QA focus areas (use when reasoning about risk, gaps, and test strategy):

References & linking:
- conref / conkeyref ranges, self-referenced content, duplicate IDs across maps
- keydef, keyref, keyscope chains; maps referencing keys across keyscopes
- xref / related-links resolution; broken refs after rename or move

Conditions & publishing:
- DITAVAL / filter attributes; profiling mistakes that silently drop content
- Multi-channel outputs: PDF, AEM Sites, HTML5 — validate each output contract
- Baseline / version/compare scenarios; reopened topics after baseline drift

Editors & UX:
- Web Editor vs Classic/oxygen workflows — regression when both coexist
- Save / reopen / collaboration (locking); merge or overwrite edge cases
- Preview accuracy vs published output (known source of false negatives)

Assets & content:
- Image MIME types, large assets, DAM path vs topic-relative paths
- metadata (dc:title, dc:format, other Dublin Core) in publish and search
- Large topics / Mongo BSON document size limits (symptoms: save failures, truncation)

APIs & validation (examples; verify against your deployment):
- Reference/listener and XML validation endpoints where configured
- Custom validation pipelines returning structured errors

Risk memos:
- Clipboard / paste from Word → hidden markup, inline styles, broken tables
- Localization: conref lang variants, translation memory vs source DITA
"""


def domain_block_for_prompt() -> str:
    bullets = taxonomy_bullet_summary_for_prompt()
    return f"{bullets}\n\n{AEM_GUIDES_QA_DOMAIN_KNOWLEDGE.strip()}"
