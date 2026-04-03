"""
Post-generation checks for LLM DITA output, keyed to the same patterns as jira_dita_pattern_hints.

Failures return human-readable repair instructions (appended on retry). Logging only by default
when repair is disabled or max repairs exhausted.
"""
import re
from typing import Dict, List

from app.services.jira_dita_pattern_hints import matched_pattern_ids

# Subset of align-related signals (evidence must suggest alignment semantics, not just "table")
_ALIGN_EVIDENCE_TERMS = (
    "@align",
    "align=",
    "cell alignment",
    "text alignment",
    "table alignment",
    "align attribute",
    "alignment",
    "justify",
    "center align",
    "right align",
    "left align",
)


def _evidence_suggests_align_semantics(evidence_text: str) -> bool:
    if not evidence_text:
        return False
    lower = evidence_text.lower()
    if not any(t in lower for t in ("table", "tgroup", "colspec", "entry", "cell", "column")):
        return False
    return any(t in lower for t in _ALIGN_EVIDENCE_TERMS)


def _combined_output_text(output: Dict[str, bytes]) -> str:
    parts: List[str] = []
    for content_bytes in output.values():
        try:
            parts.append(content_bytes.decode("utf-8", errors="ignore"))
        except Exception:
            continue
    return "\n".join(parts)


def validate_llm_dita_patterns(
    evidence_text: str,
    output: Dict[str, bytes],
) -> List[str]:
    """
    Run pattern-specific validators for patterns that matched the evidence at generation time.

    Returns a list of repair instructions (empty if OK).
    """
    if not output:
        return []

    patterns = matched_pattern_ids(evidence_text)
    if not patterns:
        return []

    combined = _combined_output_text(output)
    lower = combined.lower()
    issues: List[str] = []

    if "table_semantics" in patterns and _evidence_suggests_align_semantics(evidence_text):
        has_table = bool(re.search(r"<\s*table\b", lower, re.IGNORECASE))
        has_align_attr = 'align="' in lower or "align='" in lower
        if not has_table and not has_align_attr:
            issues.append(
                "Evidence calls for table alignment semantics: include at least one <table> with "
                "<tgroup>/<row>/<entry> and demonstrate align on <colspec> or <entry>, "
                "or a two-column reference table documenting align values (left, right, center, justify, char)."
            )

    if "rte_inline" in patterns:
        ev_lower = evidence_text.lower()
        rte_signal = any(
            k in ev_lower
            for k in (
                "cursor",
                "arrow key",
                "rich text editor",
                " rte",
                "inline tag",
                "nested tag",
                "editor behavior",
            )
        )
        if rte_signal:
            has_inline = any(tag in lower for tag in ("<b>", "<i>", "<u>"))
            if not has_inline:
                issues.append(
                    "Evidence describes RTE or inline formatting: include nested <b>, <i>, and/or <u> "
                    "inside <p> in a topic body (no images-only workaround)."
                )

    if "keyref_chain" in patterns:
        ev_lower = evidence_text.lower()
        chain_signal = any(
            k in ev_lower
            for k in (
                "nested keydef",
                "keydef chain",
                "keymap",
                "map hierarchy",
                "intermediate keymap",
            )
        )
        if chain_signal:
            has_key = "keydef" in lower or "keyref" in lower
            if not has_key:
                issues.append(
                    "Evidence describes keydef/keyref or nested maps: output must include <keydef> "
                    "and/or <topicref keyref=\"...\"/> (or equivalent) in a <map>, not topic-only prose."
                )

    return issues
