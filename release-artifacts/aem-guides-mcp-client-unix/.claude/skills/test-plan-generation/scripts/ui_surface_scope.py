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
_CODE_FILE_LINE_RE = re.compile(
    r"^(?:[A-Za-z]:)?[\\/]?(?:[^:\\/\r\n]+[\\/])*"
    r"[^:\\/\r\n]+\.(?:"
    r"c|cc|cfg|conf|config|cpp|css|csv|go|groovy|h|hpp|html|ini|java|js|"
    r"json|jsx|jsp|kt|kts|less|php|properties|py|rb|rs|scss|sh|sql|ts|"
    r"tsx|xml|yaml|yml"
    r"):[1-9]\d*(?:-[1-9]\d*)?$",
    re.I,
)
_CHUNK_ID_RE = re.compile(r"^chunk_id:[A-Za-z0-9][A-Za-z0-9._:-]*$")


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


def _valid_edge_source(value) -> bool:
    text = str(value).strip() if isinstance(value, str) else ""
    return bool(_CODE_FILE_LINE_RE.fullmatch(text) or _CHUNK_ID_RE.fullmatch(text))


def _normalise_surface(value) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))


def _disposition_signature(entry):
    if not isinstance(entry, dict):
        return None
    disposition = entry.get("disposition")
    if disposition == "COVERED_BY_AC":
        return disposition, str(entry.get("ac_ref", "")).strip()
    if disposition == "OPEN_QUESTION":
        return disposition, str(entry.get("open_question_ref", "")).strip()
    if disposition == "OUT_OF_SCOPE":
        return disposition, ""
    return None


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


def validate_consumer_edges(
    block,
    edges,
    *,
    ac_ids=None,
    open_question_ids=None,
    plan_text="",
    catalog_path=None,
):
    """Cross-check declared UI surfaces against grounded CONSUMER edges.

    Base block and catalog validation remains unchanged. This umbrella helper
    additionally proves that every declared render surface is represented by a
    CONSUMER edge with the same disposition and AC/Open Question reference.
    It can validate only the direct edges supplied by traversal; an indirect or
    undiscovered UI consumer cannot be inferred here.
    """
    problems, notes = validate_ui_surface_scope(
        block,
        ac_ids=ac_ids,
        open_question_ids=open_question_ids,
        plan_text=plan_text,
        catalog_path=catalog_path,
    )
    problems = list(problems)
    notes = list(notes)
    if not isinstance(block, dict):
        return problems, notes
    surfaces = block.get("render_surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        return problems, notes
    if not isinstance(edges, list):
        problems.append("relationship edges must be a list for UI CONSUMER validation")
        return problems, notes

    consumers = []
    for edge_index, edge in enumerate(edges):
        if isinstance(edge, dict) and edge.get("relation_type") == "CONSUMER":
            consumers.append((edge_index, edge))

    for surface_index, surface_entry in enumerate(surfaces):
        if not isinstance(surface_entry, dict):
            continue
        surface = str(surface_entry.get("surface", "")).strip()
        normalized = _normalise_surface(surface)
        if not normalized:
            continue
        matches = [
            (edge_index, edge)
            for edge_index, edge in consumers
            if _normalise_surface(edge.get("neighbor", "")) == normalized
        ]
        surface_tag = f"ui_surface_scope.render_surfaces[{surface_index}]"
        if not matches:
            problems.append(
                f"{surface_tag} surface {surface!r} has no matching CONSUMER edge"
            )
            continue

        expected_signature = _disposition_signature(surface_entry)
        for edge_index, edge in matches:
            edge_tag = f"construct_relationships.edges[{edge_index}]"
            if not _valid_edge_source(edge.get("source")):
                problems.append(
                    f"{edge_tag}.source for UI surface {surface!r} must be a code "
                    "file:line or chunk_id:<id> citation"
                )
            actual_signature = _disposition_signature(edge)
            if actual_signature != expected_signature:
                problems.append(
                    f"{edge_tag} disposition/reference does not match {surface_tag} "
                    f"for surface {surface!r}"
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


def _run_self_tests():
    catalog, error = _load_catalog()
    assert not error
    construct_type = next(iter(catalog))
    surfaces = catalog[construct_type]
    last_surface = surfaces[-1]
    block = {
        "schema_version": SCHEMA_VERSION,
        "construct_type": construct_type,
        "render_surfaces": [
            {
                "surface": surface,
                "disposition": "COVERED_BY_AC",
                "ac_ref": "AC-01",
            }
            for surface in surfaces
        ],
        "config_scope": {
            "scope": "USER",
            "disposition": "COVERED_BY_AC",
            "ac_ref": "AC-01",
        },
        "upgrade_persistence": {
            "disposition": "COVERED_BY_AC",
            "ac_ref": "AC-01",
        },
        "sibling_regression": {
            "disposition": "OUT_OF_SCOPE",
            "reason": "No sibling construct is affected by this isolated fixture.",
        },
        "surfaces_grounding": ["C:/repo/rendering.ts:42"],
    }
    edges = [
        {
            "relation_type": "CONSUMER",
            "neighbor": surface,
            "source": (
                "chunk_id:ui_surface_catalog_tail"
                if surface == last_surface
                else "C:/repo/rendering.ts:42"
            ),
            "disposition": "COVERED_BY_AC",
            "ac_ref": "AC-01",
        }
        for surface in surfaces
    ]
    failures, _ = validate_consumer_edges(
        block, edges, ac_ids={"AC-01"}, open_question_ids=set()
    )
    assert failures == []

    failures, _ = validate_consumer_edges(
        block, edges[:-1], ac_ids={"AC-01"}, open_question_ids=set()
    )
    assert any(
        last_surface in problem and "no matching CONSUMER" in problem
        for problem in failures
    )

    invalid_source = [dict(edge) for edge in edges]
    invalid_source[0]["source"] = "Jira: remembered UI"
    failures, _ = validate_consumer_edges(
        block, invalid_source, ac_ids={"AC-01"}, open_question_ids=set()
    )
    assert any("must be a code file:line or chunk_id:<id>" in problem for problem in failures)

    mismatched = [dict(edge) for edge in edges]
    mismatched[0]["ac_ref"] = "AC-02"
    failures, _ = validate_consumer_edges(
        block, mismatched, ac_ids={"AC-01", "AC-02"}, open_question_ids=set()
    )
    assert any("disposition/reference does not match" in problem for problem in failures)


if __name__ == "__main__":
    _run_self_tests()
    print("UI SURFACE SCOPE SELF-TESTS PASSED")
