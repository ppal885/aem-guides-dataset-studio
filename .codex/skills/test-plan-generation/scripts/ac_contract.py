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
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\([^)]*\)")
TILDE_MARKUP_RE = re.compile(
    r"~~|(?<!\w)~[^~\r\n]+~(?!\w)|(?<!\w)~(?!\w)"
)
EMPHASIS_MARKUP_RE = re.compile(
    r"\*\*|__|(?<!\w)\*[^*\r\n]+\*(?!\w)|(?<!\w)_[^_\r\n]+_(?!\w)"
)
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[._:/-][A-Za-z0-9]+)*")
LOGICAL_JOIN_RE = re.compile(
    r"(?i)\band/or\b|\bas well as\b|\b(?:and|or|while|whereas)\b"
)
DOUBLE_NEGATIVE_RE = re.compile(
    r"(?i)\b(?:not|never|no)\b[^|.;]{0,80}\b(?:unless|without|except)\b"
)
AND_OR_RE = re.compile(r"(?i)\band\s*/\s*or\b")
SECOND_ACTION_RE = re.compile(r"(?i)\band\s+then\b")
CROSS_AC_REFERENCE_RE = re.compile(r"(?<![A-Za-z0-9_-])AC-\d{2}(?![A-Za-z0-9_-])")
COMPLEX_PHRASE_REPLACEMENTS = {
    "in the event that": "if",
    "in order to": "to",
    "with respect to": "for",
    "subsequent to": "after",
    "prior to": "before",
    "on the condition that": "if",
    "including but not limited to": "an exact list",
    "aforementioned": "the named item",
    "thereafter": "then",
    "whereby": "a direct statement",
    "wherein": "a direct statement",
    "utilize": "use",
    "utilizes": "uses",
    "utilized": "used",
    "respectively": "separate ACs for each mapping",
}


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
    """Parse one full-record AC in the immutable ``aem-guides-ac-v1`` grammar.

    The human-facing ``Starting point / Action / Expected result`` block is
    presentation only. Accepting it here would let a durable plan and automation
    handoff lose status, sphere, canonical fields, and evidence while still
    appearing machine-readable.
    """
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


def validate_ac_paste_safety(criterion: AcceptanceCriterion) -> list[str]:
    """Reject inline markup that Jira/Confluence can reinterpret after paste."""
    text = " | ".join(
        criterion[field] for field in ("given", "when", "then", "evidence")
    )
    errors: list[str] = []
    if "`" in text:
        errors.append(
            "acceptance criterion must not use backticks/code spans; write the bare token"
        )
    if TILDE_MARKUP_RE.search(text):
        errors.append(
            "acceptance criterion must not use tilde markup because it can render as strikethrough"
        )
    if EMPHASIS_MARKUP_RE.search(text):
        errors.append(
            "acceptance criterion must not use bold/italic markers; use plain text"
        )
    if MARKDOWN_LINK_RE.search(text):
        errors.append(
            "acceptance criterion must not embed a Markdown link; use plain text or a bare URL"
        )
    return errors


def validate_ac_readability(criterion: AcceptanceCriterion) -> list[str]:
    """Keep Given/When/Then short enough to understand on the first read.

    Technical identifiers remain valid. The checks target sentence structure,
    not vocabulary scores, because AEM, DITA, API, paths, and configuration
    names are often necessary product terms.
    """
    errors: list[str] = []
    for field in ("given", "when", "then"):
        text = criterion[field]
        label = field.capitalize()

        if ";" in text:
            errors.append(
                f"{label} contains a semicolon; use a short sentence or split the ideas into separate ACs"
            )

        lowercase = text.lower()
        for phrase, replacement in COMPLEX_PHRASE_REPLACEMENTS.items():
            if phrase in lowercase:
                errors.append(
                    f"{label} uses the hard-to-read phrase '{phrase}'; use '{replacement}' instead"
                )

        if DOUBLE_NEGATIVE_RE.search(text):
            errors.append(
                f"{label} uses a double negative; state the expected rule directly"
            )

        if AND_OR_RE.search(text):
            errors.append(
                f"{label} uses 'and/or'; name the exact choice or split the AC"
            )

        if field == "when" and SECOND_ACTION_RE.search(text):
            errors.append(
                "When contains a second action after 'and then'; keep one trigger or action"
            )

        if CROSS_AC_REFERENCE_RE.search(text):
            errors.append(
                f"{label} refers to another AC; state the product outcome directly so this AC can be read and tested alone"
            )

    return errors
