"""
Utilities for same-file xref, conref and conrefend in DITA.
Generates href/conref values in project-consistent format.
"""
from typing import Optional


def self_xref_href(
    target_id: str,
    topic_id: Optional[str] = None,
    current_filename: str = "",
    use_filename: bool = False,
) -> str:
    """
    Generate same-file xref href.
    Returns #target_id or #topicId/elementId or samefile.dita#topicId/elementId.
    Convention: use fragment-only when use_filename=False (project default).
    """
    if topic_id and topic_id != target_id:
        frag = f"{topic_id}/{target_id}"
    else:
        frag = target_id
    if use_filename and current_filename:
        return f"{current_filename}#{frag}"
    return f"#{frag}"


def self_conref_value(
    topic_id: str,
    target_id: str,
    current_filename: str,
    use_filename: bool = False,
) -> str:
    """
    Generate same-file conref value.
    Format: "#topicId/elementId" or "samefile.dita#topicId/elementId".
    For single element: "#elementId" or "samefile.dita#elementId" when topic_id == target_id.
    """
    if topic_id == target_id:
        frag = target_id
    else:
        frag = f"{topic_id}/{target_id}"
    if use_filename and current_filename:
        return f"{current_filename}#{frag}"
    return f"#{frag}"


def self_conrefend_value(
    topic_id: str,
    end_target_id: str,
    current_filename: str,
    use_filename: bool = False,
) -> str:
    """Generate same-file conrefend value. Same format as conref."""
    return self_conref_value(topic_id, end_target_id, current_filename, use_filename)
