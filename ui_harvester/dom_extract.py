"""Pure DOM/accessibility -> structured UI extraction.

These functions take plain dicts (an accessibility node shape produced by
Playwright's `page.accessibility.snapshot()` or a DOM `evaluate` result) and
return structured UI facts. They are intentionally browser-free so they are unit
testable and so ~90%+ of extraction is deterministic with NO Vision calls.

capability != control type: a control's product CAPABILITY is derived from its
accessible name; the CONTROL_PATTERN is derived from its role. We keep them
separate (HOW vs WHAT), and we never infer shared implementation from a shared
control pattern - that stays POTENTIAL_SHARED_COMPONENT until code verifies it.
"""

import re

from . import taxonomy

_CAP_SLUG_RE = re.compile(r"[^a-z0-9]+")


def capability_slug(name):
    """Map an accessible name to a stable CAPABILITY slug (WHAT product function).
    e.g. 'Create Baseline' -> 'CREATE_BASELINE'. Empty for unnamed controls."""
    slug = _CAP_SLUG_RE.sub("_", (name or "").strip().lower()).strip("_")
    return slug.upper()[:60]


def classify_node(node):
    """One accessibility node -> {control_pattern, capability, name, disabled,
    states[], visual_primitive?}. Deterministic, no Vision.

    node is a dict with any of: role, name, disabled, and raw aria-* attributes
    under an 'attributes' dict (aria-expanded/selected/checked/pressed/disabled).
    """
    attrs = node.get("attributes") or {}
    role = node.get("role", "")
    has_expanded = "aria-expanded" in attrs or node.get("expanded") is not None
    control = taxonomy.map_role_to_control(role, has_aria_expanded=has_expanded)

    states = []
    # Playwright surfaces some aria state as top-level keys AND some as attributes.
    if node.get("expanded") is True or attrs.get("aria-expanded") == "true":
        states.append("EXPANDED")
    elif node.get("expanded") is False or attrs.get("aria-expanded") == "false":
        states.append("COLLAPSED")
    if node.get("selected") is True or attrs.get("aria-selected") == "true":
        states.append("SELECTED")
    if node.get("checked") is True or attrs.get("aria-checked") == "true":
        states.append("CHECKED")
    disabled = bool(node.get("disabled")) or attrs.get("aria-disabled") == "true"
    if disabled:
        states.append("DISABLED")

    out = {
        "control_pattern": control,
        "capability": capability_slug(node.get("name", "")),
        "name": (node.get("name") or "").strip(),
        "disabled": disabled,
        "states": states,
    }
    # A chevron glyph is retained only as a visual hint, never as primary identity.
    if control == "DISCLOSURE_TOGGLE":
        out["visual_primitive"] = "CHEVRON"
    return out


def extract_capabilities(nodes):
    """Split a list of accessibility nodes into visible vs disabled capability
    slugs (deduped, sorted). Unnamed controls are skipped for capability purposes."""
    visible, disabled = set(), set()
    for node in nodes or []:
        c = classify_node(node)
        if not c["capability"]:
            continue
        (disabled if c["disabled"] else visible).add(c["capability"])
    return sorted(visible), sorted(disabled)


def control_pattern_histogram(nodes):
    """Count control patterns present - useful for surface fingerprints."""
    hist = {}
    for node in nodes or []:
        p = classify_node(node)["control_pattern"]
        hist[p] = hist.get(p, 0) + 1
    return hist


def shared_component_candidate(node_a, node_b):
    """Two visually/structurally similar controls -> a CANDIDATE only. We never
    assert shared implementation from the DOM; code must verify."""
    a, b = classify_node(node_a), classify_node(node_b)
    if a["control_pattern"] == b["control_pattern"] and a["capability"] == b["capability"]:
        return "POTENTIAL_SHARED_COMPONENT"
    if a["control_pattern"] == b["control_pattern"]:
        return "SAME_UI_PATTERN_CANDIDATE"
    return "UNRELATED"
