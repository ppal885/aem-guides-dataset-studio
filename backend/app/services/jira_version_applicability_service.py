"""Deterministic release applicability for historical Jira evidence.

Version overlap is a ranking signal only. Historical evidence is never allowed to
define current-ticket behaviour merely because a release number matches.
"""

from __future__ import annotations

import re
from typing import Any, Iterable


_VERSION_NUMBER_RE = re.compile(r"\d+(?:[._-]\d+)*", re.I)


def _values(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        values: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                value = item.get("name") or item.get("value") or ""
            else:
                value = item
            text = str(value or "").strip()
            if text:
                values.append(text)
        return values
    text = str(raw or "").strip()
    return [text] if text else []


def canonical_version(value: Any) -> str:
    """Normalize formatting without guessing a product channel or release family."""
    text = str(value or "").strip().casefold()
    if not text:
        return ""
    text = re.sub(r"\b(?:adobe\s+)?aem\s+guides\b", "", text)
    text = re.sub(r"\bguides\b", "", text)
    text = re.sub(r"\bversion\b|\bver\b", "", text)
    text = text.replace("_", "-")
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9.-]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-.")


def _canonical_versions(values: Iterable[Any]) -> list[str]:
    return list(
        dict.fromkeys(
            version
            for version in (canonical_version(value) for value in values)
            if version
        )
    )


def _numeric_tuple(value: str) -> tuple[int, ...] | None:
    match = _VERSION_NUMBER_RE.search(value)
    if not match:
        return None
    try:
        return tuple(int(part) for part in re.split(r"[._-]", match.group(0)))
    except ValueError:
        return None


def _relative_age(current: list[str], historical: list[str]) -> str:
    current_numbers = [value for value in (_numeric_tuple(item) for item in current) if value]
    historical_numbers = [value for value in (_numeric_tuple(item) for item in historical) if value]
    if not current_numbers or not historical_numbers:
        return "unknown"
    current_max = max(current_numbers)
    historical_max = max(historical_numbers)
    if historical_max < current_max:
        return "historical_older"
    if historical_max > current_max:
        return "historical_newer"
    return "same_numeric_release"


def classify_version_applicability(
    *,
    current_affected_versions: Any = None,
    current_fix_versions: Any = None,
    historical_affected_versions: Any = None,
    historical_fix_versions: Any = None,
) -> dict[str, Any]:
    """Return a fail-soft version contract used only for ranking and QA scope."""
    current_affected = _canonical_versions(_values(current_affected_versions))
    current_fix = _canonical_versions(_values(current_fix_versions))
    historical_affected = _canonical_versions(_values(historical_affected_versions))
    historical_fix = _canonical_versions(_values(historical_fix_versions))
    current = list(dict.fromkeys([*current_affected, *current_fix]))
    historical = list(dict.fromkeys([*historical_affected, *historical_fix]))
    shared = sorted(set(current) & set(historical))

    if shared:
        classification = "same_release"
        reason = "Current and historical Jira evidence share an explicit normalized release value."
        ranking_multiplier = 1.08
    elif current and historical:
        classification = "different_release"
        reason = (
            "Both tickets provide release values, but none overlap exactly; retain the ticket "
            "as a regression signal and revalidate behaviour on the current release."
        )
        ranking_multiplier = 0.9
    else:
        classification = "unknown"
        reason = (
            "One or both tickets lack sufficient release metadata; version applicability cannot "
            "be established from indexed history."
        )
        ranking_multiplier = 0.97

    return {
        "schema_version": "jira-version-applicability-v1",
        "classification": classification,
        "current": {
            "affected_versions": current_affected,
            "fix_versions": current_fix,
            "all_versions": current,
        },
        "historical": {
            "affected_versions": historical_affected,
            "fix_versions": historical_fix,
            "all_versions": historical,
        },
        "shared_versions": shared,
        "relative_age": _relative_age(current, historical),
        "ranking_multiplier": ranking_multiplier,
        "hard_filter_allowed": False,
        "usable_as_current_expected_behavior": False,
        "requires_current_ticket_validation": True,
        "reason": reason,
    }
