"""Validate explicit terminal-state dispositions for asynchronous work."""

from __future__ import annotations


SCHEMA_VERSION = "aem-guides-terminal-states-v1"
REQUIRED_STATES = ("succeeded", "failed", "cancelled", "retry_exhausted")
DISPOSITIONS = ("COVERED_BY_AC", "OPEN_QUESTION")


def validate_terminal_states(
    block, *, ac_ids=None, open_question_ids=None, plan_text=""
):
    del plan_text
    known_ac_ids = None if ac_ids is None else set(ac_ids)
    known_oq_ids = None if open_question_ids is None else set(open_question_ids)
    if not isinstance(block, dict):
        return ["terminal_states must be an object"]
    problems = []
    if block.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"terminal_states.schema_version must be {SCHEMA_VERSION}")
    states = block.get("states")
    if not isinstance(states, list):
        return problems + ["terminal_states.states must be a list"]
    seen = set()
    for index, entry in enumerate(states):
        tag = f"terminal_states.states[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{tag} must be an object")
            continue
        state = entry.get("state")
        if state not in REQUIRED_STATES:
            problems.append(f"{tag}.state is unknown: {state!r}")
            continue
        if state in seen:
            problems.append(f"{tag} duplicates terminal state {state!r}")
        seen.add(state)
        disposition = entry.get("disposition")
        if disposition not in DISPOSITIONS:
            problems.append(f"{tag}.disposition must be one of {DISPOSITIONS}")
        elif disposition == "COVERED_BY_AC":
            ref = str(entry.get("ac_ref", "")).strip()
            if not ref or (known_ac_ids is not None and ref not in known_ac_ids):
                problems.append(f"{tag}: COVERED_BY_AC requires a valid ac_ref")
        else:
            ref = str(entry.get("open_question_ref", "")).strip()
            if not ref or (known_oq_ids is not None and ref not in known_oq_ids):
                problems.append(f"{tag}: OPEN_QUESTION requires a valid open_question_ref")
    missing = [state for state in REQUIRED_STATES if state not in seen]
    if missing:
        problems.append(f"missing terminal state disposition(s): {missing}")
    return problems
