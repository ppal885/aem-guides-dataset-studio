"""Signal-activated root-cause / fix-driven authoring gate.

When current evidence supplies a root cause, implementation link, or positive
fixed/merged/verified claim, the plan must validate the described change and its
blast radius.  Merely citing the evidence is not enough.  Plans without a
positive fix signal remain backward-compatible and pass untouched.

Generic only.  Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable


PREFIX = "ROOT-CAUSE/FIX GATE:"
BLOCK_NAME = "root_cause_fix"
ALLOWED_LIFECYCLE_STAGES = {
    "implementation review",
    "post-fix validation",
    "post fix validation",
}

PLACEHOLDERS = {
    "",
    "n/a",
    "na",
    "none",
    "not available",
    "not provided",
    "unknown",
    "tbd",
    "to be decided",
}

ABSENCE_CLAIM_RE = re.compile(
    r"\b(?:no|without)\s+(?:linked\s+|development\s+|implementation\s+)?"
    r"(?:pr|pull\s+request|commit|branch|diff|root[-\s]?cause|rca)\b|"
    r"\b(?:pr|pull\s+request|commit|branch|diff|root[-\s]?cause|rca)\b"
    r".{0,45}\b(?:not\s+(?:available|present|provided|captured|inspected|linked|confirmed)|"
    r"unavailable|missing|none|not\s+applicable)\b|"
    r"\bnot\s+a\s+confirmed\s+diff\b",
    re.IGNORECASE,
)

NEGATED_FIX_STATUS_RE = re.compile(
    r"\b(?:no|not|never|without)\s+(?:an?\s+|yet\s+)?"
    r"(?:merged|cherry[-\s]?picked|hotfix(?:ed)?|fixed|verified)\b|"
    r"\b(?:merged|cherry[-\s]?picked|hotfix(?:ed)?|fixed|verified)\b"
    r".{0,30}\b(?:not\s+(?:available|present|confirmed)|unavailable|missing)\b|"
    r"\b(?:could|was|is|has)\s+not\s+"
    r"(?:be\s+)?(?:merged|cherry[-\s]?picked|hotfix(?:ed)?|fixed|verified)\b",
    re.IGNORECASE,
)

TEXT_SIGNAL_PATTERNS = (
    (
        "root-cause statement",
        re.compile(
            r"\b(?:root[-\s]?cause|rca)\s*(?::|=|-)\s*"
            r"(?!unknown\b|none\b|n/?a\b|not\s+(?:available|provided)\b)\S|"
            r"\b(?:root[-\s]?cause|rca)\s+(?:is|was|identified\s+as)\s+"
            r"(?!unknown\b|none\b|n/?a\b|not\s+(?:available|provided)\b)\S|"
            r"\bcaused\s+by\b",
            re.IGNORECASE,
        ),
    ),
    (
        "linked pull request",
        re.compile(
            r"https?://\S+/(?:pull|pulls|merge_requests?)/\d+\b|"
            r"\b(?:linked|implementation|fix|development)\s+"
            r"(?:pr|pull\s+request)\b|\b(?:pr|pull\s+request)\s*#\d+\b",
            re.IGNORECASE,
        ),
    ),
    (
        "linked commit",
        re.compile(
            r"https?://\S+/commit(?:s)?/[0-9a-f]{7,40}\b|"
            r"\bcommit(?:\s+(?:sha|id))?\s*(?::|=|#)?\s*[0-9a-f]{7,40}\b|"
            r"\b(?:linked|implementation|fix|development)\s+commit\b",
            re.IGNORECASE,
        ),
    ),
    (
        "linked branch",
        re.compile(
            r"\b(?:linked|implementation|fix|development)\s+branch\b|"
            r"\bbranch\s*(?::|=|is)\s*(?:refs/heads/)?"
            r"(?:fix|bugfix|hotfix|feature)[/_-][A-Za-z0-9._/-]+\b",
            re.IGNORECASE,
        ),
    ),
    (
        "supplied diff",
        re.compile(
            r"(?:^|\n)diff\s+--git\s+|(?:^|\n)@@\s+-\d|"
            r"\b(?:linked|attached|supplied|pasted|inspected|implementation|fix)\s+diff\b",
            re.IGNORECASE,
        ),
    ),
    (
        "positive fix-status claim",
        re.compile(
            # "merged" only counts in a fix/PR/branch/release context, never the bare
            # word: publishing and layout tickets legitimately say "merged page layout",
            # "merged with previous page", or "merged cells", which are not fix status.
            # Require a real VCS/merge-workflow term near "merged"; do NOT treat the
            # generic words fix/change/patch as merge context - they collide with plain
            # prose like "the fix must restore metadata on the merged page".
            r"\bmerged\b(?=[^.\n]{0,40}\b(?:pr|pull\s+request|mr|merge\s+request|"
            r"branch|develop|master|main|trunk|release|build|hotfix|commit|"
            r"changeset)\b)"
            r"|\b(?:pr|pull\s+request|mr|merge\s+request|branch|commit|changeset|"
            r"hotfix)\b[^.\n]{0,40}?\bmerged\b"
            r"|\bcherry[-\s]?picked\b"
            r"|\bhotfix(?:ed)?\b"
            r"|\bfix\s+(?:implemented|landed|available)\b"
            r"|\bfixed\s+in(?:\s+(?:build|version|release))?\b"
            r"|\bverified\s+in(?:\s+(?:build|version|release))?\b",
            re.IGNORECASE,
        ),
    ),
)

ROOT_CAUSE_KEYS = {"root_cause", "rootcause", "rca", "cause_statement"}
PR_KEYS = {"pull_request", "pull_requests", "pr_url", "pull_request_url", "pr_number"}
COMMIT_KEYS = {"commit", "commits", "commit_sha", "commit_id", "changeset"}
DIFF_KEYS = {"diff", "patch", "diff_hunks", "changed_hunks"}
BRANCH_KEYS = {"fix_branch", "implementation_branch", "development_branch", "linked_branch"}
DEVELOPMENT_LINK_KEYS = {"development_link", "development_links", "implementation_link"}

AC_ID_RE = re.compile(r"\bAC-\d{2,}\b", re.IGNORECASE)
OQ_ID_RE = re.compile(r"\bOQ-\d{2,}\b", re.IGNORECASE)
PRE_DEVELOPMENT_RE = re.compile(r"\bpre[-\s]?development\b", re.IGNORECASE)
NOT_PRE_DEVELOPMENT_RE = re.compile(
    r"\b(?:not|never|forbids?)\s+pre[-\s]?development\b", re.IGNORECASE
)
NARROW_VERIFICATION_RE = re.compile(
    r"\b(?:unit\s+tests?|single\s+(?:build|test|run)|one\s+(?:build|test|run)|"
    r"local\s+build|smoke\s+tests?|compile(?:d)?|"
    r"verified\s+in\s+(?:a\s+)?build)\b",
    re.IGNORECASE,
)
BROAD_VERIFICATION_RE = re.compile(
    r"\b(?:end[-\s]?to[-\s]?end|e2e|integration\s+tests?|system\s+tests?|"
    r"preset\s+matrix|engine\s+matrix|shared[-\s]?path|cross[-\s]?version|"
    r"full\s+regression|all\s+supported)\b",
    re.IGNORECASE,
)


def _problem(message: str) -> str:
    return f"{PREFIX} {message}"


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().casefold()).strip("_")


def _is_concrete_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = re.sub(r"\s+", " ", value.strip()).casefold().rstrip(".")
    return len(normalized) >= 3 and normalized not in PLACEHOLDERS


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"true", "yes", "1"}


def _manifest_scalars(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = _normalized_key(key)
            if not path and normalized == BLOCK_NAME:
                continue
            yield from _manifest_scalars(child, (*path, normalized))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _manifest_scalars(child, (*path, str(index)))
    elif isinstance(value, str):
        yield path, value


def _text_signals(text: str) -> list[str]:
    detected: list[str] = []
    for line in (text or "").splitlines() or [text or ""]:
        candidate = line.strip()
        if not candidate or ABSENCE_CLAIM_RE.search(candidate):
            continue
        for label, pattern in TEXT_SIGNAL_PATTERNS:
            if label == "positive fix-status claim" and NEGATED_FIX_STATUS_RE.search(candidate):
                continue
            if pattern.search(candidate):
                detected.append(label)
    return detected


def detect_signals(plan_body: str = "", manifest: dict[str, Any] | None = None) -> list[str]:
    """Return positive, generic signals that make the fix-driven gate applicable."""
    manifest_data = manifest if isinstance(manifest, dict) else {}
    detected: list[str] = []
    if BLOCK_NAME in manifest_data:
        detected.append(f"{BLOCK_NAME} block")

    for path, value in _manifest_scalars(manifest_data):
        if not _is_concrete_text(value) or ABSENCE_CLAIM_RE.search(value):
            continue
        path_keys = set(path)
        if path_keys & ROOT_CAUSE_KEYS:
            detected.append("root-cause field")
        elif path_keys & (PR_KEYS | DEVELOPMENT_LINK_KEYS):
            detected.append("implementation-link field")
        elif path_keys & COMMIT_KEYS:
            detected.append("commit field")
        elif path_keys & DIFF_KEYS:
            detected.append("diff field")
        elif path_keys & BRANCH_KEYS:
            detected.append("implementation-branch field")
        detected.extend(_text_signals(value))

    detected.extend(_text_signals(plan_body or ""))
    return list(dict.fromkeys(detected))


def _section(plan_body: str, name: str) -> str:
    match = re.search(
        rf"\*\*{re.escape(name)}\*\*(.*?)(?:\n\*\*|\Z)",
        plan_body or "",
        re.DOTALL | re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _plan_records(plan_body: str, section_name: str, prefix: str) -> dict[str, str]:
    section = _section(plan_body, section_name)
    pattern = AC_ID_RE if prefix == "AC" else OQ_ID_RE
    records: dict[str, str] = {}
    for line in section.splitlines():
        match = pattern.search(line)
        if match:
            records[match.group(0).upper()] = line.strip()
    return records


def _string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return None
    return [item.strip() for item in value if item.strip()]


def _preserve_refs(item: Any) -> list[str]:
    if isinstance(item, str):
        return [match.group(0).upper() for match in AC_ID_RE.finditer(item)]
    if isinstance(item, dict):
        values: list[str] = []
        mapped = item.get("mapped_ac")
        if isinstance(mapped, str):
            values.append(mapped)
        refs = item.get("ac_refs")
        if isinstance(refs, list):
            values.extend(ref for ref in refs if isinstance(ref, str))
        return [match.group(0).upper() for value in values for match in AC_ID_RE.finditer(value)]
    return []


def _main_feature_verdict(plan_body: str) -> str | None:
    automation = _section(plan_body, "Automation Coverage & Gaps")
    match = re.search(
        r"\bMain\s+feature\s+coverage\s*:\s*"
        r"(Covered|Partially\s+covered|Not\s+covered|Unverified)\b",
        automation,
        re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", match.group(1).strip()).casefold() if match else None


def _plan_declares_pre_development(plan_body: str) -> bool:
    for line in (plan_body or "").splitlines():
        if "lifecycle" not in line.casefold():
            continue
        if PRE_DEVELOPMENT_RE.search(line) and not NOT_PRE_DEVELOPMENT_RE.search(line):
            return True
    return False


def _narrow_verification(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    return bool(NARROW_VERIFICATION_RE.search(value)) and not bool(
        BROAD_VERIFICATION_RE.search(value)
    )


def is_present(plan_body: str = "", manifest: dict[str, Any] | None = None) -> bool:
    return bool(detect_signals(plan_body, manifest))


def validate(plan_body: str = "", manifest: dict[str, Any] | None = None) -> list[str]:
    manifest_data = manifest if isinstance(manifest, dict) else {}
    signals = detect_signals(plan_body, manifest_data)
    if not signals:
        return []

    block = manifest_data.get(BLOCK_NAME)
    if not isinstance(block, dict):
        return [_problem(
            f"positive fix evidence ({', '.join(signals)}) requires a {BLOCK_NAME} manifest block"
        )]

    problems: list[str] = []
    if not _is_concrete_text(block.get("fix_contract")):
        problems.append(_problem("root_cause_fix.fix_contract must state in one line what changed"))

    lifecycle = re.sub(
        r"\s+", " ", str(block.get("lifecycle_stage") or "").strip().casefold()
    )
    if PRE_DEVELOPMENT_RE.search(lifecycle):
        problems.append(_problem(
            "lifecycle_stage cannot be Pre-Development when a fix is described or linked"
        ))
    elif lifecycle not in ALLOWED_LIFECYCLE_STAGES:
        problems.append(_problem(
            "root_cause_fix.lifecycle_stage must be Implementation Review or Post-Fix Validation"
        ))
    if _plan_declares_pre_development(plan_body):
        problems.append(_problem(
            "the visible plan still declares a Pre-Development lifecycle despite positive fix evidence"
        ))

    ac_records = _plan_records(plan_body, "Acceptance Criteria", "AC")
    oq_records = _plan_records(plan_body, "Open Questions", "OQ")

    preserves = block.get("fix_preserves", [])
    if preserves is None:
        preserves = []
    if not isinstance(preserves, list):
        problems.append(_problem("root_cause_fix.fix_preserves must be a list"))
    else:
        for index, invariant in enumerate(preserves):
            refs = _preserve_refs(invariant)
            if not refs:
                problems.append(_problem(
                    f"fix_preserves[{index}] must name the real AC-## that guards the invariant"
                ))
                continue
            missing = [ref for ref in refs if ref not in ac_records]
            if missing:
                problems.append(_problem(
                    f"fix_preserves[{index}] references ACs not present in the plan: {', '.join(missing)}"
                ))

    # The requirement oracle is built from the ticket/attachment/UI, independent of the
    # diff: the fix is never the spec. Any place the fix is narrower than the requirement
    # is a recorded scope-delta mapped to an AC or an Open Question, never silently dropped.
    if not _is_concrete_text(block.get("requirement_oracle")):
        problems.append(_problem(
            "root_cause_fix.requirement_oracle must state, in requirement terms grounded in the "
            "ticket/attachment/UI, what the issue asks - the fix diff is not the specification"
        ))

    scope_delta = block.get("scope_delta")
    if scope_delta is None:
        scope_delta = []
    if not isinstance(scope_delta, list):
        problems.append(_problem("root_cause_fix.scope_delta must be a list"))
    elif not scope_delta:
        if not (
            _is_truthy(block.get("fix_fully_covers_requirement"))
            and _is_concrete_text(block.get("fix_fully_covers_reason"))
        ):
            problems.append(_problem(
                "an empty scope_delta requires fix_fully_covers_requirement true with a concrete "
                "fix_fully_covers_reason; otherwise record where the fix is narrower than the requirement"
            ))
    else:
        for index, item in enumerate(scope_delta):
            if not isinstance(item, dict):
                problems.append(_problem(f"scope_delta[{index}] must be an object"))
                continue
            if not _is_concrete_text(item.get("requirement")):
                problems.append(_problem(
                    f"scope_delta[{index}] must name the requirement the fix does not fully cover"
                ))
            mapped_ac = str(item.get("mapped_ac") or "").strip().upper()
            oq_ref = str(item.get("open_question_ref") or "").strip().upper()
            if not mapped_ac and not oq_ref:
                problems.append(_problem(
                    f"scope_delta[{index}] must map to an AC or an Open Question"
                ))
                continue
            if mapped_ac and mapped_ac not in ac_records:
                problems.append(_problem(
                    f"scope_delta[{index}] references {mapped_ac}, but that AC is not present"
                ))
            if oq_ref and oq_ref not in oq_records:
                problems.append(_problem(
                    f"scope_delta[{index}] references {oq_ref}, but that Open Question is not present"
                ))

    risks = block.get("fix_introduced_risks")
    if risks is None:
        risks = []
    if not isinstance(risks, list):
        problems.append(_problem("root_cause_fix.fix_introduced_risks must be a list"))
    elif not risks:
        if not _is_concrete_text(block.get("no_new_risk_reason")):
            problems.append(_problem(
                "an empty fix_introduced_risks list requires an explicit no_new_risk_reason"
            ))
    else:
        for index, risk in enumerate(risks):
            if not isinstance(risk, dict):
                problems.append(_problem(f"fix_introduced_risks[{index}] must be an object"))
                continue
            mapped_ac = str(risk.get("mapped_ac") or "").strip().upper()
            oq_ref = str(risk.get("open_question_ref") or "").strip().upper()
            if not mapped_ac and not oq_ref:
                problems.append(_problem(
                    f"fix_introduced_risks[{index}] must map to a negative AC or an Open Question"
                ))
                continue
            if mapped_ac:
                if mapped_ac not in ac_records:
                    problems.append(_problem(
                        f"fix_introduced_risks[{index}] references {mapped_ac}, but that AC is not present"
                    ))
                elif not re.search(r"\(Negative\)", ac_records[mapped_ac], re.IGNORECASE):
                    problems.append(_problem(
                        f"fix_introduced_risks[{index}] maps to {mapped_ac}, which must be a Negative AC"
                    ))
            if oq_ref and oq_ref not in oq_records:
                problems.append(_problem(
                    f"fix_introduced_risks[{index}] references {oq_ref}, but that Open Question is not present"
                ))

    added_tests = block.get("added_tests")
    if added_tests is None:
        added_tests = []
    if not isinstance(added_tests, list):
        problems.append(_problem("root_cause_fix.added_tests must be a list"))
    elif added_tests:
        verdict = _main_feature_verdict(plan_body)
        if verdict not in {"covered", "partially covered"}:
            problems.append(_problem(
                "added_tests is non-empty, so Automation Coverage must report the main feature "
                "as Covered or Partially covered"
            ))

    verification_gap = _string_list(block.get("verification_gap"))
    if verification_gap is None:
        problems.append(_problem("root_cause_fix.verification_gap must be a list of strings"))
        verification_gap = []
    if _narrow_verification(block.get("verification_performed")) and not verification_gap:
        problems.append(_problem(
            "narrow verification (for example one build or unit test) requires verification_gap "
            "to name the untested sign-off scope"
        ))

    return problems


def summarize(plan_body: str = "", manifest: dict[str, Any] | None = None) -> str:
    if not is_present(plan_body, manifest):
        return "RootCauseFixDriven: NOT_APPLICABLE (no positive fix signal)"
    signals = detect_signals(plan_body, manifest)
    problems = validate(plan_body, manifest)
    lines = [f"RootCauseFixDriven: {'CLEAN' if not problems else 'ISSUES'}"]
    lines.append(f"  signals: {', '.join(signals)}")
    lines.extend(f"  {problem}" for problem in problems)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan")
    parser.add_argument("--manifest")
    args = parser.parse_args()

    try:
        plan_body = Path(args.plan).read_text(encoding="utf-8") if args.plan else ""
        manifest = (
            json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            if args.manifest
            else {}
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(_problem(f"could not read inputs: {type(exc).__name__}"))
        return 1

    print(summarize(plan_body, manifest))
    return 0 if not validate(plan_body, manifest) else 1


if __name__ == "__main__":
    raise SystemExit(main())
