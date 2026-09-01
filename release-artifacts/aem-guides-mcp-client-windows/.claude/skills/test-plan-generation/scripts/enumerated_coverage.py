"""Validate complete disposition of reporter-enumerated requirements.

The manifest block is deliberately versioned and fail-closed. A numbered or
bulleted issue list is a source contract: every item must be represented in order
and mapped to a real AC, a real Open Question, or an explicit out-of-scope reason.
"""

from __future__ import annotations

import re


SCHEMA_VERSION = "aem-guides-enumerated-requirements-v1"
DISPOSITIONS = ("COVERED_BY_AC", "OPEN_QUESTION", "OUT_OF_SCOPE")
_NUMBERED_RE = re.compile(r"(?m)^\s*\d{1,3}[.)]\s+\S")
_HASH_ITEM_RE = re.compile(r"(?m)^\s*#\s+\S")
_BULLET_RE = re.compile(r"(?m)^\s*[-*]\s+\S")
_THRESHOLD = 3


def is_present(manifest: dict) -> bool:
    return isinstance(manifest, dict) and isinstance(
        manifest.get("enumerated_requirements"), dict
    )


def _issue_text(manifest: dict) -> str:
    issue = manifest.get("issue") if isinstance(manifest, dict) else None
    if isinstance(issue, dict):
        return "\n".join(
            str(issue.get(key, "")) for key in ("summary", "description", "title")
        )
    return str(issue or "")


def likely_enumerated(manifest: dict) -> int:
    """Return the strongest confidently detected list count, otherwise zero."""
    text = _issue_text(manifest)
    count = max(
        len(_NUMBERED_RE.findall(text)),
        len(_HASH_ITEM_RE.findall(text)),
        len(_BULLET_RE.findall(text)),
    )
    return count if count >= _THRESHOLD else 0


def _refs(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def validate_enumerated_requirements(
    block: object,
    *,
    ac_ids: object = None,
    open_question_ids: object = None,
    detected_count: int = 0,
) -> list[str]:
    known_ac_ids = None if ac_ids is None else set(ac_ids)
    known_oq_ids = None if open_question_ids is None else set(open_question_ids)
    if not isinstance(block, dict):
        return ["enumerated_requirements must be a versioned JSON object"]

    problems: list[str] = []
    if block.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"enumerated_requirements.schema_version must be {SCHEMA_VERSION}")
    active = block.get("active")
    if not isinstance(active, bool):
        problems.append("enumerated_requirements.active must be true or false")
        return problems
    if not active:
        if detected_count:
            problems.append(
                "enumerated_requirements cannot be inactive when the issue contains "
                f"a detected list of {detected_count} items"
            )
        if not str(block.get("reason", "")).strip():
            problems.append("inactive enumerated_requirements requires a non-empty reason")
        return problems

    if not str(block.get("source_ref", "")).strip():
        problems.append("active enumerated_requirements requires source_ref")
    declared_count = block.get("source_item_count")
    if not isinstance(declared_count, int) or isinstance(declared_count, bool) or declared_count < 1:
        problems.append("source_item_count must be a positive integer")
    if block.get("source_complete") is not True:
        problems.append("source_complete must be true after transcribing the complete source list")
    if detected_count and declared_count != detected_count:
        problems.append(
            f"source_item_count {declared_count!r} does not match detected source count {detected_count}"
        )

    items = block.get("items")
    if not isinstance(items, list) or not items:
        return problems + ["active enumerated_requirements.items must be a non-empty list"]
    if isinstance(declared_count, int) and len(items) != declared_count:
        problems.append(
            f"items contains {len(items)} entries but source_item_count is {declared_count}"
        )

    seen_ids: set[str] = set()
    seen_indices: set[int] = set()
    ac_to_items: dict[str, list[str]] = {}
    for index, entry in enumerate(items):
        tag = f"enumerated_requirements.items[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{tag} must be an object")
            continue
        item_id = str(entry.get("id", "")).strip()
        if not re.fullmatch(r"REQ-\d{2}", item_id):
            problems.append(f"{tag}.id must use stable REQ-## form")
        elif item_id in seen_ids:
            problems.append(f"{tag} duplicates id {item_id}")
        seen_ids.add(item_id)
        source_index = entry.get("source_index")
        if not isinstance(source_index, int) or isinstance(source_index, bool) or source_index < 1:
            problems.append(f"{tag}.source_index must be a positive integer")
        elif source_index in seen_indices:
            problems.append(f"{tag} duplicates source_index {source_index}")
        seen_indices.add(source_index)
        if not str(entry.get("text", "")).strip():
            problems.append(f"{tag} is missing the source item text")

        disposition = entry.get("disposition")
        if disposition not in DISPOSITIONS:
            problems.append(f"{tag}.disposition must be one of {DISPOSITIONS}")
            continue
        if disposition == "COVERED_BY_AC":
            refs = _refs(entry.get("ac_refs"))
            if not refs:
                problems.append(f"{tag}: COVERED_BY_AC requires non-empty ac_refs")
            for ref in refs:
                if known_ac_ids is not None and ref not in known_ac_ids:
                    problems.append(f"{tag}: ac_ref {ref!r} is not an AC defined in the plan")
                ac_to_items.setdefault(ref, []).append(item_id or tag)
        elif disposition == "OPEN_QUESTION":
            ref = str(entry.get("open_question_ref", "")).strip()
            if not ref:
                problems.append(f"{tag}: OPEN_QUESTION requires open_question_ref")
            elif known_oq_ids is not None and ref not in known_oq_ids:
                problems.append(f"{tag}: open_question_ref {ref!r} is not declared")
        elif not str(entry.get("reason", "")).strip():
            problems.append(f"{tag}: OUT_OF_SCOPE requires a non-empty reason")

    if isinstance(declared_count, int) and declared_count > 0:
        expected = set(range(1, declared_count + 1))
        if seen_indices != expected:
            problems.append("source_index values must be unique and contiguous from 1 to source_item_count")

    justifications = block.get("shared_contract_justifications", {})
    if not isinstance(justifications, dict):
        problems.append("shared_contract_justifications must be an object")
        justifications = {}
    for ac_ref, item_ids in ac_to_items.items():
        if len(item_ids) > 1 and not str(justifications.get(ac_ref, "")).strip():
            problems.append(
                f"{ac_ref} covers independently pass/fail items {', '.join(item_ids)}; "
                "add a shared_contract_justification or split the AC mapping"
            )
    return problems


def overloaded_ac_refs(block: object, *, threshold: int = 2) -> dict[str, list[str]]:
    if not isinstance(block, dict) or not isinstance(block.get("items"), list):
        return {}
    by_ref: dict[str, list[str]] = {}
    for entry in block["items"]:
        if not isinstance(entry, dict) or entry.get("disposition") != "COVERED_BY_AC":
            continue
        for ref in _refs(entry.get("ac_refs")):
            by_ref.setdefault(ref, []).append(str(entry.get("id", "?")))
    return {ref: ids for ref, ids in by_ref.items() if len(ids) >= threshold}


def summarize(manifest: dict, plan_text: str = "") -> str:
    lines = [
        "EnumeratedRequirementCoverage: "
        f"present={is_present(manifest)} likely_enumerated={likely_enumerated(manifest)}"
    ]
    if is_present(manifest):
        ac_ids = set(re.findall(r"AC-\d{2}", plan_text or ""))
        for problem in validate_enumerated_requirements(
            manifest["enumerated_requirements"],
            ac_ids=ac_ids,
            detected_count=likely_enumerated(manifest),
        ):
            lines.append(f"  FAIL {problem}")
    return "\n".join(lines)
