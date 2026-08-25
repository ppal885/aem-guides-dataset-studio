"""Feature-class registry for reusable QA-dimension coverage.

The registry turns recurring review misses into data: add one REGISTRY row,
register a validator only when the dimension is new, and add one self-test.
Classification is deliberately advisory; an explicit declaration is validated
strictly, while a detected class without a declaration produces REVIEW only.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path


SCHEMA_VERSION = "aem-guides-feature-classification-v1"
DATA_SCHEMA_VERSION = "aem-guides-feature-class-registry-v1"


def _load_peer(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        module_name, Path(__file__).with_name(filename)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ui_surface_scope_mod = _load_peer("ui_surface_scope", "ui_surface_scope.py")
role_provisioning_mod = _load_peer("role_provisioning", "role_provisioning.py")
concurrency_race_mod = _load_peer(
    "feature_registry_concurrency_race", "concurrency_race_explorer.py"
)
terminal_states_mod = _load_peer("terminal_states", "terminal_states.py")
configuration_enumeration_mod = _load_peer(
    "configuration_enumeration_scope", "configuration_enumeration_scope.py"
)


def _load_registry():
    path = Path(__file__).with_name("data") / "feature_class_registry.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != DATA_SCHEMA_VERSION:
        raise ValueError(f"feature class registry schema must be {DATA_SCHEMA_VERSION}")
    classes = data.get("classes")
    if not isinstance(classes, dict) or not classes:
        raise ValueError("feature class registry must declare classes")
    for class_name, config in classes.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", str(class_name)):
            raise ValueError(f"invalid feature class name: {class_name!r}")
        if not isinstance(config, dict):
            raise ValueError(f"feature class {class_name!r} must be an object")
        for key in ("signals", "required_dimensions"):
            values = config.get(key)
            if not isinstance(values, list) or not values or not all(
                isinstance(value, str) and value.strip() for value in values
            ):
                raise ValueError(
                    f"feature class {class_name!r}.{key} must be a non-empty string list"
                )
    return classes


REGISTRY = _load_registry()


def _validate_concurrency(
    block, *, ac_ids=None, open_question_ids=None, plan_text=""
):
    del plan_text
    problems = concurrency_race_mod.validate_concurrency_race_analysis(
        block, ac_ids=ac_ids, open_question_ids=open_question_ids
    )
    if isinstance(block, dict) and block.get("active") is not True:
        problems.append(
            "concurrency_race_analysis must be active for a declared async_job class"
        )
    return problems


DIMENSION_VALIDATORS = {
    "ui_surface_scope": ui_surface_scope_mod.validate_ui_surface_scope,
    "role_provisioning": role_provisioning_mod.validate_role_provisioning,
    "concurrency_race_analysis": _validate_concurrency,
    "terminal_states": terminal_states_mod.validate_terminal_states,
    "configuration_enumeration_scope": (
        configuration_enumeration_mod.validate_configuration_enumeration_scope
    ),
}


_EXCLUDED_SIGNAL_KEYS = {
    "feature_classification",
    "ui_surface_scope",
    "role_provisioning",
    "concurrency_race_analysis",
    "terminal_states",
    "configuration_enumeration_scope",
}


def _value_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _value_strings(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from _value_strings(nested)


def _signal_haystack(manifest, plan_text):
    parts = [str(plan_text or "")]
    if isinstance(manifest, dict):
        for key, value in manifest.items():
            if key not in _EXCLUDED_SIGNAL_KEYS:
                parts.extend(_value_strings(value))
    return "\n".join(parts).casefold()


def _terminal_token_pattern(token: str) -> str:
    if token == "display":
        return r"display(?:s|ed|ing)?"
    if token == "rendered":
        return r"render(?:s|ed|ing)?"
    if token == "queue":
        return r"(?:queue(?:s|d)?|queuing)"
    escaped = re.escape(token)
    if len(token) > 3 and not token.endswith("s"):
        return escaped + r"(?:s|es)?"
    return escaped


def _contains_signal(haystack: str, signal: str) -> bool:
    tokens = signal.casefold().split()
    patterns = [re.escape(token) for token in tokens]
    if patterns:
        patterns[-1] = _terminal_token_pattern(tokens[-1])
    phrase = r"\s+".join(patterns)
    return bool(re.search(rf"(?<![\w-]){phrase}(?![\w-])", haystack))


def classify(manifest, plan_text):
    """Return advisory feature classes in deterministic REGISTRY order."""
    haystack = _signal_haystack(manifest, plan_text)
    return [
        class_name
        for class_name, config in REGISTRY.items()
        if any(_contains_signal(haystack, signal) for signal in config["signals"])
    ]


def _normalise_validator_result(result):
    if isinstance(result, tuple) and len(result) == 2:
        failures, notes = result
        return list(failures or []), list(notes or [])
    return list(result or []), []


def validate_feature_classification(
    manifest, plan_text, *, ac_ids, open_question_ids
):
    """Return ``(failures, notes)`` for declared or advisory classification."""
    if not isinstance(manifest, dict):
        return ["manifest must be an object"], []

    detected = classify(manifest, plan_text)
    block = manifest.get("feature_classification")
    if block is None:
        if detected:
            return [], [
                "REVIEW feature-classification: detected class(es) "
                + ", ".join(detected)
                + "; declare feature_classification and its required dimensions"
            ]
        return [], []
    if not isinstance(block, dict):
        return ["feature_classification must be an object"], []

    failures = []
    notes = []
    if block.get("schema_version") != SCHEMA_VERSION:
        failures.append(f"feature_classification.schema_version must be {SCHEMA_VERSION}")

    classes = block.get("classes")
    if not isinstance(classes, list) or not classes:
        return failures + ["feature_classification.classes must be a non-empty list"], notes

    declared = []
    for index, value in enumerate(classes):
        class_name = str(value).strip()
        if class_name not in REGISTRY:
            failures.append(
                f"feature_classification.classes[{index}] is unknown: {class_name!r}"
            )
            continue
        if class_name in declared:
            failures.append(f"feature_classification.classes duplicates {class_name!r}")
            continue
        declared.append(class_name)

    undeclared_detected = [
        class_name for class_name in detected if class_name not in declared
    ]
    if undeclared_detected:
        notes.append(
            "REVIEW feature-classification: detected class(es) "
            + ", ".join(undeclared_detected)
            + "; declare feature_classification and its required dimensions"
        )

    if not str(block.get("rationale", "")).strip():
        failures.append("feature_classification.rationale must be non-empty")
    evidence = block.get("evidence")
    if not isinstance(evidence, list) or not evidence or not all(
        isinstance(item, str) and item.strip() for item in evidence
    ):
        failures.append(
            "feature_classification.evidence must be a non-empty list of grounded references"
        )

    required_dimensions = []
    for class_name in declared:
        for dimension in REGISTRY[class_name]["required_dimensions"]:
            if dimension not in required_dimensions:
                required_dimensions.append(dimension)

    known_ac_ids = set(ac_ids or [])
    known_oq_ids = set(open_question_ids or [])
    for dimension in required_dimensions:
        dimension_block = manifest.get(dimension)
        if not isinstance(dimension_block, dict):
            failures.append(
                f"declared class requires manifest block {dimension!r}"
            )
            continue
        validator = DIMENSION_VALIDATORS.get(dimension)
        if validator is None:
            failures.append(f"no validator is registered for dimension {dimension!r}")
            continue
        result = validator(
            dimension_block,
            ac_ids=known_ac_ids,
            open_question_ids=known_oq_ids,
            plan_text=plan_text,
        )
        dimension_failures, dimension_notes = _normalise_validator_result(result)
        failures.extend(f"{dimension}: {problem}" for problem in dimension_failures)
        notes.extend(f"{dimension}: {note}" for note in dimension_notes)

    if not failures:
        notes.append(
            "feature classes validated: " + ", ".join(declared)
        )
    return failures, notes
