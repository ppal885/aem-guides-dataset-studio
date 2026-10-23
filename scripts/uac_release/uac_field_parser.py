"""One place for the Acceptance Criteria grammar, for this automation and for downstream readers (Vision).

Two shapes of the same UAC exist:

* ``UAC.md`` as the skill writes it (markdown): ``- Acceptance Criteria NN: statement`` lines, each
  followed by indented case sub-points and ``**Source:**`` / ``**TBD:**`` lines. The ``*_MD`` patterns
  below are what ``uac_release_runner.py`` checks before posting.
* The Jira Acceptance Criteria field after ``jira_safe_text.jira_field_body`` (wiki markup):
  ``* *Acceptance Criteria NN:* statement`` bullets with ``** ...`` nested cases, Source and TBD, an
  optional italic ``_Note: ..._`` line on top, and whatever QE edited afterwards (``AC-NN:`` labels,
  strikethrough, added criteria). ``uac_learning_harvester.parse_criteria`` already reads that shape;
  :func:`parse_field` and :func:`ac_texts_only` expose it here so a consumer that only wants the
  criterion text never re-implements the grammar. ``docs/vision_uac_contract.md`` documents it.
"""
from __future__ import annotations

import re

# ``UAC.md`` (markdown source). A criterion block runs to the next criterion, a legacy "Suggested checks"
# heading, an "Out of scope" list, or the end of the file.
AC_LINE_MD = re.compile(r"^- Acceptance Criteria (\d+):\s*(.+)$", re.M)
AC_BLOCK_MD = re.compile(
    r"^- Acceptance Criteria (\d+):(.*?)(?=^- Acceptance Criteria \d+:|^Suggested checks\b|^Out of scope\b|\Z)",
    re.M | re.S)
# Criterion statements and their case sub-points, in file order: the lines whose wording QE reads.
AC_STATEMENT_OR_CASE_MD = re.compile(r"^- Acceptance Criteria \d+:\s*(.+)$|^\s+- (.+)$", re.M)
# The "Note:" line the skill writes above the first criterion when the fix is only proposed (unmerged PR)
# or the root cause is not confirmed. It is not a criterion.
NOTE_LINE_MD = re.compile(r"^Note:\s*(.+)$", re.M)


def ac_lines_md(uac_text: str) -> dict[int, str]:
    """``{number: statement}`` for every criterion line of a ``UAC.md``."""
    return {int(n): text for n, text in AC_LINE_MD.findall(uac_text or "")}


def ac_blocks_md(uac_text: str) -> dict[int, str]:
    """``{number: block body}`` (statement, cases, Source and TBD lines) for every criterion of a ``UAC.md``."""
    return {int(n): body for n, body in AC_BLOCK_MD.findall(uac_text or "")}


def ac_count_md(uac_text: str) -> int:
    return len(AC_LINE_MD.findall(uac_text or ""))


def statements_and_cases_md(uac_text: str) -> list[str]:
    """Criterion statements and case sub-points in file order, for vocabulary checks."""
    return [a or b for a, b in AC_STATEMENT_OR_CASE_MD.findall(uac_text or "")]


def parse_field(field_text: str) -> list[dict]:
    """Criteria of a Jira Acceptance Criteria field (wiki text, as Jira returns it).

    Each item has ``number``, ``text`` (the statement QE left standing), ``full`` (the statement as written),
    ``source``, ``tbd``, ``struck_parts`` and ``notes``. A criterion QE rejected with strikethrough has an
    empty ``text`` and its ``full`` statement in ``struck_parts``. Text before the first criterion (the
    proposed-fix Note line, a Scope line) and an Open Questions section are not criteria.
    """
    from uac_learning_harvester import parse_criteria  # the field grammar lives with the QE-edit harvester

    return parse_criteria(field_text or "")


def ac_texts_only(field_text: str, *, include_struck: bool = False) -> list[str]:
    """The text of each criterion in a Jira Acceptance Criteria field, in order, without Source and TBD lines.

    A criterion's text is its statement followed by its case sub-points (the nested bullets QE reads as part
    of the criterion). This is the view a downstream reader such as Vision needs. Criteria QE struck through
    are left out unless ``include_struck`` is true, in which case their original text is returned.
    """
    texts: list[str] = []
    for criterion in parse_field(field_text):
        text = criterion.get("text") or ""
        if not text and include_struck:
            text = criterion.get("full") or ""
        if text:
            texts.append(text)
    return texts


def has_open_decision(field_text: str) -> bool:
    """True when any criterion still carries a TBD: the decision is pending, the criterion is not final."""
    return any(c.get("tbd") for c in parse_field(field_text))
