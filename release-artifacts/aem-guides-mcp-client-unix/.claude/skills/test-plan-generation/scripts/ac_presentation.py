"""Deterministic plain-language presentation of canonical acceptance criteria.

The canonical record keeps Given, When, Then, status, sphere, and evidence for
validation and automation. This module only changes how that verified record is
shown to people. It copies clause text verbatim so technical names and product
meaning cannot drift during presentation.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

# A source that CLAIMS inspected implementation or documentation evidence must name
# the artifact a reviewer can open. "current implementation review of the title
# fallback" reads like evidence but is unverifiable prose, and it hides the case
# where the criterion was actually written from inference.
_EVIDENCE_CLAIM_MARKERS = (
    "current implementation",
    "implementation review",
    "review of the implementation",
    "code review",
    "review of the code",
    "inspected",
    "inspection of",
    "the codebase",
    "product documentation",
    "the documentation",
)

# Any one of these proves the source is locatable: a Jira key, a file with line
# numbers, a file:line citation, or a named documentation surface.
_LOCATABLE_PATTERNS = (
    re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b"),
    re.compile(r"\blines?\s+\d+", re.IGNORECASE),
    re.compile(r"\.\w+:\d+"),
    re.compile(r"experience league", re.IGNORECASE),
)

# Asserting that evidence does NOT exist is a legitimate, checkable source even
# though it names no artifact - that is the whole point of the assertion.
_ABSENCE_PATTERN = re.compile(
    r"\b(no|none|not)\b[^.]{0,80}\b(exist|exists|documented|found|available|defined)\b",
    re.IGNORECASE,
)
_QE_CHECK_LEAD_RE = re.compile(r"^(?:verify|confirm|check)\b", re.IGNORECASE)
_QE_STATUS_PREFIX_RE = re.compile(r"^(?:proposed|confirmed):\s*", re.IGNORECASE)
_QE_ARTICLE_PREFIX_RE = re.compile(r"^(?:A|An|The|No|Each)\b")
_QE_TBD_QUESTION_RE = re.compile(r"\?\s*(?:\(TBD\))?\.?\s*$", re.IGNORECASE)


def validate_ac_source_specificity(ac_id: str, source: str) -> None:
    """Reject a Source line that claims evidence without naming a locatable artifact.

    A source may rest on QE analysis, but it must not dress inference up as an
    inspected artifact. When it claims implementation or documentation evidence it
    must cite a Jira key, a file with line numbers, or a named documentation page -
    or explicitly assert that the evidence does not exist.
    """

    text = source.strip()
    lowered = text.lower()
    if not any(marker in lowered for marker in _EVIDENCE_CLAIM_MARKERS):
        return
    if any(pattern.search(text) for pattern in _LOCATABLE_PATTERNS):
        return
    if _ABSENCE_PATTERN.search(text):
        return
    raise ValueError(
        f"acceptance criterion {ac_id!r} cites evidence without a locatable source: "
        f"{text!r}; name the Jira key, the file and line numbers, or the "
        "documentation page, or state plainly that no such evidence exists"
    )


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


def _as_manual_qe_check(value: str) -> str:
    """Wrap a concrete outcome in the human-requested manual-QE voice."""

    text = _QE_STATUS_PREFIX_RE.sub("", value.strip())
    if (
        not text
        or _QE_CHECK_LEAD_RE.match(text)
        or _QE_TBD_QUESTION_RE.search(text)
    ):
        return text
    article = _QE_ARTICLE_PREFIX_RE.match(text)
    if article:
        text = article.group(0).lower() + text[article.end():]
    return f"Verify that {text}"


_AC_ID_RE = re.compile(r"^AC-(\d+)$", re.IGNORECASE)


def human_ac_label(ac_id: str) -> str:
    """Spell out the human-facing label for an internal ``AC-##`` id.

    The internal id stays ``AC-01`` for traceability (scenario mappings,
    ``ac_ref`` fields, manifests). The delivered label is spelled out because
    ``AC-01`` matches Jira's issue-key shape ``[A-Z]+-\\d+``: Jira auto-links it
    to a non-existent issue and renders it struck through. ``Acceptance
    Criteria 01`` carries no such shape. Any other id form is returned as-is.
    """

    match = _AC_ID_RE.match(str(ac_id).strip())
    if not match:
        return str(ac_id)
    return f"Acceptance Criteria {int(match.group(1)):02d}"


def project_ac_for_people(
    criterion: Mapping[str, str],
    *,
    include_status: bool,
    header_bullet: bool,
) -> str:
    """Render one strict AC as a single manual-QE verification sentence.

    Non-negotiable presentation rules: one line per AC (no Starting point / Action /
    Expected result scaffolding), no forced Given / When / Then labels, and never the
    [Proposed]/[Confirmed] status tag in human-facing text (include_status must be False
    for chat and Jira; the Needs_Human_Review label conveys status). The underlying
    clause stays unchanged after the concrete ``Verify that`` presentation wrapper.
    The visible label is spelled out as ``Acceptance Criteria ##`` while the
    internal id remains ``AC-##``.
    """

    ac_id = human_ac_label(criterion["id"])
    status = f" [{criterion['status']}]" if include_status else ""
    header_prefix = "- " if header_bullet else ""
    # Clause text is copied verbatim (not capitalized) so a leading lowercase technical
    # token such as largeFileTagCount cannot be corrupted during presentation.
    text = str(criterion.get("text") or "").strip()
    given = str(criterion.get("given") or "").strip()
    when = str(criterion.get("when") or "").strip()
    if given and when:
        # Legacy Given/When/Then record: project the three clauses into one sentence.
        sentence = f"{_mid(criterion['given'])}; when {_mid(criterion['when'])}, {_clause(criterion['then'])}"
    else:
        # Canonical plain criterion: show the verbatim body.
        sentence = _clause(text or criterion.get("then") or "")
    sentence = _as_manual_qe_check(sentence)
    return f"{header_prefix}{ac_id}{status}: {sentence}"


def project_ac_block_for_people(
    criterion: Mapping[str, str],
    *,
    include_status: bool = False,
    header_bullet: bool = True,
    for_jira: bool = False,
) -> str:
    """Render the delivered chat block for one AC: criterion, source, optional TBD.

    The delivered UAC is a FLAT list. This block is the only structure allowed
    around a criterion:

        - Acceptance Criteria 01: <verbatim criterion>.
          **Source:** <underlying source>.
          **TBD:** <undecided product decision>?

    No section headings, no ticket title line, no content sub-points, and no
    separate Open Questions section: an undecided decision rides on the AC it
    governs so the unknown stays attached to the contract it blocks. The
    criterion body itself stays paste-safe plain text; ``**Source:**`` and
    ``**TBD:**`` are chat-only labels and are emitted as plain ``Source:`` /
    ``TBD:`` when ``for_jira`` is True, because Jira renders markdown emphasis
    as literal characters.
    """

    lines = [
        project_ac_for_people(
            criterion,
            include_status=include_status,
            header_bullet=header_bullet,
        )
    ]
    source = str(criterion.get("source") or criterion.get("evidence") or "").strip()
    if not source:
        raise ValueError(
            f"acceptance criterion {criterion.get('id')!r} has no source; every "
            "delivered AC must show the authority it rests on"
        )
    validate_ac_source_specificity(str(criterion.get("id")), source)
    tbd = str(criterion.get("tbd") or "").strip()
    source_label = "Source:" if for_jira else "**Source:**"
    tbd_label = "TBD:" if for_jira else "**TBD:**"
    lines.append(f"  {source_label} {_clause(source)}")
    if tbd:
        question = tbd if tbd.endswith("?") else tbd.rstrip(".") + "?"
        lines.append(f"  {tbd_label} {question}")
    return "\n".join(lines)
