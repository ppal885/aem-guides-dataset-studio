"""
Compose small pattern-specific instruction blocks for the LLM DITA fallback.

Keeps llm_dita_generator.txt focused on global rules; heterogeneous Jira issues
pull in only the modules that match their text.
"""
import re
from pathlib import Path

PATTERN_MODULES_DIR = (
    Path(__file__).resolve().parent.parent / "templates" / "prompts" / "pattern_modules"
)

# (pattern_id, module_filename_stem) — stem must match pattern_modules/<stem>.txt
PATTERN_IDS = ("table_semantics", "rte_inline", "keyref_chain")

# Keyword groups: if any phrase matches evidence (substring, case-insensitive), pattern applies.
_PATTERN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "table_semantics": (
        "table",
        "tgroup",
        "colspec",
        "tbody",
        "thead",
        "row",
        "entry",
        "cell",
        "column",
        "@align",
        "align=",
        "cell alignment",
        "text alignment",
        "table alignment",
        "align attribute",
        "right-click",
        "right click",
        "delete column",
        "merge cell",
    ),
    "rte_inline": (
        "cursor",
        "arrow key",
        "arrow keys",
        "rich text editor",
        "inline tag",
        "italic tag",
        "bold tag",
        "<i>",
        "<b>",
        "<u>",
        "nested tag",
        "editor behavior",
        "keyboard navigation",
    ),
    "keyref_chain": (
        "keydef",
        "keyref",
        "keymap",
        "nested keydef",
        "keydef chain",
        "nested keymap",
        "map hierarchy",
        "intermediate keymap",
        "key scope",
        "keyscope",
        "duplicate key",
        "unresolved key",
    ),
}


def matched_pattern_ids(evidence_text: str) -> list[str]:
    """Return pattern ids whose keywords appear in evidence (stable order)."""
    if not evidence_text or not isinstance(evidence_text, str):
        return []
    lower = evidence_text.lower()
    out: list[str] = []
    for pid in PATTERN_IDS:
        if pid == "rte_inline" and re.search(r"\brte\b", lower):
            out.append(pid)
            continue
        keywords = _PATTERN_KEYWORDS.get(pid, ())
        if any(kw.lower() in lower for kw in keywords):
            out.append(pid)
    return out


def compose_pattern_hints(evidence_text: str) -> str:
    """
    Load matching pattern module files and return a single block for the user prompt.
    Returns empty string when nothing matches or files are missing.
    """
    matched = matched_pattern_ids(evidence_text)
    if not matched:
        return ""

    blocks: list[str] = []
    for pid in matched:
        path = PATTERN_MODULES_DIR / f"{pid}.txt"
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    blocks.append(text)
            except OSError:
                continue

    if not blocks:
        return ""

    return (
        "\n\nPATTERN-SPECIFIC HINTS (apply when relevant to USER INPUT):\n"
        + "\n\n---\n\n".join(blocks)
        + "\n"
    )
