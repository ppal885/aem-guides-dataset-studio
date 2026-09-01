"""Deterministic plain-language presentation of canonical acceptance criteria.

The canonical record keeps Given, When, Then, status, sphere, and evidence for
validation and automation. This module only changes how that verified record is
shown to people. It copies clause text verbatim so technical names and product
meaning cannot drift during presentation.
"""

from __future__ import annotations

from collections.abc import Mapping


def _clause(value: str) -> str:
    """Return one unchanged clause with terminal punctuation."""

    cleaned = value.strip()
    if not cleaned:
        raise ValueError("acceptance-criterion presentation clause is empty")
    return cleaned if cleaned.endswith((".", "!", "?")) else cleaned + "."


def _mid(value: str) -> str:
    """Return a verbatim clause safe to use mid-sentence (no trailing period)."""

    cleaned = value.strip()
    if not cleaned:
        raise ValueError("acceptance-criterion presentation clause is empty")
    return cleaned.rstrip(".")


def project_ac_for_people(
    criterion: Mapping[str, str],
    *,
    include_status: bool,
    header_bullet: bool,
) -> str:
    """Render one strict AC as a single plain-language sentence, verbatim clauses.

    Non-negotiable presentation rules: one line per AC (no Starting point / Action /
    Expected result scaffolding), no forced Given / When / Then labels, and never the
    [Proposed]/[Confirmed] status tag in human-facing text (include_status must be False
    for chat and Jira; the Needs_Human_Review label conveys status). Clause text is
    copied verbatim so technical names and product meaning cannot drift.
    """

    ac_id = criterion["id"]
    status = f" [{criterion['status']}]" if include_status else ""
    header_prefix = "- " if header_bullet else ""
    # Clause text is copied verbatim (not capitalized) so a leading lowercase technical
    # token such as largeFileTagCount cannot be corrupted during presentation.
    sentence = f"{_mid(criterion['given'])}; when {_mid(criterion['when'])}, {_clause(criterion['then'])}"
    return f"{header_prefix}{ac_id}{status}: {sentence}"
