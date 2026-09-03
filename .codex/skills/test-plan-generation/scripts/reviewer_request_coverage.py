"""Signal-activated reviewer-request coverage gate (UACFIX-18).

When a human reviewer explicitly asks to check a surface or behaviour (a Jira
comment such as "also check Map Preview / Download PDF / sorting / temp files"),
or a shared-consumer surface is placed in scope, that item is an ACCEPTANCE
CRITERION with its own scenario - never demoted to a P3 Regression bullet or a
generic Open Question. This gate makes that non-negotiable enforceable.

Activation is deliberately conservative: it fires only when the manifest carries
a ``reviewer_requests`` block OR an explicit ``reviewer_comments`` list that
contains an imperative check. It never scans the plan's own Test Scenarios for
verbs like "verify", so plans without reviewer feedback pass untouched.

Generic only.  Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PREFIX = "REVIEWER-REQUEST GATE:"
BLOCK_NAME = "reviewer_requests"
COMMENTS_KEY = "reviewer_comments"

AC_ID_RE = re.compile(r"AC-\d{2,}")
OQ_ID_RE = re.compile(r"OQ-\d{2,}")

VALID_DISPOSITIONS = {
    "COVERED_BY_AC",
    "OPEN_QUESTION_UNRESOLVED_PATH",
    "OUT_OF_SCOPE",
}

# Imperative "please also check X" style reviewer asks. Kept tight to avoid
# firing on ordinary prose.
IMPERATIVE_RE = re.compile(
    r"\b(?:also\s+(?:check|cover|verify|test|validate|consider|handle)"
    r"|please\s+(?:check|verify|cover|ensure|confirm)"
    r"|should\s+(?:also\s+)?(?:check|cover|verify|be\s+checked|be\s+covered)"
    r"|areas?\s+(?:i|we)\s+think\s+we\s+should\s+(?:also\s+)?check"
    r"|impact\s+(?:on|to)\b"
    r"|make\s+sure"
    r"|don't\s+forget"
    r"|what\s+about)\b",
    re.IGNORECASE,
)

_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "check", "also", "please", "verify", "cover", "should", "we", "i", "impact",
    "make", "sure", "test", "that", "this", "it", "its", "be", "with", "via",
}


def _problem(message: str) -> str:
    return f"{PREFIX} {message}"


def _concrete(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _section(plan_body: str, name: str) -> str:
    match = re.search(
        rf"\*\*{re.escape(name)}\*\*(.*?)(?:\n\*\*|\Z)",
        plan_body or "",
        re.DOTALL | re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _plan_ids(plan_body: str, section_name: str, pattern: re.Pattern[str]) -> set[str]:
    section = _section(plan_body, section_name)
    return {m.group(0).upper() for m in pattern.finditer(section)}


def _comment_texts(manifest: dict[str, Any]) -> list[str]:
    raw = manifest.get(COMMENTS_KEY)
    texts: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                texts.append(item.strip())
            elif isinstance(item, dict):
                body = item.get("body") or item.get("text") or ""
                if isinstance(body, str) and body.strip():
                    texts.append(body.strip())
    return texts


def _imperative_comments(manifest: dict[str, Any]) -> list[str]:
    return [c for c in _comment_texts(manifest) if IMPERATIVE_RE.search(c)]


def _tokens(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9]+", (text or "").lower())
        if t not in _STOPWORDS and len(t) > 2
    }


def detect_signals(plan_body: str = "", manifest: dict[str, Any] | None = None) -> list[str]:
    manifest_data = manifest if isinstance(manifest, dict) else {}
    detected: list[str] = []
    if isinstance(manifest_data.get(BLOCK_NAME), list) and manifest_data[BLOCK_NAME]:
        detected.append(f"{BLOCK_NAME} block")
    if _imperative_comments(manifest_data):
        detected.append("reviewer imperative comment")
    return detected


def is_present(plan_body: str = "", manifest: dict[str, Any] | None = None) -> bool:
    return bool(detect_signals(plan_body, manifest))


def validate(plan_body: str = "", manifest: dict[str, Any] | None = None) -> list[str]:
    manifest_data = manifest if isinstance(manifest, dict) else {}
    signals = detect_signals(plan_body, manifest_data)
    if not signals:
        return []

    block = manifest_data.get(BLOCK_NAME)
    if not isinstance(block, list) or not block:
        return [_problem(
            "reviewer request signal detected but no reviewer_requests block is present; "
            "every reviewer-named check must be captured as an entry mapped to an AC, "
            "an Open Question (only when the code path is unresolved), or an explicit "
            "out-of-scope reason"
        )]

    problems: list[str] = []
    plan_acs = _plan_ids(plan_body, "Acceptance Criteria", AC_ID_RE)
    plan_oqs = _plan_ids(plan_body, "Open Questions", OQ_ID_RE)
    manifest_oqs = {
        _concrete(oq.get("id")).upper()
        for oq in (manifest_data.get("open_questions") or [])
        if isinstance(oq, dict) and _concrete(oq.get("id"))
    }
    known_oqs = plan_oqs | manifest_oqs

    entry_texts: list[str] = []
    for index, entry in enumerate(block):
        label = f"reviewer_requests[{index}]"
        if not isinstance(entry, dict):
            problems.append(_problem(f"{label} must be an object"))
            continue
        rid = _concrete(entry.get("request_id")) or label
        raw_text = _concrete(entry.get("raw_text"))
        entry_texts.append(raw_text)
        surface = _concrete(entry.get("surface_or_behavior"))
        disposition = _concrete(entry.get("disposition")).upper()

        if not raw_text:
            problems.append(_problem(f"{rid} must quote the reviewer's raw_text"))
        if not surface:
            problems.append(_problem(f"{rid} must name the surface_or_behavior requested"))
        if disposition not in VALID_DISPOSITIONS:
            problems.append(_problem(
                f"{rid} disposition must be one of "
                f"{sorted(VALID_DISPOSITIONS)} (a reviewer ask can never be left as a "
                f"regression bullet); got {entry.get('disposition')!r}"
            ))
            continue

        if disposition == "COVERED_BY_AC":
            refs = [
                m.group(0).upper()
                for ref in (entry.get("ac_refs") or [])
                if isinstance(ref, str)
                for m in AC_ID_RE.finditer(ref)
            ]
            if not refs:
                problems.append(_problem(
                    f"{rid} is COVERED_BY_AC but has no ac_refs; a reviewer-named check "
                    f"must become its own AC"
                ))
            missing = [r for r in refs if r not in plan_acs]
            if missing:
                problems.append(_problem(
                    f"{rid} ac_refs {missing} are not present in the plan Acceptance Criteria"
                ))
        elif disposition == "OPEN_QUESTION_UNRESOLVED_PATH":
            oq_ref = _concrete(entry.get("open_question_ref")).upper()
            if not oq_ref:
                problems.append(_problem(
                    f"{rid} is OPEN_QUESTION_UNRESOLVED_PATH but names no open_question_ref"
                ))
            elif oq_ref not in known_oqs:
                problems.append(_problem(
                    f"{rid} open_question_ref {oq_ref} is not a known Open Question"
                ))
        else:  # OUT_OF_SCOPE
            if not _concrete(entry.get("reason")):
                problems.append(_problem(
                    f"{rid} is OUT_OF_SCOPE but gives no reason"
                ))

    # Rule 4: every imperative reviewer comment must be captured by some entry.
    entry_token_sets = [_tokens(t) for t in entry_texts if t]
    for comment in _imperative_comments(manifest_data):
        c_tokens = _tokens(comment)
        if not c_tokens:
            continue
        captured = any(
            len(c_tokens & e_tokens) >= 2 or (e_tokens and e_tokens <= c_tokens)
            for e_tokens in entry_token_sets
        )
        if not captured:
            snippet = comment if len(comment) <= 80 else comment[:77] + "..."
            problems.append(_problem(
                f"reviewer imperative not captured by any reviewer_requests entry: {snippet!r}"
            ))

    return problems


def require_reviewer_comments_declared(manifest: dict[str, Any] | None = None) -> list[str]:
    """Stop this gate from being dormant.

    The coverage gate above only activates once a reviewer comment is present in the
    manifest - but nothing forced the author to put the fetched Jira comments there,
    so a real reviewer ask (e.g. "also check Map Preview / Download PDF / temp files")
    silently fell through. This makes the input mandatory and affirmative: every
    manifest must declare ``reviewer_comments`` (the fetched Jira reviewer/review
    comments). An empty list is allowed only with ``reviewer_comments_checked: true``
    to affirm the comments were inspected and none carry an imperative check request.
    """
    manifest_data = manifest if isinstance(manifest, dict) else {}
    if BLOCK_NAME in manifest_data or isinstance(manifest_data.get("reviewer_requests"), list) and manifest_data.get("reviewer_requests"):
        # A declared reviewer_requests block already proves the comments were mined.
        pass
    if COMMENTS_KEY not in manifest_data:
        return [_problem(
            "reviewer_comments must be declared: copy the fetched Jira reviewer/review "
            "comments here so a reviewer-requested check cannot be silently missed; use "
            "an empty list with reviewer_comments_checked: true when the issue has no "
            "reviewer comment carrying an imperative check request"
        )]
    value = manifest_data.get(COMMENTS_KEY)
    if not isinstance(value, list):
        return [_problem("reviewer_comments must be a list of comment strings")]
    if not value:
        checked = manifest_data.get("reviewer_comments_checked")
        truthy = checked is True or (isinstance(checked, str) and checked.strip().casefold() in {"true", "yes", "1"})
        if not truthy:
            return [_problem(
                "reviewer_comments is empty; set reviewer_comments_checked: true to affirm "
                "you inspected the Jira comments and none contain a reviewer check request"
            )]
    return []


def summarize(plan_body: str = "", manifest: dict[str, Any] | None = None) -> str:
    manifest_data = manifest if isinstance(manifest, dict) else {}
    if not detect_signals(plan_body, manifest_data):
        return "reviewer-request coverage: not activated"
    block = manifest_data.get(BLOCK_NAME)
    count = len(block) if isinstance(block, list) else 0
    return f"reviewer-request coverage: {count} reviewer request(s) dispositioned"


def main() -> int:
    parser = argparse.ArgumentParser(description="Reviewer-request coverage gate (UACFIX-18)")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    plan_body = args.plan.read_text(encoding="utf-8") if args.plan.exists() else ""
    manifest_data = (
        json.loads(args.manifest.read_text(encoding="utf-8"))
        if args.manifest.exists()
        else {}
    )
    problems = validate(plan_body, manifest_data)
    if problems:
        for problem in problems:
            print(problem)
        return 1
    print(summarize(plan_body, manifest_data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
