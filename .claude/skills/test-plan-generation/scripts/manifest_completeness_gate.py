"""Signal-activated manifest-block completeness gate.

Many reasoning gates are intentionally backward-compatible: an absent optional
manifest block is treated as not applicable.  That compatibility becomes a
pipeline bypass when the plan already contains a reliable signal that the block
is applicable.  This module closes that gap without inventing a second signal
path.  It reuses the existing publishing, value-provenance, shared-path,
clarification, and behavior-model detectors.

An activated block must be present and non-empty.  A producer may instead record
an explicit, attributable waiver in ``manifest.block_waivers``.  Waivers make an
omission visible; they do not make the omitted reasoning true.

Generic only.  Standard library only.
"""
from __future__ import annotations

import json
from pathlib import Path

import behavior_model
import clarification_gate
import publishing_scope_coverage
import shared_path_regression_coverage
import value_provenance_coverage


FAILURE_PREFIX = "COMPLETENESS GATE:"
WAIVER_BLOCK = "block_waivers"

# These are the canonical semantic blocks already required by v3 manifests.  The
# completeness gate also activates them for an explicitly behavioral legacy
# manifest, preventing schema-v2 compatibility from becoming an omission bypass.
CORE_BEHAVIOR_BLOCKS = (
    "contract_facts",
    "issue_domains",
    "behavior_model",
    "behavior_graph",
    "semantic_closure",
    "coverage_hypotheses",
    "missing_questions",
    "evidence_lifecycle",
    "verifications",
    "dispositions",
    "acceptance_promotions",
)

# Public, deterministic SIGNAL -> REQUIRED_BLOCK registry.  Signal computation
# lives in ``detect_signals`` below and delegates to the existing detectors.
SIGNAL_REQUIRED_BLOCKS = {
    "behaviour_reasoning": CORE_BEHAVIOR_BLOCKS,
    "clarification_reasoning": ("clarification",),
    "publishing_or_preset": ("publishing_scope",),
    "value_write": ("clarification",),
    "shared_code_path": (
        "clarification",
        "change_impact",
        "scope_applicability",
        "entry_point_equivalence",
    ),
    "versioned_behavior": ("temporal_evidence",),
    "generated_artifact_behavior": ("generated_output_contract",),
}


def _failure(message: str) -> str:
    return f"{FAILURE_PREFIX} {message}"


def _is_non_empty(value) -> bool:
    """Return whether a manifest block contains usable declared content."""
    # JSON manifest blocks in this runtime are objects or arrays.  Scalars must
    # not count as a declaration because they would keep the owning validator
    # from receiving its real schema.
    return isinstance(value, (dict, list)) and bool(value)


def _behavior_fields(manifest: dict) -> dict:
    block = manifest.get("behavior_model")
    return block if isinstance(block, dict) else {}


def detect_signals(plan_body: str, manifest: dict) -> dict[str, bool]:
    """Return registry signals using only existing generic detector contracts."""
    if not isinstance(plan_body, str):
        plan_body = ""
    if not isinstance(manifest, dict):
        manifest = {}

    clarification_signals = clarification_gate.activation_signals(
        plan_body, manifest
    )
    model = _behavior_fields(manifest)
    behavior_opt_out = manifest.get("behaviour_matters") is False

    # Keep the existing behaviour_matters=false escape for the canonical
    # BehaviorModel pipeline.  Independent publishing/value/shared-path signals
    # still retain their own existing applicability semantics.
    behaviour_reasoning = not behavior_opt_out and (
        clarification_signals.get("behaviour_matters", False)
        or clarification_signals.get("behavior_reasoning_block", False)
        or behavior_model.is_present(manifest)
    )

    return {
        "behaviour_reasoning": bool(behaviour_reasoning),
        "clarification_reasoning": bool(
            not behavior_opt_out
            and (
                clarification_signals.get("behaviour_matters", False)
                or clarification_signals.get("behavior_reasoning_block", False)
            )
        ),
        "publishing_or_preset": bool(
            publishing_scope_coverage.is_publishing_ticket(manifest, plan_body)
        ),
        "value_write": bool(value_provenance_coverage.is_value_ticket(plan_body)),
        "shared_code_path": bool(
            shared_path_regression_coverage.is_shared_path_plan(plan_body)
        ),
        "versioned_behavior": bool(
            not behavior_opt_out and model.get("versioned_models")
        ),
        "generated_artifact_behavior": bool(
            not behavior_opt_out
            and (model.get("generated_artifacts") or model.get("artifact_shapes"))
        ),
    }


def required_blocks(plan_body: str, manifest: dict) -> dict[str, tuple[str, ...]]:
    """Return each required block and the active signals that require it."""
    signals = detect_signals(plan_body, manifest)
    by_block: dict[str, list[str]] = {}
    for signal_name, blocks in SIGNAL_REQUIRED_BLOCKS.items():
        if not signals.get(signal_name, False):
            continue
        for block in blocks:
            by_block.setdefault(block, []).append(signal_name)
    return {block: tuple(names) for block, names in by_block.items()}


def is_present(manifest, plan_body: str = "") -> bool:
    """Return whether at least one completeness-registry requirement is active."""
    return isinstance(manifest, dict) and bool(required_blocks(plan_body, manifest))


def _waivers(manifest: dict) -> tuple[dict[str, dict], list[str]]:
    raw = manifest.get(WAIVER_BLOCK, [])
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        return {}, [_failure("manifest.block_waivers must be a list")]

    indexed: dict[str, dict] = {}
    problems: list[str] = []
    for index, waiver in enumerate(raw):
        tag = f"manifest.block_waivers[{index}]"
        if not isinstance(waiver, dict):
            problems.append(_failure(f"{tag} must be an object"))
            continue
        block = str(waiver.get("block", "") or "").strip()
        reason = str(waiver.get("reason", "") or "").strip()
        waived_by = str(waiver.get("waived_by", "") or "").strip()
        if not block:
            problems.append(_failure(f"{tag}.block is required"))
        if not reason:
            problems.append(_failure(f"{tag}.reason is required and must be non-empty"))
        if not waived_by:
            problems.append(_failure(f"{tag}.waived_by is required"))
        if not block:
            continue
        if block in indexed:
            problems.append(
                _failure(f"{tag}.block duplicates waiver for '{block}'")
            )
            continue
        if reason and waived_by:
            indexed[block] = waiver
    return indexed, problems


def validate(plan_body, manifest) -> tuple[bool, list[str]]:
    """Validate all signal-activated blocks and explicit omission waivers."""
    if not isinstance(plan_body, str):
        return False, [_failure("plan_body must be a string")]
    if not isinstance(manifest, dict):
        return False, [_failure("manifest must be an object")]

    waivers, messages = _waivers(manifest)
    for block, signal_names in required_blocks(plan_body, manifest).items():
        if _is_non_empty(manifest.get(block)) or block in waivers:
            continue
        signals = ", ".join(signal_names)
        messages.append(
            _failure(
                f"required manifest block '{block}' is absent or empty; activated "
                f"by signal(s): {signals}. Add a non-empty block or an explicit "
                "manifest.block_waivers entry with block, reason, and waived_by."
            )
        )
    return not messages, messages


def summarize(manifest, plan_body: str = "") -> str:
    """Return a concise non-mutating summary of completeness state."""
    if not isinstance(manifest, dict):
        return "ManifestCompletenessGate: INVALID_MANIFEST"
    requirements = required_blocks(plan_body, manifest)
    waivers, waiver_problems = _waivers(manifest)
    missing = [
        block
        for block in requirements
        if not _is_non_empty(manifest.get(block)) and block not in waivers
    ]
    status = "CLEAN" if not missing and not waiver_problems else "ISSUES"
    active = [name for name, enabled in detect_signals(plan_body, manifest).items() if enabled]
    satisfied = sum(
        1 for block in requirements if _is_non_empty(manifest.get(block))
    )
    waived = sum(1 for block in requirements if block in waivers)
    return (
        f"ManifestCompletenessGate: {status} "
        f"(signals={','.join(active) or 'none'}; required={len(requirements)}; "
        f"present={satisfied}; waived={waived}; missing={len(missing)})"
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Signal-activated manifest-block completeness gate"
    )
    parser.add_argument("--manifest", required=True, help="evidence manifest JSON")
    parser.add_argument("--plan", required=True, help="test-plan Markdown body")
    args = parser.parse_args()

    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        plan_body = Path(args.plan).read_text(encoding="utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(_failure(f"could not read inputs: {exc}"))
        return 1

    print(summarize(manifest, plan_body))
    ok, messages = validate(plan_body, manifest)
    for message in messages:
        print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
