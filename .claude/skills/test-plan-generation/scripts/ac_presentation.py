"""Deterministic plain-language presentation of canonical acceptance criteria.

The canonical record keeps Given, When, Then, status, sphere, and evidence for
validation and automation. This module only changes how that verified record is
shown to people. It copies clause text verbatim so technical names and product
meaning cannot drift during presentation.
"""

from __future__ import annotations

from collections.abc import Mapping


PRESENTATION_FIELDS = (
    ("given", "Starting point"),
    ("when", "Action"),
    ("then", "Expected result"),
)


def _clause(value: str) -> str:
    """Return one unchanged clause with terminal punctuation."""

    cleaned = value.strip()
    if not cleaned:
        raise ValueError("acceptance-criterion presentation clause is empty")
    return cleaned if cleaned.endswith((".", "!", "?")) else cleaned + "."


def project_ac_for_people(
    criterion: Mapping[str, str],
    *,
    include_status: bool,
    header_bullet: bool,
) -> str:
    """Render one strict AC as three short, labelled, verbatim clauses."""

    ac_id = criterion["id"]
    status = f" [{criterion['status']}]" if include_status else ""
    header_prefix = "- " if header_bullet else ""
    detail_prefix = "  - " if header_bullet else "- "
    lines = [f"{header_prefix}{ac_id}{status}"]
    lines.extend(
        f"{detail_prefix}{label}: {_clause(criterion[field])}"
        for field, label in PRESENTATION_FIELDS
    )
    return "\n".join(lines)
