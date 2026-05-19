"""Load and validate bundled QA Studio knowledge JSON (playbooks, actions, DOM patterns)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parent.parent / "data" / "qa_studio"


class BundledKnowledgeError(Exception):
    pass


def _read_json(name: str) -> dict[str, Any]:
    path = _DATA / name
    if not path.is_file():
        raise BundledKnowledgeError(f"Missing bundled file: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def load_playbooks_bundle() -> dict[str, Any]:
    data = _read_json("playbooks.json")
    if not isinstance(data.get("playbooks"), list):
        raise BundledKnowledgeError("playbooks.json: missing playbooks array")
    return data


@lru_cache
def load_action_catalog_bundle() -> dict[str, Any]:
    data = _read_json("action_catalog.json")
    if not isinstance(data.get("actions"), list):
        raise BundledKnowledgeError("action_catalog.json: missing actions array")
    return data


@lru_cache
def load_dom_patterns_bundle() -> dict[str, Any]:
    data = _read_json("dom_patterns.json")
    if not isinstance(data.get("patterns"), list):
        raise BundledKnowledgeError("dom_patterns.json: missing patterns array")
    return data


def bundled_counts_and_meta() -> dict[str, Any]:
    """Counts and schema version for dashboard / index admin."""
    pb = load_playbooks_bundle()
    ac = load_action_catalog_bundle()
    dm = load_dom_patterns_bundle()
    return {
        "playbooks": len(pb["playbooks"]),
        "action_catalog": len(ac["actions"]),
        "dom_patterns": len(dm["patterns"]),
        "versions": {
            "playbooks": pb.get("version"),
            "action_catalog": ac.get("version"),
            "dom_patterns": dm.get("version"),
        },
        "bundle_path": str(_DATA),
    }


def validate_bundled_knowledge() -> dict[str, Any]:
    """Validate bundled JSON shape; returns errors/warnings lists (no exceptions on soft issues)."""
    errors: list[str] = []
    warnings: list[str] = []
    try:
        pb = load_playbooks_bundle()
        for i, p in enumerate(pb.get("playbooks", [])):
            if not isinstance(p, dict):
                errors.append(f"playbooks[{i}] is not an object")
                continue
            if not p.get("id"):
                errors.append(f"playbooks[{i}] missing id")
            if not p.get("area"):
                warnings.append(f"playbook {p.get('id')}: missing area")
    except BundledKnowledgeError as e:
        errors.append(str(e))
    try:
        load_action_catalog_bundle()
    except BundledKnowledgeError as e:
        errors.append(str(e))
    try:
        load_dom_patterns_bundle()
    except BundledKnowledgeError as e:
        errors.append(str(e))
    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def list_playbooks() -> list[dict[str, Any]]:
    return list(load_playbooks_bundle().get("playbooks", []))


def search_playbooks(
    *,
    area: str | None = None,
    workflow: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    q = (query or "").lower().strip()
    out: list[dict[str, Any]] = []
    for p in list_playbooks():
        if area and str(p.get("area", "")).lower() != area.lower():
            continue
        if workflow and str(p.get("workflow", "")).lower() != workflow.lower():
            continue
        if q:
            hay = json.dumps(p, ensure_ascii=False).lower()
            if q not in hay:
                continue
        out.append(p)
    return out
