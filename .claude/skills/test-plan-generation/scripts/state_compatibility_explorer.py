"""ExistingStateCompatibilityExplorer (Prompt 11) - reason about persisted/stale
state across the fix boundary, and stop "recovery of old corrupted state" from
silently becoming an AC.

WHY THIS EXISTS
---------------
Many AEM Guides bugs are state-lifecycle bugs: first run works, later runs fail
until generated nodes are deleted; a bug leaves stale/corrupted persisted data;
cache/repository properties survive across operations; a fix may only prevent NEW
corruption without repairing OLD state. These three states are NOT interchangeable:

  CLEAN_PRE_FIX_STATE            - fresh content, pre-fix code.
  STATE_CREATED_BY_FIXED_CODE    - fresh content, fixed code.
  STATE_CREATED_BY_BUGGY_OLD_CODE- already-corrupted state left by the bug.

Critical rule: do NOT convert recovery of already-corrupted state into an
Acceptance Criterion unless product/engineering evidence establishes that
backward-compatibility/recovery requirement. If unclear -> OPEN QUESTION.

Generic only. Stdlib only.
"""

STATE_ORIGINS = ("CLEAN_PRE_FIX_STATE", "STATE_CREATED_BY_FIXED_CODE", "STATE_CREATED_BY_BUGGY_OLD_CODE")

# Signals that a state-lifecycle / persisted-state dimension is in play.
ACTIVATION_SIGNALS = (
    "first run", "first generation", "subsequent run", "subsequent generation", "second run",
    "second generation", "every subsequent", "until", "deleted", "stale", "corrupt",
    "corrupted", "leftover", "left behind", "persist", "persisted", "cache", "cached",
    "migration", "migrate", "upgrade", "recover", "recovery", "regenerate", "republish",
    "recompute", "survives", "already-failed", "already failed", "already-corrupted",
    "repository property", "generated nodes", "stale state",
)

RECOVERY_QUESTIONS = (
    "Does the fix only prevent new corruption?",
    "Can existing affected state recover automatically?",
    "Is explicit cleanup required?",
    "Does regeneration recompute the state?",
    "Does delete/recreate output remove stale state?",
    "Is upgrade/backward compatibility expected?",
)


def _bm_text(manifest):
    bm = manifest.get("behavior_model") if isinstance(manifest, dict) else None
    if not isinstance(bm, dict):
        return "", bm
    parts = []
    for f in ("trigger", "operations", "affected_state", "unknowns", "read_paths",
              "update_paths", "remove_paths", "recompute_paths", "write_paths"):
        parts.extend(str(x) for x in (bm.get(f) or []))
    for fact in (bm.get("facts") or []):
        if isinstance(fact, dict):
            parts.append(str(fact.get("fact", "")))
    return " ".join(parts).lower(), bm


def detect_signals(manifest):
    """Return the state-lifecycle signals present in the behaviour model / evidence."""
    text, bm = _bm_text(manifest)
    hits = sorted({s for s in ACTIVATION_SIGNALS if s in text})
    # remove/recompute paths are a strong structural signal even without keywords
    if isinstance(bm, dict) and (bm.get("remove_paths") or bm.get("recompute_paths")):
        hits.append("state-mutation-paths")
    return sorted(set(hits))


def is_active(manifest):
    """State-compatibility exploration is expected when persisted/stale-state signals
    exist. Not triggered for plain UI/stateless tickets."""
    return bool(detect_signals(manifest))


def validate_state_compatibility(block):
    """Validate a manifest `state_compatibility` block. Returns problem strings."""
    if not isinstance(block, dict):
        return ["state_compatibility must be a JSON object"]
    problems = []
    if not isinstance(block.get("active", True), bool):
        problems.append("state_compatibility.active must be a boolean")
    if not block.get("active", True):
        return problems

    states = block.get("states")
    if not isinstance(states, dict):
        problems.append("state_compatibility.states must be an object addressing the three state origins")
    else:
        for origin in STATE_ORIGINS:
            if origin not in states:
                problems.append(f"state_compatibility.states must address {origin} (do not assume the three states behave identically)")

    recovery = block.get("recovery_of_old_state")
    if not isinstance(recovery, dict):
        problems.append("state_compatibility.recovery_of_old_state must be an object {required, evidence, disposition}")
        return problems
    required = recovery.get("required")
    evidence = recovery.get("evidence", []) or []
    disposition = recovery.get("disposition", "")
    if required not in (True, False, "unknown"):
        problems.append("recovery_of_old_state.required must be true, false, or 'unknown'")
    if disposition not in ("ACCEPTANCE_CONTRACT", "OPEN_QUESTION", "OUT_OF_SCOPE"):
        problems.append("recovery_of_old_state.disposition must be ACCEPTANCE_CONTRACT, OPEN_QUESTION, or OUT_OF_SCOPE")
    # The critical rule: recovery of already-corrupted state may be an AC only with
    # product/engineering evidence that the compatibility requirement exists.
    if disposition == "ACCEPTANCE_CONTRACT" and (required is not True or not evidence):
        problems.append(
            "recovery_of_old_state is dispositioned ACCEPTANCE_CONTRACT without product/engineering evidence that "
            "old-state recovery is required - do not assume the fix repairs already-corrupted state; make it an "
            "OPEN_QUESTION unless evidence establishes the compatibility requirement"
        )
    if required == "unknown" and disposition != "OPEN_QUESTION":
        problems.append("recovery_of_old_state.required is unknown, so its disposition must be OPEN_QUESTION")
    return problems


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("state_compatibility"), dict)


def summarize(manifest):
    problems = []
    active = is_active(manifest)
    lines = [f"ExistingStateCompatibilityExplorer: active={active} signals={detect_signals(manifest)}"]
    if is_present(manifest):
        problems = validate_state_compatibility(manifest["state_compatibility"])
    elif active:
        problems = ["state-lifecycle signals present but no state_compatibility exploration recorded"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)
