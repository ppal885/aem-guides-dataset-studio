"""Classify how a related Jira ticket matches the base (feature, error, workflow, regression)."""

from __future__ import annotations

import re
from typing import Any


def _tok(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{4,}", (s or "").lower()) if len(t) >= 4}


def classify_related_match(
    *,
    base_blob: str,
    related_doc: str,
    related_title: str,
    related_meta: dict[str, Any],
) -> tuple[str, str]:
    """Return (match_type, one_line_reason)."""
    bb = f"{base_blob} {related_title}".lower()
    rd = f"{related_doc} {related_title}".lower()
    combined = f"{bb}\n{rd}"

    if any(x in combined for x in ("regression", " broke ", "broken after", "used to work")):
        return "regression", "Overlap on regression / breakage language vs base ticket themes."
    err_sig = ("error", "exception", "stack", "500", "failed", "nullpointer", "timeout")
    if sum(1 for x in err_sig if x in combined) >= 2:
        return "error", "Shared error/failure vocabulary between excerpts."

    if any(x in combined for x in ("steps", "repro", "workflow", "user flow", "click")):
        tok_overlap = _tok(base_blob) & _tok(related_doc)
        if len(tok_overlap) >= 4:
            return "workflow", f"Workflow/repro vocabulary plus term overlap ({', '.join(sorted(tok_overlap)[:4])})."

    comp = str(related_meta.get("components") or "").lower()
    if comp and comp in bb:
        return "feature", "Related components align with base ticket context."

    tok_overlap = _tok(base_blob) & _tok(related_doc)
    if len(tok_overlap) >= 6:
        return "feature", f"Strong topical overlap: {', '.join(sorted(tok_overlap)[:6])}."

    tok_overlap2 = _tok(base_blob) & _tok(related_title)
    if len(tok_overlap2) >= 3:
        return "feature", f"Title tokens overlap with base context: {', '.join(sorted(tok_overlap2)[:5])}."

    return "feature", "Vector similarity / metadata boost; validate in Jira before treating as same root cause."
