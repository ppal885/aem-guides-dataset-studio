"""Probe-coverage enforcement gate (UACGAP-01).

The miss-probe library (data/miss_probes.json) encodes recurring discovery misses
(output-generation entry points, attribute-value derivation, shared-platform
features, ...). Until now those probes were ADVISORY: the dimension synthesizer
surfaced the raised dimension as a REVIEW note, but nothing FAILED a plan that
ignored it - so the same class of miss could recur ticket after ticket.

This gate closes that loop. When an ACTIVE probe's signal matches the current
evidence (issue text + plan), its implied dimension MUST be dispositioned: either
covered by a clarification dimension of that axis, or explicitly handled in a
manifest `probe_dispositions` block. Otherwise the plan fails.

SHADOW probes stay advisory (never hard-fail). Plans whose evidence matches no
probe are unaffected (backward-compatible).

Generic only. Standard library only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path
from typing import Any


PREFIX = "PROBE COVERAGE GATE:"
DISPOSITION_BLOCK = "probe_dispositions"
VALID_DISPOSITIONS = {"COVERED", "REJECTED", "NOT_APPLICABLE", "DEFERRED_OPEN_QUESTION"}
_PROBE_ID_RE = re.compile(r"\bMP-\d+\b")


def _load_miss_probe_library():
    path = Path(__file__).with_name("miss_probe_library.py")
    spec = importlib.util.spec_from_file_location("miss_probe_library", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _problem(message: str) -> str:
    return f"{PREFIX} {message}"


def _issue_text(manifest: dict[str, Any]) -> str:
    issue = manifest.get("issue") if isinstance(manifest, dict) else None
    if not isinstance(issue, dict):
        return ""
    parts = [str(issue.get("summary", "")), str(issue.get("description", ""))]
    labels = issue.get("labels")
    if isinstance(labels, list):
        parts.append(" ".join(str(x) for x in labels))
    comps = issue.get("components")
    if isinstance(comps, list):
        parts.append(" ".join(str(x) for x in comps))
    return "\n".join(parts)


def _evidence_pairs(plan_body: str, manifest: dict[str, Any]) -> list[tuple[str, str]]:
    return [("issue", _issue_text(manifest)), ("plan", plan_body or "")]


def activated_probes(plan_body: str = "", manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return the ACTIVE probes whose signal matches the current evidence.

    Each item: {probe_id, axis, candidate, shadow}. SHADOW probes are included with
    shadow=True so callers can report them without hard-failing.
    """
    manifest_data = manifest if isinstance(manifest, dict) else {}
    try:
        mpl = _load_miss_probe_library()
        candidates = mpl.candidates_for(_evidence_pairs(plan_body, manifest_data))
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in candidates:
        pid = str(c.get("probe_id") or "")
        if not pid:
            m = _PROBE_ID_RE.search(str(c.get("reason", "")))
            pid = m.group(0) if m else ""
        if not pid or pid in seen:
            continue
        seen.add(pid)
        out.append({
            "probe_id": pid,
            "axis": str(c.get("dimension") or "").upper(),
            "candidate": str(c.get("candidate") or ""),
            "shadow": bool(c.get("non_authoritative")),
        })
    return out


def is_present(plan_body: str = "", manifest: dict[str, Any] | None = None) -> bool:
    return any(not p["shadow"] for p in activated_probes(plan_body, manifest))


def _covered_axes(manifest: dict[str, Any]) -> set[str]:
    """Axes the plan has already reasoned about: clarification dimensions and any
    coverage_hypotheses dimensions."""
    axes: set[str] = set()
    clar = manifest.get("clarification") if isinstance(manifest, dict) else None
    if isinstance(clar, dict):
        for dim in clar.get("dimension_space") or []:
            if isinstance(dim, dict) and dim.get("material", True) and dim.get("resolution"):
                axes.add(str(dim.get("axis", "")).upper())
    for hyp in (manifest.get("coverage_hypotheses") or []) if isinstance(manifest, dict) else []:
        if isinstance(hyp, dict) and hyp.get("dimension"):
            axes.add(str(hyp.get("dimension", "")).upper())
            if hyp.get("implied_dimension_axis"):
                axes.add(str(hyp["implied_dimension_axis"]).upper())
    # UACGAP-06: a populated entry_point_equivalence block is a first-class way to
    # disposition the ENTRY_POINT axis (its own gate validates the block's shape),
    # so it satisfies an ENTRY_POINT probe just like a clarification dimension.
    epe = manifest.get("entry_point_equivalence") if isinstance(manifest, dict) else None
    if isinstance(epe, dict) and isinstance(epe.get("candidates"), list) and epe["candidates"]:
        axes.add("ENTRY_POINT")
    axes.discard("")
    return axes


def _dispositions(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in (manifest.get(DISPOSITION_BLOCK) or []) if isinstance(manifest, dict) else []:
        if isinstance(item, dict) and item.get("probe_id"):
            out[str(item["probe_id"])] = item
    return out


def validate(plan_body: str = "", manifest: dict[str, Any] | None = None) -> list[str]:
    manifest_data = manifest if isinstance(manifest, dict) else {}
    probes = [p for p in activated_probes(plan_body, manifest_data) if not p["shadow"]]
    if not probes:
        return []
    covered = _covered_axes(manifest_data)
    disp = _dispositions(manifest_data)
    problems: list[str] = []
    for p in probes:
        pid, axis = p["probe_id"], p["axis"]
        if axis in covered:
            continue
        d = disp.get(pid)
        if isinstance(d, dict):
            verdict = str(d.get("disposition", "")).strip().upper()
            if verdict in VALID_DISPOSITIONS and str(d.get("reason", "")).strip():
                continue
        problems.append(_problem(
            f"probe {pid} ({axis}) matched the evidence but its dimension is not covered - "
            f"record a coverage hypothesis with implied_dimension_axis {axis}, "
            f"a resolved clarification dimension, or a "
            f"{DISPOSITION_BLOCK} entry {{probe_id:{pid}, disposition, reason}} explicitly "
            f"rejecting or scoping it out"
        ))
    return problems


def summarize(plan_body: str = "", manifest: dict[str, Any] | None = None) -> str:
    probes = activated_probes(plan_body, manifest)
    if not probes:
        return "probe coverage gate: no probe activated"
    active = [p["probe_id"] for p in probes if not p["shadow"]]
    shadow = [p["probe_id"] for p in probes if p["shadow"]]
    parts = [f"probe coverage gate: {len(active)} active probe(s) {active}"]
    if shadow:
        parts.append(f"shadow (advisory) {shadow}")
    problems = validate(plan_body, manifest)
    parts.append("CLEAN" if not problems else f"{len(problems)} uncovered")
    return " | ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe-coverage enforcement gate")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    plan_body = args.plan.read_text(encoding="utf-8") if args.plan.exists() else ""
    manifest_data = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest.exists() else {}
    problems = validate(plan_body, manifest_data)
    if problems:
        for p in problems:
            print(p)
        return 1
    print(summarize(plan_body, manifest_data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
