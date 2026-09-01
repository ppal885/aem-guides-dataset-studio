"""Fail-closed, exactly-once completeness over every material candidate."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping


def disposition_sources(dispositions):
    sources = []
    for record in dispositions or []:
        if not isinstance(record, Mapping):
            continue
        refs = record.get("source_refs")
        if isinstance(refs, list):
            sources.extend(str(ref) for ref in refs if str(ref).strip())
        elif record.get("source_ref"):
            sources.append(str(record.get("source_ref")))
    return sources


def validate_behavioral_completeness(
    manifest,
    *,
    material_item_ids,
    required_blocks=None,
):
    problems = []
    if not isinstance(manifest, Mapping):
        return ["manifest must be an object"]
    for block_name in required_blocks or []:
        if not isinstance(manifest.get(block_name), Mapping):
            problems.append(f"behavioral completeness requires block {block_name!r}")
    dispositions = manifest.get("dispositions")
    if not isinstance(dispositions, list):
        return problems + ["dispositions must be a list for behavioral completeness"]
    counts = Counter(disposition_sources(dispositions))
    for item_id in sorted(set(material_item_ids or [])):
        if counts[item_id] == 0:
            problems.append(f"material candidate {item_id} has no coverage disposition")
        elif counts[item_id] > 1:
            problems.append(f"material candidate {item_id} is dispositioned more than once")
    known = set(material_item_ids or [])
    for ref in counts:
        if ref not in known:
            problems.append(f"coverage disposition references unknown material candidate {ref}")

    # Every promoted AC must point back to a disposition and a material candidate.
    disposition_ids = {
        str(item.get("finding_id")) for item in dispositions
        if isinstance(item, Mapping) and item.get("finding_id")
    }
    promotion_block = manifest.get("acceptance_promotions")
    promotion_records = (
        promotion_block.get("records", [])
        if isinstance(promotion_block, Mapping)
        else []
    )
    for record in (promotion_records or []):
        if not isinstance(record, Mapping):
            continue
        if record.get("decision") in ("PROMOTED_CONFIRMED", "PROMOTED_PROPOSED"):
            if record.get("disposition_ref") not in disposition_ids:
                problems.append(
                    f"promotion {record.get('promotion_id', '?')} does not reference a canonical coverage disposition"
                )
    return problems
