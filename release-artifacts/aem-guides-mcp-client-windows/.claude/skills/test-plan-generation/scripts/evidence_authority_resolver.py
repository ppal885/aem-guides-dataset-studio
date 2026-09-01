"""EvidenceAuthorityResolver (Prompt 15) - not all evidence is equally authoritative,
and conflicts must not be resolved by recency or similarity.

WHY THIS EXISTS
---------------
RAG surfaces old and new Jira comments, product docs, spec, current code, old
automation, proposed designs, and final decisions. "Latest comment wins" and
"highest similarity wins" are both wrong. This module classifies each evidence item's
status and authority, forbids recency/similarity as a conflict-resolution method, and
requires a genuine authority conflict to be resolved by an explicit decision or
preserved as an Open Question. Superseded/rejected evidence cannot stand as current truth.

Generic only. Stdlib only.
"""

EVIDENCE_STATUSES = (
    "PROPOSED", "UNDER_DISCUSSION", "CONFIRMED", "IMPLEMENTED",
    "SUPERSEDED", "REJECTED", "HISTORICAL_COMPATIBILITY", "UNKNOWN",
)
AUTHORITY_DIMENSIONS = (
    "PRODUCT_REQUIREMENT_AUTHORITY", "SPECIFICATION_AUTHORITY",
    "IMPLEMENTATION_AUTHORITY", "HISTORICAL_BEHAVIOR", "TEST_EVIDENCE",
)
# Statuses that are NOT current truth and must not ground a current conclusion.
NON_CURRENT_STATUSES = frozenset({"SUPERSEDED", "REJECTED", "PROPOSED", "UNDER_DISCUSSION", "UNKNOWN"})

# Conflict resolution methods.
BANNED_RESOLUTIONS = frozenset({"LATEST_COMMENT", "LATEST_WINS", "MOST_RECENT", "RECENCY", "HIGHEST_SIMILARITY", "SIMILARITY"})
VALID_RESOLUTIONS = frozenset({
    "EXPLICIT_FINAL_DECISION", "AUTHORITY_ORDERING", "CURRENT_IMPLEMENTATION",
    "CURRENT_DOCS", "LATER_CORRECTION", "ACCEPTED_PRODUCT_DECISION",
})
DISPOSITIONS = frozenset({"OPEN_QUESTION", "RESOLVED"})


def is_current(item):
    return isinstance(item, dict) and item.get("status") not in NON_CURRENT_STATUSES


def validate_item(item):
    problems = []
    eid = item.get("evidence_id", "?") if isinstance(item, dict) else "?"
    tag = f"evidence '{eid}'"
    if not isinstance(item, dict):
        return [f"{tag}: each evidence item must be an object"]
    if not (item.get("evidence_id") or "").strip():
        problems.append(f"{tag}: missing evidence_id")
    if not (item.get("statement") or "").strip():
        problems.append(f"{tag}: missing statement")
    if item.get("status") not in EVIDENCE_STATUSES:
        problems.append(f"{tag}: status '{item.get('status')}' must be one of {', '.join(EVIDENCE_STATUSES)}")
    if item.get("authority") not in AUTHORITY_DIMENSIONS:
        problems.append(f"{tag}: authority '{item.get('authority')}' must be one of {', '.join(AUTHORITY_DIMENSIONS)}")
    return problems


def validate_conflict(conflict, items_by_id):
    problems = []
    if not isinstance(conflict, dict):
        return ["each conflict must be an object"]
    between = conflict.get("between", [])
    tag = f"conflict {between or '?'}"
    if not isinstance(between, list) or len(between) < 2:
        problems.append(f"{tag}: 'between' must list at least two evidence_ids")
        between = between if isinstance(between, list) else []
    for eid in between:
        if eid not in items_by_id:
            problems.append(f"{tag}: references unknown evidence_id '{eid}'")

    method = (conflict.get("resolution_method") or "").upper()
    disposition = conflict.get("disposition", "")
    if disposition not in DISPOSITIONS:
        problems.append(f"{tag}: disposition must be OPEN_QUESTION or RESOLVED")
    # Never resolve by recency or similarity.
    if method in BANNED_RESOLUTIONS:
        problems.append(
            f"{tag}: resolution_method '{method}' is forbidden - evidence conflicts must not be resolved by recency "
            f"('latest comment wins') or similarity ('highest similarity wins'); use an explicit decision/authority "
            f"ordering, or preserve the conflict as an OPEN_QUESTION"
        )
    if disposition == "RESOLVED":
        if method not in VALID_RESOLUTIONS:
            problems.append(f"{tag}: a RESOLVED conflict needs a valid resolution_method ({', '.join(sorted(VALID_RESOLUTIONS))})")
        if not (conflict.get("resolved_by") or "").strip():
            problems.append(f"{tag}: a RESOLVED conflict must state resolved_by (which authority/decision wins)")
        if not (conflict.get("note") or "").strip():
            problems.append(f"{tag}: a RESOLVED conflict must explain the resolution in 'note'")
        winner = conflict.get("resolved_by")
        if winner in items_by_id and not is_current(items_by_id[winner]):
            problems.append(f"{tag}: resolved_by '{winner}' is superseded/rejected/not-yet-confirmed and cannot be the current truth")
    return problems


def validate_evidence_authority(block):
    if not isinstance(block, dict):
        return ["evidence_authority must be a JSON object with 'items' and optional 'conflicts'"]
    problems = []
    items = block.get("items", [])
    if not isinstance(items, list):
        problems.append("evidence_authority.items must be a list")
        items = []
    for it in items:
        problems.extend(validate_item(it))
    items_by_id = {it.get("evidence_id"): it for it in items if isinstance(it, dict) and it.get("evidence_id")}
    conflicts = block.get("conflicts", [])
    if not isinstance(conflicts, list):
        problems.append("evidence_authority.conflicts must be a list")
        conflicts = []
    for c in conflicts:
        problems.extend(validate_conflict(c, items_by_id))
    return problems


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("evidence_authority"), dict)


def summarize(manifest):
    problems = []
    if is_present(manifest):
        problems = validate_evidence_authority(manifest["evidence_authority"])
    lines = [f"EvidenceAuthorityResolver: {'CLEAN' if not problems else 'ISSUES'}"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)
