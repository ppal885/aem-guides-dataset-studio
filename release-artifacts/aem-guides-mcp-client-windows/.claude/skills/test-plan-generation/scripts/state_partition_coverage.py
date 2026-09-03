"""State-partition coverage gate (generic anti-miss), backward-compatible.

WHY THIS EXISTS
---------------
Measured across a corpus of human UAC_Done tickets and a blind-draft scoring run,
the single most frequent AND most-dropped coverage dimension is the STATE PARTITION:
a senior QA tests a behaviour under BOTH values of the state axis it touches - a
Global vs a Folder profile, a baseline vs the current version, an enumdef-bound vs
an unbound subjectdef, a condition/feature-flag enabled vs disabled. A description-
only draft tends to cover only the single state the ticket happens to name.

So this is a HARD, signal-activated requirement (like publishing_scope_coverage and
value_provenance_coverage): when the ACs name a state axis, at least one AC must
test more than one value of it (or the plan must disposition why only one state
applies). It deliberately does NOT cover DITA-OT-processing on/off or preset
in/out scope - publishing_scope_coverage owns those.

Generic only. Stdlib only.
"""
from __future__ import annotations

import re

# Activate when the ACs name a partitionable state axis (excluding the axes that
# publishing_scope_coverage already owns).
STATE_SIGNALS = (
    "global profile", "folder profile", "folder-level profile", "folder level profile",
    "baseline", "enumdef", "bound by enum", "condition preset", "feature flag",
    "when enabled", "when disabled", "configuration enabled", "setting enabled",
    "toggle is on", "toggle is off",
    # Language-count axis: a workflow/behaviour can differ between a single-language
    # (monolingual) job and a multi-language one; a description that reproduces on one
    # rarely proves the other. Both values must be tested when either is named.
    "single language", "single-language", "monolingual",
    "multi language", "multi-language", "multilingual",
    # Config-toggle axis for a named on/off product setting (e.g. automatic
    # translation approval): the on and off states are distinct partitions.
    "automatically approve", "auto approve", "auto-approve", "approve translation",
)

# Presence of any of these shows more than one value of the axis is tested.
PARTITION_TERMS = (
    "both", "with and without", "and without", "enabled and disabled",
    "on and off", "global profile and folder", "folder profile and global",
    "global and folder profile", "each profile", "per profile", "both profiles",
    "baseline and current", "bound and unbound", "regardless of the profile",
    "for both", "as well as without", "both bound", "and not in enumdef",
    "single and multi", "single- and multi", "monolingual and multilingual",
    "both single", "both monolingual", "as well as multi", "as well as multilingual",
    "approval on and off", "with and without approval", "approved and not approved",
)


def _acceptance_block(plan_text: str) -> str:
    if not plan_text:
        return ""
    m = re.search(r"\*\*Acceptance Criteria\*\*(.*?)(?:\n\*\*|\Z)", plan_text, re.S)
    return m.group(1) if m else plan_text


def is_state_ticket(plan_text: str) -> bool:
    ac = _acceptance_block(plan_text).lower()
    return any(sig in ac for sig in STATE_SIGNALS)


def _opt_out_reason(manifest) -> str:
    if not isinstance(manifest, dict):
        return ""
    na = manifest.get("state_partition_not_applicable")
    if isinstance(na, dict):
        return str(na.get("reason", "")).strip()
    if isinstance(na, str):
        return na.strip()
    return ""


def validate(manifest, plan_text: str = "") -> list[str]:
    if not is_state_ticket(plan_text):
        return []
    if len(_opt_out_reason(manifest)) >= 12:
        return []
    ac = _acceptance_block(plan_text).lower()
    if any(term in ac for term in PARTITION_TERMS):
        return []
    return [
        "state-partition ticket: the ACs name a state axis (profile, baseline, "
        "enumdef-bound/unbound, condition or feature-flag) but no acceptance criterion "
        "tests more than one value of it. Add an AC that covers both values (for "
        "example both a Global and a Folder profile, baseline and current, bound and "
        "unbound), or set state_partition_not_applicable with a concrete reason."
    ]


def summarize(manifest, plan_text: str = "") -> str:
    if not is_state_ticket(plan_text):
        return "StatePartitionCoverage: NOT_APPLICABLE (no state-axis signal)"
    problems = validate(manifest, plan_text)
    lines = [f"StatePartitionCoverage: {'CLEAN' if not problems else 'ISSUES'}"]
    lines.extend(f"  {p}" for p in problems)
    return "\n".join(lines)


def run_self_tests() -> None:
    nl = chr(10)
    non_state = nl.join(["**Acceptance Criteria**", "- AC-01: the panel shows the value.", ""])
    assert validate({}, non_state) == []

    single = nl.join([
        "**Acceptance Criteria**",
        "- AC-01: the behaviour holds under a Global Profile.",
        "**Expected**", ""])
    assert any("state-partition" in p for p in validate({}, single)), "single-state must fail"

    both = nl.join([
        "**Acceptance Criteria**",
        "- AC-01: the behaviour holds under both a Global Profile and a Folder Profile.",
        "**Expected**", ""])
    assert validate({}, both) == [], "partition term must pass"

    optout = {"state_partition_not_applicable": {"reason": "Only the Global profile can host this construct; a Folder profile cannot define it."}}
    assert validate(optout, single) == [], "concrete opt-out must pass"
    assert any("state-partition" in p for p in validate({"state_partition_not_applicable": "n/a"}, single)), "stub reason must not opt out"

    # Language-count axis: naming a single-language job requires the multi-language
    # value to be tested too (or vice versa).
    lang_single = nl.join([
        "**Acceptance Criteria**",
        "- AC-01: Accept Translation completes for a single-language translation job.",
        "**Expected**", ""])
    assert any("state-partition" in p for p in validate({}, lang_single)), "single-language axis must force the multi-language value"
    lang_both = nl.join([
        "**Acceptance Criteria**",
        "- AC-01: Accept Translation completes for both single and multi-language translation jobs.",
        "**Expected**", ""])
    assert validate({}, lang_both) == [], "single and multi language partition must pass"

    # Config-toggle axis: automatic translation approval on vs off.
    approve_single = nl.join([
        "**Acceptance Criteria**",
        "- AC-01: translation completes when Automatically Approve Translations is on.",
        "**Expected**", ""])
    assert any("state-partition" in p for p in validate({}, approve_single)), "auto-approve axis must force both states"
    approve_both = nl.join([
        "**Acceptance Criteria**",
        "- AC-01: translation completes with Automatically Approve Translations on and off.",
        "**Expected**", ""])
    assert validate({}, approve_both) == [], "auto-approve on and off must pass"
    print("state_partition_coverage self-tests: PASS")


if __name__ == "__main__":
    run_self_tests()
