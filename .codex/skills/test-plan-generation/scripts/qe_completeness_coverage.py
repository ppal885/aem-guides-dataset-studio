"""Enforce complete QE-owned UAC coverage across ACs, questions, and regression.

The gate does not infer whether prose is acceptance scope.  Instead, an
activated plan must carry an explicit ``qe_completeness`` classification ledger.
This keeps checkable behavior from being parked in Open Questions or bare
regression bullets while preserving genuine product decisions for Human review.

Generic only.  Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


PREFIX = "QE COMPLETENESS GATE:"
REVIEW_PREFIX = "QE COMPLETENESS REVIEW:"
SCHEMA_VERSION = "aem-guides-qe-completeness-v1"

OPEN_QUESTION_CATEGORIES = {
    "GENUINE_PRODUCT_DECISION",
    "DEFERRED_COVERAGE",
}
REGRESSION_CATEGORIES = {
    "SAFETY_RETEST",
    "IN_SCOPE_BEHAVIOR",
}

AC_REF_RE = re.compile(r"^AC-\d{2,}$", re.IGNORECASE)
OQ_REF_RE = re.compile(r"^OQ-\d{2,}$", re.IGNORECASE)
AC_LINE_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?(AC-\d{2,})\b", re.IGNORECASE
)
OQ_LINE_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?(OQ-\d{2,})\s*(?:\*\*)?\s*(?::|[-—])",
    re.IGNORECASE,
)
BULLET_RE = re.compile(r"^\s*[-*]\s+(.+?)\s*$")
P3_REGRESSION_RE = re.compile(
    r"^\s*[-*]\s*P3\b.*\[\s*Regression\s*\]", re.IGNORECASE
)
NO_OPEN_QUESTIONS = "No open questions from current evidence"


def _problem(message: str) -> str:
    return f"{PREFIX} {message}"


def _review(message: str) -> str:
    return f"{REVIEW_PREFIX} {message}"


def _heading_title(line: str) -> str | None:
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.startswith("#"):
        title = stripped.lstrip("#").strip()
    elif len(stripped) >= 4 and stripped.startswith("**") and stripped.endswith("**"):
        title = stripped[2:-2].strip()
    else:
        return None
    return re.sub(r"\s+", " ", title).casefold()


def _bullet_text(line: str) -> str | None:
    match = BULLET_RE.match(line)
    return match.group(1).strip() if match else None


def _normalize_item(value: str) -> str:
    text = str(value or "").strip()
    bullet = BULLET_RE.match(text)
    if bullet:
        text = bullet.group(1)
    return re.sub(r"\s+", " ", text).strip()


def _plan_state(plan_body: str) -> dict[str, Any]:
    ac_ids: list[str] = []
    open_question_refs: list[str] = []
    unnumbered_open_questions: list[str] = []
    regression_by_line: dict[int, str] = {}
    current_section: str | None = None

    for line_number, line in enumerate((plan_body or "").splitlines(), 1):
        ac_match = AC_LINE_RE.match(line)
        if ac_match:
            ac_ids.append(ac_match.group(1).upper())

        if current_section == "open questions":
            normalized_line = _normalize_item(line)
            if normalized_line.casefold() == NO_OPEN_QUESTIONS.casefold():
                continue
            oq_match = OQ_LINE_RE.match(line)
            if oq_match:
                open_question_refs.append(oq_match.group(1).upper())
                continue

        heading = _heading_title(line)
        if heading is not None:
            current_section = heading
            continue

        bullet = _bullet_text(line)
        if current_section == "open questions":
            if bullet is None:
                if line.strip():
                    unnumbered_open_questions.append(line.strip())
                continue
            unnumbered_open_questions.append(_normalize_item(bullet))

        if current_section in {"regression areas", "p3 regression", "p3 regressions"}:
            if bullet:
                regression_by_line[line_number] = _normalize_item(bullet)

        if P3_REGRESSION_RE.match(line):
            regression_by_line[line_number] = _normalize_item(line)

    return {
        "ac_ids": ac_ids,
        "open_question_refs": open_question_refs,
        "unnumbered_open_questions": unnumbered_open_questions,
        "regression_items": list(regression_by_line.values()),
    }


def _block(manifest: dict[str, Any] | None) -> Any:
    return manifest.get("qe_completeness") if isinstance(manifest, dict) else None


def _manifest_open_question_ids(manifest: dict[str, Any] | None) -> set[str]:
    if not isinstance(manifest, dict):
        return set()
    records = manifest.get("open_questions")
    if not isinstance(records, list):
        return set()
    identifiers: set[str] = set()
    for record in records:
        if isinstance(record, dict):
            value = record.get("id") or record.get("oq_ref")
        else:
            value = record
        normalized = str(value or "").strip().upper()
        if OQ_REF_RE.fullmatch(normalized):
            identifiers.add(normalized)
    return identifiers


def _concrete_reason(value: Any) -> bool:
    reason = re.sub(r"\s+", " ", str(value or "").strip()).rstrip(".")
    return len(reason) >= 12 and reason.casefold() not in {
        "n/a",
        "na",
        "none",
        "unknown",
        "tbd",
        "not applicable",
        "to be decided",
    }


def is_present(plan_body: str = "", manifest: dict[str, Any] | None = None) -> bool:
    state = _plan_state(plan_body)
    activated = bool(
        state["open_question_refs"]
        or state["unnumbered_open_questions"]
        or state["regression_items"]
    )
    return activated or _block(manifest) is not None


def _validate_open_questions(
    plan_body: str,
    manifest: dict[str, Any],
    block: dict[str, Any],
) -> list[str]:
    state = _plan_state(plan_body)
    plan_refs = state["open_question_refs"]
    plan_ref_set = set(plan_refs)
    manifest_refs = _manifest_open_question_ids(manifest)
    ac_ids = set(state["ac_ids"])
    problems: list[str] = []

    if len(plan_refs) != len(plan_ref_set):
        duplicates = sorted(ref for ref, count in Counter(plan_refs).items() if count > 1)
        problems.append(_problem(
            "the plan contains duplicate Open Question references: " + ", ".join(duplicates)
        ))
    for item in state["unnumbered_open_questions"]:
        problems.append(_problem(
            f"Open Questions contains an unnumbered real item that cannot be classified exactly once: {item}"
        ))

    records = block.get("open_question_classification")
    if not isinstance(records, list):
        return problems + [_problem(
            "qe_completeness.open_question_classification must be a list"
        )]

    classified_refs: list[str] = []
    for index, record in enumerate(records):
        location = f"qe_completeness.open_question_classification[{index}]"
        if not isinstance(record, dict):
            problems.append(_problem(f"{location} must be an object"))
            continue

        oq_ref = str(record.get("oq_ref") or "").strip().upper()
        if not OQ_REF_RE.fullmatch(oq_ref):
            problems.append(_problem(f"{location}.oq_ref must be an OQ-## reference"))
            continue
        classified_refs.append(oq_ref)

        if oq_ref not in plan_ref_set:
            problems.append(_problem(
                f"{oq_ref} is classified but is not present in the plan Open Questions section"
            ))
        if oq_ref not in manifest_refs:
            problems.append(_problem(
                f"{oq_ref} must also exist in manifest.open_questions"
            ))

        category = str(record.get("category") or "").strip().upper()
        if category not in OPEN_QUESTION_CATEGORIES:
            problems.append(_problem(
                f"{oq_ref}.category must be one of {', '.join(sorted(OPEN_QUESTION_CATEGORIES))}"
            ))
            continue
        if not _concrete_reason(record.get("reason")):
            problems.append(_problem(
                f"{oq_ref} must include a concrete classification reason"
            ))

        expected_flag = record.get("can_be_ac_with_expected")
        if not isinstance(expected_flag, bool):
            problems.append(_problem(
                f"{oq_ref}.can_be_ac_with_expected must be true or false"
            ))

        promoted_ref = str(record.get("promoted_ac_ref") or "").strip().upper()
        if promoted_ref:
            if not AC_REF_RE.fullmatch(promoted_ref):
                problems.append(_problem(
                    f"{oq_ref}.promoted_ac_ref must be an AC-## reference"
                ))
            elif promoted_ref not in ac_ids:
                problems.append(_problem(
                    f"{oq_ref}.promoted_ac_ref names {promoted_ref}, but that AC is not present in the plan"
                ))

        if category == "DEFERRED_COVERAGE":
            problems.append(_problem(
                f"{oq_ref} is DEFERRED_COVERAGE; promote the checkable behavior to a real AC "
                "and remove or rewrite the Open Question"
            ))
            if not promoted_ref:
                problems.append(_problem(
                    f"{oq_ref} DEFERRED_COVERAGE requires promoted_ac_ref after promotion"
                ))

    counts = Counter(classified_refs)
    for oq_ref in sorted(plan_ref_set):
        if counts[oq_ref] == 0:
            problems.append(_problem(
                f"{oq_ref} is present in the plan but missing from open_question_classification"
            ))
        elif counts[oq_ref] > 1:
            problems.append(_problem(
                f"{oq_ref} must be classified exactly once, not {counts[oq_ref]} times"
            ))

    return problems


def _validate_regression(
    plan_body: str,
    block: dict[str, Any],
) -> list[str]:
    state = _plan_state(plan_body)
    plan_items = state["regression_items"]
    plan_counts = Counter(plan_items)
    ac_ids = set(state["ac_ids"])
    problems: list[str] = []

    duplicate_plan_items = sorted(item for item, count in plan_counts.items() if count > 1)
    for item in duplicate_plan_items:
        problems.append(_problem(
            f"the same regression item appears more than once and cannot be classified exactly: {item}"
        ))

    records = block.get("regression_classification")
    if not isinstance(records, list):
        return problems + [_problem(
            "qe_completeness.regression_classification must be a list"
        )]

    classified_items: list[str] = []
    for index, record in enumerate(records):
        location = f"qe_completeness.regression_classification[{index}]"
        if not isinstance(record, dict):
            problems.append(_problem(f"{location} must be an object"))
            continue
        item = _normalize_item(str(record.get("item") or ""))
        if not item:
            problems.append(_problem(f"{location}.item must contain the exact regression bullet text"))
            continue
        classified_items.append(item)
        if item not in plan_counts:
            problems.append(_problem(
                f"regression classification does not exactly match a plan item: {item}"
            ))

        category = str(record.get("category") or "").strip().upper()
        if category not in REGRESSION_CATEGORIES:
            problems.append(_problem(
                f"regression item category must be one of {', '.join(sorted(REGRESSION_CATEGORIES))}: {item}"
            ))
            continue

        ac_ref = str(record.get("ac_ref") or "").strip().upper()
        if category == "IN_SCOPE_BEHAVIOR" and not ac_ref:
            problems.append(_problem(
                f"IN_SCOPE_BEHAVIOR requires ac_ref to a real AC in the plan: {item}"
            ))
        if ac_ref:
            if not AC_REF_RE.fullmatch(ac_ref):
                problems.append(_problem(f"regression item ac_ref must be an AC-## reference: {item}"))
            elif ac_ref not in ac_ids:
                problems.append(_problem(
                    f"regression item references {ac_ref}, but that AC is not present in the plan: {item}"
                ))

    classification_counts = Counter(classified_items)
    for item in plan_items:
        if classification_counts[item] == 0:
            problems.append(_problem(
                f"regression item is missing from regression_classification: {item}"
            ))
        elif classification_counts[item] > 1:
            problems.append(_problem(
                f"regression item must be classified exactly once, not "
                f"{classification_counts[item]} times: {item}"
            ))

    return problems


def validate(
    plan_body: str = "",
    manifest: dict[str, Any] | None = None,
) -> list[str]:
    manifest_data = manifest if isinstance(manifest, dict) else {}
    state = _plan_state(plan_body)
    activated = bool(
        state["open_question_refs"]
        or state["unnumbered_open_questions"]
        or state["regression_items"]
    )
    block = _block(manifest_data)

    if not activated and block is None:
        return []
    if block is None:
        return [_problem(
            "the plan contains real Open Questions or regression items, but the "
            "qe_completeness block is missing"
        )]
    if not isinstance(block, dict):
        return [_problem("qe_completeness must be an object")]

    problems: list[str] = []
    if block.get("schema_version") != SCHEMA_VERSION:
        problems.append(_problem(
            f"qe_completeness.schema_version must be {SCHEMA_VERSION!r}"
        ))
    problems.extend(_validate_open_questions(plan_body, manifest_data, block))
    problems.extend(_validate_regression(plan_body, block))
    return problems


def review(
    plan_body: str = "",
    manifest: dict[str, Any] | None = None,
) -> list[str]:
    block = _block(manifest)
    if not isinstance(block, dict):
        return []
    records = block.get("open_question_classification")
    if not isinstance(records, list):
        return []

    reviews: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        oq_ref = str(record.get("oq_ref") or "").strip().upper()
        category = str(record.get("category") or "").strip().upper()
        promoted_ref = str(record.get("promoted_ac_ref") or "").strip().upper()
        if (
            OQ_REF_RE.fullmatch(oq_ref)
            and category == "GENUINE_PRODUCT_DECISION"
            and record.get("can_be_ac_with_expected") is True
            and not promoted_ref
        ):
            reviews.append(_review(
                f"{oq_ref} can be written as an AC with the QE-expected contract and "
                "flagged for dev down-scope; prefer an AC over an Open Question."
            ))
    return reviews


def summarize(
    plan_body: str = "",
    manifest: dict[str, Any] | None = None,
) -> str:
    if not is_present(plan_body, manifest):
        return "QeCompletenessCoverage: NOT_APPLICABLE (no Open Question or regression item)"
    problems = validate(plan_body, manifest)
    reviews = review(plan_body, manifest)
    status = "ISSUES" if problems else "REVIEW" if reviews else "CLEAN"
    lines = [f"QeCompletenessCoverage: {status}"]
    lines.extend(f"  {problem}" for problem in problems)
    lines.extend(f"  {note}" for note in reviews)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="QE-owned UAC completeness coverage gate")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    try:
        plan_body = Path(args.plan).read_text(encoding="utf-8")
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(_problem(f"input could not be read: {type(exc).__name__}"))
        return 1
    if not isinstance(manifest, dict):
        print(_problem("manifest root must be an object"))
        return 1

    print(summarize(plan_body, manifest))
    return 0 if not validate(plan_body, manifest) else 1


if __name__ == "__main__":
    raise SystemExit(main())
