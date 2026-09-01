"""ScenarioEquivalenceReducer (Prompt 14) - collapse redundant scenario combinations
to representative behavioural paths.

WHY THIS EXISTS
---------------
Rich exploration can produce a Cartesian blow-up (3 href states x 3 lock states x
3 nesting states x 5 outputs x 3 lifecycle states). That is unacceptable. Two
scenarios are EQUIVALENT when they exercise the same semantic decision, the same
implementation branch, the same persisted-state transition, and the same resulting
contract - keep one representative. Preserve an extra scenario only when it
introduces a genuinely distinguishing factor.

Goal: maximum behavioural coverage with the minimum number of non-redundant tests.
Generic only. Stdlib only.
"""

SIGNATURE_KEYS = ("semantic_decision", "implementation_branch", "state_transition", "resulting_contract")

DISTINGUISHING_FACTORS = (
    "different_branch",
    "different_effective_value",
    "different_lifecycle_transition",
    "different_consumer_policy",
    "known_regression_history",
    "different_authority_behavior",
)


def _norm(s):
    return " ".join(str(s or "").lower().split())


def signature(entry):
    sig = entry.get("signature", {}) if isinstance(entry, dict) else {}
    return tuple(_norm(sig.get(k, "")) for k in SIGNATURE_KEYS)


def reduce(scenarios):
    """Group scenarios by behavioural signature. Within a group, scenarios with NO
    distinguishing factor collapse to one representative; a scenario that carries a
    distinguishing factor is always kept. Returns (representatives, collapsed)."""
    representatives, collapsed = [], []
    seen_plain = {}  # signature -> representative (for entries with no distinguishing factor)
    for s in scenarios:
        factors = s.get("distinguishing_factors", []) if isinstance(s, dict) else []
        sig = signature(s)
        if factors:
            representatives.append(s)  # a distinguishing factor makes it its own path
            continue
        if sig in seen_plain:
            collapsed.append(s)
        else:
            seen_plain[sig] = s
            representatives.append(s)
    return representatives, collapsed


def validate_entry(entry, by_id):
    problems = []
    sid = entry.get("scenario_id", "?") if isinstance(entry, dict) else "?"
    tag = f"scenario_reduction '{sid}'"
    if not isinstance(entry, dict):
        return [f"{tag}: each item must be an object"]
    sig = entry.get("signature")
    if not isinstance(sig, dict):
        problems.append(f"{tag}: signature must be an object with {', '.join(SIGNATURE_KEYS)}")
    else:
        for k in SIGNATURE_KEYS:
            if not (sig.get(k) or "").strip():
                problems.append(f"{tag}: signature.{k} is required (fully characterise the behavioural path)")
    factors = entry.get("distinguishing_factors", []) or []
    for f in factors:
        if f not in DISTINGUISHING_FACTORS:
            problems.append(f"{tag}: distinguishing factor '{f}' must be one of {', '.join(DISTINGUISHING_FACTORS)}")
    representative = entry.get("representative")
    if not isinstance(representative, bool):
        problems.append(f"{tag}: representative must be a boolean")
        return problems
    # a scenario introducing a distinguishing factor is its own path - it cannot be collapsed
    if factors and not representative:
        problems.append(f"{tag}: introduces a distinguishing factor ({', '.join(factors)}) so it cannot be collapsed; mark it representative")
    if not representative:
        target = entry.get("collapsed_into")
        if not target:
            problems.append(f"{tag}: a collapsed scenario must set collapsed_into to its representative")
        elif target not in by_id:
            problems.append(f"{tag}: collapsed_into '{target}' is not a scenario in this block")
        else:
            rep = by_id[target]
            if not rep.get("representative"):
                problems.append(f"{tag}: collapsed_into '{target}' is not itself a representative")
            if signature(rep) != signature(entry):
                problems.append(f"{tag}: collapsed into '{target}' but their behavioural signatures differ - they are not equivalent")
    return problems


def validate_reduction(block):
    if not isinstance(block, list):
        return ["scenario_reduction must be a JSON list"]
    by_id = {e.get("scenario_id"): e for e in block if isinstance(e, dict) and e.get("scenario_id")}
    problems = []
    for entry in block:
        problems.extend(validate_entry(entry, by_id))
    # redundancy: two representatives with identical signature and no distinguishing factor
    plain_reps = {}
    for e in block:
        if not isinstance(e, dict) or not e.get("representative") or (e.get("distinguishing_factors") or []):
            continue
        sig = signature(e)
        if sig in plain_reps:
            problems.append(
                f"scenario_reduction: '{e.get('scenario_id')}' and '{plain_reps[sig]}' share the same behavioural "
                f"signature with no distinguishing factor - collapse them to a single representative"
            )
        else:
            plain_reps[sig] = e.get("scenario_id")
    return problems


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("scenario_reduction"), list)


def summarize(manifest):
    problems = []
    if is_present(manifest):
        block = manifest["scenario_reduction"]
        problems = validate_reduction(block)
        reps, collapsed = reduce(block)
        head = f"ScenarioEquivalenceReducer: {len(reps)} representative(s), {len(collapsed)} collapsed"
    else:
        head = "ScenarioEquivalenceReducer: no scenario_reduction block"
    lines = [head]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)
