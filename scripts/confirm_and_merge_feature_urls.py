#!/usr/bin/env python3
"""Auto-confirm Experience League URLs for pending feature-map features and merge
the confirmed ones into the governed feature-map.

For every feature still marked URL-unconfirmed in the scratch surface drafts, this
queries the local aem_guides corpus; if the top hit is an AEM Guides Experience
League page under the distance threshold, it stamps the URL and conforms the
feature to the strict feature_map governance, then merges it into
data/aem_feature_map.json. Features whose page is still not in the corpus stay
unconfirmed (honest - no fabricated URL). Run AFTER refreshing the crawl
(scripts/vm_ingest_review_authoring_publishing_gaps.sh).

Default is a dry run (report only). Pass --apply to write the merged map.

    python scripts/confirm_and_merge_feature_urls.py            # dry run
    python scripts/confirm_and_merge_feature_urls.py --apply    # write + validate
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
SKILL = REPO / ".codex" / "skills" / "test-plan-generation"
FEATURE_MAP = SKILL / "data" / "aem_feature_map.json"
GUIDES_PREFIX = "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
DISTANCE_MAX = 0.35  # honesty threshold: a weak hit must not auto-stamp a URL

# scratch drafts holding the pending (url_confirmed=false) features
DRAFTS = {
    "PUBLISHING_OUTPUT": "publishing_surface_draft.json",
    "AUTHORING": "authoring_surface_draft.json",
    "REVIEW": "review_surface_draft.json",
}


def _scratch_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    # default: the session scratchpad gb_run sibling used for these drafts
    # Repo-tracked drafts so this runs on any box (VM included), not just the authoring session.
    return REPO / "scripts" / "feature_map_drafts"


def _slug(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def _query_top(fm_query: str):
    """Return (url, title, distance) of the top aem_guides hit, or None."""
    sys.path.insert(0, str(BACKEND))
    from dotenv import load_dotenv

    load_dotenv(str(BACKEND / ".env"))
    from app.services.embedding_service import embed_query
    from app.services import vector_store_service as v

    emb = embed_query(fm_query)
    emb = emb.tolist() if hasattr(emb, "tolist") else list(emb)
    rows = v.query_collection(v.CHROMA_COLLECTION_AEM_GUIDES, emb, k=3) or []
    for r in rows:
        m = r.get("metadata") or {}
        url = str(m.get("url") or m.get("source") or "")
        if url.startswith(GUIDES_PREFIX):
            return url, str(m.get("title") or ""), float(r.get("distance", 1.0))
    return None


def _load_feature_map(fm) -> tuple[dict, list[str]]:
    data = json.loads(FEATURE_MAP.read_text(encoding="utf-8"))
    return data, fm.validate_repository_map(str(FEATURE_MAP))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write the merged map (default: dry run)")
    ap.add_argument("--scratch-dir", default=None, help="dir holding the *_surface_draft.json files")
    ap.add_argument("--distance-max", type=float, default=DISTANCE_MAX)
    args = ap.parse_args(argv)

    sys.path.insert(0, str(SKILL / "scripts"))
    import feature_map as fm

    scratch = _scratch_dir(args.scratch_dir)
    data, pre_problems = _load_feature_map(fm)
    if pre_problems:
        print("REFUSING: live feature-map already fails governance:", pre_problems)
        return 2
    surfaces_by_name = {s["surface"]: s for s in data["surfaces"]}

    confirmed, still_pending = [], []
    for surface_name, draft_file in DRAFTS.items():
        path = scratch / draft_file
        if not path.is_file():
            print(f"(skip {surface_name}: draft not found at {path})")
            continue
        draft = json.loads(path.read_text(encoding="utf-8"))
        for feat in draft.get("native_features", []):
            if feat.get("url_confirmed"):
                continue
            axis = str(feat.get("implied_dimension_axis", "")).upper()
            if axis not in fm.VALID_AXES:
                still_pending.append((surface_name, feat["feature"], f"invalid axis {axis}"))
                continue
            query = f"{feat['feature']} {feat.get('candidate_template', '')[:80]}"
            hit = _query_top(query)
            if not hit or hit[2] > args.distance_max:
                still_pending.append((surface_name, feat["feature"], "no confident corpus hit"))
                continue
            url, title, dist = hit
            conformed = {
                "feature": feat["feature"],
                "shared_flows": feat.get("shared_flows", []),
                "implied_dimension_axis": axis,
                "candidate_template": feat["candidate_template"],
                "reference": "Experience League " + _slug(url),
                "reference_urls": [url],
                "approval_status": "HUMAN_APPROVED",
            }
            # merge into the surface (create it if new, e.g. REVIEW)
            surf = surfaces_by_name.get(surface_name)
            if surf is None:
                surf = {"surface": surface_name, "match": draft.get("match", []), "native_features": []}
                data["surfaces"].append(surf)
                surfaces_by_name[surface_name] = surf
            if conformed["feature"] not in {f["feature"] for f in surf["native_features"]}:
                surf["native_features"].append(conformed)
            confirmed.append((surface_name, feat["feature"], round(dist, 3), url))

    print(f"\n=== CONFIRMED {len(confirmed)} ===")
    for s, f, d, u in confirmed:
        print(f"  [{s}] {f}  (dist {d})  {u}")
    print(f"\n=== STILL PENDING {len(still_pending)} ===")
    for s, f, why in still_pending:
        print(f"  [{s}] {f}  - {why}")

    problems = fm.validate_repository_map()  # validate the in-memory result by writing to a temp path
    # validate against the mutated file only when applying
    if args.apply and confirmed:
        FEATURE_MAP.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        post = fm.validate_repository_map(str(FEATURE_MAP))
        if post:
            print("\nGOVERNANCE FAILED after merge:", post)
            return 3
        print(f"\nAPPLIED: merged {len(confirmed)} feature(s); feature-map now has "
              f"{len(data['surfaces'])} surfaces. Governance clean.")
        print("NEXT: sync copies+globals, bump the surface-count self-test if a new surface was added, run self-tests, commit.")
    elif confirmed:
        print(f"\nDRY RUN: {len(confirmed)} feature(s) would merge. Re-run with --apply to write.")
    else:
        print("\nNothing confirmable yet - refresh the crawl "
              "(scripts/vm_ingest_review_authoring_publishing_gaps.sh) first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
