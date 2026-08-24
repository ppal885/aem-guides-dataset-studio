"""AcceptanceCriterionDecidability - catch ACs that are not yet decided, measurable,
single-outcome contracts.

WHY THIS EXISTS
---------------
The coverage/grounding gates answer "is every dimension represented and cited?" They
do NOT answer "is each AC actually acceptance-testable?" A grounded, mapped AC can
still be un-shippable because it:
  - uses a non-measurable qualifier ("bounded logs", "reasonable time") with no number;
  - defers its own decision ("a limit to be agreed", "TBD") - a design decision, not a
    contract;
  - offers a menu of alternative mechanisms ("via an index, keyset paging, or a custom
    index") - the solution is undecided;
  - asserts an ambiguous async terminal state ("failed or aborted") instead of the
    distinct states (succeeded / failed / cancelled / retry-exhausted).

This gate flags those generically (no domain/construct rules). The clearest class -
an AC that explicitly defers its own decision - is a hard failure; the softer,
higher-false-positive classes are loud REVIEW notes. Stdlib only.
"""

import re

# An AC that defers its own decision is not a contract -> hard failure.
UNDECIDED_MARKERS = (
    "to be agreed", "to be decided", "to be determined", "to be finalized", "to be finalised",
    "tbd", "pending decision", "not yet decided", "yet to be decided", "once agreed", "once decided",
)
# Non-measurable qualifiers: acceptable only when a concrete number/threshold is present too.
IMMEASURABLE_TERMS = (
    "bounded", "reasonable", "appropriate", "sufficiently", "as needed", "minimal",
    "acceptable", "efficiently", "quickly", "a small number", "not too many", "large",
)
# A menu of alternative mechanisms inside one AC (the solution is undecided): a
# "via/through/using/by ... or ..." construction.
ALTERNATIVE_RE = re.compile(r"\b(?:via|through|using)\b[^.|]{0,80}?\bor\b", re.IGNORECASE)
# Ambiguous async terminal state phrasing.
AMBIG_TERMINAL_RE = re.compile(
    r"\b(failed or aborted|aborted or failed|non-?success(?:ful)?|success or failure)\b", re.IGNORECASE)
_DIGIT_RE = re.compile(r"\d")

_HEADING_RE = re.compile(r"^\*\*(.+?)\*\*\s*$")
_AC_LINE_RE = re.compile(r"^- AC-\d{2,}\b")
_PREFIX_RE = re.compile(r"^-\s*AC-\d{2,}(?:\s*\[[^\]]*\])?:\s*")


def _acceptance_lines(plan_text):
    out, capture = [], False
    for line in (plan_text or "").splitlines():
        m = _HEADING_RE.match(line.strip())
        if m:
            capture = (m.group(1).strip() == "Acceptance Criteria")
            continue
        if capture and _AC_LINE_RE.match(line.strip()):
            out.append(line.strip())
    return out


def _ac_id(line):
    parts = line.split()
    return parts[1].rstrip(":") if len(parts) > 1 else "AC"


def _outcome(line):
    """The Then/outcome portion of an AC. Strips the "- AC-01:" / "- AC-01 [Confirmed]:"
    prefix first so the id number is never read as a threshold, then takes the text after
    'Then' (tagged G|W|T form) and drops any '| Evidence:' citation."""
    seg = _PREFIX_RE.sub("", line.strip())
    seg = seg.split("Then", 1)[1] if "Then" in seg else seg
    seg = seg.split("| Evidence:", 1)[0]
    return seg


def evaluate_plan(plan_text):
    """Return (failures, notes). Failures are hard (undecided-decision ACs); notes are
    loud REVIEW advisories for the softer, higher-false-positive classes."""
    failures, notes = [], []
    for line in _acceptance_lines(plan_text):
        acid = _ac_id(line)
        low = line.lower()
        outcome = _outcome(line)
        olow = outcome.lower()

        if any(m in low for m in UNDECIDED_MARKERS):
            failures.append(
                f"{acid} defers its own decision (a 'to be agreed / TBD'-class marker) - an AC must be a decided, "
                f"testable contract; move the undecided choice to Open Questions and keep only the observable outcome"
            )
            continue

        hits = [t for t in IMMEASURABLE_TERMS if t in olow]
        if hits and not _DIGIT_RE.search(outcome):
            notes.append(
                f"REVIEW ac-decidability {acid}: the outcome uses a non-measurable qualifier ({hits[0]!r}) with no "
                f"concrete threshold - give a measurable oracle (a number/limit/observable value) or defer to Open Questions"
            )
        if ALTERNATIVE_RE.search(outcome):
            notes.append(
                f"REVIEW ac-decidability {acid}: the outcome lists alternative mechanisms (\"via X ... or ...\") - "
                f"that is an undecided design choice; state the observable outcome and defer the mechanism to Open Questions"
            )
        if AMBIG_TERMINAL_RE.search(outcome):
            notes.append(
                f"REVIEW ac-decidability {acid}: ambiguous terminal state (e.g. \"failed or aborted\") - for an "
                f"async/job outcome, specify the distinct terminal states (succeeded / failed / cancelled / "
                f"retry-exhausted), each with its own oracle"
            )
    return failures, notes


def summarize(plan_text=""):
    failures, notes = evaluate_plan(plan_text)
    lines = [f"AcceptanceCriterionDecidability: {'ISSUES' if failures or notes else 'CLEAN'}"]
    for f in failures:
        lines.append(f"  FAIL {f}")
    for n in notes:
        lines.append(f"  {n}")
    return "\n".join(lines)
