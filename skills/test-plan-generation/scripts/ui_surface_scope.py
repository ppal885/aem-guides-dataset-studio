"""Construct-scoped UI surface coverage backed by a small growing catalog.

Feedback-loop rule: when review discovers a missed render surface for a known
construct, add it with ``add_catalog_surface``. That surface can no longer be
silently missed by the next ticket for the same construct. The catalog does not
claim to enumerate every product surface; it reduces repeat misses and forces a
grounded, per-construct enumeration rather than an impossible global screen list.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path


SCHEMA_VERSION = "aem-guides-ui-surface-scope-v1"
DISPOSITIONS = ("COVERED_BY_AC", "OPEN_QUESTION", "OUT_OF_SCOPE")
CONFIG_SCOPES = ("USER", "GLOBAL", "FOLDER", "OTHER")
CATALOG_PATH = Path(__file__).with_name("data") / "ui_surface_catalog.json"
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _load_catalog(path=None):
    catalog_path = Path(path) if path is not None else CATALOG_PATH
    try:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"could not read UI surface catalog {catalog_path}: {exc}"
    if not isinstance(data, dict) or not all(
        isinstance(key, str)
        and _SLUG_RE.fullmatch(key)
        and isinstance(value, list)
        and all(isinstance(item, str) and item.strip() for item in value)
        for key, value in data.items()
    ):
        return None, "UI surface catalog must map construct slugs to surface-name lists"
    return data, ""


def _valid_grounding(value) -> bool:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list) or not values:
        return False
    cleaned = [item.strip() for item in values if isinstance(item, str) and item.strip()]
    if len(cleaned) != len(values):
        return False
    return any(
        re.search(r":\d+(?:-\d+)?(?:\D|$)", item)
        or re.match(r"(?i)^RAG:", item)
        for item in cleaned
    )


def _validate_disposition(entry, tag, *, ac_ids, open_question_ids, allow_out=True):
    problems = []
    disposition = entry.get("disposition") if isinstance(entry, dict) else None
    allowed = DISPOSITIONS if allow_out else DISPOSITIONS[:2]
    if disposition not in allowed:
        return [f"{tag}.disposition must be one of {allowed}"]
    if disposition == "COVERED_BY_AC":
        ref = str(entry.get("ac_ref", "")).strip()
        if not ref or (ac_ids is not None and ref not in ac_ids):
            problems.append(f"{tag}: COVERED_BY_AC requires a valid ac_ref")
    elif disposition == "OPEN_QUESTION":
        ref = str(entry.get("open_question_ref", "")).strip()
        if not ref or (open_question_ids is not None and ref not in open_question_ids):
            problems.append(f"{tag}: OPEN_QUESTION requires a valid open_question_ref")
    elif not str(entry.get("reason", "")).strip():
        problems.append(f"{tag}: OUT_OF_SCOPE requires a non-empty reason")
    return problems


def validate_ui_surface_scope(
    block,
    *,
    ac_ids=None,
    open_question_ids=None,
    plan_text="",
    catalog_path=None,
):
    """Return ``(failures, notes)`` for a ui_surface_scope block."""
    del plan_text
    known_ac_ids = None if ac_ids is None else set(ac_ids)
    known_oq_ids = None if open_question_ids is None else set(open_question_ids)
    if not isinstance(block, dict):
        return ["ui_surface_scope must be an object"], []

    problems = []
    notes = []
    if block.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"ui_surface_scope.schema_version must be {SCHEMA_VERSION}")

    construct_type = str(block.get("construct_type", "")).strip()
    if not _SLUG_RE.fullmatch(construct_type):
        problems.append("ui_surface_scope.construct_type must be a stable lowercase slug")

    render_surfaces = block.get("render_surfaces")
    if not isinstance(render_surfaces, list) or not render_surfaces:
        return problems + ["ui_surface_scope.render_surfaces must be a non-empty list"], notes

    declared = {}
    for index, entry in enumerate(render_surfaces):
        tag = f"ui_surface_scope.render_surfaces[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{tag} must be an object")
            continue
        surface = str(entry.get("surface", "")).strip()
        if not surface:
            problems.append(f"{tag}.surface must be non-empty")
            continue
        normalized = surface.casefold()
        if normalized in declared:
            problems.append(f"{tag} duplicates surface {surface!r}")
        declared[normalized] = surface
        problems.extend(
            _validate_disposition(
                entry,
                tag,
                ac_ids=known_ac_ids,
                open_question_ids=known_oq_ids,
            )
        )

    config_scope = block.get("config_scope")
    if not isinstance(config_scope, dict):
        problems.append("ui_surface_scope.config_scope must be an object")
    else:
        scope = config_scope.get("scope")
        if scope not in CONFIG_SCOPES:
            problems.append(f"config_scope.scope must be one of {CONFIG_SCOPES}")
        if scope == "OTHER" and not str(config_scope.get("other_scope", "")).strip():
            problems.append("config_scope OTHER requires other_scope")
        problems.extend(
            _validate_disposition(
                config_scope,
                "config_scope",
                ac_ids=known_ac_ids,
                open_question_ids=known_oq_ids,
                allow_out=False,
            )
        )

    upgrade = block.get("upgrade_persistence")
    if not isinstance(upgrade, dict):
        problems.append("ui_surface_scope.upgrade_persistence must be an object")
    else:
        problems.extend(
            _validate_disposition(
                upgrade,
                "upgrade_persistence",
                ac_ids=known_ac_ids,
                open_question_ids=known_oq_ids,
                allow_out=False,
            )
        )

    sibling = block.get("sibling_regression")
    if not isinstance(sibling, dict):
        problems.append("ui_surface_scope.sibling_regression must be an object")
    elif sibling.get("disposition") == "COVERED_BY_AC":
        ref = str(sibling.get("ac_ref", "")).strip()
        if not ref or (known_ac_ids is not None and ref not in known_ac_ids):
            problems.append("sibling_regression COVERED_BY_AC requires a valid ac_ref")
        sibling_construct = str(sibling.get("sibling_construct", "")).strip()
        if not _SLUG_RE.fullmatch(sibling_construct):
            problems.append("sibling_regression requires a stable sibling_construct slug")
    elif sibling.get("disposition") == "OUT_OF_SCOPE":
        if not str(sibling.get("reason", "")).strip():
            problems.append("sibling_regression OUT_OF_SCOPE requires a non-empty reason")
    else:
        problems.append(
            "sibling_regression must be COVERED_BY_AC or explicitly OUT_OF_SCOPE"
        )

    if not _valid_grounding(block.get("surfaces_grounding")):
        problems.append(
            "surfaces_grounding must contain at least one rendering-layer file:line or RAG citation"
        )

    catalog, catalog_error = _load_catalog(catalog_path)
    if catalog_error:
        problems.append(catalog_error)
    elif construct_type and construct_type not in catalog:
        notes.append(
            f"REVIEW ui-surface-scope: construct {construct_type!r} is not in the catalog; "
            "add a grounded catalog entry"
        )
    elif construct_type:
        catalog_surfaces = catalog[construct_type]
        for surface in catalog_surfaces:
            if surface.casefold() not in declared:
                problems.append(
                    f"catalog surface {surface!r} for construct {construct_type!r} is neither "
                    "covered nor dispositioned - add it or justify out-of-scope"
                )
        catalog_names = {surface.casefold() for surface in catalog_surfaces}
        for normalized, surface in declared.items():
            if normalized not in catalog_names:
                notes.append(
                    f"REVIEW ui-surface-scope: declared surface {surface!r} is not yet in the "
                    f"catalog for construct {construct_type!r}; add it when evidence confirms reuse"
                )

    return problems, notes


def add_catalog_surface(construct_type, surface, *, catalog_path=None):
    """Append one normalized-unique surface; return True only when the file changed."""
    slug = str(construct_type).strip()
    name = str(surface).strip()
    if not _SLUG_RE.fullmatch(slug):
        raise ValueError("construct_type must be a stable lowercase slug")
    if not name:
        raise ValueError("surface must be non-empty")
    path = Path(catalog_path) if catalog_path is not None else CATALOG_PATH
    catalog, error = _load_catalog(path)
    if error:
        if path.exists():
            raise ValueError(error)
        catalog = {}
    values = catalog.setdefault(slug, [])
    if name.casefold() in {item.casefold() for item in values}:
        return False
    values.append(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", delete=False, dir=path.parent
    ) as handle:
        handle.write(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n")
        temporary = Path(handle.name)
    temporary.replace(path)
    return True
