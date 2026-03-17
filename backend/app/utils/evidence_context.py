"""Evidence context helpers for routing - detect RTE/inline formatting vs media content."""


def evidence_has_inline_formatting_rte_signal(text: str) -> bool:
    """
    Evidence mentions cursor, arrow keys, RTE, inline tags (<i>, <b>, <u>) - editor/RTE behavior.
    Used to skip video/media overrides when evidence is primarily about RTE/cursor issues
    (e.g. "reviewing the customer's video" in an RTE bug report should not route to media_rich_content).
    """
    if not text:
        return False
    t = text.lower()
    return any(
        k in t
        for k in (
            "cursor",
            "arrow key",
            "arrow keys",
            "keyboard navigation",
            "rich text editor",
            "rte",
            "italic tag",
            "bold tag",
            "opening italic tag",
            "inline tag",
            "inline formatting",
            "nested tag",
            "editor behavior",
            "<i>",
            "<b>",
            "<u>",
            "<li>",
        )
    )
