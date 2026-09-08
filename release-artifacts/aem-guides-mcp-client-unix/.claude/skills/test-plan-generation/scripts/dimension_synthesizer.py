"""Evidence-driven dimension synthesizer (UACDISCOVER-01).

Raises DISCOVERY, not enforcement. From the manifest's own evidence (behavior
model + evidence catalog + recorded RAG probes), it proposes candidate test
dimensions - including ones the ticket text never named - as INVESTIGATION
CANDIDATEs that flow into the existing coverage_hypotheses -> verifications
pipeline and clarification_gate.dimension_space. It never authors an AC and never
hard-fails; run_gates surfaces candidates without evidence-backed terminal
decisions as DISCOVERY review notes (exit-compatible, but non-postable).

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
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import coverage_hypotheses
import discovery_disposition
import recorded_neighbor_discovery


BLOCK_ACTIVATORS = ("behavior_model", "evidence_catalog", "construct_relationships")
MAX_OFFLINE_DOC_QUERIES = 6
OFFLINE_DOC_RESULTS_PER_QUERY = 4
MAX_OFFLINE_DOC_CANDIDATES = 8
MAX_OFFLINE_DOC_DISTANCE = 0.5
OFFLINE_HISTORY_RESULTS = 5

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
        for key in ("trigger", "operations", "inputs", "outputs", "affected_state",
                    "read_paths", "write_paths", "update_paths", "consumers", "processors",
                    "configuration_branches", "publishing_modes"):
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


def _load_sibling_module(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name(filename))
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_offline_retrieval():
    """Test seam and fail-open loader for the optional local-Chroma provider."""
    try:
        return _load_sibling_module("offline_retrieval", "offline_retrieval.py")
    except Exception:
        return None


def _load_feature_map():
    try:
        return _load_sibling_module("feature_map", "feature_map.py")
    except Exception:
        return None


def _stable_suffix(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _query_text(pairs: list[tuple[str, str]], limit: int = 1_200) -> str:
    return " ".join(" ".join(text.split()) for _, text in pairs if text.strip())[:limit]


def _feature_query_groups(feature_candidates: list[dict]) -> list[tuple[str, str, tuple[str, ...]]]:
    """Group one documented surface/source, then share the budget across surfaces.

    Several sibling features may live on the same documentation page. Combining
    their query vocabulary saves calls; round-robin ordering prevents a large
    early surface from starving a smaller matched surface. No product names or
    feature-specific priorities participate in this scheduling.
    """
    surfaces: dict[str, dict[tuple, dict]] = {}
    for candidate in feature_candidates:
        feature = str(candidate.get("feature", "")).strip()
        if not feature:
            continue
        surface = str(candidate.get("surface") or "surface").strip()
        references = tuple(sorted({str(value).strip()
                                   for value in candidate.get("reference_urls") or []
                                   if str(value).strip()}))
        # Without a source, do not merge unrelated feature names into one query.
        key = (references, "" if references else feature.casefold())
        groups = surfaces.setdefault(surface, {})
        group = groups.setdefault(key, {"features": [], "flows": [], "references": references})
        if feature not in group["features"]:
            group["features"].append(feature)
        for value in candidate.get("shared_flows") or []:
            flow = str(value).strip()
            if flow and flow not in group["flows"]:
                group["flows"].append(flow)

    buckets = [(surface, list(groups.values())) for surface, groups in surfaces.items()]
    queries: list[tuple[str, str, tuple[str, ...]]] = []
    for index in range(max((len(groups) for _, groups in buckets), default=0)):
        for surface, groups in buckets:
            if index >= len(groups):
                continue
            group = groups[index]
            queries.append((
                f"feature_map:{surface}:{'|'.join(group['features'])}",
                " ".join((*group["features"], *group["flows"])),
                group["references"],
            ))
    return queries


def _offline_doc_query_plan(
    pairs: list[tuple[str, str]],
    rag_probes: object,
    feature_candidates: list[dict],
) -> tuple[list[tuple[str, str, tuple[str, ...]]], list[str]]:
    """Return bounded queries and exact feature groups deferred by the budget."""
    queries: list[tuple[str, str, tuple[str, ...]]] = []
    if isinstance(rag_probes, list):
        for index, probe in enumerate(rag_probes, start=1):
            if isinstance(probe, str) and probe.strip():
                queries.append((f"rag_probe:{index}", probe.strip(), ()))
            if len(queries) >= 2:
                break

    behavior = _query_text(pairs)
    unique: list[tuple[str, str, tuple[str, ...]]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()

    def append_query(query: tuple[str, str, tuple[str, ...]]) -> bool:
        label, text, references = query
        normalized = " ".join(text.casefold().split())
        key = (normalized, references)
        if not normalized or key in seen:
            return False
        seen.add(key)
        unique.append((label, text, references))
        return True

    for query in queries:
        append_query(query)
    # Reserve current behavior, including when two explicit RAG probes are present.
    feature_budget = MAX_OFFLINE_DOC_QUERIES - len(unique) - bool(behavior)
    deferred: list[str] = []
    feature_count = 0
    for query in _feature_query_groups(feature_candidates):
        key = (" ".join(query[1].casefold().split()), query[2])
        if key in seen:
            continue
        if feature_count >= feature_budget:
            deferred.append(query[0])
        elif append_query(query):
            feature_count += 1
    if behavior:
        append_query(("current_behavior", behavior, ()))
    return unique, deferred


def _offline_doc_queries(
    pairs: list[tuple[str, str]],
    rag_probes: object,
    feature_candidates: list[dict],
) -> list[tuple[str, str, tuple[str, ...]]]:
    """Compatibility view of the bounded, surface-diverse query plan."""
    return _offline_doc_query_plan(pairs, rag_probes, feature_candidates)[0]


def _offline_rag_candidates(
    offline,
    pairs: list[tuple[str, str]],
    rag_probes: object,
    feature_candidates: list[dict],
) -> tuple[list[dict], list[str]]:
    queries, deferred = _offline_doc_query_plan(pairs, rag_probes, feature_candidates)
    budget_gaps = ([
        f"RAG_NEIGHBORHOOD: {len(deferred)} feature-map query group(s) deferred by the "
        f"{MAX_OFFLINE_DOC_QUERIES}-query budget; not retrieved: {', '.join(deferred)}"
    ] if deferred else [])
    if offline is None:
        return [], budget_gaps + [
            "RAG_NEIGHBORHOOD: offline retrieval helper unavailable; no offline RAG candidate fabricated"
        ]
    if not queries:
        return [], []

    candidates: list[dict] = []
    seen_sources: set[str] = set()
    last_reason = "query_returned_no_rows"
    for query_index, (query_label, query, expected_references) in enumerate(queries):
        rows = offline.retrieve_docs(query, OFFLINE_DOC_RESULTS_PER_QUERY)
        status = offline.retrieval_status("docs")
        last_reason = str(status.get("reason") or last_reason)
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_url = str(row.get("url") or "").strip()
            if expected_references and row_url not in set(expected_references):
                continue
            distance = row.get("distance")
            if isinstance(distance, (int, float)) and float(distance) > MAX_OFFLINE_DOC_DISTANCE:
                continue
            source_ref = str(row.get("source_ref") or row.get("url") or row.get("title") or "").strip()
            if not source_ref or source_ref.casefold() in seen_sources:
                continue
            seen_sources.add(source_ref.casefold())
            title = str(row.get("title") or "").strip()
            snippet = str(row.get("snippet") or "").strip()
            display = title or (snippet[:180] + ("..." if len(snippet) > 180 else ""))
            evidence = f"OFFLINE_CHROMA: {display}"
            if row.get("url"):
                evidence += f" <{row['url']}>"
            candidates.append(
                {
                    "hypothesis_id": "",
                    "dimension": "DOWNSTREAM_REGRESSION",
                    "candidate": f"investigate adjacent documented product behavior: {display}",
                    "reason": (
                        "RAG_NEIGHBORHOOD: offline product-documentation neighbor retrieved; "
                        "verify applicability and inspect the underlying source before promotion"
                    ),
                    "technical_basis": [
                        f"RAG_NEIGHBORHOOD:offline_query:{query_label}",
                        f"source_ref:{source_ref}",
                        *(f"expected_reference:{value}" for value in expected_references),
                    ],
                    "current_evidence": [evidence],
                    "status": "INVESTIGATION_CANDIDATE",
                    "requires_more_evidence": True,
                    "confidence": 0.3,
                    "equivalence_key": f"RAG_NEIGHBORHOOD:{_stable_suffix(source_ref)}",
                    "generator": "RAG_NEIGHBORHOOD",
                    "source": "OFFLINE_CHROMA",
                    "source_label": "OFFLINE_CHROMA",
                    "authority_class": "SUPPORTING_DISCOVERY",
                    "non_authoritative": True,
                    "advisory_only": True,
                    "offline_retrieval": True,
                    "retrieved_title": title,
                    "retrieved_url": str(row.get("url") or ""),
                    "distance": distance,
                }
            )
            if len(candidates) >= MAX_OFFLINE_DOC_CANDIDATES:
                break
        provider_status = str(status.get("status") or "").upper()
        if provider_status in {"UNAVAILABLE", "ERROR"}:
            budget_gaps.append(
                f"RAG_NEIGHBORHOOD: retrieval stopped with provider status {provider_status}; "
                f"{len(queries) - query_index - 1} planned query group(s) not executed; "
                "retained partial supporting results only"
            )
            break
        if len(candidates) >= MAX_OFFLINE_DOC_CANDIDATES:
            budget_gaps.append(
                "RAG_NEIGHBORHOOD: retrieval stopped with status CANDIDATE_LIMIT; "
                f"{len(queries) - query_index - 1} planned query group(s) not executed; "
                "retained bounded supporting results only"
            )
            break
    if candidates:
        return candidates, budget_gaps
    return [], budget_gaps + [
        f"RAG_NEIGHBORHOOD: offline retrieval produced no usable result ({last_reason}); "
        "no offline RAG candidate fabricated"
    ]


def _issue_component(manifest: dict) -> str:
    issue = manifest.get("issue") if isinstance(manifest.get("issue"), dict) else {}
    raw = issue.get("components") or issue.get("component") or manifest.get("component")
    if isinstance(raw, list):
        return next((str(value).strip() for value in raw if str(value).strip()), "")
    return str(raw or "").strip()


def _issue_key(manifest: dict) -> str:
    issue = manifest.get("issue") if isinstance(manifest.get("issue"), dict) else {}
    return str(issue.get("key") or manifest.get("jira_key") or "").strip().upper()


def _history_candidates(manifest: dict, pairs: list[tuple[str, str]], offline) -> tuple[list[dict], list[str]]:
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
    component = _issue_component(manifest)
    query = _query_text(pairs)
    if component:
        query = f"{query} {component}".strip()
    if offline is None or not query or not component:
        reason = (
            "offline retrieval helper unavailable" if offline is None
            else "component or behavior query unavailable"
        )
        gaps.append(
            "HISTORY_NEIGHBORHOOD: no live search_jira_history run recorded and "
            f"{reason}; no history candidate fabricated"
        )
        return [], gaps

    rows = offline.retrieve_history(query, component, OFFLINE_HISTORY_RESULTS)
    target_key = _issue_key(manifest)
    cands: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        jira_key = str(row.get("jira_key") or "").strip().upper()
        if not jira_key or jira_key == target_key:
            continue
        title = str(row.get("title") or "").strip()
        display = f"{jira_key}: {title}" if title else jira_key
        cands.append(
            {
                "hypothesis_id": "",
                "dimension": "DOWNSTREAM_REGRESSION",
                "candidate": f"investigate whether same-component defect behavior from {display} can recur on the touched path",
                "reason": (
                    "HISTORY_NEIGHBORHOOD: offline same-component jira_qa neighbor; "
                    "supporting discovery only, not a live history run"
                ),
                "technical_basis": [
                    f"HISTORY_NEIGHBORHOOD:OFFLINE_CHROMA:{jira_key}",
                    f"component:{component}",
                ],
                "current_evidence": [f"OFFLINE_CHROMA: {display}"],
                "status": "INVESTIGATION_CANDIDATE",
                "requires_more_evidence": True,
                "confidence": 0.25,
                "equivalence_key": f"HISTORY_NEIGHBORHOOD:{jira_key}",
                "generator": "HISTORY_NEIGHBORHOOD",
                "source": "OFFLINE_CHROMA",
                "source_label": "OFFLINE_CHROMA",
                "authority_class": "SUPPORTING_DISCOVERY",
                "non_authoritative": True,
                "advisory_only": True,
                "offline_retrieval": True,
                "indexed_history_run": False,
                "jira_key": jira_key,
                "retrieved_title": title,
                "distance": row.get("distance"),
            }
        )
    if cands:
        return cands, gaps
    status = offline.retrieval_status("history")
    gaps.append(
        "HISTORY_NEIGHBORHOOD: no live search_jira_history run recorded and offline "
        f"jira_qa produced no usable same-component result ({status.get('reason', 'empty')}); "
        "no history candidate fabricated"
    )
    return [], gaps


def synthesize(manifest: dict | None) -> dict:
    """Return {candidates, gaps, activated}. Never raises, never fabricates."""
    data = manifest if isinstance(manifest, dict) else {}
    if not any(data.get(k) for k in BLOCK_ACTIVATORS):
        return {"candidates": [], "gaps": ["not activated: no behavior_model, evidence_catalog or construct_relationships"], "activated": False}

    pairs = _evidence_texts(data)
    exploration = coverage_hypotheses.generate_from_model(data)
    candidates = exploration["candidates"] + _match_signals(pairs, "CODE_NEIGHBORHOOD")
    # Preserve each inspected sibling/caller identity, not just the broad family.
    # These are recorded discoveries, not a claim of an exhaustive code search.
    candidates += recorded_neighbor_discovery.candidates_for(data)

    # Load the curated checklist before offline RAG. Matched entries may provide
    # bounded, Human-approved query vocabulary; they are never treated as evidence.
    feature_candidates: list[dict] = []
    feature_map = _load_feature_map()
    if feature_map is None:
        feature_gap = "FEATURE_MAP: curated feature map unavailable"
    else:
        try:
            feature_candidates = feature_map.candidates_for(pairs)
            feature_gap = ""
        except Exception as exc:  # pragma: no cover - defensive
            feature_gap = f"FEATURE_MAP: curated feature map unavailable ({type(exc).__name__})"

    rag = data.get("rag_probes")
    if isinstance(rag, list) and rag:
        rag_pairs = [(f"rag_probe:{p[:40]}", str(p)) for p in rag if isinstance(p, str)]
        candidates += _match_signals(rag_pairs, "RAG_NEIGHBORHOOD")
    gaps: list[str] = []

    offline = _load_offline_retrieval()
    offline_rag, offline_rag_gaps = _offline_rag_candidates(
        offline, pairs, rag, feature_candidates
    )
    candidates += offline_rag
    gaps += offline_rag_gaps
    if not (isinstance(rag, list) and rag) and not offline_rag:
        # Preserve the original gap text for callers that already depend on it.
        gaps.append("RAG_NEIGHBORHOOD: no rag_probes recorded; no RAG candidate generated")

    hist_cands, hist_gaps = _history_candidates(data, pairs, offline)
    candidates += hist_cands
    gaps += hist_gaps

    # LEARNED_PROBE candidates from the miss-probe library (UACDISCOVER-02).
    try:
        mpl = _load_sibling_module("miss_probe_library", "miss_probe_library.py")
        if mpl is None:
            raise RuntimeError("miss-probe module loader unavailable")
        candidates += mpl.candidates_for(pairs)
    except Exception as exc:  # pragma: no cover - defensive
        gaps.append(f"LEARNED_PROBE: miss-probe library unavailable ({exc})")

    # FEATURE_MAP itself remains an independent advisory generator. Offline RAG
    # results above exist only when a current local source was actually retrieved.
    candidates += feature_candidates
    if feature_gap:
        gaps.append(feature_gap)

    # Customer identity stays in corpus-side profile metadata, never in routing
    # code or the Human-approved product feature map. Every match is advisory.
    try:
        profiles = _load_sibling_module("customer_discovery", "customer_discovery.py")
        if profiles is None:
            raise RuntimeError("profile loader unavailable")
        profile_result = profiles.discover(data, pairs)
        candidates += profile_result["candidates"]
        gaps += [f"CUSTOMER_PROFILE: {gap}" for gap in profile_result["gaps"]]
    except Exception as exc:
        gaps.append(f"CUSTOMER_PROFILE: unavailable ({type(exc).__name__}); no advice fabricated")

    # Normalize discovery axes into the existing v3 vocabulary. Keep the exact
    # axis/probe/feature identity: a broad family cannot stand in for its siblings.
    for cand in candidates:
        axis = cand["dimension"]
        if axis in coverage_hypotheses.DISCOVERY_DIMENSION_BY_AXIS:
            cand.setdefault("implied_dimension_axis", axis)
            cand["dimension"] = coverage_hypotheses.DISCOVERY_DIMENSION_BY_AXIS[axis]
        cand["hypothesis_id"] = "DS-" + _stable_suffix(
            f"{cand['generator']}:{cand['dimension']}:{cand.get('equivalence_key') or cand['candidate']}"
        )
    # Recorded history queries can share a family. Collapse only exact family
    # keys, preserving all generator provenance on the retained representative.
    kept = {}
    for cand in candidates:
        key = (cand["dimension"], cand.get("equivalence_key") or cand["candidate"])
        if key in kept:
            for field in ("technical_basis", "current_evidence"):
                kept[key][field] = list(dict.fromkeys(kept[key][field] + cand[field]))
        else:
            kept[key] = cand
    return {"candidates": list(kept.values()), "gaps": gaps, "activated": True,
            "explorers": exploration["explorers"]}


def is_present(manifest: dict | None = None) -> bool:
    data = manifest if isinstance(manifest, dict) else {}
    return any(data.get(k) for k in BLOCK_ACTIVATORS)


def review_notes(manifest: dict | None = None) -> list[str]:
    """Exit-compatible, non-postable notes until each discovery is dispositioned."""
    data = manifest if isinstance(manifest, dict) else {}
    result = synthesize(data)
    if not result["activated"]:
        return []
    notes: list[str] = []
    for cand in result["candidates"]:
        reason = discovery_disposition.review_reason(cand, data)
        if not reason:
            continue
        feature_context = (
            f", feature={cand.get('feature')}, reference={cand.get('reference')}"
            if cand.get("generator") == "FEATURE_MAP"
            else ""
        )
        source_context = (
            f", source_label={cand.get('source_label')}, authority={cand.get('authority_class')}"
            if cand.get("source_label")
            else ""
        )
        notes.append(
            f"DISCOVERY: unrepresented dimension {cand.get('implied_dimension_axis') or cand['dimension']} "
            f"(generator={cand['generator']}{feature_context}{source_context}, "
            f"evidence={','.join(cand['current_evidence'])}): "
            f"{cand['candidate']} - {reason}; bind this exact candidate to verification and disposition"
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
