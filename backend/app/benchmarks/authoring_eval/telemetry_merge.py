"""
Optional merge of product analytics into benchmark reports.

``regeneration_rate`` and ``edit_after_generation_rate`` are not observable from a single
``generate_topic_from_request`` call. In production, emit structured events (for example
``chat_authoring_regeneration``, ``chat_authoring_edit_after_generate``) with ``session_id``
and ``pipeline_run_id``, then join offline:

Example consumer (pseudo-code)::

    events = load_jsonl(\"analytics/authoring_events.jsonl\")
    regen_rate = mean(e[\"regenerated\"] for e in events if e[\"feature\"] == \"screenshot_dita\")

This module is a placeholder hook so teams can plug warehouse exports without changing core scoring.
"""

from __future__ import annotations

from typing import Any


def apply_external_rates(aggregates: dict[str, Any], *, regeneration_rate: float | None, edit_rate: float | None) -> dict[str, Any]:
    """Return a shallow copy of aggregates with optional telemetry fields filled."""
    out = dict(aggregates)
    if regeneration_rate is not None:
        out["regeneration_rate"] = regeneration_rate
    if edit_rate is not None:
        out["edit_after_generation_rate"] = edit_rate
    return out
