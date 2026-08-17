"""Canonical machine-readable Acceptance Criteria contract.

Every test-plan producer and automation-draft consumer must use this module's
single-line grammar. Keeping the parser deterministic prevents downstream
agents from guessing which prose is setup, action, assertion, or provenance.
"""

from __future__ import annotations

import re
from typing import TypedDict


AC_SCHEMA_VERSION = "aem-guides-ac-v1"
AC_STATUSES = ("Confirmed", "Proposed")
AC_SPHERES = ("Basic", "Negative", "Integration", "Performance")
AC_EXACT_FORMAT = (
    "- AC-## [Confirmed|Proposed]: "
    "(Basic|Negative|Integration|Performance) "
    "Given <precondition/input> | When <single trigger/action> | "
    "Then <observable outcome> | Evidence: <underlying source>."
)

_FIELD = r"\S(?:[^|\r\n]*\S)?"
AC_LINE_RE = re.compile(
    rf"^- (?P<id>AC-\d{{2}}) \[(?P<status>{'|'.join(AC_STATUSES)})\]: "
    rf"\((?P<sphere>{'|'.join(AC_SPHERES)})\) "
    rf"Given (?P<given>{_FIELD}) \| "
    rf"When (?P<when>{_FIELD}) \| "
    rf"Then (?P<then>{_FIELD}) \| "
    rf"Evidence: (?P<evidence>{_FIELD})\.$"
)
HEADING_RE = re.compile(r"^\*\*(.+?)\*\*$")
RESERVED_FIELD_RE = re.compile(r"(?:^|\s)(?:Given|When|Then|Evidence:)\s")


class AcceptanceCriterion(TypedDict):
    id: str
    status: str
    sphere: str
    given: str
    when: str
    then: str
    evidence: str
    raw: str
    schema_version: str


def parse_ac_line(line: str) -> AcceptanceCriterion | None:
    """Parse one AC only when it exactly matches the canonical grammar."""
    match = AC_LINE_RE.fullmatch(line)
    if not match:
        return None
    fields = match.groupdict()
    if any(RESERVED_FIELD_RE.search(fields[name]) for name in ("given", "when", "then")):
        return None
    return {
        "id": fields["id"],
        "status": fields["status"],
        "sphere": fields["sphere"],
        "given": fields["given"],
        "when": fields["when"],
        "then": fields["then"],
        "evidence": fields["evidence"],
        "raw": line[2:],
        "schema_version": AC_SCHEMA_VERSION,
    }


def acceptance_lines(text: str) -> list[str]:
    """Return non-empty lines from the full plan's Acceptance Criteria section."""
    lines: list[str] = []
    in_section = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        heading = HEADING_RE.fullmatch(line.strip())
        if heading:
            in_section = heading.group(1) == "Acceptance Criteria"
            continue
        if in_section and line.strip():
            lines.append(line)
    return lines


def validate_ac_sequence(criteria: list[AcceptanceCriterion]) -> list[str]:
    """Require stable, unique, contiguous IDs beginning at AC-01."""
    if not criteria:
        return ["Acceptance Criteria must contain at least one canonical AC line"]
    actual = [criterion["id"] for criterion in criteria]
    expected = [f"AC-{index:02d}" for index in range(1, len(criteria) + 1)]
    errors: list[str] = []
    if len(actual) != len(set(actual)):
        errors.append("Acceptance Criteria IDs must be unique")
    if actual != expected:
        errors.append(
            "Acceptance Criteria IDs must be contiguous and ordered from AC-01; "
            f"expected {', '.join(expected)}, found {', '.join(actual)}"
        )
    return errors
