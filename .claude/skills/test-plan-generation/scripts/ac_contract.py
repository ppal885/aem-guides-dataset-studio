"""Canonical machine-readable Acceptance Criteria contract.

Every test-plan producer and automation-draft consumer must use this module's
single-line grammar. Keeping the parser deterministic prevents downstream
agents from guessing which prose is setup, action, assertion, or provenance.
"""

from __future__ import annotations

import re
from typing import TypedDict


AC_SCHEMA_VERSION = "aem-guides-ac-v2"
AC_SCHEMA_VERSION_LEGACY = "aem-guides-ac-v1"
AC_STATUSES = ("Confirmed", "Proposed")
AC_SPHERES = ("Basic", "Negative", "Integration", "Performance")

# Canonical produced grammar (v2): one plain-English acceptance criterion, no
# Given/When/Then scaffolding and no pipes. Long criteria are broken into indented
# sub-points; the whole presented set is capped at AC_PRESENTATION_CAP.
AC_EXACT_FORMAT = (
    "- AC-## [Confirmed|Proposed]: "
    "(Basic|Negative|Integration|Performance) "
    "<plain-English acceptance criterion>. Evidence: <underlying source>."
)

# Cap on how many AC-## points a presented UAC may carry. More than this must be
# consolidated/merged (senior-QA style) and the granular detail pushed into
# sub-points or the linked full-record markdown.
AC_PRESENTATION_CAP = 10

_FIELD = r"\S(?:[^|\r\n]*\S)?"
# v2 plain criterion body: no pipes, must not open with the Given keyword.
_PLAIN_BODY = r"(?!Given )[^|\r\n]+?"
PLAIN_AC_LINE_RE = re.compile(
    rf"^- (?P<id>AC-\d{{2}}) \[(?P<status>{'|'.join(AC_STATUSES)})\]: "
    rf"\((?P<sphere>{'|'.join(AC_SPHERES)})\) "
    rf"(?P<text>{_PLAIN_BODY})\.?\s+Evidence: (?P<evidence>[^|\r\n]+?)\.$"
)
# Legacy Given/When/Then grammar (v1). Still parsed so saved plans and the
# historical test corpus keep working; it is no longer produced or documented.
LEGACY_AC_LINE_RE = re.compile(
    rf"^- (?P<id>AC-\d{{2}}) \[(?P<status>{'|'.join(AC_STATUSES)})\]: "
    rf"\((?P<sphere>{'|'.join(AC_SPHERES)})\) "
    rf"Given (?P<given>{_FIELD}) \| "
    rf"When (?P<when>{_FIELD}) \| "
    rf"Then (?P<then>{_FIELD}) \| "
    rf"Evidence: (?P<evidence>{_FIELD})\.$"
)
# Back-compat alias: older callers imported AC_LINE_RE for the GWT grammar.
AC_LINE_RE = LEGACY_AC_LINE_RE
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
    text: str
    evidence: str
    raw: str
    schema_version: str


def parse_ac_line(line: str) -> AcceptanceCriterion | None:
    """Parse one full-record AC.

    The canonical produced grammar is the plain v2 form (``AC-## [status]:
    (Sphere) <plain criterion>. Evidence: ...``) with no Given/When/Then
    scaffolding. The legacy v1 Given/When/Then grammar is still accepted so
    saved plans and the historical corpus keep parsing, but it is no longer
    produced or documented.

    ``text`` always holds the plain criterion body. For legacy v1 lines the
    individual ``given``/``when``/``then`` fields are also populated and
    ``text`` is their readable join, so downstream consumers that read ``then``
    keep working unchanged.

    The human-facing ``Starting point / Action / Expected result`` block is
    presentation only and is never accepted here.
    """
    plain = PLAIN_AC_LINE_RE.fullmatch(line)
    if plain:
        fields = plain.groupdict()
        text = fields["text"].strip()
        if RESERVED_FIELD_RE.search(text):
            # A plain criterion must not smuggle the reserved Given/When/Then/
            # Evidence field keywords into its body.
            return None
        return {
            "id": fields["id"],
            "status": fields["status"],
            "sphere": fields["sphere"],
            "given": "",
            "when": "",
            "then": text,
            "text": text,
            "evidence": fields["evidence"].strip(),
            "raw": line[2:],
            "schema_version": AC_SCHEMA_VERSION,
        }

    match = LEGACY_AC_LINE_RE.fullmatch(line)
    if not match:
        return None
    fields = match.groupdict()
    if any(RESERVED_FIELD_RE.search(fields[name]) for name in ("given", "when", "then")):
        return None
    combined = f"{fields['given']}; {fields['when'].strip()}, {fields['then'].strip()}"
    return {
        "id": fields["id"],
        "status": fields["status"],
        "sphere": fields["sphere"],
        "given": fields["given"],
        "when": fields["when"],
        "then": fields["then"],
        "text": combined,
        "evidence": fields["evidence"],
        "raw": line[2:],
        "schema_version": AC_SCHEMA_VERSION_LEGACY,
    }


def acceptance_lines(text: str) -> list[str]:
    """Return top-level (non-indented) lines from the Acceptance Criteria section.

    Indented sub-point bullets (``  - ...``) elaborate the AC head above them and
    are not standalone AC lines, so they are excluded here. Use
    ``acceptance_sub_points`` to read them.
    """
    lines: list[str] = []
    in_section = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        heading = HEADING_RE.fullmatch(line.strip())
        if heading:
            in_section = heading.group(1) == "Acceptance Criteria"
            continue
        if in_section and line.strip() and not line.startswith((" ", "\t")):
            lines.append(line)
    return lines


AC_HEAD_RE = re.compile(r"^- (AC-\d{2})\b")
SUB_POINT_RE = re.compile(r"^\s+-\s+(.+?)\s*$")


def acceptance_sub_points(text: str) -> dict[str, list[str]]:
    """Return ``{ac_id: [sub_point_text, ...]}`` for indented AC sub-points.

    A sub-point is an indented ``- ...`` bullet that follows an AC head line and
    breaks a long criterion into short, scannable clauses.
    """
    out: dict[str, list[str]] = {}
    in_section = False
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        heading = HEADING_RE.fullmatch(line.strip())
        if heading:
            in_section = heading.group(1) == "Acceptance Criteria"
            current = None
            continue
        if not in_section or not line.strip():
            continue
        head = AC_HEAD_RE.match(line)
        if head and not line.startswith((" ", "\t")):
            current = head.group(1)
            out.setdefault(current, [])
            continue
        sub = SUB_POINT_RE.match(line)
        if sub and current:
            out[current].append(sub.group(1).strip())
    return {ac_id: points for ac_id, points in out.items() if points}


def validate_ac_count(plan_text: str) -> list[str]:
    """Hard-cap the number of presented AC-## points at AC_PRESENTATION_CAP.

    A senior human QA keeps a UAC to a handful of consolidated points and pushes
    granular detail into sub-points or a linked full record. More than the cap
    means the set must be merged, not split.
    """
    ac_ids = [
        head.group(1)
        for line in acceptance_lines(plan_text)
        for head in [AC_HEAD_RE.match(line)]
        if head
    ]
    if len(ac_ids) > AC_PRESENTATION_CAP:
        return [
            f"Acceptance Criteria has {len(ac_ids)} AC points; the presented UAC must be "
            f"consolidated to at most {AC_PRESENTATION_CAP}. Merge related criteria into a "
            "single AC, break each merged AC into short sub-points, and keep any remaining "
            "granular detail in the linked full-record markdown - do not drop accepted meaning."
        ]
    return []


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
