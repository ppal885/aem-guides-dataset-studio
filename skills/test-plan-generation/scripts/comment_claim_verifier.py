"""CommentClaimVerifier - force a Jira comment's own claim about CURRENT code/behaviour
to be reconciled against the actual diff/code, not accepted as fact.

WHY THIS EXISTS
---------------
An author's RCA comment ("there is no DB-mode gate here"), a reviewer's finding ("this
reads the wrong property"), or a "Fix Ready" note can be stale or simply wrong by the time
QA writes a plan - the comment describes what someone believed at the time they wrote it,
not what the current diff actually does. Treating such comments as ground truth produces
Acceptance Criteria for behaviour that was never real, or that the code already contradicts.

This module is deliberately generic - it does not know what any specific comment says. It
only enforces that IF the plan records a comment_claims entry, it carries a real
verification outcome (checked against cited code/diff evidence, or explicitly carried
forward as an Open Question) - never left as an unreconciled assertion. Stdlib only.
"""

import re

CLAIM_SOURCES = ("author_rca", "reviewer_finding", "reporter_note", "fix_ready_note", "other_comment")
VERIFICATION_STATUSES = ("VERIFIED_TRUE", "VERIFIED_FALSE", "STALE_SUPERSEDED", "UNVERIFIABLE")

# Soft heuristic only (mirrors implementation_grounding's signal style) - used to print an
# informational nudge, never a hard failure, since detecting "this comment makes a current-
# behaviour claim" reliably needs judgement the gate cannot fully automate.
CLAIM_PHRASES = (
    "there is no", "there's no", "currently does not", "currently doesn't", "does not exist",
    "no longer", "still does", "still returns", "wrong property", "wrong key", "incorrect property",
    "this reads", "this writes", "not fixed", "already fixed", "fix ready", "should be fixed",
    "the code does", "the code doesn't", "root cause is", "root caused by",
)

# Negation-plus-verb constructions ("neither class checks X()", "does not validate Y") that a
# plain substring list cannot catch because the negation and the verb are separated by the
# claim's own subject. Found missing this exact real-world phrasing on GUIDES-47692's PR-author
# comment ("neither class checks DatabaseConf.isDbEnabled()") during verification - added after
# that gap was caught by testing the heuristic against a real comment, not just synthetic cases.
CLAIM_PATTERNS = (
    re.compile(r"\bneither\b[^.?!]{0,60}\b(checks?|validates?|verifies?|gates?|handles?)\b", re.IGNORECASE),
    re.compile(r"\b(does not|doesn't|did not|didn't|never)\b[^.?!]{0,40}\b(check|validate|verify|gate|handle)s?\b", re.IGNORECASE),
    re.compile(r"\b(no|missing)\b[^.?!]{0,30}\b(check|validation|verification|gate)\b", re.IGNORECASE),
)


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("comment_claims"), list)


def likely_claims_in_comments(manifest):
    """Best-effort, non-blocking: comment text that looks like a current-behaviour claim."""
    issue = manifest.get("issue") if isinstance(manifest, dict) else None
    comments = []
    if isinstance(issue, dict):
        raw = issue.get("comments") or issue.get("comment") or []
        if isinstance(raw, list):
            comments = [str(c.get("body", c) if isinstance(c, dict) else c) for c in raw]
        elif isinstance(raw, str):
            comments = [raw]
    hits = []
    for text in comments:
        lower = text.lower()
        if any(p in lower for p in CLAIM_PHRASES) or any(p.search(text) for p in CLAIM_PATTERNS):
            hits.append(text[:160])
    return hits


def validate_comment_claims(value, *, open_question_ids=None):
    """Validate a manifest `comment_claims` list. Returns problem strings.

    Omitting the field entirely is allowed (backward-compatible) - only a present,
    malformed, or unreconciled entry is a failure.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        return ["comment_claims must be a list"]
    problems = []
    open_ids = set(open_question_ids or [])
    for i, item in enumerate(value):
        if not isinstance(item, dict):
            problems.append(f"comment_claims[{i}] must be an object")
            continue
        claim = str(item.get("claim", "")).strip()
        if not claim:
            problems.append(
                f"comment_claims[{i}] is missing 'claim' (the exact assertion the comment "
                f"makes about current code/behaviour)"
            )
        source = str(item.get("comment_source", "")).strip()
        if source not in CLAIM_SOURCES:
            problems.append(f"comment_claims[{i}].comment_source must be one of: {', '.join(CLAIM_SOURCES)}")
        status = str(item.get("verification_status", "")).strip()
        if status not in VERIFICATION_STATUSES:
            problems.append(f"comment_claims[{i}].verification_status must be one of: {', '.join(VERIFICATION_STATUSES)}")
            continue
        evidence = item.get("evidence_ids") or []
        has_evidence = isinstance(evidence, list) and any(str(e).strip() for e in evidence)
        if status in ("VERIFIED_TRUE", "VERIFIED_FALSE", "STALE_SUPERSEDED") and not has_evidence:
            problems.append(
                f"comment_claims[{i}] with verification_status={status} must cite evidence_ids "
                f"from the diff/code that was actually checked - not just re-assert the comment"
            )
        if status == "UNVERIFIABLE":
            ref = str(item.get("open_question_ref", "")).strip()
            if not ref:
                problems.append(
                    f"comment_claims[{i}] is UNVERIFIABLE but has no open_question_ref - carry it "
                    f"forward as an Open Question instead of silently dropping an unresolved claim"
                )
            elif open_ids and ref not in open_ids:
                problems.append(
                    f"comment_claims[{i}].open_question_ref '{ref}' is not in the plan's open_questions"
                )
    return problems


def summarize(manifest):
    lines = []
    hits = likely_claims_in_comments(manifest)
    declared = manifest.get("comment_claims") if isinstance(manifest, dict) else None
    if hits and not (isinstance(declared, list) and declared):
        lines.append(
            "CommentClaimVerifier: comment text with current-behaviour phrasing was found "
            "but no comment_claims entries are recorded - consider verifying and recording them:"
        )
        for h in hits[:5]:
            lines.append(f"  - {h!r}")
    problems = validate_comment_claims(declared, open_question_ids=None)
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)
