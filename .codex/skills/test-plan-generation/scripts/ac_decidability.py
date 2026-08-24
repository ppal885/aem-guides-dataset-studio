"""Acceptance-criterion decidability checks shared by every plan consumer.

The structural parser proves that fields exist. This module proves that a full-record
AC is a decided and finite pass/fail contract rather than an open product decision,
an unmeasurable promise, a menu of implementation choices, or an ambiguous terminal
state. All findings are hard failures because unresolved decisions belong in the
Open Questions section and must never reach Jira or automation handoff as sign-off ACs.
"""

from __future__ import annotations

import re

from ac_contract import acceptance_lines, parse_ac_line


UNDECIDED_MARKERS = (
    "to be agreed",
    "to be decided",
    "to be determined",
    "to be finalized",
    "to be finalised",
    "tbd",
    "pending decision",
    "pending scope",
    "pending approval",
    "not yet decided",
    "yet to be decided",
    "once agreed",
    "once decided",
    "if approved",
    "if this is in scope",
    "if in scope",
    "subject to approval",
)

# These qualifiers need a numeric or explicitly source-backed comparative boundary.
IMMEASURABLE_TERMS = (
    "bounded",
    "reasonable time",
    "acceptable time",
    "acceptable duration",
    "quickly",
    "a small number",
    "not too many",
    "minimal logging",
    "minimal log",
)

ALTERNATIVE_RE = re.compile(
    r"\b(?:via|through|using|uses?|implemented (?:with|by)|by means of)\b"
    r"[^.|]{0,160}?\b(?:or|versus)\b",
    re.IGNORECASE,
)
AMBIG_TERMINAL_RE = re.compile(
    r"\b(?:failed or aborted|aborted or failed|failed or cancelled|cancelled or failed|"
    r"non-?success(?:ful)?|success or failure|failed\s*/\s*cancelled)\b",
    re.IGNORECASE,
)
NON_FINITE_RE = re.compile(
    r"\b(?:does not|must not|will not)\s+(?:continue|run|loop|grow|increase)\s+"
    r"(?:forever|indefinitely)\b|\bdoes not always\b|\bwithout (?:unbounded|indefinite)\b",
    re.IGNORECASE,
)
BOUND_VALUE = r"(?:\d+(?:\.\d+)?|zero|one|two|three|four|five|six|seven|eight|nine|ten|once|twice)"
EXPLICIT_BOUND_RE = re.compile(
    rf"\b(?:no more than|no fewer than|at most|at least|within)\s+{BOUND_VALUE}\b|"
    rf"\bbounded\s+(?:to|at|by)\s+{BOUND_VALUE}\b|"
    r"\b(?:configured|approved|documented)\s+(?:limit|threshold|baseline)\b|"
    r"\bcompared with\s+(?:the\s+)?(?:before-fix|approved|documented)\s+baseline\b",
    re.IGNORECASE,
)


def evaluate_plan(plan_text: str) -> tuple[list[str], list[str]]:
    """Return hard failures and advisory notes (currently no soft advisories)."""
    failures: list[str] = []
    for line in acceptance_lines(plan_text):
        criterion = parse_ac_line(line)
        if criterion is None:
            # Structural consumers report the canonical-grammar failure. Never try to
            # recover prose here because doing so would recreate the compact-parser hole.
            continue
        criterion_id = criterion["id"]
        contract_text = " ".join(
            (criterion["given"], criterion["when"], criterion["then"])
        )
        lowered_contract = contract_text.casefold()
        then = criterion["then"]
        lowered_then = then.casefold()

        marker = next((item for item in UNDECIDED_MARKERS if item in lowered_contract), None)
        if marker:
            failures.append(
                f"{criterion_id} contains unresolved decision marker {marker!r}; move the "
                "decision and its QA impact to Open Questions"
            )
            continue

        vague = next((item for item in IMMEASURABLE_TERMS if item in lowered_then), None)
        if vague and not EXPLICIT_BOUND_RE.search(then):
            failures.append(
                f"{criterion_id} uses non-measurable outcome {vague!r} without a numeric, "
                "configured, or source-backed comparative boundary"
            )

        if ALTERNATIVE_RE.search(then):
            failures.append(
                f"{criterion_id} lists alternative mechanisms in its outcome; keep the "
                "observable product result in the AC and disposition the mechanism separately"
            )

        if AMBIG_TERMINAL_RE.search(then):
            failures.append(
                f"{criterion_id} uses an ambiguous terminal result; define success, failure, "
                "cancellation, and retry-exhaustion outcomes independently when applicable"
            )

        if NON_FINITE_RE.search(then):
            failures.append(
                f"{criterion_id} uses a non-finite negative outcome instead of a bounded "
                "observable oracle with an explicit attempt, count, duration, or terminal state"
            )

    return failures, []


def summarize(plan_text: str = "") -> str:
    failures, _ = evaluate_plan(plan_text)
    lines = [f"AcceptanceCriterionDecidability: {'ISSUES' if failures else 'CLEAN'}"]
    lines.extend(f"  FAIL {failure}" for failure in failures)
    return "\n".join(lines)
