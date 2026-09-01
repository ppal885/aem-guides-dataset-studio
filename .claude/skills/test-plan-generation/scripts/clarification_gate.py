"""Ask-first clarification gate for material QE dimensions.

The gate is deliberately separate from the existing publishing, value-provenance,
and shared-path coverage gates.  Those gates validate acceptance-criteria content;
this gate reuses their signal detectors only to prove that the relevant dimension
was enumerated and resolved before acceptance criteria were authored.

Backward compatibility is explicit: a non-activated manifest may omit the optional
``clarification`` block.  Once the ticket carries behavioural or known forcing-gate
signals, omission becomes a hard failure.

Generic only.  Standard library only.
"""
from __future__ import annotations

import re

import publishing_scope_coverage
import shared_path_regression_coverage
import value_provenance_coverage


BLOCK_NAME = "clarification"
SCHEMA_VERSION = "aem-guides-clarification-v1"
FAILURE_PREFIX = "CLARIFICATION GATE:"

AXES = (
    "VALUE_SET_CHANNEL",
    "CODE_PATH_CONSUMER",
    "OUTPUT_PRESET",
    "TOPIC_TYPE",
    "TERMINAL_STATE",
    "LIFECYCLE",
    "CONFIG_BRANCH",
    "PERMISSION_ROLE",
    "MIGRATION_PATH",
)

RESOLUTIONS = (
    "COVERED_BY_AC",
    "RESOLVED_FROM_EVIDENCE",
    "ASKED_AND_ANSWERED",
    "DEFERRED_OPEN_QUESTION",
    "UNRESOLVED",
)

QUESTION_STATUSES = ("ANSWERED", "WAITING")
ANSWERED_BY_VALUES = ("user", "evidence")

AC_ID_RE = re.compile(r"\bAC-\d+\b", re.IGNORECASE)
REPOSITORY_CHANNEL_RE = re.compile(
    r"\b(?:crx\s*/?\s*de|crxde|repository(?:[\s-]+metadata)?[\s-]+node|"
    r"jcr:content(?:/metadata)?)\b",
    re.IGNORECASE,
)


def _failure(message: str) -> str:
    return f"{FAILURE_PREFIX} {message}"


def is_present(manifest) -> bool:
    """Return whether *manifest* contains a clarification object."""
    return isinstance(manifest, dict) and isinstance(manifest.get(BLOCK_NAME), dict)


def _activation_signals(plan_body: str, manifest: dict) -> dict[str, bool]:
    """Return the generic signals that make clarification mandatory.

    The three plan detectors are the existing coverage-gate detectors.  Their
    pass/fail decisions remain in their owning modules; only their applicability
    signals are reused here.
    """
    behavior_declared = (
        "behaviour_matters" in manifest
        and manifest.get("behaviour_matters") is not False
    )
    behavior_blocks = any(
        key in manifest for key in ("behavior_model", "coverage_hypotheses")
    )
    publishing = publishing_scope_coverage.is_publishing_ticket(manifest, plan_body)
    value_write = value_provenance_coverage.is_value_ticket(plan_body)
    shared_path = shared_path_regression_coverage.is_shared_path_plan(plan_body)
    return {
        "behaviour_matters": behavior_declared,
        "behavior_reasoning_block": behavior_blocks,
        "publishing_or_preset": publishing,
        "value_write": value_write,
        "shared_code_path": shared_path,
    }


def _known_open_question_ids(manifest: dict) -> set[str]:
    values = manifest.get("open_questions")
    if not isinstance(values, list):
        return set()
    return {
        str(item.get("id", "")).strip().upper()
        for item in values
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }


def _string_list(value) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def validate(plan_body, manifest) -> tuple[bool, list[str]]:
    """Validate ask-first clarification state.

    Returns ``(ok, messages)``.  Every message is a hard failure and carries the
    stable ``CLARIFICATION GATE:`` prefix so callers and fixtures can identify it.
    """
    if not isinstance(plan_body, str):
        return False, [_failure("plan_body must be a string")]
    if not isinstance(manifest, dict):
        return False, [_failure("manifest must be an object")]

    signals = _activation_signals(plan_body, manifest)
    activated = any(signals.values())
    if not is_present(manifest):
        if BLOCK_NAME in manifest:
            return False, [_failure("clarification must be an object")]
        if not activated:
            return True, []
        active_names = ", ".join(name for name, present in signals.items() if present)
        return False, [
            _failure(
                "clarification block is required because ask-first signals were found: "
                f"{active_names}"
            )
        ]

    block = manifest[BLOCK_NAME]
    messages: list[str] = []
    if block.get("schema_version") != SCHEMA_VERSION:
        messages.append(
            _failure(f"clarification.schema_version must be '{SCHEMA_VERSION}'")
        )

    dimensions = block.get("dimension_space")
    if not isinstance(dimensions, list):
        messages.append(_failure("clarification.dimension_space must be a list"))
        dimensions = []
    elif activated and not dimensions:
        messages.append(
            _failure("clarification.dimension_space must enumerate at least one dimension")
        )

    plan_ac_ids = {match.upper() for match in AC_ID_RE.findall(plan_body)}
    open_question_ids = _known_open_question_ids(manifest)
    seen_dimension_ids: set[str] = set()
    seen_axes: set[str] = set()
    repository_channel_enumerated = False

    for index, dimension in enumerate(dimensions):
        tag = f"clarification.dimension_space[{index}]"
        if not isinstance(dimension, dict):
            messages.append(_failure(f"{tag} must be an object"))
            continue

        dimension_id = str(dimension.get("dimension_id", "") or "").strip()
        if not dimension_id:
            messages.append(_failure(f"{tag}.dimension_id is required"))
        elif dimension_id in seen_dimension_ids:
            messages.append(_failure(f"{tag}.dimension_id duplicates '{dimension_id}'"))
        else:
            seen_dimension_ids.add(dimension_id)

        axis = str(dimension.get("axis", "") or "").strip()
        if axis not in AXES:
            messages.append(
                _failure(f"{tag}.axis must be one of {', '.join(AXES)}")
            )
        else:
            seen_axes.add(axis)

        candidate = str(dimension.get("candidate", "") or "").strip()
        if not candidate:
            messages.append(_failure(f"{tag}.candidate is required"))
        if axis == "VALUE_SET_CHANNEL" and REPOSITORY_CHANNEL_RE.search(candidate):
            repository_channel_enumerated = True

        material = dimension.get("material")
        if not isinstance(material, bool):
            messages.append(_failure(f"{tag}.material must be true or false"))
        if not str(dimension.get("materiality_reason", "") or "").strip():
            messages.append(_failure(f"{tag}.materiality_reason is required"))

        resolution = dimension.get("resolution")
        if resolution not in RESOLUTIONS:
            messages.append(
                _failure(f"{tag}.resolution must be one of {', '.join(RESOLUTIONS)}")
            )
            continue
        if material is True and resolution == "UNRESOLVED":
            messages.append(
                _failure(
                    f"{tag} ({dimension_id or axis or 'unknown'}): material dimension "
                    "must not remain UNRESOLVED"
                )
            )

        if resolution == "DEFERRED_OPEN_QUESTION":
            oq_ref = str(dimension.get("open_question_ref", "") or "").strip().upper()
            if not oq_ref:
                messages.append(
                    _failure(
                        f"{tag}: DEFERRED_OPEN_QUESTION requires open_question_ref"
                    )
                )
            elif oq_ref not in open_question_ids:
                messages.append(
                    _failure(
                        f"{tag}.open_question_ref '{oq_ref}' is not declared in "
                        "manifest.open_questions"
                    )
                )

        if resolution == "COVERED_BY_AC":
            ac_refs = dimension.get("ac_refs")
            if not _string_list(ac_refs):
                messages.append(
                    _failure(f"{tag}: COVERED_BY_AC requires non-empty ac_refs")
                )
            else:
                for raw_ref in ac_refs:
                    ac_ref = raw_ref.strip().upper()
                    if ac_ref not in plan_ac_ids:
                        messages.append(
                            _failure(
                                f"{tag}.ac_refs contains '{raw_ref}', which is absent "
                                "from the plan body"
                            )
                        )

    questions = block.get("questions_surfaced_to_user", [])
    blocking_question_exists = False
    if not isinstance(questions, list):
        messages.append(
            _failure("clarification.questions_surfaced_to_user must be a list")
        )
        questions = []

    seen_question_ids: set[str] = set()
    for index, question in enumerate(questions):
        tag = f"clarification.questions_surfaced_to_user[{index}]"
        if not isinstance(question, dict):
            messages.append(_failure(f"{tag} must be an object"))
            continue
        question_id = str(question.get("question_id", "") or "").strip()
        if not question_id:
            messages.append(_failure(f"{tag}.question_id is required"))
        elif question_id in seen_question_ids:
            messages.append(_failure(f"{tag}.question_id duplicates '{question_id}'"))
        else:
            seen_question_ids.add(question_id)
        if not str(question.get("question", "") or "").strip():
            messages.append(_failure(f"{tag}.question is required"))

        blocking = question.get("blocking")
        if not isinstance(blocking, bool):
            messages.append(_failure(f"{tag}.blocking must be true or false"))
        elif blocking:
            blocking_question_exists = True

        status = question.get("status")
        if status not in QUESTION_STATUSES:
            messages.append(
                _failure(
                    f"{tag}.status must be one of {', '.join(QUESTION_STATUSES)}"
                )
            )
        if blocking is True and status != "ANSWERED":
            messages.append(
                _failure(
                    f"{tag} ({question_id or 'unknown'}): blocking question must be ANSWERED"
                )
            )
        if status == "ANSWERED":
            if not str(question.get("answer", "") or "").strip():
                messages.append(_failure(f"{tag}.answer is required when status is ANSWERED"))
            if question.get("answered_by") not in ANSWERED_BY_VALUES:
                messages.append(
                    _failure(
                        f"{tag}.answered_by must be one of {', '.join(ANSWERED_BY_VALUES)} "
                        "when status is ANSWERED"
                    )
                )

    if blocking_question_exists and block.get("authoring_gated_on_answers") is not True:
        messages.append(
            _failure(
                "clarification.authoring_gated_on_answers must be true when a blocking "
                "question exists"
            )
        )

    if signals["publishing_or_preset"] and "OUTPUT_PRESET" not in seen_axes:
        messages.append(
            _failure(
                "publishing or preset signal requires an OUTPUT_PRESET dimension"
            )
        )
    if signals["value_write"]:
        if "VALUE_SET_CHANNEL" not in seen_axes:
            messages.append(
                _failure("value-write signal requires a VALUE_SET_CHANNEL dimension")
            )
        elif not repository_channel_enumerated:
            messages.append(
                _failure(
                    "VALUE_SET_CHANNEL must enumerate a CRX/DE or repository-node candidate"
                )
            )
    if signals["shared_code_path"] and "CODE_PATH_CONSUMER" not in seen_axes:
        messages.append(
            _failure("shared-code-path signal requires a CODE_PATH_CONSUMER dimension")
        )

    return not messages, messages


def summarize(manifest) -> str:
    """Return a concise, non-validating summary of the clarification block."""
    if not is_present(manifest):
        return "ClarificationGate: NOT_PRESENT"
    block = manifest[BLOCK_NAME]
    dimensions = block.get("dimension_space")
    questions = block.get("questions_surfaced_to_user")
    dimension_count = len(dimensions) if isinstance(dimensions, list) else 0
    question_count = len(questions) if isinstance(questions, list) else 0
    return (
        "ClarificationGate: PRESENT "
        f"({dimension_count} dimension(s), {question_count} surfaced question(s))"
    )


def main() -> int:
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Ask-first clarification forcing gate")
    parser.add_argument("--manifest", required=True, help="evidence manifest JSON")
    parser.add_argument("--plan", required=True, help="test-plan Markdown body")
    args = parser.parse_args()

    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        plan_body = Path(args.plan).read_text(encoding="utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(_failure(f"could not read inputs: {exc}"))
        return 1

    print(summarize(manifest))
    ok, messages = validate(plan_body, manifest)
    for message in messages:
        print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
