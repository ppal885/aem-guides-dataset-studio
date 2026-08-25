"""Review canonical acceptance criteria for first-read tester clarity.

This complements the strict AC grammar. Ordinary clarity concerns are loud
``REVIEW`` notes so an existing plan is not silently invalidated; only grossly
long outcome text is a hard failure. Product-specific terms live in the data
file, not in this logic.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path


DATA_SCHEMA_VERSION = "aem-guides-ac-readability-signals-v1"
FIELD_REVIEW_WORDS = 28
OUTCOME_HARD_WORDS = 45
FIELD_REVIEW_SENTENCES = 2
CLAUSE_REVIEW_COUNT = 5
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[._:/-][A-Za-z0-9]+)*")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
CLAUSE_RE = re.compile(r"[,;:]|\b(?:and|or|but|while|whereas|which|that)\b", re.I)
CLASS_METHOD_RE = re.compile(r"\b[A-Z][A-Za-z0-9_$]*\.[a-z][A-Za-z0-9_$]*\b")
CALL_RE = re.compile(r"\b[a-z][A-Za-z0-9_$]*[A-Z][A-Za-z0-9_$]*\s*\(")
FILE_LINE_RE = re.compile(r"\b[^\s|]+\.(?:java|py|js|ts|tsx|jsx|xml|json|csv):\d+\b", re.I)
PATH_RE = re.compile(
    r"(?:\b[A-Za-z]:\\[^\s|]+|(?<![\w.])/(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+)"
)
_OVERLAP_STOP_WORDS = frozenset(
    {
        "a", "an", "and", "as", "at", "be", "by", "for", "from", "given",
        "in", "is", "it", "of", "on", "or", "the", "then", "to", "when",
        "with", "without", "user", "system", "asset", "action", "result",
    }
)
_REDUNDANCY_MIN_TOKENS = 6
_REDUNDANCY_CONTAINMENT = 0.88
_SUMMARY_MIN_OUTCOME_TOKENS = 5
_SUMMARY_UNION_CONTAINMENT = 0.75


def _load_peer(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        module_name, Path(__file__).with_name(filename)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ac_contract_mod = _load_peer("ac_contract_for_readability", "ac_contract.py")


def _signals() -> dict:
    path = Path(__file__).with_name("data") / "ac_readability.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != DATA_SCHEMA_VERSION:
        raise ValueError(f"ac readability data schema must be {DATA_SCHEMA_VERSION}")
    return data


def _sentences(text: str) -> int:
    return len([part for part in SENTENCE_RE.split(text.strip()) if part.strip()])


def _jargon_matches(text: str, terms: list[str]) -> list[str]:
    found: list[str] = []
    for term in terms:
        if re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", text, re.I):
            found.append(term)
    for label, pattern in (
        ("Class.method", CLASS_METHOD_RE),
        ("camelCaseCall()", CALL_RE),
        ("file:line", FILE_LINE_RE),
        ("file path", PATH_RE),
    ):
        if pattern.search(text):
            found.append(label)
    return found


def _content_tokens(criterion: dict[str, str]) -> set[str]:
    text = " ".join(criterion[field] for field in ("given", "when", "then"))
    return {
        match.group(0).casefold()
        for match in WORD_RE.finditer(text)
        if match.group(0).casefold() not in _OVERLAP_STOP_WORDS
    }


def _outcome_tokens(criterion: dict[str, str]) -> set[str]:
    return {
        match.group(0).casefold()
        for match in WORD_RE.finditer(criterion["then"])
        if match.group(0).casefold() not in _OVERLAP_STOP_WORDS
    }


def review_plan(
    plan_text: str, *, named_surfaces: list[str] | tuple[str, ...] = ()
) -> tuple[list[str], list[str]]:
    """Return ``(hard_failures, review_notes)`` for canonical AC lines."""
    data = _signals()
    failures: list[str] = []
    notes: list[str] = []
    parsed: list[dict[str, str]] = []
    for line in ac_contract_mod.acceptance_lines(plan_text):
        criterion = ac_contract_mod.parse_ac_line(line)
        if criterion is None:
            continue
        parsed.append(criterion)
        ac_id = criterion["id"]
        outcome = criterion["then"]
        if len(WORD_RE.findall(outcome)) > OUTCOME_HARD_WORDS:
            failures.append(
                f"{ac_id} outcome is grossly long; split it into separate acceptance criteria"
            )
        long_fields: list[str] = []
        for field in ("given", "when", "then"):
            field_text = criterion[field]
            if (
                len(WORD_RE.findall(field_text)) > FIELD_REVIEW_WORDS
                or _sentences(field_text) > FIELD_REVIEW_SENTENCES
                or len(CLAUSE_RE.findall(field_text)) > CLAUSE_REVIEW_COUNT
            ):
                long_fields.append(field.capitalize())
        if long_fields:
            notes.append(
                f"REVIEW ac-readability: {ac_id} too long in {', '.join(long_fields)}; "
                "split into short sentences"
            )

        tester_text = " | ".join(
            criterion[field] for field in ("given", "when", "then")
        )
        jargon = _jargon_matches(tester_text, list(data.get("jargon_terms") or []))
        if jargon:
            notes.append(
                f"REVIEW ac-readability: {ac_id} contains code/jargon ({', '.join(jargon)}); "
                "move it to a Note for developer"
            )
        lowered = tester_text.casefold()
        has_named_surface = any(
            str(surface).strip()
            and str(surface).casefold() in lowered
            for surface in named_surfaces
        )
        vague = [] if has_named_surface else [
            phrase
            for phrase in data.get("vague_surface_phrases") or []
            if str(phrase).casefold() in lowered
        ]
        if vague:
            notes.append(
                f"REVIEW ac-readability: {ac_id} uses a vague surface ({', '.join(vague)}); "
                "name the exact screen"
            )

    repeated_ids: set[str] = set()
    prior_outcome_union: set[str] = set()
    prior_outcomes: list[set[str]] = []
    for right_index, right in enumerate(parsed):
        right_tokens = _content_tokens(right)
        if len(right_tokens) < _REDUNDANCY_MIN_TOKENS:
            continue
        for left in parsed[:right_index]:
            left_tokens = _content_tokens(left)
            smaller = min(len(left_tokens), len(right_tokens))
            if smaller < _REDUNDANCY_MIN_TOKENS:
                continue
            containment = len(left_tokens & right_tokens) / smaller
            if containment >= _REDUNDANCY_CONTAINMENT:
                repeated_ids.add(right["id"])
                notes.append(
                    "REVIEW ac-readability: "
                    f"{right['id']} substantially repeats {left['id']}; keep one distinct "
                    "product outcome instead of a summary criterion"
                )
                break

        outcome_tokens = _outcome_tokens(right)
        if (
            right_index >= 2
            and right["id"] not in repeated_ids
            and len(outcome_tokens) >= _SUMMARY_MIN_OUTCOME_TOKENS
        ):
            covered = len(outcome_tokens & prior_outcome_union) / len(outcome_tokens)
            contributors = sum(bool(tokens & outcome_tokens) for tokens in prior_outcomes)
            strongest_single = max(
                (
                    len(tokens & outcome_tokens) / len(outcome_tokens)
                    for tokens in prior_outcomes
                ),
                default=0.0,
            )
            if (
                covered >= _SUMMARY_UNION_CONTAINMENT
                and strongest_single < _SUMMARY_UNION_CONTAINMENT
                and contributors >= 2
            ):
                notes.append(
                    "REVIEW ac-readability: "
                    f"{right['id']} summarizes outcomes already stated by earlier criteria; "
                    "remove the recap or state one new observable result"
                )
        prior_outcome_union.update(outcome_tokens)
        prior_outcomes.append(outcome_tokens)
    return failures, notes


def run_self_tests() -> None:
    header = "**Acceptance Criteria**\n"
    footer = "\n**Expected Behaviour**\n- Known."
    clear = (
        header
        + "- AC-01 [Proposed]: (Basic) Given a topic is open in Named Editor Screen | "
        "When the author selects an attribute | Then its friendly name is shown | "
        "Evidence: reviewer feedback."
        + footer
    )
    assert review_plan(clear) == ([], [])
    vague = clear.replace("Named Editor Screen", "the panel")
    assert any("name the exact screen" in note for note in review_plan(vague)[1])
    named_context = vague.replace(
        "When the author selects an attribute",
        "When the author selects an attribute in Named Editor Screen",
    )
    assert not any(
        "name the exact screen" in note
        for note in review_plan(
            named_context, named_surfaces=["Named Editor Screen"]
        )[1]
    )
    jargon = clear.replace("its friendly name is shown", "Widget.render uses p95 from /tmp/value.json")
    jargon_notes = review_plan(jargon)[1]
    assert any("Note for developer" in note for note in jargon_notes)
    gross = clear.replace(
        "its friendly name is shown",
        " ".join(f"result{index}" for index in range(46)),
    )
    assert review_plan(gross)[0]
    repeated = clear.replace(
        footer,
        "\n- AC-02 [Proposed]: (Basic) Given a topic is open in Named Editor Screen | "
        "When the author selects an attribute | Then its configured friendly name is shown | "
        "Evidence: reviewer feedback." + footer,
    )
    assert any(
        "summary criterion" in note for note in review_plan(repeated)[1]
    )
    long_setup = clear.replace(
        "a topic is open in Named Editor Screen",
        " ".join(f"setup{index}" for index in range(29)),
    )
    assert any("too long in Given" in note for note in review_plan(long_setup)[1])
    recap = (
        header
        + "- AC-01 [Proposed]: (Basic) Given one DITA file is selected | "
        "When the action menu opens | Then View source is hidden for a non-DITA file after menu refresh | "
        "Evidence: Jira description.\n"
        + "- AC-02 [Proposed]: (Basic) Given one DITA file is selected | "
        "When the action menu opens | Then Edit topics is hidden for a non-DITA file after selection changes | "
        "Evidence: Jira description.\n"
        + "- AC-03 [Proposed]: (Basic) Given one file is selected | "
        "When the action menu opens | Then View source and Edit topics are hidden for a non-DITA file | "
        "Evidence: Jira description."
        + footer
    )
    assert any("summarizes outcomes" in note for note in review_plan(recap)[1])


if __name__ == "__main__":
    run_self_tests()
    print("AC READABILITY SELF-TESTS PASSED")
