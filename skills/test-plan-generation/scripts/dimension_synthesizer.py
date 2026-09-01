"""Evidence-driven dimension synthesizer (UACDISCOVER-01).

Raises DISCOVERY, not enforcement. From the manifest's own evidence (behavior
model + evidence catalog + recorded RAG probes), it proposes candidate test
dimensions - including ones the ticket text never named - as INVESTIGATION
CANDIDATEs that flow into the existing coverage_hypotheses -> verifications
pipeline and clarification_gate.dimension_space. It never authors an AC and never
hard-fails; run_gates surfaces the candidates that are not yet represented as a
non-blocking DISCOVERY review note.

Five generators, each candidate tagged with the generating evidence and generator:
  * CODE_NEIGHBORHOOD  - generic signals in cited code text/paths.
  * RAG_NEIGHBORHOOD   - recorded product-RAG probes.
  * HISTORY_NEIGHBORHOOD - same-component recurring defects (search_jira_history or
    the offline jira_qa corpus). When neither history source is available it records
    a gap; it never fabricates a candidate.
  * LEARNED_PROBE - governed, reusable probes derived from Human-confirmed misses.
  * FEATURE_MAP - curated native AEM/Guides features that ride a matched shared flow.

Generic only.  Standard library only.  No concrete symbol or Jira key is hardcoded;
the signal map is generic vocabulary, not product identifiers.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


BLOCK_ACTIVATORS = ("behavior_model", "evidence_catalog")

# Generic token -> (dimension, candidate_template). Vocabulary only; no product
# symbol, class, config key, or Jira id appears here.
CODE_SIGNAL_MAP: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (
        ("metadata", "jcr:content", "jcr ", "repository node", "property", "attribute value"),
        "VALUE_SET_CHANNEL",
        "value provenance beyond the authoring UI - repository node (CRX/DE), source file, API/import, migration",
    ),
    (
        ("baseclass", "base class", "abstract ", "extends", "override", "superclass", "shared ", "common "),
        "CODE_PATH_CONSUMER",
        "other consumers of the shared code path (each output type, engine, caller, or surface)",
    ),
    (
        ("preset", "output type", "publish", "render", "transform", "dita-ot", "dita ot"),
        "OUTPUT_PRESET",
        "behavior across output presets and DITA-OT processing on/off",
    ),
    (
        ("migrat", "upgrade", "version boundary", "backward compat", "non-uuid", "uuid"),
        "MIGRATION_PATH",
        "pre-migration state, the migration itself, mixed-version coexistence, and rollback",
    ),
    (
        ("concurren", "parallel", "lock", "queue", "job ", "thread", "async"),
        "REPRO_DIMENSION",
        "concurrency and terminal-state matrix (success, failure, cancel, retry exhaustion)",
    ),
    (
        ("permission", "role", "acl", "authoriz", "privilege", "entitlement"),
        "PERMISSION_ROLE",
        "permission/role enforcement and privilege-escalation boundary on the changed path",
    ),
)


def _text_of(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return " ".join(_text_of(v) for v in value)
    if isinstance(value, dict):
        return " ".join(_text_of(v) for v in value.values())
    return ""


def _evidence_texts(manifest: dict) -> list[tuple[str, str]]:
    """Return (evidence_label, text) pairs from catalog + behavior model."""
    pairs: list[tuple[str, str]] = []
    catalog = manifest.get("evidence_catalog")
    if isinstance(catalog, dict):
        catalog = catalog.get("sources") or catalog.get("entries")
    if isinstance(catalog, list):
        for entry in catalog:
            if isinstance(entry, dict):
                label = str(entry.get("id") or entry.get("source_id") or "evidence")
                text = " ".join(
                    str(entry.get(k, "")) for k in ("source_ref", "note", "document", "text", "artifact")
                )
                pairs.append((label, text))
    bm = manifest.get("behavior_model")
    if isinstance(bm, dict):
        for fact in bm.get("facts") or []:
            if isinstance(fact, dict):
                eids = [e for e in (fact.get("evidence_ids") or []) if isinstance(e, str)]
                label = eids[0] if eids else "behavior_model"
                pairs.append((label, str(fact.get("fact", ""))))
        for key in ("read_paths", "write_paths", "update_paths", "consumers", "processors", "configuration_branches"):
            text = _text_of(bm.get(key))
            if text.strip():
                pairs.append((f"behavior_model.{key}", text))
    return pairs


def _match_signals(pairs: list[tuple[str, str]], generator: str) -> list[dict]:
    seen: dict[str, dict] = {}
    for label, text in pairs:
        low = text.lower()
        for tokens, dimension, template in CODE_SIGNAL_MAP:
            if any(tok in low for tok in tokens):
                cand = seen.get(dimension)
                if cand is None:
                    seen[dimension] = {
                        "hypothesis_id": "",
                        "dimension": dimension,
                        "candidate": template,
                        "reason": f"{generator} signal detected in evidence text",
                        "technical_basis": [f"{generator}: token match in {label}"],
                        "current_evidence": [label],
                        "status": "INVESTIGATION_CANDIDATE",
                        "requires_more_evidence": True,
                        "confidence": 0.4,
                        "equivalence_key": f"{generator}:{dimension}",
                        "generator": generator,
                    }
                else:
                    if label not in cand["current_evidence"]:
                        cand["current_evidence"].append(label)
    return list(seen.values())


def _history_candidates(manifest: dict) -> tuple[list[dict], list[str]]:
    """Best-effort same-component history candidates; records a gap if no source."""
    gaps: list[str] = []
    # Live history evidence, when the author recorded it in the manifest.
    if manifest.get("indexed_history_run") is True and isinstance(
        manifest.get("jira_history_queries"), list
    ) and manifest["jira_history_queries"]:
        cands: list[dict] = []
        for i, q in enumerate(manifest["jira_history_queries"], start=1):
            if not isinstance(q, dict):
                continue
            comp = str(q.get("component", "")).strip()
            cands.append({
                "hypothesis_id": "",
                "dimension": "DOWNSTREAM_REGRESSION",
                "candidate": f"recurring same-component defect classes ({comp or 'component'}) as negative/regression dimensions",
                "reason": "HISTORY_NEIGHBORHOOD: recorded search_jira_history query",
                "technical_basis": [f"HISTORY_NEIGHBORHOOD: jira_history_queries[{i}]"],
                "current_evidence": [f"jira_history:{q.get('scope', 'query')}"],
                "status": "INVESTIGATION_CANDIDATE",
                "requires_more_evidence": True,
                "confidence": 0.3,
                "equivalence_key": "HISTORY_NEIGHBORHOOD:same-component",
                "generator": "HISTORY_NEIGHBORHOOD",
            })
        return cands, gaps
    gaps.append(
        "HISTORY_NEIGHBORHOOD: no live search_jira_history run recorded and no offline "
        "jira_qa result supplied in the manifest; no history candidate fabricated"
    )
    return [], gaps


def synthesize(manifest: dict | None) -> dict:
    """Return {candidates, gaps, activated}. Never raises, never fabricates."""
    data = manifest if isinstance(manifest, dict) else {}
    if not any(data.get(k) for k in BLOCK_ACTIVATORS):
        return {"candidates": [], "gaps": ["not activated: no behavior_model or evidence_catalog"], "activated": False}

    pairs = _evidence_texts(data)
    candidates = _match_signals(pairs, "CODE_NEIGHBORHOOD")

    rag = data.get("rag_probes")
    if isinstance(rag, list) and rag:
        rag_pairs = [(f"rag_probe:{p[:40]}", str(p)) for p in rag if isinstance(p, str)]
        candidates += _match_signals(rag_pairs, "RAG_NEIGHBORHOOD")
    gaps: list[str] = []
    if not (isinstance(rag, list) and rag):
        gaps.append("RAG_NEIGHBORHOOD: no rag_probes recorded; no RAG candidate generated")

    hist_cands, hist_gaps = _history_candidates(data)
    candidates += hist_cands
    gaps += hist_gaps

    # LEARNED_PROBE candidates from the miss-probe library (UACDISCOVER-02).
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "miss_probe_library", Path(__file__).with_name("miss_probe_library.py")
        )
        mpl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mpl)  # type: ignore[union-attr]
        candidates += mpl.candidates_for(pairs)
    except Exception as exc:  # pragma: no cover - defensive
        gaps.append(f"LEARNED_PROBE: miss-probe library unavailable ({exc})")

    # FEATURE_MAP candidates from the human-approved AEM/Guides domain checklist
    # (UACDISCOVER-03). This is advisory and fail-open: a missing or malformed map
    # contributes no candidates and cannot make canonical generation unavailable.
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "feature_map", Path(__file__).with_name("feature_map.py")
        )
        feature_map = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(feature_map)  # type: ignore[union-attr]
        candidates += feature_map.candidates_for(pairs)
    except Exception as exc:  # pragma: no cover - defensive
        gaps.append(f"FEATURE_MAP: curated feature map unavailable ({exc})")

    # Assign stable ids.
    for i, cand in enumerate(candidates, start=1):
        cand["hypothesis_id"] = f"DS-{i:02d}"
    return {"candidates": candidates, "gaps": gaps, "activated": True}


def _represented_dimensions(manifest: dict) -> set[str]:
    reps: set[str] = set()
    for h in manifest.get("coverage_hypotheses") or []:
        if isinstance(h, dict) and h.get("dimension"):
            reps.add(str(h["dimension"]).upper())
    clar = manifest.get("clarification")
    if isinstance(clar, dict):
        for d in clar.get("dimension_space") or []:
            if isinstance(d, dict) and d.get("axis"):
                reps.add(str(d["axis"]).upper())
    return reps


def _represented_feature_map_candidates(manifest: dict) -> set[str]:
    """Return exact FEATURE_MAP equivalence keys explicitly dispositioned.

    A broad dimension such as CODE_PATH_CONSUMER does not prove that every native
    feature on a matched shared flow was investigated. Feature-map candidates are
    therefore suppressed only by their exact equivalence key (or surface+feature
    tags), while all pre-existing generators keep the legacy axis-level behavior.
    """
    represented: set[str] = set()
    blocks: list[Any] = list(manifest.get("coverage_hypotheses") or [])
    clarification = manifest.get("clarification")
    if isinstance(clarification, dict):
        blocks += list(clarification.get("dimension_space") or [])
    for item in blocks:
        if not isinstance(item, dict):
            continue
        equivalence_key = str(item.get("equivalence_key", "")).strip().casefold()
        if equivalence_key.startswith("feature_map:"):
            represented.add(equivalence_key)
        surface = str(item.get("surface", "")).strip().upper()
        feature = str(item.get("feature", "")).strip()
        if surface and feature:
            represented.add(
                f"feature_map:{surface}:{re.sub(r'[^a-z0-9]+', '-', feature.casefold()).strip('-')}"
            )
    return represented


def is_present(manifest: dict | None = None) -> bool:
    data = manifest if isinstance(manifest, dict) else {}
    return any(data.get(k) for k in BLOCK_ACTIVATORS)


def review_notes(manifest: dict | None = None) -> list[str]:
    """Non-blocking DISCOVERY notes for candidates not yet represented."""
    data = manifest if isinstance(manifest, dict) else {}
    result = synthesize(data)
    if not result["activated"]:
        return []
    represented = _represented_dimensions(data)
    represented_feature_map = _represented_feature_map_candidates(data)
    notes: list[str] = []
    for cand in result["candidates"]:
        if cand.get("generator") == "FEATURE_MAP":
            if str(cand.get("equivalence_key", "")).casefold() in represented_feature_map:
                continue
        elif cand["dimension"].upper() in represented:
            continue
        feature_context = (
            f", feature={cand.get('feature')}, reference={cand.get('reference')}"
            if cand.get("generator") == "FEATURE_MAP"
            else ""
        )
        notes.append(
            f"DISCOVERY: unrepresented dimension {cand['dimension']} "
            f"(generator={cand['generator']}{feature_context}, "
            f"evidence={','.join(cand['current_evidence'])}): "
            f"{cand['candidate']} - dispose or reject it in coverage_hypotheses/dimension_space"
        )
    return notes


def summarize(manifest: dict | None = None) -> str:
    result = synthesize(manifest)
    if not result["activated"]:
        return "dimension synthesizer: not activated"
    return (
        f"dimension synthesizer: {len(result['candidates'])} candidate(s), "
        f"{len(result['gaps'])} gap(s)"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evidence-driven dimension synthesizer (UACDISCOVER-01)")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    manifest = (
        json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest.exists() else {}
    )
    result = synthesize(manifest)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(summarize(manifest))
        for note in review_notes(manifest):
            print(f"REVIEW {note}")
        for gap in result["gaps"]:
            print(f"GAP {gap}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
