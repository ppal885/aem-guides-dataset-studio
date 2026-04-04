"""Attribute catalog: look up DITA attribute specs from seed for test data generation.

Given an attribute name (e.g. "format"), returns valid values, supported elements,
combination attributes, and builds test scenario descriptions.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple

SEED_PATH = Path(__file__).resolve().parent.parent / "storage" / "dita_spec_seed.json"


class AttributeSpec(NamedTuple):
    """Resolved attribute specification from the seed."""

    attribute_name: str
    all_valid_values: list[str]
    supported_elements: list[str]
    combination_attributes: list[str]
    default_scenarios: list[str]
    text_content: str  # raw spec text for RAG injection


@lru_cache(maxsize=1)
def _load_seed() -> list[dict[str, Any]]:
    try:
        with open(SEED_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def _find_attribute_entry(attr_name: str) -> dict[str, Any] | None:
    """Find seed entry for an attribute (matches element_name like 'format_attribute')."""
    seed = _load_seed()
    # Try exact match first, then suffix match
    candidates = [
        f"{attr_name}_attribute",
        f"{attr_name.replace('-', '_')}_attribute",
        attr_name,
    ]
    for entry in seed:
        ename = entry.get("element_name", "")
        if ename in candidates:
            return entry
    # Fallback: partial match
    for entry in seed:
        ename = entry.get("element_name", "")
        if attr_name.replace("-", "_") in ename and entry.get("content_type") == "attribute":
            return entry
    return None


def get_attribute_spec(attr_name: str) -> AttributeSpec | None:
    """Look up attribute from dita_spec_seed.json, return full spec."""
    entry = _find_attribute_entry(attr_name)
    if entry is None:
        return None

    tdc = entry.get("test_data_coverage") or {}
    return AttributeSpec(
        attribute_name=attr_name,
        all_valid_values=tdc.get("all_values", []),
        supported_elements=tdc.get("supported_elements", []),
        combination_attributes=tdc.get("combination_attributes", []),
        default_scenarios=tdc.get("default_scenarios", []),
        text_content=entry.get("text_content", ""),
    )


def build_test_scenarios(
    attr_name: str,
    elements: list[str],
    mentioned_values: list[str],
) -> list[str]:
    """Generate test scenario descriptions for all value×element combinations."""
    spec = get_attribute_spec(attr_name)
    if spec is None:
        return [f"{attr_name}={v} on relevant elements" for v in mentioned_values]

    scenarios: list[str] = []
    target_elements = elements or spec.supported_elements[:4]
    all_values = spec.all_valid_values or mentioned_values

    # Generate scenarios for each value on primary element
    primary_elem = target_elements[0] if target_elements else "topicref"
    for val in all_values:
        scenarios.append(f"{primary_elem} with {attr_name}={val}")

    # Default/omitted case
    for ds in spec.default_scenarios:
        scenarios.append(ds)

    # Cross-element coverage for mentioned values
    for elem in target_elements[1:]:
        for val in mentioned_values or all_values[:3]:
            scenarios.append(f"{elem} with {attr_name}={val}")

    # Combination scenarios
    for combo_attr in spec.combination_attributes[:3]:
        scenarios.append(
            f"{primary_elem} with {attr_name}={all_values[0] if all_values else 'value'} + {combo_attr}"
        )

    return scenarios
