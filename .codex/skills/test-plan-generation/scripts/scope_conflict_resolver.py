"""ScopeConflictResolver + ProblemThread - stop the reasoner from merging distinct
scopes (reported problem, customer expectation, Jira description, engineering
investigation, current PR/fix, secondary defects, unresolved behaviour) into one
acceptance contract, and force a Jira-scope-vs-fix-scope reconciliation.

The optional ``implementation_scope_authority`` block also prevents behavior
found only in a PR, commit, or diff from silently becoming approved product
scope. Such an AC stays Proposed and points to an Open Question unless a named
product authority explicitly approves it.

WHY THIS EXISTS
---------------
A Jira often carries several behavioural problems and several scope authorities. If the
PR only fixes one capability while the Jira describes three, silently treating the Jira
as fully solved is wrong. This module keeps each problem as its own ProblemThread with
its own status, and requires that a material Jira-scope vs fix-scope mismatch be surfaced
as an Open Question rather than merged away.

Generic - no ticket-specific content. Stdlib only.
"""

import re

THREAD_STATUS = ("CONFIRMED", "PROPOSED", "CURRENT_FIX", "SECONDARY_DEFECT", "UNRESOLVED", "OUT_OF_SCOPE")
ALIGNMENT = ("FULL_SCOPE_FIX", "PARTIAL_SCOPE_FIX", "DIFFERENT_SCOPE_FIX", "SECONDARY_FIX", "UNKNOWN_FIX_SCOPE")
# Alignments that mean the fix does NOT clearly cover the reported scope -> must be exposed.
NON_FULL_ALIGNMENT = frozenset({"PARTIAL_SCOPE_FIX", "DIFFERENT_SCOPE_FIX", "UNKNOWN_FIX_SCOPE"})
# A thread with one of these statuses must never be promoted to a product AC.
NON_AC_STATUS = frozenset({"SECONDARY_DEFECT", "UNRESOLVED", "OUT_OF_SCOPE"})

FIX_PRESENT_SIGNALS = ("pr ", "pull request", "fix ready", "fix is", "patch", "the fix", "commit ", "branch ", "starling#")
# Pre-development markers: a plan that only discusses the eventual fix (with no
# inspected PR, branch, or diff) must not trip implementation-scope reconciliation.
PRE_DEVELOPMENT_SIGNALS = (
    "development has not started", "pre-development", "no pull request",
    "not applicable - development", "not applicable — development",
)
MULTI_PROBLEM_SIGNALS = ("also ", "second issue", "another problem", "in addition", "separately", "two problems",
                         "multiple issues", "as well as", "additionally", "font", "preview", "and the")

IMPLEMENTATION_SCOPE_SCHEMA = "aem-guides-implementation-scope-authority-v1"
IMPLEMENTATION_DECISIONS = ("OPEN_QUESTION", "PRODUCT_APPROVED")
_CANONICAL_AC_RE = re.compile(
    r"(?m)^- (?P<id>AC-\d{2}) \[(?P<status>Confirmed|Proposed)\]: "
    r"\((?:Basic|Negative|Integration|Performance)\) .+? \| Evidence: "
    r"(?P<evidence>.+)\.$"
)
_IMPLEMENTATION_EVIDENCE_RE = re.compile(
    r"\b(?:pull request|PR\s*#?\d+|commit\s+[0-9a-f]{7,40}|candidate diff|"
    r"changed-code evidence|implementation diff)\b",
    re.IGNORECASE,
)
_PRODUCT_AUTHORITY_RE = re.compile(
    r"\b(?:Jira (?:description|UAC|accepted UAC|reviewer comment)|accepted UAC|"
    r"human review|reviewer feedback|product decision|approved requirement|"
    r"approved design|Figma design)\b",
    re.IGNORECASE,
)


def _text(manifest, plan_text=""):
    parts = [plan_text or ""]
    issue = manifest.get("issue") if isinstance(manifest, dict) else None
    if isinstance(issue, dict):
        parts += [str(issue.get(k, "")) for k in ("summary", "description", "title")]
    elif issue:
        parts.append(str(issue))
    return " ".join(parts).lower()


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("scope_conflict"), dict)


def implementation_scope_candidates(plan_text=""):
    """Return ACs whose stated evidence is implementation-only.

    This is deliberately evidence-field based. A source path alone can support
    an implementation observation without implying that the behavior is new
    product scope; explicit PR/commit/diff evidence activates this check.
    """
    candidates = []
    for match in _CANONICAL_AC_RE.finditer(str(plan_text or "")):
        evidence = match.group("evidence")
        if _IMPLEMENTATION_EVIDENCE_RE.search(evidence) and not _PRODUCT_AUTHORITY_RE.search(evidence):
            candidates.append(
                {
                    "ac_ref": match.group("id"),
                    "status": match.group("status"),
                    "evidence": evidence,
                }
            )
    return candidates


def validate_implementation_scope_authority(
    block, *, candidates=None, open_question_ids=None
):
    """Validate decisions for implementation-only behavior candidates."""
    if not isinstance(block, dict):
        return ["implementation_scope_authority must be an object"]
    problems = []
    if block.get("schema_version") != IMPLEMENTATION_SCOPE_SCHEMA:
        problems.append(
            "implementation_scope_authority.schema_version must be "
            + IMPLEMENTATION_SCOPE_SCHEMA
        )
    items = block.get("items")
    if not isinstance(items, list) or not items:
        return problems + [
            "implementation_scope_authority.items must be a non-empty list"
        ]
    candidate_by_id = {
        str(item.get("ac_ref", "")): item
        for item in (candidates or [])
        if isinstance(item, dict)
    }
    seen = set()
    open_ids = None if open_question_ids is None else set(open_question_ids)
    for index, item in enumerate(items):
        tag = f"implementation_scope_authority.items[{index}]"
        if not isinstance(item, dict):
            problems.append(f"{tag} must be an object")
            continue
        ac_ref = str(item.get("ac_ref", "")).strip()
        if not re.fullmatch(r"AC-\d{2}", ac_ref):
            problems.append(f"{tag}.ac_ref must use AC-## form")
        elif ac_ref in seen:
            problems.append(f"{tag}.ac_ref duplicates {ac_ref}")
        seen.add(ac_ref)
        candidate = candidate_by_id.get(ac_ref)
        if candidates is not None and candidate is None:
            problems.append(
                f"{tag}.ac_ref {ac_ref!r} is not an implementation-only candidate"
            )
        decision = str(item.get("decision", "")).strip()
        if decision not in IMPLEMENTATION_DECISIONS:
            problems.append(
                f"{tag}.decision must be one of {IMPLEMENTATION_DECISIONS}"
            )
        elif decision == "OPEN_QUESTION":
            if candidate is not None and candidate.get("status") != "Proposed":
                problems.append(
                    f"{tag}.ac_ref {ac_ref} must remain Proposed until product scope is approved"
                )
            oq_ref = str(item.get("open_question_ref", "")).strip()
            if not re.fullmatch(r"OQ-\d{2}", oq_ref) or (
                open_ids is not None and oq_ref not in open_ids
            ):
                problems.append(
                    f"{tag}: OPEN_QUESTION requires a real open_question_ref"
                )
        elif decision == "PRODUCT_APPROVED":
            authority = str(item.get("authority_source", "")).strip()
            if not authority or not _PRODUCT_AUTHORITY_RE.search(authority):
                problems.append(
                    f"{tag}: PRODUCT_APPROVED requires a named product-authority source"
                )
    missing = sorted(set(candidate_by_id) - seen)
    if missing:
        problems.append(
            "implementation_scope_authority is missing implementation-only ACs: "
            + ", ".join(missing)
        )
    return problems


def is_active(manifest, plan_text=""):
    """Scope reconciliation is expected when a fix/PR is present AND more than one problem
    or scope authority is in play."""
    t = _text(manifest, plan_text)
    if any(signal in t for signal in PRE_DEVELOPMENT_SIGNALS):
        return False
    fix = any(s in t for s in FIX_PRESENT_SIGNALS)
    multi = any(s in t for s in MULTI_PROBLEM_SIGNALS)
    return bool(fix and multi)


def _validate_thread(th, i):
    problems = []
    tag = f"scope_conflict.problem_threads[{i}]"
    if not isinstance(th, dict):
        return [f"{tag} must be an object"]
    if not str(th.get("thread_id", "")).strip():
        problems.append(f"{tag} is missing thread_id")
    if not str(th.get("problem_statement", "")).strip():
        problems.append(f"{tag} is missing problem_statement")
    status = str(th.get("status", "")).strip()
    if status not in THREAD_STATUS:
        problems.append(f"{tag}.status must be one of {', '.join(THREAD_STATUS)}")
    # a non-AC thread must not claim to be an acceptance contract
    if status in NON_AC_STATUS and th.get("maps_to_ac"):
        problems.append(f"{tag} has status {status} and must NOT map to a product Acceptance Criterion - "
                        "keep it as a secondary/unresolved/out-of-scope finding")
    return problems


def validate_scope_conflict(block, *, open_question_ids=None):
    if not isinstance(block, dict):
        return ["scope_conflict must be a JSON object"]
    if not isinstance(block.get("active", True), bool):
        return ["scope_conflict.active must be a boolean"]
    if not block.get("active", True):
        return []
    problems = []
    threads = block.get("problem_threads")
    if not isinstance(threads, list) or not threads:
        problems.append("scope_conflict.problem_threads must be a non-empty list (one per distinct problem)")
        threads = []
    for i, th in enumerate(threads):
        problems += _validate_thread(th, i)

    alignment = str(block.get("alignment", "")).strip()
    if alignment not in ALIGNMENT:
        problems.append(f"scope_conflict.alignment must be one of {', '.join(ALIGNMENT)}")

    # The core rule: a material Jira-scope vs fix-scope mismatch must be surfaced as an
    # Open Question, never merged into 'the Jira is fully solved'.
    open_ids = None if open_question_ids is None else set(open_question_ids)
    refs = [str(r).strip() for r in (block.get("open_question_refs") or []) if str(r).strip()]
    if alignment in NON_FULL_ALIGNMENT:
        if not refs:
            problems.append(f"scope_conflict.alignment is {alignment} but no open_question_refs are recorded - a "
                            "material scope mismatch must be surfaced as an Open Question, not merged away")
        elif open_ids is not None:
            missing = [r for r in refs if r not in open_ids]
            if missing:
                problems.append("scope_conflict.open_question_refs not present in the plan's open_questions: "
                                + ", ".join(missing))
    return problems


def unresolved_scope_without_open_question(block, open_question_ids=None):
    """True when a material scope mismatch exists but no open question exposes it (gate FAIL)."""
    if not isinstance(block, dict) or not block.get("active", True):
        return False
    alignment = str(block.get("alignment", "")).strip()
    refs = [str(r).strip() for r in (block.get("open_question_refs") or []) if str(r).strip()]
    if alignment not in NON_FULL_ALIGNMENT:
        return False
    if not refs:
        return True
    if open_question_ids is None:
        return False
    known = set(open_question_ids)
    return any(ref not in known for ref in refs)


def summarize(manifest, plan_text=""):
    lines = [f"ScopeConflictResolver: active={is_active(manifest, plan_text)}"]
    if is_present(manifest):
        for p in validate_scope_conflict(manifest["scope_conflict"]):
            lines.append(f"  {p}")
    return "\n".join(lines)
