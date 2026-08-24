"""EnumeratedRequirementCoverage - force every reporter-enumerated sub-requirement
(the numbered/bulleted defect or requirement list a ticket often carries) to be
dispositioned, so a multi-part ticket cannot silently drop one of its items.

WHY THIS EXISTS
---------------
Tickets like GUIDES-53897 enumerate many distinct sub-defects (loop never breaks,
result always success, pagination skips a failed page, no cancellation, unbounded
execution, weak logging, ...). The existing gates cover the affected code surface
(operation enum + config keys via affected_surface) and race patterns (concurrency
race), but nothing checks the ONE list the reporter actually wrote: did every
enumerated item become an Acceptance Criterion, an Open Question, or an explicit
out-of-scope decision? A reader can quietly miss item 6 of 9 and the plan still
passes every other gate.

This gate is deliberately generic - it knows nothing about any specific ticket. It
only enforces that IF a manifest records the reporter's enumerated requirements,
each one carries a real disposition:

  COVERED_BY_AC  - mapped to a product Acceptance Criterion (needs ac_ref).
  OPEN_QUESTION  - unresolved / product decision (needs open_question_ref).
  OUT_OF_SCOPE   - explicitly excluded for this ticket (needs reason).

Backward-compatible: a manifest with no `enumerated_requirements` block is not a
failure. When absent but the issue text clearly enumerates several items, the gate
emits a non-blocking REVIEW note (the heuristic cannot reliably tell a real
requirement list from incidental numbering). Stdlib only.
"""

import re

DISPOSITIONS = ("COVERED_BY_AC", "OPEN_QUESTION", "OUT_OF_SCOPE")

# Heuristic: an enumerated list in the issue text (numbered "1." / "1)" items or a
# markdown "# " / "- " list) with several entries. Used ONLY for the soft REVIEW note.
_NUMBERED_RE = re.compile(r"(?m)^\s*(\d{1,2})[.)]\s+\S")
_HASH_ITEM_RE = re.compile(r"(?m)^\s*#\s+\S")
_ENUMERATION_THRESHOLD = 3


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("enumerated_requirements"), list)


def _issue_text(manifest):
    issue = manifest.get("issue") if isinstance(manifest, dict) else None
    if isinstance(issue, dict):
        return " \n".join(str(issue.get(k, "")) for k in ("summary", "description", "title"))
    return str(issue or "")


def likely_enumerated(manifest):
    """Best-effort, non-blocking: does the issue text carry a multi-item enumerated
    list? Returns the count of detected items (0 when not enumerated)."""
    text = _issue_text(manifest)
    numbered = len(_NUMBERED_RE.findall(text))
    hashed = len(_HASH_ITEM_RE.findall(text))
    count = max(numbered, hashed)
    return count if count >= _ENUMERATION_THRESHOLD else 0


def validate_enumerated_requirements(block, *, ac_ids=None, open_question_ids=None):
    """Return a list of problem strings; empty list means valid."""
    ac_ids = set(ac_ids or [])
    open_question_ids = set(open_question_ids or [])
    problems = []

    if not isinstance(block, list):
        return ["enumerated_requirements must be a JSON list (one entry per reporter-enumerated item)"]
    if not block:
        return ["enumerated_requirements is present but empty - list each reporter-enumerated item, or omit the block"]

    seen_ids = set()
    for i, entry in enumerate(block):
        tag = f"enumerated_requirements[{i}]"
        if not isinstance(entry, dict):
            problems.append(f"{tag} must be an object")
            continue
        rid = str(entry.get("id", "")).strip()
        if not rid:
            problems.append(f"{tag} is missing 'id'")
        elif rid in seen_ids:
            problems.append(f"{tag}: duplicate id '{rid}'")
        else:
            seen_ids.add(rid)
        if not str(entry.get("text", "")).strip():
            problems.append(f"{tag} ('{rid or '?'}') is missing 'text' (the reporter's requirement/sub-defect)")
        disp = entry.get("disposition")
        if disp not in DISPOSITIONS:
            problems.append(f"{tag} ('{rid or '?'}'): disposition must be one of {DISPOSITIONS}, got {disp!r}")
            continue
        if disp == "COVERED_BY_AC":
            ac_ref = str(entry.get("ac_ref", "") or "").strip()
            if not ac_ref:
                problems.append(f"{tag} ('{rid or '?'}'): COVERED_BY_AC requires an ac_ref")
            elif ac_ids and ac_ref not in ac_ids:
                problems.append(f"{tag} ('{rid or '?'}'): ac_ref '{ac_ref}' is not an AC defined in the plan")
        elif disp == "OPEN_QUESTION":
            oq_ref = str(entry.get("open_question_ref", "") or "").strip()
            if not oq_ref:
                problems.append(f"{tag} ('{rid or '?'}'): OPEN_QUESTION requires an open_question_ref")
            elif open_question_ids and oq_ref not in open_question_ids:
                problems.append(f"{tag} ('{rid or '?'}'): open_question_ref '{oq_ref}' is not in the plan's open_questions")
        elif disp == "OUT_OF_SCOPE":
            if not str(entry.get("reason", "") or "").strip():
                problems.append(f"{tag} ('{rid or '?'}'): OUT_OF_SCOPE requires a non-empty reason")
    return problems


def overloaded_ac_refs(block, *, threshold=2):
    """Return {ac_ref: [ids]} for ACs that COVERED_BY_AC-map two or more DISTINCT
    enumerated requirements. Coverage-existence is not coverage-adequacy: several
    distinct sub-requirements folded onto one AC is a smell that the AC is over-loaded
    and one requirement may not actually be satisfied (e.g. structured-progress folded
    into a logging AC). Advisory only."""
    if not isinstance(block, list):
        return {}
    by_ref = {}
    for entry in block:
        if not isinstance(entry, dict) or entry.get("disposition") != "COVERED_BY_AC":
            continue
        ref = str(entry.get("ac_ref", "") or "").strip()
        rid = str(entry.get("id", "") or "").strip()
        if ref:
            by_ref.setdefault(ref, []).append(rid)
    return {ref: ids for ref, ids in by_ref.items() if len(ids) >= threshold}


def summarize(manifest, plan_text=""):
    lines = [f"EnumeratedRequirementCoverage: present={is_present(manifest)} likely_enumerated={likely_enumerated(manifest)}"]
    if is_present(manifest):
        ac_ids = set(re.findall(r"AC-\d{2}", plan_text or ""))
        for p in validate_enumerated_requirements(manifest["enumerated_requirements"], ac_ids=ac_ids):
            lines.append(f"  {p}")
    return "\n".join(lines)
